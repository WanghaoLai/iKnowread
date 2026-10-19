import asyncio
import logging
import os
import signal

import aiomysql
from tortoise import Tortoise

from app.config import settings
from app.migrations.runner import run_migrations


_INSTANCE_LOCK_NAME = "iknowread_application_singleton"
_instance_lock_connection = None
_instance_lock_valid: bool | None = None
_instance_lock_monitor: asyncio.Task | None = None
_instance_lock_io_lock: asyncio.Lock | None = None
logger = logging.getLogger(__name__)


def instance_lock_failed() -> bool:
    """Fast, fail-closed signal used by request middleware."""
    return _instance_lock_valid is False


def _io_lock() -> asyncio.Lock:
    global _instance_lock_io_lock
    if _instance_lock_io_lock is None:
        _instance_lock_io_lock = asyncio.Lock()
    return _instance_lock_io_lock


async def ensure_database():
    """数据库不存在时自动创建（先查存在性，避免 IF NOT EXISTS 的重复告警）。"""
    conn = await aiomysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
    )
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
                (settings.DB_DATABASE,),
            )
            if await cur.fetchone():
                return
            await cur.execute(
                f"CREATE DATABASE `{settings.DB_DATABASE}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conn.close()


async def acquire_instance_lock() -> None:
    """Enforce the single-instance invariant required by in-memory guards."""
    global _instance_lock_connection, _instance_lock_valid
    if _instance_lock_connection is not None:
        return
    connection = await aiomysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        db=settings.DB_DATABASE,
    )
    try:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT GET_LOCK(%s, 0)", (_INSTANCE_LOCK_NAME,))
            row = await cursor.fetchone()
        if not row or int(row[0] or 0) != 1:
            raise RuntimeError(
                "当前架构仅支持一个后端实例；已有实例持有运行锁，请勿增加 worker 或副本"
            )
    except BaseException:
        connection.close()
        raise
    _instance_lock_connection = connection
    _instance_lock_valid = True


async def verify_instance_lock() -> bool:
    """Keep the advisory-lock session alive and prove this process still owns it."""
    global _instance_lock_valid
    connection = _instance_lock_connection
    if connection is None:
        # Unit tests construct the ASGI app without running its lifespan. Only a
        # previously acquired-and-lost lock is a failed production invariant.
        return _instance_lock_valid is not False
    try:
        async with _io_lock():
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT IS_USED_LOCK(%s) = CONNECTION_ID()", (_INSTANCE_LOCK_NAME,)
                )
                row = await cursor.fetchone()
        valid = bool(row and int(row[0] or 0) == 1)
    except asyncio.CancelledError:
        raise
    except Exception:
        valid = False
    if not valid and _instance_lock_valid is not False:
        logger.critical("Application singleton lock was lost; rejecting further requests")
    _instance_lock_valid = valid
    return valid


async def _monitor_instance_lock() -> None:
    while True:
        await asyncio.sleep(max(1.0, settings.INSTANCE_LOCK_HEARTBEAT_SECONDS))
        if not await verify_instance_lock():
            _request_process_restart()
            return


def _request_process_restart() -> None:
    """Gracefully stop the server so the configured supervisor can recover."""
    logger.critical("Stopping process after singleton lock loss")
    os.kill(os.getpid(), signal.SIGTERM)


def start_instance_lock_monitor() -> None:
    global _instance_lock_monitor
    if _instance_lock_monitor is None or _instance_lock_monitor.done():
        _instance_lock_monitor = asyncio.create_task(
            _monitor_instance_lock(), name="database-instance-lock-monitor"
        )


async def stop_instance_lock_monitor() -> None:
    global _instance_lock_monitor
    task = _instance_lock_monitor
    _instance_lock_monitor = None
    if task is None:
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def release_instance_lock() -> None:
    global _instance_lock_connection, _instance_lock_valid, _instance_lock_io_lock
    connection = _instance_lock_connection
    _instance_lock_connection = None
    if connection is None:
        _instance_lock_valid = None
        return
    try:
        async with _io_lock():
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT RELEASE_LOCK(%s)", (_INSTANCE_LOCK_NAME,))
    except Exception:
        # A dropped advisory-lock session is already a terminal lock failure. Do
        # not turn application shutdown into a second, unrelated failure.
        logger.warning("Could not release application singleton lock", exc_info=True)
    finally:
        connection.close()
        _instance_lock_valid = None
        _instance_lock_io_lock = None


def tortoise_config() -> dict:
    return {
        "connections": {
            "default": {
                "engine": "tortoise.backends.mysql",
                "credentials": {
                    "host": settings.DB_HOST,
                    "port": settings.DB_PORT,
                    "database": settings.DB_DATABASE,
                    "user": settings.DB_USER,
                    "password": settings.DB_PASSWORD,
                    "minsize": 1,
                    "maxsize": 10,
                    "charset": "utf8mb4",
                    "echo": settings.DB_ECHO,
                },
            },
        },
        "apps": {
            "models": {
                "models": ["app.models"],
                "default_connection": "default",
            }
        },
        "use_tz": True,
        "timezone": "Asia/Shanghai",
    }


async def init_db() -> None:
    """Initialize Tortoise, then apply explicit versioned migrations."""
    if settings.DB_AUTO_CREATE:
        await ensure_database()
    await Tortoise.init(config=tortoise_config())
    try:
        await run_migrations()
        await acquire_instance_lock()
    except BaseException:
        await Tortoise.close_connections()
        raise


async def close_db() -> None:
    await release_instance_lock()
    await Tortoise.close_connections()

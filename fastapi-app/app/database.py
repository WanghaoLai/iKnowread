import aiomysql
from tortoise import Tortoise

from app.config import settings
from app.migrations.runner import run_migrations


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
    await run_migrations()


async def close_db() -> None:
    await Tortoise.close_connections()

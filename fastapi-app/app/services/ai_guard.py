from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import HTTPException

from app.config import settings


_global_slots: asyncio.Semaphore | None = None
_global_count: int | None = None
_account_slots: dict[int, asyncio.Semaphore] = defaultdict(
    lambda: asyncio.Semaphore(max(1, settings.AI_ACCOUNT_CONCURRENCY))
)


def _global() -> asyncio.Semaphore:
    global _global_slots, _global_count
    count = max(1, min(settings.AI_GLOBAL_CONCURRENCY, 32))
    if _global_slots is None or _global_count != count:
        _global_slots = asyncio.Semaphore(count)
        _global_count = count
    return _global_slots


def prune_account_slots(active_account_ids: set[int]) -> None:
    """回收已删除账号的信号量映射；在途请求仍持有原对象引用，不受影响。"""
    for account_id in [key for key in _account_slots if key not in active_account_ids]:
        del _account_slots[account_id]


def cached_account_slot_ids() -> set[int]:
    return set(_account_slots)


@asynccontextmanager
async def ai_request_slot(account_id: int):
    global_slot = _global()
    account_slot = _account_slots[int(account_id)]
    acquired_global = False
    acquired_account = False
    try:
        try:
            async with asyncio.timeout(max(0.05, settings.AI_QUEUE_WAIT_SECONDS)):
                await account_slot.acquire()
                acquired_account = True
                # 同一账号的排队请求先等账号槽位，不应占住全局槽位
                # 并把其他账号挤出服务。
                await global_slot.acquire()
                acquired_global = True
        except TimeoutError:
            raise HTTPException(
                status_code=429,
                detail="当前 AI 请求较多，请稍后重试",
                headers={"Retry-After": "2"},
            ) from None
        yield
    finally:
        if acquired_global:
            global_slot.release()
        if acquired_account:
            account_slot.release()

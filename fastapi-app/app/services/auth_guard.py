from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request

from app.config import settings


class SlidingWindowLimiter:
    """Single-process sliding-window limiter; suitable for the one-worker deployment."""

    def __init__(self) -> None:
        self._events: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def check(self, key: str, limit: int, window: int) -> None:
        now = time.monotonic()
        async with self._lock:
            events = self._events.setdefault(key, deque())
            self._events.move_to_end(key)
            cutoff = now - max(1, window)
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= max(1, limit):
                retry_after = max(1, int(window - (now - events[0])) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="请求过于频繁，请稍后重试",
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)
            while len(self._events) > 4096:
                self._events.popitem(last=False)

    def clear(self) -> None:
        self._events.clear()


limiter = SlidingWindowLimiter()
_password_slots: asyncio.Semaphore | None = None
_password_slot_count: int | None = None


def client_ip(request: Request) -> str:
    # Uvicorn only trusts forwarded headers from the private Docker proxy; see Dockerfile.
    return request.client.host if request.client else "unknown"


async def limit_auth(request: Request, action: str, subject: str = "") -> None:
    if action == "register":
        limit = settings.REGISTER_RATE_LIMIT
    else:
        limit = settings.LOGIN_RATE_LIMIT
    await limiter.check(
        f"{action}:ip:{client_ip(request)}", limit, settings.AUTH_RATE_WINDOW_SECONDS
    )
    if subject:
        subject_hash = hashlib.sha256(subject.strip().lower()[:255].encode()).hexdigest()[:24]
        await limiter.check(
            f"{action}:account:{subject_hash}", limit * 2, settings.AUTH_RATE_WINDOW_SECONDS
        )


def _slots() -> asyncio.Semaphore:
    global _password_slots, _password_slot_count
    count = max(1, min(settings.PASSWORD_WORKERS, 8))
    if _password_slots is None or _password_slot_count != count:
        _password_slots = asyncio.Semaphore(count)
        _password_slot_count = count
    return _password_slots


async def password_work(function: Callable, *args):
    try:
        async with asyncio.timeout(max(0.05, settings.PASSWORD_QUEUE_WAIT_SECONDS)):
            await _slots().acquire()
    except TimeoutError:
        raise HTTPException(
            status_code=429,
            detail="认证请求较多，请稍后重试",
            headers={"Retry-After": "2"},
        ) from None
    try:
        return await asyncio.to_thread(function, *args)
    finally:
        _slots().release()

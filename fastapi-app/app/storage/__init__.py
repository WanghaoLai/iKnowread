import asyncio
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import TypeVar

from app.storage.base import StorageBackend
from app.storage.local import LocalStorage

T = TypeVar("T")


async def run_storage_io(operation: Callable[..., T], /, *args, **kwargs) -> T:
    """Run a synchronous storage operation outside the application event loop."""
    return await asyncio.to_thread(operation, *args, **kwargs)


async def complete_on_cancellation(operation: Awaitable[T]) -> T:
    """Let a filesystem/database consistency unit finish before propagating cancellation.

    ``asyncio.to_thread`` cannot stop its worker after the awaiting request is
    cancelled.  A destructive service operation must therefore finish its
    commit-or-rollback protocol instead of abandoning a still-running move.
    """
    task = asyncio.create_task(operation)
    cancellation: asyncio.CancelledError | None = None
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError as exc:
            cancellation = cancellation or exc
            if task.done():
                break
        except BaseException:
            # Read the original exception from the task below.  If the caller
            # was also cancelled, cancellation remains the observable result.
            break

    if cancellation is not None:
        # Consume the operation result/exception so the background task never
        # becomes an unobserved task, then preserve the caller's cancellation.
        try:
            task.result()
        except BaseException:
            pass
        raise cancellation
    return task.result() if task.done() else result


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    return LocalStorage()

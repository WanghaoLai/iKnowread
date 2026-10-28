import asyncio
from collections.abc import Callable, Coroutine
from functools import lru_cache
import logging
from typing import Any, TypeVar

from app.storage.base import StorageBackend
from app.storage.local import LocalStorage

T = TypeVar("T")
logger = logging.getLogger(__name__)


async def run_storage_io(operation: Callable[..., T], /, *args, **kwargs) -> T:
    """Run a synchronous storage operation outside the application event loop."""
    return await asyncio.to_thread(operation, *args, **kwargs)


async def complete_on_cancellation(operation: Coroutine[Any, Any, T]) -> T:
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


async def rollback_on_cancellation(
    operation: Coroutine[Any, Any, T],
    rollback: Callable[[T], Coroutine[Any, Any, None]],
) -> T:
    """Rollback a completed publication when its caller is cancelled.

    Storage writes running in worker threads cannot be stopped safely.  The
    publication therefore finishes behind a shield, then a compensating action
    removes everything it published before cancellation reaches the caller.
    """
    task = asyncio.create_task(operation)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        async def finish_and_rollback() -> None:
            try:
                result = await task
            except BaseException:
                # The operation owns cleanup of its partial state.
                return
            await rollback(result)

        try:
            await complete_on_cancellation(finish_and_rollback())
        except asyncio.CancelledError:
            # A second cancellation is propagated below after compensation.
            pass
        except BaseException:
            logger.exception("Cancellation compensation failed")
        raise cancellation


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    return LocalStorage()

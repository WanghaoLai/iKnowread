import asyncio
from itertools import islice
import logging
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.models import Account, Document
from app.services.account_service import RELATIVE_PREFIX
from app.services.ai_guard import cached_account_slot_ids, prune_account_slots
from app.services.resource_limits import cached_account_lock_ids, prune_account_locks
from app.storage import get_storage, run_storage_io

logger = logging.getLogger(__name__)
_cleanup_task: asyncio.Task | None = None
_reconcile_lock = asyncio.Lock()


def _remove_stale_unreferenced(storage, prefixes, referenced, cutoff) -> None:
    for prefix in prefixes:
        for key in storage.iter_keys_iter(prefix):
            if key not in referenced and storage.modified_at(key) < cutoff:
                storage.delete(key)


async def reconcile_storage() -> None:
    """Incrementally reconcile storage with bounded in-memory working sets."""
    async with _reconcile_lock:
        storage = get_storage()
        await _recover_staged_deletes()
        cached_ids = cached_account_lock_ids() | cached_account_slot_ids()
        active_cached_ids = set()
        if cached_ids:
            active_cached_ids = set(
                await Account.filter(id__in=cached_ids).values_list("id", flat=True)
            )
        prune_account_locks(active_cached_ids)
        prune_account_slots(active_cached_ids)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        batch_size = max(1, settings.STORAGE_RECONCILE_ACCOUNT_BATCH_SIZE)
        cursor = 0
        while True:
            accounts = await Account.filter(id__gt=cursor).order_by("id").limit(
                batch_size
            ).values("id", "role", "avatar")
            if not accounts:
                break
            for account in accounts:
                account_id = int(account["id"])
                referenced: set[str] = set()
                avatar = account.get("avatar")
                if avatar and avatar.startswith(RELATIVE_PREFIX):
                    referenced.add(avatar[len(RELATIVE_PREFIX):])
                document_paths = await Document.filter(account_id=account_id).values_list(
                    "path", "ocr_path"
                )
                for path, ocr_path in document_paths:
                    for value in (path, ocr_path):
                        if value and value.startswith(RELATIVE_PREFIX):
                            referenced.add(value[len(RELATIVE_PREFIX):])
                await run_storage_io(
                    _remove_stale_unreferenced,
                    storage,
                    (f"{account['role']}/{account_id}",),
                    referenced,
                    cutoff,
                )
            cursor = int(accounts[-1]["id"])
            await asyncio.sleep(0)

        await run_storage_io(
            _remove_stale_unreferenced, storage, ("temp",), set(), cutoff
        )


async def _cleanup_loop(*, run_immediately: bool) -> None:
    if run_immediately:
        try:
            await reconcile_storage()
        except Exception:
            logger.exception("Initial storage reconciliation failed")
    while True:
        await asyncio.sleep(max(60, settings.STORAGE_RECONCILE_INTERVAL_SECONDS))
        try:
            await reconcile_storage()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodic storage reconciliation failed")


def start_periodic_cleanup(*, run_immediately: bool = False) -> None:
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(
            _cleanup_loop(run_immediately=run_immediately),
            name="storage-reconciliation",
        )


async def stop_periodic_cleanup() -> None:
    global _cleanup_task
    if _cleanup_task is None:
        return
    task = _cleanup_task
    _cleanup_task = None
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def _recover_staged_deletes() -> None:
    storage = get_storage()
    keys = await run_storage_io(
        lambda: list(islice(
            storage.iter_keys_iter("_trash"),
            max(1, settings.STORAGE_RECONCILE_TRASH_BATCH_SIZE),
        ))
    )
    recovered_trees: set[str] = set()
    purged_tickets: set[str] = set()
    for staged_key in keys:
        parts = staged_key.split("/")
        if len(parts) < 4 or parts[0] != "_trash":
            await run_storage_io(storage.delete, staged_key)
            continue
        ticket = "/".join(parts[:2])
        if ticket in purged_tickets:
            continue
        marker = parts[2]
        if marker == "file":
            original = "/".join(parts[3:])
            referenced = await Document.filter(path=RELATIVE_PREFIX + original).exists()
            referenced = referenced or await Document.filter(ocr_path=RELATIVE_PREFIX + original).exists()
            referenced = referenced or await Account.filter(avatar=RELATIVE_PREFIX + original).exists()
            if referenced:
                await run_storage_io(storage.restore, staged_key, original)
            else:
                await run_storage_io(storage.delete, staged_key)
        elif marker == "tree" and len(parts) >= 6:
            role, raw_id = parts[3], parts[4]
            original_prefix = f"{role}/{raw_id}"
            staged_prefix = f"{ticket}/tree/{original_prefix}"
            if staged_prefix in recovered_trees:
                continue
            recovered_trees.add(staged_prefix)
            exists = raw_id.isdigit() and await Account.filter(id=int(raw_id), role=role).exists()
            if exists:
                await run_storage_io(storage.restore_tree, staged_prefix, original_prefix)
            else:
                await run_storage_io(storage.delete_tree, ticket)
                purged_tickets.add(ticket)
        else:
            await run_storage_io(storage.delete_tree, ticket)
            purged_tickets.add(ticket)

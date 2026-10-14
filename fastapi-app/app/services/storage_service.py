import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.models import Account, Document
from app.services.account_service import RELATIVE_PREFIX
from app.storage import get_storage

logger = logging.getLogger(__name__)
_cleanup_task: asyncio.Task | None = None


async def reconcile_storage() -> None:
    """Recover interrupted deletes and remove stale managed uploads."""
    storage = get_storage()
    await _recover_staged_deletes()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    referenced = {
        path[len(RELATIVE_PREFIX):]
        for path in await Document.all().values_list("path", flat=True)
        if path and path.startswith(RELATIVE_PREFIX)
    }
    referenced.update(
        path[len(RELATIVE_PREFIX):]
        for path in await Document.exclude(ocr_path=None).values_list("ocr_path", flat=True)
        if path and path.startswith(RELATIVE_PREFIX)
    )
    referenced.update(
        avatar[len(RELATIVE_PREFIX):]
        for avatar in await Account.exclude(avatar=None).values_list("avatar", flat=True)
        if avatar and avatar.startswith(RELATIVE_PREFIX)
    )
    for prefix in ("temp", "admin", "user"):
        for key in storage.iter_keys(prefix):
            if key not in referenced and storage.modified_at(key) < cutoff:
                storage.delete(key)


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(60 * 60)
        try:
            await reconcile_storage()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodic storage reconciliation failed")


def start_periodic_cleanup() -> None:
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_loop(), name="storage-reconciliation")


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
    keys = storage.iter_keys("_trash")
    recovered_trees: set[str] = set()
    purged_tickets: set[str] = set()
    for staged_key in keys:
        parts = staged_key.split("/")
        if len(parts) < 4 or parts[0] != "_trash":
            storage.delete(staged_key)
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
                storage.restore(staged_key, original)
            else:
                storage.delete(staged_key)
        elif marker == "tree" and len(parts) >= 6:
            role, raw_id = parts[3], parts[4]
            original_prefix = f"{role}/{raw_id}"
            staged_prefix = f"{ticket}/tree/{original_prefix}"
            if staged_prefix in recovered_trees:
                continue
            recovered_trees.add(staged_prefix)
            exists = raw_id.isdigit() and await Account.filter(id=int(raw_id), role=role).exists()
            if exists:
                storage.restore_tree(staged_prefix, original_prefix)
            else:
                storage.delete_tree(ticket)
                purged_tickets.add(ticket)
        else:
            storage.delete_tree(ticket)
            purged_tickets.add(ticket)

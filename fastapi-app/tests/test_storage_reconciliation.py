import asyncio
import unittest
from unittest.mock import patch

from tortoise import Tortoise

from app.services import storage_service


class StorageReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()

    async def asyncTearDown(self):
        await storage_service.stop_periodic_cleanup()
        await Tortoise.close_connections()

    async def test_initial_reconciliation_runs_off_the_startup_path(self):
        entered = asyncio.Event()

        async def blocking_reconcile():
            entered.set()
            await asyncio.Event().wait()

        with patch.object(storage_service, "reconcile_storage", blocking_reconcile):
            storage_service.start_periodic_cleanup(run_immediately=True)
            await asyncio.wait_for(entered.wait(), 1)
            self.assertIsNotNone(storage_service._cleanup_task)
            self.assertFalse(storage_service._cleanup_task.done())

    async def test_staged_delete_recovery_respects_batch_budget(self):
        class Storage:
            def __init__(self):
                self.deleted = []

            def iter_keys_iter(self, _prefix):
                yield from (f"invalid-{index}" for index in range(20))

            def delete(self, key):
                self.deleted.append(key)

        storage = Storage()
        with (
            patch.object(storage_service, "get_storage", return_value=storage),
            patch.object(
                storage_service.settings,
                "STORAGE_RECONCILE_TRASH_BATCH_SIZE",
                3,
            ),
        ):
            await storage_service._recover_staged_deletes()
        self.assertEqual(storage.deleted, ["invalid-0", "invalid-1", "invalid-2"])

    async def test_reconciliation_lock_prevents_overlapping_runs(self):
        first_started = asyncio.Event()
        release = asyncio.Event()
        class EmptyStorage:
            def iter_keys_iter(self, _prefix):
                return iter(())

        storage = EmptyStorage()

        async def recover_once():
            first_started.set()
            await release.wait()

        with (
            patch.object(storage_service, "get_storage", return_value=storage),
            patch.object(storage_service, "_recover_staged_deletes", recover_once),
        ):
            first = asyncio.create_task(storage_service.reconcile_storage())
            await asyncio.wait_for(first_started.wait(), 1)
            second = asyncio.create_task(storage_service.reconcile_storage())
            await asyncio.sleep(0)
            self.assertFalse(second.done())
            release.set()
            await asyncio.gather(first, second)


if __name__ == "__main__":
    unittest.main()

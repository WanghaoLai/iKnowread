"""验证账号删除后进程内锁与 AI 信号量映射的回收逻辑。"""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import ai_guard, resource_limits


class AccountCleanupTests(unittest.TestCase):
    def tearDown(self):
        resource_limits._account_locks.clear()
        ai_guard._account_slots.clear()

    def test_prune_removes_entries_of_deleted_accounts(self):
        stale_lock = resource_limits.account_lock(9001)
        stale_slot = ai_guard._account_slots[9002]
        resource_limits.account_lock(3)
        ai_guard._account_slots[3]

        resource_limits.prune_account_locks({3})
        ai_guard.prune_account_slots({3})

        self.assertNotIn(9001, resource_limits._account_locks)
        self.assertNotIn(9002, ai_guard._account_slots)
        self.assertIn(3, resource_limits._account_locks)
        self.assertIn(3, ai_guard._account_slots)
        self.assertFalse(stale_lock.locked())
        self.assertFalse(stale_slot.locked())

    def test_held_lock_survives_prune_until_released(self):
        lock = resource_limits.account_lock(9003)

        async def scenario():
            async with lock:
                resource_limits.prune_account_locks(set())
                self.assertIn(9003, resource_limits._account_locks)

        asyncio.run(scenario())
        resource_limits.prune_account_locks(set())
        self.assertNotIn(9003, resource_limits._account_locks)


if __name__ == "__main__":
    unittest.main()

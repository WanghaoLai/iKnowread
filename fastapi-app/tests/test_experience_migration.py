import unittest
from unittest.mock import patch

from app.migrations import v021_bootstrap_experience_account as migration
from app.migrations import v022_repair_experience_collision as repair_migration
from app.security import hash_password, verify_password


class ExperienceMigrationConnection:
    def __init__(self, account=None, policy_exists=False):
        self.account = account
        self.policy_exists = policy_exists
        self.executed = []
        self.next_id = 7

    async def execute_query_dict(self, query, params=None):
        if "FROM `account`" not in query:
            raise AssertionError(f"unexpected query: {query}")
        username = (params or [None])[0]
        if username != migration.EXPERIENCE_USERNAME or self.account is None:
            return []
        return [dict(self.account)]

    async def execute_query(self, query, params=None):
        params = params or []
        normalized = " ".join(query.split())
        self.executed.append((normalized, list(params)))
        if normalized.startswith("INSERT INTO `account`"):
            self.account = {
                "id": self.next_id,
                "role": "user",
                "password": params[1],
                "is_experience": True,
            }
        elif normalized.startswith("UPDATE `account` SET `is_experience`"):
            self.account["is_experience"] = False
        elif normalized.startswith("DELETE FROM `experience_policy`"):
            self.policy_exists = False
        elif normalized.startswith("INSERT INTO `experience_policy`"):
            if not self.policy_exists:
                self.policy_exists = True
        return 1, []


class ExperienceMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_account_and_policy_are_created(self):
        connection = ExperienceMigrationConnection()

        await migration.upgrade(connection)

        self.assertEqual(connection.account["role"], "user")
        self.assertTrue(connection.account["is_experience"])
        self.assertTrue(
            verify_password(migration.EXPERIENCE_PASSWORD, connection.account["password"])
        )
        self.assertTrue(connection.policy_exists)

    async def test_existing_user_is_preserved_and_not_published(self):
        password_hash = hash_password(migration.EXPERIENCE_PASSWORD)
        connection = ExperienceMigrationConnection(account={
            "id": 3,
            "role": "user",
            "password": password_hash,
            "is_experience": False,
        })

        await migration.upgrade(connection)

        self.assertEqual(connection.account["password"], password_hash)
        self.assertFalse(connection.account["is_experience"])
        self.assertFalse(connection.policy_exists)
        self.assertFalse(any(
            query.startswith("UPDATE `account` SET `password`")
            for query, _ in connection.executed
        ))

    async def test_existing_password_is_never_replaced(self):
        password_hash = hash_password("old-password")
        connection = ExperienceMigrationConnection(account={
            "id": 3,
            "role": "user",
            "password": password_hash,
            "is_experience": False,
        })

        await migration.upgrade(connection)

        self.assertEqual(connection.account["password"], password_hash)
        self.assertFalse(any(
            query.startswith("UPDATE `account` SET `password`")
            for query, _ in connection.executed
        ))

    async def test_admin_named_test_is_preserved(self):
        connection = ExperienceMigrationConnection(account={
            "id": 1,
            "role": "admin",
            "password": "hash",
            "is_experience": False,
        })

        await migration.upgrade(connection)

        self.assertEqual(connection.account["password"], "hash")
        self.assertFalse(connection.account["is_experience"])

    async def test_legacy_v020_metadata_is_removed_without_rehashing(self):
        connection = ExperienceMigrationConnection(account={
            "id": 3,
            "role": "user",
            "password": hash_password(migration.EXPERIENCE_PASSWORD),
            "is_experience": True,
        }, policy_exists=True)

        with patch.object(migration, "hash_password", wraps=hash_password) as hasher:
            await migration.upgrade(connection)

        hasher.assert_not_called()
        self.assertFalse(connection.account["is_experience"])
        self.assertFalse(connection.policy_exists)


class RepairExperienceCollisionConnection:
    def __init__(self, victim=True):
        self.victim = victim
        self.account = {
            "id": 3,
            "password": hash_password(repair_migration.__name__),
            "is_experience": True,
            "session_version": 7,
        }
        self.policy_exists = True
        self.share_exists = True

    async def execute_query_dict(self, query, params=None):
        self.assert_query = " ".join(query.split())
        return [{"id": self.account["id"]}] if self.victim else []

    async def execute_query(self, query, params=None):
        normalized = " ".join(query.split())
        params = params or []
        if normalized.startswith("DELETE FROM `experience_document_share`"):
            self.share_exists = False
        elif normalized.startswith("DELETE FROM `experience_policy`"):
            self.policy_exists = False
        elif normalized.startswith("UPDATE `account` SET `password`"):
            self.account["password"] = params[0]
            self.account["is_experience"] = False
            self.account["session_version"] += 1
        return 1, []


class RepairExperienceCollisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_preexisting_account_is_quarantined_from_public_credential(self):
        connection = RepairExperienceCollisionConnection()

        await repair_migration.upgrade(connection)

        self.assertFalse(connection.account["is_experience"])
        self.assertEqual(connection.account["session_version"], 8)
        self.assertFalse(connection.policy_exists)
        self.assertFalse(connection.share_exists)
        self.assertFalse(
            verify_password(migration.EXPERIENCE_PASSWORD, connection.account["password"])
        )
        self.assertIn("created_at` < `introduced`.`applied_at", connection.assert_query)

    async def test_genuine_bootstrap_account_is_unchanged(self):
        connection = RepairExperienceCollisionConnection(victim=False)
        before = dict(connection.account)

        await repair_migration.upgrade(connection)

        self.assertEqual(connection.account, before)
        self.assertTrue(connection.policy_exists)
        self.assertTrue(connection.share_exists)


if __name__ == "__main__":
    unittest.main()

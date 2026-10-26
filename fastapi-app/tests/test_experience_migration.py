import unittest
from unittest.mock import patch

from app.migrations import v021_bootstrap_experience_account as migration
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
        elif normalized.startswith("UPDATE `account` SET `password`"):
            self.account["password"] = params[0]
            self.account["is_experience"] = True
        elif normalized.startswith("UPDATE `account` SET `is_experience`"):
            self.account["is_experience"] = True
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

    async def test_existing_user_is_promoted_without_overwriting_current_password(self):
        password_hash = hash_password(migration.EXPERIENCE_PASSWORD)
        connection = ExperienceMigrationConnection(account={
            "id": 3,
            "role": "user",
            "password": password_hash,
            "is_experience": False,
        })

        await migration.upgrade(connection)

        self.assertEqual(connection.account["password"], password_hash)
        self.assertTrue(connection.account["is_experience"])
        self.assertFalse(any(
            query.startswith("UPDATE `account` SET `password`")
            for query, _ in connection.executed
        ))

    async def test_wrong_existing_password_is_safely_replaced(self):
        connection = ExperienceMigrationConnection(account={
            "id": 3,
            "role": "user",
            "password": hash_password("old-password"),
            "is_experience": False,
        })

        await migration.upgrade(connection)

        self.assertTrue(
            verify_password(migration.EXPERIENCE_PASSWORD, connection.account["password"])
        )
        self.assertTrue(any(
            query.startswith("UPDATE `account` SET `password`")
            for query, _ in connection.executed
        ))

    async def test_admin_named_test_is_never_silently_repurposed(self):
        connection = ExperienceMigrationConnection(account={
            "id": 1,
            "role": "admin",
            "password": "hash",
            "is_experience": False,
        })

        with self.assertRaisesRegex(RuntimeError, "不是普通用户"):
            await migration.upgrade(connection)

        self.assertEqual(connection.executed, [])

    async def test_repeat_run_preserves_existing_policy(self):
        connection = ExperienceMigrationConnection(account={
            "id": 3,
            "role": "user",
            "password": hash_password(migration.EXPERIENCE_PASSWORD),
            "is_experience": True,
        }, policy_exists=True)

        with patch.object(migration, "hash_password", wraps=hash_password) as hasher:
            await migration.upgrade(connection)
            await migration.upgrade(connection)

        hasher.assert_not_called()
        self.assertTrue(connection.policy_exists)


if __name__ == "__main__":
    unittest.main()

from tortoise import Tortoise

from app.migrations.v001_unify_accounts import _column_exists

VERSION = 7
NAME = "session_revocation"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    if not await _column_exists(connection, "account", "session_version"):
        await connection.execute_query(
            "ALTER TABLE `account` "
            "ADD COLUMN `session_version` INT NOT NULL DEFAULT 1 AFTER `role`"
        )

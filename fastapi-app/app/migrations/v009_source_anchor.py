from tortoise import Tortoise

from app.migrations.v001_unify_accounts import _column_exists

VERSION = 9
NAME = "add_unified_source_anchor"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    if not await _column_exists(connection, "note", "source_anchor"):
        await connection.execute_query(
            "ALTER TABLE `note` ADD COLUMN `source_anchor` JSON NULL "
            "AFTER `document_version`"
        )

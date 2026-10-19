from tortoise import Tortoise

from app.migrations.v001_unify_accounts import _column_exists, _index_exists

VERSION = 11
NAME = "document_recycle_bin"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    if not await _column_exists(connection, "document", "deleted_at"):
        await connection.execute_query(
            "ALTER TABLE `document` ADD COLUMN `deleted_at` DATETIME(6) NULL "
            "AFTER `ocr_updated_at`"
        )
    if not await _index_exists(connection, "document", "ix_document__account_id__deleted_at"):
        await connection.execute_query(
            "ALTER TABLE `document` ADD INDEX `ix_document__account_id__deleted_at` "
            "(`account_id`, `deleted_at`)"
        )

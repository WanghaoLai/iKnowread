from tortoise import Tortoise

from app.migrations.v001_unify_accounts import _column_exists, _index_exists

VERSION = 8
NAME = "version_document_content_references"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")

    if not await _column_exists(connection, "document", "content_version"):
        await connection.execute_query(
            "ALTER TABLE `document` ADD COLUMN `content_version` VARCHAR(32) NULL "
            "AFTER `path`"
        )
    await connection.execute_query(
        "UPDATE `document` SET `content_version` = REPLACE(UUID(), '-', '') "
        "WHERE `content_version` IS NULL OR `content_version` = ''"
    )
    await connection.execute_query(
        "ALTER TABLE `document` MODIFY COLUMN `content_version` VARCHAR(32) NOT NULL"
    )
    if not await _index_exists(connection, "document", "ux_document_content_version"):
        await connection.execute_query(
            "ALTER TABLE `document` ADD UNIQUE INDEX `ux_document_content_version` "
            "(`content_version`)"
        )

    if not await _column_exists(connection, "note", "document_version"):
        await connection.execute_query(
            "ALTER TABLE `note` ADD COLUMN `document_version` VARCHAR(32) NULL "
            "AFTER `document_name`"
        )
    # 历史笔记创建时没有版本证据，保留 NULL 比猜测为当前版本更可靠；
    # 新建笔记从本迁移起都会保存精确的内容版本。
    if not await _index_exists(connection, "note", "ix_note_document_version"):
        await connection.execute_query(
            "ALTER TABLE `note` ADD INDEX `ix_note_document_version` "
            "(`document_id`, `document_version`)"
        )

from tortoise import Tortoise

from app.migrations.v001_unify_accounts import _column_exists, _constraint_exists, _index_exists

VERSION = 4
NAME = "add_document_ocr"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    columns = (
        ("ocr_status", "VARCHAR(20) NOT NULL DEFAULT 'not_applicable'"),
        ("ocr_path", "VARCHAR(500) NULL"),
        ("ocr_error", "VARCHAR(500) NULL"),
        ("ocr_updated_at", "DATETIME(6) NULL"),
    )
    for name, definition in columns:
        if not await _column_exists(connection, "document", name):
            await connection.execute_query(
                f"ALTER TABLE `document` ADD COLUMN `{name}` {definition}"
            )

    # 已有 PDF 也进入队列；这样历史扫描件无需重新上传。
    await connection.execute_query(
        "UPDATE `document` SET `ocr_status` = 'pending', `ocr_error` = NULL "
        "WHERE `ext` = 'pdf' AND `ocr_path` IS NULL "
        "AND `ocr_status` IN ('not_applicable', 'processing')"
    )
    await connection.execute_query(
        "UPDATE `document` SET `ocr_status` = 'not_applicable', `ocr_path` = NULL, "
        "`ocr_error` = NULL WHERE `ext` <> 'pdf'"
    )

    if not await _index_exists(connection, "document", "ix_document_ocr_status"):
        await connection.execute_query(
            "ALTER TABLE `document` ADD INDEX `ix_document_ocr_status` (`ocr_status`)"
        )
    if not await _constraint_exists(connection, "document", "ck_document_ocr_status"):
        await connection.execute_query(
            "ALTER TABLE `document` ADD CONSTRAINT `ck_document_ocr_status` "
            "CHECK (`ocr_status` IN "
            "('not_applicable', 'pending', 'processing', 'ready', 'failed'))"
        )

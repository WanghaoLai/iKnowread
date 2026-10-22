from tortoise import Tortoise

from app.migrations.v001_unify_accounts import _column_exists, _constraint_exists, _index_exists


VERSION = 16
NAME = "url_web_imports"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    columns = (
        ("source_type", "VARCHAR(10) NOT NULL DEFAULT 'local'"),
        ("source_url", "VARCHAR(2048) NULL"),
        ("source_title", "VARCHAR(500) NULL"),
        ("source_fetched_at", "DATETIME(6) NULL"),
    )
    for name, definition in columns:
        if not await _column_exists(connection, "document", name):
            await connection.execute_query(
                f"ALTER TABLE `document` ADD COLUMN `{name}` {definition}"
            )
    await connection.execute_query(
        "UPDATE `document` SET `source_type`='local' "
        "WHERE `source_type` IS NULL OR `source_type` NOT IN ('local', 'url')"
    )
    if not await _index_exists(connection, "document", "ix_document_source_type"):
        await connection.execute_query(
            "ALTER TABLE `document` ADD INDEX `ix_document_source_type` (`source_type`)"
        )
    if not await _constraint_exists(connection, "document", "ck_document_source_type"):
        await connection.execute_query(
            "ALTER TABLE `document` ADD CONSTRAINT `ck_document_source_type` "
            "CHECK (`source_type` IN ('local', 'url'))"
        )
    await connection.execute_query(
        """
        CREATE TABLE IF NOT EXISTS `web_import_job` (
          `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
          `account_id` INT NOT NULL,
          `source_url` VARCHAR(2048) NOT NULL,
          `status` VARCHAR(20) NOT NULL DEFAULT 'pending',
          `progress` INT NOT NULL DEFAULT 0,
          `error` VARCHAR(500) NULL,
          `attempt_count` INT NOT NULL DEFAULT 0,
          `result_document_id` INT NULL,
          `started_at` DATETIME(6) NULL,
          `finished_at` DATETIME(6) NULL,
          `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
          CONSTRAINT `fk_web_import_account`
            FOREIGN KEY (`account_id`) REFERENCES `account` (`id`) ON DELETE CASCADE,
          CONSTRAINT `fk_web_import_document`
            FOREIGN KEY (`result_document_id`) REFERENCES `document` (`id`) ON DELETE SET NULL,
          CONSTRAINT `ck_web_import_status`
            CHECK (`status` IN ('pending', 'processing', 'success', 'failed')),
          KEY `ix_web_import_account_created` (`account_id`, `created_at`),
          KEY `ix_web_import_status_updated` (`status`, `updated_at`)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
    )

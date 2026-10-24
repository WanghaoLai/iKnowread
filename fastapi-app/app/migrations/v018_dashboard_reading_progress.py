from tortoise import Tortoise

from app.migrations.v001_unify_accounts import _constraint_exists, _index_exists


VERSION = 18
NAME = "dashboard_reading_progress"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    await connection.execute_query(
        """
        CREATE TABLE IF NOT EXISTS `reading_progress` (
          `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
          `account_id` INT NOT NULL,
          `document_id` INT NOT NULL,
          `document_version` VARCHAR(32) NOT NULL,
          `source_anchor` JSON NOT NULL,
          `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
          CONSTRAINT `fk_reading_progress_account`
            FOREIGN KEY (`account_id`) REFERENCES `account` (`id`) ON DELETE CASCADE,
          CONSTRAINT `fk_reading_progress_document`
            FOREIGN KEY (`document_id`) REFERENCES `document` (`id`) ON DELETE CASCADE,
          UNIQUE KEY `ux_reading_progress_account_document` (`account_id`, `document_id`),
          KEY `ix_reading_progress_account_updated` (`account_id`, `updated_at`)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
    )
    if not await _index_exists(
        connection, "reading_progress", "ux_reading_progress_account_document"
    ):
        await connection.execute_query(
            "ALTER TABLE `reading_progress` ADD UNIQUE INDEX "
            "`ux_reading_progress_account_document` (`account_id`, `document_id`)"
        )
    if not await _index_exists(
        connection, "reading_progress", "ix_reading_progress_account_updated"
    ):
        await connection.execute_query(
            "ALTER TABLE `reading_progress` ADD INDEX "
            "`ix_reading_progress_account_updated` (`account_id`, `updated_at`)"
        )
    if not await _constraint_exists(
        connection, "reading_progress", "fk_reading_progress_account"
    ):
        await connection.execute_query(
            "ALTER TABLE `reading_progress` ADD CONSTRAINT "
            "`fk_reading_progress_account` FOREIGN KEY (`account_id`) "
            "REFERENCES `account` (`id`) ON DELETE CASCADE"
        )
    if not await _constraint_exists(
        connection, "reading_progress", "fk_reading_progress_document"
    ):
        await connection.execute_query(
            "ALTER TABLE `reading_progress` ADD CONSTRAINT "
            "`fk_reading_progress_document` FOREIGN KEY (`document_id`) "
            "REFERENCES `document` (`id`) ON DELETE CASCADE"
        )

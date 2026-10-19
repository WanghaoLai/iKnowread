from tortoise import Tortoise


VERSION = 13
NAME = "unify_document_processing_status"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    await connection.execute_query(
        """
        CREATE TABLE IF NOT EXISTS `document_processing_task` (
          `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
          `document_id` INT NOT NULL,
          `task_type` VARCHAR(30) NOT NULL,
          `status` VARCHAR(20) NOT NULL DEFAULT 'not_started',
          `progress` INT NOT NULL DEFAULT 0,
          `error` VARCHAR(500) NULL,
          `attempt_count` INT NOT NULL DEFAULT 0,
          `started_at` DATETIME(6) NULL,
          `finished_at` DATETIME(6) NULL,
          `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
          CONSTRAINT `fk_processing_task_document`
            FOREIGN KEY (`document_id`) REFERENCES `document` (`id`) ON DELETE CASCADE,
          UNIQUE KEY `ux_processing_task_document_type` (`document_id`, `task_type`),
          KEY `ix_processing_task_status_updated` (`status`, `updated_at`)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
    )
    # Backfill every existing document without modifying document or note rows.
    # INSERT IGNORE keeps this migration restart-safe after an implicit DDL commit.
    await connection.execute_query(
        """
        INSERT IGNORE INTO `document_processing_task`
          (`document_id`, `task_type`, `status`, `progress`, `error`, `finished_at`)
        SELECT `id`, 'ocr', `ocr_status`,
          CASE WHEN `ocr_status` = 'ready' THEN 100
               WHEN `ocr_status` = 'processing' THEN 50 ELSE 0 END,
          `ocr_error`,
          CASE WHEN `ocr_status` IN ('ready', 'failed') THEN `ocr_updated_at` ELSE NULL END
        FROM `document`
        """
    )
    for task_type in ("text_extraction", "index_rebuild"):
        await connection.execute_query(
            "INSERT IGNORE INTO `document_processing_task` "
            "(`document_id`, `task_type`, `status`, `progress`) "
            "SELECT `id`, %s, 'not_started', 0 FROM `document`",
            [task_type],
        )

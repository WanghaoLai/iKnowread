from tortoise import Tortoise

VERSION = 6
NAME = "add_user_notes"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    await connection.execute_query(
        """
        CREATE TABLE IF NOT EXISTS `note` (
          `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
          `account_id` INT NOT NULL,
          `document_id` INT NULL,
          `document_name` VARCHAR(255) NULL,
          `source_type` VARCHAR(30) NOT NULL DEFAULT 'manual',
          `title` VARCHAR(200) NOT NULL,
          `selected_text` LONGTEXT NULL,
          `content` LONGTEXT NOT NULL,
          `remark` LONGTEXT NOT NULL,
          `provider` VARCHAR(50) NULL,
          `config_name` VARCHAR(100) NULL,
          `model` VARCHAR(100) NULL,
          `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
          INDEX `ix_note_account_created` (`account_id`, `created_at`),
          INDEX `ix_note_account_document` (`account_id`, `document_id`),
          CONSTRAINT `fk_note_account` FOREIGN KEY (`account_id`)
            REFERENCES `account` (`id`) ON DELETE CASCADE,
          CONSTRAINT `fk_note_document` FOREIGN KEY (`document_id`)
            REFERENCES `document` (`id`) ON DELETE SET NULL,
          CONSTRAINT `ck_note_source_type`
            CHECK (`source_type` IN ('manual', 'ai_explanation'))
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
    )

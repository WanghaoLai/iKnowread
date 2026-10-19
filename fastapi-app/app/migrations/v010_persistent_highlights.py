from tortoise import Tortoise

from app.migrations.v001_unify_accounts import _constraint_exists, _index_exists

VERSION = 10
NAME = "add_persistent_document_highlights"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    await connection.execute_query(
        """
        CREATE TABLE IF NOT EXISTS `highlight` (
          `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
          `account_id` INT NOT NULL,
          `document_id` INT NOT NULL,
          `document_version` VARCHAR(32) NOT NULL,
          `anchor_key` VARCHAR(64) NOT NULL,
          `source_anchor` JSON NOT NULL,
          `selected_text` LONGTEXT NOT NULL,
          `remark` LONGTEXT NOT NULL,
          `provider` VARCHAR(50) NULL,
          `config_name` VARCHAR(100) NULL,
          `model` VARCHAR(100) NULL,
          `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
          CONSTRAINT `fk_highlight_account` FOREIGN KEY (`account_id`) REFERENCES `account` (`id`) ON DELETE CASCADE,
          CONSTRAINT `fk_highlight_document` FOREIGN KEY (`document_id`) REFERENCES `document` (`id`) ON DELETE CASCADE,
          UNIQUE KEY `ux_highlight_anchor` (`account_id`, `document_id`, `document_version`, `anchor_key`),
          KEY `ix_highlight_document_version` (`account_id`, `document_id`, `document_version`)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
    )
    # 兼容极少数曾手工创建过同名表但缺少约束/索引的环境。
    if not await _index_exists(connection, "highlight", "ux_highlight_anchor"):
        await connection.execute_query(
            "ALTER TABLE `highlight` ADD UNIQUE INDEX `ux_highlight_anchor` "
            "(`account_id`, `document_id`, `document_version`, `anchor_key`)"
        )
    if not await _index_exists(connection, "highlight", "ix_highlight_document_version"):
        await connection.execute_query(
            "ALTER TABLE `highlight` ADD INDEX `ix_highlight_document_version` "
            "(`account_id`, `document_id`, `document_version`)"
        )
    if not await _constraint_exists(connection, "highlight", "fk_highlight_account"):
        await connection.execute_query(
            "ALTER TABLE `highlight` ADD CONSTRAINT `fk_highlight_account` "
            "FOREIGN KEY (`account_id`) REFERENCES `account` (`id`) ON DELETE CASCADE"
        )
    if not await _constraint_exists(connection, "highlight", "fk_highlight_document"):
        await connection.execute_query(
            "ALTER TABLE `highlight` ADD CONSTRAINT `fk_highlight_document` "
            "FOREIGN KEY (`document_id`) REFERENCES `document` (`id`) ON DELETE CASCADE"
        )

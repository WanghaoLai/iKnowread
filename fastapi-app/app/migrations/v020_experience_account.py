from tortoise import Tortoise

from app.migrations.v001_unify_accounts import _column_exists, _constraint_exists, _index_exists


VERSION = 20
NAME = "experience_account_policy"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    if not await _column_exists(connection, "account", "is_experience"):
        await connection.execute_query(
            "ALTER TABLE `account` ADD COLUMN `is_experience` BOOLEAN NOT NULL DEFAULT FALSE "
            "AFTER `role`"
        )
    if not await _index_exists(connection, "account", "ix_account_is_experience"):
        await connection.execute_query(
            "ALTER TABLE `account` ADD INDEX `ix_account_is_experience` (`is_experience`)"
        )
    await connection.execute_query(
        """
        CREATE TABLE IF NOT EXISTS `experience_policy` (
          `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
          `account_id` INT NOT NULL,
          `enabled` BOOLEAN NOT NULL DEFAULT TRUE,
          `public_password` VARCHAR(128) NOT NULL DEFAULT '',
          `ai_config_id` INT NULL,
          `daily_ai_limit` INT NOT NULL DEFAULT 20,
          `ai_usage_date` DATE NULL,
          `ai_used_today` INT NOT NULL DEFAULT 0,
          `show_highlights` BOOLEAN NOT NULL DEFAULT TRUE,
          `show_notes` BOOLEAN NOT NULL DEFAULT TRUE,
          `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
          CONSTRAINT `fk_experience_policy_account`
            FOREIGN KEY (`account_id`) REFERENCES `account` (`id`) ON DELETE CASCADE,
          CONSTRAINT `fk_experience_policy_ai_config`
            FOREIGN KEY (`ai_config_id`) REFERENCES `ai_config` (`id`) ON DELETE SET NULL,
          CONSTRAINT `ck_experience_daily_ai_limit`
            CHECK (`daily_ai_limit` BETWEEN 0 AND 1000),
          CONSTRAINT `ck_experience_ai_used_today`
            CHECK (`ai_used_today` >= 0),
          UNIQUE KEY `ux_experience_policy_account` (`account_id`)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
    )
    await connection.execute_query(
        """
        CREATE TABLE IF NOT EXISTS `experience_document_share` (
          `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
          `account_id` INT NOT NULL,
          `document_id` INT NOT NULL,
          `shared_by_id` INT NULL,
          `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          CONSTRAINT `fk_experience_share_account`
            FOREIGN KEY (`account_id`) REFERENCES `account` (`id`) ON DELETE CASCADE,
          CONSTRAINT `fk_experience_share_document`
            FOREIGN KEY (`document_id`) REFERENCES `document` (`id`) ON DELETE CASCADE,
          CONSTRAINT `fk_experience_share_creator`
            FOREIGN KEY (`shared_by_id`) REFERENCES `account` (`id`) ON DELETE SET NULL,
          UNIQUE KEY `ux_experience_share_account_document` (`account_id`, `document_id`),
          KEY `ix_experience_share_account_created` (`account_id`, `created_at`)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
    )
    repairs = (
        ("experience_policy", "ux_experience_policy_account", "UNIQUE INDEX", "(`account_id`)"),
        ("experience_document_share", "ux_experience_share_account_document", "UNIQUE INDEX", "(`account_id`, `document_id`)"),
        ("experience_document_share", "ix_experience_share_account_created", "INDEX", "(`account_id`, `created_at`)"),
    )
    for table, name, kind, columns in repairs:
        if not await _index_exists(connection, table, name):
            await connection.execute_query(
                f"ALTER TABLE `{table}` ADD {kind} `{name}` {columns}"
            )
    constraints = (
        ("experience_policy", "fk_experience_policy_account", "FOREIGN KEY (`account_id`) REFERENCES `account` (`id`) ON DELETE CASCADE"),
        ("experience_policy", "fk_experience_policy_ai_config", "FOREIGN KEY (`ai_config_id`) REFERENCES `ai_config` (`id`) ON DELETE SET NULL"),
        ("experience_document_share", "fk_experience_share_account", "FOREIGN KEY (`account_id`) REFERENCES `account` (`id`) ON DELETE CASCADE"),
        ("experience_document_share", "fk_experience_share_document", "FOREIGN KEY (`document_id`) REFERENCES `document` (`id`) ON DELETE CASCADE"),
        ("experience_document_share", "fk_experience_share_creator", "FOREIGN KEY (`shared_by_id`) REFERENCES `account` (`id`) ON DELETE SET NULL"),
    )
    for table, name, definition in constraints:
        if not await _constraint_exists(connection, table, name):
            await connection.execute_query(
                f"ALTER TABLE `{table}` ADD CONSTRAINT `{name}` {definition}"
            )
    await connection.execute_query(
        "UPDATE `account` SET `is_experience`=TRUE "
        "WHERE `username`='test' AND `role`='user'"
    )
    await connection.execute_query(
        """
        INSERT INTO `experience_policy`
          (`account_id`, `enabled`, `public_password`, `daily_ai_limit`,
           `show_highlights`, `show_notes`)
        SELECT `candidate`.`id`, TRUE, 'test1234', 20, TRUE, TRUE
        FROM `account` AS `candidate`
        WHERE `candidate`.`username`='test'
          AND `candidate`.`role`='user'
          AND `candidate`.`is_experience`=TRUE
          AND NOT EXISTS (
            SELECT 1 FROM `experience_policy` AS `existing`
            WHERE `existing`.`account_id`=`candidate`.`id`
          )
        """
    )

from tortoise import Tortoise

from app.migrations.v001_unify_accounts import _column_exists, _constraint_exists, _index_exists

VERSION = 5
NAME = "support_multiple_ai_providers"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")

    columns = (
        ("provider", "VARCHAR(20) NOT NULL DEFAULT 'deepseek' AFTER `account_id`"),
        ("name", "VARCHAR(100) NULL AFTER `provider`"),
        ("is_active", "BOOL NOT NULL DEFAULT FALSE AFTER `system_prompt`"),
        ("created_at", "DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) AFTER `is_active`"),
        (
            "updated_at",
            "DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) "
            "ON UPDATE CURRENT_TIMESTAMP(6) AFTER `created_at`",
        ),
    )
    for name, definition in columns:
        if not await _column_exists(connection, "ai_config", name):
            await connection.execute_query(
                f"ALTER TABLE `ai_config` ADD COLUMN `{name}` {definition}"
            )

    # v003 每个账号只有一项，因此原配置可以安全地成为迁移后的当前启用项。
    await connection.execute_query(
        "UPDATE `ai_config` SET `provider` = 'deepseek' "
        "WHERE `provider` IS NULL OR `provider` = ''"
    )
    await connection.execute_query(
        "UPDATE `ai_config` SET `name` = CONCAT('DeepSeek · ', `model`) "
        "WHERE `name` IS NULL OR `name` = ''"
    )
    await connection.execute_query("UPDATE `ai_config` SET `is_active` = TRUE")
    await connection.execute_query(
        "ALTER TABLE `ai_config` MODIFY COLUMN `name` VARCHAR(100) NOT NULL"
    )

    # 先建立普通账号索引，确保移除旧唯一索引时外键始终有可用索引。
    if not await _index_exists(connection, "ai_config", "ix_ai_config_account_id"):
        await connection.execute_query(
            "ALTER TABLE `ai_config` ADD INDEX `ix_ai_config_account_id` (`account_id`)"
        )

    indexes = await connection.execute_query_dict(
        "SELECT INDEX_NAME, NON_UNIQUE, "
        "GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',') AS columns_list "
        "FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_config' "
        "GROUP BY INDEX_NAME, NON_UNIQUE"
    )
    for index in indexes:
        name = str(index["INDEX_NAME"])
        if name != "PRIMARY" and int(index["NON_UNIQUE"]) == 0 and index["columns_list"] == "account_id":
            safe_name = name.replace("`", "``")
            await connection.execute_query(
                f"ALTER TABLE `ai_config` DROP INDEX `{safe_name}`"
            )

    if not await _index_exists(connection, "ai_config", "ux_ai_config_account_name"):
        await connection.execute_query(
            "ALTER TABLE `ai_config` ADD UNIQUE INDEX `ux_ai_config_account_name` "
            "(`account_id`, `name`)"
        )
    if not await _index_exists(connection, "ai_config", "ix_ai_config_account_active"):
        await connection.execute_query(
            "ALTER TABLE `ai_config` ADD INDEX `ix_ai_config_account_active` "
            "(`account_id`, `is_active`)"
        )
    if not await _constraint_exists(connection, "ai_config", "ck_ai_config_provider"):
        await connection.execute_query(
            "ALTER TABLE `ai_config` ADD CONSTRAINT `ck_ai_config_provider` "
            "CHECK (`provider` IN ('deepseek', 'glm', 'mimo', 'bailian'))"
        )

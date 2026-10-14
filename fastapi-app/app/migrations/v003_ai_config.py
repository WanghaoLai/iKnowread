from tortoise import Tortoise

VERSION = 3
NAME = "add_account_ai_config"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    await connection.execute_query("""
        CREATE TABLE IF NOT EXISTS `ai_config` (
            `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            `account_id` INT NOT NULL UNIQUE,
            `base_url` VARCHAR(255) NOT NULL,
            `model` VARCHAR(100) NOT NULL,
            `encrypted_api_key` LONGTEXT NOT NULL,
            `temperature` DOUBLE NOT NULL DEFAULT 1,
            `max_tokens` INT NOT NULL DEFAULT 4096,
            `thinking` BOOL NOT NULL DEFAULT FALSE,
            `system_prompt` LONGTEXT NOT NULL,
            CONSTRAINT `fk_ai_config_account` FOREIGN KEY (`account_id`)
                REFERENCES `account` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    """)

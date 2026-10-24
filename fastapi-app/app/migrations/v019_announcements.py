from tortoise import Tortoise

from app.migrations.v001_unify_accounts import _constraint_exists, _index_exists


VERSION = 19
NAME = "system_announcements"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    await connection.execute_query(
        """
        CREATE TABLE IF NOT EXISTS `announcement` (
          `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
          `title` VARCHAR(200) NOT NULL,
          `content` LONGTEXT NOT NULL,
          `status` VARCHAR(20) NOT NULL DEFAULT 'draft',
          `published_revision` INT NOT NULL DEFAULT 0,
          `published_at` DATETIME(6) NULL,
          `created_by_id` INT NULL,
          `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
          CONSTRAINT `fk_announcement_creator`
            FOREIGN KEY (`created_by_id`) REFERENCES `account` (`id`) ON DELETE SET NULL,
          CONSTRAINT `ck_announcement_status`
            CHECK (`status` IN ('draft', 'published', 'offline')),
          KEY `ix_announcement_status_published` (`status`, `published_at`)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
    )
    await connection.execute_query(
        """
        CREATE TABLE IF NOT EXISTS `announcement_read` (
          `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
          `account_id` INT NOT NULL,
          `announcement_id` INT NOT NULL,
          `read_revision` INT NOT NULL,
          `read_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
          CONSTRAINT `fk_announcement_read_account`
            FOREIGN KEY (`account_id`) REFERENCES `account` (`id`) ON DELETE CASCADE,
          CONSTRAINT `fk_announcement_read_announcement`
            FOREIGN KEY (`announcement_id`) REFERENCES `announcement` (`id`) ON DELETE CASCADE,
          UNIQUE KEY `ux_announcement_read_account_announcement`
            (`account_id`, `announcement_id`),
          KEY `ix_announcement_read_account_time` (`account_id`, `read_at`)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
    )
    repairs = (
        ("announcement", "ix_announcement_status_published", "INDEX", "(`status`, `published_at`)"),
        ("announcement_read", "ux_announcement_read_account_announcement", "UNIQUE INDEX", "(`account_id`, `announcement_id`)"),
        ("announcement_read", "ix_announcement_read_account_time", "INDEX", "(`account_id`, `read_at`)"),
    )
    for table, name, kind, columns in repairs:
        if not await _index_exists(connection, table, name):
            await connection.execute_query(
                f"ALTER TABLE `{table}` ADD {kind} `{name}` {columns}"
            )
    constraints = (
        ("announcement", "fk_announcement_creator", "FOREIGN KEY (`created_by_id`) REFERENCES `account` (`id`) ON DELETE SET NULL"),
        ("announcement_read", "fk_announcement_read_account", "FOREIGN KEY (`account_id`) REFERENCES `account` (`id`) ON DELETE CASCADE"),
        ("announcement_read", "fk_announcement_read_announcement", "FOREIGN KEY (`announcement_id`) REFERENCES `announcement` (`id`) ON DELETE CASCADE"),
    )
    for table, name, definition in constraints:
        if not await _constraint_exists(connection, table, name):
            await connection.execute_query(
                f"ALTER TABLE `{table}` ADD CONSTRAINT `{name}` {definition}"
            )
    if not await _constraint_exists(connection, "announcement", "ck_announcement_status"):
        await connection.execute_query(
            "ALTER TABLE `announcement` ADD CONSTRAINT `ck_announcement_status` "
            "CHECK (`status` IN ('draft', 'published', 'offline'))"
        )

from __future__ import annotations

import shutil
from pathlib import Path

from tortoise import Tortoise

from app.config import settings
from app.security import PASSWORD_SCHEME, hash_password, password_needs_rehash

VERSION = 1
NAME = "unify_accounts"


async def _table_exists(connection, table: str) -> bool:
    rows = await connection.execute_query_dict(
        "SELECT 1 FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s LIMIT 1",
        [table],
    )
    return bool(rows)


async def _column_exists(connection, table: str, column: str) -> bool:
    rows = await connection.execute_query_dict(
        "SELECT 1 FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
        "AND COLUMN_NAME = %s LIMIT 1",
        [table, column],
    )
    return bool(rows)


async def _index_exists(connection, table: str, index: str) -> bool:
    rows = await connection.execute_query_dict(
        "SELECT 1 FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
        "AND INDEX_NAME = %s LIMIT 1",
        [table, index],
    )
    return bool(rows)


async def _constraint_exists(connection, table: str, constraint: str) -> bool:
    rows = await connection.execute_query_dict(
        "SELECT 1 FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
        "AND CONSTRAINT_NAME = %s LIMIT 1",
        [table, constraint],
    )
    return bool(rows)


def _move_account_directories(mapping: dict[tuple[str, int], int]) -> None:
    """Move through a staging namespace so ID chains cannot consume each other."""
    stage_root = settings.upload_dir / "_migration_v001_accounts"
    staged_marker = stage_root / ".staging-complete"
    if not staged_marker.exists():
        # 只有所有源目录已隔离后才写标记。如果进程在隔离阶段中断，
        # 重启可继续隔离；进入发布阶段后则不会把已发布的目标误当源目录。
        for (role, old_id), _new_id in sorted(mapping.items()):
            source = settings.upload_dir / role / str(old_id)
            staged = stage_root / role / str(old_id)
            if staged.exists() or not source.exists():
                continue
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(staged))
        stage_root.mkdir(parents=True, exist_ok=True)
        staged_marker.touch()

    for (role, old_id), new_id in sorted(mapping.items()):
        staged = stage_root / role / str(old_id)
        if not staged.exists():
            continue
        target = settings.upload_dir / role / str(new_id)
        target.mkdir(parents=True, exist_ok=True)
        for item in staged.iterdir():
            destination = target / item.name
            if destination.exists():
                raise RuntimeError(f"迁移文件冲突：{destination}")
            shutil.move(str(item), str(destination))
        staged.rmdir()
    staged_marker.unlink(missing_ok=True)
    if stage_root.exists():
        for role_dir in stage_root.iterdir():
            if role_dir.is_dir() and not any(role_dir.iterdir()):
                role_dir.rmdir()
        if not any(stage_root.iterdir()):
            stage_root.rmdir()


def _migrated_avatar(avatar: str | None, role: str, old_id: int, new_id: int) -> str | None:
    if not avatar or old_id == new_id:
        return avatar
    old_prefix = f"files/download/{role}/{old_id}/"
    new_prefix = f"files/download/{role}/{new_id}/"
    return avatar.replace(old_prefix, new_prefix, 1) if avatar.startswith(old_prefix) else avatar


def _prepare_legacy_password(stored: str) -> str:
    """Hash legacy plaintext while preserving recognized hashes for login upgrade."""
    if not password_needs_rehash(stored):
        return stored
    if stored.startswith(f"{PASSWORD_SCHEME}$"):
        return stored
    return hash_password(stored)


async def _create_current_tables(connection) -> None:
    await connection.execute_query(
        """
        CREATE TABLE IF NOT EXISTS `account` (
          `id` INT NOT NULL AUTO_INCREMENT,
          `username` VARCHAR(255) NOT NULL,
          `password` VARCHAR(255) NOT NULL,
          `name` VARCHAR(255) NOT NULL,
          `avatar` VARCHAR(500) NULL,
          `role` VARCHAR(20) NOT NULL,
          `session_version` INT NOT NULL DEFAULT 1,
          `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          PRIMARY KEY (`id`),
          UNIQUE KEY `ux_account_username` (`username`),
          KEY `ix_account_role` (`role`)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
    )
    await connection.execute_query(
        """
        CREATE TABLE IF NOT EXISTS `document` (
          `id` INT NOT NULL AUTO_INCREMENT,
          `name` VARCHAR(255) NOT NULL,
          `ext` VARCHAR(20) NOT NULL,
          `size` BIGINT NOT NULL DEFAULT 0,
          `path` VARCHAR(500) NOT NULL,
          `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          `account_id` INT NOT NULL,
          PRIMARY KEY (`id`),
          KEY `ix_document_account_id` (`account_id`),
          CONSTRAINT `fk_document_account` FOREIGN KEY (`account_id`)
            REFERENCES `account` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
    )


async def _migrate_legacy_accounts(connection) -> dict[tuple[str, int], int]:
    legacy: list[tuple[str, dict]] = []
    for role, table in (("admin", "admin"), ("user", "user")):
        if await _table_exists(connection, table):
            rows = await connection.execute_query_dict(
                f"SELECT id, username, password, name, avatar FROM `{table}` ORDER BY id"
            )
            legacy.extend((role, row) for row in rows)

    usernames: dict[str, str] = {}
    for role, row in legacy:
        username = str(row["username"])
        previous = usernames.get(username)
        if previous and previous != role:
            raise RuntimeError(f"管理员和用户存在同名账号：{username}")
        usernames[username] = role

    mapping: dict[tuple[str, int], int] = {}
    for role, row in legacy:
        old_id = int(row["id"])
        username = str(row["username"])
        existing = await connection.execute_query_dict(
            "SELECT id, role FROM `account` WHERE username = %s LIMIT 1", [username]
        )
        if existing:
            if existing[0]["role"] != role:
                raise RuntimeError(f"统一账号角色冲突：{username}")
            new_id = int(existing[0]["id"])
        else:
            password = _prepare_legacy_password(str(row["password"]))
            id_in_use = await connection.execute_query_dict(
                "SELECT 1 FROM `account` WHERE id = %s LIMIT 1", [old_id]
            )
            avatar = row.get("avatar")
            if id_in_use:
                await connection.execute_query(
                    "INSERT INTO `account` (username, password, name, avatar, role) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    [username, password, row["name"], avatar, role],
                )
            else:
                await connection.execute_query(
                    "INSERT INTO `account` (id, username, password, name, avatar, role) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    [old_id, username, password, row["name"], avatar, role],
                )
            inserted = await connection.execute_query_dict(
                "SELECT id FROM `account` WHERE username = %s LIMIT 1", [username]
            )
            new_id = int(inserted[0]["id"])

        migrated_avatar = _migrated_avatar(row.get("avatar"), role, old_id, new_id)
        if migrated_avatar != row.get("avatar"):
            await connection.execute_query(
                "UPDATE `account` SET avatar = %s WHERE id = %s", [migrated_avatar, new_id]
            )
        mapping[(role, old_id)] = new_id
    _move_account_directories(mapping)
    return mapping


async def _migrate_documents(connection, mapping: dict[tuple[str, int], int]) -> None:
    if not await _table_exists(connection, "document"):
        return
    has_legacy_owner = await _column_exists(connection, "document", "user_id")
    if has_legacy_owner and not await _column_exists(connection, "document", "account_id"):
        await connection.execute_query("ALTER TABLE `document` ADD COLUMN `account_id` INT NULL")

    if has_legacy_owner:
        for (role, old_id), account_id in mapping.items():
            await connection.execute_query(
                "UPDATE `document` SET account_id = %s "
                "WHERE user_id = %s AND role IN (%s, %s)",
                [account_id, old_id, role, "管理员" if role == "admin" else "用户"],
            )
            old_prefix = f"files/download/{role}/{old_id}/"
            new_prefix = f"files/download/{role}/{account_id}/"
            await connection.execute_query(
                "UPDATE `document` SET `path` = CONCAT(%s, SUBSTRING(`path`, CHAR_LENGTH(%s) + 1)) "
                "WHERE user_id = %s AND role IN (%s, %s) AND `path` LIKE %s",
                [new_prefix, old_prefix, old_id, role,
                 "管理员" if role == "admin" else "用户", old_prefix + "%"],
            )
        missing = await connection.execute_query_dict(
            "SELECT id FROM `document` WHERE account_id IS NULL LIMIT 1"
        )
        if missing:
            raise RuntimeError(f"文档 {missing[0]['id']} 无法匹配所属账号")
        await connection.execute_query(
            "ALTER TABLE `document` MODIFY COLUMN `account_id` INT NOT NULL"
        )
        if await _column_exists(connection, "document", "role"):
            await connection.execute_query("ALTER TABLE `document` DROP COLUMN `role`")
        await connection.execute_query("ALTER TABLE `document` DROP COLUMN `user_id`")

    if not await _index_exists(connection, "document", "ix_document_account_id"):
        await connection.execute_query(
            "ALTER TABLE `document` ADD INDEX `ix_document_account_id` (`account_id`)"
        )
    if not await _constraint_exists(connection, "document", "fk_document_account"):
        await connection.execute_query(
            "ALTER TABLE `document` ADD CONSTRAINT `fk_document_account` "
            "FOREIGN KEY (`account_id`) REFERENCES `account` (`id`) ON DELETE CASCADE"
        )


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    await _create_current_tables(connection)
    mapping = await _migrate_legacy_accounts(connection)
    await _migrate_documents(connection, mapping)

    for table in ("admin", "user"):
        if await _table_exists(connection, table):
            await connection.execute_query(f"DROP TABLE `{table}`")


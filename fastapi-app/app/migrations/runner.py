import hashlib
from pathlib import Path
import warnings

from tortoise.transactions import in_transaction

from app.migrations import (
    v001_unify_accounts,
    v002_enforce_invariants,
    v003_ai_config,
    v004_document_ocr,
    v005_multi_ai_config,
    v006_notes,
    v007_session_revocation,
    v008_document_content_version,
    v009_source_anchor,
    v010_persistent_highlights,
    v011_recycle_bin,
    v012_normalize_usernames,
    v013_document_processing_tasks,
    v014_remove_placeholder_processing_tasks,
    v015_markdown_documents,
    v016_web_imports,
    v017_web_import_lifecycle,
    v018_dashboard_reading_progress,
    v019_announcements,
    v020_experience_account,
    v021_bootstrap_experience_account,
)

MIGRATIONS = (
    v001_unify_accounts,
    v002_enforce_invariants,
    v003_ai_config,
    v004_document_ocr,
    v005_multi_ai_config,
    v006_notes,
    v007_session_revocation,
    v008_document_content_version,
    v009_source_anchor,
    v010_persistent_highlights,
    v011_recycle_bin,
    v012_normalize_usernames,
    v013_document_processing_tasks,
    v014_remove_placeholder_processing_tasks,
    v015_markdown_documents,
    v016_web_imports,
    v017_web_import_lifecycle,
    v018_dashboard_reading_progress,
    v019_announcements,
    v020_experience_account,
    v021_bootstrap_experience_account,
)

# v020 was exercised locally before its first release and then corrected to
# remove MySQL's deprecated VALUES(col) upsert syntax. Accept only those exact
# pre-release checksums once, adopt the corrected checksum, and keep rejecting
# every other form of applied-migration drift.
LEGACY_MIGRATION_CHECKSUMS = {
    20: frozenset(
        {
            "20b9ce4606e0cd3533aa780c42c67918b45d8f4119d53798214f04de244c4602",
            "9739dc7522c72ca2b74635aaa17ea61be9cad1e459c1cf332d640100f4b4059c",
        }
    ),
}


def migration_checksum(migration) -> str:
    return hashlib.sha256(Path(migration.__file__).read_bytes()).hexdigest()


def migration_checksum_is_compatible(
    version: int, recorded: str | None, current: str
) -> bool:
    """Allow current content or an explicitly reviewed pre-release checksum."""
    return recorded == current or recorded in LEGACY_MIGRATION_CHECKSUMS.get(version, ())


async def run_migrations() -> None:
    """Apply each known migration once, in a fixed reviewable order."""
    # GET_LOCK 属于 MySQL 物理会话。交易上下文会在整个迁移期间固定一条
    # 连接，避免普通连接池在不同查询间换会话导致锁实际未被持有。
    async with in_transaction("default") as connection:
        lock_rows = await connection.execute_query_dict(
            "SELECT GET_LOCK('iknowread_schema_migration', 60) AS acquired"
        )
        if not lock_rows or int(lock_rows[0]["acquired"] or 0) != 1:
            raise RuntimeError("无法取得数据库迁移锁，请确认没有其他实例同时启动")
        try:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    await connection.execute_query(
                        """
                        CREATE TABLE IF NOT EXISTS `schema_migration` (
                          `version` INT NOT NULL PRIMARY KEY,
                          `name` VARCHAR(255) NOT NULL,
                          `checksum` CHAR(64) NULL,
                          `applied_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                        """
                    )
                checksum_column = await connection.execute_query_dict(
                    "SELECT 1 FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='schema_migration' "
                    "AND COLUMN_NAME='checksum'"
                )
                if not checksum_column:
                    await connection.execute_query(
                        "ALTER TABLE `schema_migration` ADD COLUMN `checksum` CHAR(64) NULL "
                        "AFTER `name`"
                    )
                applied_rows = await connection.execute_query_dict(
                    "SELECT version, name, checksum FROM `schema_migration`"
                )
                applied = {int(row["version"]): row for row in applied_rows}
                for migration in MIGRATIONS:
                    checksum = migration_checksum(migration)
                    if migration.VERSION in applied:
                        recorded = applied[migration.VERSION].get("checksum")
                        if recorded and recorded != checksum:
                            if not migration_checksum_is_compatible(
                                migration.VERSION, recorded, checksum
                            ):
                                raise RuntimeError(
                                    f"迁移文件 v{migration.VERSION:03d} 已在应用后被修改，拒绝启动"
                                )
                            await connection.execute_query(
                                "UPDATE `schema_migration` SET `checksum`=%s WHERE `version`=%s",
                                [checksum, migration.VERSION],
                            )
                        if not recorded:
                            # Existing installations predate checksums. Adopt the
                            # currently deployed files once, then enforce immutability.
                            await connection.execute_query(
                                "UPDATE `schema_migration` SET `checksum`=%s WHERE `version`=%s",
                                [checksum, migration.VERSION],
                            )
                        continue
                    await migration.upgrade(connection)
                    await connection.execute_query(
                        "INSERT INTO `schema_migration` (version, name, checksum) "
                        "VALUES (%s, %s, %s)",
                        [migration.VERSION, migration.NAME, checksum],
                    )
            except BaseException:
                # MySQL DDL can commit implicitly. Each migration must remain
                # restart-safe; rollback still protects transactional DML/version rows.
                await connection.rollback()
                raise
            else:
                # 迁移版本记录先对其他会话可见，然后才允许下一实例取锁。
                await connection.commit()
        finally:
            await connection.execute_query("SELECT RELEASE_LOCK('iknowread_schema_migration')")

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
)

MIGRATIONS = (
    v001_unify_accounts,
    v002_enforce_invariants,
    v003_ai_config,
    v004_document_ocr,
    v005_multi_ai_config,
    v006_notes,
    v007_session_revocation,
)


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
                          `applied_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                        """
                    )
                applied_rows = await connection.execute_query_dict(
                    "SELECT version FROM `schema_migration`"
                )
                applied = {int(row["version"]) for row in applied_rows}
                for migration in MIGRATIONS:
                    if migration.VERSION in applied:
                        continue
                    await migration.upgrade(connection)
                    await connection.execute_query(
                        "INSERT INTO `schema_migration` (version, name) VALUES (%s, %s)",
                        [migration.VERSION, migration.NAME],
                    )
            except BaseException:
                # 在释放命名锁前先回滚最后一个未提交事务，避免下一实例
                # 拿到锁却读到本实例的中间状态。
                await connection.rollback()
                raise
            else:
                # 迁移版本记录先对其他会话可见，然后才允许下一实例取锁。
                await connection.commit()
        finally:
            await connection.execute_query("SELECT RELEASE_LOCK('iknowread_schema_migration')")

import asyncio
import re
import sys
from pathlib import Path

async def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import aiomysql
    from app.config import settings
    from app.migrations.runner import MIGRATIONS

    expected_migration_versions = {migration.VERSION for migration in MIGRATIONS}

    conn = await aiomysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        db=settings.DB_DATABASE,
    )
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT COUNT(*) FROM `account` "
                "WHERE password IS NULL OR password NOT LIKE 'pbkdf2_sha256$%'"
            )
            assert (await cursor.fetchone())[0] == 0, "account 中仍有未哈希密码"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'account' "
                "AND COLUMN_NAME = 'username' AND NON_UNIQUE = 0"
            )
            assert (await cursor.fetchone())[0] > 0, "account.username 缺少唯一索引"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ('admin', 'user')"
            )
            assert (await cursor.fetchone())[0] == 0, "旧账号表仍然存在"
            await cursor.execute(
                "SELECT COUNT(*) FROM document d LEFT JOIN account a ON a.id=d.account_id "
                "WHERE a.id IS NULL"
            )
            assert (await cursor.fetchone())[0] == 0, "存在无归属文档"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='document' "
                "AND COLUMN_NAME IN ('name','ext','size','path','account_id') AND IS_NULLABLE='NO'"
            )
            assert (await cursor.fetchone())[0] == 5, "文档必填列仍允许 NULL"
            await cursor.execute("SELECT version, checksum FROM schema_migration")
            migration_rows = await cursor.fetchall()
            assert {int(row[0]) for row in migration_rows} == expected_migration_versions, (
                "数据库迁移版本与当前代码不一致"
            )
            assert all(
                isinstance(row[1], str) and re.fullmatch(r"[0-9a-f]{64}", row[1])
                for row in migration_rows
            ), "数据库迁移校验和不完整"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND ((TABLE_NAME='document' "
                "AND COLUMN_NAME='content_version' AND IS_NULLABLE='NO') OR "
                "(TABLE_NAME='note' AND COLUMN_NAME='document_version'))"
            )
            assert (await cursor.fetchone())[0] == 2, "文档或笔记缺少内容版本列"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='document' "
                "AND COLUMN_NAME='deleted_at' AND IS_NULLABLE='YES'"
            )
            assert (await cursor.fetchone())[0] == 1, "文档缺少回收站时间字段"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='document' "
                "AND INDEX_NAME='ix_document__account_id__deleted_at'"
            )
            assert (await cursor.fetchone())[0] == 2, "回收站查询缺少账号与删除时间索引"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='note' "
                "AND COLUMN_NAME='source_anchor' AND DATA_TYPE='json'"
            )
            assert (await cursor.fetchone())[0] == 1, "笔记缺少统一原文定位字段"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='highlight' "
                "AND COLUMN_NAME IN ('document_version','anchor_key','source_anchor','selected_text','remark')"
            )
            assert (await cursor.fetchone())[0] == 5, "高亮表缺少版本、定位或备注字段"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='account' "
                "AND COLUMN_NAME='session_version' AND IS_NULLABLE='NO'"
            )
            assert (await cursor.fetchone())[0] == 1, "账号缺少会话撤销版本"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA=DATABASE() AND CONSTRAINT_NAME IN "
                "('fk_document_account','ck_account_role','ck_document_ext','ck_document_size')"
            )
            assert (await cursor.fetchone())[0] == 4, "数据约束不完整"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='document' "
                "AND COLUMN_NAME IN ('source_type','source_url','source_title','source_fetched_at')"
            )
            assert (await cursor.fetchone())[0] == 4, "文档缺少网页来源字段"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='web_import_job' "
                "AND CONSTRAINT_NAME IN "
                "('fk_web_import_account','fk_web_import_document','ck_web_import_status')"
            )
            assert (await cursor.fetchone())[0] == 3, "网页收藏任务约束不完整"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.CHECK_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA=DATABASE() "
                "AND CONSTRAINT_NAME='ck_web_import_status' "
                "AND CHECK_CLAUSE LIKE '%canceled%'"
            )
            assert (await cursor.fetchone())[0] == 1, "网页收藏任务状态不支持取消"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='document' "
                "AND INDEX_NAME='ux_document_path' AND NON_UNIQUE=0"
            )
            assert (await cursor.fetchone())[0] > 0, "文档路径缺少唯一约束"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='document' "
                "AND INDEX_NAME='ux_document_content_version' AND NON_UNIQUE=0"
            )
            assert (await cursor.fetchone())[0] == 1, "文档内容版本缺少唯一约束"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='ai_config' "
                "AND INDEX_NAME='ux_ai_config_account_name' AND NON_UNIQUE=0"
            )
            assert (await cursor.fetchone())[0] == 2, "模型配置缺少账号与名称联合唯一约束"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='ai_config' "
                "AND CONSTRAINT_NAME IN ('fk_ai_config_account','ck_ai_config_provider')"
            )
            assert (await cursor.fetchone())[0] == 2, "模型配置数据约束不完整"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='note' "
                "AND CONSTRAINT_NAME IN ('fk_note_account','fk_note_document','ck_note_source_type')"
            )
            assert (await cursor.fetchone())[0] == 3, "笔记数据约束不完整"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='highlight' "
                "AND CONSTRAINT_NAME IN ('fk_highlight_account','fk_highlight_document')"
            )
            assert (await cursor.fetchone())[0] == 2, "高亮账号或文档约束不完整"
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='highlight' "
                "AND INDEX_NAME='ux_highlight_anchor' AND NON_UNIQUE=0"
            )
            assert (await cursor.fetchone())[0] == 4, "高亮原文定位缺少联合唯一约束"
            await cursor.execute(
                "SELECT COUNT(*) FROM ("
                "SELECT account_id FROM ai_config GROUP BY account_id HAVING SUM(is_active) <> 1"
                ") invalid_ai_accounts"
            )
            assert (await cursor.fetchone())[0] == 0, "存在没有唯一启用模型配置的账号"
    finally:
        conn.close()
    print("database-security-check: PASS")


if __name__ == "__main__":
    asyncio.run(main())

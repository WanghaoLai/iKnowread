import asyncio
import sys
from pathlib import Path

import aiomysql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings


async def main() -> None:
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
            await cursor.execute(
                "SELECT COUNT(*) FROM schema_migration WHERE version IN (1, 2, 3, 4, 5, 6, 7)"
            )
            assert (await cursor.fetchone())[0] == 7, "数据库迁移版本不完整"
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
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='document' "
                "AND INDEX_NAME='ux_document_path' AND NON_UNIQUE=0"
            )
            assert (await cursor.fetchone())[0] > 0, "文档路径缺少唯一约束"
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

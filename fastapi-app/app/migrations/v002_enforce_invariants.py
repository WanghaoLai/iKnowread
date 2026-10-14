from tortoise import Tortoise

from app.migrations.v001_unify_accounts import _constraint_exists, _index_exists

VERSION = 2
NAME = "enforce_data_invariants"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    # 先校验存量数据满足约束；不满足时给出具体记录与处置指引，避免裸 RuntimeError 令人无从下手
    invalid_account = await connection.execute_query_dict(
        "SELECT id, username FROM `account` WHERE role NOT IN ('admin', 'user') ORDER BY id LIMIT 20"
    )
    if invalid_account:
        items = ", ".join(f"{row['id']}({row['username']})" for row in invalid_account)
        raise RuntimeError(
            f"以下账号的角色不是 admin/user，无法完成升级：{items}。"
            "请先修正这些记录（如 UPDATE account SET role='user' WHERE id=...）后重启服务。"
        )

    invalid_document = await connection.execute_query_dict(
        "SELECT id, name, ext FROM `document` WHERE name IS NULL OR name = '' "
        "OR ext IS NULL OR ext NOT IN ('pdf', 'docx') "
        "OR path IS NULL OR path = '' OR size IS NULL OR size < 0 ORDER BY id LIMIT 20"
    )
    if invalid_document:
        items = ", ".join(f"{row['id']}({row['name']}, .{row['ext']})" for row in invalid_document)
        ids = ", ".join(str(row["id"]) for row in invalid_document)
        raise RuntimeError(
            f"以下文档记录不满足约束（仅支持 PDF/DOCX）：{items}。"
            f"请先导出或删除后重启服务，例如：DELETE FROM document WHERE id IN ({ids})。"
        )
    duplicate_path = await connection.execute_query_dict(
        "SELECT path, COUNT(*) AS n FROM `document` GROUP BY path HAVING COUNT(*) > 1 LIMIT 20"
    )
    if duplicate_path:
        items = ", ".join(f"{row['path']} ×{row['n']}" for row in duplicate_path)
        raise RuntimeError(
            f"多个文档记录引用同一文件，无法确定保留哪条：{items}。"
            "请先人工去重（保留一条 DELETE 掉其余）后重启服务。"
        )

    await connection.execute_query(
        "ALTER TABLE `document` "
        "MODIFY COLUMN `name` VARCHAR(255) NOT NULL, "
        "MODIFY COLUMN `ext` VARCHAR(20) NOT NULL, "
        "MODIFY COLUMN `size` BIGINT NOT NULL DEFAULT 0, "
        "MODIFY COLUMN `path` VARCHAR(500) NOT NULL"
    )
    if not await _index_exists(connection, "document", "ux_document_path"):
        await connection.execute_query(
            "ALTER TABLE `document` ADD UNIQUE INDEX `ux_document_path` (`path`)"
        )
    if not await _constraint_exists(connection, "account", "ck_account_role"):
        await connection.execute_query(
            "ALTER TABLE `account` ADD CONSTRAINT `ck_account_role` "
            "CHECK (`role` IN ('admin', 'user'))"
        )
    if not await _constraint_exists(connection, "document", "ck_document_ext"):
        await connection.execute_query(
            "ALTER TABLE `document` ADD CONSTRAINT `ck_document_ext` "
            "CHECK (`ext` IN ('pdf', 'docx'))"
        )
    if not await _constraint_exists(connection, "document", "ck_document_size"):
        await connection.execute_query(
            "ALTER TABLE `document` ADD CONSTRAINT `ck_document_size` CHECK (`size` >= 0)"
        )

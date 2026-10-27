import asyncio

from tortoise import Tortoise

from app.security import hash_password, password_needs_rehash, verify_password


VERSION = 21
NAME = "bootstrap_experience_account"

EXPERIENCE_USERNAME = "test"
EXPERIENCE_PASSWORD = "test1234"
EXPERIENCE_NAME = "在线体验"


async def _password_is_current(stored: str | None) -> bool:
    if password_needs_rehash(stored):
        return False
    return await asyncio.to_thread(verify_password, EXPERIENCE_PASSWORD, stored)


async def upgrade(connection=None) -> None:
    """Ensure the advertised experience identity and its default policy exist."""
    connection = connection or Tortoise.get_connection("default")
    rows = await connection.execute_query_dict(
        "SELECT `id`, `role`, `password`, `is_experience` FROM `account` "
        "WHERE `username`=%s FOR UPDATE",
        [EXPERIENCE_USERNAME],
    )
    if rows:
        account = rows[0]
        if account["role"] != "user":
            raise RuntimeError("账号 test 已存在但不是普通用户，无法初始化体验账号")
        account_id = int(account["id"])
        if await _password_is_current(account.get("password")):
            if not account.get("is_experience"):
                await connection.execute_query(
                    "UPDATE `account` SET `is_experience`=TRUE WHERE `id`=%s",
                    [account_id],
                )
        else:
            password_hash = await asyncio.to_thread(hash_password, EXPERIENCE_PASSWORD)
            await connection.execute_query(
                "UPDATE `account` SET `password`=%s, `is_experience`=TRUE, "
                "`session_version`=`session_version`+1 WHERE `id`=%s",
                [password_hash, account_id],
            )
    else:
        password_hash = await asyncio.to_thread(hash_password, EXPERIENCE_PASSWORD)
        await connection.execute_query(
            "INSERT INTO `account` "
            "(`username`, `password`, `name`, `role`, `is_experience`, "
            "`session_version`, `created_at`) "
            "VALUES (%s, %s, %s, 'user', TRUE, 1, CURRENT_TIMESTAMP(6))",
            [EXPERIENCE_USERNAME, password_hash, EXPERIENCE_NAME],
        )
        rows = await connection.execute_query_dict(
            "SELECT `id`, `role`, `password`, `is_experience` FROM `account` "
            "WHERE `username`=%s FOR UPDATE",
            [EXPERIENCE_USERNAME],
        )
        if not rows:
            raise RuntimeError("体验账号创建失败")
        account_id = int(rows[0]["id"])

    await connection.execute_query(
        """
        INSERT INTO `experience_policy`
          (`account_id`, `enabled`, `public_password`, `daily_ai_limit`,
           `show_highlights`, `show_notes`)
        SELECT %s, TRUE, %s, 20, TRUE, TRUE
        WHERE NOT EXISTS (
          SELECT 1 FROM `experience_policy` WHERE `account_id`=%s
        )
        """,
        [account_id, EXPERIENCE_PASSWORD, account_id],
    )

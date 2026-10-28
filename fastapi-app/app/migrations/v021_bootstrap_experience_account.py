import asyncio
import warnings

from tortoise import Tortoise

from app.security import hash_password


VERSION = 21
NAME = "bootstrap_experience_account"

EXPERIENCE_USERNAME = "test"
EXPERIENCE_PASSWORD = "test1234"
EXPERIENCE_NAME = "在线体验"


async def upgrade(connection=None) -> None:
    """Create an experience identity only when its username is unclaimed."""
    connection = connection or Tortoise.get_connection("default")
    rows = await connection.execute_query_dict(
        "SELECT `id`, `role`, `password`, `is_experience` FROM `account` "
        "WHERE `username`=%s FOR UPDATE",
        [EXPERIENCE_USERNAME],
    )
    if rows:
        account = rows[0]
        account_id = int(account["id"])
        # An older v020 may already have marked the colliding account and
        # created a public policy.  Undo only that metadata; never modify the
        # account's password, role, name, session version, or owned data.
        await connection.execute_query(
            "DELETE FROM `experience_document_share` WHERE `account_id`=%s",
            [account_id],
        )
        await connection.execute_query(
            "DELETE FROM `experience_policy` WHERE `account_id`=%s",
            [account_id],
        )
        if account.get("is_experience"):
            await connection.execute_query(
                "UPDATE `account` SET `is_experience`=FALSE WHERE `id`=%s",
                [account_id],
            )
        warnings.warn(
            "账号 test 已存在；为保护既有身份，在线体验账号未自动创建",
            RuntimeWarning,
            stacklevel=2,
        )
        return
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

import asyncio
import secrets
import warnings

from tortoise import Tortoise

from app.security import hash_password


VERSION = 22
NAME = "repair_experience_account_collision"


async def upgrade(connection=None) -> None:
    """Quarantine accounts that v020/v021 mistook for the public identity.

    A genuine bootstrap account is created after v020 was recorded.  A `test`
    account created before that point predates the feature and must be treated
    as user-owned.  Its original password cannot be recovered after v021, so a
    random unknown password closes the leaked public credential until an
    administrator explicitly resets it.
    """
    connection = connection or Tortoise.get_connection("default")
    rows = await connection.execute_query_dict(
        """
        SELECT `account`.`id`
        FROM `account`
        INNER JOIN `schema_migration` AS `introduced`
          ON `introduced`.`version`=20
        WHERE `account`.`username`='test'
          AND `account`.`is_experience`=TRUE
          AND `account`.`created_at` < `introduced`.`applied_at`
        FOR UPDATE
        """
    )
    if not rows:
        return

    account_id = int(rows[0]["id"])
    password_hash = await asyncio.to_thread(
        hash_password, secrets.token_urlsafe(48)
    )
    await connection.execute_query(
        "DELETE FROM `experience_document_share` WHERE `account_id`=%s",
        [account_id],
    )
    await connection.execute_query(
        "DELETE FROM `experience_policy` WHERE `account_id`=%s",
        [account_id],
    )
    await connection.execute_query(
        "UPDATE `account` SET `password`=%s, `is_experience`=FALSE, "
        "`session_version`=`session_version`+1 WHERE `id`=%s",
        [password_hash, account_id],
    )
    warnings.warn(
        "检测到曾被体验迁移接管的 test 账号；已撤销公开凭据，需由管理员重置密码",
        RuntimeWarning,
        stacklevel=2,
    )

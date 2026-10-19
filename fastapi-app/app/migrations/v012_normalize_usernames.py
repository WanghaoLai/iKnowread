from tortoise import Tortoise

from app.schemas.account import normalize_username

VERSION = 12
NAME = "normalize_usernames"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    accounts = await connection.execute_query_dict(
        "SELECT `id`, `username` FROM `account` ORDER BY `id`"
    )
    normalized_by_name: dict[str, tuple[int, str]] = {}
    updates: list[tuple[str, int]] = []
    for account in accounts:
        account_id = int(account["id"])
        original = str(account["username"])
        try:
            normalized = normalize_username(original)
        except ValueError as exc:
            raise RuntimeError(f"账号 {account_id} 的用户名无法规范化") from exc
        if normalized in normalized_by_name:
            previous_id, previous_original = normalized_by_name[normalized]
            raise RuntimeError(
                "用户名规范化后发生冲突："
                f"账号 {previous_id} ({previous_original!r}) 与 "
                f"账号 {account_id} ({original!r})"
            )
        normalized_by_name[normalized] = (account_id, original)
        if normalized != original:
            updates.append((normalized, account_id))

    for normalized, account_id in updates:
        await connection.execute_query(
            "UPDATE `account` SET `username`=%s WHERE `id`=%s",
            [normalized, account_id],
        )

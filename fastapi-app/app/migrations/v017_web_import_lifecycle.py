from tortoise import Tortoise

from app.migrations.v001_unify_accounts import _constraint_exists


VERSION = 17
NAME = "web_import_lifecycle"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    if await _constraint_exists(connection, "web_import_job", "ck_web_import_status"):
        await connection.execute_query(
            "ALTER TABLE `web_import_job` DROP CHECK `ck_web_import_status`"
        )
    await connection.execute_query(
        "ALTER TABLE `web_import_job` ADD CONSTRAINT `ck_web_import_status` "
        "CHECK (`status` IN ('pending', 'processing', 'success', 'failed', 'canceled'))"
    )

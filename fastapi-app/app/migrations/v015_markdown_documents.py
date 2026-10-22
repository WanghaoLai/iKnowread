from tortoise import Tortoise

from app.migrations.v001_unify_accounts import _constraint_exists


VERSION = 15
NAME = "allow_markdown_documents"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    # v002 intentionally remains immutable because applied migration checksums
    # are verified at startup. Replace its format constraint in a new migration.
    if await _constraint_exists(connection, "document", "ck_document_ext"):
        await connection.execute_query(
            "ALTER TABLE `document` DROP CHECK `ck_document_ext`"
        )
    await connection.execute_query(
        "ALTER TABLE `document` ADD CONSTRAINT `ck_document_ext` "
        "CHECK (`ext` IN ('pdf', 'docx', 'md'))"
    )

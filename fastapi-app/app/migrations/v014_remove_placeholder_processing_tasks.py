from tortoise import Tortoise


VERSION = 14
NAME = "remove_placeholder_processing_tasks"


async def upgrade(connection=None) -> None:
    connection = connection or Tortoise.get_connection("default")
    # These task types were exposed before any worker existed for them. Keeping
    # their permanent "not_started" rows presents planned work as live work.
    await connection.execute_query(
        "DELETE FROM `document_processing_task` "
        "WHERE `task_type` IN ('text_extraction', 'index_rebuild')"
    )

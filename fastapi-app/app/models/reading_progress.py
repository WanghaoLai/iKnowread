from tortoise import fields
from tortoise.models import Model


class ReadingProgress(Model):
    """Latest version-bound reading position for one account and document."""

    id = fields.IntField(primary_key=True)
    account = fields.ForeignKeyField(
        "models.Account", related_name="reading_progress", on_delete=fields.CASCADE
    )
    document = fields.ForeignKeyField(
        "models.Document", related_name="reading_progress", on_delete=fields.CASCADE
    )
    document_version = fields.CharField(max_length=32)
    source_anchor = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "reading_progress"
        unique_together = (("account", "document"),)
        indexes = (("account", "updated_at"),)

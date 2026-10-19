from tortoise import fields
from tortoise.models import Model


class Highlight(Model):
    id = fields.IntField(primary_key=True)
    account = fields.ForeignKeyField(
        "models.Account", related_name="highlights", on_delete=fields.CASCADE
    )
    document = fields.ForeignKeyField(
        "models.Document", related_name="highlights", on_delete=fields.CASCADE
    )
    document_version = fields.CharField(max_length=32)
    anchor_key = fields.CharField(max_length=64)
    source_anchor = fields.JSONField()
    selected_text = fields.TextField()
    remark = fields.TextField(default="")
    provider = fields.CharField(max_length=50, null=True)
    config_name = fields.CharField(max_length=100, null=True)
    model = fields.CharField(max_length=100, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "highlight"
        ordering = ["-created_at", "-id"]
        indexes = (("account", "document", "document_version"),)
        unique_together = (("account", "document", "document_version", "anchor_key"),)

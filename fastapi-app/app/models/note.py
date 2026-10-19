from tortoise import fields
from tortoise.models import Model


class Note(Model):
    id = fields.IntField(primary_key=True)
    account = fields.ForeignKeyField(
        "models.Account", related_name="notes", on_delete=fields.CASCADE
    )
    document = fields.ForeignKeyField(
        "models.Document", related_name="notes", null=True, on_delete=fields.SET_NULL
    )
    document_name = fields.CharField(max_length=255, null=True)
    document_version = fields.CharField(max_length=32, null=True)
    source_anchor = fields.JSONField(null=True)
    source_type = fields.CharField(max_length=30, default="manual")
    title = fields.CharField(max_length=200)
    selected_text = fields.TextField(null=True)
    content = fields.TextField()
    remark = fields.TextField(default="")
    provider = fields.CharField(max_length=50, null=True)
    config_name = fields.CharField(max_length=100, null=True)
    model = fields.CharField(max_length=100, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "note"
        ordering = ["-created_at"]
        indexes = (("account", "created_at"), ("account", "document"))

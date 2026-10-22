from tortoise import fields
from tortoise.models import Model


class WebImportJob(Model):
    """A durable URL-to-Markdown import owned by one account."""

    id = fields.IntField(primary_key=True)
    account = fields.ForeignKeyField(
        "models.Account", related_name="web_import_jobs", on_delete=fields.CASCADE
    )
    source_url = fields.CharField(max_length=2048)
    status = fields.CharField(max_length=20, default="pending")
    progress = fields.IntField(default=0)
    error = fields.CharField(max_length=500, null=True)
    attempt_count = fields.IntField(default=0)
    result_document = fields.ForeignKeyField(
        "models.Document", related_name="web_import_jobs",
        null=True, on_delete=fields.SET_NULL,
    )
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "web_import_job"
        indexes = (("account", "created_at"), ("status", "updated_at"))

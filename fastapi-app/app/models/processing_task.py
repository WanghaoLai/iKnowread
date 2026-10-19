from tortoise import fields
from tortoise.models import Model


class DocumentProcessingTask(Model):
    """A durable, document-scoped status row for background processing stages."""

    id = fields.IntField(primary_key=True)
    document = fields.ForeignKeyField(
        "models.Document", related_name="processing_tasks", on_delete=fields.CASCADE
    )
    task_type = fields.CharField(max_length=30)
    status = fields.CharField(max_length=20, default="not_started")
    progress = fields.IntField(default=0)
    error = fields.CharField(max_length=500, null=True)
    attempt_count = fields.IntField(default=0)
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "document_processing_task"
        unique_together = (("document", "task_type"),)
        indexes = (("status", "updated_at"),)

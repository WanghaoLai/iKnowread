from tortoise import fields
from tortoise.models import Model


class Announcement(Model):
    id = fields.IntField(primary_key=True)
    title = fields.CharField(max_length=200)
    content = fields.TextField()
    status = fields.CharField(max_length=20, default="draft")
    published_revision = fields.IntField(default=0)
    published_at = fields.DatetimeField(null=True)
    created_by = fields.ForeignKeyField(
        "models.Account",
        related_name="created_announcements",
        null=True,
        on_delete=fields.SET_NULL,
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "announcement"
        ordering = ["-published_at", "-id"]
        indexes = (("status", "published_at"),)


class AnnouncementRead(Model):
    id = fields.IntField(primary_key=True)
    account = fields.ForeignKeyField(
        "models.Account", related_name="announcement_reads", on_delete=fields.CASCADE
    )
    announcement = fields.ForeignKeyField(
        "models.Announcement", related_name="read_records", on_delete=fields.CASCADE
    )
    read_revision = fields.IntField()
    read_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "announcement_read"
        unique_together = (("account", "announcement"),)
        indexes = (("account", "read_at"),)

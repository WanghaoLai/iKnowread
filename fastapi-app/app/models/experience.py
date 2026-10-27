from tortoise import fields
from tortoise.models import Model


class ExperiencePolicy(Model):
    """Server-enforced policy for an explicitly marked experience account."""

    id = fields.IntField(primary_key=True)
    account = fields.OneToOneField(
        "models.Account", related_name="experience_policy", on_delete=fields.CASCADE
    )
    enabled = fields.BooleanField(default=True)
    public_password = fields.CharField(max_length=128, default="")
    ai_config = fields.ForeignKeyField(
        "models.AIConfig", related_name="experience_policies",
        null=True, on_delete=fields.SET_NULL,
    )
    daily_ai_limit = fields.IntField(default=20)
    ai_usage_date = fields.DateField(null=True)
    ai_used_today = fields.IntField(default=0)
    show_highlights = fields.BooleanField(default=True)
    show_notes = fields.BooleanField(default=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "experience_policy"


class ExperienceDocumentShare(Model):
    """An administrator-owned document explicitly exposed to an experience account."""

    id = fields.IntField(primary_key=True)
    account = fields.ForeignKeyField(
        "models.Account", related_name="experience_document_shares",
        on_delete=fields.CASCADE,
    )
    document = fields.ForeignKeyField(
        "models.Document", related_name="experience_shares",
        on_delete=fields.CASCADE,
    )
    shared_by = fields.ForeignKeyField(
        "models.Account", related_name="experience_shares_created",
        null=True, on_delete=fields.SET_NULL,
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "experience_document_share"
        unique_together = (("account", "document"),)
        indexes = (("account", "created_at"),)

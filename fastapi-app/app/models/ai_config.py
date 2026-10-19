from tortoise import fields
from tortoise.models import Model


class AIConfig(Model):
    id = fields.IntField(primary_key=True)
    account = fields.ForeignKeyField("models.Account", related_name="ai_configs", on_delete=fields.CASCADE)
    provider = fields.CharField(max_length=20, default="deepseek")
    name = fields.CharField(max_length=100)
    base_url = fields.CharField(max_length=255)
    model = fields.CharField(max_length=100)
    encrypted_api_key = fields.TextField()
    temperature = fields.FloatField(default=1)
    max_tokens = fields.IntField(default=4096)
    thinking = fields.BooleanField(default=False)
    system_prompt = fields.TextField(default="")
    is_active = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ai_config"
        unique_together = (("account", "name"),)
        indexes = (("account", "is_active"),)

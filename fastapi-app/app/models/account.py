from tortoise import fields
from tortoise.models import Model


class Account(Model):
    """The single identity model used by administrators and regular users."""

    id = fields.IntField(primary_key=True)
    username = fields.CharField(max_length=255, unique=True)
    password = fields.CharField(max_length=255)
    name = fields.CharField(max_length=255)
    avatar = fields.CharField(max_length=500, null=True)
    role = fields.CharField(max_length=20, db_index=True)
    session_version = fields.IntField(default=1)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "account"


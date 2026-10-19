import secrets

from tortoise.models import Model
from tortoise import fields


def new_content_version() -> str:
    """为一次可见文档内容快照生成不可复用的标识。"""
    return secrets.token_hex(16)


class Document(Model):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=255)
    ext = fields.CharField(max_length=20)
    size = fields.BigIntField(default=0)
    path = fields.CharField(max_length=500)
    content_version = fields.CharField(max_length=32, unique=True, default=new_content_version)
    ocr_status = fields.CharField(max_length=20, default="not_applicable")
    ocr_path = fields.CharField(max_length=500, null=True)
    ocr_error = fields.CharField(max_length=500, null=True)
    ocr_updated_at = fields.DatetimeField(null=True)
    deleted_at = fields.DatetimeField(null=True)
    account = fields.ForeignKeyField(
        "models.Account", related_name="documents", on_delete=fields.CASCADE
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "document"
        ordering = ["-created_at"]
        indexes = (("account", "deleted_at"),)

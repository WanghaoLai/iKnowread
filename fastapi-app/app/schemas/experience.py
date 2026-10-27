from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExperienceSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    public_password: str = Field(min_length=8, max_length=128)
    ai_config_id: int | None = Field(default=None, ge=1)
    daily_ai_limit: int = Field(default=20, ge=0, le=1000)
    show_highlights: bool = True
    show_notes: bool = True
    document_ids: list[int] = Field(default_factory=list, max_length=200)

    @field_validator("document_ids")
    @classmethod
    def unique_documents(cls, value: list[int]) -> list[int]:
        if any(document_id < 1 for document_id in value):
            raise ValueError("文档编号无效")
        if len(set(value)) != len(value):
            raise ValueError("共享文档不能重复")
        return value


class ExperienceCapability(BaseModel):
    enabled: bool = False
    username: str = ""
    password: str = ""


class ExperienceSessionPolicy(BaseModel):
    is_experience: bool
    enabled: bool = False
    ai_enabled: bool = False
    daily_ai_limit: int = 0
    ai_used_today: int = 0
    ai_remaining_today: int = 0
    show_highlights: bool = False
    show_notes: bool = False
    document_upload_limit: int = 0
    storage_quota_bytes: int = 0
    usage_date: date | None = None

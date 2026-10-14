from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NoteCreate(BaseModel):
    source_type: Literal["manual", "ai_explanation"] = "manual"
    document_id: int | None = Field(default=None, ge=1)
    title: str = Field(default="", max_length=200)
    selected_text: str | None = Field(default=None, max_length=4000)
    content: str = Field(min_length=1, max_length=50000)
    remark: str = Field(default="", max_length=5000)
    provider: str | None = Field(default=None, max_length=50)
    config_name: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)

    @field_validator("title", "content", "remark", mode="before")
    @classmethod
    def strip_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("selected_text", "provider", "config_name", "model", mode="before")
    @classmethod
    def strip_optional_text(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_source(self):
        if self.source_type == "ai_explanation":
            if not self.document_id:
                raise ValueError("AI 划词笔记必须关联来源文档")
            if not self.selected_text:
                raise ValueError("AI 划词笔记必须包含选中文字")
        return self


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=50000)
    remark: str | None = Field(default=None, max_length=5000)

    @field_validator("title", "content", "remark", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def reject_explicit_null(self):
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} 不能为 null")
        return self


class NotePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int | None
    document_name: str | None
    source_type: str
    title: str
    selected_text: str | None
    content: str
    remark: str
    provider: str | None
    config_name: str | None
    model: str | None
    created_at: datetime
    updated_at: datetime

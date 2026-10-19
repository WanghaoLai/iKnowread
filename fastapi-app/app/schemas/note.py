from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.source_anchor import SourceAnchor, normalize_selected_text


class NoteCreate(BaseModel):
    source_type: Literal["manual", "ai_explanation"] = "manual"
    document_id: int | None = Field(default=None, ge=1)
    document_version: str | None = Field(default=None, min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")
    source_anchor: SourceAnchor | None = None
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

    @field_validator("selected_text", "document_version", "provider", "config_name", "model", mode="before")
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
            if not self.document_version:
                raise ValueError("AI 划词笔记必须包含文档版本")
            if not self.source_anchor or not self.source_anchor.selector:
                raise ValueError("AI 划词笔记必须包含原文定位")
        if self.source_anchor and self.source_anchor.selector:
            if not self.selected_text:
                raise ValueError("带原文定位的笔记必须包含选中文字")
            if normalize_selected_text(self.source_anchor.selector.quote.exact) != self.selected_text:
                raise ValueError("笔记选中文字与原文定位不一致")
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


class NoteExportRequest(BaseModel):
    scope: Literal["all", "document", "selected"]
    document_id: int | None = Field(default=None, ge=1)
    document_name: str | None = Field(default=None, max_length=255)
    unlinked: bool = False
    note_ids: list[int] = Field(default_factory=list, max_length=5000)

    @field_validator("document_name", mode="before")
    @classmethod
    def strip_document_name(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        return value or None

    @field_validator("note_ids")
    @classmethod
    def unique_note_ids(cls, value):
        if any(note_id < 1 for note_id in value):
            raise ValueError("笔记 ID 无效")
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_scope(self):
        document_selectors = sum((
            self.document_id is not None,
            self.document_name is not None,
            self.unlinked,
        ))
        if self.scope == "document" and document_selectors != 1:
            raise ValueError("按文档导出时必须选择一个文档")
        if self.scope == "document" and self.note_ids:
            raise ValueError("按文档导出不能同时指定笔记")
        if self.scope == "selected" and not self.note_ids:
            raise ValueError("批量导出时至少选择一条笔记")
        if self.scope == "selected" and document_selectors:
            raise ValueError("批量导出不能同时指定文档")
        if self.scope == "all" and (document_selectors or self.note_ids):
            raise ValueError("全量导出不能附带筛选条件")
        return self


class NotePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int | None
    document_name: str | None
    document_version: str | None
    document_status: Literal["available", "recycled", "deleted", "unlinked"] = "unlinked"
    source_anchor: dict | None
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

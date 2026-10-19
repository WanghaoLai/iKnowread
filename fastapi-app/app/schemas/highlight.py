from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.source_anchor import SourceAnchor, normalize_selected_text


class HighlightCreate(BaseModel):
    document_id: int = Field(ge=1)
    source_anchor: SourceAnchor
    selected_text: str = Field(min_length=1, max_length=4000)
    remark: str = Field(default="", max_length=12000)
    provider: str | None = Field(default=None, max_length=50)
    config_name: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)

    @field_validator("selected_text", "remark", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("provider", "config_name", "model", mode="before")
    @classmethod
    def strip_optional_text(cls, value):
        if not isinstance(value, str):
            return value
        return value.strip() or None

    @model_validator(mode="after")
    def require_text_selector(self):
        if not self.source_anchor.selector:
            raise ValueError("高亮必须包含原文文本定位")
        if normalize_selected_text(self.source_anchor.selector.quote.exact) != self.selected_text:
            raise ValueError("高亮文字与原文定位不一致")
        return self


class HighlightUpdate(BaseModel):
    remark: str = Field(max_length=12000)

    @field_validator("remark", mode="before")
    @classmethod
    def strip_remark(cls, value):
        return value.strip() if isinstance(value, str) else value


class HighlightPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    document_version: str
    source_anchor: dict
    selected_text: str
    remark: str
    provider: str | None
    config_name: str | None
    model: str | None
    created_at: datetime
    updated_at: datetime

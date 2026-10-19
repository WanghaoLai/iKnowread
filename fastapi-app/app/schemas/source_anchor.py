import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SOURCE_ANCHOR_PROTOCOL = "iknowread.source-anchor/v1"


def normalize_selected_text(value: str) -> str:
    """Canonical display form shared by anchor-backed API payloads."""
    compact = re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip()
    return re.sub(r"([\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", r"\1", compact)


class TextQuoteSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exact: str = Field(min_length=1, max_length=8000)
    prefix: str = Field(default="", max_length=200)
    suffix: str = Field(default="", max_length=200)


class TextPositionSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("文本定位结束位置必须大于开始位置")
        return self


class SourceTextSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: TextPositionSelector
    quote: TextQuoteSelector


class SourceAnchor(BaseModel):
    """跨阅读进度、高亮、搜索和 AI 引用共用的原文定位协议。"""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["iknowread.source-anchor/v1"] = SOURCE_ANCHOR_PROTOCOL
    document_id: int = Field(ge=1)
    document_version: str = Field(
        min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$"
    )
    source_format: Literal["pdf", "docx"]
    scope: Literal["page", "document"]
    page: int | None = Field(default=None, ge=1)
    progression: float = Field(default=0, ge=0, le=1)
    selector: SourceTextSelector | None = None

    @model_validator(mode="after")
    def format_scope(self):
        if self.source_format == "pdf" and (self.scope != "page" or self.page is None):
            raise ValueError("PDF 定位必须包含页码并使用 page 范围")
        if self.source_format == "docx" and (self.scope != "document" or self.page is not None):
            raise ValueError("DOCX 定位必须使用 document 范围且不包含页码")
        return self

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


AnnouncementStatus = Literal["draft", "published", "offline"]


def _required_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("内容不能为空")
    return value


class AnnouncementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=100_000)
    status: Literal["draft", "published"] = "draft"

    _normalize_title = field_validator("title")(_required_text)
    _normalize_content = field_validator("content")(_required_text)


class AnnouncementUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=100_000)

    _normalize_title = field_validator("title")(_required_text)
    _normalize_content = field_validator("content")(_required_text)


class AnnouncementStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AnnouncementStatus


class AnnouncementAdminPublic(BaseModel):
    id: int
    title: str
    content: str
    status: AnnouncementStatus
    published_revision: int
    published_at: datetime | None
    created_by_id: int | None
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime


class AnnouncementPublic(BaseModel):
    id: int
    title: str
    content: str
    published_revision: int
    published_at: datetime
    is_read: bool


class AnnouncementReadPublic(BaseModel):
    announcement_id: int
    read_revision: int
    read_at: datetime

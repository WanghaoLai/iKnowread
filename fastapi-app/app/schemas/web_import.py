from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.url_safety import normalize_public_url


class WebImportCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_public_url(value)


class WebImportJobPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_url: str
    status: str
    progress: int
    error: str | None
    attempt_count: int
    result_document_id: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentProcessingStagePublic(BaseModel):
    type: str
    label: str
    status: str
    progress: int
    error: str | None = None
    updated_at: datetime | None = None


class DocumentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ext: str
    size: int
    content_version: str
    ocr_status: str
    ocr_error: str | None
    ocr_updated_at: datetime | None
    deleted_at: datetime | None
    account_id: int
    created_at: datetime
    processing_stages: list[DocumentProcessingStagePublic] = Field(default_factory=list)

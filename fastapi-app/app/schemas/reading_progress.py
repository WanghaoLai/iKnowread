from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.source_anchor import SourceAnchor


class ReadingProgressUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_anchor: SourceAnchor


class ReadingProgressPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: int
    document_version: str
    source_anchor: SourceAnchor
    updated_at: datetime

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ext: str
    size: int
    path: str
    ocr_status: str
    ocr_error: str | None
    ocr_updated_at: datetime | None
    account_id: int
    created_at: datetime

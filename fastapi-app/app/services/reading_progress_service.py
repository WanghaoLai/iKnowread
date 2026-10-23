from app.common.exception_handler import CustomException
from app.models import Document, ReadingProgress
from app.schemas.reading_progress import ReadingProgressPublic


def serialize(record: ReadingProgress) -> dict:
    return ReadingProgressPublic.model_validate(record).model_dump()


async def _current_document(account_id: int, document_id: int) -> Document:
    document = await Document.get_or_none(
        id=document_id,
        account_id=account_id,
        deleted_at__isnull=True,
    )
    if document is None:
        raise CustomException("文档不存在", status_code=404)
    return document


async def save(account_id: int, anchor) -> dict:
    document = await _current_document(account_id, anchor.document_id)
    if (
        anchor.document_version != document.content_version
        or anchor.source_format != document.ext
    ):
        raise CustomException("阅读进度与当前文档版本不一致，请刷新后重试", status_code=409)
    record, _ = await ReadingProgress.update_or_create(
        account_id=account_id,
        document_id=document.id,
        defaults={
            "document_version": document.content_version,
            "source_anchor": anchor.model_dump(),
        },
    )
    return serialize(record)


async def get_current(account_id: int, document_id: int) -> dict | None:
    document = await _current_document(account_id, document_id)
    record = await ReadingProgress.get_or_none(
        account_id=account_id,
        document_id=document.id,
        document_version=document.content_version,
    )
    return serialize(record) if record else None

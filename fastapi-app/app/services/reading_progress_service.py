from app.common.exception_handler import CustomException
from app.models import Document, ReadingProgress
from app.schemas.reading_progress import ReadingProgressPublic
from app.dependencies import CurrentAccount


def serialize(record: ReadingProgress) -> dict:
    return ReadingProgressPublic.model_validate(record).model_dump()


async def _current_document(current: CurrentAccount | int, document_id: int) -> Document:
    document = await Document.get_or_none(id=document_id, deleted_at__isnull=True)
    if document is None:
        raise CustomException("文档不存在", status_code=404)
    if isinstance(current, int):
        if document.account_id != current:
            raise CustomException("文档不存在", status_code=404)
    elif not current.is_experience:
        if document.account_id != current.id:
            raise CustomException("文档不存在", status_code=404)
    else:
        from app.services import experience_service
        await experience_service.require_document_read(current, document)
    return document


async def save(current: CurrentAccount | int, anchor) -> dict:
    account_id = current if isinstance(current, int) else current.id
    document = await _current_document(current, anchor.document_id)
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


async def get_current(current: CurrentAccount | int, document_id: int) -> dict | None:
    account_id = current if isinstance(current, int) else current.id
    document = await _current_document(current, document_id)
    record = await ReadingProgress.get_or_none(
        account_id=account_id,
        document_id=document.id,
        document_version=document.content_version,
    )
    return serialize(record) if record else None

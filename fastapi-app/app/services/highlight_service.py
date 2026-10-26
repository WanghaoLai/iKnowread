import hashlib
import json

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.common.exception_handler import CustomException
from app.config import settings
from app.dependencies import CurrentAccount
from app.models import Account, Document, Highlight
from app.schemas.highlight import HighlightCreate, HighlightPublic, HighlightUpdate


def serialize(highlight: Highlight) -> dict:
    return HighlightPublic.model_validate(highlight).model_dump()


def _anchor_key(anchor: dict) -> str:
    # progression 是当时的滚动比例，会随视口高度变化；高亮身份只由版本、
    # 页码和文本选择器决定，避免同一段文字换个窗口大小后被重复保存。
    identity = {key: value for key, value in anchor.items() if key != "progression"}
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _owned_document(current: CurrentAccount, document_id: int) -> Document:
    document = await Document.get_or_none(id=document_id, deleted_at__isnull=True)
    if document is None:
        raise CustomException("文档不存在", status_code=404)
    from app.services import experience_service
    await experience_service.require_document_read(current, document)
    return document


def _validate_anchor(document: Document, anchor) -> None:
    if (
        anchor.document_id != document.id
        or anchor.document_version != document.content_version
        or anchor.source_format != document.ext
    ):
        raise CustomException("原文定位与当前文档版本不一致，请重新选择内容", status_code=409)


async def list_current(
    current: CurrentAccount, document_id: int, document_version: str
) -> list[dict]:
    document = await _owned_document(current, document_id)
    if document_version != document.content_version:
        raise CustomException("文档内容已更新，请刷新后查看高亮", status_code=409)
    from app.services import experience_service
    owner_id = current.id
    read_only = False
    if current.is_experience:
        policy = await experience_service.require_enabled(current)
        if not policy.show_highlights:
            return []
        owner_id = document.account_id
        read_only = True
    records = await Highlight.filter(
        account_id=owner_id,
        document_id=document.id,
        document_version=document_version,
    ).order_by("-created_at", "-id").limit(max(1, settings.DOCUMENT_HIGHLIGHT_LIMIT))
    result = [serialize(record) for record in records]
    for item in result:
        item["read_only"] = read_only
    return result


async def create(current: CurrentAccount, payload: HighlightCreate) -> dict:
    from app.services import experience_service
    experience_service.deny_experience_write(current, "添加高亮")
    document = await _owned_document(current, payload.document_id)
    _validate_anchor(document, payload.source_anchor)
    anchor = payload.source_anchor.model_dump()
    key = _anchor_key(anchor)
    try:
        async with in_transaction() as connection:
            account = await Account.filter(id=current.id).using_db(
                connection
            ).select_for_update().first()
            if account is None:
                raise CustomException("账号不存在", status_code=404)
            existing = await Highlight.get_or_none(
                account_id=current.id,
                document_id=document.id,
                document_version=document.content_version,
                anchor_key=key,
                using_db=connection,
            )
            if existing is not None:
                raise CustomException("该内容已经高亮，可在高亮管理中编辑备注", status_code=409)
            total = await Highlight.filter(account_id=current.id).using_db(connection).count()
            if total >= max(1, settings.USER_HIGHLIGHT_LIMIT):
                raise CustomException("高亮数量已达到账号上限，请先删除不需要的高亮", status_code=413)
            document_total = await Highlight.filter(
                account_id=current.id,
                document_id=document.id,
            ).using_db(connection).count()
            if document_total >= max(1, settings.DOCUMENT_HIGHLIGHT_LIMIT):
                raise CustomException("当前文档的高亮数量已达到上限", status_code=413)
            record = await Highlight.create(
                account_id=current.id,
                document_id=document.id,
                document_version=document.content_version,
                anchor_key=key,
                source_anchor=anchor,
                selected_text=payload.selected_text,
                remark=payload.remark,
                provider=payload.provider,
                config_name=payload.config_name,
                model=payload.model,
                using_db=connection,
            )
    except IntegrityError:
        # 查询与写入之间仍可能有并发请求，由数据库唯一约束完成最终仲裁。
        raise CustomException(
            "该内容已经高亮，可在高亮管理中编辑备注", status_code=409
        ) from None
    return serialize(record)


async def get_owned(account_id: int, highlight_id: int) -> Highlight:
    record = await Highlight.get_or_none(
        id=highlight_id,
        account_id=account_id,
        document__deleted_at__isnull=True,
    )
    if record is None:
        raise CustomException("高亮不存在", status_code=404)
    return record


async def update(account_id: int, highlight_id: int, payload: HighlightUpdate) -> dict:
    record = await get_owned(account_id, highlight_id)
    record.remark = payload.remark
    await record.save(update_fields=["remark", "updated_at"])
    return serialize(record)


async def delete(account_id: int, highlight_id: int) -> None:
    record = await get_owned(account_id, highlight_id)
    await record.delete()

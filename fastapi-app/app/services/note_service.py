from datetime import datetime

from tortoise.expressions import Q
from tortoise.functions import Count
from tortoise.transactions import in_transaction

from app.common.exception_handler import CustomException
from app.dependencies import CurrentAccount, require_document_owner
from app.models import Account, Document, Note
from app.schemas.note import NoteCreate, NotePublic, NoteUpdate
from app.services.ai_providers import get_provider
from app.config import settings


def _document_status(note: Note, document_states: dict[int, object] | None = None) -> str:
    if note.document_id is None:
        return "deleted" if note.document_name else "unlinked"
    deleted_at = (document_states or {}).get(note.document_id)
    return "recycled" if deleted_at is not None else "available"


def serialize(note: Note, document_states: dict[int, object] | None = None) -> dict:
    payload = NotePublic.model_validate(note).model_dump()
    payload["document_status"] = _document_status(note, document_states)
    return payload


async def _document_states(notes: list[Note]) -> dict[int, object]:
    document_ids = {note.document_id for note in notes if note.document_id is not None}
    if not document_ids:
        return {}
    rows = await Document.filter(id__in=document_ids).values("id", "deleted_at")
    return {int(row["id"]): row["deleted_at"] for row in rows}


def _query(
    account_id: int, keyword: str = "", document_id: int | None = None,
    unlinked: bool = False, document_name: str | None = None,
):
    query = Note.filter(account_id=account_id)
    if keyword := keyword.strip():
        query = query.filter(
            Q(title__icontains=keyword)
            | Q(document_name__icontains=keyword)
            | Q(selected_text__icontains=keyword)
            | Q(content__icontains=keyword)
            | Q(remark__icontains=keyword)
        )
    if unlinked:
        # 仅指从未关联过文档的笔记；原文档已删除的笔记按 document_name 分组过滤。
        query = query.filter(document_id__isnull=True, document_name__isnull=True)
    elif document_name is not None:
        query = query.filter(document_id__isnull=True, document_name=document_name)
    elif document_id is not None:
        query = query.filter(document_id=document_id)
    return query


def _ordered(query, sort: str):
    if sort == "oldest":
        return query.order_by("created_at", "id")
    if sort == "document":
        return query.order_by("document_name", "-created_at", "-id")
    return query.order_by("-created_at", "-id")


def _default_title(payload: NoteCreate, document_name: str | None) -> str:
    if payload.title:
        return payload.title
    if payload.selected_text:
        compact = " ".join(payload.selected_text.split())
        return compact[:60] + ("…" if len(compact) > 60 else "")
    if document_name:
        return f"《{document_name}》阅读笔记"[:200]
    return "未命名笔记"


async def create(current: CurrentAccount, payload: NoteCreate) -> dict:
    document = None
    if payload.document_id is not None:
        document = await Document.get_or_none(id=payload.document_id, deleted_at__isnull=True)
        if document is None:
            raise CustomException("来源文档不存在", status_code=404)
        require_document_owner(current, document)
        if (
            payload.source_type == "ai_explanation"
            and payload.document_version != document.content_version
        ):
            raise CustomException(
                "文档内容已更新，请重新选择内容后再添加笔记", status_code=409
            )
        if payload.source_anchor and (
            payload.source_anchor.document_id != document.id
            or payload.source_anchor.document_version != document.content_version
            or payload.source_anchor.source_format != document.ext
        ):
            raise CustomException("原文定位与当前文档不一致，请重新选择内容", status_code=409)
    elif payload.source_anchor:
        raise CustomException("原文定位必须关联来源文档")
    async with in_transaction() as connection:
        account = await Account.filter(id=current.id).using_db(
            connection
        ).select_for_update().first()
        if account is None:
            raise CustomException("账号不存在", status_code=404)
        note_count = await Note.filter(account_id=current.id).using_db(connection).count()
        if note_count >= max(1, settings.USER_NOTE_LIMIT):
            raise CustomException("笔记数量已达到账号上限，请先删除不需要的笔记", status_code=413)
        note = await Note.create(
            account_id=current.id,
            document_id=document.id if document else None,
            document_name=document.name if document else None,
            document_version=document.content_version if document else None,
            source_anchor=payload.source_anchor.model_dump() if payload.source_anchor else None,
            source_type=payload.source_type,
            title=_default_title(payload, document.name if document else None),
            selected_text=payload.selected_text,
            content=payload.content,
            remark=payload.remark,
            provider=payload.provider,
            config_name=payload.config_name,
            model=payload.model,
            using_db=connection,
        )
    return serialize(note)


async def select_page(
    account_id: int,
    keyword: str,
    document_id: int | None,
    unlinked: bool,
    document_name: str | None,
    sort: str,
    page_num: int,
    page_size: int,
) -> dict:
    query = _query(account_id, keyword, document_id, unlinked, document_name)
    notes = await _ordered(query, sort).offset((page_num - 1) * page_size).limit(page_size)
    document_states = await _document_states(notes)
    return {
        "total": await query.count(),
        "list": [serialize(note, document_states) for note in notes],
    }


async def summary(account_id: int) -> dict:
    # 返回原始 document_name（可空）：已删文档的笔记按原名各自分组，
    # 前端用「name:文档名」精确过滤，避免多个已删文档的笔记混在一个筛选里。
    rows = await Note.filter(account_id=account_id).group_by(
        "document_id", "document_name"
    ).annotate(count=Count("id")).values("document_id", "document_name", "count")
    items = [{
        "document_id": row["document_id"],
        "document_name": row["document_name"],
        "count": int(row["count"]),
    } for row in rows]
    items.sort(key=lambda item: (-item["count"], item["document_name"] or ""))
    return {"total": sum(item["count"] for item in items), "documents": items}


async def get_owned(account_id: int, note_id: int) -> Note:
    note = await Note.get_or_none(id=note_id, account_id=account_id)
    if note is None:
        raise CustomException("笔记不存在", status_code=404)
    return note


async def update(account_id: int, note_id: int, payload: NoteUpdate) -> dict:
    note = await get_owned(account_id, note_id)
    document_states = await _document_states([note])
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return serialize(note, document_states)
    for field, value in changes.items():
        setattr(note, field, value)
    await note.save(update_fields=[*changes.keys(), "updated_at"])
    return serialize(note, document_states)


async def delete(account_id: int, note_id: int) -> None:
    note = await get_owned(account_id, note_id)
    await note.delete()


def _markdown_text(value: str | None, *, quote: bool = False) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if quote:
        return "\n".join(f"> {line}" if line else ">" for line in value.splitlines())
    return value


async def export_markdown(
    account_id: int, keyword: str, document_id: int | None,
    unlinked: bool, document_name: str | None, sort: str,
    note_ids: list[int] | None = None,
) -> str:
    # Count and all pages must observe one database snapshot. Otherwise an insert
    # or delete between OFFSET batches can duplicate or omit notes.
    async with in_transaction() as connection:
        return await _export_markdown_snapshot(
            connection, account_id, keyword, document_id, unlinked,
            document_name, sort, note_ids,
        )


async def _export_markdown_snapshot(
    connection,
    account_id: int, keyword: str, document_id: int | None,
    unlinked: bool, document_name: str | None, sort: str,
    note_ids: list[int] | None,
) -> str:
    query = _query(
        account_id, keyword, document_id, unlinked, document_name
    ).using_db(connection)
    if note_ids is not None:
        query = query.filter(id__in=note_ids)
    query = _ordered(query, sort)
    total = await query.count()
    if note_ids is not None and total != len(note_ids):
        raise CustomException("选中的笔记已变化，请刷新后重新选择", status_code=409)
    if total > max(1, settings.NOTE_EXPORT_MAX_ITEMS):
        raise CustomException(
            f"一次最多导出 {settings.NOTE_EXPORT_MAX_ITEMS} 条笔记，请先缩小筛选范围",
            status_code=413,
        )
    exported_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    lines = ["# 我的笔记", "", f"> 导出时间：{exported_at}　共 {total} 条", ""]
    output_bytes = sum(len(line.encode("utf-8")) + 1 for line in lines)
    current_document = object()
    for offset in range(0, total, 100):
        notes = await query.offset(offset).limit(100)
        for note in notes:
            block: list[str] = []
            document_name = note.document_name or "未关联文档"
            if sort == "document" and document_name != current_document:
                current_document = document_name
                block.extend([f"## {document_name}", ""])
            heading = "###" if sort == "document" else "##"
            block.extend([
                f"{heading} {note.title}", "",
                f"- 来源：{document_name}",
                f"- 类型：{'AI 划词解释' if note.source_type == 'ai_explanation' else '手动笔记'}",
                f"- 创建时间：{note.created_at.astimezone().strftime('%Y-%m-%d %H:%M')}",
            ])
            if note.document_version:
                block.append(f"- 文档版本：{note.document_version}")
            if note.source_anchor:
                location = (
                    f"第 {note.source_anchor.get('page')} 页"
                    if note.source_anchor.get("page") else
                    f"全文 {round(float(note.source_anchor.get('progression', 0)) * 100)}%"
                )
                block.append(f"- 原文定位：{location}（{note.source_anchor.get('protocol', '')}）")
            if note.model:
                try:
                    provider_label = get_provider(note.provider).name if note.provider else ""
                except ValueError:
                    provider_label = note.provider or ""
                model_label = " · ".join(part for part in [provider_label, note.model] if part)
                block.append(f"- 模型：{model_label}")
            if note.selected_text:
                block.extend(["", "**选中文字**", "", _markdown_text(note.selected_text, quote=True)])
            block.extend(["", "**笔记内容**", "", _markdown_text(note.content)])
            if note.remark:
                block.extend(["", "**我的备注**", "", _markdown_text(note.remark)])
            block.extend(["", "---", ""])
            output_bytes += sum(len(line.encode("utf-8")) + 1 for line in block)
            if output_bytes > max(1, settings.NOTE_EXPORT_MAX_BYTES):
                raise CustomException("导出内容超过大小上限，请先缩小筛选范围", status_code=413)
            lines.extend(block)
    return "\n".join(lines).rstrip() + "\n"

from datetime import datetime

from tortoise.expressions import Q
from tortoise.functions import Count

from app.common.exception_handler import CustomException
from app.dependencies import CurrentAccount, require_document_owner
from app.models import Document, Note
from app.schemas.note import NoteCreate, NotePublic, NoteUpdate
from app.services.ai_providers import get_provider
from app.config import settings


def serialize(note: Note) -> dict:
    return NotePublic.model_validate(note).model_dump()


def _query(
    account_id: int, keyword: str = "", document_id: int | None = None, unlinked: bool = False
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
        query = query.filter(document_id__isnull=True)
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
        document = await Document.get_or_none(id=payload.document_id)
        if document is None:
            raise CustomException("来源文档不存在", status_code=404)
        require_document_owner(current, document)
    note = await Note.create(
        account_id=current.id,
        document_id=document.id if document else None,
        document_name=document.name if document else None,
        source_type=payload.source_type,
        title=_default_title(payload, document.name if document else None),
        selected_text=payload.selected_text,
        content=payload.content,
        remark=payload.remark,
        provider=payload.provider,
        config_name=payload.config_name,
        model=payload.model,
    )
    return serialize(note)


async def select_page(
    account_id: int,
    keyword: str,
    document_id: int | None,
    unlinked: bool,
    sort: str,
    page_num: int,
    page_size: int,
) -> dict:
    query = _query(account_id, keyword, document_id, unlinked)
    notes = await _ordered(query, sort).offset((page_num - 1) * page_size).limit(page_size)
    return {"total": await query.count(), "list": [serialize(note) for note in notes]}


async def summary(account_id: int) -> dict:
    rows = await Note.filter(account_id=account_id).group_by(
        "document_id", "document_name"
    ).annotate(count=Count("id")).values("document_id", "document_name", "count")
    items = [{
        "document_id": row["document_id"],
        "document_name": (
            row["document_name"] or
            ("未关联或原文档已删除" if row["document_id"] is None else "未命名文档")
        ),
        "count": int(row["count"]),
    } for row in rows]
    items.sort(key=lambda item: (-item["count"], item["document_name"]))
    return {"total": sum(item["count"] for item in items), "documents": items}


async def get_owned(account_id: int, note_id: int) -> Note:
    note = await Note.get_or_none(id=note_id, account_id=account_id)
    if note is None:
        raise CustomException("笔记不存在", status_code=404)
    return note


async def update(account_id: int, note_id: int, payload: NoteUpdate) -> dict:
    note = await get_owned(account_id, note_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return serialize(note)
    for field, value in changes.items():
        setattr(note, field, value)
    await note.save(update_fields=[*changes.keys(), "updated_at"])
    return serialize(note)


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
    account_id: int, keyword: str, document_id: int | None, unlinked: bool, sort: str
) -> str:
    query = _ordered(_query(account_id, keyword, document_id, unlinked), sort)
    total = await query.count()
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

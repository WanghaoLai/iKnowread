from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response

from app.common.result import PageInfo, Result
from app.dependencies import CurrentAccount, get_current_account
from app.schemas.note import NoteCreate, NoteUpdate
from app.services import note_service

router = APIRouter(prefix="/notes")


@router.get("")
async def select_page(
    keyword: str = "",
    document_id: int | None = Query(default=None, alias="documentId", ge=1),
    unlinked: bool = False,
    sort: str = Query(default="newest", pattern="^(newest|oldest|document)$"),
    page_num: int = Query(default=1, alias="pageNum", ge=1),
    page_size: int = Query(default=12, alias="pageSize", ge=1, le=100),
    current: CurrentAccount = Depends(get_current_account),
):
    page = await note_service.select_page(
        current.id, keyword, document_id, unlinked, sort, page_num, page_size
    )
    return Result.success(PageInfo(**page))


@router.get("/summary")
async def summary(current: CurrentAccount = Depends(get_current_account)):
    return Result.success(await note_service.summary(current.id))


@router.get("/export")
async def export_notes(
    keyword: str = "",
    document_id: int | None = Query(default=None, alias="documentId", ge=1),
    unlinked: bool = False,
    sort: str = Query(default="newest", pattern="^(newest|oldest|document)$"),
    current: CurrentAccount = Depends(get_current_account),
):
    content = await note_service.export_markdown(current.id, keyword, document_id, unlinked, sort)
    filename = f"notes-{datetime.now().strftime('%Y%m%d-%H%M')}.md"
    return Response(
        content=("\ufeff" + content).encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename={filename}; filename*=UTF-8''{quote('我的笔记.md')}"
            )
        },
    )


@router.post("")
async def create_note(
    payload: NoteCreate,
    current: CurrentAccount = Depends(get_current_account),
):
    return Result.success(await note_service.create(current, payload))


@router.put("/{note_id}")
async def update_note(
    note_id: int,
    payload: NoteUpdate,
    current: CurrentAccount = Depends(get_current_account),
):
    return Result.success(await note_service.update(current.id, note_id, payload))


@router.delete("/{note_id}")
async def delete_note(
    note_id: int,
    current: CurrentAccount = Depends(get_current_account),
):
    await note_service.delete(current.id, note_id)
    return Result.success()

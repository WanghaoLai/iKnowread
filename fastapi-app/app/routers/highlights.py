from fastapi import APIRouter, Depends, Query

from app.api_paths import HIGHLIGHTS_ITEM_ROUTE, HIGHLIGHTS_PREFIX
from app.common.result import Result
from app.dependencies import CurrentAccount, get_current_account
from app.schemas.highlight import HighlightCreate, HighlightUpdate
from app.services import highlight_service
from app.services import experience_service

router = APIRouter(prefix=HIGHLIGHTS_PREFIX)


@router.get("")
async def list_highlights(
    document_id: int = Query(alias="documentId", ge=1),
    document_version: str = Query(
        alias="documentVersion", min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$"
    ),
    current: CurrentAccount = Depends(get_current_account),
):
    return Result.success(
        await highlight_service.list_current(current, document_id, document_version)
    )


@router.post("")
async def create_highlight(
    payload: HighlightCreate,
    current: CurrentAccount = Depends(get_current_account),
):
    return Result.success(await highlight_service.create(current, payload))


@router.put(HIGHLIGHTS_ITEM_ROUTE)
async def update_highlight(
    highlight_id: int,
    payload: HighlightUpdate,
    current: CurrentAccount = Depends(get_current_account),
):
    experience_service.deny_experience_write(current, "编辑高亮")
    return Result.success(
        await highlight_service.update(current.id, highlight_id, payload)
    )


@router.delete(HIGHLIGHTS_ITEM_ROUTE)
async def delete_highlight(
    highlight_id: int,
    current: CurrentAccount = Depends(get_current_account),
):
    experience_service.deny_experience_write(current, "删除高亮")
    await highlight_service.delete(current.id, highlight_id)
    return Result.success()

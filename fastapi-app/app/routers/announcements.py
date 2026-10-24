from fastapi import APIRouter, Depends, Query

from app.common.result import PageInfo, Result
from app.dependencies import CurrentAccount, get_current_account, require_admin
from app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementStatusUpdate,
    AnnouncementUpdate,
)
from app.services import announcement_service


router = APIRouter(prefix="/announcements")
admin_router = APIRouter(prefix="/admin/announcements")


@router.get("")
async def list_announcements(
    page_num: int = Query(1, alias="pageNum", ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=50),
    current: CurrentAccount = Depends(get_current_account),
):
    return Result.success(
        await announcement_service.user_list(current.id, page_num, page_size)
    )


@router.put("/read-all")
async def read_all(current: CurrentAccount = Depends(get_current_account)):
    return Result.success(await announcement_service.mark_all_read(current.id))


@router.put("/{announcement_id}/read")
async def read_announcement(
    announcement_id: int,
    current: CurrentAccount = Depends(get_current_account),
):
    return Result.success(
        await announcement_service.mark_read(current.id, announcement_id)
    )


@admin_router.get("")
async def admin_list_announcements(
    keyword: str = Query("", max_length=200),
    status: str | None = Query(None, pattern="^(draft|published|offline)$"),
    page_num: int = Query(1, alias="pageNum", ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=100),
    _current: CurrentAccount = Depends(require_admin),
):
    page = await announcement_service.admin_list(
        keyword.strip(), status, page_num, page_size
    )
    return Result.success(PageInfo(**page))


@admin_router.post("")
async def create_announcement(
    payload: AnnouncementCreate,
    current: CurrentAccount = Depends(require_admin),
):
    return Result.success(await announcement_service.create(current.id, payload))


@admin_router.put("/{announcement_id}")
async def update_announcement(
    announcement_id: int,
    payload: AnnouncementUpdate,
    _current: CurrentAccount = Depends(require_admin),
):
    return Result.success(await announcement_service.update(announcement_id, payload))


@admin_router.patch("/{announcement_id}/status")
async def update_announcement_status(
    announcement_id: int,
    payload: AnnouncementStatusUpdate,
    _current: CurrentAccount = Depends(require_admin),
):
    return Result.success(
        await announcement_service.update_status(announcement_id, payload)
    )


@admin_router.delete("/{announcement_id}")
async def delete_announcement(
    announcement_id: int,
    _current: CurrentAccount = Depends(require_admin),
):
    await announcement_service.delete(announcement_id)
    return Result.success()

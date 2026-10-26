from fastapi import APIRouter, Depends, Query

from app.api_paths import api_path
from app.common.result import PageInfo, Result
from app.dependencies import CurrentAccount, get_current_account, require_admin
from app.schemas.experience import ExperienceSettingsUpdate
from app.services import experience_service


router = APIRouter(tags=["在线体验"])


@router.get(api_path("experience.me"))
async def my_experience_policy(
    current: CurrentAccount = Depends(get_current_account),
):
    return Result.success(await experience_service.session_policy(current))


@router.get(api_path("experience.admin_settings"))
async def get_admin_settings(current: CurrentAccount = Depends(require_admin)):
    return Result.success(await experience_service.admin_settings(current.id))


@router.put(api_path("experience.update_admin_settings"))
async def update_admin_settings(
    payload: ExperienceSettingsUpdate,
    current: CurrentAccount = Depends(require_admin),
):
    return Result.success(await experience_service.update_settings(current.id, payload))


@router.get(api_path("experience.admin_documents"))
async def get_admin_documents(
    name: str = "",
    page_num: int = Query(1, alias="pageNum", ge=1),
    page_size: int = Query(50, alias="pageSize", ge=1, le=100),
    current: CurrentAccount = Depends(require_admin),
):
    page = await experience_service.eligible_documents(
        current.id, name, page_num, page_size
    )
    return Result.success(PageInfo(**page))

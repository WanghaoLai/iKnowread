from fastapi import APIRouter, Depends, HTTPException, Query

from app.common.result import PageInfo, Result
from app.dependencies import CurrentAccount, get_current_account, require_admin, require_self_or_admin
from app.schemas.account import AccountCreate, AccountPublic, AccountUpdate
from app.services import account_service

router = APIRouter(prefix="/accounts")


@router.post("")
async def add(payload: AccountCreate, _=Depends(require_admin)):
    account = await account_service.create(payload.model_dump())
    return Result.success(AccountPublic.model_validate(account))


@router.put("/{account_id}")
async def update(account_id: int, payload: AccountUpdate, current: CurrentAccount = Depends(get_current_account)):
    account = await account_service.get_by_id(account_id)
    require_self_or_admin(current, account_id)
    updated = await account_service.update(account_id, payload.model_dump(exclude_unset=True))
    return Result.success(AccountPublic.model_validate(updated))


@router.delete("/{account_id}")
async def delete(account_id: int, current: CurrentAccount = Depends(require_admin)):
    if current.id == account_id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    await account_service.delete(account_id)
    return Result.success()


@router.get("/{account_id}")
async def select_one(account_id: int, current: CurrentAccount = Depends(get_current_account)):
    account = await account_service.get_by_id(account_id)
    require_self_or_admin(current, account_id)
    return Result.success(AccountPublic.model_validate(account))


@router.get("")
async def select_page(
    role: str,
    name: str = "",
    page_num: int = Query(1, alias="pageNum", ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=100),
    _=Depends(require_admin),
):
    page = await account_service.select_page(role, name, page_num, page_size)
    return Result.success(PageInfo(**page))

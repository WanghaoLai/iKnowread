from fastapi import APIRouter, Depends, Query, Request

from app.api_paths import (
    WEB_IMPORTS_PREFIX,
    WEB_IMPORT_CANCEL_ROUTE,
    WEB_IMPORT_ITEM_ROUTE,
    WEB_IMPORT_RETRY_ROUTE,
)
from app.common.result import Result
from app.dependencies import CurrentAccount, get_current_account
from app.schemas.web_import import WebImportCreate
from app.services import web_import_service


router = APIRouter(prefix=WEB_IMPORTS_PREFIX)


@router.post("")
async def create_web_import(
    body: WebImportCreate,
    request: Request,
    current: CurrentAccount = Depends(get_current_account),
):
    await web_import_service.limit(request, current.id)
    return Result.success(await web_import_service.create(current.id, body.url))


@router.get("")
async def list_web_imports(limit: int = Query(20, ge=1, le=100), current: CurrentAccount = Depends(get_current_account)):
    return Result.success(await web_import_service.list_for_account(current.id, limit))


@router.get(WEB_IMPORT_ITEM_ROUTE)
async def get_web_import(job_id: int, current: CurrentAccount = Depends(get_current_account)):
    job = await web_import_service.get_for_account(job_id, current.id)
    return Result.success(web_import_service.serialize(job))


@router.post(WEB_IMPORT_RETRY_ROUTE)
async def retry_web_import(
    job_id: int,
    request: Request,
    current: CurrentAccount = Depends(get_current_account),
):
    await web_import_service.limit(request, current.id)
    return Result.success(await web_import_service.retry(job_id, current.id))


@router.post(WEB_IMPORT_CANCEL_ROUTE)
async def cancel_web_import(
    job_id: int,
    current: CurrentAccount = Depends(get_current_account),
):
    return Result.success(await web_import_service.cancel(job_id, current.id))


@router.delete(WEB_IMPORT_ITEM_ROUTE)
async def delete_web_import(
    job_id: int,
    current: CurrentAccount = Depends(get_current_account),
):
    await web_import_service.delete(job_id, current.id)
    return Result.success()

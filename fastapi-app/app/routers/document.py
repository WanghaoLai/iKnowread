from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.api_paths import (
    DOCUMENTS_PREFIX,
    DOCUMENT_DOWNLOAD_ROUTE,
    DOCUMENT_ITEM_ROUTE,
    DOCUMENT_LIST_ROUTE,
    DOCUMENT_OCR_ROUTE,
    DOCUMENT_OCR_STATUS_ROUTE,
    DOCUMENT_PROCESSING_STATUS_ROUTE,
    DOCUMENT_PREVIEW_ROUTE,
    DOCUMENT_PURGE_ROUTE,
    DOCUMENT_RECYCLE_ROUTE,
    DOCUMENT_RESTORE_ROUTE,
    DOCUMENT_UPLOAD_ROUTE,
)
from app.common.exception_handler import CustomException
from app.common.result import Result, PageInfo
from app.dependencies import CurrentAccount, get_current_account, require_document_owner
from app.services import document_service
from app.services import ocr_service
from app.services import processing_task_service
from app.services import experience_service
from app.storage import get_storage, run_storage_io

router = APIRouter(prefix=DOCUMENTS_PREFIX)


def _require_content_version(doc, version: str | None) -> None:
    if version is not None and version != doc.content_version:
        raise CustomException("文档内容已更新，请刷新后重新打开", status_code=409)


# 上传文档（保存到当前账号专属目录）
# 注意：静态段路由必须声明在 /{doc_id} 之前，否则会被动态段抢先匹配。
@router.post(DOCUMENT_UPLOAD_ROUTE)
async def upload(
    file: UploadFile = File(...),
    current: CurrentAccount = Depends(get_current_account),
):
    experience_service.deny_experience_write(current, "上传文档")
    doc = await document_service.upload(current.id, current.role, file)
    if doc["ext"] == "pdf":
        await ocr_service.enqueue(doc["id"])
    return Result.success(doc)


# 分页查询当前账号的文档列表
@router.get(DOCUMENT_LIST_ROUTE)
async def select_page(
    name: str = "",
    page_num: int = Query(1, alias="pageNum", ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=100),
    current: CurrentAccount = Depends(get_current_account),
):
    page = await document_service.select_page(current, name, page_num, page_size)
    return Result.success(PageInfo(**page))


# 回收站：分页查询当前账号已删除的文档
@router.get(DOCUMENT_RECYCLE_ROUTE)
async def recycle_select_page(
    name: str = "",
    page_num: int = Query(1, alias="pageNum", ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=100),
    current: CurrentAccount = Depends(get_current_account),
):
    experience_service.deny_experience_write(current, "使用回收站")
    page = await document_service.recycle_page(current.id, name, page_num, page_size)
    return Result.success(PageInfo(**page))


# 从回收站恢复文档（高亮、笔记关联、阅读进度一并复原）
@router.post(DOCUMENT_RESTORE_ROUTE)
async def restore(doc_id: int, current: CurrentAccount = Depends(get_current_account)):
    experience_service.deny_experience_write(current, "恢复文档")
    doc = await document_service.get_by_id(doc_id, include_deleted=True)
    require_document_owner(current, doc)
    restored = await document_service.restore(doc_id)
    if restored["ext"] == "pdf" and restored["ocr_status"] == "pending":
        await ocr_service.enqueue(doc_id)
    return Result.success(restored)


# 彻底删除回收站中的文档及其文件
@router.delete(DOCUMENT_PURGE_ROUTE)
async def purge(doc_id: int, current: CurrentAccount = Depends(get_current_account)):
    experience_service.deny_experience_write(current, "彻底删除文档")
    doc = await document_service.get_by_id(doc_id, include_deleted=True)
    require_document_owner(current, doc)
    await document_service.delete(doc_id)
    return Result.success()


# 按记录下载（还原原始文件名）
@router.get(DOCUMENT_DOWNLOAD_ROUTE)
async def download(
    doc_id: int,
    version: str | None = Query(default=None, min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$"),
    current: CurrentAccount = Depends(get_current_account),
):
    doc = await document_service.get_by_id(doc_id)
    await experience_service.require_document_read(current, doc)
    _require_content_version(doc, version)
    storage = get_storage()
    return await run_storage_io(
        storage.response, document_service.storage_key(doc), filename=doc.name,
        media_type="text/markdown; charset=utf-8" if doc.ext == "md" else "application/octet-stream",
    )


# 在线预览只负责 PDF；DOCX 和 Markdown 由前端使用受保护下载接口渲染。
@router.get(DOCUMENT_PREVIEW_ROUTE)
async def preview(
    doc_id: int,
    version: str | None = Query(default=None, min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$"),
    current: CurrentAccount = Depends(get_current_account),
):
    doc = await document_service.get_by_id(doc_id)
    await experience_service.require_document_read(current, doc)
    _require_content_version(doc, version)
    if doc.ext != "pdf":
        from fastapi import HTTPException
        raise HTTPException(status_code=415, detail="该格式不支持 PDF 预览")
    storage = get_storage()
    preview_key = await ocr_service.preview_storage_key(doc)
    return await run_storage_io(
        storage.response, preview_key, media_type="application/pdf", inline=True,
    )


@router.get(DOCUMENT_OCR_STATUS_ROUTE)
async def ocr_status(doc_id: int, current: CurrentAccount = Depends(get_current_account)):
    doc = await document_service.get_by_id(doc_id)
    await experience_service.require_document_read(current, doc)
    return Result.success(document_service.serialize(doc))


@router.get(DOCUMENT_PROCESSING_STATUS_ROUTE)
async def processing_status(
    doc_id: int, current: CurrentAccount = Depends(get_current_account)
):
    doc = await document_service.get_by_id(doc_id)
    await experience_service.require_document_read(current, doc)
    return Result.success({
        "document_id": doc.id,
        "document_version": doc.content_version,
        "stages": await processing_task_service.stages_for_document(doc),
    })


@router.post(DOCUMENT_OCR_ROUTE)
async def retry_ocr(doc_id: int, current: CurrentAccount = Depends(get_current_account)):
    experience_service.deny_experience_write(current, "重新执行 OCR")
    doc = await document_service.get_by_id(doc_id)
    require_document_owner(current, doc)
    await ocr_service.retry(doc)
    refreshed = await document_service.get_by_id(doc_id)
    return Result.success(document_service.serialize(refreshed))


# 删除文档：移入回收站，可在回收站中恢复或彻底删除。
@router.delete(DOCUMENT_ITEM_ROUTE)
async def delete(doc_id: int, current: CurrentAccount = Depends(get_current_account)):
    experience_service.deny_experience_write(current, "删除文档")
    doc = await document_service.get_by_id(doc_id)
    require_document_owner(current, doc)
    await document_service.soft_delete(doc_id)
    return Result.success()

from fastapi import APIRouter, Depends, File, Query, UploadFile
from app.common.result import Result, PageInfo
from app.dependencies import CurrentAccount, get_current_account, require_document_owner
from app.services import document_service
from app.services import ocr_service
from app.storage import get_storage

router = APIRouter(prefix="/document")


# 上传文档（保存到当前账号专属目录）
@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    current: CurrentAccount = Depends(get_current_account),
):
    doc = await document_service.upload(current.id, current.role, file)
    if doc["ext"] == "pdf":
        await ocr_service.enqueue(doc["id"])
    return Result.success(doc)


# 分页查询当前账号的文档列表
@router.get("/selectPage")
async def select_page(
    name: str = "",
    page_num: int = Query(1, alias="pageNum", ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=100),
    current: CurrentAccount = Depends(get_current_account),
):
    page = await document_service.select_page(current.id, name, page_num, page_size)
    return Result.success(PageInfo(**page))


# 按记录下载（还原原始文件名）
@router.get("/download/{doc_id}")
async def download(doc_id: int, current: CurrentAccount = Depends(get_current_account)):
    doc = await document_service.get_by_id(doc_id)
    require_document_owner(current, doc)
    return get_storage().response(
        document_service.storage_key(doc), filename=doc.name,
        media_type="application/octet-stream",
    )


# 在线预览只负责 PDF；DOCX 由前端使用受保护下载接口渲染。
@router.get("/preview/{doc_id}")
async def preview(doc_id: int, current: CurrentAccount = Depends(get_current_account)):
    doc = await document_service.get_by_id(doc_id)
    require_document_owner(current, doc)
    if doc.ext != "pdf":
        from fastapi import HTTPException
        raise HTTPException(status_code=415, detail="该格式不支持 PDF 预览")
    return get_storage().response(
        ocr_service.preview_storage_key(doc), media_type="application/pdf", inline=True,
    )


@router.get("/{doc_id}/ocr-status")
async def ocr_status(doc_id: int, current: CurrentAccount = Depends(get_current_account)):
    doc = await document_service.get_by_id(doc_id)
    require_document_owner(current, doc)
    return Result.success(document_service.serialize(doc))


@router.post("/{doc_id}/ocr")
async def retry_ocr(doc_id: int, current: CurrentAccount = Depends(get_current_account)):
    doc = await document_service.get_by_id(doc_id)
    require_document_owner(current, doc)
    await ocr_service.retry(doc)
    refreshed = await document_service.get_by_id(doc_id)
    return Result.success(document_service.serialize(refreshed))


# 删除数据库记录和原文件。
@router.delete("/delete/{doc_id}")
async def delete(doc_id: int, current: CurrentAccount = Depends(get_current_account)):
    doc = await document_service.get_by_id(doc_id)
    require_document_owner(current, doc)
    await document_service.delete(doc_id)
    return Result.success()

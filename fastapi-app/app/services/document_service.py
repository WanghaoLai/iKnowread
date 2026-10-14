from fastapi import UploadFile

from app.common.exception_handler import CustomException
from app.models import Account, Document
from app.schemas.document import DocumentPublic
from app.services.account_service import RELATIVE_PREFIX, normalize_role
from app.services.file_validation import validate_document
from app.services.resource_limits import account_lock, ensure_additional_storage, ensure_document_capacity
from app.config import settings
from app.storage import get_storage
from tortoise.transactions import in_transaction

ALLOWED_EXTS = {"pdf", "docx"}
MAX_SIZE = 50 * 1024 * 1024


def serialize(doc: Document) -> dict:
    return DocumentPublic.model_validate(doc).model_dump()


async def get_by_id(doc_id: int) -> Document:
    doc = await Document.get_or_none(id=doc_id)
    if doc is None:
        raise CustomException("文件不存在", status_code=404)
    return doc


def storage_key(doc: Document) -> str:
    if doc.path and doc.path.startswith(RELATIVE_PREFIX):
        return doc.path[len(RELATIVE_PREFIX):]
    raise CustomException("文件路径无效")


def ocr_storage_key(doc: Document) -> str | None:
    if doc.ocr_path and doc.ocr_path.startswith(RELATIVE_PREFIX):
        return doc.ocr_path[len(RELATIVE_PREFIX):]
    return None


async def upload(account_id: int, role: str, file: UploadFile) -> dict:
    normalized = normalize_role(role)
    if not normalized or not await Account.filter(id=account_id, role=normalized).exists():
        raise CustomException("账号不存在", status_code=404)
    name = file.filename or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXTS:
        raise CustomException("不支持的文件格式，仅支持 PDF / DOCX")
    if file.size and file.size > MAX_SIZE:
        raise CustomException("文件大小不能超过 50MB", status_code=413)
    await validate_document(file, ext)
    storage = get_storage()
    async with account_lock(account_id):
        await ensure_document_capacity(account_id, int(file.size or 0))
        key = await storage.save(name, file.file, subdir=f"{normalized}/{account_id}/documents")
        size = storage.size(key)
        if size > MAX_SIZE:
            storage.delete(key)
            raise CustomException("文件大小不能超过 50MB", status_code=413)
        try:
            # The saved file is now part of on-disk usage; re-check with zero
            # additional bytes to handle clients that omitted Content-Length.
            await ensure_additional_storage(account_id, 0)
            ocr_status = "pending" if ext == "pdf" and settings.OCR_ENABLED else "not_applicable"
            ocr_error = None
            if ext == "pdf" and not settings.OCR_ENABLED:
                ocr_status = "failed"
                ocr_error = "OCR 服务未启用"
            doc = await Document.create(
                name=name[:255], ext=ext, size=size,
                path=f"{RELATIVE_PREFIX}{key}", account_id=account_id,
                ocr_status=ocr_status,
                ocr_error=ocr_error,
            )
        except Exception:
            storage.delete(key)
            raise
    return serialize(doc)


async def select_page(account_id: int, name: str = "", page_num: int = 1, page_size: int = 10) -> dict:
    query = Document.filter(account_id=account_id, name__contains=name)
    docs = await query.offset((page_num - 1) * page_size).limit(page_size)
    return {"total": await query.count(), "list": [serialize(doc) for doc in docs]}


async def delete(doc_id: int) -> None:
    doc = await get_by_id(doc_id)
    async with account_lock(doc.account_id):
        doc = await get_by_id(doc_id)
        keys = [storage_key(doc)]
        if derived := ocr_storage_key(doc):
            keys.append(derived)
        storage = get_storage()
        staged = [(key, storage.stage(key)) for key in keys]
        try:
            async with in_transaction() as connection:
                await Document.filter(id=doc_id).using_db(connection).delete()
        except Exception:
            for key, staged_key in reversed(staged):
                if staged_key:
                    storage.restore(staged_key, key)
            raise
        for _, staged_key in staged:
            if staged_key:
                storage.delete(staged_key)

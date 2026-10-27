from datetime import datetime, timezone
import logging

from fastapi import UploadFile

from app.common.exception_handler import CustomException
from app.models import Account, Document
from app.schemas.document import DocumentPublic
from app.services.account_service import RELATIVE_PREFIX, normalize_role
from app.services.file_validation import validate_document
from app.services.resource_limits import account_lock, ensure_additional_storage, ensure_document_capacity
from app.services import processing_task_service
from app.storage import complete_on_cancellation, get_storage, run_storage_io
from tortoise.transactions import in_transaction

ALLOWED_EXTS = {"pdf", "docx", "md"}
MAX_SIZE = 50 * 1024 * 1024
logger = logging.getLogger(__name__)


def _all_files_exist(storage, keys: list[str]) -> bool:
    return all(storage.exists(key) for key in keys)


def _stage_files(storage, keys: list[str]) -> list[tuple[str, str | None]]:
    staged: list[tuple[str, str | None]] = []
    try:
        for key in keys:
            staged.append((key, storage.stage(key)))
    except Exception:
        for key, staged_key in reversed(staged):
            if staged_key:
                storage.restore(staged_key, key)
        raise
    return staged


def _restore_staged_files(storage, staged: list[tuple[str, str | None]]) -> None:
    for key, staged_key in reversed(staged):
        if staged_key:
            storage.restore(staged_key, key)


def _purge_staged_files(storage, staged: list[tuple[str, str | None]]) -> None:
    for _, staged_key in staged:
        if not staged_key:
            continue
        try:
            storage.delete(staged_key)
        except Exception:
            # 数据库删除已提交；暂存文件会由存储对账任务清理。
            logger.exception("Failed to remove staged document file")


def serialize(doc: Document) -> dict:
    return DocumentPublic.model_validate(doc).model_dump()


async def get_by_id(doc_id: int, *, include_deleted: bool = False) -> Document:
    doc = await Document.get_or_none(
        id=doc_id, **({} if include_deleted else {"deleted_at__isnull": True})
    )
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
        raise CustomException("不支持的文件格式，仅支持 PDF / DOCX / Markdown")
    if file.size and file.size > MAX_SIZE:
        raise CustomException("文件大小不能超过 50MB", status_code=413)
    await validate_document(file, ext)
    storage = get_storage()
    async with account_lock(account_id):
        await ensure_document_capacity(account_id, int(file.size or 0))
        key = await storage.save(name, file.file, subdir=f"{normalized}/{account_id}/documents")
        size = await run_storage_io(storage.size, key)
        if size > MAX_SIZE:
            await run_storage_io(storage.delete, key)
            raise CustomException("文件大小不能超过 50MB", status_code=413)
        try:
            # The saved file is now part of on-disk usage; re-check with zero
            # additional bytes to handle clients that omitted Content-Length.
            await ensure_additional_storage(account_id, 0)
            ocr_status = "not_applicable"
            ocr_error = None
            if ext == "pdf":
                # A PDF may only enter the polling state when a live queue can
                # actually accept it. Configuration alone is insufficient: an
                # unavailable OCR executable would otherwise leave it pending forever.
                from app.services import ocr_service
                ocr_error = ocr_service.availability_error()
                ocr_status = "failed" if ocr_error else "pending"
            doc = await Document.create(
                name=name[:255], ext=ext, size=size,
                path=f"{RELATIVE_PREFIX}{key}", account_id=account_id,
                ocr_status=ocr_status,
                ocr_error=ocr_error,
            )
            try:
                await processing_task_service.initialize_document(doc)
            except Exception:
                # A new upload has no dependent user data yet. Remove the new
                # row so task initialization and file publication are atomic to
                # the caller; cascading cleanup removes any partial stage rows.
                await doc.delete()
                raise
        except Exception:
            await run_storage_io(storage.delete, key)
            raise
    return serialize(doc)


async def select_page(current, name: str = "", page_num: int = 1, page_size: int = 10) -> dict:
    if isinstance(current, int):
        query = Document.filter(
            account_id=current, deleted_at__isnull=True, name__contains=name
        )
        read_only = False
    elif current.is_experience:
        from app.services import experience_service
        query = await experience_service.shared_documents_query(current, name)
        read_only = True
    else:
        query = Document.filter(
            account_id=current.id, deleted_at__isnull=True, name__contains=name
        )
        read_only = False
    query = query.order_by("-created_at", "-id")
    docs = await query.offset((page_num - 1) * page_size).limit(page_size)
    stages = await processing_task_service.stages_for_documents(docs)
    items = []
    for doc in docs:
        item = serialize(doc)
        item["read_only"] = read_only
        item["processing_stages"] = stages[doc.id]
        items.append(item)
    return {"total": await query.count(), "list": items}


async def recycle_page(account_id: int, name: str = "", page_num: int = 1, page_size: int = 10) -> dict:
    query = Document.filter(
        account_id=account_id, deleted_at__isnull=False, name__contains=name
    ).order_by("-deleted_at", "-id")
    docs = await query.offset((page_num - 1) * page_size).limit(page_size)
    return {"total": await query.count(), "list": [serialize(doc) for doc in docs]}


async def soft_delete(doc_id: int) -> None:
    """移入回收站：只标记 deleted_at，文件、高亮、笔记关联全部原样保留。"""
    doc = await get_by_id(doc_id)
    async with account_lock(doc.account_id):
        updated = await Document.filter(id=doc_id, deleted_at__isnull=True).update(
            deleted_at=datetime.now(timezone.utc)
        )
        if not updated:
            raise CustomException("文件不存在", status_code=404)


async def restore(doc_id: int) -> dict:
    """从回收站恢复：清空 deleted_at，文档及其高亮、笔记关联、阅读进度全部复原。"""
    doc = await get_by_id(doc_id, include_deleted=True)
    if doc.deleted_at is None:
        raise CustomException("该文档不在回收站中", status_code=409)
    async with account_lock(doc.account_id):
        # 只恢复可完整读取的快照。尤其是扫描 PDF，丢失 OCR 产物后即使原文件
        # 尚在，高亮锚点也可能无法重新解析，不能把损坏记录放回文档列表。
        storage = get_storage()
        required_keys = [storage_key(doc)]
        if derived := ocr_storage_key(doc):
            required_keys.append(derived)
        unique_keys = list(dict.fromkeys(required_keys))
        if not await run_storage_io(_all_files_exist, storage, unique_keys):
            raise CustomException("文档文件不完整，无法恢复，请联系管理员", status_code=409)
        await ensure_document_capacity(
            doc.account_id, 0, adds_new_document=False
        )
        updated = await Document.filter(id=doc_id, deleted_at__isnull=False).update(
            deleted_at=None
        )
        if not updated:
            raise CustomException("该文档不在回收站中", status_code=409)
    return serialize(await get_by_id(doc_id))


async def _delete_consistently(doc_id: int) -> None:
    """彻底删除数据库记录和原文件（回收站中的最终删除）。"""
    doc = await get_by_id(doc_id, include_deleted=True)
    if doc.deleted_at is None:
        raise CustomException("请先将文档移入回收站，再彻底删除", status_code=409)
    async with account_lock(doc.account_id):
        doc = await get_by_id(doc_id, include_deleted=True)
        if doc.deleted_at is None:
            raise CustomException("请先将文档移入回收站，再彻底删除", status_code=409)
        keys = [storage_key(doc)]
        if derived := ocr_storage_key(doc):
            keys.append(derived)
        storage = get_storage()
        staged = await run_storage_io(_stage_files, storage, list(dict.fromkeys(keys)))
        try:
            async with in_transaction() as connection:
                await Document.filter(id=doc_id).using_db(connection).delete()
        except BaseException:
            await run_storage_io(_restore_staged_files, storage, staged)
            raise
        await run_storage_io(_purge_staged_files, storage, staged)


async def delete(doc_id: int) -> None:
    """彻底删除并保证请求取消不会中断文件/数据库一致性协议。"""
    await complete_on_cancellation(_delete_consistently(doc_id))

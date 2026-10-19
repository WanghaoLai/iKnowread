from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import sys
import tempfile
from datetime import datetime, timezone
from importlib.util import find_spec
from pathlib import Path

from app.common.exception_handler import CustomException
from app.config import settings
from app.models import Document
from app.services.account_service import RELATIVE_PREFIX
from app.storage import get_storage, run_storage_io
from app.services.resource_limits import account_lock, ensure_additional_storage
from app.services import processing_task_service

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[int] | None = None
_workers: list[asyncio.Task] = []
_queued_ids: set[int] = set()
_availability_error: str | None = "OCR 服务尚未启动"


async def _record_status(
    document_id: int, status: str, error: str | None = None
) -> None:
    """Mirror OCR into the unified task table without risking OCR delivery."""
    try:
        await processing_task_service.set_status(
            document_id, processing_task_service.OCR, status, error=error
        )
    except Exception:
        # The legacy document fields remain authoritative and are overlaid by
        # the unified read model, so a mirror failure cannot hide real progress.
        logger.exception("Failed to persist unified OCR status document=%s", document_id)


def availability_error() -> str | None:
    """Return ``None`` only while the in-process OCR queue can accept work."""
    if not settings.OCR_ENABLED:
        return "OCR 服务未启用"
    return _availability_error


def is_available() -> bool:
    return availability_error() is None and _queue is not None and bool(_workers)


def derived_storage_key(doc: Document) -> str | None:
    path = doc.ocr_path
    if path and path.startswith(RELATIVE_PREFIX):
        return path[len(RELATIVE_PREFIX):]
    return None


async def preview_storage_key(doc: Document) -> str:
    storage = get_storage()
    derived = derived_storage_key(doc)
    # 重新处理期间继续提供上一份成功产物。新产物只有在数据库中的路径、
    # 状态和派生更新时间原子切换后才会对用户可见。
    if derived and await run_storage_io(storage.exists, derived):
        return derived
    from app.services.document_service import storage_key
    return storage_key(doc)


def _existing_size(storage, key: str | None) -> int:
    if not key or not storage.exists(key):
        return 0
    return storage.size(key)


def _command_prefix() -> list[str] | None:
    command = settings.OCR_COMMAND.strip()
    if not command:
        return None
    if Path(command).is_absolute():
        return [command] if Path(command).is_file() else None
    if executable := shutil.which(command):
        return [executable]
    # pip --user 的脚本目录不一定在 PATH；模块入口仍由当前 Python 可靠启动。
    if command == "ocrmypdf" and find_spec("ocrmypdf") is not None:
        return [sys.executable, "-m", "ocrmypdf"]
    return None


def _safe_error(stderr: str) -> str:
    lowered = stderr.lower()
    if "language" in lowered and any(
        marker in lowered for marker in ("not found", "failed loading", "does not have", "language data")
    ):
        return f"OCR 缺少语言包：{settings.OCR_LANGUAGES}，请安装后重试"
    if "encrypted" in lowered or "password" in lowered:
        return "PDF 已加密，无法执行 OCR"
    if "image too large" in lowered or "decompression bomb" in lowered:
        return "PDF 页面图像过大，已停止 OCR"
    return "OCR 处理失败，请稍后重试或联系管理员"


async def _mark_unavailable(message: str) -> None:
    query = Document.filter(ext="pdf", ocr_status__in=["pending", "processing"])
    document_ids = await query.values_list("id", flat=True)
    await query.update(
        ocr_status="failed",
        ocr_error=message,
        ocr_updated_at=datetime.now(timezone.utc),
    )
    for document_id in document_ids:
        await _record_status(int(document_id), "failed", message)


async def start() -> None:
    global _queue, _availability_error
    if _workers:
        return
    _availability_error = "OCR 服务尚未启动"
    if not settings.OCR_ENABLED:
        _availability_error = "OCR 服务未启用"
        await _mark_unavailable(_availability_error)
        return
    if not _command_prefix():
        _availability_error = "OCR 服务不可用，请安装 OCRmyPDF 后重试"
        await _mark_unavailable(_availability_error)
        return

    # 环境依赖后来补齐时自动恢复，不要求用户逐份点击重试。
    recoverable_errors = (
        "OCR 服务未启用",
        "OCR 服务不可用，请安装 OCRmyPDF 后重试",
    )
    await Document.filter(ext="pdf", ocr_status="failed", ocr_error__in=recoverable_errors).update(
        ocr_status="pending",
        ocr_error=None,
        ocr_updated_at=datetime.now(timezone.utc),
    )
    await Document.filter(
        ext="pdf", ocr_status="failed", ocr_error__startswith="OCR 缺少语言包"
    ).update(
        ocr_status="pending",
        ocr_error=None,
        ocr_updated_at=datetime.now(timezone.utc),
    )

    # 进程异常退出时 processing 不应永久挂起，启动后统一恢复为待处理。
    await Document.filter(ext="pdf", ocr_status="processing").update(
        ocr_status="pending",
        ocr_error=None,
        ocr_updated_at=datetime.now(timezone.utc),
    )
    storage = get_storage()
    for doc in await Document.filter(ext="pdf", ocr_status="ready", deleted_at__isnull=True):
        key = derived_storage_key(doc)
        if not key or not await run_storage_io(storage.exists, key):
            await Document.filter(id=doc.id).update(
                ocr_status="pending",
                ocr_path=None,
                ocr_error="OCR 派生文件缺失，已自动重新处理",
                ocr_updated_at=datetime.now(timezone.utc),
            )
    _queue = asyncio.Queue()
    worker_count = max(1, min(settings.OCR_WORKERS, 4))
    for index in range(worker_count):
        _workers.append(asyncio.create_task(_worker(), name=f"pdf-ocr-{index + 1}"))
    _availability_error = None
    logger.info("PDF OCR queue started with %s worker(s)", worker_count)
    # 回收站中的文档不参与 OCR，避免恢复前内容版本被刷新。
    for doc_id in await Document.filter(
        ext="pdf", ocr_status="pending", deleted_at__isnull=True
    ).values_list("id", flat=True):
        await enqueue(int(doc_id))


async def stop() -> None:
    global _queue, _availability_error
    tasks = list(_workers)
    _workers.clear()
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _queued_ids.clear()
    _queue = None
    _availability_error = "OCR 服务尚未启动" if settings.OCR_ENABLED else "OCR 服务未启用"


async def enqueue(doc_id: int) -> None:
    if not is_available() or doc_id in _queued_ids:
        return
    _queued_ids.add(doc_id)
    await _queue.put(doc_id)
    logger.info("OCR job queued document=%s queue_depth=%s", doc_id, _queue.qsize())


async def retry(doc: Document) -> None:
    if doc.ext != "pdf":
        raise CustomException("仅 PDF 支持 OCR")
    if error := availability_error():
        raise CustomException(error)
    if doc.ocr_status in ("pending", "processing"):
        return
    await Document.filter(id=doc.id).update(
        ocr_status="pending",
        ocr_error=None,
        ocr_updated_at=datetime.now(timezone.utc),
    )
    await _record_status(doc.id, "pending")
    await enqueue(doc.id)


async def _worker() -> None:
    assert _queue is not None
    while True:
        doc_id = await _queue.get()
        logger.info("OCR job started document=%s queue_depth=%s", doc_id, _queue.qsize())
        try:
            await process_document(doc_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unexpected OCR worker failure for document %s", doc_id)
        finally:
            _queued_ids.discard(doc_id)
            _queue.task_done()
            # 文档可能在 OCR 期间经历“删除→恢复”。恢复请求发生在任务释放
            # 去重标记前时 enqueue 会被去重；此处补偿，避免文档永久停在 pending。
            try:
                if await Document.filter(
                    id=doc_id, ocr_status="pending", deleted_at__isnull=True
                ).exists():
                    await enqueue(doc_id)
            except Exception:
                logger.exception("Failed to requeue restored OCR document %s", doc_id)
            logger.info("OCR job finished document=%s queue_depth=%s", doc_id, _queue.qsize())


def _copy_source_to(source_key: str, destination: Path) -> None:
    storage = get_storage()
    with storage.open(source_key) as source, destination.open("wb") as output:
        shutil.copyfileobj(source, output, length=1024 * 1024)


def _kill_process_group(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()


async def _run_command(source: Path, output: Path) -> tuple[int, str]:
    command = _command_prefix()
    if not command:
        return 127, "ocrmypdf not found"
    args = [
        *command,
        "--mode", "skip",
        "--language", settings.OCR_LANGUAGES,
        "--rotate-pages",
        "--deskew",
        "--output-type", "pdf",
        "--optimize", "0",
        "--jobs", str(max(1, min(settings.OCR_JOBS_PER_DOCUMENT, 4))),
        "--tesseract-timeout", str(max(1, settings.OCR_PAGE_TIMEOUT_SECONDS)),
        "--max-image-mpixels", str(max(1.0, settings.OCR_MAX_IMAGE_MPIXELS)),
        str(source),
        str(output),
    ]
    # OCR 进程不需要数据库或大模型密钥；只传递运行所需环境，缩小恶意 PDF 的可见范围。
    child_env = {
        key: value
        for key in ("PATH", "LANG", "LC_ALL", "TESSDATA_PREFIX", "HOME")
        if (value := os.environ.get(key))
    }
    child_env["TMPDIR"] = str(source.parent)
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
        env=child_env,
    )
    try:
        _, stderr = await asyncio.wait_for(
            process.communicate(), timeout=max(30, settings.OCR_TIMEOUT_SECONDS)
        )
    except (asyncio.TimeoutError, asyncio.CancelledError):
        _kill_process_group(process)
        await process.wait()
        raise
    return process.returncode or 0, stderr.decode("utf-8", errors="replace")[-12000:]


async def process_document(doc_id: int) -> None:
    claimed = await Document.filter(
        id=doc_id, ext="pdf", ocr_status="pending", deleted_at__isnull=True
    ).update(
        ocr_status="processing",
        ocr_error=None,
        ocr_updated_at=datetime.now(timezone.utc),
    )
    if not claimed:
        return
    await _record_status(doc_id, "processing")

    doc = await Document.get_or_none(id=doc_id).prefetch_related("account")
    if doc is None:
        return
    from app.services.document_service import storage_key

    try:
        with tempfile.TemporaryDirectory(prefix="iknowread-ocr-") as directory:
            source = Path(directory) / "source.pdf"
            output = Path(directory) / "searchable.pdf"
            await asyncio.to_thread(_copy_source_to, storage_key(doc), source)
            try:
                return_code, stderr = await _run_command(source, output)
            except asyncio.TimeoutError:
                raise RuntimeError("OCR timeout")
            if return_code != 0 or not output.is_file() or output.stat().st_size == 0:
                safe_error = _safe_error(stderr)
                logger.warning(
                    "OCRmyPDF failed document=%s return_code=%s category=%s",
                    doc_id,
                    return_code,
                    safe_error,
                )
                raise RuntimeError(safe_error)

            async with account_lock(doc.account_id):
                # 删除和 OCR 最终发布共用账号锁。若文档已进入回收站，保留删除
                # 时的内容版本，不生成新产物，恢复后再从 pending 继续。
                current = await Document.get_or_none(
                    id=doc_id,
                    ocr_status="processing",
                    deleted_at__isnull=True,
                )
                if current is None:
                    await Document.filter(
                        id=doc_id,
                        ocr_status="processing",
                        deleted_at__isnull=False,
                    ).update(
                        ocr_status="pending",
                        ocr_error=None,
                        ocr_updated_at=datetime.now(timezone.utc),
                    )
                    await _record_status(doc_id, "pending")
                    return
                old_key = derived_storage_key(current)
                storage = get_storage()
                old_size = await run_storage_io(_existing_size, storage, old_key)
                try:
                    # The old derivative remains readable until the database swap,
                    # but it is reclaimed immediately afterwards. Credit it for the
                    # per-account quota while retaining the full host free-space check.
                    await ensure_additional_storage(
                        doc.account_id,
                        output.stat().st_size,
                        reclaimable_size=old_size,
                    )
                except CustomException as exc:
                    raise RuntimeError("OCR 派生文件超过账号或服务器存储限额") from exc
                with output.open("rb") as result:
                    new_key = await storage.save(
                        f"document_{doc_id}_searchable.pdf",
                        result,
                        subdir=f"{doc.account.role}/{doc.account_id}/ocr",
                    )
                updated = await Document.filter(
                    id=doc_id,
                    ocr_status="processing",
                    deleted_at__isnull=True,
                ).update(
                    ocr_status="ready",
                    ocr_path=RELATIVE_PREFIX + new_key,
                    ocr_error=None,
                    ocr_updated_at=datetime.now(timezone.utc),
                )
                if not updated:
                    await run_storage_io(storage.delete, new_key)
                    return
                await _record_status(doc_id, "ready")
                if old_key and old_key != new_key:
                    await run_storage_io(storage.delete, old_key)
    except asyncio.CancelledError:
        await Document.filter(id=doc_id, ocr_status="processing").update(
            ocr_status="pending",
            ocr_updated_at=datetime.now(timezone.utc),
        )
        await _record_status(doc_id, "pending")
        raise
    except Exception as exception:
        message = str(exception)
        if message == "OCR timeout":
            safe_message = "OCR 处理超时，请拆分文档后重试"
        elif message.startswith("OCR ") or message.startswith("PDF "):
            safe_message = message[:500]
        else:
            logger.exception("OCR processing failed for document %s", doc_id)
            safe_message = "OCR 处理失败，请稍后重试或联系管理员"
        updated = await Document.filter(
            id=doc_id, ocr_status="processing", deleted_at__isnull=True
        ).update(
            ocr_status="failed",
            ocr_error=safe_message,
            ocr_updated_at=datetime.now(timezone.utc),
        )
        if updated:
            await _record_status(doc_id, "failed", safe_message)
        if not updated:
            await Document.filter(
                id=doc_id, ocr_status="processing", deleted_at__isnull=False
            ).update(
                ocr_status="pending",
                ocr_error=None,
                ocr_updated_at=datetime.now(timezone.utc),
            )
            await _record_status(doc_id, "pending")

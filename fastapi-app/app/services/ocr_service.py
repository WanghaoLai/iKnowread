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
from app.storage import get_storage
from app.services.resource_limits import account_lock, ensure_additional_storage

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[int] | None = None
_workers: list[asyncio.Task] = []
_queued_ids: set[int] = set()


def derived_storage_key(doc: Document) -> str | None:
    path = doc.ocr_path
    if path and path.startswith(RELATIVE_PREFIX):
        return path[len(RELATIVE_PREFIX):]
    return None


def preview_storage_key(doc: Document) -> str:
    storage = get_storage()
    derived = derived_storage_key(doc)
    if doc.ocr_status == "ready" and derived and storage.exists(derived):
        return derived
    from app.services.document_service import storage_key
    return storage_key(doc)


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
    await Document.filter(ext="pdf", ocr_status__in=["pending", "processing"]).update(
        ocr_status="failed",
        ocr_error=message,
        ocr_updated_at=datetime.now(timezone.utc),
    )


async def start() -> None:
    global _queue
    if _workers:
        return
    if not settings.OCR_ENABLED:
        await _mark_unavailable("OCR 服务未启用")
        return
    if not _command_prefix():
        await _mark_unavailable("OCR 服务不可用，请安装 OCRmyPDF 后重试")
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
    for doc in await Document.filter(ext="pdf", ocr_status="ready"):
        key = derived_storage_key(doc)
        if not key or not storage.exists(key):
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
    logger.info("PDF OCR queue started with %s worker(s)", worker_count)
    for doc_id in await Document.filter(ext="pdf", ocr_status="pending").values_list("id", flat=True):
        await enqueue(int(doc_id))


async def stop() -> None:
    global _queue
    tasks = list(_workers)
    _workers.clear()
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _queued_ids.clear()
    _queue = None


async def enqueue(doc_id: int) -> None:
    if _queue is None or doc_id in _queued_ids:
        return
    _queued_ids.add(doc_id)
    await _queue.put(doc_id)
    logger.info("OCR job queued document=%s queue_depth=%s", doc_id, _queue.qsize())


async def retry(doc: Document) -> None:
    if doc.ext != "pdf":
        raise CustomException("仅 PDF 支持 OCR")
    if not settings.OCR_ENABLED:
        raise CustomException("OCR 服务未启用")
    if not _command_prefix():
        raise CustomException("OCR 服务不可用，请先安装 OCRmyPDF")
    if doc.ocr_status in ("pending", "processing"):
        return
    await Document.filter(id=doc.id).update(
        ocr_status="pending",
        ocr_error=None,
        ocr_updated_at=datetime.now(timezone.utc),
    )
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
    claimed = await Document.filter(id=doc_id, ext="pdf", ocr_status="pending").update(
        ocr_status="processing",
        ocr_error=None,
        ocr_updated_at=datetime.now(timezone.utc),
    )
    if not claimed:
        return

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

            # 文档可能在耗时处理期间被删除；此时不再生成孤立派生文件。
            current = await Document.get_or_none(id=doc_id)
            if current is None:
                return
            async with account_lock(doc.account_id):
                try:
                    await ensure_additional_storage(doc.account_id, output.stat().st_size)
                except CustomException as exc:
                    raise RuntimeError("OCR 派生文件超过账号或服务器存储限额") from exc
                with output.open("rb") as result:
                    new_key = await get_storage().save(
                        f"document_{doc_id}_searchable.pdf",
                        result,
                        subdir=f"{doc.account.role}/{doc.account_id}/ocr",
                    )
            old_key = derived_storage_key(current)
            updated = await Document.filter(id=doc_id, ocr_status="processing").update(
                ocr_status="ready",
                ocr_path=RELATIVE_PREFIX + new_key,
                ocr_error=None,
                ocr_updated_at=datetime.now(timezone.utc),
            )
            if not updated:
                get_storage().delete(new_key)
                return
            if old_key and old_key != new_key:
                get_storage().delete(old_key)
    except asyncio.CancelledError:
        await Document.filter(id=doc_id, ocr_status="processing").update(
            ocr_status="pending",
            ocr_updated_at=datetime.now(timezone.utc),
        )
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
        await Document.filter(id=doc_id, ocr_status="processing").update(
            ocr_status="failed",
            ocr_error=safe_message,
            ocr_updated_at=datetime.now(timezone.utc),
        )

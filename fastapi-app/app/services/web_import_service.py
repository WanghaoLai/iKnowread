from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import io
import json
import logging
from urllib.parse import urlsplit

from tortoise.expressions import F
from tortoise.transactions import in_transaction

from app.common.exception_handler import CustomException
from app.config import settings
from app.models import Account, Document, DocumentProcessingTask, WebImportJob
from app.schemas.web_import import WebImportJobPublic
from app.services.account_service import RELATIVE_PREFIX, normalize_role
from app.services.auth_guard import client_ip, limiter
from app.services.crawler_client import CrawlerError
from app.services import crawler_client
from app.services.resource_limits import account_lock, ensure_additional_storage, ensure_document_capacity
from app.services.url_safety import assert_resolved_public
from app.storage import complete_on_cancellation, get_storage, run_storage_io


logger = logging.getLogger(__name__)
_queue: asyncio.Queue[int] | None = None
_workers: list[asyncio.Task] = []
_dispatcher: asyncio.Task | None = None
_queued: set[int] = set()


class _JobStateChanged(RuntimeError):
    """Publication lost its processing-state compare-and-swap (for example cancel)."""


def serialize(job: WebImportJob) -> dict:
    return WebImportJobPublic.model_validate(job).model_dump()


def _safe_title(value: str, url: str) -> str:
    fallback = urlsplit(url).hostname or "网页收藏"
    return (" ".join(value.split()) or fallback)[:500]


def _filename(title: str) -> str:
    cleaned = "".join("_" if ch in '/\\:*?\"<>|' or ord(ch) < 32 else ch for ch in title)
    return f"{(cleaned.strip().strip('.') or '网页收藏')[:200]}.md"


def build_markdown(*, title: str, url: str, fetched_at: datetime, raw: str) -> bytes:
    frontmatter = (
        "---\nsource: url\n"
        f"source_url: {json.dumps(url, ensure_ascii=False)}\n"
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        f"fetched_at: {json.dumps(fetched_at.isoformat(), ensure_ascii=False)}\n"
        "---\n\n"
    )
    return (frontmatter + raw.strip() + "\n").encode("utf-8")


async def limit(request, account_id: int) -> None:
    """创建/重试的频率闸：IP 与账号双维度滑动窗口，防排队接口被脚本灌满。"""
    await limiter.check(
        f"web_import:ip:{client_ip(request)}",
        settings.WEB_IMPORT_RATE_LIMIT, settings.WEB_IMPORT_RATE_WINDOW_SECONDS,
    )
    await limiter.check(
        f"web_import:account:{account_id}",
        settings.WEB_IMPORT_RATE_LIMIT, settings.WEB_IMPORT_RATE_WINDOW_SECONDS,
    )


async def _ensure_pending_slot(account_id: int) -> None:
    """账号级并发槽：pending+processing 合计不超过上限（调用方须持有 account_lock）。

    计数检查与建行/重置之间必须同处一次持锁，否则并发请求可同时
    通过计数检查突破上限。account_lock 是不可重入的 asyncio.Lock。
    """
    active = await WebImportJob.filter(
        account_id=account_id, status__in=["pending", "processing"]
    ).count()
    if active >= max(1, settings.WEB_IMPORT_PENDING_LIMIT):
        raise CustomException(
            f"等待中的网页收藏任务已达上限（{max(1, settings.WEB_IMPORT_PENDING_LIMIT)} 个），请先等任务完成",
            status_code=429,
        )


async def create(account_id: int, url: str) -> dict:
    if error := await crawler_client.runtime_availability_error():
        raise CustomException(error, status_code=503)
    # 词法校验在 schema 完成；这里把域名解析到公网的校验放在建任务之前，
    # 内网域名（含 rebinding 静态形态）不会进入队列。
    try:
        await assert_resolved_public(urlsplit(url).hostname or "")
    except ValueError as exc:
        raise CustomException(str(exc), status_code=400) from exc
    async with account_lock(account_id):
        await _ensure_pending_slot(account_id)
        job = await WebImportJob.create(account_id=account_id, source_url=url)
    await enqueue(job.id)
    return serialize(job)


async def get_for_account(job_id: int, account_id: int) -> WebImportJob:
    job = await WebImportJob.get_or_none(id=job_id, account_id=account_id)
    if job is None:
        raise CustomException("抓取任务不存在", status_code=404)
    return job


async def list_for_account(account_id: int, limit: int = 20) -> list[dict]:
    jobs = await WebImportJob.filter(account_id=account_id).order_by("-created_at", "-id").limit(limit)
    return [serialize(job) for job in jobs]


async def retry(job_id: int, account_id: int) -> dict:
    job = await get_for_account(job_id, account_id)
    if job.status != "failed":
        raise CustomException("只有失败的抓取任务可以重试", status_code=409)
    if job.attempt_count >= max(1, settings.WEB_IMPORT_MAX_ATTEMPTS):
        raise CustomException(
            f"该任务已尝试 {job.attempt_count} 次仍未成功，请删除后重新创建",
            status_code=409,
        )
    if error := await crawler_client.runtime_availability_error():
        raise CustomException(error, status_code=503)
    async with account_lock(account_id):
        await _ensure_pending_slot(account_id)
        updated = await WebImportJob.filter(id=job.id, status="failed").update(
            status="pending", progress=0, error=None, started_at=None, finished_at=None
        )
    if not updated:
        raise CustomException("抓取任务状态已变化，请刷新后重试", status_code=409)
    await enqueue(job.id)
    return serialize(await WebImportJob.get(id=job.id))


async def cancel(job_id: int, account_id: int) -> dict:
    job = await get_for_account(job_id, account_id)
    if job.status not in {"pending", "processing"}:
        raise CustomException("只有排队中或抓取中的任务可以取消", status_code=409)
    changed = await WebImportJob.filter(
        id=job.id, account_id=account_id, status__in=["pending", "processing"]
    ).update(
        status="canceled", progress=100, error="任务已取消",
        finished_at=datetime.now(timezone.utc),
    )
    if not changed:
        raise CustomException("抓取任务状态已变化，请刷新后重试", status_code=409)
    return serialize(await WebImportJob.get(id=job.id))


async def delete(job_id: int, account_id: int) -> None:
    job = await get_for_account(job_id, account_id)
    if job.status in {"pending", "processing"}:
        raise CustomException("请先取消正在执行的抓取任务", status_code=409)
    await WebImportJob.filter(id=job.id, account_id=account_id).delete()


async def enqueue(job_id: int) -> bool:
    if _queue is None or job_id in _queued:
        return False
    try:
        _queue.put_nowait(job_id)
    except asyncio.QueueFull:
        return False
    _queued.add(job_id)
    return True


async def start() -> None:
    global _queue, _workers, _dispatcher
    if _workers:
        return
    if error := crawler_client.availability_error():
        # Configuration is loaded once when the backend process starts. Keep
        # durable pending jobs untouched while the feature is intentionally
        # disabled; enabling it and restarting the backend resumes the queue.
        logger.info("Web import worker not started: %s", error)
        return
    _queue = asyncio.Queue(maxsize=max(1, settings.WEB_IMPORT_QUEUE_SIZE))
    await WebImportJob.filter(status="processing").update(
        status="pending", progress=0, error="服务重启，任务已重新排队",
        started_at=None, finished_at=None,
    )
    count = settings.WEB_IMPORT_WORKERS
    _workers = [asyncio.create_task(_worker(), name=f"web-import-{index}") for index in range(count)]
    _dispatcher = asyncio.create_task(_dispatch_loop(), name="web-import-dispatcher")
    await _fill_queue()


async def stop() -> None:
    global _queue, _workers, _dispatcher
    tasks = [*_workers, *([_dispatcher] if _dispatcher else [])]
    _workers = []
    _dispatcher = None
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    _queued.clear()
    _queue = None


async def _worker() -> None:
    while True:
        assert _queue is not None
        job_id = await _queue.get()
        try:
            await _process(job_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unexpected web import worker error job_id=%s", job_id)
            await _fail(job_id, "网页收藏失败，请稍后重试")
        finally:
            _queued.discard(job_id)
            _queue.task_done()


async def _fill_queue() -> None:
    if _queue is None:
        return
    available = _queue.maxsize - _queue.qsize()
    if available <= 0:
        return
    limit = min(available, max(1, settings.WEB_IMPORT_RECOVERY_BATCH_SIZE))
    query = WebImportJob.filter(status="pending")
    if _queued:
        query = query.exclude(id__in=list(_queued))
    pending_ids = await query.order_by("created_at", "id").limit(limit).values_list("id", flat=True)
    for job_id in pending_ids:
        await enqueue(job_id)


async def _cleanup_terminal_jobs() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(
        days=max(1, settings.WEB_IMPORT_RETENTION_DAYS)
    )
    ids = await WebImportJob.filter(
        status__in=["success", "failed", "canceled"], finished_at__lt=cutoff
    ).order_by("finished_at", "id").limit(
        max(1, settings.WEB_IMPORT_CLEANUP_BATCH_SIZE)
    ).values_list("id", flat=True)
    if ids:
        return await WebImportJob.filter(id__in=ids).delete()
    return 0


async def _dispatch_loop() -> None:
    while True:
        try:
            await _fill_queue()
            await _cleanup_terminal_jobs()
            await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Web import dispatcher iteration failed")
            await asyncio.sleep(5)


async def _fail(job_id: int, message: str) -> None:
    await WebImportJob.filter(id=job_id, status="processing").update(
        status="failed", progress=100, error=message[:500],
        finished_at=datetime.now(timezone.utc),
    )


async def _process(job_id: int) -> None:
    now = datetime.now(timezone.utc)
    claimed = await WebImportJob.filter(id=job_id, status="pending").update(
        status="processing", progress=10, error=None, started_at=now,
        finished_at=None, attempt_count=F("attempt_count") + 1,
    )
    if not claimed:
        return
    job = await WebImportJob.get(id=job_id)
    try:
        page = await crawler_client.crawl(job.source_url)
        await WebImportJob.filter(id=job_id, status="processing").update(progress=70)
        fetched_at = datetime.now(timezone.utc)
        title = _safe_title(page.title, job.source_url)
        content = build_markdown(title=title, url=job.source_url, fetched_at=fetched_at, raw=page.markdown)
        if len(content) > max(1, settings.MARKDOWN_MAX_BYTES):
            raise CrawlerError("提取后的 Markdown 超过 5MB 限制")
        await complete_on_cancellation(_publish(job, title, fetched_at, content))
    except CrawlerError as exc:
        await _fail(job_id, str(exc))
    except CustomException as exc:
        await _fail(job_id, exc.message)
    except _JobStateChanged:
        # cancel/delete state is authoritative; _publish already rolled back its
        # database transaction and removes the staged file in its exception path.
        return


async def _publish(job: WebImportJob, title: str, fetched_at: datetime, content: bytes) -> None:
    account = await Account.get_or_none(id=job.account_id)
    normalized = normalize_role(account.role) if account else None
    if not account or not normalized:
        raise CustomException("账号不存在", status_code=404)
    storage = get_storage()
    async with account_lock(job.account_id):
        await ensure_document_capacity(job.account_id, len(content))
        key = await storage.save(
            _filename(title), io.BytesIO(content),
            subdir=f"{normalized}/{job.account_id}/documents",
        )
        try:
            size = await run_storage_io(storage.size, key)
            await ensure_additional_storage(job.account_id, 0)
            async with in_transaction() as connection:
                document = await Document.create(
                    using_db=connection, name=_filename(title)[:255], ext="md", size=size,
                    path=f"{RELATIVE_PREFIX}{key}", account_id=job.account_id,
                    ocr_status="not_applicable", source_type="url",
                    source_url=job.source_url, source_title=title, source_fetched_at=fetched_at,
                )
                await DocumentProcessingTask.create(
                    using_db=connection, document_id=document.id, task_type="ocr",
                    status="not_applicable", progress=0,
                )
                updated = await WebImportJob.filter(id=job.id, status="processing").using_db(connection).update(
                    status="success", progress=100, error=None,
                    result_document_id=document.id, finished_at=fetched_at,
                )
                if not updated:
                    raise _JobStateChanged("web import job state changed during publication")
        except BaseException:
            await run_storage_io(storage.delete, key)
            raise

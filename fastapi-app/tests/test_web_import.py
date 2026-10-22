import asyncio
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import HTTPException
from tortoise import Tortoise

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.common.exception_handler import CustomException
from app.config import settings
from app.models import Account, Document, WebImportJob
from app.services import crawler_client, document_service, web_import_service
from app.services import url_safety
from app.services.auth_guard import limiter
from app.services.crawler_client import CrawledPage
from app.services.url_safety import normalize_public_url
from app.storage import get_storage


class UrlSafetyTests(unittest.TestCase):
    def test_accepts_public_http_urls_and_removes_fragments(self):
        self.assertEqual(
            normalize_public_url("https://Example.com/article?q=1#part"),
            "https://example.com/article?q=1",
        )
        self.assertEqual(normalize_public_url("https://example.com:443/a"), "https://example.com:443/a")

    def test_rejects_local_and_non_http_destinations(self):
        for value in (
            "file:///etc/passwd", "http://localhost/admin", "http://127.0.0.1/",
            "http://10.0.0.8/", "http://[::1]/", "https://printer.local/",
            "https://user:secret@example.com/",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_public_url(value)

    def test_rejects_non_dotted_ipv4_encodings(self):
        # Chromium 会把这些归一化为 127.0.0.1 再连接；ipaddress 不认，
        # 词法层必须按可疑 IP 变体直接拒绝。
        for value in (
            "http://2130706433/", "http://0x7f000001/", "http://0177.0.0.1/",
            "http://169.254.169.254/", "http://0.0.0.0/",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_public_url(value)

    def test_rejects_ports_outside_the_allowlist(self):
        for value in (
            "http://example.com:8080/", "https://example.com:6379/",
            "https://example.com:8443/",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_public_url(value)


class ResolvedHostTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_domain_resolving_to_private_address(self):
        with patch.object(
            url_safety, "_resolve_host", AsyncMock(return_value=["93.184.216.34", "10.0.0.5"])
        ):
            with self.assertRaises(ValueError):
                await url_safety.assert_resolved_public("rebinding.example")

    async def test_accepts_domain_resolving_only_to_public_addresses(self):
        with patch.object(
            url_safety, "_resolve_host", AsyncMock(return_value=["93.184.216.34"])
        ):
            await url_safety.assert_resolved_public("example.com")

    async def test_literal_ips_skip_dns_and_follow_is_global(self):
        await url_safety.assert_resolved_public("8.8.8.8")
        with self.assertRaises(ValueError):
            await url_safety.assert_resolved_public("192.168.1.10")

    async def test_dns_failure_becomes_readable_rejection(self):
        with patch.object(url_safety, "_resolve_host", AsyncMock(side_effect=OSError("name or service not known"))):
            with self.assertRaises(ValueError):
                await url_safety.assert_resolved_public("nonexistent.example.invalid")


class CrawlerAvailabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        crawler_client.reset_probe_cache()

    async def test_runtime_probe_reports_healthy_service(self):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.get.return_value = httpx.Response(
            200, request=httpx.Request("GET", "http://crawler/health")
        )
        crawler_client.reset_probe_cache()
        with (
            patch.object(settings, "CRAWLER_ENABLED", True),
            patch.object(settings, "CRAWLER_API_TOKEN", "test-token"),
            patch.object(crawler_client.httpx, "AsyncClient", return_value=client),
        ):
            self.assertIsNone(await crawler_client.runtime_availability_error(force=True))

    async def test_runtime_probe_reports_unreachable_optional_service(self):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.get.side_effect = httpx.ConnectError("offline")
        crawler_client.reset_probe_cache()
        with (
            patch.object(settings, "CRAWLER_ENABLED", True),
            patch.object(settings, "CRAWLER_API_TOKEN", "test-token"),
            patch.object(crawler_client.httpx, "AsyncClient", return_value=client),
        ):
            self.assertEqual(
                await crawler_client.runtime_availability_error(force=True),
                "网页收藏服务暂不可用",
            )

    async def test_crawler_failure_does_not_expose_upstream_diagnostics(self):
        sensitive = "browser failed at http://crawler:11235/?token=secret-api-key"
        response = httpx.Response(
            200,
            json={"success": True, "results": [{"success": False, "error_message": sensitive}]},
            request=httpx.Request("POST", "http://crawler/crawl"),
        )
        stream = AsyncMock()
        stream.__aenter__.return_value = response
        stream.__aexit__.return_value = None
        client = MagicMock()
        client.__aenter__.return_value = client
        client.stream.return_value = stream
        with (
            patch.object(settings, "CRAWLER_ENABLED", True),
            patch.object(settings, "CRAWLER_API_TOKEN", "test-token"),
            patch.object(crawler_client.httpx, "AsyncClient", return_value=client),
        ):
            with self.assertRaisesRegex(crawler_client.CrawlerError, "^网页抓取失败$") as ctx:
                await crawler_client.crawl("https://example.com")
        self.assertNotIn("secret-api-key", str(ctx.exception))

    async def test_worker_configuration_is_bounded(self):
        from pydantic import ValidationError

        from app.config import Settings

        self.assertEqual(Settings(WEB_IMPORT_WORKERS=4, _env_file=None).WEB_IMPORT_WORKERS, 4)
        for invalid in (0, 5):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                Settings(WEB_IMPORT_WORKERS=invalid, _env_file=None)


class WebImportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [
            patch.object(settings, "UPLOAD_DIR", self.temp.name),
            patch.object(settings, "STORAGE_MIN_FREE_BYTES", 0),
            patch.object(settings, "USER_STORAGE_QUOTA_BYTES", 10 * 1024 * 1024),
            patch.object(settings, "USER_DOCUMENT_LIMIT", 10),
            patch.object(settings, "USER_TOTAL_DOCUMENT_LIMIT", 20),
            patch.object(settings, "MARKDOWN_MAX_BYTES", 1024 * 1024),
            patch.object(settings, "WEB_IMPORT_PENDING_LIMIT", 2),
            patch.object(settings, "WEB_IMPORT_MAX_ATTEMPTS", 3),
            patch.object(
                web_import_service.crawler_client,
                "runtime_availability_error",
                AsyncMock(return_value=None),
            ),
        ]
        for item in self.patches:
            item.start()
        limiter.clear()
        get_storage.cache_clear()
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.account = await Account.create(
            username="web-reader", password="unused", name="网页读者", role="user"
        )

    async def asyncTearDown(self):
        await Tortoise.close_connections()
        limiter.clear()
        get_storage.cache_clear()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    async def test_success_publishes_markdown_document_with_source_metadata(self):
        job = await WebImportJob.create(
            account_id=self.account.id, source_url="https://example.com/article"
        )
        crawler = AsyncMock(return_value=CrawledPage(markdown="# 正文\n\n内容", title="示例文章"))
        with patch.object(web_import_service.crawler_client, "crawl", crawler):
            await web_import_service._process(job.id)

        await job.refresh_from_db()
        self.assertEqual(job.status, "success")
        self.assertEqual(job.attempt_count, 1)
        document = await Document.get(id=job.result_document_id)
        self.assertEqual(document.source_type, "url")
        self.assertEqual(document.source_url, job.source_url)
        self.assertEqual(document.source_title, "示例文章")
        self.assertEqual(document.ext, "md")
        with get_storage().open(document_service.storage_key(document)) as source:
            text = source.read().decode()
        self.assertIn("source: url", text)
        self.assertIn("# 正文", text)

    async def test_failed_job_can_be_reset_for_retry(self):
        job = await WebImportJob.create(
            account_id=self.account.id, source_url="https://example.com/fail",
            status="failed", error="timeout", progress=100, attempt_count=1,
        )
        with (
            patch.object(settings, "CRAWLER_ENABLED", True),
            patch.object(settings, "CRAWLER_API_TOKEN", "test-token"),
        ):
            result = await web_import_service.retry(job.id, self.account.id)
        self.assertEqual(result["status"], "pending")
        self.assertIsNone(result["error"])

    async def test_create_blocked_when_domain_resolves_to_private_address(self):
        with (
            patch.object(settings, "CRAWLER_ENABLED", True),
            patch.object(settings, "CRAWLER_API_TOKEN", "test-token"),
            patch.object(url_safety, "_resolve_host", AsyncMock(return_value=["10.0.0.5"])),
        ):
            with self.assertRaises(CustomException) as ctx:
                await web_import_service.create(self.account.id, "https://internal.example/")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(await WebImportJob.filter(account_id=self.account.id).count(), 0)

    async def test_create_blocked_when_pending_limit_reached(self):
        for index in range(2):
            await WebImportJob.create(
                account_id=self.account.id,
                source_url=f"https://example.com/pending-{index}",
                status="pending",
            )
        with (
            patch.object(settings, "CRAWLER_ENABLED", True),
            patch.object(settings, "CRAWLER_API_TOKEN", "test-token"),
            patch.object(url_safety, "_resolve_host", AsyncMock(return_value=["93.184.216.34"])),
        ):
            with self.assertRaises(CustomException) as ctx:
                await web_import_service.create(self.account.id, "https://example.com/more")
        self.assertEqual(ctx.exception.status_code, 429)

    async def test_create_allowed_again_once_slot_frees_up(self):
        await WebImportJob.create(
            account_id=self.account.id, source_url="https://example.com/a", status="pending",
        )
        await WebImportJob.create(
            account_id=self.account.id, source_url="https://example.com/b", status="failed",
        )
        with (
            patch.object(settings, "CRAWLER_ENABLED", True),
            patch.object(settings, "CRAWLER_API_TOKEN", "test-token"),
            patch.object(url_safety, "_resolve_host", AsyncMock(return_value=["93.184.216.34"])),
        ):
            result = await web_import_service.create(self.account.id, "https://example.com/c")
        self.assertEqual(result["status"], "pending")

    async def test_retry_blocked_at_max_attempts(self):
        job = await WebImportJob.create(
            account_id=self.account.id, source_url="https://example.com/dead",
            status="failed", error="upstream down", attempt_count=3,
        )
        with (
            patch.object(settings, "CRAWLER_ENABLED", True),
            patch.object(settings, "CRAWLER_API_TOKEN", "test-token"),
        ):
            with self.assertRaises(CustomException) as ctx:
                await web_import_service.retry(job.id, self.account.id)
        self.assertEqual(ctx.exception.status_code, 409)

    async def test_retry_blocked_when_pending_limit_reached(self):
        for index in range(2):
            await WebImportJob.create(
                account_id=self.account.id,
                source_url=f"https://example.com/pending-{index}",
                status="pending",
            )
        job = await WebImportJob.create(
            account_id=self.account.id, source_url="https://example.com/failed",
            status="failed", error="timeout", attempt_count=1,
        )
        with (
            patch.object(settings, "CRAWLER_ENABLED", True),
            patch.object(settings, "CRAWLER_API_TOKEN", "test-token"),
        ):
            with self.assertRaises(CustomException) as ctx:
                await web_import_service.retry(job.id, self.account.id)
        self.assertEqual(ctx.exception.status_code, 429)

    async def test_disabled_service_keeps_pending_jobs_for_a_later_restart(self):
        job = await WebImportJob.create(
            account_id=self.account.id,
            source_url="https://example.com/later",
            status="pending",
        )
        with patch.object(settings, "CRAWLER_ENABLED", False):
            await web_import_service.start()
        await job.refresh_from_db()
        self.assertEqual(job.status, "pending")
        self.assertEqual(web_import_service._workers, [])

    async def test_start_creates_configured_number_of_workers(self):
        await web_import_service.stop()

    async def test_multiple_workers_process_distinct_jobs_concurrently(self):
        await web_import_service.stop()
        for index in range(2):
            await WebImportJob.create(
                account_id=self.account.id,
                source_url=f"https://example.com/concurrent-{index}",
            )
        active = 0
        peak = 0
        both_started = asyncio.Event()
        release = asyncio.Event()

        async def concurrent_crawl(_url):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 2:
                both_started.set()
            try:
                await release.wait()
                return CrawledPage(markdown="# concurrent", title="concurrent")
            finally:
                active -= 1

        try:
            with (
                patch.object(settings, "CRAWLER_ENABLED", True),
                patch.object(settings, "CRAWLER_API_TOKEN", "test-token"),
                patch.object(settings, "WEB_IMPORT_WORKERS", 2),
                patch.object(web_import_service.crawler_client, "crawl", concurrent_crawl),
            ):
                await web_import_service.start()
                await asyncio.wait_for(both_started.wait(), 1)
                self.assertEqual(peak, 2)
                release.set()
                await asyncio.wait_for(web_import_service._queue.join(), 2)
        finally:
            release.set()
            await web_import_service.stop()

        self.assertEqual(await WebImportJob.filter(status="success").count(), 2)
        self.assertEqual(await Document.filter(account_id=self.account.id).count(), 2)
        with (
            patch.object(settings, "CRAWLER_ENABLED", True),
            patch.object(settings, "CRAWLER_API_TOKEN", "test-token"),
            patch.object(settings, "WEB_IMPORT_WORKERS", 3),
        ):
            await web_import_service.start()
            self.assertEqual(len(web_import_service._workers), 3)
            self.assertEqual(
                {task.get_name() for task in web_import_service._workers},
                {"web-import-0", "web-import-1", "web-import-2"},
            )
        await web_import_service.stop()

    async def test_create_and_retry_rate_limited_per_account(self):
        request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.9"))
        with patch.object(settings, "WEB_IMPORT_RATE_LIMIT", 2):
            for _ in range(2):
                await web_import_service.limit(request, self.account.id)
            with self.assertRaises(HTTPException) as ctx:
                await web_import_service.limit(request, self.account.id)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("Retry-After", ctx.exception.headers)

    async def test_cancel_prevents_in_flight_job_from_publishing(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def delayed_crawl(_url):
            started.set()
            await release.wait()
            return CrawledPage(markdown="# 不应发布", title="已取消")

        job = await WebImportJob.create(
            account_id=self.account.id,
            source_url="https://example.com/cancel",
        )
        with patch.object(web_import_service.crawler_client, "crawl", delayed_crawl):
            processing = asyncio.create_task(web_import_service._process(job.id))
            await asyncio.wait_for(started.wait(), 1)
            canceled = await web_import_service.cancel(job.id, self.account.id)
            release.set()
            await processing

        self.assertEqual(canceled["status"], "canceled")
        await job.refresh_from_db()
        self.assertEqual(job.status, "canceled")
        self.assertIsNone(job.result_document_id)
        self.assertEqual(await Document.filter(account_id=self.account.id).count(), 0)

    async def test_active_job_must_be_canceled_before_deletion(self):
        job = await WebImportJob.create(
            account_id=self.account.id,
            source_url="https://example.com/delete",
        )
        with self.assertRaises(CustomException) as ctx:
            await web_import_service.delete(job.id, self.account.id)
        self.assertEqual(ctx.exception.status_code, 409)
        await web_import_service.cancel(job.id, self.account.id)
        await web_import_service.delete(job.id, self.account.id)
        self.assertFalse(await WebImportJob.filter(id=job.id).exists())

    async def test_in_memory_dispatch_queue_is_bounded(self):
        previous = web_import_service._queue
        web_import_service._queue = asyncio.Queue(maxsize=1)
        web_import_service._queued.clear()
        try:
            self.assertTrue(await web_import_service.enqueue(101))
            self.assertFalse(await web_import_service.enqueue(102))
            self.assertEqual(web_import_service._queue.qsize(), 1)
        finally:
            web_import_service._queued.clear()
            web_import_service._queue = previous

    async def test_terminal_history_cleanup_is_bounded_by_retention_and_batch(self):
        old = datetime.now(timezone.utc) - timedelta(days=31)
        for index in range(2):
            await WebImportJob.create(
                account_id=self.account.id,
                source_url=f"https://example.com/old-{index}",
                status="failed",
                finished_at=old,
            )
        recent = await WebImportJob.create(
            account_id=self.account.id,
            source_url="https://example.com/recent",
            status="success",
            finished_at=datetime.now(timezone.utc),
        )
        with (
            patch.object(settings, "WEB_IMPORT_RETENTION_DAYS", 30),
            patch.object(settings, "WEB_IMPORT_CLEANUP_BATCH_SIZE", 1),
        ):
            self.assertEqual(await web_import_service._cleanup_terminal_jobs(), 1)
        self.assertEqual(
            await WebImportJob.filter(status="failed").count(), 1
        )
        self.assertTrue(await WebImportJob.filter(id=recent.id).exists())

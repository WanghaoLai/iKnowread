"""隔离存储与 SQLite，验证 OCR 派生文件完整生命周期，不调用真实 OCR 进程。"""
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from tortoise import Tortoise

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.config import settings
from app.dependencies import CurrentAccount, get_current_account
from app.models import Account, Document, DocumentProcessingTask, Highlight, Note
from app.services import document_service, ocr_service, processing_task_service
from app.storage import get_storage


class OCRTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.upload_patch = patch.object(settings, "UPLOAD_DIR", self.temp.name)
        self.upload_patch.start()
        self.ocr_enabled_patch = patch.object(settings, "OCR_ENABLED", True)
        self.ocr_enabled_patch.start()
        get_storage.cache_clear()
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.user = await Account.create(
            username="ocr-user", name="测试", password="unused", role="user"
        )
        self.other = await Account.create(
            username="ocr-other", name="其他", password="unused", role="user"
        )
        self.app = create_app()
        self.as_account(self.user)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        await ocr_service.stop()
        await Tortoise.close_connections()
        get_storage.cache_clear()
        self.ocr_enabled_patch.stop()
        self.upload_patch.stop()
        self.temp.cleanup()

    def as_account(self, account):
        self.app.dependency_overrides[get_current_account] = lambda: CurrentAccount(
            account.id, account.role, account
        )

    async def make_document(self, *, status="pending", owner=None, derived=False):
        owner = owner or self.user
        storage = get_storage()
        original_key = await storage.save(
            "scan.pdf", io.BytesIO(b"%PDF-original"), subdir=f"user/{owner.id}"
        )
        ocr_path = None
        if derived:
            derived_key = await storage.save(
                "scan_searchable.pdf", io.BytesIO(b"%PDF-derived"),
                subdir=f"user/{owner.id}/ocr",
            )
            ocr_path = "files/download/" + derived_key
        doc = await Document.create(
            name="scan.pdf",
            ext="pdf",
            size=13,
            path="files/download/" + original_key,
            account_id=owner.id,
            ocr_status=status,
            ocr_path=ocr_path,
        )
        return doc, original_key

    async def test_process_creates_searchable_derivative_and_preserves_original(self):
        doc, original_key = await self.make_document()
        original_version = doc.content_version

        async def fake_run(source, output):
            self.assertEqual(source.read_bytes(), b"%PDF-original")
            output.write_bytes(b"%PDF-searchable")
            return 0, ""

        with patch.object(ocr_service, "_run_command", side_effect=fake_run):
            await ocr_service.process_document(doc.id)

        updated = await Document.get(id=doc.id)
        derived_key = document_service.ocr_storage_key(updated)
        self.assertEqual(updated.ocr_status, "ready")
        self.assertEqual(updated.content_version, original_version)
        self.assertIsNotNone(updated.ocr_updated_at)
        self.assertTrue(get_storage().exists(original_key))
        self.assertTrue(get_storage().exists(derived_key))
        self.assertEqual(await ocr_service.preview_storage_key(updated), derived_key)
        task = await DocumentProcessingTask.get(
            document_id=doc.id, task_type=processing_task_service.OCR
        )
        self.assertEqual(task.status, "ready")
        self.assertEqual(task.progress, 100)

    async def test_processing_status_lists_only_executable_stages(self):
        doc, _ = await self.make_document(status="pending")

        response = await self.client.get(f"/documents/{doc.id}/processing-status")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["document_id"], doc.id)
        stages = {stage["type"]: stage for stage in data["stages"]}
        self.assertEqual(set(stages), {"ocr"})
        self.assertEqual(stages["ocr"]["status"], "pending")

        listed = await self.client.get("/documents")
        listed_stages = listed.json()["data"]["list"][0]["processing_stages"]
        self.assertEqual(len(listed_stages), 1)

        self.as_account(self.other)
        forbidden = await self.client.get(f"/documents/{doc.id}/processing-status")
        self.assertEqual(forbidden.status_code, 403)

    async def test_preview_uses_derivative_download_keeps_original_and_owner_is_enforced(self):
        doc, _ = await self.make_document(status="ready", derived=True)
        preview = await self.client.get(f"/documents/{doc.id}/preview")
        download = await self.client.get(f"/documents/{doc.id}/download")
        self.assertEqual(preview.content, b"%PDF-derived")
        self.assertEqual(download.content, b"%PDF-original")

        self.as_account(self.other)
        self.assertEqual(
            (await self.client.get(f"/documents/{doc.id}/ocr-status")).status_code, 403
        )
        self.assertEqual((await self.client.post(f"/documents/{doc.id}/ocr")).status_code, 403)

    async def test_failure_is_safe_and_retry_returns_to_queue_state(self):
        doc, _ = await self.make_document()
        with self.assertLogs("app.services.ocr_service", level="WARNING") as captured:
            with patch.object(
                ocr_service,
                "_run_command",
                return_value=(1, "Tesseract language chi_sim not found at /private/secret"),
            ):
                await ocr_service.process_document(doc.id)
        self.assertNotIn("/private/secret", "\n".join(captured.output))

        failed = await Document.get(id=doc.id)
        self.assertEqual(failed.ocr_status, "failed")
        self.assertIn("语言包", failed.ocr_error)
        self.assertNotIn("/private/secret", failed.ocr_error)

        with patch.object(ocr_service, "availability_error", return_value=None):
            response = await self.client.post(f"/documents/{doc.id}/ocr")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["ocr_status"], "pending")

    async def test_reprocessing_publishes_derivative_without_changing_source_version(self):
        doc, _ = await self.make_document(status="ready", derived=True)
        old_key = document_service.ocr_storage_key(doc)
        old_version = doc.content_version

        with patch.object(ocr_service, "availability_error", return_value=None):
            await ocr_service.retry(doc)
        pending = await Document.get(id=doc.id)
        self.assertEqual(pending.content_version, old_version)
        self.assertEqual(await ocr_service.preview_storage_key(pending), old_key)

        async def fake_run(source, output):
            output.write_bytes(b"%PDF-new-searchable")
            return 0, ""

        with patch.object(ocr_service, "_run_command", side_effect=fake_run):
            await ocr_service.process_document(doc.id)
        updated = await Document.get(id=doc.id)
        self.assertEqual(updated.content_version, old_version)
        self.assertNotEqual(document_service.ocr_storage_key(updated), old_key)
        with get_storage().open(document_service.ocr_storage_key(updated)) as result:
            self.assertEqual(result.read(), b"%PDF-new-searchable")
        versioned_preview = await self.client.get(
            f"/documents/{doc.id}/preview", params={"version": old_version}
        )
        self.assertEqual(versioned_preview.status_code, 200, versioned_preview.text)
        self.assertEqual(versioned_preview.content, b"%PDF-new-searchable")

    async def test_reprocessing_credits_replaced_derivative_against_account_quota(self):
        doc, original_key = await self.make_document(status="ready", derived=True)
        old_key = document_service.ocr_storage_key(doc)
        storage = get_storage()
        new_content = b"%PDF-new-searchable"
        final_size = storage.size(original_key) + len(new_content)

        with patch.object(ocr_service, "availability_error", return_value=None):
            await ocr_service.retry(doc)

        async def fake_run(source, output):
            output.write_bytes(new_content)
            return 0, ""

        with (
            patch.object(settings, "USER_STORAGE_QUOTA_BYTES", final_size),
            patch.object(settings, "STORAGE_MIN_FREE_BYTES", 0),
            patch.object(ocr_service, "_run_command", side_effect=fake_run),
        ):
            await ocr_service.process_document(doc.id)

        updated = await Document.get(id=doc.id)
        self.assertEqual(updated.ocr_status, "ready")
        self.assertFalse(storage.exists(old_key))
        self.assertEqual(
            storage.size(original_key) + storage.size(document_service.ocr_storage_key(updated)),
            final_size,
        )

    async def test_failed_reprocessing_keeps_old_version_and_preview(self):
        doc, _ = await self.make_document(status="ready", derived=True)
        old_key = document_service.ocr_storage_key(doc)
        old_version = doc.content_version
        with patch.object(ocr_service, "availability_error", return_value=None):
            await ocr_service.retry(doc)
        with patch.object(ocr_service, "_run_command", return_value=(1, "failed")):
            await ocr_service.process_document(doc.id)
        failed = await Document.get(id=doc.id)
        self.assertEqual(failed.content_version, old_version)
        self.assertEqual(await ocr_service.preview_storage_key(failed), old_key)

    async def test_ocr_publish_preserves_highlights_and_notes(self):
        doc, _ = await self.make_document()
        anchor = {
            "protocol": "iknowread.source-anchor/v1",
            "document_id": doc.id,
            "document_version": doc.content_version,
            "source_format": "pdf",
            "scope": "page",
            "page": 1,
            "progression": 0.1,
            "selector": {
                "position": {"start": 0, "end": 4},
                "quote": {"exact": "测试文字", "prefix": "", "suffix": ""},
            },
        }
        highlight = await self.client.post("/highlights", json={
            "document_id": doc.id,
            "source_anchor": anchor,
            "selected_text": "测试文字",
            "remark": "保留高亮",
        })
        note = await self.client.post("/notes", json={
            "source_type": "ai_explanation",
            "document_id": doc.id,
            "document_version": doc.content_version,
            "source_anchor": anchor,
            "selected_text": "测试文字",
            "content": "保留笔记",
        })
        self.assertEqual(highlight.status_code, 200, highlight.text)
        self.assertEqual(note.status_code, 200, note.text)

        async def fake_run(_source, output):
            output.write_bytes(b"%PDF-searchable")
            return 0, ""

        with patch.object(ocr_service, "_run_command", side_effect=fake_run):
            await ocr_service.process_document(doc.id)

        updated = await Document.get(id=doc.id)
        self.assertEqual(updated.content_version, doc.content_version)
        self.assertEqual(await Highlight.filter(document_id=doc.id).count(), 1)
        self.assertEqual(await Note.filter(document_id=doc.id).count(), 1)
        listed = await self.client.get("/highlights", params={
            "documentId": doc.id,
            "documentVersion": doc.content_version,
        })
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()["data"]), 1)

    async def test_delete_removes_original_and_derivative(self):
        doc, original_key = await self.make_document(status="ready", derived=True)
        derived_key = document_service.ocr_storage_key(doc)
        # 现在的删除语义：先软删除进回收站（文件保留），再彻底删除。
        await document_service.soft_delete(doc.id)
        self.assertTrue(get_storage().exists(original_key))
        self.assertTrue(get_storage().exists(derived_key))
        await document_service.delete(doc.id)
        self.assertFalse(get_storage().exists(original_key))
        self.assertFalse(get_storage().exists(derived_key))
        self.assertFalse(await Document.filter(id=doc.id).exists())

    async def test_delete_during_ocr_preserves_version_and_restore_requeues(self):
        doc, _ = await self.make_document()
        original_version = doc.content_version

        async def delete_while_processing(source, output):
            await document_service.soft_delete(doc.id)
            output.write_bytes(b"%PDF-should-not-be-published")
            return 0, ""

        with patch.object(ocr_service, "_run_command", side_effect=delete_while_processing):
            await ocr_service.process_document(doc.id)

        recycled = await Document.get(id=doc.id)
        self.assertIsNotNone(recycled.deleted_at)
        self.assertEqual(recycled.content_version, original_version)
        self.assertEqual(recycled.ocr_status, "pending")
        self.assertIsNone(recycled.ocr_path)
        self.assertEqual(len(get_storage().iter_keys(f"user/{self.user.id}/ocr")), 0)

        enqueue = AsyncMock()
        with patch("app.routers.document.ocr_service.enqueue", enqueue):
            response = await self.client.post(f"/documents/recycle-bin/{doc.id}/restore")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["content_version"], original_version)
        enqueue.assert_awaited_once_with(doc.id)


if __name__ == "__main__":
    unittest.main()

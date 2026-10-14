"""隔离存储与 SQLite，验证 OCR 派生文件完整生命周期，不调用真实 OCR 进程。"""
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from tortoise import Tortoise

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.config import settings
from app.dependencies import CurrentAccount, get_current_account
from app.models import Account, Document
from app.services import document_service, ocr_service
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

        async def fake_run(source, output):
            self.assertEqual(source.read_bytes(), b"%PDF-original")
            output.write_bytes(b"%PDF-searchable")
            return 0, ""

        with patch.object(ocr_service, "_run_command", side_effect=fake_run):
            await ocr_service.process_document(doc.id)

        updated = await Document.get(id=doc.id)
        derived_key = document_service.ocr_storage_key(updated)
        self.assertEqual(updated.ocr_status, "ready")
        self.assertIsNotNone(updated.ocr_updated_at)
        self.assertTrue(get_storage().exists(original_key))
        self.assertTrue(get_storage().exists(derived_key))
        self.assertEqual(ocr_service.preview_storage_key(updated), derived_key)

    async def test_preview_uses_derivative_download_keeps_original_and_owner_is_enforced(self):
        doc, _ = await self.make_document(status="ready", derived=True)
        preview = await self.client.get(f"/document/preview/{doc.id}")
        download = await self.client.get(f"/document/download/{doc.id}")
        self.assertEqual(preview.content, b"%PDF-derived")
        self.assertEqual(download.content, b"%PDF-original")

        self.as_account(self.other)
        self.assertEqual(
            (await self.client.get(f"/document/{doc.id}/ocr-status")).status_code, 403
        )
        self.assertEqual((await self.client.post(f"/document/{doc.id}/ocr")).status_code, 403)

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

        with patch.object(ocr_service, "_command_prefix", return_value=["/fake/ocrmypdf"]):
            response = await self.client.post(f"/document/{doc.id}/ocr")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["ocr_status"], "pending")

    async def test_delete_removes_original_and_derivative(self):
        doc, original_key = await self.make_document(status="ready", derived=True)
        derived_key = document_service.ocr_storage_key(doc)
        await document_service.delete(doc.id)
        self.assertFalse(get_storage().exists(original_key))
        self.assertFalse(get_storage().exists(derived_key))
        self.assertFalse(await Document.filter(id=doc.id).exists())


if __name__ == "__main__":
    unittest.main()

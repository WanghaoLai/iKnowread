"""隔离存储与 SQLite，验证回收站软删除、恢复与彻底删除的完整生命周期。"""
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
from app.common.exception_handler import CustomException
from app.config import settings
from app.dependencies import CurrentAccount, get_current_account
from app.models import Account, Document, Highlight
from app.services import document_service
from app.storage import get_storage


class RecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.upload_patch = patch.object(settings, "UPLOAD_DIR", self.temp.name)
        self.upload_patch.start()
        get_storage.cache_clear()
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.user = await Account.create(
            username="recycle-user", name="回收站用户", password="unused", role="user"
        )
        self.other = await Account.create(
            username="recycle-other", name="其他用户", password="unused", role="user"
        )
        self.app = create_app()
        self.as_account(self.user)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        await Tortoise.close_connections()
        get_storage.cache_clear()
        self.upload_patch.stop()
        self.temp.cleanup()

    def as_account(self, account):
        self.app.dependency_overrides[get_current_account] = lambda: CurrentAccount(
            account.id, account.role, account
        )

    async def make_document(self, *, owner=None, name="回收站文档.pdf"):
        owner = owner or self.user
        storage = get_storage()
        key = await storage.save(
            name, io.BytesIO(b"%PDF-original"), subdir=f"user/{owner.id}"
        )
        return await Document.create(
            name=name, ext="pdf", size=13,
            path="files/download/" + key, account_id=owner.id,
        )

    def anchor(self, document):
        return {
            "protocol": "iknowread.source-anchor/v1",
            "document_id": document.id,
            "document_version": document.content_version,
            "source_format": "pdf",
            "scope": "page",
            "page": 1,
            "progression": 0.1,
            "selector": {
                "position": {"start": 10, "end": 15},
                "quote": {"exact": "关键内容", "prefix": "这里是", "suffix": "需要理解"},
            },
        }

    async def make_highlight(self, document, *, remark="AI 解释备注"):
        response = await self.client.post("/highlights", json={
            "document_id": document.id,
            "source_anchor": self.anchor(document),
            "selected_text": "关键内容",
            "remark": remark,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    async def test_soft_delete_and_restore_roundtrip(self):
        doc = await self.make_document()
        highlight = await self.make_highlight(doc, remark="恢复后必须还在的备注")
        raw_key = doc.path.removeprefix("files/download/")
        self.assertEqual(
            (await self.client.get(f"/files/download/{raw_key}")).status_code, 404
        )

        deleted = await self.client.delete(f"/documents/{doc.id}")
        self.assertEqual(deleted.status_code, 200, deleted.text)

        active = (await self.client.get("/documents")).json()["data"]
        self.assertEqual(active["total"], 0)
        recycled = (await self.client.get("/documents/recycle-bin")).json()["data"]
        self.assertEqual(recycled["total"], 1)
        self.assertEqual(recycled["list"][0]["name"], "回收站文档.pdf")
        self.assertIsNotNone(recycled["list"][0]["deleted_at"])

        # 回收站期间：预览与高亮接口不可用，但数据行保留
        self.assertEqual((await self.client.get(f"/documents/{doc.id}/preview")).status_code, 404)
        self.assertEqual(
            (await self.client.get("/highlights", params={
                "documentId": doc.id, "documentVersion": doc.content_version,
            })).status_code, 404
        )
        self.assertEqual(await Highlight.all().count(), 1)
        self.assertTrue(get_storage().exists(raw_key))
        self.assertEqual(
            (await self.client.get(f"/files/download/{raw_key}")).status_code, 404
        )
        self.assertEqual(
            (await self.client.put(
                f"/highlights/{highlight['id']}", json={"remark": "回收站内篡改"}
            )).status_code,
            404,
        )
        self.assertEqual(
            (await self.client.delete(f"/highlights/{highlight['id']}")).status_code,
            404,
        )

        restored = await self.client.post(f"/documents/recycle-bin/{doc.id}/restore")
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertIsNone(restored.json()["data"]["deleted_at"])

        active = (await self.client.get("/documents")).json()["data"]
        self.assertEqual(active["total"], 1)
        self.assertEqual(active["list"][0]["id"], doc.id)
        self.assertEqual(
            (await self.client.get(f"/documents/{doc.id}/preview")).status_code, 200
        )
        highlights = (await self.client.get("/highlights", params={
            "documentId": doc.id, "documentVersion": doc.content_version,
        })).json()["data"]
        self.assertEqual(len(highlights), 1)
        self.assertEqual(highlights[0]["remark"], "恢复后必须还在的备注")
        self.assertEqual(highlights[0]["id"], highlight["id"])
        self.assertEqual(highlights[0]["source_anchor"], self.anchor(doc))
        self.assertEqual(restored.json()["data"]["content_version"], doc.content_version)

    async def test_restore_rejects_incomplete_file_snapshot(self):
        doc = await self.make_document()
        await self.client.delete(f"/documents/{doc.id}")
        get_storage().delete(doc.path.removeprefix("files/download/"))

        response = await self.client.post(f"/documents/recycle-bin/{doc.id}/restore")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("文件不完整", response.text)
        self.assertIsNotNone((await Document.get(id=doc.id)).deleted_at)

    async def test_restore_requeues_pending_pdf(self):
        doc = await self.make_document()
        doc.ocr_status = "pending"
        await doc.save(update_fields=["ocr_status"])
        await self.client.delete(f"/documents/{doc.id}")

        enqueue = AsyncMock()
        with patch("app.routers.document.ocr_service.enqueue", enqueue):
            response = await self.client.post(f"/documents/recycle-bin/{doc.id}/restore")
        self.assertEqual(response.status_code, 200, response.text)
        enqueue.assert_awaited_once_with(doc.id)

    async def test_purge_removes_files_and_cascades_highlights(self):
        doc = await self.make_document()
        await self.make_highlight(doc)
        original_key = doc.path.removeprefix("files/download/")

        self.assertEqual((await self.client.delete(f"/documents/{doc.id}")).status_code, 200)
        purged = await self.client.delete(f"/documents/recycle-bin/{doc.id}")
        self.assertEqual(purged.status_code, 200, purged.text)

        self.assertIsNone(await Document.get_or_none(id=doc.id))
        self.assertEqual(await Highlight.all().count(), 0)
        self.assertFalse(get_storage().exists(original_key))
        recycled = (await self.client.get("/documents/recycle-bin")).json()["data"]
        self.assertEqual(recycled["total"], 0)

    async def test_partial_file_staging_failure_restores_already_moved_file(self):
        doc = await self.make_document()
        storage = get_storage()
        derived_key = await storage.save(
            "searchable.pdf", io.BytesIO(b"%PDF-derived"), subdir=f"user/{self.user.id}/ocr"
        )
        doc.ocr_path = "files/download/" + derived_key
        doc.ocr_status = "ready"
        await doc.save(update_fields=["ocr_path", "ocr_status"])
        original_key = doc.path.removeprefix("files/download/")
        await self.client.delete(f"/documents/{doc.id}")

        original_stage = storage.stage
        calls = 0

        def fail_second_stage(key):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated staging failure")
            return original_stage(key)

        with patch.object(storage, "stage", side_effect=fail_second_stage):
            with self.assertRaises(OSError):
                await document_service.delete(doc.id)
        self.assertTrue(await Document.filter(id=doc.id).exists())
        self.assertTrue(storage.exists(original_key))
        self.assertTrue(storage.exists(derived_key))

    async def test_purge_and_restore_require_recycled_state(self):
        doc = await self.make_document()
        self.assertEqual(
            (await self.client.delete(f"/documents/recycle-bin/{doc.id}")).status_code, 409
        )
        self.assertEqual(
            (await self.client.post(f"/documents/recycle-bin/{doc.id}/restore")).status_code, 409
        )
        self.assertIsNotNone(await Document.get_or_none(id=doc.id))

    async def test_purge_rechecks_recycled_state_after_lock(self):
        doc = await self.make_document()
        await self.client.delete(f"/documents/{doc.id}")
        recycled = await Document.get(id=doc.id)
        calls = 0

        async def state_changes_while_waiting(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                recycled.deleted_at = None
            return recycled

        with patch.object(document_service, "get_by_id", side_effect=state_changes_while_waiting):
            with self.assertRaises(CustomException) as caught:
                await document_service.delete(doc.id)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertTrue(get_storage().exists(doc.path.removeprefix("files/download/")))
        self.assertTrue(await Document.filter(id=doc.id).exists())

    async def test_recycle_endpoints_enforce_ownership(self):
        doc = await self.make_document()
        await self.client.delete(f"/documents/{doc.id}")
        self.as_account(self.other)
        self.assertEqual(
            (await self.client.post(f"/documents/recycle-bin/{doc.id}/restore")).status_code, 403
        )
        self.assertEqual(
            (await self.client.delete(f"/documents/recycle-bin/{doc.id}")).status_code, 403
        )
        self.assertEqual(
            (await self.client.get("/documents/recycle-bin")).json()["data"]["total"], 0
        )

    async def test_restore_rejected_when_document_limit_reached(self):
        with patch.object(settings, "USER_DOCUMENT_LIMIT", 1):
            first = await self.make_document(name="第一份.pdf")
            second = await self.make_document(name="第二份.pdf")
            await self.client.delete(f"/documents/{first.id}")
            # 活跃文档已到上限（second），恢复 first 会被拒绝
            rejected = await self.client.post(f"/documents/recycle-bin/{first.id}/restore")
            self.assertEqual(rejected.status_code, 413, rejected.text)
            self.assertIsNotNone((await Document.get(id=first.id)).deleted_at)
            # 腾出名额后恢复成功
            await self.client.delete(f"/documents/{second.id}")
            restored = await self.client.post(f"/documents/recycle-bin/{first.id}/restore")
            self.assertEqual(restored.status_code, 200, restored.text)


if __name__ == "__main__":
    unittest.main()

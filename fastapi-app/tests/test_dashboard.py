import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx
from tortoise import Tortoise

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.dependencies import CurrentAccount, get_current_account
from app.models import (
    Account,
    Document,
    DocumentProcessingTask,
    Note,
    ReadingProgress,
    WebImportJob,
)


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.user = await Account.create(
            username="dashboard-user", name="首页用户", password="unused", role="user"
        )
        self.other = await Account.create(
            username="dashboard-other", name="其他用户", password="unused", role="user"
        )
        self.document = await Document.create(
            name="系统设计.pdf", ext="pdf", size=100,
            path="files/download/user/1/design.pdf", account_id=self.user.id,
        )
        self.recycled = await Document.create(
            name="已删除.pdf", ext="pdf", size=100,
            path="files/download/user/1/deleted.pdf", account_id=self.user.id,
            deleted_at=datetime.now(timezone.utc),
        )
        self.other_document = await Document.create(
            name="其他账号.pdf", ext="pdf", size=100,
            path="files/download/user/2/private.pdf", account_id=self.other.id,
        )
        await Note.create(
            account_id=self.user.id, document_id=self.document.id,
            title="架构笔记", content="聚合首页数据",
        )
        await Note.create(
            account_id=self.other.id, document_id=self.other_document.id,
            title="私有笔记", content="不可见",
        )
        await DocumentProcessingTask.create(
            document_id=self.document.id, task_type="ocr", status="processing", progress=50
        )
        await WebImportJob.create(
            account_id=self.user.id, source_url="https://example.com/article",
            status="pending", progress=0,
        )
        self.app = create_app()
        self.as_account(self.user)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )

    def as_account(self, account):
        self.app.dependency_overrides[get_current_account] = lambda: CurrentAccount(
            account.id, account.role, account
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        await Tortoise.close_connections()

    def anchor(self, document=None, version=None):
        document = document or self.document
        return {
            "protocol": "iknowread.source-anchor/v1",
            "document_id": document.id,
            "document_version": version or document.content_version,
            "source_format": document.ext,
            "scope": "page",
            "page": 4,
            "progression": 0.375,
            "selector": None,
        }

    async def test_progress_roundtrip_and_dashboard_aggregation(self):
        saved = await self.client.put(
            "/reading-progress", json={"source_anchor": self.anchor()}
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["data"]["source_anchor"]["page"], 4)

        loaded = await self.client.get(f"/reading-progress/{self.document.id}")
        self.assertEqual(loaded.status_code, 200, loaded.text)
        self.assertEqual(loaded.json()["data"]["document_version"], self.document.content_version)

        dashboard = await self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        data = dashboard.json()["data"]
        self.assertEqual(data["document_total"], 1)
        self.assertEqual(data["note_total"], 1)
        self.assertEqual(data["processing_total"], 2)
        self.assertEqual([item["id"] for item in data["recent_documents"]], [self.document.id])
        self.assertEqual(data["recent_reading"][0]["document"]["id"], self.document.id)
        self.assertEqual(data["web_imports"][0]["status"], "pending")

    async def test_progress_rejects_stale_and_foreign_documents(self):
        stale = await self.client.put(
            "/reading-progress",
            json={"source_anchor": self.anchor(version="a" * 32)},
        )
        self.assertEqual(stale.status_code, 409, stale.text)

        foreign = await self.client.put(
            "/reading-progress", json={"source_anchor": self.anchor(self.other_document)}
        )
        self.assertEqual(foreign.status_code, 404, foreign.text)
        self.assertEqual(await ReadingProgress.all().count(), 0)

    async def test_recycled_progress_is_hidden_and_hard_delete_cascades(self):
        await self.client.put("/reading-progress", json={"source_anchor": self.anchor()})
        self.document.deleted_at = datetime.now(timezone.utc)
        await self.document.save(update_fields=["deleted_at"])

        self.assertEqual(
            (await self.client.get(f"/reading-progress/{self.document.id}")).status_code,
            404,
        )
        dashboard = (await self.client.get("/dashboard")).json()["data"]
        self.assertEqual(dashboard["recent_reading"], [])
        self.assertEqual(dashboard["document_total"], 0)
        self.assertEqual(await ReadingProgress.all().count(), 1)

        await self.document.delete()
        self.assertEqual(await ReadingProgress.all().count(), 0)

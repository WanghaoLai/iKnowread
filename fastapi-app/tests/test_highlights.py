"""隔离 SQLite，验证持久化高亮、版本边界和账号隔离。"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from tortoise import Tortoise

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.config import settings
from app.dependencies import CurrentAccount, get_current_account
from app.models import Account, Document, Highlight


class HighlightTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.user = await Account.create(
            username="highlight-user", name="高亮用户", password="unused", role="user"
        )
        self.other = await Account.create(
            username="highlight-other", name="其他用户", password="unused", role="user"
        )
        self.document = await Document.create(
            name="可高亮文档.pdf", ext="pdf", size=100,
            path="files/download/user/1/highlight.pdf", account_id=self.user.id,
        )
        self.other_document = await Document.create(
            name="其他文档.pdf", ext="pdf", size=100,
            path="files/download/user/2/highlight.pdf", account_id=self.other.id,
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

    def anchor(self, *, document=None, version=None, source_format="pdf"):
        document = document or self.document
        return {
            "protocol": "iknowread.source-anchor/v1",
            "document_id": document.id,
            "document_version": version or document.content_version,
            "source_format": source_format,
            "scope": "page" if source_format == "pdf" else "document",
            "page": 2 if source_format == "pdf" else None,
            "progression": 0.25,
            "selector": {
                "position": {"start": 10, "end": 15},
                "quote": {"exact": "关键内容", "prefix": "这里是", "suffix": "需要理解"},
            },
        }

    async def create_highlight(self, **overrides):
        payload = {
            "document_id": self.document.id,
            "source_anchor": self.anchor(),
            "selected_text": "关键内容",
            "remark": "AI 对关键内容的解释",
            "provider": "deepseek",
            "config_name": "阅读模型",
            "model": "deepseek-chat",
        }
        payload.update(overrides)
        return await self.client.post("/highlights", json=payload)

    async def asyncTearDown(self):
        await self.client.aclose()
        await Tortoise.close_connections()

    async def test_create_list_update_and_delete(self):
        created_response = await self.create_highlight()
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()["data"]
        self.assertEqual(created["document_version"], self.document.content_version)
        self.assertEqual(created["source_anchor"]["page"], 2)
        self.assertEqual(created["remark"], "AI 对关键内容的解释")

        listed = await self.client.get("/highlights", params={
            "documentId": self.document.id,
            "documentVersion": self.document.content_version,
        })
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual([item["id"] for item in listed.json()["data"]], [created["id"]])

        updated = await self.client.put(
            f"/highlights/{created['id']}", json={"remark": "修改后的个人理解"}
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["data"]["remark"], "修改后的个人理解")

        deleted = await self.client.delete(f"/highlights/{created['id']}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(await Highlight.all().count(), 0)

    async def test_duplicate_anchor_is_rejected(self):
        self.assertEqual((await self.create_highlight()).status_code, 200)
        same_anchor = self.anchor()
        same_anchor["progression"] = 0.8
        duplicate = await self.create_highlight(
            remark="另一个备注", source_anchor=same_anchor
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertIn("已经高亮", duplicate.text)
        self.assertEqual(await Highlight.all().count(), 1)

    async def test_highlight_creation_and_listing_are_bounded(self):
        with (
            patch.object(settings, "USER_HIGHLIGHT_LIMIT", 10),
            patch.object(settings, "DOCUMENT_HIGHLIGHT_LIMIT", 1),
        ):
            self.assertEqual((await self.create_highlight()).status_code, 200)
            second_anchor = self.anchor()
            second_anchor["selector"]["position"] = {"start": 20, "end": 25}
            second_anchor["selector"]["quote"]["prefix"] = "不同位置"
            rejected = await self.create_highlight(source_anchor=second_anchor)
            listed = await self.client.get("/highlights", params={
                "documentId": self.document.id,
                "documentVersion": self.document.content_version,
            })
        self.assertEqual(rejected.status_code, 413, rejected.text)
        self.assertEqual(len(listed.json()["data"]), 1)

    async def test_stale_or_mismatched_anchor_is_rejected(self):
        old_version = self.document.content_version
        self.document.content_version = "e" * 32
        await self.document.save(update_fields=["content_version"])

        stale = await self.create_highlight(source_anchor=self.anchor(version=old_version))
        self.assertEqual(stale.status_code, 409, stale.text)
        wrong_document = await self.create_highlight(
            source_anchor=self.anchor(document=self.other_document, version=self.document.content_version)
        )
        self.assertEqual(wrong_document.status_code, 409, wrong_document.text)
        wrong_format = await self.create_highlight(
            source_anchor=self.anchor(version=self.document.content_version, source_format="docx")
        )
        self.assertEqual(wrong_format.status_code, 409, wrong_format.text)

        stale_list = await self.client.get("/highlights", params={
            "documentId": self.document.id, "documentVersion": old_version,
        })
        self.assertEqual(stale_list.status_code, 409, stale_list.text)
        self.assertEqual(await Highlight.all().count(), 0)

    async def test_account_isolation_and_document_cascade(self):
        created = (await self.create_highlight()).json()["data"]
        self.as_account(self.other)
        forbidden_list = await self.client.get("/highlights", params={
            "documentId": self.document.id,
            "documentVersion": self.document.content_version,
        })
        self.assertEqual(forbidden_list.status_code, 403, forbidden_list.text)
        self.assertEqual(
            (await self.client.put(f"/highlights/{created['id']}", json={"remark": "越权"})).status_code,
            404,
        )
        self.assertEqual((await self.client.delete(f"/highlights/{created['id']}")).status_code, 404)

        self.as_account(self.user)
        await self.document.delete()
        self.assertEqual(await Highlight.all().count(), 0)

    async def test_validation_and_authentication(self):
        no_selector = await self.create_highlight(
            source_anchor={**self.anchor(), "selector": None}
        )
        self.assertEqual(no_selector.status_code, 422, no_selector.text)
        too_long = await self.create_highlight(remark="a" * 12001)
        self.assertEqual(too_long.status_code, 422, too_long.text)
        mismatched_text = await self.create_highlight(selected_text="篡改后的文字")
        self.assertEqual(mismatched_text.status_code, 422, mismatched_text.text)

        self.app.dependency_overrides.clear()
        for method, path, body in [
            ("GET", "/highlights", None),
            ("POST", "/highlights", {}),
            ("PUT", "/highlights/1", {"remark": ""}),
            ("DELETE", "/highlights/1", None),
        ]:
            params = (
                {"documentId": self.document.id, "documentVersion": self.document.content_version}
                if method == "GET" else None
            )
            response = await self.client.request(method, path, json=body, params=params)
            self.assertEqual(response.status_code, 401, response.text)


if __name__ == "__main__":
    unittest.main()

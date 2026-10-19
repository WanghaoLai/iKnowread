"""隔离 SQLite，验证笔记生命周期、账号隔离、文档快照与导出。"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
from tortoise import Tortoise

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.config import settings
from app.dependencies import CurrentAccount, get_current_account
from app.models import Account, Document, Note


class NoteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.user = await Account.create(
            username="note-user", name="笔记用户", password="unused", role="user"
        )
        self.other = await Account.create(
            username="note-other", name="其他用户", password="unused", role="user"
        )
        self.document = await Document.create(
            name="第一性原理.pdf", ext="pdf", size=100,
            path="files/download/user/1/book.pdf", account_id=self.user.id,
        )
        self.other_document = await Document.create(
            name="私有资料.pdf", ext="pdf", size=100,
            path="files/download/user/2/private.pdf", account_id=self.other.id,
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

    async def create_ai_note(self, *, remark="我的理解"):
        anchor = {
            "protocol": "iknowread.source-anchor/v1",
            "document_id": self.document.id,
            "document_version": self.document.content_version,
            "source_format": "pdf",
            "scope": "page",
            "page": 3,
            "progression": 0.25,
            "selector": {
                "position": {"start": 12, "end": 17},
                "quote": {"exact": "第一性原理", "prefix": "理解", "suffix": "需要"},
            },
        }
        response = await self.client.post("/notes", json={
            "source_type": "ai_explanation",
            "document_id": self.document.id,
            "document_version": self.document.content_version,
            "source_anchor": anchor,
            "selected_text": "第一性原理",
            "content": "从最基本、不可再分的事实开始推导。",
            "remark": remark,
            "provider": "deepseek",
            "config_name": "学习模型",
            "model": "deepseek-chat",
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    async def test_ai_note_keeps_document_snapshot_after_document_deleted(self):
        created = await self.create_ai_note()
        self.assertEqual(created["document_name"], "第一性原理.pdf")
        self.assertEqual(created["document_version"], self.document.content_version)
        self.assertEqual(created["document_status"], "available")
        self.assertEqual(created["source_anchor"]["page"], 3)
        self.assertEqual(created["title"], "第一性原理")
        self.assertEqual(created["remark"], "我的理解")

        await self.document.delete()
        note = await Note.get(id=created["id"])
        self.assertIsNone(note.document_id)
        self.assertEqual(note.document_name, "第一性原理.pdf")
        listed = (await self.client.get("/notes")).json()["data"]["list"]
        self.assertEqual(listed[0]["document_name"], "第一性原理.pdf")
        self.assertEqual(listed[0]["document_status"], "deleted")

    async def test_note_reports_recycled_document_status(self):
        created = await self.create_ai_note()
        self.document.deleted_at = datetime.now(timezone.utc)
        await self.document.save(update_fields=["deleted_at"])

        listed = (await self.client.get("/notes")).json()["data"]["list"]
        self.assertEqual(listed[0]["id"], created["id"])
        self.assertEqual(listed[0]["document_status"], "recycled")

    async def test_anchor_text_mismatch_is_rejected(self):
        anchor = {
            "protocol": "iknowread.source-anchor/v1",
            "document_id": self.document.id,
            "document_version": self.document.content_version,
            "source_format": "pdf",
            "scope": "page",
            "page": 1,
            "progression": 0,
            "selector": {
                "position": {"start": 0, "end": 5},
                "quote": {"exact": "原始文字", "prefix": "", "suffix": ""},
            },
        }
        response = await self.client.post("/notes", json={
            "source_type": "ai_explanation",
            "document_id": self.document.id,
            "document_version": self.document.content_version,
            "source_anchor": anchor,
            "selected_text": "篡改文字",
            "content": "不应保存",
        })
        self.assertEqual(response.status_code, 422, response.text)

    async def test_deleted_document_notes_filter_by_original_name(self):
        await self.create_ai_note()
        second = await Document.create(
            name="第二本书.pdf", ext="pdf", size=100,
            path="files/download/user/1/second.pdf", account_id=self.user.id,
        )
        response = await self.client.post("/notes", json={
            "source_type": "manual", "document_id": second.id,
            "title": "第二本笔记", "content": "另一些内容。",
        })
        self.assertEqual(response.status_code, 200, response.text)
        await self.document.delete()
        await second.delete()

        summary = (await self.client.get("/notes/summary")).json()["data"]
        self.assertEqual(summary["total"], 2)
        names = {item["document_name"]: item["count"] for item in summary["documents"]}
        self.assertEqual(names, {"第一性原理.pdf": 1, "第二本书.pdf": 1})

        by_name = (await self.client.get(
            "/notes", params={"documentName": "第一性原理.pdf"}
        )).json()["data"]
        self.assertEqual(by_name["total"], 1)
        self.assertEqual(by_name["list"][0]["document_name"], "第一性原理.pdf")

        unlinked = (await self.client.get("/notes", params={"unlinked": True})).json()["data"]
        self.assertEqual(unlinked["total"], 0)

    async def test_manual_update_delete_and_summary(self):
        response = await self.client.post("/notes", json={
            "source_type": "manual",
            "document_id": self.document.id,
            "title": "读后思考",
            "content": "先拆解假设，再验证事实。",
        })
        self.assertEqual(response.status_code, 200, response.text)
        manual = response.json()["data"]
        note_id = manual["id"]
        self.assertEqual(manual["document_version"], self.document.content_version)
        self.assertEqual(manual["document_status"], "available")

        updated = await self.client.put(f"/notes/{note_id}", json={
            "title": "更新后的思考", "remark": "需要实践验证"
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["data"]["remark"], "需要实践验证")

        invalid_update = await self.client.put(
            f"/notes/{note_id}", json={"remark": None}
        )
        self.assertEqual(invalid_update.status_code, 422, invalid_update.text)

        summary = (await self.client.get("/notes/summary")).json()["data"]
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["documents"][0]["count"], 1)
        self.assertEqual((await self.client.delete(f"/notes/{note_id}")).status_code, 200)
        self.assertEqual(await Note.all().count(), 0)

    async def test_note_creation_respects_account_limit(self):
        payload = {"source_type": "manual", "title": "边界", "content": "内容"}
        with patch.object(settings, "USER_NOTE_LIMIT", 1):
            self.assertEqual((await self.client.post("/notes", json=payload)).status_code, 200)
            rejected = await self.client.post("/notes", json=payload)
        self.assertEqual(rejected.status_code, 413, rejected.text)
        self.assertEqual(await Note.filter(account_id=self.user.id).count(), 1)

    async def test_search_sort_and_markdown_export(self):
        ai_note = await self.create_ai_note(remark="重点复习")
        manual_response = await self.client.post("/notes", json={
            "source_type": "manual", "title": "无关联笔记",
            "content": "刻意练习与即时反馈。",
        })
        self.assertEqual(manual_response.status_code, 200, manual_response.text)
        manual_note = manual_response.json()["data"]
        filtered = await self.client.get("/notes", params={"keyword": "复习"})
        self.assertEqual(filtered.json()["data"]["total"], 1)
        grouped = await self.client.get("/notes", params={"sort": "document"})
        self.assertEqual(grouped.status_code, 200)
        unlinked = await self.client.get("/notes", params={"unlinked": True})
        self.assertEqual(unlinked.json()["data"]["total"], 1)
        self.assertEqual(unlinked.json()["data"]["list"][0]["document_status"], "unlinked")

        exported = await self.client.get("/notes/export", params={"sort": "document"})
        self.assertEqual(exported.status_code, 200)
        text = exported.content.decode("utf-8-sig")
        self.assertIn("# 我的笔记", text)
        self.assertIn("## 第一性原理.pdf", text)
        self.assertIn("第一性原理", text)
        self.assertIn("重点复习", text)
        self.assertIn(f"文档版本：{self.document.content_version}", text)
        self.assertIn("原文定位：第 3 页（iknowread.source-anchor/v1）", text)
        self.assertIn("attachment", exported.headers["content-disposition"])

        by_document = await self.client.post("/notes/export", json={
            "scope": "document", "document_id": self.document.id,
        })
        self.assertEqual(by_document.status_code, 200, by_document.text)
        document_text = by_document.content.decode("utf-8-sig")
        self.assertIn(ai_note["title"], document_text)
        self.assertNotIn("刻意练习", document_text)

        selected = await self.client.post("/notes/export", json={
            "scope": "selected", "note_ids": [manual_note["id"]],
        })
        self.assertEqual(selected.status_code, 200, selected.text)
        selected_text = selected.content.decode("utf-8-sig")
        self.assertIn("刻意练习", selected_text)
        self.assertNotIn("从最基本、不可再分的事实开始推导", selected_text)

        all_notes = await self.client.post("/notes/export", json={"scope": "all"})
        self.assertEqual(all_notes.status_code, 200, all_notes.text)
        all_text = all_notes.content.decode("utf-8-sig")
        self.assertIn("刻意练习", all_text)
        self.assertIn("从最基本、不可再分的事实开始推导", all_text)

        invalid_selected = await self.client.post("/notes/export", json={
            "scope": "selected", "note_ids": [],
        })
        self.assertEqual(invalid_selected.status_code, 422, invalid_selected.text)

        invalid_document = await self.client.post("/notes/export", json={
            "scope": "document",
        })
        self.assertEqual(invalid_document.status_code, 422, invalid_document.text)

    async def test_account_and_document_isolation(self):
        created = await self.create_ai_note()
        forbidden = await self.client.post("/notes", json={
            "source_type": "ai_explanation",
            "document_id": self.other_document.id,
            "document_version": self.other_document.content_version,
            "source_anchor": {
                "protocol": "iknowread.source-anchor/v1",
                "document_id": self.other_document.id,
                "document_version": self.other_document.content_version,
                "source_format": "pdf", "scope": "page", "page": 1,
                "progression": 0, "selector": {
                    "position": {"start": 0, "end": 2},
                    "quote": {"exact": "秘密", "prefix": "", "suffix": ""},
                },
            },
            "selected_text": "秘密",
            "content": "不应保存",
        })
        self.assertEqual(forbidden.status_code, 403)

        self.as_account(self.other)
        self.assertEqual((await self.client.get("/notes")).json()["data"]["total"], 0)
        self.assertEqual((await self.client.put(f"/notes/{created['id']}", json={"remark": "越权"})).status_code, 404)
        self.assertEqual((await self.client.delete(f"/notes/{created['id']}")).status_code, 404)
        forbidden_export = await self.client.post("/notes/export", json={
            "scope": "selected", "note_ids": [created["id"]],
        })
        self.assertEqual(forbidden_export.status_code, 409, forbidden_export.text)

    async def test_ai_note_rejects_stale_document_version(self):
        old_version = self.document.content_version
        self.document.content_version = "f" * 32
        await self.document.save(update_fields=["content_version"])
        response = await self.client.post("/notes", json={
            "source_type": "ai_explanation",
            "document_id": self.document.id,
            "document_version": old_version,
            "source_anchor": {
                "protocol": "iknowread.source-anchor/v1",
                "document_id": self.document.id,
                "document_version": old_version,
                "source_format": "pdf", "scope": "page", "page": 1,
                "progression": 0, "selector": {
                    "position": {"start": 0, "end": 3},
                    "quote": {"exact": "旧位置", "prefix": "", "suffix": ""},
                },
            },
            "selected_text": "旧位置",
            "content": "旧解释",
        })
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("文档内容已更新", response.text)
        self.assertEqual(await Note.all().count(), 0)

    async def test_note_rejects_anchor_for_another_document(self):
        response = await self.client.post("/notes", json={
            "source_type": "ai_explanation",
            "document_id": self.document.id,
            "document_version": self.document.content_version,
            "source_anchor": {
                "protocol": "iknowread.source-anchor/v1",
                "document_id": self.other_document.id,
                "document_version": self.document.content_version,
                "source_format": "pdf", "scope": "page", "page": 1,
                "progression": 0, "selector": {
                    "position": {"start": 0, "end": 2},
                    "quote": {"exact": "原文", "prefix": "", "suffix": ""},
                },
            },
            "selected_text": "原文",
            "content": "解释",
        })
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("原文定位", response.text)

    async def test_authentication_and_validation(self):
        invalid = await self.client.post("/notes", json={
            "source_type": "ai_explanation", "content": "缺少选文和文档"
        })
        self.assertEqual(invalid.status_code, 422)
        self.app.dependency_overrides.clear()
        for method, path in [
            ("GET", "/notes"), ("GET", "/notes/summary"),
            ("GET", "/notes/export"), ("POST", "/notes/export"), ("POST", "/notes"),
            ("PUT", "/notes/1"), ("DELETE", "/notes/1"),
        ]:
            response = await self.client.request(method, path, json={} if method in {"POST", "PUT"} else None)
            self.assertEqual(response.status_code, 401, response.text)


if __name__ == "__main__":
    unittest.main()

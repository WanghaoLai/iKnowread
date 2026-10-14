"""隔离 SQLite，验证笔记生命周期、账号隔离、文档快照与导出。"""
import sys
import unittest
from pathlib import Path

import httpx
from tortoise import Tortoise

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
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
        response = await self.client.post("/notes", json={
            "source_type": "ai_explanation",
            "document_id": self.document.id,
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
        self.assertEqual(created["title"], "第一性原理")
        self.assertEqual(created["remark"], "我的理解")

        await self.document.delete()
        note = await Note.get(id=created["id"])
        self.assertIsNone(note.document_id)
        self.assertEqual(note.document_name, "第一性原理.pdf")
        listed = (await self.client.get("/notes")).json()["data"]["list"]
        self.assertEqual(listed[0]["document_name"], "第一性原理.pdf")

    async def test_manual_update_delete_and_summary(self):
        response = await self.client.post("/notes", json={
            "source_type": "manual",
            "document_id": self.document.id,
            "title": "读后思考",
            "content": "先拆解假设，再验证事实。",
        })
        self.assertEqual(response.status_code, 200, response.text)
        note_id = response.json()["data"]["id"]

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

    async def test_search_sort_and_markdown_export(self):
        await self.create_ai_note(remark="重点复习")
        await self.client.post("/notes", json={
            "source_type": "manual", "title": "无关联笔记",
            "content": "刻意练习与即时反馈。",
        })
        filtered = await self.client.get("/notes", params={"keyword": "复习"})
        self.assertEqual(filtered.json()["data"]["total"], 1)
        grouped = await self.client.get("/notes", params={"sort": "document"})
        self.assertEqual(grouped.status_code, 200)
        unlinked = await self.client.get("/notes", params={"unlinked": True})
        self.assertEqual(unlinked.json()["data"]["total"], 1)

        exported = await self.client.get("/notes/export", params={"sort": "document"})
        self.assertEqual(exported.status_code, 200)
        text = exported.content.decode("utf-8-sig")
        self.assertIn("# 我的笔记", text)
        self.assertIn("## 第一性原理.pdf", text)
        self.assertIn("第一性原理", text)
        self.assertIn("重点复习", text)
        self.assertIn("attachment", exported.headers["content-disposition"])

    async def test_account_and_document_isolation(self):
        created = await self.create_ai_note()
        forbidden = await self.client.post("/notes", json={
            "source_type": "ai_explanation",
            "document_id": self.other_document.id,
            "selected_text": "秘密",
            "content": "不应保存",
        })
        self.assertEqual(forbidden.status_code, 403)

        self.as_account(self.other)
        self.assertEqual((await self.client.get("/notes")).json()["data"]["total"], 0)
        self.assertEqual((await self.client.put(f"/notes/{created['id']}", json={"remark": "越权"})).status_code, 404)
        self.assertEqual((await self.client.delete(f"/notes/{created['id']}")).status_code, 404)

    async def test_authentication_and_validation(self):
        invalid = await self.client.post("/notes", json={
            "source_type": "ai_explanation", "content": "缺少选文和文档"
        })
        self.assertEqual(invalid.status_code, 422)
        self.app.dependency_overrides.clear()
        for method, path in [
            ("GET", "/notes"), ("GET", "/notes/summary"),
            ("GET", "/notes/export"), ("POST", "/notes"),
            ("PUT", "/notes/1"), ("DELETE", "/notes/1"),
        ]:
            response = await self.client.request(method, path, json={} if method in {"POST", "PUT"} else None)
            self.assertEqual(response.status_code, 401, response.text)


if __name__ == "__main__":
    unittest.main()

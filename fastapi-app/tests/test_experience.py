import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException
from tortoise import Tortoise

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.dependencies import CurrentAccount, get_current_account
from app.models import (
    AIConfig,
    Account,
    Document,
    ExperienceDocumentShare,
    ExperiencePolicy,
    Highlight,
    Note,
)
from app.services import experience_service


class ExperienceAccountTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.admin = await Account.create(
            username="admin", name="管理员", password="admin-hash", role="admin"
        )
        self.other_admin = await Account.create(
            username="other-admin", name="其他管理员", password="hash", role="admin"
        )
        self.experience = await Account.create(
            username="test", name="在线体验", password="test-hash", role="user",
            is_experience=True,
        )
        self.regular = await Account.create(
            username="regular", name="普通用户", password="hash", role="user"
        )
        self.config = await AIConfig.create(
            account_id=self.admin.id,
            provider="deepseek",
            name="体验模型",
            base_url="https://api.example.com",
            model="example-model",
            encrypted_api_key="encrypted",
            is_active=True,
        )
        self.policy = await ExperiencePolicy.create(
            account_id=self.experience.id,
            enabled=True,
            public_password="test1234",
            ai_config_id=self.config.id,
            daily_ai_limit=2,
            show_highlights=True,
            show_notes=True,
        )
        self.shared = await Document.create(
            name="共享.pdf", ext="pdf", size=100,
            path="files/download/admin/1/shared.pdf", account_id=self.admin.id,
        )
        self.private = await Document.create(
            name="未共享.pdf", ext="pdf", size=100,
            path="files/download/admin/1/private.pdf", account_id=self.admin.id,
        )
        self.other_admin_document = await Document.create(
            name="其他管理员.pdf", ext="pdf", size=100,
            path="files/download/admin/2/other.pdf", account_id=self.other_admin.id,
        )
        self.user_document = await Document.create(
            name="普通用户.pdf", ext="pdf", size=100,
            path="files/download/user/4/user.pdf", account_id=self.regular.id,
        )
        await ExperienceDocumentShare.create(
            account_id=self.experience.id,
            document_id=self.shared.id,
            shared_by_id=self.admin.id,
        )
        self.anchor = {
            "protocol": "iknowread.source-anchor/v1",
            "document_id": self.shared.id,
            "document_version": self.shared.content_version,
            "source_format": "pdf",
            "scope": "page",
            "page": 1,
            "progression": 0.2,
            "selector": {
                "position": {"start": 0, "end": 4},
                "quote": {"exact": "共享内容", "prefix": "", "suffix": ""},
            },
        }
        self.highlight = await Highlight.create(
            account_id=self.admin.id,
            document_id=self.shared.id,
            document_version=self.shared.content_version,
            anchor_key="a" * 64,
            source_anchor=self.anchor,
            selected_text="共享内容",
            remark="管理员高亮",
        )
        self.note = await Note.create(
            account_id=self.admin.id,
            document_id=self.shared.id,
            document_name=self.shared.name,
            document_version=self.shared.content_version,
            source_anchor=self.anchor,
            source_type="manual",
            title="管理员笔记",
            selected_text="共享内容",
            content="只读笔记内容",
        )
        self.app = create_app()
        self.as_account(self.experience)
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

    async def test_capability_and_session_policy_are_explicit(self):
        capability = await self.client.get("/capabilities")
        self.assertEqual(capability.status_code, 200, capability.text)
        self.assertEqual(capability.json()["data"]["experience_account"], {
            "enabled": True, "username": "test", "password": "test1234",
        })
        session = await self.client.get("/experience/me")
        self.assertEqual(session.status_code, 200, session.text)
        data = session.json()["data"]
        self.assertTrue(data["is_experience"])
        self.assertEqual(data["document_upload_limit"], 0)
        self.assertEqual(data["storage_quota_bytes"], 0)
        self.assertEqual(data["ai_remaining_today"], 2)

    async def test_document_list_contains_only_explicit_admin_shares(self):
        response = await self.client.get("/documents", params={"pageNum": 1, "pageSize": 20})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["total"], 1)
        item = response.json()["data"]["list"][0]
        self.assertEqual(item["id"], self.shared.id)
        self.assertTrue(item["read_only"])

        for document in (self.private, self.other_admin_document, self.user_document):
            denied = await self.client.get(f"/documents/{document.id}/download")
            self.assertEqual(denied.status_code, 403, denied.text)

    async def test_shared_highlights_and_notes_are_read_only(self):
        highlights = await self.client.get("/highlights", params={
            "documentId": self.shared.id,
            "documentVersion": self.shared.content_version,
        })
        self.assertEqual(highlights.status_code, 200, highlights.text)
        self.assertEqual(highlights.json()["data"][0]["remark"], "管理员高亮")
        self.assertTrue(highlights.json()["data"][0]["read_only"])

        notes = await self.client.get("/notes")
        self.assertEqual(notes.status_code, 200, notes.text)
        self.assertEqual(notes.json()["data"]["list"][0]["title"], "管理员笔记")
        self.assertTrue(notes.json()["data"]["list"][0]["read_only"])

        create_highlight = await self.client.post("/highlights", json={
            "document_id": self.shared.id,
            "source_anchor": self.anchor,
            "selected_text": "共享内容",
            "remark": "越权写入",
        })
        self.assertEqual(create_highlight.status_code, 403, create_highlight.text)
        self.assertEqual(
            (await self.client.put(
                f"/highlights/{self.highlight.id}", json={"remark": "越权"}
            )).status_code,
            403,
        )
        self.assertEqual(
            (await self.client.delete(f"/notes/{self.note.id}")).status_code, 403
        )
        self.assertEqual(
            (await self.client.post("/notes", json={
                "source_type": "manual", "title": "越权", "content": "越权",
            })).status_code,
            403,
        )

    async def test_all_resource_mutations_are_denied(self):
        self.assertEqual(
            (await self.client.post("/web-imports", json={"url": "https://example.com"})).status_code,
            403,
        )
        self.assertEqual(
            (await self.client.delete(f"/documents/{self.shared.id}")).status_code,
            403,
        )
        self.assertEqual(
            (await self.client.put("/password", json={
                "password": "test1234", "newPassword": "different-password",
            })).status_code,
            403,
        )
        self.assertEqual((await self.client.get("/ai/configs")).status_code, 403)
        self.assertEqual((await self.client.post("/ai/chat", json={"messages": [
            {"role": "user", "content": "hello"},
        ]})).status_code, 403)

    async def test_ai_quota_is_server_enforced(self):
        current = CurrentAccount(self.experience.id, self.experience.role, self.experience)
        self.assertEqual((await experience_service.consume_ai_quota(current)).id, self.config.id)
        self.assertEqual((await experience_service.consume_ai_quota(current)).id, self.config.id)
        with self.assertRaises(HTTPException) as raised:
            await experience_service.consume_ai_quota(current)
        self.assertEqual(raised.exception.status_code, 429)
        refreshed = await ExperiencePolicy.get(id=self.policy.id)
        self.assertEqual(refreshed.ai_used_today, 2)

    async def test_admin_can_manage_only_owned_documents_and_ai_config(self):
        other_share = await ExperienceDocumentShare.create(
            account_id=self.experience.id,
            document_id=self.other_admin_document.id,
            shared_by_id=self.other_admin.id,
        )
        self.as_account(self.admin)
        loaded = await self.client.get("/admin/experience")
        self.assertEqual(loaded.status_code, 200, loaded.text)
        self.assertEqual(loaded.json()["data"]["document_ids"], [self.shared.id])
        self.assertEqual(loaded.json()["data"]["ai_config_id"], self.config.id)

        invalid = await self.client.put("/admin/experience", json={
            "enabled": True,
            "public_password": "test1234",
            "ai_config_id": self.config.id,
            "daily_ai_limit": 3,
            "show_highlights": True,
            "show_notes": True,
            "document_ids": [self.other_admin_document.id],
        })
        self.assertEqual(invalid.status_code, 400, invalid.text)

        with patch(
            "app.services.experience_service.password_work",
            new=AsyncMock(return_value="new-password-hash"),
        ):
            updated = await self.client.put("/admin/experience", json={
                "enabled": True,
                "public_password": "newpass123",
                "ai_config_id": self.config.id,
                "daily_ai_limit": 3,
                "show_highlights": False,
                "show_notes": False,
                "document_ids": [self.private.id],
            })
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["data"]["document_ids"], [self.private.id])
        refreshed_account = await Account.get(id=self.experience.id)
        self.assertEqual(refreshed_account.password, "new-password-hash")
        self.assertEqual(refreshed_account.session_version, 2)
        self.assertTrue(await ExperienceDocumentShare.filter(id=other_share.id).exists())


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path

import httpx
from tortoise import Tortoise

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.dependencies import CurrentAccount, get_current_account
from app.models import Account, Announcement, AnnouncementRead


class AnnouncementTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.admin = await Account.create(
            username="notice-admin", name="公告管理员", password="unused", role="admin"
        )
        self.user = await Account.create(
            username="notice-user", name="公告用户", password="unused", role="user"
        )
        self.other = await Account.create(
            username="notice-other", name="其他用户", password="unused", role="user"
        )
        self.app = create_app()
        self.as_account(self.admin)
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

    async def create(self, title="系统维护通知", status="draft"):
        response = await self.client.post("/admin/announcements", json={
            "title": title,
            "content": "## 公告内容\n\n请及时保存工作。",
            "status": status,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    async def test_admin_crud_filter_and_user_visibility(self):
        draft = await self.create("草稿公告")
        published = await self.create("已发布公告", "published")
        self.assertEqual(draft["published_revision"], 0)
        self.assertEqual(published["published_revision"], 1)
        self.assertEqual(published["created_by_name"], "公告管理员")

        filtered = await self.client.get(
            "/admin/announcements",
            params={"keyword": "发布", "status": "published", "pageNum": 1, "pageSize": 10},
        )
        self.assertEqual(filtered.status_code, 200, filtered.text)
        self.assertEqual(filtered.json()["data"]["total"], 1)
        self.assertEqual(filtered.json()["data"]["list"][0]["id"], published["id"])

        self.as_account(self.user)
        visible = (await self.client.get("/announcements")).json()["data"]
        self.assertEqual(visible["total"], 1)
        self.assertEqual(visible["unread_count"], 1)
        self.assertEqual(visible["list"][0]["id"], published["id"])
        self.assertFalse(visible["list"][0]["is_read"])

        forbidden = await self.client.get("/admin/announcements")
        self.assertEqual(forbidden.status_code, 403, forbidden.text)

    async def test_read_state_is_per_account_and_tracks_published_revision(self):
        item = await self.create(status="published")
        self.as_account(self.user)
        marked = await self.client.put(f"/announcements/{item['id']}/read")
        self.assertEqual(marked.status_code, 200, marked.text)
        self.assertEqual(marked.json()["data"]["read_revision"], 1)
        mine = (await self.client.get("/announcements")).json()["data"]
        self.assertEqual(mine["unread_count"], 0)
        self.assertTrue(mine["list"][0]["is_read"])

        self.as_account(self.other)
        theirs = (await self.client.get("/announcements")).json()["data"]
        self.assertEqual(theirs["unread_count"], 1)
        self.assertFalse(theirs["list"][0]["is_read"])

        self.as_account(self.admin)
        updated = await self.client.put(f"/admin/announcements/{item['id']}", json={
            "title": "更新后的系统维护通知",
            "content": "## 新内容\n\n维护时间已经调整。",
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["data"]["published_revision"], 2)

        self.as_account(self.user)
        refreshed = (await self.client.get("/announcements")).json()["data"]
        self.assertEqual(refreshed["unread_count"], 1)
        self.assertFalse(refreshed["list"][0]["is_read"])

    async def test_offline_republish_read_all_and_delete_cascade(self):
        first = await self.create("第一条", "published")
        second = await self.create("第二条", "published")
        self.as_account(self.user)
        read_all = await self.client.put("/announcements/read-all")
        self.assertEqual(read_all.status_code, 200, read_all.text)
        self.assertEqual(read_all.json()["data"]["unread_count"], 0)
        self.assertEqual(await AnnouncementRead.filter(account_id=self.user.id).count(), 2)

        self.as_account(self.admin)
        offline = await self.client.patch(
            f"/admin/announcements/{first['id']}/status", json={"status": "offline"}
        )
        self.assertEqual(offline.status_code, 200, offline.text)
        republished = await self.client.patch(
            f"/admin/announcements/{first['id']}/status", json={"status": "published"}
        )
        self.assertEqual(republished.status_code, 200, republished.text)
        self.assertEqual(republished.json()["data"]["published_revision"], 2)

        self.as_account(self.user)
        page = (await self.client.get(
            "/announcements", params={"pageNum": 1, "pageSize": 1}
        )).json()["data"]
        self.assertEqual(page["total"], 2)
        self.assertEqual(len(page["list"]), 1)
        self.assertEqual(page["list"][0]["id"], first["id"])
        self.assertEqual(page["unread_count"], 1)

        self.as_account(self.admin)
        deleted = await self.client.delete(f"/admin/announcements/{second['id']}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertFalse(await Announcement.filter(id=second["id"]).exists())
        self.assertFalse(await AnnouncementRead.filter(announcement_id=second["id"]).exists())

    async def test_validation_and_missing_or_offline_read(self):
        invalid = await self.client.post("/admin/announcements", json={
            "title": "  ", "content": "内容", "status": "draft",
        })
        self.assertEqual(invalid.status_code, 422, invalid.text)
        offline = await self.create(status="draft")
        self.as_account(self.user)
        response = await self.client.put(f"/announcements/{offline['id']}/read")
        self.assertEqual(response.status_code, 404, response.text)

    async def test_user_pagination_and_unread_statistics_stay_global(self):
        published = [
            await self.create(f"分页公告 {number}", "published")
            for number in range(6)
        ]
        await self.create("不可见草稿", "draft")
        self.as_account(self.user)
        for item in published[:2]:
            response = await self.client.put(f"/announcements/{item['id']}/read")
            self.assertEqual(response.status_code, 200, response.text)

        response = await self.client.get(
            "/announcements", params={"pageNum": 2, "pageSize": 2}
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["total"], 6)
        self.assertEqual(data["unread_count"], 4)
        self.assertEqual(len(data["list"]), 2)

        republished = published[0]
        self.as_account(self.admin)
        await self.client.patch(
            f"/admin/announcements/{republished['id']}/status",
            json={"status": "offline"},
        )
        await self.client.patch(
            f"/admin/announcements/{republished['id']}/status",
            json={"status": "published"},
        )
        self.as_account(self.user)
        refreshed = (await self.client.get("/announcements")).json()["data"]
        self.assertEqual(refreshed["total"], 6)
        self.assertEqual(refreshed["unread_count"], 5)

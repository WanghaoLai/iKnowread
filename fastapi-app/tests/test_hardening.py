"""Regression tests for deployment-blocking security and resource-boundary bugs."""
import io
import asyncio
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pypdfium2
from fastapi import HTTPException
from tortoise import Tortoise

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.config import settings
from app.dependencies import CurrentAccount, get_current_account
from app.migrations.v001_unify_accounts import (
    _move_account_directories,
    _prepare_legacy_password,
)
from app.models import Account, Document, Note
from app.services import ai_service, auth_service
from app.services.auth_guard import limiter
from app.security import (
    SESSION_COOKIE,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.storage import get_storage
from app.upload_guard import UploadConcurrencyMiddleware


def one_page_pdf() -> bytes:
    output = io.BytesIO()
    document = pypdfium2.PdfDocument.new()
    try:
        document.new_page(595, 842)
        document.save(output)
    finally:
        document.close()
    return output.getvalue()


class HardeningAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [
            patch.object(settings, "UPLOAD_DIR", self.temp.name),
            patch.object(settings, "OCR_ENABLED", False),
            patch.object(settings, "STORAGE_MIN_FREE_BYTES", 0),
            patch.object(settings, "USER_STORAGE_QUOTA_BYTES", 100 * 1024 * 1024),
            patch.object(settings, "USER_DOCUMENT_LIMIT", 10),
        ]
        for item in self.patches:
            item.start()
        get_storage.cache_clear()
        limiter.clear()
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.user = await Account.create(
            username="hardening-user", name="测试", password="unused", role="user"
        )
        self.app = create_app()
        self.app.dependency_overrides[get_current_account] = lambda: CurrentAccount(
            self.user.id, self.user.role, self.user
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        await Tortoise.close_connections()
        limiter.clear()
        get_storage.cache_clear()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    async def upload_pdf(self):
        return await self.client.post(
            "/document/upload", files={"file": ("safe.pdf", one_page_pdf(), "application/pdf")}
        )

    async def test_invalid_document_content_is_rejected(self):
        pdf = await self.client.post(
            "/document/upload", files={"file": ("fake.pdf", b"not a pdf", "application/pdf")}
        )
        docx = await self.client.post(
            "/document/upload", files={"file": ("fake.docx", b"not a zip", "application/octet-stream")}
        )
        self.assertEqual(pdf.status_code, 400, pdf.text)
        self.assertEqual(docx.status_code, 400, docx.text)
        self.assertEqual(await Document.all().count(), 0)

    async def test_disabled_ocr_has_terminal_status_and_no_polling_state(self):
        response = await self.upload_pdf()
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["ocr_status"], "failed")
        self.assertEqual(data["ocr_error"], "OCR 服务未启用")

    async def test_document_path_cannot_be_claimed_and_deleted_as_avatar(self):
        uploaded = await self.upload_pdf()
        data = uploaded.json()["data"]
        response = await self.client.put(
            f"/accounts/{self.user.id}", json={"name": "测试", "avatar": data["path"]}
        )
        self.assertEqual(response.status_code, 400, response.text)
        key = data["path"].removeprefix("files/download/")
        self.assertTrue(get_storage().exists(key))

    async def test_avatar_replacement_keeps_referenced_file_then_removes_old_file(self):
        png = b"\x89PNG\r\n\x1a\n" + b"safe-avatar"
        first_upload = await self.client.post(
            "/files/upload", files={"file": ("first.png", png, "image/png")}
        )
        self.assertEqual(first_upload.status_code, 200, first_upload.text)
        first_path = first_upload.json()["data"]
        first_key = first_path.removeprefix("files/download/")
        first_update = await self.client.put(
            f"/accounts/{self.user.id}", json={"name": "测试", "avatar": first_path}
        )
        self.assertEqual(first_update.status_code, 200, first_update.text)

        second_upload = await self.client.post(
            "/files/upload", files={"file": ("second.png", png, "image/png")}
        )
        self.assertEqual(second_upload.status_code, 200, second_upload.text)
        second_path = second_upload.json()["data"]
        second_key = second_path.removeprefix("files/download/")
        self.assertTrue(get_storage().exists(first_key))
        self.assertTrue(get_storage().exists(second_key))

        second_update = await self.client.put(
            f"/accounts/{self.user.id}", json={"name": "测试", "avatar": second_path}
        )
        self.assertEqual(second_update.status_code, 200, second_update.text)
        self.assertFalse(get_storage().exists(first_key))
        self.assertTrue(get_storage().exists(second_key))

    async def test_document_count_and_page_size_are_bounded(self):
        with patch.object(settings, "USER_DOCUMENT_LIMIT", 1):
            self.assertEqual((await self.upload_pdf()).status_code, 200)
            second = await self.upload_pdf()
            self.assertEqual(second.status_code, 413, second.text)
        page = await self.client.get("/document/selectPage", params={"pageSize": 1000000})
        self.assertEqual(page.status_code, 422)

    async def test_note_export_limit_is_enforced_before_building_response(self):
        for index in range(2):
            await Note.create(
                account_id=self.user.id, source_type="manual", title=f"n{index}",
                content="content", remark="",
            )
        with patch.object(settings, "NOTE_EXPORT_MAX_ITEMS", 1):
            response = await self.client.get("/notes/export")
        self.assertEqual(response.status_code, 413, response.text)

    async def test_registration_can_be_closed(self):
        self.app.dependency_overrides.clear()
        with patch.object(settings, "ALLOW_REGISTRATION", False):
            response = await self.client.post(
                "/register", json={"username": "blocked", "password": "password123"}
            )
        self.assertEqual(response.status_code, 403, response.text)

    async def test_request_log_uses_route_template_and_omits_query_secret(self):
        with self.assertLogs("app.observability", level="INFO") as captured:
            response = await self.client.get(
                "/capabilities", params={"api_key": "must-not-enter-logs"}
            )
        self.assertEqual(response.status_code, 200, response.text)
        request_id = response.headers.get("X-Request-ID", "")
        self.assertRegex(request_id, re.compile(r"^[0-9a-f]{24}$"))
        logs = "\n".join(captured.output)
        self.assertIn("route=/capabilities", logs)
        self.assertIn(f"request_id={request_id}", logs)
        self.assertNotIn("must-not-enter-logs", logs)

    async def test_unhandled_error_log_omits_exception_message(self):
        async def explode():
            raise RuntimeError("api-key-must-not-enter-logs")

        self.app.add_api_route("/__test_error", explode, methods=["GET"])
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=self.app, raise_app_exceptions=False
            ),
            base_url="http://test",
        )
        try:
            with self.assertLogs("app.common.exception_handler", level="ERROR") as captured:
                response = await client.get("/__test_error")
        finally:
            await client.aclose()
        self.assertEqual(response.status_code, 500, response.text)
        request_id = response.headers.get("X-Request-ID", "")
        self.assertRegex(request_id, re.compile(r"^[0-9a-f]{24}$"))
        logs = "\n".join(captured.output)
        self.assertIn("exception_type=RuntimeError", logs)
        self.assertIn(f"request_id={request_id}", logs)
        self.assertNotIn("api-key-must-not-enter-logs", logs)

    async def test_login_rate_limit_is_enforced_server_side(self):
        self.app.dependency_overrides.clear()
        self.user.password = hash_password("password123")
        await self.user.save(update_fields=["password"])
        payload = {"username": self.user.username, "password": "password123", "role": "user"}
        with patch.object(settings, "LOGIN_RATE_LIMIT", 1):
            first = await self.client.post("/login", json=payload)
            second = await self.client.post("/login", json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 429, second.text)
        self.assertIn("Retry-After", second.headers)
    async def test_logout_revokes_a_copied_session_token(self):
        self.app.dependency_overrides.clear()
        self.user.password = hash_password("password123")
        await self.user.save(update_fields=["password"])
        login = await self.client.post(
            "/login",
            json={
                "username": self.user.username,
                "password": "password123",
                "role": "user",
            },
        )
        self.assertEqual(login.status_code, 200, login.text)
        token = login.cookies.get(SESSION_COOKIE)
        self.assertTrue(token)
        headers = {"Authorization": f"Bearer {token}"}
        self.assertEqual((await self.client.get("/me", headers=headers)).status_code, 200)
        self.assertEqual((await self.client.post("/logout", headers=headers)).status_code, 200)
        replay = await self.client.get("/me", headers=headers)
        self.assertEqual(replay.status_code, 401, replay.text)

    async def test_low_iteration_hash_is_upgraded_only_after_valid_login(self):
        with patch("app.security.PASSWORD_ITERATIONS", 1_000):
            old_hash = hash_password("password123")
        self.user.password = old_hash
        await self.user.save(update_fields=["password"])

        await auth_service.migrate_legacy_passwords()
        unchanged = await Account.get(id=self.user.id)
        self.assertEqual(unchanged.password, old_hash)

        logged_in = await auth_service.login("user", self.user.username, "password123")
        self.assertNotEqual(logged_in.password, old_hash)
        self.assertTrue(verify_password("password123", logged_in.password))
        self.assertFalse(password_needs_rehash(logged_in.password))

    async def test_same_account_ai_requests_are_bounded(self):
        entered = asyncio.Event()
        release = asyncio.Event()

        async def slow_complete(*_args, **_kwargs):
            entered.set()
            await release.wait()
            return {"content": "ok"}

        config = SimpleNamespace(account_id=self.user.id)
        with (
            patch.object(settings, "AI_ACCOUNT_CONCURRENCY", 1),
            patch.object(settings, "AI_QUEUE_WAIT_SECONDS", 0.05),
            patch.object(ai_service, "_complete", side_effect=slow_complete),
        ):
            first = asyncio.create_task(ai_service.complete(config, []))
            await entered.wait()
            try:
                with self.assertRaises(HTTPException) as raised:
                    await ai_service.complete(config, [])
                self.assertEqual(raised.exception.status_code, 429)
            finally:
                release.set()
                await first


class UploadConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_is_rejected_before_second_handler_starts(self):
        from fastapi import FastAPI

        app = FastAPI()
        app.add_middleware(
            UploadConcurrencyMiddleware,
            limit=1,
            queue_wait_seconds=0.02,
            paths={"/document/upload"},
        )
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        handler_starts = 0

        @app.post("/document/upload")
        async def held_upload():
            nonlocal handler_starts
            handler_starts += 1
            first_started.set()
            await release_first.wait()
            return {"ok": True}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = asyncio.create_task(client.post("/document/upload"))
            await asyncio.wait_for(first_started.wait(), timeout=1)
            second = await client.post("/document/upload")
            self.assertEqual(second.status_code, 429, second.text)
            self.assertEqual(second.headers.get("Retry-After"), "1")
            self.assertEqual(handler_starts, 1)
            release_first.set()
            self.assertEqual((await first).status_code, 200)


class LegacyDirectoryMigrationTests(unittest.TestCase):
    def test_legacy_password_migration_preserves_recognized_hashes(self):
        with patch("app.security.PASSWORD_ITERATIONS", 1_000):
            old_hash = hash_password("password123")
        self.assertEqual(_prepare_legacy_password(old_hash), old_hash)
        migrated_plaintext = _prepare_legacy_password("legacy-password")
        self.assertNotEqual(migrated_plaintext, "legacy-password")
        self.assertTrue(verify_password("legacy-password", migrated_plaintext))

    def test_id_chain_is_staged_before_destinations_are_published(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, "UPLOAD_DIR", directory):
            root = Path(directory)
            for account_id in (1, 2):
                folder = root / "user" / str(account_id)
                folder.mkdir(parents=True)
                (folder / f"owner-{account_id}.pdf").write_text(str(account_id))
            _move_account_directories({("user", 1): 2, ("user", 2): 3})
            self.assertEqual(
                sorted(path.name for path in (root / "user" / "2").iterdir()),
                ["owner-1.pdf"],
            )
            self.assertEqual(
                sorted(path.name for path in (root / "user" / "3").iterdir()),
                ["owner-2.pdf"],
            )

    def test_interrupted_publish_does_not_restage_an_already_published_target(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, "UPLOAD_DIR", directory):
            root = Path(directory)
            published = root / "user" / "2"
            published.mkdir(parents=True)
            (published / "owner-1.pdf").write_text("1")
            staged = root / "_migration_v001_accounts" / "user" / "2"
            staged.mkdir(parents=True)
            (staged / "owner-2.pdf").write_text("2")
            (root / "_migration_v001_accounts" / ".staging-complete").touch()

            _move_account_directories({("user", 1): 2, ("user", 2): 3})

            self.assertEqual(
                sorted(path.name for path in (root / "user" / "2").iterdir()),
                ["owner-1.pdf"],
            )
            self.assertEqual(
                sorted(path.name for path in (root / "user" / "3").iterdir()),
                ["owner-2.pdf"],
            )
            self.assertFalse((root / "_migration_v001_accounts").exists())


if __name__ == "__main__":
    unittest.main()

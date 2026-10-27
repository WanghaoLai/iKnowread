"""Regression tests for deployment-blocking security and resource-boundary bugs."""
import ast
import io
import asyncio
import json
import re
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pypdfium2
from fastapi import HTTPException, Request
from PIL import Image
from tortoise import Tortoise

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.document as document_router
import app.routers.files as files_router
from app import create_app
from app import database
from app.api_paths import API_CONTRACT, DOCUMENT_UPLOAD_PATH, UPLOAD_PATHS
from app.config import Settings, settings
from app.dependencies import CurrentAccount, get_current_account
from app.migrations.v001_unify_accounts import (
    _move_account_directories,
    _prepare_legacy_password,
)
from app.migrations.runner import (
    LEGACY_MIGRATION_CHECKSUMS,
    migration_checksum,
    migration_checksum_is_compatible,
)
from app.migrations import (
    v015_markdown_documents,
    v016_web_imports,
    v017_web_import_lifecycle,
)
from app.models import Account, Document, Note
from app.schemas.document import DocumentPublic
from app.schemas.account import normalize_username
from app.services import (
    account_service,
    ai_guard,
    ai_service,
    auth_service,
    captcha_service,
    document_service,
    ocr_service,
)
from app.services.auth_guard import limit_auth, limiter
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


def small_png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2, 2), (20, 80, 140)).save(output, format="PNG")
    return output.getvalue()


class ConfigurationTests(unittest.TestCase):
    def test_async_code_does_not_call_synchronous_storage_io_directly(self):
        blocking_methods = {
            "open", "exists", "size", "delete", "move", "stage", "restore",
            "stage_tree", "restore_tree", "delete_tree", "iter_keys",
            "modified_at", "response",
        }
        violations = []

        class AsyncStorageVisitor(ast.NodeVisitor):
            def __init__(self, path, storage_names):
                self.path = path
                self.storage_names = storage_names

            # Synchronous helpers declared inside an async function are allowed:
            # their caller must pass the helper to run_storage_io.
            def visit_FunctionDef(self, node):
                return

            def visit_AsyncFunctionDef(self, node):
                return

            def visit_Lambda(self, node):
                return

            def visit_Call(self, node):
                function = node.func
                if (
                    isinstance(function, ast.Attribute)
                    and function.attr in blocking_methods
                    and (
                        isinstance(function.value, ast.Name)
                        and function.value.id in self.storage_names
                        or isinstance(function.value, ast.Call)
                        and isinstance(function.value.func, ast.Name)
                        and function.value.func.id == "get_storage"
                    )
                ):
                    violations.append(f"{self.path}:{node.lineno} .{function.attr}()")
                self.generic_visit(node)

        app_root = Path(__file__).resolve().parents[1] / "app"
        for path in app_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for function in ast.walk(tree):
                if not isinstance(function, ast.AsyncFunctionDef):
                    continue
                storage_names = {"storage"}
                for node in ast.walk(function):
                    if (
                        isinstance(node, ast.Assign)
                        and isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Name)
                        and node.value.func.id == "get_storage"
                    ):
                        storage_names.update(
                            target.id for target in node.targets if isinstance(target, ast.Name)
                        )
                visitor = AsyncStorageVisitor(path.relative_to(app_root.parent), storage_names)
                for statement in function.body:
                    visitor.visit(statement)

        self.assertEqual(violations, [])

    def test_username_normalization_is_canonical_and_bounded(self):
        self.assertEqual(normalize_username("  ｔｅｓｔ\u3000"), "test")
        with self.assertRaisesRegex(ValueError, "账号格式无效"):
            normalize_username("name\u200b")
        with self.assertRaisesRegex(ValueError, "账号格式无效"):
            normalize_username("x" * 256)

    def test_upload_guard_paths_match_real_upload_routes(self):
        app = create_app()
        upload_operation_names = {
            document_router.upload.__name__,
            files_router.upload_file.__name__,
        }
        actual_paths = {
            path
            for path, operations in app.openapi()["paths"].items()
            if any(
                operations.get("post", {}).get("operationId", "").startswith(
                    f"{operation_name}_"
                )
                for operation_name in upload_operation_names
            )
        }
        self.assertEqual(actual_paths, set(UPLOAD_PATHS))

        guard = next(
            middleware
            for middleware in app.user_middleware
            if middleware.cls is UploadConcurrencyMiddleware
        )
        self.assertEqual(frozenset(guard.kwargs["paths"]), UPLOAD_PATHS)

    def test_document_public_schema_does_not_expose_storage_path(self):
        self.assertNotIn("path", DocumentPublic.model_fields)

    def test_frontend_api_contract_matches_backend_routes(self):
        app = create_app()
        contract_path = (
            Path(__file__).resolve().parents[2]
            / "vue/src/api/apiContract.json"
        )
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        self.assertEqual(contract, API_CONTRACT)
        expected = {(entry["path"], entry["method"]) for entry in contract.values()}
        actual = {
            (path, method.upper())
            for path, operations in app.openapi()["paths"].items()
            for method in operations
            if method in {"get", "post", "put", "patch", "delete"}
        }
        self.assertTrue(expected.issubset(actual), expected - actual)

    def test_database_identifier_rejects_sql_syntax(self):
        with self.assertRaises(ValueError):
            Settings(DB_DATABASE="iknowread`; DROP DATABASE mysql; --", _env_file=None)

    def test_safe_defaults_require_explicit_local_or_production_configuration(self):
        configured = Settings(_env_file=None)
        self.assertEqual(configured.HOST, "127.0.0.1")
        self.assertFalse(configured.DEBUG)
        self.assertFalse(configured.ALLOW_REGISTRATION)
        self.assertFalse(configured.DB_AUTO_CREATE)
        self.assertEqual(configured.CORS_ORIGINS, "")

    def test_migration_checksum_detects_source_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "migration.py"
            source.write_text("VERSION = 1\n", encoding="utf-8")
            migration = SimpleNamespace(__file__=str(source))
            first = migration_checksum(migration)
            self.assertRegex(first, r"^[0-9a-f]{64}$")
            source.write_text("VERSION = 1\nNAME = 'changed'\n", encoding="utf-8")
            self.assertNotEqual(first, migration_checksum(migration))

    def test_v020_accepts_only_reviewed_legacy_checksum(self):
        current = "ed79bd800aea49f82257747c6a4eb7c418df916fc5ae6d7def0088658ba72603"
        legacy = {
            "20b9ce4606e0cd3533aa780c42c67918b45d8f4119d53798214f04de244c4602",
            "9739dc7522c72ca2b74635aaa17ea61be9cad1e459c1cf332d640100f4b4059c",
        }

        self.assertEqual(LEGACY_MIGRATION_CHECKSUMS[20], frozenset(legacy))
        self.assertTrue(migration_checksum_is_compatible(20, current, current))
        for checksum in legacy:
            self.assertTrue(migration_checksum_is_compatible(20, checksum, current))
        self.assertFalse(migration_checksum_is_compatible(20, "0" * 64, current))
        self.assertFalse(migration_checksum_is_compatible(19, next(iter(legacy)), current))

    def test_v020_avoids_deprecated_mysql_values_function(self):
        from app.migrations import v020_experience_account

        source = Path(v020_experience_account.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(source, r"VALUES\s*\(")
        self.assertIn("NOT EXISTS", source)

    def test_latest_migration_is_registered(self):
        from app.migrations.runner import MIGRATIONS

        from app.migrations import (
            v018_dashboard_reading_progress,
            v019_announcements,
            v020_experience_account,
            v021_bootstrap_experience_account,
        )

        self.assertIs(MIGRATIONS[-1], v021_bootstrap_experience_account)
        self.assertEqual(v016_web_imports.VERSION, 16)
        self.assertEqual(v017_web_import_lifecycle.VERSION, 17)
        self.assertEqual(v018_dashboard_reading_progress.VERSION, 18)
        self.assertEqual(v019_announcements.VERSION, 19)
        self.assertEqual(v020_experience_account.VERSION, 20)
        self.assertEqual(v021_bootstrap_experience_account.VERSION, 21)


class _MarkdownMigrationConnection:
    def __init__(self, constraint_exists=True):
        self.constraint_exists = constraint_exists
        self.executed = []

    async def execute_query_dict(self, _query, _params=None):
        return [{"1": 1}] if self.constraint_exists else []

    async def execute_query(self, query):
        self.executed.append(query)


class MarkdownMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_document_format_constraint_is_replaced_with_markdown_support(self):
        connection = _MarkdownMigrationConnection()

        await v015_markdown_documents.upgrade(connection)

        self.assertEqual(len(connection.executed), 2)
        self.assertIn("DROP CHECK `ck_document_ext`", connection.executed[0])
        self.assertIn("CHECK (`ext` IN ('pdf', 'docx', 'md'))", connection.executed[1])

    async def test_missing_document_format_constraint_is_created(self):
        connection = _MarkdownMigrationConnection(constraint_exists=False)

        await v015_markdown_documents.upgrade(connection)

        self.assertEqual(len(connection.executed), 1)
        self.assertIn("CHECK (`ext` IN ('pdf', 'docx', 'md'))", connection.executed[0])


class _InstanceLockCursor:
    def __init__(self, acquired):
        self.acquired = acquired
        self.queries = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, query, params=None):
        self.queries.append((query, params))

    async def fetchone(self):
        return (self.acquired,)


class _InstanceLockConnection:
    def __init__(self, acquired):
        self.cursor_value = _InstanceLockCursor(acquired)
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def close(self):
        self.closed = True


class InstanceLockTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await database.stop_instance_lock_monitor()
        database._instance_lock_connection = None
        database._instance_lock_valid = None
        database._instance_lock_io_lock = None

    async def test_single_instance_lock_is_held_until_shutdown(self):
        connection = _InstanceLockConnection(1)
        with patch.object(database.aiomysql, "connect", AsyncMock(return_value=connection)):
            await database.acquire_instance_lock()
        self.assertIs(database._instance_lock_connection, connection)
        self.assertFalse(connection.closed)
        await database.release_instance_lock()
        self.assertTrue(connection.closed)
        self.assertIn("RELEASE_LOCK", connection.cursor_value.queries[-1][0])

    async def test_second_instance_is_rejected(self):
        connection = _InstanceLockConnection(0)
        with (
            patch.object(database.aiomysql, "connect", AsyncMock(return_value=connection)),
            self.assertRaisesRegex(RuntimeError, "仅支持一个后端实例"),
        ):
            await database.acquire_instance_lock()
        self.assertTrue(connection.closed)

    async def test_lost_lock_is_detected_and_becomes_fail_closed(self):
        connection = _InstanceLockConnection(1)
        with patch.object(database.aiomysql, "connect", AsyncMock(return_value=connection)):
            await database.acquire_instance_lock()
        connection.cursor_value.acquired = 0

        with self.assertLogs("app.database", level="CRITICAL"):
            self.assertFalse(await database.verify_instance_lock())
        self.assertTrue(database.instance_lock_failed())

        await database.release_instance_lock()
        self.assertFalse(database.instance_lock_failed())

    async def test_lock_monitor_requests_supervised_restart_after_loss(self):
        with (
            patch.object(database.asyncio, "sleep", AsyncMock()),
            patch.object(database, "verify_instance_lock", AsyncMock(return_value=False)),
            patch.object(database, "_request_process_restart") as restart,
        ):
            await database._monitor_instance_lock()
        restart.assert_called_once_with()


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
        await captcha_service.clear()
        limiter.clear()
        get_storage.cache_clear()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    async def upload_pdf(self):
        return await self.client.post(
            "/documents", files={"file": ("safe.pdf", one_page_pdf(), "application/pdf")}
        )

    async def captcha_fields(self, code: str = "ABCDE") -> dict:
        challenge = await captcha_service.issue(code)
        return {"captcha_id": challenge["captcha_id"], "captcha_code": code}

    async def test_invalid_document_content_is_rejected(self):
        pdf = await self.client.post(
            "/documents", files={"file": ("fake.pdf", b"not a pdf", "application/pdf")}
        )
        docx = await self.client.post(
            "/documents", files={"file": ("fake.docx", b"not a zip", "application/octet-stream")}
        )
        markdown = await self.client.post(
            "/documents", files={"file": ("fake.md", b"\xff\xfe\x00\x00", "text/markdown")}
        )
        self.assertEqual(pdf.status_code, 400, pdf.text)
        self.assertEqual(docx.status_code, 400, docx.text)
        self.assertEqual(markdown.status_code, 400, markdown.text)
        self.assertEqual(await Document.all().count(), 0)

    async def test_markdown_upload_download_and_annotation_round_trip(self):
        content = "# 第一性原理\n\nMarkdown **正文**与中文内容。\n".encode()
        uploaded = await self.client.post(
            "/documents",
            files={"file": ("thinking.md", content, "text/markdown")},
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        document = uploaded.json()["data"]
        self.assertEqual(document["ext"], "md")
        self.assertEqual(document["ocr_status"], "not_applicable")

        downloaded = await self.client.get(
            f"/documents/{document['id']}/download",
            params={"version": document["content_version"]},
        )
        self.assertEqual(downloaded.status_code, 200, downloaded.text)
        self.assertEqual(downloaded.content, content)
        self.assertTrue(downloaded.headers["content-type"].startswith("text/markdown"))

        highlighted = await self.client.post(
            "/highlights",
            json={
                "document_id": document["id"],
                "source_anchor": {
                    "protocol": "iknowread.source-anchor/v1",
                    "document_id": document["id"],
                    "document_version": document["content_version"],
                    "source_format": "md",
                    "scope": "document",
                    "page": None,
                    "progression": 0,
                    "selector": {
                        "position": {"start": 0, "end": 5},
                        "quote": {"exact": "第一性原理", "prefix": "", "suffix": ""},
                    },
                },
                "selected_text": "第一性原理",
                "remark": "Markdown 高亮",
            },
        )
        self.assertEqual(highlighted.status_code, 200, highlighted.text)

    async def test_markdown_size_limit_is_enforced_while_validating_content(self):
        with patch.object(settings, "MARKDOWN_MAX_BYTES", 8):
            response = await self.client.post(
                "/documents",
                files={"file": ("large.md", b"123456789", "text/markdown")},
            )
        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(await Document.all().count(), 0)

    async def test_disabled_ocr_has_terminal_status_and_no_polling_state(self):
        response = await self.upload_pdf()
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["ocr_status"], "failed")
        self.assertEqual(data["ocr_error"], "OCR 服务未启用")

    async def test_unavailable_ocr_runtime_has_terminal_status(self):
        with (
            patch.object(settings, "OCR_ENABLED", True),
            patch.object(
                ocr_service,
                "_availability_error",
                "OCR 服务不可用，请安装 OCRmyPDF 后重试",
            ),
        ):
            response = await self.upload_pdf()
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["ocr_status"], "failed")
        self.assertIn("OCRmyPDF", data["ocr_error"])

    async def test_document_path_cannot_be_claimed_and_deleted_as_avatar(self):
        uploaded = await self.upload_pdf()
        data = uploaded.json()["data"]
        document = await Document.get(id=data["id"])
        response = await self.client.put(
            f"/accounts/{self.user.id}", json={"name": "测试", "avatar": document.path}
        )
        self.assertEqual(response.status_code, 400, response.text)
        key = document.path.removeprefix("files/download/")
        self.assertTrue(get_storage().exists(key))

    async def test_avatar_replacement_keeps_referenced_file_then_removes_old_file(self):
        png = small_png()
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

    async def test_account_tree_move_does_not_block_the_event_loop(self):
        account = await Account.create(
            username="storage-io-user", name="存储线程测试", password="unused", role="user"
        )
        storage = get_storage()
        await storage.save(
            "large-tree.bin", io.BytesIO(b"content"), subdir=f"user/{account.id}/documents"
        )
        original_stage_tree = storage.stage_tree
        started = threading.Event()
        release = threading.Event()

        def held_stage_tree(prefix):
            started.set()
            if not release.wait(timeout=1):
                raise AssertionError("storage operation blocked the event loop")
            return original_stage_tree(prefix)

        with patch.object(storage, "stage_tree", side_effect=held_stage_tree):
            deletion = asyncio.create_task(account_service.delete(account.id))
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(0.005)
            self.assertTrue(started.is_set())
            # This coroutine can only resume while stage_tree is waiting when
            # the filesystem operation is running in a worker thread.
            await asyncio.sleep(0.01)
            release.set()
            await deletion

        self.assertFalse(await Account.filter(id=account.id).exists())

    async def test_cancelled_account_delete_finishes_consistency_unit(self):
        account = await Account.create(
            username="cancelled-delete-user", name="取消删除测试", password="unused", role="user"
        )
        storage = get_storage()
        key = await storage.save(
            "owned.bin", io.BytesIO(b"content"), subdir=f"user/{account.id}/documents"
        )
        original_stage_tree = storage.stage_tree
        started = threading.Event()
        release = threading.Event()

        def held_stage_tree(prefix):
            started.set()
            if not release.wait(timeout=1):
                raise AssertionError("cancelled storage operation was abandoned")
            return original_stage_tree(prefix)

        with patch.object(storage, "stage_tree", side_effect=held_stage_tree):
            deletion = asyncio.create_task(account_service.delete(account.id))
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            deletion.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await deletion

        self.assertFalse(await Account.filter(id=account.id).exists())
        self.assertFalse(storage.exists(key))

    async def test_avatar_requires_a_complete_decodable_image(self):
        response = await self.client.post(
            "/files/upload",
            files={"file": ("broken.png", b"\x89PNG\r\n\x1a\nnot-an-image", "image/png")},
        )
        self.assertEqual(response.status_code, 400, response.text)

    async def test_long_document_filename_is_bounded_before_filesystem_write(self):
        filename = f"{'文档' * 150}.pdf"
        response = await self.client.post(
            "/documents",
            files={"file": (filename, one_page_pdf(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        document = await Document.get(id=response.json()["data"]["id"])
        stored = document.path.rsplit("/", 1)[-1]
        self.assertLessEqual(len(stored.encode("utf-8")), 255)

    async def test_document_count_and_page_size_are_bounded(self):
        with patch.object(settings, "USER_DOCUMENT_LIMIT", 1):
            self.assertEqual((await self.upload_pdf()).status_code, 200)
            second = await self.upload_pdf()
            self.assertEqual(second.status_code, 413, second.text)
        page = await self.client.get("/documents", params={"pageSize": 1000000})
        self.assertEqual(page.status_code, 422)

    async def test_recycled_documents_count_toward_total_document_limit(self):
        recycled = await Document.create(
            name="recycled.pdf", ext="pdf", size=1,
            path=f"files/download/user/{self.user.id}/recycled.pdf",
            account_id=self.user.id,
            deleted_at=datetime.now(timezone.utc),
        )
        with (
            patch.object(settings, "USER_DOCUMENT_LIMIT", 10),
            patch.object(settings, "USER_TOTAL_DOCUMENT_LIMIT", 1),
        ):
            response = await self.upload_pdf()
        self.assertEqual(response.status_code, 413, response.text)
        self.assertIn("清理回收站", response.text)
        self.assertTrue(await Document.filter(id=recycled.id).exists())

    async def test_account_and_document_pages_have_stable_newest_first_order(self):
        older_document = await Document.create(
            name="older.pdf", ext="pdf", size=1,
            path=f"files/download/user/{self.user.id}/older.pdf",
            account_id=self.user.id,
        )
        newer_document = await Document.create(
            name="newer.pdf", ext="pdf", size=1,
            path=f"files/download/user/{self.user.id}/newer.pdf",
            account_id=self.user.id,
        )
        document_page = await document_service.select_page(self.user.id, page_size=1)
        self.assertEqual(document_page["list"][0]["id"], newer_document.id)
        self.assertNotEqual(newer_document.id, older_document.id)

        newer_account = await Account.create(
            username="hardening-newer", name="较新账号", password="unused", role="user"
        )
        account_page = await account_service.select_page("user", page_size=1)
        self.assertEqual(account_page["list"][0]["id"], newer_account.id)

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

    async def test_capabilities_reports_runtime_ocr_availability(self):
        with (
            patch.object(settings, "OCR_ENABLED", True),
            patch.object(
                ocr_service,
                "availability_error",
                return_value="OCR runtime dependency is unavailable",
            ),
        ):
            unavailable = await self.client.get("/capabilities")
        self.assertEqual(unavailable.status_code, 200, unavailable.text)
        self.assertFalse(unavailable.json()["data"]["ocr_enabled"])
        self.assertEqual(
            unavailable.json()["data"]["ocr_error"],
            "OCR runtime dependency is unavailable",
        )

        with patch.object(ocr_service, "availability_error", return_value=None):
            available = await self.client.get("/capabilities")
        self.assertEqual(available.status_code, 200, available.text)
        self.assertTrue(available.json()["data"]["ocr_enabled"])
        self.assertIsNone(available.json()["data"]["ocr_error"])

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
        payload = {
            "username": self.user.username, "password": "password123", "role": "user",
            **await self.captcha_fields(),
        }
        with patch.object(settings, "LOGIN_RATE_LIMIT", 1):
            first = await self.client.post("/login", json=payload)
            second = await self.client.post("/login", json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 429, second.text)
        self.assertIn("Retry-After", second.headers)

    async def test_password_change_rate_limit_is_enforced_before_password_work(self):
        payload = {"password": "wrong-password", "newPassword": "new-password-123"}
        with patch.object(settings, "PASSWORD_CHANGE_RATE_LIMIT", 1):
            first = await self.client.put("/password", json=payload)
            second = await self.client.put("/password", json=payload)
        self.assertEqual(first.status_code, 400, first.text)
        self.assertEqual(second.status_code, 429, second.text)
        self.assertIn("Retry-After", second.headers)

    async def test_password_change_account_limit_cannot_be_bypassed_by_changing_ip(self):
        first_request = Request({"type": "http", "client": ("198.51.100.10", 1234)})
        second_request = Request({"type": "http", "client": ("203.0.113.20", 5678)})
        with patch.object(settings, "PASSWORD_CHANGE_RATE_LIMIT", 1):
            await limit_auth(first_request, "password", str(self.user.id))
            with self.assertRaises(HTTPException) as raised:
                await limit_auth(second_request, "password", str(self.user.id))
        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn("Retry-After", raised.exception.headers)

    async def test_invalid_login_uses_one_safe_actionable_message(self):
        self.app.dependency_overrides.clear()
        self.user.password = hash_password("password123")
        await self.user.save(update_fields=["password"])
        invalid_attempts = [
            {"username": "missing-user", "password": "password123", "role": "user"},
            {"username": self.user.username, "password": "wrong-password", "role": "user"},
            {"username": self.user.username, "password": "password123", "role": "admin"},
        ]
        for payload in invalid_attempts:
            limiter.clear()
            payload.update(await self.captcha_fields())
            response = await self.client.post("/login", json=payload)
            self.assertEqual(response.status_code, 401, response.text)
            self.assertEqual(response.json(), {"code": "401", "msg": "账号或密码错误"})
            self.assertNotIn(payload["password"], response.text)

    async def test_login_normalizes_surrounding_username_whitespace(self):
        self.app.dependency_overrides.clear()
        self.user.password = hash_password("password123")
        await self.user.save(update_fields=["password"])
        response = await self.client.post("/login", json={
            "username": f"  {self.user.username}\u3000",
            "password": "password123",
            "role": "user",
            **await self.captcha_fields(),
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["username"], self.user.username)

    async def test_captcha_is_image_based_short_lived_and_one_time(self):
        self.app.dependency_overrides.clear()
        self.user.password = hash_password("password123")
        await self.user.save(update_fields=["password"])

        with patch("app.services.captcha_service._new_code", return_value="ABCDE"):
            issued = await self.client.get("/captcha")
        self.assertEqual(issued.status_code, 200, issued.text)
        self.assertEqual(issued.headers.get("cache-control"), "no-store, no-cache, must-revalidate")
        challenge = issued.json()["data"]
        self.assertTrue(challenge["image"].startswith("data:image/png;base64,"))
        self.assertNotIn("ABCDE", issued.text)

        payload = {
            "username": self.user.username, "password": "password123", "role": "user",
            "captcha_id": challenge["captcha_id"], "captcha_code": "EDCBA",
        }
        incorrect = await self.client.post("/login", json=payload)
        self.assertEqual(incorrect.status_code, 400, incorrect.text)
        self.assertIn("验证码错误", incorrect.json()["msg"])

        payload["captcha_code"] = "ABCDE"
        replay = await self.client.post("/login", json=payload)
        self.assertEqual(replay.status_code, 400, replay.text)
        self.assertIn("验证码已失效", replay.json()["msg"])

        payload.update(await self.captcha_fields())
        successful = await self.client.post("/login", json=payload)
        self.assertEqual(successful.status_code, 200, successful.text)

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
                **await self.captcha_fields(),
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

    async def test_plaintext_password_migration_uses_restart_safe_batches(self):
        accounts = [
            await Account.create(
                username=f"legacy-batch-{index}", name="存量账号",
                password=f"legacy-password-{index}", role="user",
            )
            for index in range(3)
        ]
        await auth_service.migrate_legacy_passwords(batch_size=1)
        for index, account in enumerate(accounts):
            migrated = await Account.get(id=account.id)
            self.assertTrue(
                verify_password(f"legacy-password-{index}", migrated.password)
            )
            self.assertTrue(migrated.password.startswith("pbkdf2_sha256$"))

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

    async def test_global_ai_timeout_releases_account_slot(self):
        ai_guard._global_slots = None
        ai_guard._global_count = None
        ai_guard._account_slots.clear()
        with (
            patch.object(settings, "AI_GLOBAL_CONCURRENCY", 1),
            patch.object(settings, "AI_ACCOUNT_CONCURRENCY", 1),
            patch.object(settings, "AI_QUEUE_WAIT_SECONDS", 0.02),
        ):
            async with ai_guard.ai_request_slot(self.user.id):
                with self.assertRaises(HTTPException) as raised:
                    async with ai_guard.ai_request_slot(self.user.id + 1):
                        self.fail("global slot should still be occupied")
                self.assertEqual(raised.exception.status_code, 429)

            # The timed-out request acquired its account slot before waiting for
            # the global slot. It must release that partial acquisition.
            async with ai_guard.ai_request_slot(self.user.id + 1):
                pass


class UploadConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_is_rejected_before_second_handler_starts(self):
        from fastapi import FastAPI

        app = FastAPI()
        app.add_middleware(
            UploadConcurrencyMiddleware,
            limit=1,
            queue_wait_seconds=0.02,
            paths={DOCUMENT_UPLOAD_PATH},
        )
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        handler_starts = 0

        @app.post(DOCUMENT_UPLOAD_PATH)
        async def held_upload():
            nonlocal handler_starts
            handler_starts += 1
            first_started.set()
            await release_first.wait()
            return {"ok": True}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = asyncio.create_task(client.post(DOCUMENT_UPLOAD_PATH))
            await asyncio.wait_for(first_started.wait(), timeout=1)
            second = await client.post(DOCUMENT_UPLOAD_PATH)
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

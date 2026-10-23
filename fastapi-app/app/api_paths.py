"""Single source of truth for public API methods and paths.

Backend routers derive their routes from this module. The frontend consumes a
generated JSON snapshot which is checked against this mapping and FastAPI's
OpenAPI output during every release.
"""

from __future__ import annotations

from typing import Final, TypedDict


class Endpoint(TypedDict):
    method: str
    path: str


def _endpoint(method: str, path: str) -> Endpoint:
    return {"method": method, "path": path}


API_CONTRACT: Final[dict[str, Endpoint]] = {
    "meta.capabilities": _endpoint("GET", "/capabilities"),
    "dashboard.summary": _endpoint("GET", "/dashboard"),
    "auth.captcha": _endpoint("GET", "/captcha"),
    "auth.me": _endpoint("GET", "/me"),
    "auth.login": _endpoint("POST", "/login"),
    "auth.logout": _endpoint("POST", "/logout"),
    "auth.register": _endpoint("POST", "/register"),
    "auth.password": _endpoint("PUT", "/password"),
    "accounts.list": _endpoint("GET", "/accounts"),
    "accounts.create": _endpoint("POST", "/accounts"),
    "accounts.get": _endpoint("GET", "/accounts/{account_id}"),
    "accounts.update": _endpoint("PUT", "/accounts/{account_id}"),
    "accounts.delete": _endpoint("DELETE", "/accounts/{account_id}"),
    "documents.list": _endpoint("GET", "/documents"),
    "documents.upload": _endpoint("POST", "/documents"),
    "documents.delete": _endpoint("DELETE", "/documents/{doc_id}"),
    "documents.preview": _endpoint("GET", "/documents/{doc_id}/preview"),
    "documents.download": _endpoint("GET", "/documents/{doc_id}/download"),
    "documents.ocr": _endpoint("POST", "/documents/{doc_id}/ocr"),
    "documents.ocr_status": _endpoint("GET", "/documents/{doc_id}/ocr-status"),
    "documents.processing_status": _endpoint("GET", "/documents/{doc_id}/processing-status"),
    "documents.recycle_list": _endpoint("GET", "/documents/recycle-bin"),
    "documents.restore": _endpoint("POST", "/documents/recycle-bin/{doc_id}/restore"),
    "documents.purge": _endpoint("DELETE", "/documents/recycle-bin/{doc_id}"),
    "files.upload": _endpoint("POST", "/files/upload"),
    "web_imports.create": _endpoint("POST", "/web-imports"),
    "web_imports.list": _endpoint("GET", "/web-imports"),
    "web_imports.get": _endpoint("GET", "/web-imports/{job_id}"),
    "web_imports.retry": _endpoint("POST", "/web-imports/{job_id}/retry"),
    "web_imports.cancel": _endpoint("POST", "/web-imports/{job_id}/cancel"),
    "web_imports.delete": _endpoint("DELETE", "/web-imports/{job_id}"),
    "notes.list": _endpoint("GET", "/notes"),
    "notes.summary": _endpoint("GET", "/notes/summary"),
    "notes.export_query": _endpoint("GET", "/notes/export"),
    "notes.export": _endpoint("POST", "/notes/export"),
    "notes.create": _endpoint("POST", "/notes"),
    "notes.update": _endpoint("PUT", "/notes/{note_id}"),
    "notes.delete": _endpoint("DELETE", "/notes/{note_id}"),
    "highlights.list": _endpoint("GET", "/highlights"),
    "highlights.create": _endpoint("POST", "/highlights"),
    "highlights.update": _endpoint("PUT", "/highlights/{highlight_id}"),
    "highlights.delete": _endpoint("DELETE", "/highlights/{highlight_id}"),
    "reading_progress.get": _endpoint("GET", "/reading-progress/{document_id}"),
    "reading_progress.save": _endpoint("PUT", "/reading-progress"),
    "announcements.list": _endpoint("GET", "/announcements"),
    "announcements.read": _endpoint("PUT", "/announcements/{announcement_id}/read"),
    "announcements.read_all": _endpoint("PUT", "/announcements/read-all"),
    "announcements.admin_list": _endpoint("GET", "/admin/announcements"),
    "announcements.create": _endpoint("POST", "/admin/announcements"),
    "announcements.update": _endpoint("PUT", "/admin/announcements/{announcement_id}"),
    "announcements.status": _endpoint("PATCH", "/admin/announcements/{announcement_id}/status"),
    "announcements.delete": _endpoint("DELETE", "/admin/announcements/{announcement_id}"),
    "ai.active_config": _endpoint("GET", "/ai/config"),
    "ai.providers": _endpoint("GET", "/ai/providers"),
    "ai.configs": _endpoint("GET", "/ai/configs"),
    "ai.create_config": _endpoint("POST", "/ai/configs"),
    "ai.update_config": _endpoint("PUT", "/ai/configs/{config_id}"),
    "ai.delete_config": _endpoint("DELETE", "/ai/configs/{config_id}"),
    "ai.activate_config": _endpoint("POST", "/ai/configs/{config_id}/activate"),
    "ai.test_saved_config": _endpoint("POST", "/ai/configs/{config_id}/test"),
    "ai.config_models": _endpoint("GET", "/ai/configs/{config_id}/models"),
    "ai.save_active_config": _endpoint("PUT", "/ai/config"),
    "ai.test": _endpoint("POST", "/ai/test"),
    "ai.chat": _endpoint("POST", "/ai/chat"),
    "ai.explain": _endpoint("POST", "/ai/explain"),
}


def api_path(name: str) -> str:
    try:
        return API_CONTRACT[name]["path"]
    except KeyError as exc:
        raise ValueError(f"unknown API endpoint: {name}") from exc


def relative_route(name: str, prefix: str) -> str:
    path = api_path(name)
    if not path.startswith(prefix):
        raise ValueError(f"endpoint {name} is outside prefix {prefix}")
    return path[len(prefix):]


DOCUMENTS_PREFIX = "/documents"
DOCUMENT_UPLOAD_ROUTE = relative_route("documents.upload", DOCUMENTS_PREFIX)
DOCUMENT_LIST_ROUTE = relative_route("documents.list", DOCUMENTS_PREFIX)
DOCUMENT_ITEM_ROUTE = relative_route("documents.delete", DOCUMENTS_PREFIX)
DOCUMENT_PREVIEW_ROUTE = relative_route("documents.preview", DOCUMENTS_PREFIX)
DOCUMENT_DOWNLOAD_ROUTE = relative_route("documents.download", DOCUMENTS_PREFIX)
DOCUMENT_OCR_ROUTE = relative_route("documents.ocr", DOCUMENTS_PREFIX)
DOCUMENT_OCR_STATUS_ROUTE = relative_route("documents.ocr_status", DOCUMENTS_PREFIX)
DOCUMENT_PROCESSING_STATUS_ROUTE = relative_route("documents.processing_status", DOCUMENTS_PREFIX)
DOCUMENT_RECYCLE_ROUTE = relative_route("documents.recycle_list", DOCUMENTS_PREFIX)
DOCUMENT_RESTORE_ROUTE = relative_route("documents.restore", DOCUMENTS_PREFIX)
DOCUMENT_PURGE_ROUTE = relative_route("documents.purge", DOCUMENTS_PREFIX)

FILES_PREFIX = "/files"
FILE_UPLOAD_ROUTE = relative_route("files.upload", FILES_PREFIX)
DOCUMENT_UPLOAD_PATH = api_path("documents.upload")
FILE_UPLOAD_PATH = api_path("files.upload")
UPLOAD_PATHS = frozenset({DOCUMENT_UPLOAD_PATH, FILE_UPLOAD_PATH})

WEB_IMPORTS_PREFIX = "/web-imports"
WEB_IMPORT_ITEM_ROUTE = relative_route("web_imports.get", WEB_IMPORTS_PREFIX)
WEB_IMPORT_RETRY_ROUTE = relative_route("web_imports.retry", WEB_IMPORTS_PREFIX)
WEB_IMPORT_CANCEL_ROUTE = relative_route("web_imports.cancel", WEB_IMPORTS_PREFIX)

NOTES_PREFIX = "/notes"
NOTES_SUMMARY_ROUTE = relative_route("notes.summary", NOTES_PREFIX)
NOTES_EXPORT_ROUTE = relative_route("notes.export", NOTES_PREFIX)
NOTES_ITEM_ROUTE = relative_route("notes.update", NOTES_PREFIX)

HIGHLIGHTS_PREFIX = "/highlights"
HIGHLIGHTS_ITEM_ROUTE = relative_route("highlights.update", HIGHLIGHTS_PREFIX)

AI_PREFIX = "/ai"
AI_CONFIG_ROUTE = relative_route("ai.active_config", AI_PREFIX)
AI_PROVIDERS_ROUTE = relative_route("ai.providers", AI_PREFIX)
AI_CONFIGS_ROUTE = relative_route("ai.configs", AI_PREFIX)
AI_CONFIG_ITEM_ROUTE = relative_route("ai.update_config", AI_PREFIX)
AI_CONFIG_ACTIVATE_ROUTE = relative_route("ai.activate_config", AI_PREFIX)
AI_CONFIG_TEST_ROUTE = relative_route("ai.test_saved_config", AI_PREFIX)
AI_CONFIG_MODELS_ROUTE = relative_route("ai.config_models", AI_PREFIX)
AI_TEST_ROUTE = relative_route("ai.test", AI_PREFIX)
AI_CHAT_ROUTE = relative_route("ai.chat", AI_PREFIX)
AI_EXPLAIN_ROUTE = relative_route("ai.explain", AI_PREFIX)

ACCOUNTS_PREFIX = "/accounts"
ACCOUNTS_ITEM_ROUTE = relative_route("accounts.get", ACCOUNTS_PREFIX)

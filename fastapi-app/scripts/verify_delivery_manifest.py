"""Fail a release when required runtime sources are absent from the Git index."""
from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
REQUIRED = (
    "compose.crawler-dev.yaml",
    "deploy/Caddyfile.crawler-gateway",
    "deploy/Dockerfile.crawler",
    "deploy/update.sh",
    "fastapi-app/app/migrations/v015_markdown_documents.py",
    "fastapi-app/app/migrations/v016_web_imports.py",
    "fastapi-app/app/migrations/v017_web_import_lifecycle.py",
    "fastapi-app/app/migrations/v018_dashboard_reading_progress.py",
    "fastapi-app/app/migrations/v019_announcements.py",
    "fastapi-app/app/migrations/v020_experience_account.py",
    "fastapi-app/app/models/experience.py",
    "fastapi-app/app/routers/experience.py",
    "fastapi-app/app/schemas/experience.py",
    "fastapi-app/app/services/experience_service.py",
    "fastapi-app/app/models/web_import_job.py",
    "fastapi-app/app/routers/web_imports.py",
    "fastapi-app/app/schemas/web_import.py",
    "fastapi-app/app/services/crawler_client.py",
    "fastapi-app/app/services/url_safety.py",
    "fastapi-app/app/services/web_import_service.py",
    "fastapi-app/scripts/ssrf_redirect_server.py",
    "fastapi-app/scripts/verify_crawler_isolation.py",
    "fastapi-app/scripts/verify_backup_migrations.py",
    "fastapi-app/scripts/verify_delivery_manifest.py",
    "vue/jsconfig.json",
    "vue/src/api/accounts.js",
    "vue/src/api/ai.js",
    "vue/src/api/apiContract.json",
    "vue/src/api/apiPaths.js",
    "vue/src/api/auth.js",
    "vue/src/api/highlights.js",
    "vue/src/api/experience.js",
    "vue/src/api/notes.js",
    "vue/src/api/webImports.js",
    "vue/src/composables/useDocumentLoader.js",
    "vue/src/composables/useSelectionExplanation.js",
    "vue/src/utils/markdown.js",
    "vue/src/views/manager/ExperienceManage.vue",
)


def main() -> None:
    if not (ROOT / ".git").exists():
        raise SystemExit("delivery manifest check requires a Git working tree")
    tracked = set(
        subprocess.run(
            ["git", "ls-files"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.splitlines()
    )
    missing = [path for path in REQUIRED if path not in tracked]
    if missing:
        formatted = "\n".join(f"  - {path}" for path in missing)
        raise SystemExit(f"required delivery files are not tracked:\n{formatted}")
    print("delivery manifest check: PASS")


if __name__ == "__main__":
    main()

from contextlib import asynccontextmanager
import secrets

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.common.exception_handler import setup_exceptions
from app.config import settings
from app.database import init_db, close_db
from app.models import Account
from app.observability import setup_observability
from app.routers import api_router
from app.security import hash_password, validate_security_config
from app.services.auth_service import migrate_legacy_passwords
from app.services.storage_service import reconcile_storage, start_periodic_cleanup, stop_periodic_cleanup
from app.services import ocr_service
from app.upload_guard import UploadConcurrencyMiddleware


async def seed_default_admin():
    """首次启动创建管理员，不再使用可预测的固定密码。"""
    if await Account.filter(role="admin").exists():
        return
    generated = not settings.DEFAULT_ADMIN_PASSWORD
    initial_password = settings.DEFAULT_ADMIN_PASSWORD or secrets.token_urlsafe(16)
    await Account.create(
        username=settings.DEFAULT_ADMIN_USERNAME,
        password=hash_password(initial_password),
        name="管理员",
        avatar=None,
        role="admin",
    )
    if generated:
        # 放在 data/ 而非 upload_dir（文件下载服务的根），避免被 /files/download 枚举到
        secret_file = settings.data_dir / ".initial-admin-password"
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(initial_password, encoding="utf-8")
        secret_file.chmod(0o600)
        print(f"已创建初始管理员 {settings.DEFAULT_ADMIN_USERNAME!r}；一次性密码保存在 {secret_file}")
    else:
        print(f"已创建初始管理员 {settings.DEFAULT_ADMIN_USERNAME!r}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_security_config()
    await init_db()
    await seed_default_admin()
    await migrate_legacy_passwords()
    await reconcile_storage()
    start_periodic_cleanup()
    await ocr_service.start()
    try:
        yield
    finally:
        await ocr_service.stop()
        await stop_periodic_cleanup()
        await close_db()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

    setup_observability(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    app.add_middleware(
        UploadConcurrencyMiddleware,
        limit=settings.UPLOAD_CONCURRENCY,
        queue_wait_seconds=settings.UPLOAD_QUEUE_WAIT_SECONDS,
        paths={"/document/upload", "/files/upload"},
    )

    app.include_router(api_router)
    setup_exceptions(app)
    return app

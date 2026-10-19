import asyncio
from contextlib import asynccontextmanager
import secrets

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api_paths import UPLOAD_PATHS
from app.common.exception_handler import SafeErrorMiddleware, setup_exceptions
from app.config import settings
from app.database import (
    close_db,
    init_db,
    instance_lock_failed,
    start_instance_lock_monitor,
    stop_instance_lock_monitor,
)
from app.models import Account
from app.observability import setup_observability
from app.routers import api_router
from app.security import hash_password, validate_security_config
from app.services.auth_service import (
    start_legacy_password_migration,
    stop_legacy_password_migration,
)
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

        def write_initial_password() -> None:
            secret_file.parent.mkdir(parents=True, exist_ok=True)
            secret_file.write_text(initial_password, encoding="utf-8")
            secret_file.chmod(0o600)

        await asyncio.to_thread(write_initial_password)
        print(f"已创建初始管理员 {settings.DEFAULT_ADMIN_USERNAME!r}；一次性密码保存在 {secret_file}")
    else:
        print(f"已创建初始管理员 {settings.DEFAULT_ADMIN_USERNAME!r}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_security_config()
    await init_db()
    start_instance_lock_monitor()
    try:
        await seed_default_admin()
        start_legacy_password_migration()
        await reconcile_storage()
        start_periodic_cleanup()
        await ocr_service.start()
        yield
    finally:
        await stop_legacy_password_migration()
        await ocr_service.stop()
        await stop_periodic_cleanup()
        await stop_instance_lock_monitor()
        await close_db()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

    @app.middleware("http")
    async def enforce_instance_lock(request, call_next):
        if instance_lock_failed() and request.url.path != "/health":
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=503,
                content={"code": "503", "msg": "服务运行锁已失效，正在等待安全重启"},
            )
        return await call_next(request)

    # add_middleware prepends: CORS -> error boundary -> observability -> upload
    # gate -> instance guard -> routes. Early 429/500 responses retain CORS.
    app.add_middleware(
        UploadConcurrencyMiddleware,
        limit=settings.UPLOAD_CONCURRENCY,
        queue_wait_seconds=settings.UPLOAD_QUEUE_WAIT_SECONDS,
        paths=UPLOAD_PATHS,
    )
    setup_observability(app)
    app.add_middleware(SafeErrorMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    app.include_router(api_router)
    setup_exceptions(app)
    return app

import os

from fastapi import APIRouter, HTTPException
from tortoise import Tortoise

from app.common.result import Result
from app.config import settings
from app.database import verify_instance_lock
from app.routers import account, ai, auth, document, files, highlights, notes
from app.services import ocr_service
from app.storage import run_storage_io

api_router = APIRouter()
for router in (
    auth.router, account.router, document.router, files.router, ai.router,
    notes.router, highlights.router,
):
    api_router.include_router(router)


def _upload_directory_is_ready() -> bool:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    return os.access(settings.upload_dir, os.R_OK | os.W_OK | os.X_OK)


@api_router.get("/")
async def root():
    return Result.success()


@api_router.get("/health")
async def health():
    return Result.success({"status": "ok"})


@api_router.get("/ready")
async def ready():
    try:
        await Tortoise.get_connection("default").execute_query("SELECT 1")
        if not await verify_instance_lock():
            raise RuntimeError("application singleton lock is unavailable")
        if not await run_storage_io(_upload_directory_is_ready):
            raise PermissionError("upload directory is not writable")
        if settings.OCR_ENABLED and not ocr_service.is_available():
            raise RuntimeError(ocr_service.availability_error() or "OCR service is unavailable")
    except Exception:
        raise HTTPException(status_code=503, detail="服务依赖尚未就绪") from None
    return Result.success({"status": "ready"})


@api_router.get("/capabilities")
async def capabilities():
    ocr_error = ocr_service.availability_error()
    return Result.success({
        "registration_enabled": settings.ALLOW_REGISTRATION,
        "ocr_enabled": ocr_error is None,
        "ocr_error": ocr_error,
    })

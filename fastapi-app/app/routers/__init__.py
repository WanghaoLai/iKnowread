import os

from fastapi import APIRouter, HTTPException
from tortoise import Tortoise

from app.common.result import Result
from app.config import settings
from app.routers import account, ai, auth, document, files, notes

api_router = APIRouter()
for router in (auth.router, account.router, document.router, files.router, ai.router, notes.router):
    api_router.include_router(router)


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
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        if not os.access(settings.upload_dir, os.R_OK | os.W_OK | os.X_OK):
            raise PermissionError("upload directory is not writable")
    except Exception:
        raise HTTPException(status_code=503, detail="服务依赖尚未就绪") from None
    return Result.success({"status": "ready"})


@api_router.get("/capabilities")
async def capabilities():
    return Result.success({
        "registration_enabled": settings.ALLOW_REGISTRATION,
        "ocr_enabled": settings.OCR_ENABLED,
    })

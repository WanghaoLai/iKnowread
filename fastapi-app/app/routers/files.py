import mimetypes
import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File, status
from PIL import Image, UnidentifiedImageError
from tortoise.expressions import Q

from app.api_paths import FILES_PREFIX, FILE_UPLOAD_ROUTE
from app.common.result import Result
from app.dependencies import CurrentAccount, get_current_account
from app.models import Account, Document
from app.services import account_service
from app.services.account_service import RELATIVE_PREFIX
from app.storage import get_storage, run_storage_io
from app.services.resource_limits import (
    account_lock,
    ensure_additional_storage,
    ensure_temporary_capacity,
)

router = APIRouter(prefix=FILES_PREFIX)

MAX_AVATAR_SIZE = 5 * 1024 * 1024
AVATAR_EXTS = {"jpg", "jpeg", "png", "gif", "webp"}
AVATAR_FORMATS = {
    "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "gif": "GIF", "webp": "WEBP",
}
MAX_AVATAR_PIXELS = 25_000_000


async def validate_avatar(file: UploadFile) -> None:
    name = file.filename or ""
    ext = Path(name).suffix.lower().lstrip(".")
    if ext not in AVATAR_EXTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="头像仅支持 JPG、PNG、GIF、WEBP")
    if file.size is not None and file.size > MAX_AVATAR_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="头像不能超过 5MB")
    def verify_image() -> bool:
        file.file.seek(0)
        with Image.open(file.file) as image:
            if image.format != AVATAR_FORMATS[ext]:
                return False
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_AVATAR_PIXELS:
                return False
            image.verify()
        return True

    try:
        valid = await asyncio.to_thread(verify_image)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        valid = False
    finally:
        await file.seek(0)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件内容不是有效图片")


# 文件上传（存入账号专属目录 user/{id} 或 admin/{id}；账号未定则暂存 temp/）
@router.post(FILE_UPLOAD_ROUTE)
async def upload_file(
    file: UploadFile = File(...),
    account_id: int = Form(None),
    role: str = Form(None),
    current: CurrentAccount = Depends(get_current_account),
):
    await validate_avatar(file)
    await ensure_temporary_capacity(int(file.size or 0))
    storage = get_storage()
    target_account_id: int | None = None
    if current.is_admin:
        normalized = account_service.normalize_role(role)
        if account_id:
            if not normalized or not await Account.filter(id=account_id, role=normalized).exists():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标账号不存在")
            subdir = f"{normalized}/{account_id}/avatars"
            target_account_id = account_id
        else:
            subdir = "temp/avatars"
    else:
        subdir = f"user/{current.id}/avatars"
        target_account_id = current.id

    async def save_avatar() -> str:
        if target_account_id is not None:
            await ensure_additional_storage(target_account_id, int(file.size or 0))
        key = await storage.save(file.filename, file.file, subdir=subdir)
        if await run_storage_io(storage.size, key) > MAX_AVATAR_SIZE:
            await run_storage_io(storage.delete, key)
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="头像不能超过 5MB")
        if target_account_id is not None:
            try:
                await ensure_additional_storage(target_account_id, 0)
            except Exception:
                await run_storage_io(storage.delete, key)
                raise
        if target_account_id is not None:
            referenced = set(
                await Account.exclude(avatar=None).filter(id=target_account_id).values_list("avatar", flat=True)
            )
            referenced_keys = {
                value[len(RELATIVE_PREFIX):] for value in referenced
                if value and value.startswith(RELATIVE_PREFIX)
            }
            def remove_unreferenced_avatars() -> None:
                for existing in storage.iter_keys(subdir):
                    if existing != key and existing not in referenced_keys:
                        storage.delete(existing)

            await run_storage_io(remove_unreferenced_avatars)
        return key

    if target_account_id is not None:
        async with account_lock(target_account_id):
            key = await save_avatar()
    else:
        key = await save_avatar()
    return Result.success(RELATIVE_PREFIX + key)


# 文件下载
@router.get("/download/{key:path}")
async def download_file(key: str, current: CurrentAccount = Depends(get_current_account)):
    storage = get_storage()
    key = storage.safe_path(key)  # 支持子目录 key（如 {userId}/xxx.pdf）
    parts = key.split("/")
    # 拒绝内部目录与隐藏文件（上传文件名总带随机前缀，合法 key 不会以 . 开头）
    if parts[0] in ("_trash", "temp") or any(part.startswith(".") for part in parts):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    # 文档必须经过 /documents/{id}/download 或 /documents/{id}/preview 校验软删除状态、
    # 内容版本和归属；禁止用历史 path 绕过回收站与版本协议。
    relative_path = RELATIVE_PREFIX + key
    if await Document.filter(Q(path=relative_path) | Q(ocr_path=relative_path)).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    own_prefix = f"{current.role}/{current.id}/"
    if not current.is_admin and not key.startswith(own_prefix):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该文件")
    media_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return await run_storage_io(
        storage.response, key, filename=Path(key).name, media_type=media_type
    )

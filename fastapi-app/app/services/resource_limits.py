from __future__ import annotations

import asyncio
import logging
import shutil
from collections import defaultdict

from app.common.exception_handler import CustomException
from app.config import settings
from app.models import Account, Document
from app.storage import get_storage


logger = logging.getLogger(__name__)


_account_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def account_lock(account_id: int) -> asyncio.Lock:
    return _account_locks[account_id]


def prune_account_locks(active_account_ids: set[int]) -> None:
    """回收已删除账号的进程内锁，避免字典随账号更替无限增长。

    正被持有的锁跳过本轮回收（持有方仍引用同一对象），下一轮清理。
    """
    for account_id in [key for key in _account_locks if key not in active_account_ids]:
        if not _account_locks[account_id].locked():
            del _account_locks[account_id]


async def ensure_document_capacity(
    account_id: int, incoming_size: int, *, adds_new_document: bool = True
) -> None:
    if incoming_size < 0:
        raise CustomException("文件大小无效")
    active_count = await Document.filter(
        account_id=account_id, deleted_at__isnull=True
    ).count()
    if active_count >= max(1, settings.USER_DOCUMENT_LIMIT):
        raise CustomException("文档数量已达到账号上限，请先删除不需要的文档", status_code=413)
    # 回收站文件仍占磁盘并持有数据库关联。若只限制活跃文档，反复上传后
    # 移入回收站可令记录和关联数据无限增长。
    if adds_new_document:
        total_count = await Document.filter(account_id=account_id).count()
        if total_count >= max(1, settings.USER_TOTAL_DOCUMENT_LIMIT):
            raise CustomException(
                "文档总数已达到账号上限，请先清理回收站", status_code=413
            )
    await ensure_additional_storage(account_id, incoming_size)


async def ensure_additional_storage(
    account_id: int, incoming_size: int, *, reclaimable_size: int = 0
) -> None:
    account = await Account.get_or_none(id=account_id)
    if account is None:
        raise CustomException("账号不存在", status_code=404)
    storage = get_storage()

    def used_bytes() -> int:
        total = 0
        for key in storage.iter_keys(f"{account.role}/{account.id}"):
            total += storage.size(key)
        return total

    used = await asyncio.to_thread(used_bytes)
    effective_used = max(0, used - max(0, reclaimable_size))
    if effective_used + incoming_size > max(1, settings.USER_STORAGE_QUOTA_BYTES):
        logger.warning(
            "account_storage_rejected account_id=%s used_bytes=%s incoming_bytes=%s quota_bytes=%s",
            account_id,
            used,
            incoming_size,
            settings.USER_STORAGE_QUOTA_BYTES,
        )
        raise CustomException("账号存储空间不足，请先删除不需要的文档", status_code=413)
    free = (await asyncio.to_thread(shutil.disk_usage, settings.upload_dir)).free
    if free - incoming_size < max(0, settings.STORAGE_MIN_FREE_BYTES):
        logger.warning(
            "host_storage_rejected account_id=%s free_bytes=%s incoming_bytes=%s reserve_bytes=%s",
            account_id,
            free,
            incoming_size,
            settings.STORAGE_MIN_FREE_BYTES,
        )
        raise CustomException("服务器存储空间不足，请联系管理员", status_code=507)


async def ensure_temporary_capacity(incoming_size: int) -> None:
    def free_bytes() -> int:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(settings.upload_dir).free

    free = await asyncio.to_thread(free_bytes)
    if free - max(0, incoming_size) < max(0, settings.STORAGE_MIN_FREE_BYTES):
        logger.warning(
            "temporary_storage_rejected free_bytes=%s incoming_bytes=%s reserve_bytes=%s",
            free,
            incoming_size,
            settings.STORAGE_MIN_FREE_BYTES,
        )
        raise CustomException("服务器存储空间不足，请联系管理员", status_code=507)

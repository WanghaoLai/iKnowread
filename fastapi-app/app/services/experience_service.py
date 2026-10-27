from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from tortoise.transactions import in_transaction

from app.common.exception_handler import CustomException
from app.dependencies import CurrentAccount
from app.models import (
    AIConfig,
    Account,
    Document,
    ExperienceDocumentShare,
    ExperiencePolicy,
)
from app.schemas.experience import ExperienceSessionPolicy, ExperienceSettingsUpdate
from app.security import hash_password
from app.services import ai_service
from app.services.auth_guard import password_work


DOCUMENT_UPLOAD_LIMIT = 0
STORAGE_QUOTA_BYTES = 0


def _today():
    return datetime.now(timezone.utc).date()


async def _experience_account(*, using_db=None) -> Account:
    query = Account.filter(is_experience=True, role="user").order_by("id")
    if using_db is not None:
        query = query.using_db(using_db)
    account = await query.first()
    if account is None:
        raise CustomException("体验账号尚未初始化", status_code=404)
    return account


async def _policy(account_id: int, *, using_db=None) -> ExperiencePolicy | None:
    query = ExperiencePolicy.filter(account_id=account_id)
    if using_db is not None:
        query = query.using_db(using_db)
    return await query.first()


async def get_policy(current: CurrentAccount) -> ExperiencePolicy | None:
    if not current.is_experience:
        return None
    return await _policy(current.id)


async def public_capability() -> dict:
    account = await Account.filter(is_experience=True, role="user").order_by("id").first()
    if account is None:
        return {"enabled": False, "username": "", "password": ""}
    policy = await _policy(account.id)
    if policy is None or not policy.enabled or not policy.public_password:
        return {"enabled": False, "username": "", "password": ""}
    return {
        "enabled": True,
        "username": account.username,
        "password": policy.public_password,
    }


async def session_policy(current: CurrentAccount) -> dict:
    if not current.is_experience:
        return ExperienceSessionPolicy(is_experience=False).model_dump()
    policy = await _policy(current.id)
    if policy is None:
        return ExperienceSessionPolicy(is_experience=True).model_dump()
    used = policy.ai_used_today if policy.ai_usage_date == _today() else 0
    enabled = bool(policy.enabled)
    limit = max(0, policy.daily_ai_limit)
    return ExperienceSessionPolicy(
        is_experience=True,
        enabled=enabled,
        ai_enabled=enabled and policy.ai_config_id is not None and used < limit,
        daily_ai_limit=limit,
        ai_used_today=used,
        ai_remaining_today=max(0, limit - used),
        show_highlights=enabled and policy.show_highlights,
        show_notes=enabled and policy.show_notes,
        document_upload_limit=DOCUMENT_UPLOAD_LIMIT,
        storage_quota_bytes=STORAGE_QUOTA_BYTES,
        usage_date=_today(),
    ).model_dump()


def deny_experience_write(current: CurrentAccount, action: str = "执行此操作") -> None:
    if current.is_experience:
        raise HTTPException(
            status_code=403,
            detail=f"体验账号仅供阅读与 AI 划词体验，不能{action}",
        )


async def require_enabled(current: CurrentAccount) -> ExperiencePolicy:
    if not current.is_experience:
        raise HTTPException(status_code=403, detail="该接口仅供体验账号使用")
    policy = await _policy(current.id)
    if policy is None or not policy.enabled:
        raise HTTPException(status_code=403, detail="在线体验当前未开放")
    return policy


async def require_document_read(current: CurrentAccount, document: Document) -> None:
    if current.is_admin:
        return
    if current.is_experience:
        await require_enabled(current)
        allowed = await ExperienceDocumentShare.filter(
            account_id=current.id,
            document_id=document.id,
            document__account__role="admin",
            document__deleted_at__isnull=True,
        ).exists()
        if not allowed:
            raise HTTPException(status_code=403, detail="该文档未向体验账号开放")
        return
    if document.account_id != current.id:
        raise HTTPException(status_code=403, detail="无权访问该文档")


async def shared_documents_query(current: CurrentAccount, name: str = ""):
    await require_enabled(current)
    return Document.filter(
        experience_shares__account_id=current.id,
        deleted_at__isnull=True,
        account__role="admin",
        name__contains=name,
    )


async def consume_ai_quota(current: CurrentAccount) -> AIConfig:
    if not current.is_experience:
        return await ai_service.get_config(current.id)
    today = _today()
    async with in_transaction() as connection:
        policy = await ExperiencePolicy.filter(account_id=current.id).using_db(
            connection
        ).select_for_update().first()
        if policy is None or not policy.enabled:
            raise HTTPException(status_code=403, detail="在线体验当前未开放")
        used = policy.ai_used_today if policy.ai_usage_date == today else 0
        if policy.ai_config_id is None:
            raise HTTPException(status_code=503, detail="管理员尚未配置体验 AI")
        if policy.daily_ai_limit <= 0 or used >= policy.daily_ai_limit:
            raise HTTPException(status_code=429, detail="今日 AI 体验次数已用完，请明日再试")
        config = await AIConfig.filter(
            id=policy.ai_config_id,
            account__role="admin",
        ).using_db(connection).first()
        if config is None:
            raise HTTPException(status_code=503, detail="体验 AI 配置不可用，请联系管理员")
        policy.ai_usage_date = today
        policy.ai_used_today = used + 1
        await policy.save(
            using_db=connection,
            update_fields=["ai_usage_date", "ai_used_today", "updated_at"],
        )
    return config


async def _serialize_settings(admin_id: int) -> dict:
    account = await _experience_account()
    policy = await _policy(account.id)
    if policy is None:
        policy = await ExperiencePolicy.create(account_id=account.id)
    shared_ids = await ExperienceDocumentShare.filter(
        account_id=account.id,
        document__account_id=admin_id,
        document__account__role="admin",
        document__deleted_at__isnull=True,
    ).values_list("document_id", flat=True)
    configs = await AIConfig.filter(account_id=admin_id).order_by("-is_active", "name", "id")
    selected_config_id = policy.ai_config_id
    if selected_config_id and not any(item.id == selected_config_id for item in configs):
        selected_config_id = None
    used = policy.ai_used_today if policy.ai_usage_date == _today() else 0
    return {
        "account": {
            "id": account.id,
            "username": account.username,
            "name": account.name,
            "is_experience": True,
        },
        "enabled": policy.enabled,
        "public_password": policy.public_password,
        "ai_config_id": selected_config_id,
        "daily_ai_limit": policy.daily_ai_limit,
        "ai_used_today": used,
        "ai_remaining_today": max(0, policy.daily_ai_limit - used),
        "show_highlights": policy.show_highlights,
        "show_notes": policy.show_notes,
        "document_ids": list(shared_ids),
        "ai_configs": [ai_service.public_config(item) for item in configs],
        "document_upload_limit": DOCUMENT_UPLOAD_LIMIT,
        "storage_quota_bytes": STORAGE_QUOTA_BYTES,
    }


async def admin_settings(admin_id: int) -> dict:
    return await _serialize_settings(admin_id)


async def eligible_documents(
    admin_id: int, name: str, page_num: int, page_size: int
) -> dict:
    query = Document.filter(
        account_id=admin_id,
        account__role="admin",
        deleted_at__isnull=True,
        name__contains=name,
    ).order_by("-created_at", "-id")
    documents = await query.offset((page_num - 1) * page_size).limit(page_size)
    return {
        "total": await query.count(),
        "list": [
            {
                "id": item.id,
                "name": item.name,
                "ext": item.ext,
                "size": item.size,
                "created_at": item.created_at,
            }
            for item in documents
        ],
    }


async def update_settings(admin_id: int, payload: ExperienceSettingsUpdate) -> dict:
    document_ids = payload.document_ids
    if document_ids:
        valid_count = await Document.filter(
            id__in=document_ids,
            account_id=admin_id,
            account__role="admin",
            deleted_at__isnull=True,
        ).count()
        if valid_count != len(document_ids):
            raise CustomException("只能共享当前管理员上传且未删除的文档", status_code=400)
    if payload.ai_config_id is not None and not await AIConfig.filter(
        id=payload.ai_config_id, account_id=admin_id
    ).exists():
        raise CustomException("只能使用当前管理员的 AI 配置", status_code=400)

    password_hash = await password_work(hash_password, payload.public_password)
    async with in_transaction() as connection:
        account = await _experience_account(using_db=connection)
        policy = await ExperiencePolicy.filter(account_id=account.id).using_db(
            connection
        ).select_for_update().first()
        if policy is None:
            policy = await ExperiencePolicy.create(account_id=account.id, using_db=connection)
        password_changed = policy.public_password != payload.public_password
        policy.enabled = payload.enabled
        policy.public_password = payload.public_password
        policy.ai_config_id = payload.ai_config_id
        policy.daily_ai_limit = payload.daily_ai_limit
        policy.show_highlights = payload.show_highlights
        policy.show_notes = payload.show_notes
        if policy.ai_usage_date != _today():
            policy.ai_usage_date = _today()
            policy.ai_used_today = 0
        await policy.save(using_db=connection)
        if password_changed:
            account.password = password_hash
            account.session_version += 1
            await account.save(
                using_db=connection,
                update_fields=["password", "session_version"],
            )
        # Each administrator manages only shares backed by their own documents;
        # saving one admin's page must not revoke another admin's published set.
        owned_document_ids = list(await Document.filter(
            account_id=admin_id
        ).using_db(connection).values_list("id", flat=True))
        if owned_document_ids:
            await ExperienceDocumentShare.filter(
                account_id=account.id,
                document_id__in=owned_document_ids,
            ).using_db(connection).delete()
        if document_ids:
            await ExperienceDocumentShare.bulk_create([
                ExperienceDocumentShare(
                    account_id=account.id,
                    document_id=document_id,
                    shared_by_id=admin_id,
                )
                for document_id in document_ids
            ], using_db=connection)
    return await _serialize_settings(admin_id)

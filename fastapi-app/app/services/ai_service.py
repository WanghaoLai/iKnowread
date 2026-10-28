import asyncio
import json
import os
import tempfile
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from httpx import AsyncClient, HTTPError, TimeoutException
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.config import BASE_DIR, settings
from app.models import Account, AIConfig
from app.schemas.ai import AISettings, AIConfigSave
from app.services.ai_providers import (
    build_request_body,
    get_provider,
    model_list_request,
    parse_model_list,
)
from app.services.ai_guard import ai_request_slot


@lru_cache(maxsize=1)
def key_cipher():
    key: str | bytes = settings.AI_CONFIG_KEY
    if not key:
        # 独立于登录密钥；重启或退出登录不会使配置失效。文件不在上传目录内。
        path = BASE_DIR / "data" / ".ai-config-key"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            key = path.read_bytes().strip()
        else:
            # 先完整写入 0600 临时文件，再原子发布，避免多 worker 读到空文件。
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                temporary_path = handle.name
                handle.write(Fernet.generate_key())
            try:
                try:
                    os.link(temporary_path, path)
                except FileExistsError:
                    pass
                key = path.read_bytes().strip()
            finally:
                os.unlink(temporary_path)
    return Fernet(key)


def public_config(config):
    if not config:
        values = AISettings().model_dump()
        return {
            "id": None,
            **values,
            "provider_name": get_provider(values["provider"]).name,
            "has_api_key": False,
            "is_active": False,
        }
    values = {name: getattr(config, name) for name in AISettings.model_fields}
    return {
        "id": config.id,
        **values,
        "provider_name": get_provider(config.provider).name,
        "has_api_key": bool(config.encrypted_api_key),
        "is_active": config.is_active,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


async def save_config(account_id: int, payload: AIConfigSave):
    """兼容旧单配置接口：更新当前项；没有配置时创建并启用。"""
    existing = await AIConfig.filter(account_id=account_id, is_active=True).first()
    if not existing:
        existing = await AIConfig.filter(account_id=account_id).order_by("id").first()
    if not existing:
        payload.activate = True
        return await create_config(account_id, payload)
    current = {field: getattr(existing, field) for field in AISettings.model_fields}
    provided = payload.model_dump(exclude={"api_key", "activate"}, exclude_unset=True)
    merged = AIConfigSave.model_validate({
        **current,
        **provided,
        "api_key": payload.api_key,
        "activate": True,
    })
    return await update_config(account_id, existing.id, merged)


async def list_configs(account_id: int):
    configs = await AIConfig.filter(account_id=account_id).order_by("-is_active", "-updated_at", "-id")
    return [public_config(config) for config in configs]


def _config_values(payload: AIConfigSave) -> dict:
    return payload.model_dump(exclude={"api_key", "activate"})


async def _lock_account(account_id: int, connection) -> None:
    # 同一账号的配置切换串行执行，避免并发请求产生多个启用项。
    await Account.filter(id=account_id).using_db(connection).select_for_update().first()


async def create_config(account_id: int, payload: AIConfigSave):
    if not payload.api_key:
        raise HTTPException(400, "新建配置请填写 API Key")
    encrypted = key_cipher().encrypt(payload.api_key.get_secret_value().encode()).decode()
    try:
        async with in_transaction() as connection:
            await _lock_account(account_id, connection)
            first = not await AIConfig.filter(account_id=account_id).using_db(connection).exists()
            active = bool(payload.activate or first)
            if active:
                await AIConfig.filter(account_id=account_id).using_db(connection).update(is_active=False)
            config = await AIConfig.create(
                account_id=account_id,
                encrypted_api_key=encrypted,
                is_active=active,
                using_db=connection,
                **_config_values(payload),
            )
    except IntegrityError:
        raise HTTPException(409, "配置名称已存在，请换一个名称") from None
    return public_config(config)


async def _owned_config(account_id: int, config_id: int, *, using_db=None):
    query = AIConfig.filter(id=config_id, account_id=account_id)
    if using_db is not None:
        query = query.using_db(using_db)
    config = await query.first()
    if not config:
        raise HTTPException(404, "模型配置不存在")
    return config


async def update_config(account_id: int, config_id: int, payload: AIConfigSave):
    try:
        async with in_transaction() as connection:
            await _lock_account(account_id, connection)
            config = await _owned_config(account_id, config_id, using_db=connection)
            if config.provider != payload.provider and not payload.api_key:
                raise HTTPException(400, "更换服务商时必须填写新的 API Key")
            for name, value in _config_values(payload).items():
                setattr(config, name, value)
            if payload.api_key:
                config.encrypted_api_key = key_cipher().encrypt(
                    payload.api_key.get_secret_value().encode()
                ).decode()
            if payload.activate:
                await AIConfig.filter(account_id=account_id).using_db(connection).update(is_active=False)
                config.is_active = True
            await config.save(using_db=connection)
    except IntegrityError:
        raise HTTPException(409, "配置名称已存在，请换一个名称") from None
    return public_config(config)


async def activate_config(account_id: int, config_id: int):
    async with in_transaction() as connection:
        await _lock_account(account_id, connection)
        config = await _owned_config(account_id, config_id, using_db=connection)
        await AIConfig.filter(account_id=account_id).using_db(connection).update(is_active=False)
        config.is_active = True
        await config.save(using_db=connection, update_fields=["is_active", "updated_at"])
    return public_config(config)


async def delete_config(account_id: int, config_id: int):
    async with in_transaction() as connection:
        await _lock_account(account_id, connection)
        config = await _owned_config(account_id, config_id, using_db=connection)
        was_active = config.is_active
        await config.delete(using_db=connection)
        replacement = None
        if was_active:
            replacement = await AIConfig.filter(account_id=account_id).using_db(connection).order_by("-updated_at", "-id").first()
            if replacement:
                replacement.is_active = True
                await replacement.save(using_db=connection, update_fields=["is_active", "updated_at"])
    return {"active_config": public_config(replacement) if replacement else None}


async def get_config(account_id: int):
    config = await AIConfig.filter(account_id=account_id, is_active=True).first()
    if not config:
        # 修复异常数据：有配置但没有启用项时，自动恢复最近更新的一项。
        fallback = await AIConfig.filter(account_id=account_id).order_by("-updated_at", "-id").first()
        if fallback:
            await activate_config(account_id, fallback.id)
            config = fallback
    if not config:
        raise HTTPException(400, "请先在 API配置页面保存模型配置")
    return config


def _decrypt_api_key(config) -> str:
    try:
        return key_cipher().decrypt(config.encrypted_api_key.encode()).decode()
    except InvalidToken:
        raise HTTPException(400, "API Key 无法解密，请在 API配置页面重新填写并保存") from None


async def discover_models(config):
    async with ai_request_slot(config.account_id):
        return await _discover_models(config)


async def _discover_models(config):
    provider = get_provider(config.provider)
    api_key = _decrypt_api_key(config)
    url, params = model_list_request(config)
    try:
        async with AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
            async with client.stream(
                "GET", url,
                headers={"Authorization": f"Bearer {api_key}"}, params=params,
            ) as response:
                status_code = response.status_code
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > max(1, settings.AI_MAX_RESPONSE_BYTES):
                        raise HTTPException(502, f"{provider.name} 返回的模型列表过大")
    except TimeoutException:
        raise HTTPException(504, f"获取 {provider.name} 模型列表超时，请重试") from None
    except HTTPError:
        raise HTTPException(502, f"无法连接 {provider.name} 获取模型列表") from None

    # GLM 的兼容入口未正式承诺模型枚举；不支持时回退到维护的常用模型。
    if config.provider == "glm" and status_code in {404, 405}:
        return {
            "models": [{"id": model, "name": "", "context_window": None, "max_output_tokens": None} for model in provider.models],
            "source": "preset",
            "message": "GLM 当前未返回动态模型目录，已加载系统维护的常用模型建议",
        }
    if status_code != 200:
        errors = {
            401: "API Key 无效，无法获取模型列表",
            403: "API Key 没有读取模型列表的权限",
            429: "获取模型列表过于频繁，请稍后重试",
        }
        raise HTTPException(502, errors.get(status_code, f"{provider.name} 未能返回模型列表"))
    try:
        models = parse_model_list(config.provider, json.loads(raw))
    except (ValueError, TypeError):
        models = []
    if not models:
        return {
            "models": [{"id": model, "name": "", "context_window": None, "max_output_tokens": None} for model in provider.models],
            "source": "preset",
            "message": f"{provider.name} 未返回可用的对话模型，已加载常用模型建议",
        }
    return {
        "models": models,
        "source": "provider",
        "message": f"已从 {provider.name} 获取 {len(models)} 个可用模型",
    }


async def _complete(
    config,
    messages: list[dict],
    *,
    test=False,
    system_prompt: str | None = None,
    max_tokens: int | None = None,
):
    api_key = _decrypt_api_key(config)
    effective_system_prompt = system_prompt if system_prompt is not None else config.system_prompt
    body = build_request_body(
        config,
        messages,
        test=test,
        system_prompt=effective_system_prompt,
        max_tokens=32 if test else (max_tokens or config.max_tokens),
    )
    provider = get_provider(config.provider)
    try:
        # 不自动重试付费生成；不跟随重定向，以免将密钥发送给其他主机。
        async with AsyncClient(timeout=120, follow_redirects=False, trust_env=False) as client:
            async with asyncio.timeout(125):
                async with client.stream(
                    "POST",
                    f"{config.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"}, json=body,
                ) as response:
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > max(1, settings.AI_MAX_RESPONSE_BYTES):
                            raise HTTPException(502, "模型返回内容过大，请减少输出长度")
    except (TimeoutException, TimeoutError):
        raise HTTPException(504, "模型响应超时，请稍后重试或减少输出长度") from None
    except HTTPError:
        raise HTTPException(502, f"无法连接 {provider.name}，请稍后重试") from None
    if response.status_code != 200:
        errors = {
            400: "模型参数不被接受，请检查模型名称及输出长度",
            401: "API Key 无效，请重新配置",
            402: f"{provider.name} 账户余额不足，请充值后重试",
            403: "API Key 没有调用该模型的权限",
            404: "模型或接口不存在，请检查 API配置",
            422: "模型参数不被接受，请检查 API配置",
            429: "模型调用频率受限，请稍后重试",
        }
        raise HTTPException(502, errors.get(response.status_code, f"{provider.name} 服务暂时不可用，请稍后重试"))
    try:
        result = json.loads(raw)
        choice = result["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty answer")
        return {
            "content": content,
            "model": config.model,
            "provider": config.provider,
            "provider_name": provider.name,
            "config_id": config.id,
            "config_name": config.name,
            "finish_reason": choice.get("finish_reason", "stop"),
        }
    except (ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(502, "模型未返回有效回答，请重试；深度思考模式可尝试增加输出长度") from None


async def complete(
    config,
    messages: list[dict],
    *,
    test=False,
    system_prompt: str | None = None,
    max_tokens: int | None = None,
):
    async with ai_request_slot(config.account_id):
        return await _complete(
            config,
            messages,
            test=test,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )

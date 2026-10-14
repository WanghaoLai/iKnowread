from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    default_base_url: str
    models: tuple[str, ...]
    api_key_url: str
    base_url_hint: str
    thinking_style: str
    token_field: str = "max_tokens"


PROVIDERS = {
    "deepseek": ProviderSpec(
        id="deepseek",
        name="DeepSeek",
        default_base_url="https://api.deepseek.com",
        models=("deepseek-flash", "deepseek-v4-pro"),
        api_key_url="https://platform.deepseek.com/api_keys",
        base_url_hint="DeepSeek 官方接口；可使用末尾带 /v1 的兼容地址。",
        thinking_style="object",
    ),
    "glm": ProviderSpec(
        id="glm",
        name="智谱 GLM",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        models=("glm-4.7", "glm-4.6", "glm-4.5-air"),
        api_key_url="https://open.bigmodel.cn/usercenter/apikeys",
        base_url_hint="智谱开放平台 OpenAI 兼容接口。",
        thinking_style="object_when_enabled",
    ),
    "mimo": ProviderSpec(
        id="mimo",
        name="Xiaomi MiMo",
        default_base_url="https://api.xiaomimimo.com/v1",
        models=("mimo-v2.6-pro", "mimo-v2.6-flash", "mimo-v2.6-pro-ultraspeed"),
        api_key_url="https://platform.xiaomimimo.com/",
        base_url_hint="Xiaomi MiMo 官方 OpenAI 兼容接口。",
        thinking_style="object",
        token_field="max_completion_tokens",
    ),
    "bailian": ProviderSpec(
        id="bailian",
        name="阿里云百炼",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        models=("qwen3.8-max", "qwen3.8-flash", "qwen-plus"),
        api_key_url="https://bailian.console.aliyun.com/",
        base_url_hint="支持百炼公共兼容地址，也支持包含 WorkspaceId 的 MaaS 地址。",
        thinking_style="boolean",
    ),
}

_BAILIAN_WORKSPACE_HOST = re.compile(
    r"^[a-zA-Z0-9-]+\.(?:cn-beijing|ap-southeast-1|us-east-1|eu-central-1|"
    r"ap-northeast-1|cn-hongkong)\.maas\.aliyuncs\.com$"
)


def get_provider(provider: str) -> ProviderSpec:
    try:
        return PROVIDERS[provider]
    except KeyError:
        raise ValueError("不支持的大模型服务商") from None


def validate_base_url(provider: str, value: str) -> str:
    """只允许厂商官方 HTTPS 入口，防止保存的密钥被发往任意主机。"""
    spec = get_provider(provider)
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.port not in (None, 443)
    ):
        raise ValueError(f"请使用 {spec.name} 官方 HTTPS 接口地址")

    host = parsed.hostname.lower()
    path = parsed.path.rstrip("/")
    valid = False
    if provider == "deepseek":
        valid = host == "api.deepseek.com" and path in ("", "/v1")
    elif provider == "glm":
        valid = host == "open.bigmodel.cn" and path == "/api/paas/v4"
    elif provider == "mimo":
        valid = host == "api.xiaomimimo.com" and path == "/v1"
    elif provider == "bailian":
        valid_host = host in {"dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com"} or bool(
            _BAILIAN_WORKSPACE_HOST.fullmatch(host)
        )
        valid = valid_host and path == "/compatible-mode/v1"
    if not valid:
        raise ValueError(f"接口地址必须是 {spec.name} 的官方兼容接口")
    return value


def provider_catalog() -> list[dict]:
    return [
        {
            "id": spec.id,
            "name": spec.name,
            "default_base_url": spec.default_base_url,
            "models": list(spec.models),
            "api_key_url": spec.api_key_url,
            "base_url_hint": spec.base_url_hint,
        }
        for spec in PROVIDERS.values()
    ]


def model_list_request(config) -> tuple[str, list[tuple[str, str | int]]]:
    """返回厂商模型目录地址；输入的 Base URL 已由 validate_base_url 限定为官方域名。"""
    if config.provider == "bailian":
        parsed = urlsplit(config.base_url)
        return (
            f"https://{parsed.netloc}/api/v1/models",
            [
                ("page_no", 1),
                ("page_size", 100),
                ("capabilities", "TG"),
                ("capabilities", "Reasoning"),
                ("supports", "inference"),
            ],
        )
    return f"{config.base_url}/models", []


def parse_model_list(provider: str, result: dict) -> list[dict]:
    if provider == "bailian":
        raw_models = result.get("output", {}).get("models", [])
        id_field = "model"
    else:
        raw_models = result.get("data", [])
        id_field = "id"
    if not isinstance(raw_models, list):
        return []

    models = []
    seen = set()
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        model_id = item.get(id_field)
        if not isinstance(model_id, str) or not re.fullmatch(r"[a-zA-Z0-9._:/-]{1,100}", model_id):
            continue
        # MiMo 的目录还包含 ASR/TTS；当前系统的 Chat Completions 只展示生成模型。
        if provider == "mimo" and ("-asr" in model_id or "-tts" in model_id):
            continue
        if model_id in seen:
            continue
        seen.add(model_id)
        model_info = item.get("model_info") if isinstance(item.get("model_info"), dict) else {}
        models.append({
            "id": model_id,
            "name": item.get("name") if isinstance(item.get("name"), str) else "",
            "context_window": item.get("context_window") or model_info.get("context_window"),
            "max_output_tokens": item.get("max_output_tokens") or model_info.get("max_output_tokens"),
        })
    return sorted(models, key=lambda item: item["id"])


def build_request_body(
    config,
    messages: list[dict],
    *,
    test: bool,
    system_prompt: str,
    max_tokens: int,
) -> dict:
    spec = get_provider(config.provider)
    body = {
        "model": config.model,
        "messages": ([{"role": "system", "content": system_prompt}] if system_prompt else []) + messages,
        "stream": False,
        spec.token_field: max_tokens,
    }
    thinking = bool(config.thinking and not test)
    if spec.thinking_style == "object":
        body["thinking"] = {"type": "enabled" if thinking else "disabled"}
    elif spec.thinking_style == "object_when_enabled" and thinking:
        body["thinking"] = {"type": "enabled"}
    elif spec.thinking_style == "boolean":
        body["enable_thinking"] = thinking
    if not thinking:
        body["temperature"] = config.temperature
    return body

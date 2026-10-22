from dataclasses import dataclass
import json
import logging
import time

import httpx

from app.config import settings


class CrawlerError(RuntimeError):
    pass


def _public_crawl_failure(raw_message: object) -> tuple[str, str]:
    """Map untrusted crawler diagnostics to a stable public failure.

    Crawl4AI may include browser errors, target URLs, proxy addresses or
    internal service details in ``error_message``. Only a coarse category is
    retained for logs and the database; the raw value never crosses this
    trust boundary.
    """
    normalized = str(raw_message or "").casefold()
    if "timeout" in normalized or "timed out" in normalized:
        return "timeout", "网页抓取超时"
    if "robots" in normalized or "forbidden" in normalized or "denied" in normalized:
        return "target_rejected", "目标网页拒绝抓取"
    return "upstream_failure", "网页抓取失败"


@dataclass(frozen=True)
class CrawledPage:
    markdown: str
    title: str


def availability_error() -> str | None:
    if not settings.CRAWLER_ENABLED:
        return "网页收藏服务未启用"
    if not settings.CRAWLER_API_TOKEN.strip():
        return "网页收藏服务未配置访问令牌"
    return None


_probe_at = 0.0
_probe_error: str | None = "网页收藏服务尚未完成健康检查"
_PROBE_TTL_SECONDS = 5.0


async def runtime_availability_error(*, force: bool = False) -> str | None:
    """Return the live crawler state without making it a backend readiness dependency."""
    global _probe_at, _probe_error
    if error := availability_error():
        return error
    now = time.monotonic()
    if not force and now - _probe_at < _PROBE_TTL_SECONDS:
        return _probe_error
    endpoint = settings.CRAWLER_BASE_URL.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(3.0, connect=2.0), trust_env=False
        ) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException):
        _probe_error = "网页收藏服务暂不可用"
    else:
        _probe_error = None
    _probe_at = now
    return _probe_error


def reset_probe_cache() -> None:
    """Reset process-local health state after configuration changes and in tests."""
    global _probe_at, _probe_error
    _probe_at = 0.0
    _probe_error = "网页收藏服务尚未完成健康检查"


async def crawl(url: str) -> CrawledPage:
    if error := availability_error():
        raise CrawlerError(error)
    endpoint = settings.CRAWLER_BASE_URL.rstrip("/") + "/crawl"
    headers = {
        "Authorization": f"Bearer {settings.CRAWLER_API_TOKEN.strip()}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(
        max(1, settings.CRAWLER_TIMEOUT_SECONDS), connect=10, pool=10, write=10
    )
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            async with client.stream(
                "POST", endpoint, headers=headers,
                json={"urls": [url], "browser_config": {}, "crawler_config": {}},
            ) as response:
                if response.status_code != 200:
                    raise CrawlerError(f"抓取服务返回 HTTP {response.status_code}")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max(1, settings.CRAWLER_MAX_RESPONSE_BYTES):
                        raise CrawlerError("抓取结果超过服务端允许的大小")
                    chunks.append(chunk)
    except CrawlerError:
        raise
    except httpx.TimeoutException as exc:
        raise CrawlerError("网页抓取超时") from exc
    except httpx.HTTPError as exc:
        raise CrawlerError("网页抓取服务暂时不可用") from exc
    try:
        payload = json.loads(b"".join(chunks))
        if not payload.get("success") or not payload.get("results"):
            raise CrawlerError("网页抓取失败")
        result = payload["results"][0]
        if not result.get("success", True):
            category, public_message = _public_crawl_failure(result.get("error_message"))
            # Log the category only. The raw crawler diagnostic can contain
            # credentials, internal hosts or browser command-line details.
            logging.getLogger(__name__).warning(
                "Crawler returned a failed result category=%s", category
            )
            raise CrawlerError(public_message)
        markdown_value = result.get("markdown")
        markdown = markdown_value.get("raw_markdown", "") if isinstance(markdown_value, dict) else markdown_value or ""
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        title = str(metadata.get("title") or "").strip()
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError, IndexError, KeyError) as exc:
        raise CrawlerError("抓取服务返回了无效结果") from exc
    if not isinstance(markdown, str) or not markdown.strip():
        raise CrawlerError("网页未提取到可阅读内容")
    return CrawledPage(markdown=markdown, title=title)

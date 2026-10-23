import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit


_ALLOWED_PORTS = {80, 443}

# Chromium 按 WHATWG 规范把十/十六/八进制 IPv4 变体（如 2130706433、
# 0x7f000001、0177.0.0.1）归一化后再连接，而 Python 的 ipaddress 只认
# 标准点分格式。仅由数字、点、十六进制字符组成且含数字的 host 一律
# 按可疑 IP 变体拒绝——正常域名不会落入该字符集。
_IP_LIKE_HOST = re.compile(r"^[0-9a-fx.]+$", re.IGNORECASE)


def normalize_public_url(value: str) -> str:
    """词法防线：协议、凭据、端口白名单、字面 IP 与 localhost 变体。

    域名是否解析到内网由 assert_resolved_public 在服务层把关。
    """
    raw = value.strip()
    if len(raw) > 2048:
        raise ValueError("URL 不能超过 2048 个字符")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL 格式无效") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("仅支持 http 或 https URL")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("URL 主机无效，且不能包含用户名或密码")
    if port is not None and port not in _ALLOWED_PORTS:
        raise ValueError("仅支持 80 或 443 端口的 URL")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("不允许访问本机或局域网地址")
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        if any(ch.isdigit() for ch in host) and _IP_LIKE_HOST.match(host):
            raise ValueError("不允许访问本机或局域网地址") from None
    else:
        if not address.is_global:
            raise ValueError("不允许访问本机或局域网地址")
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc = f"{netloc}:{port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


async def _resolve_host(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, None, type=socket.SOCK_STREAM
    )
    return [info[4][0] for info in infos]


async def assert_resolved_public(host: str) -> None:
    """Early rejection before a task enters the durable crawler queue.

    This check reduces abusive queue traffic but is not the SSRF boundary: a
    resolver result checked here cannot be reused safely by a separate browser.
    The pinned Crawl4AI 0.9.4 image validates and pins the address it actually
    dials for every request and redirect hop. Deployment additionally keeps
    that browser container off the backend and database networks.
    """
    stripped = host.strip("[]")
    try:
        address = ipaddress.ip_address(stripped)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("不允许访问本机或局域网地址")
        return
    try:
        records = await _resolve_host(stripped)
    except OSError as exc:
        # 域名不存在等解析失败不能向上冒泡成 500，统一收敛为可读的拒绝。
        raise ValueError("域名无法解析，请检查 URL") from exc
    if not records:
        raise ValueError("域名无法解析，请检查 URL")
    for resolved in records:
        address = ipaddress.ip_address(resolved)
        if not address.is_global:
            raise ValueError("不允许访问本机或局域网地址")

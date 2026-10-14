"""Password hashing and signed authentication tokens.

Only standard-library primitives are used so the security boundary does not
depend on an optional runtime package. Tokens are signed, short lived, and
bound to the account's current password hash so a password change immediately
invalidates existing sessions.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
import warnings

from app.config import settings

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000
SESSION_COOKIE = "iknowread_session"
SESSION_MAX_AGE = 8 * 60 * 60

_runtime_secret: str | None = None


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret() -> bytes:
    global _runtime_secret
    configured = settings.AUTH_SECRET.strip()
    if configured:
        return configured.encode("utf-8")
    if not settings.DEBUG:
        raise RuntimeError("生产环境必须配置 AUTH_SECRET")
    if _runtime_secret is None:
        _runtime_secret = secrets.token_urlsafe(48)
        warnings.warn("未配置 AUTH_SECRET，已生成仅本次进程有效的开发密钥")
    return _runtime_secret.encode("utf-8")


def validate_security_config() -> None:
    _secret()
    settings.cors_origin_list


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("密码不能为空")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    if password is None or stored is None:
        return False
    if not stored.startswith(f"{PASSWORD_SCHEME}$"):
        # One-time compatibility path for databases created before hashing was
        # introduced. Startup/login migrates the value immediately afterwards.
        return hmac.compare_digest(password, stored)
    try:
        _, iterations, salt, expected = stored.split("$", 3)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), _b64decode(salt), int(iterations)
        )
        return hmac.compare_digest(actual, _b64decode(expected))
    except (TypeError, ValueError):
        return False


def password_needs_rehash(stored: str | None) -> bool:
    if not stored or not stored.startswith(f"{PASSWORD_SCHEME}$"):
        return True
    try:
        return int(stored.split("$", 3)[1]) < PASSWORD_ITERATIONS
    except (IndexError, ValueError):
        return True


def _password_fingerprint(stored: str) -> str:
    return hmac.new(_secret(), stored.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def issue_session_token(
    account_id: int, role: str, password_hash: str, session_version: int
) -> str:
    payload = {
        "v": 2,
        "sub": account_id,
        "role": role,
        "exp": int(time.time()) + SESSION_MAX_AGE,
        "pwd": _password_fingerprint(password_hash),
        "sv": session_version,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64encode(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def decode_session_token(token: str) -> dict:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(signature)):
            raise ValueError("签名无效")
        payload = json.loads(_b64decode(encoded))
        if payload.get("v") != 2 or int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("会话已过期")
        if (
            payload.get("role") not in {"admin", "user"}
            or not isinstance(payload.get("sub"), int)
            or not isinstance(payload.get("sv"), int)
            or payload["sv"] < 1
        ):
            raise ValueError("会话内容无效")
        return payload
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("登录状态无效或已过期") from exc


def session_matches_account(
    payload: dict, password_hash: str, session_version: int
) -> bool:
    return (
        hmac.compare_digest(
            str(payload.get("pwd", "")), _password_fingerprint(password_hash)
        )
        and payload.get("sv") == session_version
    )

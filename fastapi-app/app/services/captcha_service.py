"""Short-lived, one-time image CAPTCHA challenges for interactive login."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.common.exception_handler import CustomException
from app.config import settings


_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_MAX_CHALLENGES = 4096
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


@dataclass(frozen=True)
class _Challenge:
    digest: bytes
    expires_at: float


_challenges: OrderedDict[str, _Challenge] = OrderedDict()
_lock = asyncio.Lock()


def _new_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(5))


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.strip().upper().encode("ascii", errors="ignore")).digest()


def _randint(start: int, end: int) -> int:
    return start + secrets.randbelow(end - start + 1)


def _font(size: int):
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10 compatibility for local development.
        return ImageFont.load_default()


def _render_png(code: str) -> str:
    width, height = 156, 52
    image = Image.new("RGB", (width, height), (246, 250, 253))
    draw = ImageDraw.Draw(image)

    for _ in range(5):
        color = (_randint(120, 190), _randint(155, 210), _randint(180, 225))
        draw.line(
            [(_randint(-10, width // 3), _randint(0, height)),
             (_randint(width * 2 // 3, width + 10), _randint(0, height))],
            fill=color,
            width=_randint(1, 2),
        )
    for _ in range(70):
        draw.point(
            (_randint(0, width - 1), _randint(0, height - 1)),
            fill=(_randint(130, 220), _randint(150, 225), _randint(160, 230)),
        )

    font = _font(32)
    for index, character in enumerate(code):
        glyph = Image.new("RGBA", (40, 48), (255, 255, 255, 0))
        glyph_draw = ImageDraw.Draw(glyph)
        bounds = glyph_draw.textbbox((0, 0), character, font=font)
        glyph_width = bounds[2] - bounds[0]
        glyph_height = bounds[3] - bounds[1]
        glyph_draw.text(
            ((40 - glyph_width) / 2 - bounds[0], (48 - glyph_height) / 2 - bounds[1]),
            character,
            font=font,
            fill=(_randint(20, 55), _randint(65, 110), _randint(105, 155), 255),
        )
        image.paste(glyph, (8 + index * 29, _randint(1, 4)), glyph)

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _remove_expired(now: float) -> None:
    expired = [key for key, item in _challenges.items() if item.expires_at <= now]
    for key in expired:
        _challenges.pop(key, None)


async def issue(code: str | None = None) -> dict:
    """Create a challenge. ``code`` is accepted for deterministic automated tests."""
    value = (code or _new_code()).strip().upper()
    if len(value) != 5 or any(character not in _ALPHABET for character in value):
        raise ValueError("验证码必须由 5 个无歧义字符组成")
    challenge_id = secrets.token_urlsafe(24)
    now = time.monotonic()
    async with _lock:
        _remove_expired(now)
        _challenges[challenge_id] = _Challenge(
            digest=_digest(value),
            expires_at=now + max(30, settings.CAPTCHA_TTL_SECONDS),
        )
        while len(_challenges) > _MAX_CHALLENGES:
            _challenges.popitem(last=False)
    return {
        "captcha_id": challenge_id,
        "image": _render_png(value),
        "expires_in": max(30, settings.CAPTCHA_TTL_SECONDS),
    }


async def verify(challenge_id: str, code: str) -> None:
    now = time.monotonic()
    async with _lock:
        _remove_expired(now)
        challenge = _challenges.pop(challenge_id, None)
    if challenge is None or challenge.expires_at <= now:
        raise CustomException("验证码已失效，请点击图片刷新后重试", status_code=400)
    if not hmac.compare_digest(challenge.digest, _digest(code)):
        raise CustomException("验证码错误，请重新输入", status_code=400)


async def clear() -> None:
    async with _lock:
        _challenges.clear()

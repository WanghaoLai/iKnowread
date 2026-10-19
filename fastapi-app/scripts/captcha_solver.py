"""Solve the local image CAPTCHA for deployment smoke tests using Tesseract."""
from __future__ import annotations

import base64
import io
import json
import re
import subprocess
import sys

from PIL import Image, ImageEnhance, ImageOps


ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def solve_image_data_url(image_url: str) -> str:
    _, encoded = image_url.split(",", 1)
    image = Image.open(io.BytesIO(base64.b64decode(encoded))).convert("L")
    image = ImageOps.autocontrast(image).point(
        lambda value: 0 if value < 115 else 255
    ).resize(
        (image.width * 4, image.height * 4), Image.Resampling.LANCZOS
    )
    image = ImageEnhance.Contrast(image).enhance(1.8)
    output = io.BytesIO()
    image.save(output, format="PNG")
    result = subprocess.run(
        [
            "tesseract", "stdin", "stdout", "--psm", "7",
            "-c", f"tessedit_char_whitelist={ALPHABET}",
        ],
        input=output.getvalue(),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return re.sub(f"[^{ALPHABET}]", "", result.stdout.decode("utf-8").upper())


def solve_response(payload: dict) -> tuple[str, str]:
    data = payload["data"]
    code = solve_image_data_url(data["image"])
    if len(code) != 5:
        raise RuntimeError("自动化验收无法识别验证码")
    return data["captcha_id"], code


if __name__ == "__main__":
    challenge_id, challenge_code = solve_response(json.load(sys.stdin))
    print(challenge_id, challenge_code)

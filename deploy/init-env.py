#!/usr/bin/env python3
"""Generate deployment secrets once; never overwrite an existing .env."""
import argparse
import os
from pathlib import Path
import re
import secrets

parser = argparse.ArgumentParser(description="生成 Docker 部署配置，不覆盖已有 .env")
parser.add_argument("domain", help="域名，例如 read.example.com（不含 https://）")
parser.add_argument("email", help="证书联系人邮箱")
args = parser.parse_args()
if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", args.domain) or "." not in args.domain:
    parser.error("请填写纯域名，不要包含协议、端口、空格或路径")
if not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", args.email):
    parser.error("请填写有效邮箱")
root = Path(__file__).resolve().parent.parent
os.umask(0o077)
try:
    with (root / ".env").open("x", encoding="utf-8") as output:
        output.write(
            f"DOMAIN={args.domain.lower()}\n"
            f"ACME_EMAIL={args.email}\n"
            f"DB_PASSWORD={secrets.token_hex(32)}\n"
            f"MYSQL_ROOT_PASSWORD={secrets.token_hex(32)}\n"
            f"AUTH_SECRET={secrets.token_hex(32)}\n"
            "OCR_ENABLED=false\n"
            "ALLOW_REGISTRATION=false\n"
            "USER_STORAGE_QUOTA_BYTES=2147483648\n"
            "USER_DOCUMENT_LIMIT=200\n"
            "USER_TOTAL_DOCUMENT_LIMIT=400\n"
            "USER_NOTE_LIMIT=10000\n"
            "USER_HIGHLIGHT_LIMIT=10000\n"
            "DOCUMENT_HIGHLIGHT_LIMIT=1000\n"
            "STORAGE_MIN_FREE_BYTES=2147483648\n"
            "APP_TAG=local\n"
        )
except FileExistsError:
    parser.exit(1, "已有 .env，未做修改；如需调整请使用 nano .env。\n")
print("已生成项目根目录 .env（权限 600），请安全备份；没有显示任何密钥。")

"""Export and resolve the shared backend/frontend API contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api_paths import API_CONTRACT

CONTRACT_FILE = (
    Path(__file__).resolve().parents[2] / "vue/src/api/apiContract.json"
)

DOCUMENT_NAMES = {
    "list": "documents.list",
    "upload": "documents.upload",
    "delete": "documents.delete",
    "preview": "documents.preview",
    "download": "documents.download",
    "ocr": "documents.ocr",
    "ocr_status": "documents.ocr_status",
    "processing_status": "documents.processing_status",
    "recycle_list": "documents.recycle_list",
    "restore": "documents.restore",
    "purge": "documents.purge",
}


def serialized_contract() -> str:
    return json.dumps(API_CONTRACT, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_contract() -> None:
    CONTRACT_FILE.write_text(serialized_contract(), encoding="utf-8")


def check_contract() -> None:
    if not CONTRACT_FILE.is_file() or CONTRACT_FILE.read_text(encoding="utf-8") != serialized_contract():
        raise SystemExit(
            "frontend API contract is stale; run: "
            "cd fastapi-app && python scripts/document_contract.py --write"
        )


def document_path(name: str, document_id: int | None = None, *, prefix: str = "") -> str:
    try:
        path = API_CONTRACT[DOCUMENT_NAMES[name]]["path"]
    except KeyError as exc:
        raise ValueError(f"unknown document endpoint: {name}") from exc
    if "{doc_id}" in path:
        if document_id is None or int(document_id) < 1:
            raise ValueError(f"document endpoint {name} requires a positive id")
        path = path.replace("{doc_id}", str(int(document_id)))
    return f"{prefix.rstrip('/')}{path}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", nargs="?", choices=sorted(DOCUMENT_NAMES))
    parser.add_argument("document_id", nargs="?", type=int)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write:
        write_contract()
        return
    if args.check:
        check_contract()
        return
    if not args.name:
        parser.error("name is required unless --write or --check is used")
    print(document_path(args.name, args.document_id, prefix=args.prefix))


if __name__ == "__main__":
    main()

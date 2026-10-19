"""Resolve document API paths for integration and Docker smoke scripts."""

from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path


CONTRACT_FILE = (
    Path(__file__).resolve().parents[2] / "vue/src/api/documentContract.json"
)


@lru_cache(maxsize=1)
def _contract() -> dict[str, dict[str, str]]:
    return json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))


def document_path(name: str, document_id: int | None = None, *, prefix: str = "") -> str:
    try:
        path = _contract()[name]["path"]
    except KeyError as exc:
        raise ValueError(f"unknown document endpoint: {name}") from exc
    if "{doc_id}" in path:
        if document_id is None or int(document_id) < 1:
            raise ValueError(f"document endpoint {name} requires a positive id")
        path = path.replace("{doc_id}", str(int(document_id)))
    return f"{prefix.rstrip('/')}{path}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", choices=sorted(_contract()))
    parser.add_argument("document_id", nargs="?", type=int)
    parser.add_argument("--prefix", default="")
    args = parser.parse_args()
    print(document_path(args.name, args.document_id, prefix=args.prefix))


if __name__ == "__main__":
    main()

from abc import ABC, abstractmethod
from datetime import datetime
from collections.abc import Iterable
from typing import BinaryIO

from starlette.responses import Response


class StorageBackend(ABC):
    """Operations required by application services; no local-path escape hatch."""

    @abstractmethod
    async def save(self, filename: str, file: BinaryIO, subdir: str = "") -> str: ...

    @abstractmethod
    def open(self, key: str) -> BinaryIO: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def size(self, key: str) -> int: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def move(self, old_key: str, new_key: str) -> None: ...

    @abstractmethod
    def stage(self, key: str) -> str | None: ...

    @abstractmethod
    def restore(self, staged_key: str, original_key: str) -> None: ...

    @abstractmethod
    def stage_tree(self, prefix: str) -> str | None: ...

    @abstractmethod
    def restore_tree(self, staged_prefix: str, original_prefix: str) -> None: ...

    @abstractmethod
    def delete_tree(self, prefix: str) -> None: ...

    @abstractmethod
    def iter_keys(self, prefix: str = "") -> list[str]: ...

    @abstractmethod
    def iter_keys_iter(self, prefix: str = "") -> Iterable[str]: ...

    @abstractmethod
    def modified_at(self, key: str) -> datetime: ...

    @abstractmethod
    def response(
        self, key: str, *, filename: str | None = None,
        media_type: str | None = None, inline: bool = False,
    ) -> Response: ...

    @staticmethod
    def safe_key(key: str) -> str:
        name = key.replace("\\", "/").split("/")[-1].strip()
        if not name or name in (".", "..") or ".." in name:
            from app.common.exception_handler import CustomException
            raise CustomException("非法文件名")
        name = "".join("_" if ord(character) < 32 else character for character in name)
        # LocalStorage prefixes 13 ASCII bytes. Keep the final component below
        # common 255-byte filesystem limits while preserving a short extension.
        if len(name.encode("utf-8")) <= 220:
            return name
        dot = name.rfind(".")
        extension = name[dot:] if 0 < dot and len(name[dot:].encode("utf-8")) <= 20 else ""
        stem = name[:dot] if extension else name
        budget = 220 - len(extension.encode("utf-8"))
        encoded = stem.encode("utf-8")[:budget]
        while True:
            try:
                stem = encoded.decode("utf-8")
                break
            except UnicodeDecodeError:
                encoded = encoded[:-1]
        return (stem.rstrip() or "file") + extension

    @staticmethod
    def safe_path(key: str) -> str:
        parts = [part for part in key.replace("\\", "/").split("/") if part not in ("", ".")]
        if not parts or any(part == ".." for part in parts):
            from app.common.exception_handler import CustomException
            raise CustomException("非法文件路径")
        return "/".join(parts)

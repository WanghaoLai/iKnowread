from abc import ABC, abstractmethod
from datetime import datetime
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
    def modified_at(self, key: str) -> datetime: ...

    @abstractmethod
    def response(
        self, key: str, *, filename: str | None = None,
        media_type: str | None = None, inline: bool = False,
    ) -> Response: ...

    @staticmethod
    def safe_key(key: str) -> str:
        name = key.replace("\\", "/").split("/")[-1]
        if not name or name in (".", "..") or ".." in name:
            from app.common.exception_handler import CustomException
            raise CustomException("非法文件名")
        return name

    @staticmethod
    def safe_path(key: str) -> str:
        parts = [part for part in key.replace("\\", "/").split("/") if part not in ("", ".")]
        if not parts or any(part == ".." for part in parts):
            from app.common.exception_handler import CustomException
            raise CustomException("非法文件路径")
        return "/".join(parts)

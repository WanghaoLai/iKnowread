import asyncio
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from starlette.responses import FileResponse

from app.common.exception_handler import CustomException
from app.config import settings
from app.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self):
        self._root = settings.upload_dir
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._root / self.safe_path(key)

    async def save(self, filename: str, file: BinaryIO, subdir: str = "") -> str:
        name = self.safe_key(filename)
        prefix = f"{self.safe_path(subdir)}/" if subdir else ""
        key = f"{prefix}{uuid.uuid4().hex[:12]}_{name}"
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)

        def copy() -> None:
            with destination.open("wb") as output:
                shutil.copyfileobj(file, output)

        try:
            await asyncio.to_thread(copy)
        except Exception:
            destination.unlink(missing_ok=True)
            self._remove_empty_parents(destination.parent)
            raise
        return key

    def open(self, key: str) -> BinaryIO:
        path = self._path(key)
        if not path.is_file():
            raise CustomException("文件不存在", status_code=404)
        return path.open("rb")

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def size(self, key: str) -> int:
        path = self._path(key)
        if not path.is_file():
            raise CustomException("文件不存在", status_code=404)
        return path.stat().st_size

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()
            self._remove_empty_parents(path.parent)

    def move(self, old_key: str, new_key: str) -> None:
        source = self._path(old_key)
        if not source.is_file():
            raise CustomException("文件不存在", status_code=404)
        destination = self._path(new_key)
        if destination.exists():
            raise CustomException("目标文件已存在", status_code=409)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        self._remove_empty_parents(source.parent)

    def stage(self, key: str) -> str | None:
        if not self.exists(key):
            return None
        staged = f"_trash/{uuid.uuid4().hex}/file/{self.safe_path(key)}"
        self.move(key, staged)
        return staged

    def restore(self, staged_key: str, original_key: str) -> None:
        self.move(staged_key, original_key)

    def stage_tree(self, prefix: str) -> str | None:
        source = self._path(prefix)
        if not source.is_dir():
            return None
        staged = f"_trash/{uuid.uuid4().hex}/tree/{self.safe_path(prefix)}"
        destination = self._path(staged)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        self._remove_empty_parents(source.parent)
        return staged

    def restore_tree(self, staged_prefix: str, original_prefix: str) -> None:
        source = self._path(staged_prefix)
        if not source.is_dir():
            return
        destination = self._path(original_prefix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise CustomException("恢复文件目录时目标已存在", status_code=409)
        shutil.move(str(source), str(destination))
        self._remove_empty_parents(source.parent)

    def delete_tree(self, prefix: str) -> None:
        path = self._path(prefix)
        if path.is_dir():
            shutil.rmtree(path)
            self._remove_empty_parents(path.parent)

    def iter_keys(self, prefix: str = "") -> list[str]:
        base = self._path(prefix) if prefix else self._root
        if not base.exists():
            return []
        return [path.relative_to(self._root).as_posix() for path in base.rglob("*") if path.is_file()]

    def modified_at(self, key: str) -> datetime:
        return datetime.fromtimestamp(self._path(key).stat().st_mtime, timezone.utc)

    def response(self, key: str, *, filename: str | None = None, media_type: str | None = None, inline: bool = False):
        path = self._path(key)
        if not path.is_file():
            raise CustomException("文件不存在", status_code=404)
        headers = {"Content-Disposition": "inline"} if inline else None
        return FileResponse(path=path, filename=None if inline else filename, media_type=media_type, headers=headers)

    def _remove_empty_parents(self, path: Path) -> None:
        while path != self._root and path.is_dir():
            try:
                path.rmdir()
            except OSError:
                break
            path = path.parent

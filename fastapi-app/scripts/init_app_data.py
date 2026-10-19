"""Import the legacy bind-mounted app data into the managed volume once."""
from __future__ import annotations

import os
from pathlib import Path
import shutil


MARKER_NAME = ".legacy-bind-imported"


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def migrate_legacy_data(legacy: Path, target: Path) -> bool:
    target.mkdir(parents=True, exist_ok=True)
    marker = target / MARKER_NAME
    legacy_items = list(legacy.iterdir()) if legacy.is_dir() else []
    if not legacy_items or marker.exists():
        return False
    if any(path.name == MARKER_NAME for path in legacy_items):
        raise RuntimeError(f"旧数据目录包含保留名称 {MARKER_NAME}")
    if any(path.is_symlink() for path in legacy.rglob("*")):
        raise RuntimeError("旧数据目录包含符号链接，拒绝自动导入")
    if any(target.iterdir()):
        raise RuntimeError("新持久卷已有数据，拒绝与旧 bind mount 自动合并")

    copied: list[Path] = []
    try:
        for source in legacy_items:
            destination = target / source.name
            # Register the destination before copying. copytree/copy2 may leave
            # a partial path behind when storage fills or an I/O error occurs.
            copied.append(destination)
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
        marker.write_text("legacy runtime/app-data imported\n", encoding="utf-8")
    except BaseException:
        for destination in reversed(copied):
            _remove(destination)
        marker.unlink(missing_ok=True)
        raise
    return True


def main() -> None:
    legacy = Path(os.environ.get("LEGACY_APP_DATA_DIR", "/legacy-source/runtime/app-data"))
    target = Path(os.environ.get("APP_DATA_DIR", "/app/data"))
    imported = migrate_legacy_data(legacy, target)
    print("app-data-init: legacy data imported" if imported else "app-data-init: no import needed")


if __name__ == "__main__":
    main()

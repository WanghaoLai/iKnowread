"""Validate restored migration records against the source saved in a backup."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys


MIGRATION_FILE = re.compile(r"^v(?P<version>[0-9]{3})_[^/]+\.py$")


def source_migrations(directory: Path) -> dict[int, str]:
    migrations: dict[int, str] = {}
    for path in directory.iterdir():
        match = MIGRATION_FILE.fullmatch(path.name)
        if not match or not path.is_file():
            continue
        version = int(match.group("version"))
        if version in migrations:
            raise ValueError(f"备份源码包含重复迁移版本：v{version:03d}")
        migrations[version] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not migrations:
        raise ValueError("备份源码中没有迁移文件")
    expected = list(range(1, max(migrations) + 1))
    if sorted(migrations) != expected:
        raise ValueError("备份源码的迁移版本不连续")
    return migrations


def applied_migrations(path: Path) -> dict[int, str]:
    applied: dict[int, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        columns = raw.split("\t", 1)
        if not columns or not columns[0].isdigit():
            raise ValueError(f"迁移记录第 {line_number} 行格式无效")
        version = int(columns[0])
        checksum = columns[1].strip() if len(columns) == 2 else ""
        if version in applied:
            raise ValueError(f"数据库包含重复迁移版本：v{version:03d}")
        if checksum and not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError(f"迁移 v{version:03d} 的校验和格式无效")
        applied[version] = checksum
    if not applied:
        raise ValueError("恢复后的数据库没有迁移记录")
    expected = list(range(1, max(applied) + 1))
    if sorted(applied) != expected:
        raise ValueError("恢复后的数据库迁移版本不连续")
    return applied


def verify(source_directory: Path, applied_path: Path) -> tuple[int, int, int]:
    available = source_migrations(source_directory)
    applied = applied_migrations(applied_path)
    if max(applied) > max(available):
        raise ValueError("数据库迁移版本高于备份源码，无法用该源码恢复")
    for version, recorded_checksum in applied.items():
        if recorded_checksum and recorded_checksum != available[version]:
            raise ValueError(f"迁移 v{version:03d} 的数据库校验和与备份源码不一致")
    return len(applied), len(available), len(available) - len(applied)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "用法: python verify_backup_migrations.py MIGRATION_DIR APPLIED_TSV"
        )
    try:
        applied, available, pending = verify(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"备份迁移校验失败：{exc}") from exc
    print(
        "backup-migration-check: PASS "
        f"(applied={applied}, source={available}, pending={pending})"
    )


if __name__ == "__main__":
    main()

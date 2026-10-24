import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.verify_backup_migrations import verify


class BackupMigrationVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.migrations = self.root / "migrations"
        self.migrations.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def add_migration(self, version: int) -> str:
        path = self.migrations / f"v{version:03d}_example.py"
        path.write_text(f"VERSION = {version}\n", encoding="utf-8")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write_applied(self, rows: list[tuple[int, str]]) -> Path:
        path = self.root / "applied.tsv"
        path.write_text(
            "".join(f"{version}\t{checksum}\n" for version, checksum in rows),
            encoding="utf-8",
        )
        return path

    def test_accepts_pending_migrations_in_new_source(self):
        first = self.add_migration(1)
        second = self.add_migration(2)
        self.add_migration(3)
        result = verify(
            self.migrations,
            self.write_applied([(1, first), (2, second)]),
        )
        self.assertEqual(result, (2, 3, 1))

    def test_rejects_checksum_drift(self):
        self.add_migration(1)
        with self.assertRaisesRegex(ValueError, "校验和与备份源码不一致"):
            verify(self.migrations, self.write_applied([(1, "0" * 64)]))

    def test_rejects_non_contiguous_database_versions(self):
        first = self.add_migration(1)
        self.add_migration(2)
        third = self.add_migration(3)
        with self.assertRaisesRegex(ValueError, "数据库迁移版本不连续"):
            verify(
                self.migrations,
                self.write_applied([(1, first), (3, third)]),
            )


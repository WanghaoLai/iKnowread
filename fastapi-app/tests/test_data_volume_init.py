import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.init_app_data import MARKER_NAME, migrate_legacy_data


class AppDataMigrationTests(unittest.TestCase):
    def test_imports_legacy_data_once_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "legacy"
            target = root / "target"
            (legacy / "files").mkdir(parents=True)
            (legacy / "files" / "document.pdf").write_bytes(b"pdf")
            (legacy / ".ai-config-key").write_text("secret", encoding="utf-8")

            self.assertTrue(migrate_legacy_data(legacy, target))
            self.assertEqual((target / "files" / "document.pdf").read_bytes(), b"pdf")
            self.assertEqual((target / ".ai-config-key").read_text(), "secret")
            self.assertTrue((target / MARKER_NAME).is_file())
            self.assertFalse(migrate_legacy_data(legacy, target))

    def test_refuses_to_merge_two_nonempty_data_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "legacy"
            target = root / "target"
            legacy.mkdir()
            target.mkdir()
            (legacy / "old").write_text("old")
            (target / "new").write_text("new")

            with self.assertRaisesRegex(RuntimeError, "拒绝.*合并"):
                migrate_legacy_data(legacy, target)
            self.assertEqual((target / "new").read_text(), "new")
            self.assertFalse((target / "old").exists())

    def test_partial_copy_is_removed_and_the_next_start_can_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "legacy"
            target = root / "target"
            (legacy / "files").mkdir(parents=True)
            (legacy / "files" / "document.pdf").write_bytes(b"pdf")

            def fail_after_creating_destination(source, destination):
                Path(destination).mkdir()
                (Path(destination) / "partial").write_bytes(b"incomplete")
                raise OSError("disk full")

            with patch(
                "scripts.init_app_data.shutil.copytree",
                side_effect=fail_after_creating_destination,
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    migrate_legacy_data(legacy, target)

            self.assertEqual(list(target.iterdir()), [])
            self.assertTrue(migrate_legacy_data(legacy, target))
            self.assertEqual((target / "files" / "document.pdf").read_bytes(), b"pdf")
            self.assertTrue((target / MARKER_NAME).is_file())


if __name__ == "__main__":
    unittest.main()

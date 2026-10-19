import unittest

from scripts.document_contract import document_path


class DocumentContractHelperTests(unittest.TestCase):
    def test_renders_paths_for_external_scripts(self):
        self.assertEqual(document_path("list"), "/documents")
        self.assertEqual(
            document_path("preview", 7, prefix="/api"),
            "/api/documents/7/preview",
        )

    def test_requires_an_id_for_item_routes(self):
        with self.assertRaisesRegex(ValueError, "requires a positive id"):
            document_path("download")


if __name__ == "__main__":
    unittest.main()

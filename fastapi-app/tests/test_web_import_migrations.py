import re
import unittest

from app.migrations import v016_web_imports, v017_web_import_lifecycle


class V15SchemaConnection:
    """Stateful information_schema double representing an installed v015 DB."""

    def __init__(self):
        self.columns = {("document", "id"), ("document", "ext")}
        self.indexes = set()
        self.constraints = {("document", "ck_document_ext")}
        self.tables = {"account", "document"}
        self.executed = []
        self.web_status_values = set()

    async def execute_query_dict(self, query, params=None):
        params = params or []
        if "information_schema.COLUMNS" in query:
            return [{"1": 1}] if tuple(params) in self.columns else []
        if "information_schema.STATISTICS" in query:
            return [{"1": 1}] if tuple(params) in self.indexes else []
        if "information_schema.TABLE_CONSTRAINTS" in query:
            return [{"1": 1}] if tuple(params) in self.constraints else []
        raise AssertionError(f"unexpected metadata query: {query}")

    async def execute_query(self, query, _params=None):
        normalized = " ".join(query.split())
        self.executed.append(normalized)
        match = re.search(r"ADD COLUMN `([^`]+)`", normalized)
        if match:
            self.columns.add(("document", match.group(1)))
        if "ADD INDEX `ix_document_source_type`" in normalized:
            self.indexes.add(("document", "ix_document_source_type"))
        if "ADD CONSTRAINT `ck_document_source_type`" in normalized:
            self.constraints.add(("document", "ck_document_source_type"))
        if "CREATE TABLE IF NOT EXISTS `web_import_job`" in normalized:
            self.tables.add("web_import_job")
            self.constraints.add(("web_import_job", "ck_web_import_status"))
            self.web_status_values = {"pending", "processing", "success", "failed"}
        if "DROP CHECK `ck_web_import_status`" in normalized:
            self.constraints.discard(("web_import_job", "ck_web_import_status"))
        if "ADD CONSTRAINT `ck_web_import_status`" in normalized:
            self.constraints.add(("web_import_job", "ck_web_import_status"))
            self.web_status_values = set(
                re.findall(r"'(pending|processing|success|failed|canceled)'", normalized)
            )


class WebImportMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_v15_database_upgrades_and_repeats_safely(self):
        connection = V15SchemaConnection()

        await v016_web_imports.upgrade(connection)
        await v017_web_import_lifecycle.upgrade(connection)
        first_schema = (
            set(connection.columns), set(connection.indexes),
            set(connection.constraints), set(connection.web_status_values),
        )
        await v016_web_imports.upgrade(connection)
        await v017_web_import_lifecycle.upgrade(connection)

        self.assertEqual(
            first_schema,
            (
                connection.columns, connection.indexes,
                connection.constraints, connection.web_status_values,
            ),
        )
        self.assertTrue({
            ("document", "source_type"),
            ("document", "source_url"),
            ("document", "source_title"),
            ("document", "source_fetched_at"),
        }.issubset(connection.columns))
        self.assertIn(("document", "ix_document_source_type"), connection.indexes)
        self.assertIn(("document", "ck_document_source_type"), connection.constraints)
        self.assertIn(("web_import_job", "ck_web_import_status"), connection.constraints)
        self.assertEqual(
            connection.web_status_values,
            {"pending", "processing", "success", "failed", "canceled"},
        )


if __name__ == "__main__":
    unittest.main()

"""Exercise every exact-source priority guard with the concurrent covering index."""
from pathlib import Path

from . import test_catalog_repair_priority_pg as priority_fixture


class CatalogRepairPriorityCoverPostgres(priority_fixture.CatalogRepairPriorityPostgres):
    def setUp(self):
        super().setUp()
        self.migration = (Path(__file__).parent / "migrations" /
                          "20261005_067_official_quote_repair_priority_cover.sql").read_text()
        # Only the isolated fixture relation is relocated. The concurrent DDL
        # stays otherwise byte-identical and is executed outside a transaction.
        original = "public.official_price_quote"
        self.assertEqual(self.migration.count(original), 1)
        self.fixture_migration = self.migration.replace(original,
                                                       self.schema + ".official_price_quote")
        self.db.execute(self.fixture_migration)

    def test_concurrent_index_is_valid_and_idempotent(self):
        keys = self.seed_changed(5)
        retained_rows = "SELECT * FROM official_price_quote ORDER BY document_id,source_locator,parser_version"
        before = self.db.execute(retained_rows).fetchall()
        self.db.execute(self.fixture_migration)
        row = self.db.execute("""SELECT i.indisvalid,i.indisready,c.relname
          FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
          WHERE i.indexrelid=to_regclass(%s)""",
          (self.schema + ".official_quote_repair_priority_cover",)).fetchone()
        self.assertEqual(row, (True, True, "official_quote_repair_priority_cover"))
        self.assertEqual(self.priority(), keys[:4])
        self.assertEqual(self.db.execute(retained_rows).fetchall(),
                         before, "Index creation must leave all retained quote fields unchanged")

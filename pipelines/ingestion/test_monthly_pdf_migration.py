"""Reapplied legacy quarantine cannot hide fully checkpointed v4 PDF prices."""

import os
import unittest
from pathlib import Path

from . import worker

MIGRATIONS = Path(__file__).parent / "migrations"
LEGACY_ERROR = (
    "Legacy monthly PDF price grids require table-local monetary verification; "
    "originals and prior parser rows retained"
)


@unittest.skipUnless(
    os.environ.get("AGRO_PUBLICATION_POSTGRES_TEST") == "1",
    "Explicit TEMP-table PostgreSQL opt-in",
)
class MonthlyPDFMigration(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp")
        self.db.execute(
            "CREATE TEMP TABLE ingestion_asset("
            "document_id text,kind text,status text,records integer,"
            "processor_version text,error text)"
        )
        self.db.execute(
            "CREATE TEMP TABLE historical_price("
            "document_id text,source_locator text,series text,details jsonb)"
        )
        self.db.execute(
            "CREATE TEMP TABLE source_pdf_page("
            "document_id text,extraction_version text,page integer)"
        )
        self.db.execute(
            "CREATE TEMP TABLE historical_price_review("
            "document_id text,source_locator text)"
        )

    def migration(self, name):
        return (MIGRATIONS / name).read_text()

    def test_legacy_reapplication_preserves_accepted_v4(self):
        self.db.execute(
            "INSERT INTO ingestion_asset VALUES"
            "('current','monthly-pdf','complete',2,'monthly-pdf-v4',NULL),"
            "('old','monthly-pdf','complete',2,'monthly-pdf-v2',NULL),"
            "('accepted-v3','monthly-pdf','complete',2,'monthly-pdf-v3',NULL)"
        )
        sql = self.migration("20260927_001_pdf_price_review.sql")
        quarantine = sql[sql.index("UPDATE ingestion_asset SET status='review'") :]
        self.db.execute(quarantine)
        self.db.execute(quarantine)
        statuses = self.db.execute(
            "SELECT document_id,status,error FROM ingestion_asset ORDER BY document_id"
        ).fetchall()
        self.assertEqual(
            statuses,
            [
                ("accepted-v3", "complete", None),
                ("current", "complete", None),
                ("old", "review", LEGACY_ERROR),
            ],
        )

    def test_forward_recovery_requires_exact_error_rows_and_pages(self):
        for did, records, error, version in [
            ("recovered", 2, LEGACY_ERROR, "monthly-pdf-v4"),
            ("partial-rows", 2, LEGACY_ERROR, "monthly-pdf-v4"),
            ("missing-page", 2, LEGACY_ERROR, "monthly-pdf-v4"),
            ("other-review", 2, "A distinct source-date conflict", "monthly-pdf-v4"),
            ("legacy", 2, LEGACY_ERROR, "monthly-pdf-v2"),
        ]:
            self.db.execute(
                "INSERT INTO ingestion_asset VALUES"
                "(%s,'monthly-pdf','review',%s,%s,%s)",
                (did, records, version, error),
            )
            for page in ([1, 2] if did != "missing-page" else [2]):
                self.db.execute(
                    "INSERT INTO source_pdf_page VALUES(%s,'pdf-text-tables-v1',%s)",
                    (did, page),
                )
            for row in range(2 if did != "partial-rows" else 1):
                self.db.execute(
                    "INSERT INTO historical_price VALUES"
                    "(%s,%s,'dane-monthly-summary',"
                    "'{\"parser_version\":\"monthly-pdf-v4\"}')",
                    (did, f"PDF page 2,row {row}"),
                )
        recovery = self.migration("20261001_042_monthly_pdf_v4_recovery.sql")
        self.db.execute(recovery)
        self.db.execute(recovery)
        statuses = self.db.execute(
            "SELECT document_id,status,error FROM ingestion_asset ORDER BY document_id"
        ).fetchall()
        self.assertEqual(
            statuses,
            [
                ("legacy", "review", LEGACY_ERROR),
                ("missing-page", "review", LEGACY_ERROR),
                ("other-review", "review", "A distinct source-date conflict"),
                ("partial-rows", "review", LEGACY_ERROR),
                ("recovered", "complete", None),
            ],
        )

    def test_publication_view_accepts_v4_but_not_unverified_legacy(self):
        sql = self.migration("20260927_001_pdf_price_review.sql")
        view = sql[sql.index("CREATE OR REPLACE VIEW") : sql.index("GRANT SELECT ON published_historical_price")]
        self.db.execute(view.replace("CREATE OR REPLACE VIEW", "CREATE TEMP VIEW"))
        self.db.execute(
            "INSERT INTO historical_price VALUES"
            "('v4','price','dane-monthly-bulletin','{\"parser_version\":\"monthly-pdf-v4\"}'),"
            "('legacy','price','dane-monthly-bulletin','{\"parser_version\":\"monthly-pdf-v2\"}')"
        )
        self.assertEqual(
            self.db.execute(
                "SELECT document_id FROM published_historical_price"
            ).fetchall(),
            [("v4",)],
        )

"""Actual worker failure handling keeps reviewed evidence out of public prices."""

import io
import os
import unittest
from contextlib import nullcontext, redirect_stdout
from datetime import date
from unittest.mock import patch

from . import daily_recovery, query_publication, worker
from .resumable_inputs import WorkDeferred


@unittest.skipUnless(
    os.environ.get("AGRO_REVIEW_RETENTION_POSTGRES_TEST") == "1",
    "Explicit opt-in for PostgreSQL TEMP-only review retention checks",
)
class ReviewRetentionTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp")
        self.db.execute("SET statement_timeout='15s'")
        for table in (
            "source_document",
            "document_alias",
            "ingestion_asset",
            "ingestion_run",
            "historical_price",
            "price_observation",
            "price_observation_review",
        ):
            self.db.execute(
                f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"
            )
            self.assertEqual(
                self.db.execute(
                    "SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)",
                    (table,),
                ).fetchone(),
                ("t",),
            )
        # Use the production publication predicate, bound to TEMP relations.
        definition = self.db.execute(
            "SELECT pg_get_viewdef('public.published_price_observation'::regclass,true)"
        ).fetchone()[0]
        self.db.execute(
            "CREATE TEMP VIEW published_price_observation AS "
            + definition.replace("public.", "pg_temp.")
        )
        self.enterContext(patch.dict(os.environ, {"AzureWebJobsStorage": ""}))
        self.body = b"retained original with a contradictory printed date"
        self.day = date(2012, 7, 6)
        self.url = "https://www.dane.gov.co/review-retention-fixture.xls"
        self.did = worker.archive(self.db, self.url, self.body, "daily", self.day)
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,observed_on,status,document_id,processor_version) "
            "VALUES(%s,'daily',%s,'review',%s,%s)",
            (self.url, self.day, self.did, worker.parser_version("daily")),
        )
        with self.db.transaction():
            worker.save_rows(
                self.db,
                self.did,
                [
                    worker.record(
                        "dane-daily", self.day, "Tomate", "Bogotá", "kg",
                        999, "Original!row 5,col 2",
                    )
                ],
            )
        # Simulate an invalid old projection that was already quarantined.
        self.db.execute(
            """INSERT INTO price_observation
            (product_id,market_id,source_id,observed_on,period,unit,price,
             source_url,document_id,source_locator)
            VALUES('tomate','bogota','dane-sipsa',%s,'daily','kg',999,%s,%s,%s)""",
            (self.day, self.url, self.did, "Original!row 5,col 2"),
        )
        self.raw_before = self.db.execute("SELECT * FROM historical_price").fetchall()
        self.prices_before = self.db.execute("SELECT * FROM price_observation").fetchall()
        self.assert_suppressed()

    def assert_suppressed(self):
        self.assertEqual(
            self.db.execute(
                "SELECT status,document_id FROM ingestion_asset WHERE url=%s",
                (self.url,),
            ).fetchone(),
            ("review", self.did),
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM published_price_observation").fetchone(),
            (0,),
        )

    def check_failure(self, error):
        def native_failure(*_args):
            # Even the pre-parse pending transition must not lift review.
            self.assert_suppressed()
            raise worker.SourceDateMismatch("Printed source date conflicts")

        def alternate_failure(*_args, **kwargs):
            self.assertEqual(kwargs["original_id"], self.did)
            self.assertEqual(kwargs["original_data"], self.body)
            self.assert_suppressed()
            raise error

        with (
            patch.object(worker, "connect", return_value=nullcontext(self.db)),
            patch.object(worker, "LOCK", 914070966),
            patch.object(worker, "fetch_asset", return_value=self.body),
            patch.object(daily_recovery, "parse_daily", side_effect=native_failure),
            patch.object(query_publication, "recover", side_effect=alternate_failure),
            patch.object(worker, "project") as project,
            patch("pipelines.ingestion.ocr.scan_document"),
            patch("pipelines.ingestion.ocr.drain", return_value={}),
            redirect_stdout(io.StringIO()),
        ):
            summary = worker.run(
                "backfill", limit=1, time_budget=60,
                ocr_limit=0, ocr_scan_limit=0, asset_url=self.url,
            )
        project.assert_not_called()
        self.assert_suppressed()
        self.assertEqual(summary["assets"], 0)
        self.assertEqual(summary["rows"], 0)
        self.assertEqual(
            self.db.execute("SELECT * FROM historical_price").fetchall(), self.raw_before
        )
        self.assertEqual(
            self.db.execute("SELECT * FROM price_observation").fetchall(), self.prices_before
        )
        self.assertEqual(
            self.db.execute("SELECT status FROM ingestion_run").fetchone(), ("partial",)
        )
        field = "deferred" if isinstance(error, WorkDeferred) else "errors"
        self.assertEqual(len(summary[field]), 1)
        self.assertEqual(summary[field][0]["url"], self.url)
        self.assertIn(
            str(error),
            self.db.execute("SELECT error FROM ingestion_asset").fetchone()[0],
        )

    def test_timeout_recovery_keeps_original_reviewed_and_old_prices_hidden(self):
        self.check_failure(TimeoutError("Independent query timed out"))

    def test_invalid_recovery_keeps_original_reviewed_and_old_prices_hidden(self):
        self.check_failure(ValueError("SIPSA query resultset is incomplete"))

    def test_deferred_recovery_keeps_original_reviewed_and_old_prices_hidden(self):
        self.check_failure(WorkDeferred("Independent query requires another run"))


if __name__ == "__main__":
    unittest.main()

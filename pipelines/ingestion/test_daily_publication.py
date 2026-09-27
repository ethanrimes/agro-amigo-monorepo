"""Production daily recovery SQL against isolated PostgreSQL TEMP tables."""

import os
import unittest
from datetime import date
from unittest.mock import patch

from . import daily_publication, daily_recovery, worker


@unittest.skipUnless(
    os.environ.get("AGRO_DAILY_RECOVERY_POSTGRES_TEST") == "1",
    "Explicit opt-in for PostgreSQL TEMP-only publication checks",
)
class DailyPublicationTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp")
        self.db.execute("SET statement_timeout='15s'")
        tables = (
            "historical_price",
            "daily_price",
            "official_source_review",
            "retained_record",
            "ingestion_asset",
            "source_document",
            "product",
        )
        for table in tables:
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
        self.did = "a" * 64
        self.url = "https://www.dane.gov.co/fixture.xls"
        self.day = date(2012, 11, 29)
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,observed_on) VALUES(%s,'daily',%s)",
            (self.url, self.day),
        )
        self.rows = [
            worker.record(
                "dane-daily",
                self.day,
                "Ahuyama",
                "Bogotá, Corabastos",
                "kg",
                1000.25,
                "Sheet!row 5,col 2",
                14.2,
            )
        ]
        self.review = {
            "source_locator": "Sheet!row 5,col 4",
            "reason": "Missing explicit market",
            "record": {"price": 500, "market_name": None},
        }

    def publish(self, rows=None, reviews=None, resolutions=None):
        parsed = {
            "rows": self.rows if rows is None else rows,
            "reviews": reviews or [],
            "date_resolutions": resolutions or [],
        }
        with patch.object(daily_recovery, "parse_daily", return_value=parsed):
            return daily_publication.publish(
                self.db, b"fixture", self.did, self.url, self.day
            )

    def test_partial_matrix_retains_every_review_and_valid_quote_replays(self):
        for _ in range(2):
            self.assertEqual(self.publish(reviews=[self.review]), 1)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone(), (1,)
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM daily_price").fetchone(), (1,)
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_source_review").fetchone(),
            (1,),
        )
        status, count, note = self.db.execute(
            "SELECT status,records,error FROM ingestion_asset"
        ).fetchone()
        self.assertEqual((status, count), ("complete", 1))
        self.assertIn("1 price cells retained", note)
        self.assertEqual(
            self.db.execute(
                "SELECT record->>'market_name' FROM official_source_review"
            ).fetchone(),
            (None,),
        )

    def test_ambiguous_only_matrix_publishes_nothing(self):
        self.assertEqual(self.publish(rows=[], reviews=[self.review]), 0)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM daily_price").fetchone(), (0,)
        )
        self.assertEqual(
            self.db.execute("SELECT status FROM ingestion_asset").fetchone(),
            ("review",),
        )

    def test_mislink_keeps_archive_gap_visible_and_never_creates_wrong_day(self):
        actual = date(2012, 11, 30)
        row = list(self.rows[0])
        row[2] = actual
        evidence = {
            "archive_date": self.day.isoformat(),
            "observation_date": actual.isoformat(),
            "corroborating_url": "https://www.dane.gov.co/actual.xls",
        }
        for _ in range(2):
            self.publish(rows=[tuple(row)], resolutions=[evidence])
        self.assertEqual(
            self.db.execute("SELECT observed_on FROM daily_price").fetchall(),
            [(actual,)],
        )
        self.assertEqual(
            self.db.execute("SELECT status FROM ingestion_asset").fetchone(),
            ("review",),
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM retained_record").fetchone(), (1,)
        )

    def test_preexisting_wrong_date_cannot_be_republished_or_rewritten(self):
        row = list(self.rows[0])
        row[2] = date(2012, 11, 28)
        with self.db.transaction():
            worker.save_rows(self.db, self.did, [tuple(row)])
        with self.assertRaisesRegex(worker.SourceDateMismatch, "immutable evidence"):
            self.publish()
        self.assertEqual(
            self.db.execute("SELECT observed_on FROM historical_price").fetchall(),
            [(row[2],)],
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM daily_price").fetchone(), (0,)
        )

    def test_projection_failure_rolls_back_prices_reviews_and_resolution(self):
        with patch.object(
            worker, "project", side_effect=ValueError("projection failure")
        ), self.assertRaisesRegex(ValueError, "projection failure"):
            self.publish(
                reviews=[self.review],
                resolutions=[
                    {
                        "archive_date": self.day.isoformat(),
                        "observation_date": self.day.isoformat(),
                    }
                ],
            )
        for table in (
            "historical_price",
            "daily_price",
            "official_source_review",
            "retained_record",
        ):
            self.assertEqual(
                self.db.execute(f"SELECT count(*) FROM {table}").fetchone(), (0,)
            )

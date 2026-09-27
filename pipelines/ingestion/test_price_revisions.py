"""Replay chronology integration checks; all writes stay in session TEMP tables."""

import os
import unittest
from datetime import date
from pathlib import Path
from time import monotonic
from unittest.mock import patch

from . import worker


@unittest.skipUnless(
    os.environ.get("AGRO_PRICE_REVISION_POSTGRES_TEST") == "1",
    "Explicit opt-in for PostgreSQL TEMP-table checks",
)
class PriceRevisionPostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        for table in (
            "historical_price",
            "daily_price",
            "price_observation",
            "coffee_reference",
            "coffee_factor",
        ):
            self.db.execute(
                f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"
            )
        self.db.execute(
            "CREATE TEMP TABLE source_document(id text PRIMARY KEY,retrieved_at timestamptz NOT NULL,content bytea,metadata jsonb DEFAULT '{}')"
        )
        self.db.execute(
            "CREATE TEMP TABLE product(id text PRIMARY KEY,name text,category text)"
        )
        self.db.execute(
            "CREATE TEMP TABLE market(id text PRIMARY KEY,name text,city text,region text)"
        )
        self.db.execute(
            "CREATE TEMP TABLE document_alias(alias text PRIMARY KEY,document_id text)"
        )
        self.db.execute(
            "CREATE TEMP TABLE ingestion_asset(kind text,status text,document_id text,checked_at timestamptz)"
        )
        self.db.execute("SET search_path=pg_temp")
        # Fail closed before the first fixture write if any unqualified table is public.
        for table in (
            "historical_price",
            "daily_price",
            "price_observation",
            "coffee_reference",
            "coffee_factor",
            "source_document",
            "product",
            "market",
            "document_alias",
            "ingestion_asset",
        ):
            self.assertEqual(
                self.db.execute(
                    "SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)",
                    (table,),
                ).fetchone(),
                ("t",),
            )
        for key, day in (
            ("a", 8),
            ("b", 20),
            ("c", 25),
            ("d", 26),
            ("e", 25),
            ("f", 27),
            ("g", 27),
        ):
            self.db.execute(
                "INSERT INTO source_document(id,retrieved_at,content) VALUES(%s,%s,%s)",
                (key * 64, f"2026-09-{day:02d}T00:00:00Z", b"fixture"),
            )
        self.db.execute(
            "INSERT INTO ingestion_asset VALUES('coffee','complete',%s,now())",
            ("d" * 64,),
        )
        self.day = date(2026, 9, 23)

    def assert_price(self, table, key, price, *, day=None):
        self.assertEqual(
            self.db.execute(
                f"SELECT price,document_id FROM {table} WHERE observed_on=%s",
                (day or self.day,),
            ).fetchall(),
            [(price, key * 64)],
        )

    def test_monthly_and_coffee_project_reject_old_replay_and_keep_equal_value_revision(
        self,
    ):
        def publish(key, value):
            did = key * 64
            with self.db.transaction():
                worker.save_rows(
                    self.db,
                    did,
                    [
                        worker.record(
                            "dane-monthly",
                            self.day,
                            "Tomate",
                            "Bogotá",
                            "kg",
                            value,
                            "monthly!row 1",
                            details={"category": "Verduras"},
                        ),
                        worker.record(
                            "fnc-daily",
                            self.day,
                            "Café",
                            "Colombia",
                            "125kg",
                            value,
                            "coffee!row 1",
                        ),
                    ],
                )
                worker.project(
                    self.db, did, f"https://example.org/{key}.xlsx", "monthly"
                )

        for key, value, expected_key, expected_value in [
            ("b", 110, "b", 110),
            ("a", 100, "b", 110),
            ("c", 120, "c", 120),
            ("d", 120, "d", 120),
            ("e", 115, "d", 120),
            ("f", 130, "f", 130),
            ("g", 135, "g", 135),
        ]:
            publish(key, value)
            for table in ("price_observation", "coffee_reference"):
                self.assert_price(table, expected_key, expected_value)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 14
        )
        # A legacy row without a document can acquire verifiable provenance.
        self.db.execute("UPDATE coffee_reference SET document_id=NULL")
        worker.project(self.db, "a" * 64, "https://example.org/a.xlsx", "coffee")
        self.assert_price("coffee_reference", "a", 100)

    def test_bulk_daily_preserves_xls_precedence_and_atomic_rollback(self):
        self.db.execute(
            'UPDATE source_document SET metadata=\'{"ingestion_kind":"daily"}\' WHERE id=%s',
            ("b" * 64,),
        )

        def publish(key, value, locator):
            with self.db.transaction():
                worker.save_rows(
                    self.db,
                    key * 64,
                    [
                        worker.record(
                            "dane-daily",
                            self.day,
                            "Tomate",
                            "Bogotá",
                            "kg",
                            value,
                            locator,
                        )
                    ],
                )
                worker.project(self.db, key * 64, "https://example.org/report", "daily")

        publish("b", 3000, "Sheet!row 1")
        publish("f", 3500, "PDF page 1, row 1")
        self.assert_price("daily_price", "b", 3000)
        with self.assertRaisesRegex(RuntimeError, "rollback"), self.db.transaction():
            self.db.execute(
                'UPDATE source_document SET metadata=\'{"ingestion_kind":"daily"}\' WHERE id=%s',
                ("g" * 64,),
            )
            publish("g", 3100, "Sheet!row 2")
            raise RuntimeError("rollback")
        self.assert_price("daily_price", "b", 3000)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 2
        )

    def publish_daily_revision(self, key, price, kind, *, variation=None):
        """Exercise the actual raw COPY and publication SQL, including metadata."""
        did = key * 64
        locator = "Prices!row 4,col 2" if kind == "daily" else "PDF page 2, row 4"
        self.db.execute(
            "UPDATE source_document SET metadata=jsonb_build_object('ingestion_kind',%s::text) WHERE id=%s",
            (kind, did),
        )
        with self.db.transaction():
            worker.save_rows(
                self.db,
                did,
                [
                    worker.record(
                        "dane-daily",
                        self.day,
                        "Tomate",
                        "Bogotá",
                        "kg",
                        price,
                        locator,
                        variation,
                    )
                ],
            )
            worker.project(self.db, did, f"https://example.org/{key}", kind)

    def test_daily_older_xls_cannot_replace_newer_xls(self):
        self.publish_daily_revision("b", 3100, "daily", variation=2)
        self.publish_daily_revision("a", 2900, "daily", variation=-3)
        self.assert_price("daily_price", "b", 3100)
        self.assertEqual(
            self.db.execute("SELECT change_percent FROM daily_price").fetchone(),
            (2,),
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone(), (2,)
        )

    def test_daily_older_pdf_cannot_replace_newer_pdf(self):
        self.publish_daily_revision("b", 3100, "daily-pdf")
        self.publish_daily_revision("a", 2900, "daily-pdf")
        self.assert_price("daily_price", "b", 3100)
        self.assertEqual(
            self.db.execute("SELECT source_page,source_locator FROM daily_price").fetchone(),
            (2, "PDF page 2, row 4"),
        )

    def test_daily_older_xls_still_supersedes_newer_pdf(self):
        self.publish_daily_revision("b", 3100, "daily-pdf")
        self.publish_daily_revision("a", 2900, "daily")
        self.assert_price("daily_price", "a", 2900)
        # Even another newer PDF cannot undo the authoritative workbook choice.
        self.publish_daily_revision("c", 3200, "daily-pdf")
        self.assert_price("daily_price", "a", 2900)
        self.assertEqual(
            self.db.execute("SELECT source_page,source_locator FROM daily_price").fetchone(),
            (None, "Prices!row 4,col 2"),
        )

    def test_daily_equal_price_newer_xls_updates_provenance_and_blocks_old_replay(self):
        self.publish_daily_revision("b", 3100, "daily", variation=2)
        self.publish_daily_revision("d", 3100, "daily", variation=2)
        self.assert_price("daily_price", "d", 3100)
        self.publish_daily_revision("c", 3050, "daily", variation=1)
        self.assert_price("daily_price", "d", 3100)

    def test_daily_equal_price_newer_pdf_updates_provenance_and_blocks_old_replay(self):
        self.publish_daily_revision("b", 3100, "daily-pdf")
        self.publish_daily_revision("d", 3100, "daily-pdf")
        self.assert_price("daily_price", "d", 3100)
        self.publish_daily_revision("c", 3050, "daily-pdf")
        self.assert_price("daily_price", "d", 3100)

    def test_current_fnc_workbook_all_8667_dates_bulk_projection(self):
        fixture = (
            Path(__file__).resolve().parents[2]
            / "artifacts/automation-audit-2026-09-26/coffee-b13fef2a71.xlsx"
        )
        if not fixture.exists():
            self.skipTest("Current official FNC original not retained locally")
        with patch.object(worker, "today", return_value=date(2026, 9, 26)):
            rows = list(worker.parse_coffee(fixture.read_bytes()))
        self.assertEqual(len(rows), 8667)
        with self.db.transaction():
            worker.save_rows(self.db, "d" * 64, rows)
        started = monotonic()
        worker.project(
            self.db,
            "d" * 64,
            "https://federaciondecafeteros.org/Septiembre-2026.xlsx",
            "coffee",
        )
        elapsed = monotonic() - started
        self.assertEqual(
            self.db.execute(
                "SELECT count(*),min(observed_on),max(observed_on) FROM coffee_reference"
            ).fetchone(),
            (8666, date(2003, 1, 2), date(2026, 9, 26)),
        )
        self.assert_price("coffee_reference", "d", 2105000, day=date(2026, 9, 26))
        print(
            f"TEMP bulk FNC publication: 8667 raw rows / 8666 unique dates in {elapsed:.3f}s",
            flush=True,
        )
        self.assertIsNone(
            self.db.execute(
                "SELECT to_regclass('pg_temp.ingestion_coffee_projection_stage')"
            ).fetchone()[0]
        )

    def test_bulletin_factors_branches_and_alias_follow_revision_and_observation_dates(
        self,
    ):
        def publish(key, value, day=None):
            day = day or self.day
            url = f"https://example.org/{key}.pdf"
            parsed = (
                [(day, value, url)],
                [(day, 94, value, url)],
                {"fnc-bogota": ("fnc-bogota", "Bogotá", "Bogotá", "Bogotá")},
                [("cafe", "fnc-bogota", "fnc", day, "daily", "125kg", value, url)],
            )
            with patch("pipelines.demo.import_data.parse_fnc", return_value=parsed):
                worker.refresh_coffee_bulletin(self.db, b"fixture", key * 64, url)

        for key, value, expected_key, expected_value in [
            ("b", 110, "b", 110),
            ("a", 100, "b", 110),
            ("c", 120, "c", 120),
            ("d", 120, "d", 120),
            ("e", 115, "d", 120),
        ]:
            publish(key, value)
            for table in ("coffee_reference", "coffee_factor", "price_observation"):
                self.assert_price(table, expected_key, expected_value)
            self.assertEqual(
                self.db.execute(
                    "SELECT document_id FROM document_alias WHERE alias='fnc-price'"
                ).fetchone(),
                (expected_key * 64,),
            )
            self.assertEqual(
                self.db.execute("SELECT source_url FROM price_observation").fetchone(),
                (f"https://example.org/{expected_key}.pdf",),
            )
        # A newly fetched old report must retain its own historical day, while the
        # newest bulletin alias continues to point at the newest observation day.
        publish("f", 80, date(2026, 8, 31))
        self.assertEqual(
            self.db.execute(
                "SELECT document_id FROM document_alias WHERE alias='fnc-price'"
            ).fetchone(),
            ("d" * 64,),
        )
        self.assert_price("coffee_factor", "f", 80, day=date(2026, 8, 31))
        publish("a", 140, date(2026, 9, 24))
        self.assertEqual(
            self.db.execute(
                "SELECT document_id FROM document_alias WHERE alias='fnc-price'"
            ).fetchone(),
            ("a" * 64,),
        )
        for table in ("coffee_reference", "coffee_factor", "price_observation"):
            self.assertEqual(
                self.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 3
            )


if __name__ == "__main__":
    unittest.main()

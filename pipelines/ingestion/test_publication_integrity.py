"""Actual PostgreSQL view withdrawal and month-evidence publication in TEMP only."""

import os
import unittest
from pathlib import Path

from . import seasonality, worker


@unittest.skipUnless(
    os.environ.get("AGRO_PUBLICATION_POSTGRES_TEST") == "1",
    "Explicit TEMP-table PostgreSQL opt-in",
)
class PublicationIntegrity(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp")
        self.db.execute(
            "CREATE TEMP TABLE source_document(id text PRIMARY KEY,retrieved_at timestamptz)"
        )
        self.db.execute(
            "CREATE TEMP TABLE ingestion_asset(document_id text,status text,observed_on date)"
        )
        self.db.execute(
            "CREATE TEMP TABLE official_price_quote(document_id text,source_locator text,quote_key text,observed_on date,parsed_at timestamptz,price numeric)"
        )
        self.db.execute(
            "CREATE TEMP TABLE official_source_review(document_id text,source_locator text,created_at timestamptz)"
        )
        for name in (
            "source_document",
            "ingestion_asset",
            "official_price_quote",
            "official_source_review",
        ):
            self.assertEqual(
                self.db.execute(
                    "SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)",
                    (name,),
                ).fetchone(),
                ("t",),
            )

    def test_review_withdraws_only_ambiguous_quote_and_later_correction_can_publish(
        self,
    ):
        sql = (
            Path(__file__).parent / "migrations/20260927_003_official_quote_review.sql"
        ).read_text()
        sql = sql[
            sql.index("CREATE OR REPLACE VIEW") : sql.index("GRANT SELECT")
        ].replace("CREATE OR REPLACE VIEW", "CREATE TEMP VIEW")
        self.db.execute(sql)
        self.db.execute("INSERT INTO source_document VALUES('doc','2026-09-01')")
        self.db.execute(
            "INSERT INTO official_price_quote VALUES('doc','bad','a','2026-09-01','2026-09-02',10),('doc','good','b','2026-09-01','2026-09-02',20)"
        )
        self.db.execute(
            "INSERT INTO official_source_review VALUES('doc','bad','2026-09-03')"
        )
        self.assertEqual(
            self.db.execute("SELECT price FROM published_official_price").fetchall(),
            [(20,)],
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0],
            2,
        )
        self.db.execute(
            "INSERT INTO official_price_quote VALUES('doc','bad','a','2026-09-01','2026-09-04',12)"
        )
        self.assertEqual(
            self.db.execute(
                "SELECT price FROM published_official_price ORDER BY quote_key"
            ).fetchall(),
            [(12,), (20,)],
        )

    def test_seasonal_bulk_publication_and_review_preserve_original_rows(self):
        self.db.execute(
            "CREATE TEMP TABLE seasonal_year(product_id text,market_id text,reference_year integer,monthly_prices jsonb,document_id text,source_rows jsonb,source_documents jsonb,validation_version text,review_reason text,PRIMARY KEY(product_id,market_id,reference_year))"
        )
        self.db.execute(
            "CREATE TEMP TABLE published_price_observation(product_id text,market_id text,observed_on date,price numeric,document_id text,source_locator text,unit text,source_id text,period text)"
        )
        self.db.execute(
            "CREATE TEMP TABLE coffee_reference(observed_on date,price numeric,document_id text)"
        )
        self.db.execute(
            "INSERT INTO published_price_observation SELECT 'p','m',make_date(2025,m,1),1000+m,m::text,'sheet row '||m,'kg','dane-sipsa','monthly' FROM generate_series(1,12) m"
        )
        self.db.execute(
            "INSERT INTO published_price_observation SELECT 'p','m',make_date(2025,m,1),50,'unit-doc','row','unit','dane-sipsa','monthly' FROM generate_series(1,12) m"
        )
        self.assertEqual(
            seasonality.refresh(self.db, 2026),
            {"complete_years": 1, "reviewed_years": 0},
        )
        result = self.db.execute(
            "SELECT monthly_prices,source_documents,review_reason FROM seasonal_year"
        ).fetchone()
        self.assertEqual(
            result, (list(range(1001, 1013)), [[str(m)] for m in range(1, 13)], None)
        )
        self.db.execute(
            "INSERT INTO published_price_observation VALUES('p','m','2025-01-01',2000,'other','row','kg','dane-sipsa','monthly')"
        )
        self.assertEqual(
            seasonality.refresh(self.db, 2026),
            {"complete_years": 0, "reviewed_years": 1},
        )
        reviewed = self.db.execute(
            "SELECT monthly_prices,review_reason FROM seasonal_year"
        ).fetchone()
        self.assertEqual(reviewed[0], result[0])
        self.assertIn("Conflicting", reviewed[1])

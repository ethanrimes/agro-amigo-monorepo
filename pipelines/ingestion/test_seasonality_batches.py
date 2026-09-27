"""Durable seasonal publication with real TEMP PostgreSQL retention triggers.

Opt in using AGRO_SEASONAL_BATCH_POSTGRES_TEST=1. Only fixture tables are used;
worker.connect can be patched to a private local PostgreSQL instance.
"""

import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import psycopg
from psycopg.pq import TransactionStatus

from . import seasonality, worker
from .resumable_inputs import WorkDeferred


@unittest.skipUnless(
    os.environ.get("AGRO_SEASONAL_BATCH_POSTGRES_TEST") == "1",
    "Explicit PostgreSQL TEMP-table opt-in",
)
class SeasonalBatchPostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.autocommit)
        self.db.execute("SET search_path=pg_temp")
        self.db.execute(
            """CREATE TEMP TABLE seasonal_year(
              product_id text,market_id text,reference_year integer,
              monthly_prices jsonb NOT NULL CHECK(jsonb_array_length(monthly_prices)=12),
              document_id text NOT NULL,source_rows jsonb NOT NULL,
              source_documents jsonb NOT NULL DEFAULT '[]',validation_version text,review_reason text,
              PRIMARY KEY(product_id,market_id,reference_year));
            CREATE TEMP TABLE published_price_observation(
              product_id text,market_id text,observed_on date,price numeric,
              document_id text,source_locator text,unit text,source_id text,period text);
            CREATE TEMP TABLE coffee_reference(observed_on date,price numeric,document_id text);
            CREATE TEMP TABLE retained_record(
              table_name text,fingerprint text,captured_at timestamptz DEFAULT now(),record jsonb,
              PRIMARY KEY(table_name,fingerprint));
            CREATE TEMP TABLE seasonal_attempt(product_id text,operation text);
            CREATE FUNCTION pg_temp.track_seasonal_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN INSERT INTO seasonal_attempt VALUES(NEW.product_id,TG_OP); RETURN NEW; END $$;
            CREATE TRIGGER track_attempt BEFORE INSERT OR UPDATE ON seasonal_year
              FOR EACH ROW EXECUTE FUNCTION pg_temp.track_seasonal_attempt();"""
        )
        # Execute the actual production retention function, scoped to pg_temp.
        schema = (Path(__file__).parent / "schema.sql").read_text()
        retain = re.search(
            r"CREATE OR REPLACE FUNCTION preserve_record_version\(\)[\s\S]*?END \$\$;",
            schema,
        ).group(0)
        self.db.execute(
            retain.replace(
                "preserve_record_version()", "pg_temp.preserve_record_version()"
            )
        )
        self.db.execute(
            """CREATE TRIGGER preserve_versions AFTER INSERT OR UPDATE ON seasonal_year
            FOR EACH ROW EXECUTE FUNCTION pg_temp.preserve_record_version()"""
        )
        self.assertEqual(
            self.db.execute(
                """SELECT count(*) FROM pg_class WHERE relpersistence='t' AND oid IN(
                'seasonal_year'::regclass,'published_price_observation'::regclass,
                'coffee_reference'::regclass,'retained_record'::regclass,'seasonal_attempt'::regclass)"""
            ).fetchone(),
            (5,),
        )
        batch = patch.object(seasonality, "BATCH_SIZE", 2)
        batch.start()
        self.addCleanup(batch.stop)
        token = worker.RUN_DEADLINE.set(None)
        self.addCleanup(worker.RUN_DEADLINE.reset, token)

    def seed(self, count=3):
        self.db.execute(
            """INSERT INTO published_price_observation
            SELECT 'p-'||lpad(p::text,3,'0'),'market',make_date(2025,m,1),1000+p*100+m,
              'doc-'||p||'-'||m,'sheet!row '||m,'kg','dane-sipsa','monthly'
            FROM generate_series(0,%s) p CROSS JOIN generate_series(1,12) m""",
            (count - 1,),
        )

    def count(self, table):
        return self.db.execute(f"SELECT count(*) FROM pg_temp.{table}").fetchone()[0]

    def fail_second_batch(self, event="INSERT"):
        self.db.execute(
            """CREATE FUNCTION pg_temp.fail_seasonal() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.product_id='p-002' THEN RAISE EXCEPTION 'forced seasonal second batch'; END IF;
              RETURN NEW; END $$"""
        )
        self.db.execute(
            f"CREATE TRIGGER fail_batch BEFORE {event} ON seasonal_year FOR EACH ROW EXECUTE FUNCTION pg_temp.fail_seasonal()"
        )

    def assert_evidence(self, count=3):
        rows = self.db.execute(
            "SELECT product_id,monthly_prices,source_rows,source_documents,validation_version,review_reason FROM seasonal_year ORDER BY product_id"
        ).fetchall()
        self.assertEqual(len(rows), count)
        for index, (_, prices, locators, docs, version, review) in enumerate(rows):
            self.assertEqual(prices, [1000 + index * 100 + m for m in range(1, 13)])
            self.assertEqual(docs, [[f"doc-{index}-{m}"] for m in range(1, 13)])
            self.assertEqual(
                locators,
                [f"doc-{index}-{m} · sheet!row {m}" for m in range(1, 13)],
            )
            self.assertEqual(version, seasonality.VERSION)
            self.assertIsNone(review)

    def test_second_batch_failure_keeps_complete_first_batch_and_resume_skips_it(self):
        self.seed()
        self.fail_second_batch()
        with self.assertRaisesRegex(psycopg.Error, "forced seasonal second batch"):
            seasonality.refresh(self.db, 2026)
        self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
        self.assert_evidence(2)
        self.assertEqual(self.count("retained_record"), 2)
        self.assertEqual(self.count("seasonal_attempt"), 2)
        self.assertIsNone(
            self.db.execute("SELECT to_regclass('pg_temp.seasonal_stage')").fetchone()[
                0
            ]
        )
        self.db.rollback()
        self.assertEqual(self.count("seasonal_year"), 2)
        self.db.execute("DROP TRIGGER fail_batch ON seasonal_year")
        self.assertEqual(
            seasonality.refresh(self.db, 2026),
            {"complete_years": 3, "reviewed_years": 0},
        )
        self.assert_evidence()
        self.assertEqual(self.count("retained_record"), 3)
        self.assertEqual(self.count("seasonal_attempt"), 3)
        seasonality.refresh(self.db, 2026)
        self.assertEqual(self.count("seasonal_attempt"), 3)
        self.assertEqual(self.count("retained_record"), 3)

    def test_run_deadline_between_batches_preserves_durable_years(self):
        self.seed()
        worker.RUN_DEADLINE.set(100)
        clock = Mock(side_effect=[0, 0, 0, 0, 101])
        with (
            patch.object(seasonality, "time", SimpleNamespace(monotonic=clock)),
            self.assertRaisesRegex(WorkDeferred, "committed complete-year batches"),
        ):
            seasonality.refresh(self.db, 2026)
        self.assertEqual(clock.call_count, 5)
        self.assert_evidence(2)
        self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
        worker.RUN_DEADLINE.set(None)
        seasonality.refresh(self.db, 2026)
        self.assert_evidence()
        self.assertEqual(self.count("seasonal_attempt"), 3)

    def test_separate_five_minute_cap_preserves_complete_batch_with_long_run_budget(self):
        self.seed()
        worker.RUN_DEADLINE.set(2100)
        clock = Mock(side_effect=[0, 0, 0, 0, 301])
        with (
            patch.object(seasonality, "time", SimpleNamespace(monotonic=clock)),
            self.assertRaisesRegex(WorkDeferred, "committed complete-year batches"),
        ):
            seasonality.refresh(self.db, 2026)
        self.assert_evidence(2)
        self.assertEqual(self.count("retained_record"), 2)
        self.assertEqual(self.count("seasonal_attempt"), 2)
        self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
        worker.RUN_DEADLINE.set(None)
        seasonality.refresh(self.db, 2026)
        self.assert_evidence()
        self.assertEqual(self.count("seasonal_attempt"), 3)

    def test_bad_final_derived_year_prevents_all_publication(self):
        self.seed()
        self.db.execute(
            "UPDATE published_price_observation SET price='NaN'::numeric WHERE product_id='p-002' AND observed_on='2025-12-01'"
        )
        with self.assertRaisesRegex(ValueError, "finite positive prices"):
            seasonality.refresh(self.db, 2026)
        self.assertEqual(self.count("seasonal_year"), 0)
        self.assertEqual(self.count("retained_record"), 0)
        self.assertEqual(self.count("seasonal_attempt"), 0)

    def test_review_batches_keep_values_and_history_then_resume_without_rewrites(self):
        self.seed()
        seasonality.refresh(self.db, 2026)
        self.db.execute(
            "DELETE FROM published_price_observation WHERE observed_on='2025-12-01'"
        )
        self.fail_second_batch("UPDATE")
        with self.assertRaisesRegex(psycopg.Error, "forced seasonal second batch"):
            seasonality.refresh(self.db, 2026)
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM seasonal_year WHERE review_reason IS NOT NULL"
            ).fetchone()[0],
            2,
        )
        self.assertEqual(self.count("retained_record"), 5)
        self.db.execute("DROP TRIGGER fail_batch ON seasonal_year")
        self.assertEqual(
            seasonality.refresh(self.db, 2026),
            {"complete_years": 0, "reviewed_years": 3},
        )
        self.assertEqual(self.count("retained_record"), 6)
        self.assertEqual(self.count("seasonal_attempt"), 6)
        for product, prices, docs in self.db.execute(
            "SELECT product_id,monthly_prices,source_documents FROM seasonal_year ORDER BY product_id"
        ):
            number = int(product[-3:])
            self.assertEqual(prices, [1000 + number * 100 + m for m in range(1, 13)])
            self.assertEqual(docs, [[f"doc-{number}-{m}"] for m in range(1, 13)])
        seasonality.refresh(self.db, 2026)
        self.assertEqual(self.count("seasonal_attempt"), 6)

    def test_outer_transaction_rolls_back_successful_or_deferred_inner_batches(self):
        self.seed()
        with (
            self.assertRaisesRegex(RuntimeError, "outer rollback"),
            self.db.transaction(),
        ):
            seasonality.refresh(self.db, 2026)
            self.assert_evidence()
            raise RuntimeError("outer rollback")
        self.assertEqual(self.count("seasonal_year"), 0)
        self.assertEqual(self.count("retained_record"), 0)
        self.assertEqual(self.count("seasonal_attempt"), 0)
        with (
            self.assertRaises(WorkDeferred),
            self.db.transaction(),
            patch.object(
                seasonality,
                "time",
                SimpleNamespace(monotonic=Mock(side_effect=[0, 0, 0, 0, 101])),
            ),
        ):
            seasonality.refresh(self.db, 2026, deadline=100)
        self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
        self.assertEqual(self.count("seasonal_year"), 0)
        self.assertEqual(self.count("retained_record"), 0)
        self.assertEqual(self.count("seasonal_attempt"), 0)


if __name__ == "__main__":
    unittest.main()

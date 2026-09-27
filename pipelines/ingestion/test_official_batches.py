"""Official quote batch interruption/resume against isolated PostgreSQL TEMP tables.

Opt in with AGRO_OFFICIAL_BATCH_POSTGRES_TEST=1. No production data is read or
written: public table definitions are copied, then search_path is TEMP only.
"""

import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from psycopg import IntegrityError
from psycopg.pq import TransactionStatus

from . import official_sources, worker
from .resumable_inputs import WorkDeferred


def quotes(count):
    return [
        {
            "source_locator": f"sheet!row {number + 1}",
            "date": "2020-01-31",
            "product_id": f"temp-product-{number}",
            "product_name": f"Temporary product {number}",
            "category": "Temporary source tests",
            "publisher": "Temporary official batch fixture",
            "series": "temporary-monthly",
            "basis": "temporary producer price",
            "currency": "COP",
            "unit": "kg",
            "market": "Temporary market",
            "price": number + 1,
            "details": {"fixture_row": number + 1},
        }
        for number in range(count)
    ]


@unittest.skipUnless(
    os.environ.get("AGRO_OFFICIAL_BATCH_POSTGRES_TEST") == "1",
    "Explicit opt-in for PostgreSQL TEMP-table batch checks",
)
class OfficialBatchPostgresTests(unittest.TestCase):
    def setUp(self):
        # This suite isolates raw batching/routing; dedicated catalog tests cover
        # the derived refresh hook against the actual migration and SQL.
        self.enterContext(
            patch(
                "pipelines.ingestion.official_catalog.refresh_document", return_value=0
            )
        )
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.autocommit)
        # Count attempted inserts, not only surviving rows. A resumed batch must
        # bypass old immutable quotes before invoking insertion triggers.
        self.db.execute(
            """SET search_path=pg_temp;
            CREATE TEMP TABLE official_price_quote (LIKE public.official_price_quote INCLUDING ALL);
            CREATE TEMP TABLE official_source_review (LIKE public.official_source_review INCLUDING ALL);
            CREATE TEMP TABLE ingestion_asset(document_id text PRIMARY KEY,observed_on date);
            CREATE TEMP TABLE source_document(id text PRIMARY KEY,metadata jsonb);
            CREATE TEMP TABLE official_insert_attempt(document_id text,source_locator text);
            CREATE TEMP TABLE ingestion_checkpoint(
              document_id text,processor_version text,step text,records bigint,
              completed_at timestamptz DEFAULT now(),
              PRIMARY KEY(document_id,processor_version,step));
            CREATE FUNCTION pg_temp.track_official_insert() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
              INSERT INTO pg_temp.official_insert_attempt VALUES(NEW.document_id,NEW.source_locator);
              RETURN NEW;
            END $$;
            CREATE TRIGGER track_insert BEFORE INSERT ON pg_temp.official_price_quote
              FOR EACH ROW EXECUTE FUNCTION pg_temp.track_official_insert();"""
        )
        self.assertEqual(
            self.db.execute(
                """SELECT count(*) FROM pg_class WHERE relpersistence='t' AND oid IN (
                'official_price_quote'::regclass,'official_source_review'::regclass,
                'ingestion_asset'::regclass,'source_document'::regclass,'official_insert_attempt'::regclass,
                'ingestion_checkpoint'::regclass)"""
            ).fetchone(),
            (6,),
        )
        self.did = "f" * 64
        self.db.execute(
            """WITH new_asset AS (INSERT INTO ingestion_asset VALUES(%s,NULL))
            INSERT INTO source_document VALUES(%s,'{"ingestion_kind":"coffee"}')""",
            (self.did, self.did),
        )
        token = worker.RUN_DEADLINE.set(None)
        self.addCleanup(worker.RUN_DEADLINE.reset, token)

    def count(self, table):
        # Call sites use fixed fixture-owned identifiers, never external input.
        return self.db.execute(f"SELECT count(*) FROM pg_temp.{table}").fetchone()[0]

    def publish(self, rows):
        return official_sources.publish_rows(self.db, rows, self.did, "coffee")

    def test_first_batch_commits_deferred_second_resumes_without_duplicate_inserts(
        self,
    ):
        rows = quotes(4001)
        worker.RUN_DEADLINE.set(150)
        clock = Mock(side_effect=[100, 200])
        with (
            patch.object(official_sources, "time", SimpleNamespace(monotonic=clock)),
            self.assertRaisesRegex(WorkDeferred, "committed quote batches will resume"),
        ):
            self.publish(iter(rows))
        self.assertEqual(clock.call_count, 2)
        self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
        self.assertEqual(self.count("official_price_quote"), 2000)
        self.assertEqual(self.count("official_insert_attempt"), 2000)
        self.assertEqual(self.count("ingestion_checkpoint"), 0)
        self.assertIsNone(
            self.db.execute("SELECT to_regclass('pg_temp.official_stage')").fetchone()[
                0
            ]
        )
        self.assertEqual(
            self.db.execute("SELECT observed_on FROM ingestion_asset").fetchone(),
            (None,),
        )
        self.assertEqual(
            self.db.execute("SELECT max(price) FROM official_price_quote").fetchone()[
                0
            ],
            2000,
        )
        # Even an explicit rollback after the deferred call cannot erase the
        # already committed first batch (the connection is idle at this point).
        self.db.rollback()
        self.assertEqual(self.count("official_price_quote"), 2000)
        worker.RUN_DEADLINE.set(None)
        self.assertEqual(self.publish(iter(rows)), 4001)
        self.assertEqual(self.count("official_price_quote"), 4001)
        self.assertEqual(self.count("official_insert_attempt"), 4001)
        self.assertEqual(
            self.db.execute(
                "SELECT document_id,processor_version,step,records FROM ingestion_checkpoint"
            ).fetchall(),
            [(self.did, worker.parser_version("coffee"), "official:complete", 4001)],
        )
        self.assertEqual(
            self.db.execute("SELECT observed_on FROM ingestion_asset").fetchone(),
            (date(2020, 1, 31),),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT sum(price),count(DISTINCT source_locator) FROM official_price_quote"
            ).fetchone(),
            (4001 * 4002 // 2, 4001),
        )
        self.assertEqual(self.publish(iter(rows)), 4001)
        self.assertEqual(self.count("official_price_quote"), 4001)
        self.assertEqual(self.count("official_insert_attempt"), 4001)
        self.assertEqual(self.count("ingestion_checkpoint"), 1)

    def test_invalid_final_row_prevents_any_source_publication_or_review(self):
        rows = quotes(2001)
        review = dict(
            rows[0],
            source_locator="review-only",
            price=None,
            details={"quality_issue": "Ambiguous printed price"},
        )
        rows.insert(0, review)
        rows[-1]["price"] = float("nan")
        with self.assertRaises(ValueError):
            self.publish(iter(rows))
        for table in (
            "official_price_quote",
            "official_source_review",
            "official_insert_attempt",
            "ingestion_checkpoint",
        ):
            self.assertEqual(self.count(table), 0)
        self.assertEqual(
            self.db.execute("SELECT observed_on FROM ingestion_asset").fetchone(),
            (None,),
        )

    def test_database_invalid_final_currency_is_rejected_before_first_batch(self):
        rows = quotes(2001)
        rows[-1]["currency"] = "XYZ"
        failure = None
        try:
            self.publish(rows)
        except (ValueError, IntegrityError) as error:
            failure = error
        self.assertEqual(
            self.count("official_price_quote"),
            0,
            "Source-wide validation must catch an invalid currency before any durable quote batch",
        )
        self.assertIsInstance(failure, ValueError)
        self.assertEqual(self.count("official_insert_attempt"), 0)
        self.assertEqual(self.count("ingestion_checkpoint"), 0)

    def test_successful_inner_batches_obey_callers_outer_rollback(self):
        with (
            self.assertRaisesRegex(RuntimeError, "caller rollback"),
            self.db.transaction(),
        ):
            self.assertEqual(self.publish(quotes(2001)), 2001)
            self.assertEqual(self.count("official_price_quote"), 2001)
            self.assertEqual(self.count("official_insert_attempt"), 2001)
            self.assertEqual(self.count("ingestion_checkpoint"), 1)
            raise RuntimeError("caller rollback")
        self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
        self.assertEqual(self.count("official_price_quote"), 0)
        self.assertEqual(self.count("official_insert_attempt"), 0)
        self.assertEqual(self.count("ingestion_checkpoint"), 0)
        self.assertEqual(
            self.db.execute("SELECT observed_on FROM ingestion_asset").fetchone(),
            (None,),
        )

    def test_deferred_inner_batch_does_not_escape_callers_outer_transaction(self):
        worker.RUN_DEADLINE.set(150)
        with (
            patch.object(
                official_sources,
                "time",
                SimpleNamespace(monotonic=Mock(side_effect=[100, 200])),
            ),
            self.assertRaises(WorkDeferred),
            self.db.transaction(),
        ):
            self.publish(quotes(2001))
        self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
        self.assertEqual(self.count("official_price_quote"), 0)
        self.assertEqual(self.count("official_insert_attempt"), 0)
        self.assertEqual(self.count("ingestion_checkpoint"), 0)


if __name__ == "__main__":
    unittest.main()

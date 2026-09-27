"""Persistent official cache parity, completion, rollback and invalidation."""

import os
import re
import threading
import time
import unittest
import uuid
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from psycopg import Error as DatabaseError
from psycopg.rows import dict_row

from . import official_catalog, official_sources, worker
from .resumable_inputs import WorkDeferred

TABLES = (
    "source_document",
    "official_price_quote",
    "official_source_review",
    "ingestion_asset",
    "ingestion_checkpoint",
)
MIGRATION = Path(__file__).parent / "migrations/20260927_007_official_catalog.sql"


def install_cache(db, *, temporary=True):
    migration = MIGRATION.read_text()
    migration = re.sub(r"^GRANT .*;\n", "", migration, flags=re.MULTILINE)
    if temporary:
        migration = migration.replace(
            "CREATE TABLE IF NOT EXISTS", "CREATE TEMP TABLE IF NOT EXISTS"
        )
        migration = migration.replace(
            "CREATE OR REPLACE FUNCTION dirty_",
            "CREATE OR REPLACE FUNCTION pg_temp.dirty_",
        )
        migration = migration.replace(
            "EXECUTE FUNCTION dirty_", "EXECUTE FUNCTION pg_temp.dirty_"
        )
    db.execute(migration)


def quote(day="2026-09-20", price=2000, locator="row 1", product="Cacao"):
    return {
        "source_locator": locator,
        "date": day,
        "product_id": product.lower(),
        "product_name": product,
        "category": "Cacao",
        "publisher": "Official test",
        "series": "farmgate",
        "basis": "Referencia por kilogramo",
        "currency": "COP",
        "unit": "kg",
        "market": "Colombia",
        "price": price,
        "details": {},
    }


@unittest.skipUnless(
    os.environ.get("AGRO_OFFICIAL_CATALOG_TEST") == "1",
    "Explicit opt-in for isolated PostgreSQL cache checks",
)
class OfficialCatalogPostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp; SET statement_timeout='15s'")
        for table in TABLES:
            self.db.execute(
                f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"
            )
        self.db.execute(
            "CREATE INDEX quote_identity ON official_price_quote(quote_key,observed_on DESC)"
        )
        install_cache(self.db)
        token = worker.RUN_DEADLINE.set(None)
        self.addCleanup(worker.RUN_DEADLINE.reset, token)
        self.version = self.enterContext(
            patch.object(worker, "parser_version", return_value="fixture-v1")
        )

    def original(self, label, retrieved="2026-09-20T00:00:00Z"):
        did = sha256(label.encode()).hexdigest()
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at) VALUES(%s,%s,'fixture',%s,'text/html','original','',%s,%s)",
            (did, label, "https://example.invalid/" + label, label.encode(), retrieved),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,document_id,status) VALUES(%s,'colombia-pork-pdf',%s,'pending')",
            ("https://example.invalid/" + label, did),
        )
        return did

    def publish(self, did, rows):
        return official_sources.publish_rows(self.db, rows, did, "colombia-pork-pdf")

    def cache(self):
        return self.db.execute(
            "SELECT quote_key,payload,dirty FROM official_catalog_current ORDER BY quote_key"
        ).fetchall()

    def assert_parity(self):
        keys = [row[0] for row in self.cache()]
        with self.db.cursor(row_factory=dict_row) as cursor:
            expected = cursor.execute(
                official_catalog.LATEST_FOR_KEYS_SQL, (keys,)
            ).fetchall()
        # JSONB's dates/timestamps are serialized; normalize through PostgreSQL.
        actual = {
            row[0]: row[1] for row in self.cache() if row[1] is not None and not row[2]
        }
        expected_json = self.db.execute(
            "SELECT to_jsonb(q) FROM (" + official_catalog.LATEST_FOR_KEYS_SQL + ") q",
            (keys,),
        ).fetchall()
        self.assertEqual(actual, {row[0]["quote_key"]: row[0] for row in expected_json})
        return expected

    def test_publication_latest_previous_and_older_replay_match_canonical_values(self):
        current = self.original("current", "2026-09-25T00:00:00Z")
        old = self.original("old", "2026-09-10T00:00:00Z")
        self.publish(
            current,
            [
                quote("2026-09-24", 2100, "latest"),
                quote("2026-09-23", 2000, "previous"),
            ],
        )
        self.publish(old, [quote("2026-09-24", 1800, "old")])
        row = self.assert_parity()[0]
        self.assertEqual(
            (row["price"], row["previous_price"], row["document_id"]),
            (2100, 2000, current),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM ingestion_checkpoint WHERE step='official:complete'"
            ).fetchone()[0],
            2,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0],
            3,
        )

    def test_review_only_refreshes_prior_keys_and_corrected_parse_republishes(self):
        did = self.original("review")
        self.publish(did, [quote()])
        self.version.return_value = "review-v2"
        row = quote(price=None)
        row["details"] = {"quality_issue": "Ambiguous label"}
        self.publish(did, [row])
        self.assertEqual([(p, d) for _, p, d in self.cache()], [(None, False)])
        self.version.return_value = "corrected-v3"
        self.publish(did, [quote(price=2200)])
        self.assertEqual(self.assert_parity()[0]["price"], 2200)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_source_review").fetchone()[
                0
            ],
            1,
        )

    def test_asset_reviews_invalidate_and_checked_at_does_not(self):
        did = self.original("asset")
        self.publish(did, [quote()])
        before = self.db.execute(
            "SELECT xmin::text FROM official_catalog_current"
        ).fetchone()
        self.db.execute("UPDATE ingestion_asset SET checked_at=now(),status='complete'")
        self.assertEqual(
            self.db.execute(
                "SELECT xmin::text FROM official_catalog_current"
            ).fetchone(),
            before,
        )
        self.db.execute("UPDATE ingestion_asset SET status='review',observed_on=NULL")
        self.assertTrue(self.cache()[0][2])
        self.assertEqual(official_catalog.refresh_dirty(self.db), 1)
        self.assertEqual(self.cache()[0][1:], (None, False))
        self.db.execute("UPDATE ingestion_asset SET status='pending'")
        self.assertTrue(self.cache()[0][2])
        official_catalog.refresh_dirty(self.db)
        self.assertEqual(self.assert_parity()[0]["price"], 2000)

    def test_review_of_previous_price_refreshes_distinct_previous_date(self):
        did = self.original("previous")
        self.publish(
            did,
            [
                quote("2026-09-24", 2200, "new"),
                quote("2026-09-23", 2100, "prior"),
                quote("2026-09-22", 2000, "old"),
            ],
        )
        self.db.execute(
            "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) VALUES(%s,'prior','review','{}','ambiguous')",
            (did,),
        )
        self.assertTrue(self.cache()[0][2])
        official_catalog.refresh_dirty(self.db)
        self.assertEqual(self.assert_parity()[0]["previous_price"], 2000)

    def test_partial_batch_can_refresh_valid_quotes_without_original_completion(self):
        did = self.original("partial")
        rows = [quote(locator=f"row {n}", product=f"Product {n}") for n in range(2001)]
        worker.RUN_DEADLINE.set(150)
        with (
            patch.object(
                official_sources,
                "time",
                SimpleNamespace(monotonic=Mock(side_effect=[100, 200])),
            ),
            self.assertRaises(WorkDeferred),
        ):
            self.publish(did, rows)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0],
            2000,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone()[0],
            0,
        )
        self.assertTrue(all(row[2] for row in self.cache()))
        self.assertEqual(official_catalog.refresh_dirty(self.db, limit=10), 10)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone()[0],
            0,
        )
        worker.RUN_DEADLINE.set(None)
        self.publish(did, rows)
        self.assertEqual(len(self.assert_parity()), 2001)
        self.assertFalse(any(row[2] for row in self.cache()))

    def test_failed_final_refresh_rolls_back_completion_but_keeps_durable_quote_batches(
        self,
    ):
        did = self.original("refresh-fails")
        with (
            patch.object(
                official_catalog,
                "refresh_keys",
                side_effect=RuntimeError("cache unavailable"),
            ),
            self.assertRaisesRegex(RuntimeError, "cache unavailable"),
        ):
            self.publish(did, [quote()])
        self.assertTrue(self.cache()[0][2])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0],
            1,
        )
        self.publish(did, [quote()])
        self.assertEqual(self.assert_parity()[0]["price"], 2000)

    def test_outer_rollback_includes_quotes_cache_and_original_completion(self):
        did = self.original("rollback")
        with self.assertRaisesRegex(RuntimeError, "rollback"), self.db.transaction():
            self.publish(did, [quote()])
            self.assertEqual(len(self.cache()), 1)
            raise RuntimeError("rollback")
        self.assertEqual(self.cache(), [])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone()[0],
            0,
        )

    def test_bootstrap_batches_are_resumable_without_dropping_cache_rows(self):
        did = self.original("bootstrap")
        self.publish(
            did, [quote(product=f"P{n}", locator=f"row {n}") for n in range(5)]
        )
        self.db.execute("UPDATE official_catalog_current SET dirty=true,payload=NULL")
        result = official_catalog.bootstrap(self.db, batch_size=2)
        self.assertEqual(result["keys"], 5)
        self.assertEqual(len(self.assert_parity()), 5)
        self.assertEqual(
            official_catalog.bootstrap(self.db, after=result["last_key"])["keys"], 0
        )

    def test_migration_seeds_missing_old_quotes_without_dirtying_clean_payloads(self):
        did = self.original("migration-seed")
        self.publish(did, [quote()])
        before = self.cache()
        # This clean existing key remains intact on migration reapplication.
        install_cache(self.db)
        self.assertEqual(self.cache(), before)
        # Simulate an old database with quotes predating dirty triggers/cache.
        self.db.execute(
            "ALTER TABLE official_price_quote DISABLE TRIGGER official_catalog_quotes"
        )
        second = quote(product="Legacy", locator="legacy")
        with patch.object(official_catalog, "refresh_document", return_value=0):
            self.publish(did, [second])
        self.assertEqual(len(self.cache()), 1)
        install_cache(self.db)
        self.assertEqual(len(self.cache()), 2)
        self.assertEqual(sum(row[2] for row in self.cache()), 1)
        self.assertEqual(official_catalog.refresh_dirty(self.db), 1)
        self.assertEqual(len(self.assert_parity()), 2)

    def test_concurrent_review_cannot_be_overwritten_by_clean_stale_refresh(self):
        # TEMP relations cannot be shared across sessions. Use a disposable schema
        # only after proving this connection is the private local test cluster.
        first, second = worker.connect(), worker.connect()
        self.assertTrue(first.info.host.startswith("/tmp/agro-catalog-pg-"))
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        name = "cache_concurrency_" + uuid.uuid4().hex
        first.execute(f"CREATE SCHEMA {name}")
        self.addCleanup(lambda: first.execute(f"DROP SCHEMA {name} CASCADE"))
        for db in (first, second):
            db.execute(f"SET search_path={name}; SET statement_timeout='5s'")
        for table in TABLES:
            first.execute(f"CREATE TABLE {table} (LIKE public.{table} INCLUDING ALL)")
        install_cache(first, temporary=False)
        self.db = first
        did = self.original("concurrent-review")
        self.publish(did, [quote()])
        key = self.cache()[0][0]
        errors = []
        started = threading.Event()

        def reviewer():
            try:
                started.set()
                second.execute(
                    "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) VALUES(%s,'row 1','review','{}','Concurrent withdrawal')",
                    (did,),
                )
            except DatabaseError as error:
                errors.append(error)

        with first.transaction():
            first.execute(
                "SELECT quote_key FROM official_catalog_current WHERE quote_key=%s FOR UPDATE",
                (key,),
            ).fetchall()
            thread = threading.Thread(target=reviewer)
            thread.start()
            self.assertTrue(started.wait(1))
            until = time.monotonic() + 3
            while time.monotonic() < until:
                waiting = first.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s",
                    (second.info.backend_pid,),
                ).fetchone()
                if waiting and waiting[0] == "Lock":
                    break
                time.sleep(0.01)
            else:
                self.fail("Concurrent review did not wait for the cache row lock")
            official_catalog.refresh_keys(first, [key])
            self.assertFalse(self.cache()[0][2])
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(
            self.cache()[0][2],
            "Committed review must invalidate the refresh computed before it",
        )
        official_catalog.refresh_dirty(first)
        self.assertEqual(self.cache()[0][1:], (None, False))


if __name__ == "__main__":
    unittest.main()

"""Private PostgreSQL proof that fresh invalidations cannot overtake waiting keys."""

import os
import re
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg

from . import official_catalog, worker
from .resumable_inputs import WorkDeferred


ROOT = Path(__file__).parent
BASE = ROOT / "migrations/20260927_007_official_catalog.sql"
OLDER = ROOT / "migrations/20261004_054_official_catalog_previous_date.sql"
FIFO = ROOT / "migrations/20261005_055_official_catalog_dirty_fifo.sql"
DOC = "d" * 64


def private_dsn():
    dsn = os.environ.get("AGRO_REFERENCE_TEST_DSN")
    if not dsn and os.environ.get("AGRO_REFERENCE_TEST_SOCKET"):
        dsn = f"host={os.environ['AGRO_REFERENCE_TEST_SOCKET']} port=65443 dbname=postgres"
    if not dsn:
        raise RuntimeError("Explicit isolated PostgreSQL DSN required")
    return dsn


@unittest.skipUnless(
    os.environ.get("AGRO_OFFICIAL_CATALOG_TEST") == "1",
    "Explicit isolated PostgreSQL opt-in",
)
class DirtyCatalogFifoPostgres(unittest.TestCase):
    def setUp(self):
        self.dsn = private_dsn()
        self.db = psycopg.connect(self.dsn, autocommit=True)
        if not str(self.db.info.host).startswith("/tmp/agro-"):
            self.db.close()
            raise RuntimeError("Only isolated private PostgreSQL is allowed")
        self.schema = "qa_dirty_fifo_" + uuid.uuid4().hex[:12]
        self.db.execute(f"CREATE SCHEMA {self.schema}")
        self.db.execute(f"SET search_path={self.schema},public")
        self.db.execute("SET statement_timeout='30s'; SET lock_timeout='10s'")
        for table in ("source_document", "official_price_quote", "official_source_review",
                      "ingestion_asset", "ingestion_checkpoint"):
            self.db.execute(f"CREATE TABLE {table} (LIKE public.{table} INCLUDING ALL)")
        self.db.execute(re.sub(r"^GRANT .*;\n", "", BASE.read_text(), flags=re.MULTILINE))
        self.db.execute(OLDER.read_text())
        self.token = worker.RUN_DEADLINE.set(None)

    def tearDown(self):
        worker.RUN_DEADLINE.reset(self.token)
        self.db.execute(f"DROP SCHEMA {self.schema} CASCADE")
        self.db.close()

    def install_fifo(self):
        self.db.execute(FIFO.read_text())

    def test_migration_seeds_existing_order_and_is_idempotent(self):
        early, later, never, clean = (f"{n:064x}" for n in range(1, 5))
        self.db.execute("""INSERT INTO official_catalog_current
          (quote_key,dirty,version,refreshed_at) VALUES
          (%s,true,'official-catalog-v1','2020-01-01'),
          (%s,true,'official-catalog-v1','2021-01-01'),
          (%s,true,'official-catalog-v1',NULL),
          (%s,false,'official-catalog-v1','2019-01-01')""",
                        (early, later, never, clean))
        self.install_fifo()
        rows = self.db.execute("SELECT quote_key,dirty,dirty_since::text FROM official_catalog_current "
                               "ORDER BY dirty_since NULLS FIRST,quote_key").fetchall()
        self.assertEqual({key: dirty for key, dirty, _ in rows},
                         {early: True, later: True, never: True, clean: False})
        times = {key: stamp for key, _, stamp in rows}
        self.assertIsNone(times[clean])
        self.assertTrue(times[early].startswith("2020-01-01"))
        self.assertTrue(times[later].startswith("2021-01-01"))
        self.assertEqual(times[never], "-infinity")
        index = self.db.execute("SELECT indexdef FROM pg_indexes WHERE schemaname=%s "
                                "AND indexname='official_catalog_dirty_fifo'", (self.schema,)).fetchone()[0]
        self.assertIn("(dirty_since, quote_key)", index)
        self.assertIn("WHERE dirty", index)
        self.install_fifo()
        self.assertEqual({key: stamp for key, _, stamp in self.db.execute(
            "SELECT quote_key,dirty,dirty_since::text FROM official_catalog_current").fetchall()}, times)

    def test_late_invalidated_old_cache_cannot_jump_earlier_waiters(self):
        self.install_fifo()
        waiting = [f"{n:064x}" for n in range(1, 101)]
        late = "f" * 64
        self.db.execute("""INSERT INTO official_catalog_current
          (quote_key,dirty,version,refreshed_at)
          SELECT lpad(to_hex(n),64,'0'),false,%s,now()-interval '1 hour'
          FROM generate_series(1,100) n""", (official_catalog.VERSION,))
        self.db.execute("INSERT INTO official_catalog_current(quote_key,dirty,version,refreshed_at) "
                        "VALUES(%s,false,%s,'2012-01-01')", (late, official_catalog.VERSION))
        official_catalog.mark_keys_dirty(self.db, waiting)
        first = self.db.execute("SELECT min(dirty_since),max(dirty_since) "
                                "FROM official_catalog_current WHERE quote_key=ANY(%s)",
                                (waiting,)).fetchone()
        official_catalog.mark_keys_dirty(self.db, [late])
        late_stamp = self.db.execute("SELECT dirty_since FROM official_catalog_current "
                                     "WHERE quote_key=%s", (late,)).fetchone()[0]
        self.assertGreater(late_stamp, first[1])
        self.assertEqual(official_catalog.refresh_dirty(self.db, limit=100), 100)
        self.assertTrue(self.db.execute("SELECT dirty FROM official_catalog_current "
                                        "WHERE quote_key=%s", (late,)).fetchone()[0])
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_catalog_current "
                                         "WHERE dirty").fetchone()[0], 1)
        self.assertEqual(official_catalog.refresh_dirty(self.db, limit=100), 1)
        self.assertIsNone(self.db.execute("SELECT dirty_since FROM official_catalog_current "
                                          "WHERE quote_key=%s", (late,)).fetchone()[0])

    def test_repeated_invalidation_keeps_place_and_all_dirty_paths_stamp(self):
        self.install_fifo()
        key = "a" * 64
        self.db.execute("INSERT INTO official_catalog_current(quote_key,dirty,version) "
                        "VALUES(%s,false,%s)", (key, official_catalog.VERSION))
        official_catalog.mark_keys_dirty(self.db, [key])
        before = self.db.execute("SELECT dirty_since,xmin::text FROM official_catalog_current "
                                 "WHERE quote_key=%s", (key,)).fetchone()
        official_catalog.mark_keys_dirty(self.db, [key])
        self.assertEqual(self.db.execute("SELECT dirty_since,xmin::text "
                                         "FROM official_catalog_current WHERE quote_key=%s",
                                         (key,)).fetchone(), before)
        official_catalog.refresh_keys(self.db, [key])
        self.assertEqual(self.db.execute("SELECT dirty,dirty_since FROM official_catalog_current "
                                         "WHERE quote_key=%s", (key,)).fetchone(), (False, None))
        self.db.execute("INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content) "
                        "VALUES(%s,'native','DANE','https://example.invalid/native.pdf','application/pdf','original','',%s)",
                        (DOC, b'native'))
        self.db.execute("""INSERT INTO official_price_quote
          (document_id,source_locator,parser_version,quote_key,product_id,product_name,
           category,publisher,series,basis,currency,unit,market,observed_on,price,details)
          VALUES(%s,'p1,r1','v1',%s,'leche','Leche','Lácteos','DANE',
           'dane-weekly','Precio mayorista semanal','COP','kg','Mercado',
           '2026-09-01',1000,'{}')""", (DOC, key))
        quote_stamp = self.db.execute("SELECT dirty_since FROM official_catalog_current "
                                      "WHERE quote_key=%s", (key,)).fetchone()[0]
        self.assertIsNotNone(quote_stamp)
        official_catalog.refresh_keys(self.db, [key])
        self.db.execute("INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) "
                        "VALUES(%s,'p1,r1','v1','{}','native conflict')", (DOC,))
        review_stamp = self.db.execute("SELECT dirty_since FROM official_catalog_current "
                                       "WHERE quote_key=%s", (key,)).fetchone()[0]
        self.assertGreater(review_stamp, quote_stamp)
        official_catalog.refresh_keys(self.db, [key])
        self.db.execute("INSERT INTO ingestion_asset(url,kind,status,document_id,observed_on) "
                        "VALUES('https://example.invalid/native.pdf','dane-weekly-pdf','review',%s,'2026-09-01')",
                        (DOC,))
        asset_stamp = self.db.execute("SELECT dirty_since FROM official_catalog_current "
                                      "WHERE quote_key=%s", (key,)).fetchone()[0]
        self.assertGreater(asset_stamp, review_stamp)

    def test_concurrent_refresh_then_new_quote_remains_dirty(self):
        self.install_fifo()
        key = "b" * 64
        self.db.execute("INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content) "
                        "VALUES(%s,'native','DANE','https://example.invalid/native.pdf','application/pdf','original','',%s)",
                        (DOC, b'native'))
        self.db.execute("INSERT INTO official_catalog_current(quote_key,dirty,version) "
                        "VALUES(%s,true,%s)", (key, official_catalog.VERSION))
        started, finished, errors = threading.Event(), threading.Event(), []

        def insert_after_lock():
            try:
                with psycopg.connect(self.dsn, autocommit=True) as other:
                    other.execute(f"SET search_path={self.schema},public")
                    other.execute("SET lock_timeout='5s'")
                    started.set()
                    other.execute("""INSERT INTO official_price_quote
                      (document_id,source_locator,parser_version,quote_key,product_id,product_name,
                       category,publisher,series,basis,currency,unit,market,observed_on,price,details)
                      VALUES(%s,'p1,r1','v1',%s,'leche','Leche','Lácteos','DANE',
                       'dane-weekly','Precio mayorista semanal','COP','kg','Mercado',
                       '2026-09-01',1000,'{}')""", (DOC, key))
            except Exception as error:
                errors.append(error)
            finally:
                finished.set()

        self.db.execute("BEGIN")
        thread = None
        try:
            official_catalog.refresh_keys(self.db, [key])
            clean_stamp = self.db.execute("SELECT dirty_since FROM official_catalog_current "
                                          "WHERE quote_key=%s", (key,)).fetchone()[0]
            self.assertIsNone(clean_stamp)
            thread = threading.Thread(target=insert_after_lock)
            thread.start()
            self.assertTrue(started.wait(3))
            self.assertFalse(finished.wait(0.1), "quote insert must wait for cache row lock")
        finally:
            self.db.execute("COMMIT")
            if thread:
                thread.join(6)
        self.assertFalse(errors)
        self.assertTrue(finished.is_set())
        dirty, stamp, refreshed = self.db.execute(
            "SELECT dirty,dirty_since,refreshed_at FROM official_catalog_current WHERE quote_key=%s",
            (key,)).fetchone()
        self.assertTrue(dirty)
        self.assertGreaterEqual(stamp, refreshed)

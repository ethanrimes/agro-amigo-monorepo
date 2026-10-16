"""Exact winner-date invalidation and bounded dirty priority on private PG."""

import os
import re
import threading
import time
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import official_catalog, worker
from .resumable_inputs import WorkDeferred


ROOT = Path(__file__).parent
OLD = ROOT / "migrations/20260927_007_official_catalog.sql"
NEW = ROOT / "migrations/20261004_054_official_catalog_previous_date.sql"
DIRTY_FIFO = ROOT / "migrations/20261005_055_official_catalog_dirty_fifo.sql"
KEY = "a" * 64
DOC_2017, DOC_2019, DOC_2026 = ("1" * 64, "2" * 64, "3" * 64)


def private_dsn():
    dsn = os.environ.get("AGRO_REFERENCE_TEST_DSN")
    if not dsn and os.environ.get("AGRO_REFERENCE_TEST_SOCKET"):
        dsn = f"host={os.environ['AGRO_REFERENCE_TEST_SOCKET']} port=65443 dbname=postgres"
    if not dsn:
        raise RuntimeError("Explicit private PostgreSQL DSN or socket required")
    return dsn


def document(db, did, label):
    db.execute("""INSERT INTO source_document
      (id,title,publisher,source_url,media_type,kind,reference_period,content)
      VALUES(%s,%s,'DANE',%s,'application/pdf','original','',%s)""",
               (did, label, f"https://example.invalid/{label}.pdf", label.encode()))


def price(db, did, locator, version, day, amount, key=KEY):
    db.execute("""INSERT INTO official_price_quote
      (document_id,source_locator,parser_version,quote_key,product_id,product_name,
       category,publisher,series,basis,currency,unit,market,observed_on,price,
       min_price,max_price,details)
      VALUES(%s,%s,%s,%s,'limon-tahiti','Limón Tahití','Frutas frescas','DANE · SIPSA',
        'dane-weekly','Precio mayorista semanal','COP','kg',
        'Medellín, Plaza Minorista "José María Villa"',%s,%s,%s,%s,%s)""",
               (did, locator, version, key, day, amount, amount, amount,
                Jsonb({"identity_dimensions": {"source_product": "Limón Tahití"}})))


class OlderQuoteInvalidationPostgres(unittest.TestCase):
    def setUp(self):
        self.dsn = private_dsn()
        self.db = psycopg.connect(self.dsn, autocommit=True)
        if not str(self.db.info.host).startswith("/tmp/agro-"):
            self.db.close()
            raise RuntimeError("Only isolated private PostgreSQL is allowed")
        self.schema = "qa_v28_" + uuid.uuid4().hex[:12]
        self.db.execute(f"CREATE SCHEMA {self.schema}")
        self.db.execute(f"SET search_path={self.schema},public")
        self.db.execute("SET statement_timeout='30s'; SET lock_timeout='10s'")
        for table in ("source_document", "official_price_quote", "official_source_review",
                      "ingestion_asset", "ingestion_checkpoint"):
            self.db.execute(f"CREATE TABLE {table} (LIKE public.{table} INCLUDING ALL)")
        self.db.execute(re.sub(r"^GRANT .*;\n", "", OLD.read_text(), flags=re.MULTILINE))
        self.db.execute(NEW.read_text())
        self.db.execute(DIRTY_FIFO.read_text())
        self.token = worker.RUN_DEADLINE.set(None)

    def tearDown(self):
        worker.RUN_DEADLINE.reset(self.token)
        self.db.execute(f"DROP SCHEMA {self.schema} CASCADE")
        self.db.close()

    def seed_winners(self):
        for did, label in ((DOC_2017, "2017-native-p16"), (DOC_2019, "2019-native-r412"),
                           (DOC_2026, "2026-native-p26")):
            document(self.db, did, label)
        # Independently checked literal Limón Tahití / Plaza Minorista anchors.
        price(self.db, DOC_2019, "1.2!row 412,cols C:E", "v19", "2019-02-15", 1400)
        price(self.db, DOC_2026, "PDF page 26,table 1,column 1,line 25", "v26",
              "2026-10-02", 3775)
        official_catalog.refresh_keys(self.db, [KEY])
        entry = self.db.execute("""SELECT payload,dirty,winner_observed_on,previous_observed_on
          FROM official_catalog_current WHERE quote_key=%s""", (KEY,)).fetchone()
        self.assertFalse(entry[1])
        self.assertEqual((entry[2], entry[3]), (date(2026, 10, 2), date(2019, 2, 15)))
        self.assertEqual(entry[0]["previous_price"], 1400)
        self.assertNotIn("previous_observed_on", entry[0], "internal date must not alter public JSON")
        return entry[0]

    def dirty(self):
        return self.db.execute("SELECT dirty FROM official_catalog_current WHERE quote_key=%s",
                               (KEY,)).fetchone()[0]

    def test_older_native_quote_is_retained_without_dirtying_same_current_previous_winners(self):
        payload = self.seed_winners()
        price(self.db, DOC_2017, "PDF page 16,table 1,column 2,line 62", "v17",
              "2017-01-27", 1063)
        self.assertFalse(self.dirty())
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0], 3)
        self.assertEqual(self.db.execute("SELECT payload FROM official_catalog_current WHERE quote_key=%s",
                                         (KEY,)).fetchone()[0], payload)
        # An explicit source replay still invalidates; this optimization never
        # bypasses source-wide retirement or review/status changes.
        official_catalog.mark_document_dirty(self.db, DOC_2017)
        self.assertTrue(self.dirty())

    def test_equal_previous_newer_and_superseding_locator_remain_dirty(self):
        for day, amount, locator in (("2019-02-15", 1450, "equal previous"),
                                     ("2020-02-15", 1900, "between"),
                                     ("2026-10-02", 3900, "same latest")):
            with self.subTest(day=day):
                self.seed_winners()
                price(self.db, DOC_2017, locator, "v17", day, amount)
                self.assertTrue(self.dirty())
                self.db.execute("TRUNCATE official_price_quote,official_catalog_current")
                self.db.execute("TRUNCATE source_document")
        self.seed_winners()
        # A new parse gives the current winner's exact locator an older date.
        # It suppresses that current quote, so the cache must be invalidated.
        price(self.db, DOC_2026, "PDF page 26,table 1,column 1,line 25", "v27",
              "2017-01-27", 1063)
        self.assertTrue(self.dirty())

    def test_equal_parse_time_same_locator_correction_invalidates_winner(self):
        self.seed_winners()
        locator = "PDF page 26,table 1,column 1,line 25"
        old_parsed_at = self.db.execute("""SELECT parsed_at FROM official_price_quote
          WHERE document_id=%s AND source_locator=%s AND parser_version='v26'""",
                                        (DOC_2026, locator)).fetchone()[0]
        # The physical locator is the existing 2026 current winner, but the
        # correction reports an older date at exactly the same parse instant.
        # Equal timestamps cannot establish which revision wins, so invalidate.
        self.db.execute("""INSERT INTO official_price_quote
          (document_id,source_locator,parser_version,quote_key,product_id,product_name,
           category,publisher,series,basis,currency,unit,market,observed_on,price,
           min_price,max_price,details,parsed_at)
          SELECT document_id,source_locator,'v27',quote_key,product_id,product_name,
           category,publisher,series,basis,currency,unit,market,'2017-01-27',1063,
           1063,1063,details,%s FROM official_price_quote
          WHERE document_id=%s AND source_locator=%s AND parser_version='v26'""",
                        (old_parsed_at, DOC_2026, locator))
        self.assertTrue(self.dirty())
        self.assertEqual(self.db.execute("""SELECT count(*) FROM official_price_quote
          WHERE document_id=%s AND source_locator=%s""", (DOC_2026, locator)).fetchone()[0], 2)

    def test_one_statement_mixed_dates_invalidates_but_all_older_rows_do_not(self):
        bulk = """INSERT INTO official_price_quote
          (document_id,source_locator,parser_version,quote_key,product_id,product_name,
           category,publisher,series,basis,currency,unit,market,observed_on,price,
           min_price,max_price,details)
          SELECT %s,v.locator,'v17',%s,'limon-tahiti','Limón Tahití',
           'Frutas frescas','DANE · SIPSA','dane-weekly','Precio mayorista semanal',
           'COP','kg','Medellín, Plaza Minorista "José María Villa"',
           v.observed_on::date,v.amount,v.amount,v.amount,
           '{"identity_dimensions":{"source_product":"Limón Tahití"}}'::jsonb
          FROM (VALUES (%s::text,%s::date,%s::numeric),
                       (%s::text,%s::date,%s::numeric)) AS v(locator,observed_on,amount)"""
        self.seed_winners()
        self.db.execute(bulk, (DOC_2017, KEY, "old p16", "2016-01-27", 900,
                               "old p17", "2017-01-27", 1063))
        self.assertFalse(self.dirty(), "both rows precede the 2019 previous winner")
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0], 4)
        self.db.execute(bulk, (DOC_2017, KEY, "old p18", "2018-01-27", 1200,
                               "new p19", "2020-01-27", 1900))
        self.assertTrue(self.dirty(), "the mixed statement has one new previous winner")
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0], 6)

    def test_post_lock_wall_day_and_future_quote_remain_guarded(self):
        # A long transaction or row-lock wait can cross a Bogotá midnight.
        # The trigger captures the wall-current day after the lock, while the
        # refresh's second statement uses its own statement day. A private
        # next-day query demonstrates an already-retained future quote's
        # eligibility without changing the server clock.
        ddl = self.db.execute("""SELECT pg_get_functiondef(
          'dirty_official_quote_catalog()'::regprocedure)""").fetchone()[0]
        self.assertIn("fresh_bogota_day := (clock_timestamp() AT TIME ZONE 'America/Bogota')::date", ddl)
        self.assertLess(ddl.index("FOR UPDATE OF c"), ddl.index("fresh_bogota_day := (clock_timestamp()"))
        self.assertNotIn("CURRENT_TIMESTAMP", ddl)
        self.assertIn("statement_timestamp() AT TIME ZONE 'America/Bogota'",
                      official_catalog.LATEST_FOR_KEYS_SQL)
        self.assertTrue(any(isinstance(value, str) and "false,%s,statement_timestamp()" in value
                            for value in official_catalog.refresh_keys.__code__.co_consts))
        self.seed_winners()
        tomorrow = self.db.execute("""SELECT ((statement_timestamp() AT TIME ZONE
          'America/Bogota')::date + 1)""").fetchone()[0]
        price(self.db, DOC_2017, "future native p16", "v17", tomorrow.isoformat(), 3900)
        self.assertTrue(self.dirty())
        official_catalog.refresh_keys(self.db, [KEY])
        today_payload = self.db.execute("SELECT payload FROM official_catalog_current WHERE quote_key=%s",
                                        (KEY,)).fetchone()[0]
        self.assertEqual(today_payload["price"], 3775)
        hypothetical_next_day = official_catalog.LATEST_FOR_KEYS_SQL.replace(
            "statement_timestamp()", "(statement_timestamp() + interval '1 day')")
        next_prices = self.db.execute("SELECT verified.price FROM (" + hypothetical_next_day +
                                      ") verified", ([KEY],)).fetchall()
        self.assertEqual(next_prices, [(3900,)])
        self.db.execute("UPDATE official_catalog_current SET refreshed_at=statement_timestamp()-interval '1 day' WHERE quote_key=%s", (KEY,))
        price(self.db, DOC_2017, "older after rollover", "v17", "2017-01-27", 1063)
        self.assertTrue(self.dirty(), "older insert after a previous-day refresh cannot suppress recheck")

    def test_missing_previous_or_migrated_internal_dates_fail_closed(self):
        document(self.db, DOC_2017, "old")
        document(self.db, DOC_2026, "current")
        price(self.db, DOC_2026, "latest", "v26", "2026-10-02", 3775)
        official_catalog.refresh_keys(self.db, [KEY])
        self.assertIsNone(self.db.execute(
            "SELECT previous_observed_on FROM official_catalog_current WHERE quote_key=%s",
            (KEY,)).fetchone()[0])
        price(self.db, DOC_2017, "old", "v17", "2017-01-27", 1063)
        self.assertTrue(self.dirty())
        official_catalog.refresh_keys(self.db, [KEY])
        self.db.execute("UPDATE official_catalog_current SET previous_observed_on=NULL WHERE quote_key=%s", (KEY,))
        price(self.db, DOC_2017, "older", "v18", "2016-01-27", 900)
        self.assertTrue(self.dirty())

    def test_mismatched_version_payload_day_and_future_winner_are_conservative(self):
        changes = (
            ("version=''", "stale version"),
            ("previous_observed_on=NULL", "unmigrated previous date"),
            ("winner_observed_on=NULL", "unmigrated winner date"),
            ("payload=jsonb_set(payload,'{observed_on}','\"2018-01-01\"')", "date mismatch"),
            ("winner_observed_on=CURRENT_DATE+interval '1 day'", "future winner"),
            ("refreshed_at=now()-interval '2 day'", "prior publication day"),
            ("dirty=true", "already dirty"),
        )
        for update, label in changes:
            with self.subTest(label=label):
                self.seed_winners()
                self.db.execute(f"UPDATE official_catalog_current SET {update} WHERE quote_key=%s", (KEY,))
                price(self.db, DOC_2017, "2017 p16", "v17", "2017-01-27", 1063)
                self.assertTrue(self.dirty(), label)
                self.db.execute("TRUNCATE official_price_quote,official_catalog_current")
                self.db.execute("TRUNCATE source_document")

    def test_asset_review_and_revised_source_keys_still_invalidate(self):
        self.seed_winners()
        price(self.db, DOC_2017, "old", "v17", "2017-01-27", 1063)
        self.assertFalse(self.dirty())
        self.db.execute("""INSERT INTO ingestion_asset
          (url,kind,status,document_id,observed_on)
          VALUES('https://example.invalid/old.pdf','dane-weekly-pdf','review',%s,'2017-01-27')""",
                        (DOC_2017,))
        self.assertTrue(self.dirty(), "asset review trigger may withdraw the old source")
        official_catalog.refresh_keys(self.db, [KEY])
        # A revised source maps the same literal locator to a new identity.
        # The insert trigger dirties the new identity; the explicit source
        # invalidation remains responsible for withdrawing the prior key.
        new_key = "b" * 64
        price(self.db, DOC_2026, "PDF page 26,table 1,column 1,line 25", "v27",
              "2017-01-27", 1063, new_key)
        self.assertTrue(self.db.execute("SELECT dirty FROM official_catalog_current WHERE quote_key=%s",
                                        (new_key,)).fetchone()[0])
        official_catalog.mark_document_dirty(self.db, DOC_2026)
        self.assertTrue(self.dirty())

    def test_review_invalidation_is_not_suppressed(self):
        self.seed_winners()
        price(self.db, DOC_2017, "old", "v17", "2017-01-27", 1063)
        self.assertFalse(self.dirty())
        self.db.execute("""INSERT INTO official_source_review
          (document_id,source_locator,parser_version,record,reason)
          VALUES(%s,'old','v17','{}','native date ambiguous')""", (DOC_2017,))
        self.assertTrue(self.dirty())

    def test_insert_waits_for_refresh_row_lock_and_uses_committed_previous_date(self):
        self.seed_winners()
        price(self.db, DOC_2017, "2017 native p16", "v17", "2017-01-27", 1063)
        official_catalog.refresh_keys(self.db, [KEY])
        self.assertEqual(self.db.execute(
            "SELECT previous_observed_on FROM official_catalog_current WHERE quote_key=%s",
            (KEY,)).fetchone()[0], date(2019, 2, 15))
        started, finished = threading.Event(), threading.Event()
        errors = []
        def insert_while_locked():
            try:
                with psycopg.connect(self.dsn, autocommit=True) as other:
                    other.execute(f"SET search_path={self.schema},public")
                    other.execute("SET lock_timeout='5s'")
                    started.set()
                    price(other, DOC_2017, "2018 native p12", "v18", "2018-01-27", 1200)
            except Exception as error:
                errors.append(error)
            finally:
                finished.set()
        self.db.execute("BEGIN")
        thread = None
        try:
            self.db.execute("""INSERT INTO official_source_review
              (document_id,source_locator,parser_version,record,reason)
              VALUES(%s,'1.2!row 412,cols C:E','review','{}','2019 cell ambiguous')""",
                            (DOC_2019,))
            official_catalog.refresh_keys(self.db, [KEY])
            self.assertEqual(self.db.execute(
                "SELECT previous_observed_on FROM official_catalog_current WHERE quote_key=%s",
                (KEY,)).fetchone()[0], date(2017, 1, 27))
            thread = threading.Thread(target=insert_while_locked, daemon=True)
            thread.start()
            self.assertTrue(started.wait(2))
            self.assertFalse(finished.wait(0.15), "insert must wait for the catalog row lock")
            self.db.execute("COMMIT")
        finally:
            if self.db.info.transaction_status.name != "IDLE":
                self.db.execute("ROLLBACK")
            if thread:
                thread.join(6)
        self.assertFalse(errors, errors)
        self.assertTrue(finished.is_set())
        self.assertTrue(self.dirty(), "2018 is no longer older than committed 2017 previous winner")

    def test_priority_four_of_hundred_keeps_oldest_fifo_and_budget(self):
        keys = [f"{n:064x}" for n in range(1, 4001)]
        self.db.execute("""INSERT INTO official_catalog_current
          (quote_key,dirty,version,refreshed_at)
          SELECT lpad(to_hex(n),64,'0'),true,'',
             now()-interval '1 day'+n*interval '1 second'
          FROM generate_series(1,4000) AS n""")
        priorities = keys[-4:]
        before = time.monotonic()
        refreshed = official_catalog.refresh_dirty(self.db, limit=100,
                                                   priority_keys=priorities)
        elapsed = time.monotonic() - before
        self.assertEqual(refreshed, 100)
        clean = [row[0] for row in self.db.execute(
            "SELECT quote_key FROM official_catalog_current WHERE NOT dirty ORDER BY quote_key"
        ).fetchall()]
        self.assertEqual(clean, keys[:96] + priorities)
        self.assertLess(elapsed, 30, "private 4000-key bounded refresh timed out")
        # Clean priorities no longer occupy slots in the next 100-key cycle.
        self.assertEqual(official_catalog.refresh_dirty(self.db, limit=100,
                         priority_keys=priorities), 100)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_catalog_current WHERE NOT dirty"
        ).fetchone()[0], 200)
        with self.assertRaisesRegex(ValueError, "At most four"):
            official_catalog.refresh_dirty(self.db, priority_keys=keys[-5:])

    def test_priority_deadline_defers_ordinary_after_committed_exact_keys(self):
        keys = [f"{n:064x}" for n in (1, 2, 3)]
        self.db.execute("INSERT INTO official_catalog_current(quote_key) VALUES(%s),(%s),(%s)", keys)
        self.db.execute("UPDATE official_catalog_current SET refreshed_at=now() WHERE quote_key=%s", (keys[0],))
        deadline_token = worker.RUN_DEADLINE.set(150)
        try:
            with patch.object(official_catalog, "_clock", side_effect=[100, 200]):
                with self.assertRaises(WorkDeferred):
                    official_catalog.refresh_dirty(self.db, limit=3, priority_keys=[keys[2]])
        finally:
            worker.RUN_DEADLINE.reset(deadline_token)
        self.assertFalse(self.db.execute("SELECT dirty FROM official_catalog_current WHERE quote_key=%s",
                                         (keys[2],)).fetchone()[0])
        self.assertTrue(self.db.execute("SELECT dirty FROM official_catalog_current WHERE quote_key=%s",
                                        (keys[0],)).fetchone()[0])

    def test_four_thousand_older_transitions_vs_old_trigger_under_reader(self):
        document(self.db, DOC_2017, "four-thousand-older-native-rows")
        self.db.execute("""INSERT INTO official_catalog_current
          (quote_key,payload,dirty,version,refreshed_at,
           winner_observed_on,previous_observed_on)
          SELECT lpad(to_hex(n),64,'0'),
            jsonb_build_object('observed_on','2026-10-02','price',3775,
                               'previous_price',1400),
            false,'official-catalog-v1',now(),'2026-10-02','2019-02-15'
          FROM generate_series(1,4000) AS n""")
        bulk = """INSERT INTO official_price_quote
          (document_id,source_locator,parser_version,quote_key,product_id,
           product_name,category,publisher,series,basis,currency,unit,
           market,observed_on,price,details)
          SELECT %s,%s || n::text,%s,lpad(to_hex(n),64,'0'),
            'limon-tahiti','Limón Tahití','Frutas frescas','DANE · SIPSA',
            'dane-weekly','Precio mayorista semanal','COP','kg',
            'Medellín, Plaza Minorista "José María Villa"','2017-01-27',1063,'{}'
          FROM generate_series(1,4000) AS n"""
        stop, ready = threading.Event(), threading.Event()
        samples, errors = [], []
        phase = ["new"]
        def reader():
            try:
                with psycopg.connect(self.dsn, autocommit=True) as db:
                    db.execute(f"SET search_path={self.schema},public")
                    ready.set()
                    while not stop.is_set():
                        count = db.execute("SELECT count(*) FROM official_catalog_current WHERE dirty").fetchone()[0]
                        samples.append((phase[0], count))
                        stop.wait(0.01)
            except Exception as error:
                errors.append(error)
                ready.set()
        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(2))
        try:
            begun = time.monotonic()
            self.db.execute(bulk, (DOC_2017, "new-older-", "v1"))
            new_elapsed = time.monotonic() - begun
            self.assertEqual(self.db.execute("SELECT count(*) FROM official_catalog_current WHERE dirty").fetchone()[0], 0)
            # Replace only this disposable schema's trigger function with the
            # original migration007 body, preserving the actual row fixture.
            baseline = OLD.read_text()
            start = baseline.index("CREATE OR REPLACE FUNCTION dirty_official_quote_catalog()")
            end = baseline.index("END $$;", start) + len("END $$;")
            self.db.execute(baseline[start:end])
            phase[0] = "old"
            begun = time.monotonic()
            self.db.execute(bulk, (DOC_2017, "baseline-older-", "v2"))
            old_elapsed = time.monotonic() - begun
            self.assertEqual(self.db.execute("SELECT count(*) FROM official_catalog_current WHERE dirty").fetchone()[0], 4000)
            self.assertEqual(self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0], 8000)
        finally:
            stop.set()
            thread.join(3)
        self.assertFalse(errors, errors)
        self.assertTrue(samples, "independent reader observed the benchmark")
        self.assertTrue(all(count == 0 for label, count in samples if label == "new"))
        self.assertLess(new_elapsed, 30)
        self.assertLess(old_elapsed, 30)
        print(f"private 4000 older inserts with reader: guarded={new_elapsed:.3f}s "
              f"legacy={old_elapsed:.3f}s guarded_dirty=0 legacy_dirty=4000 "
              f"reader_samples={len(samples)}")


if __name__ == "__main__":
    unittest.main()

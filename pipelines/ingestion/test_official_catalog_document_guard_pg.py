"""Private PostgreSQL controls for source-wide older reparse invalidation."""

import hashlib
import json
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

from . import official_catalog, official_sources, worker


ROOT = Path(__file__).parent
KEY = "a" * 64
OLD, PRIOR, CURRENT = ("1" * 64, "2" * 64, "3" * 64)


class DocumentGuardPostgres(unittest.TestCase):
    def setUp(self):
        dsn = os.environ.get("AGRO_REFERENCE_TEST_DSN")
        if not dsn:
            raise RuntimeError("Explicit private PostgreSQL DSN required")
        self.dsn = dsn
        self.db = psycopg.connect(dsn, autocommit=True)
        if not str(self.db.info.host).startswith("/tmp/agro-"):
            self.db.close()
            raise RuntimeError("Only isolated private PostgreSQL is allowed")
        self.schema = "qa_doc_guard_" + uuid.uuid4().hex[:12]
        self.db.execute(f"CREATE SCHEMA {self.schema}")
        self.db.execute(f"SET search_path={self.schema},public")
        self.db.execute("SET statement_timeout='15s'")
        for table in ("source_document", "official_price_quote", "official_source_review",
                      "ingestion_asset", "ingestion_checkpoint"):
            self.db.execute(f"CREATE TABLE {table} (LIKE public.{table} INCLUDING ALL)")
        self.db.execute(re.sub(r"^GRANT .*;\n", "", (ROOT / "migrations/20260927_007_official_catalog.sql").read_text(), flags=re.MULTILINE))
        self.db.execute((ROOT / "migrations/20261004_054_official_catalog_previous_date.sql").read_text())
        self.db.execute((ROOT / "migrations/20261005_055_official_catalog_dirty_fifo.sql").read_text())
        self.db.execute((ROOT / "migrations/20261006_068_official_catalog_reviewed_older_guard.sql").read_text())
        self.deadline_token = worker.RUN_DEADLINE.set(None)

    def tearDown(self):
        worker.RUN_DEADLINE.reset(self.deadline_token)
        self.db.execute(f"DROP SCHEMA {self.schema} CASCADE")
        self.db.close()

    def doc(self, did):
        self.db.execute("""INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content)
          VALUES(%s,'retained native source','DANE',%s,'application/pdf','original','',%s)""",
          (did, f"https://example.invalid/{did}.pdf", b"retained native source"))

    def quote(self, did, locator, version, day, amount, key=KEY):
        self.db.execute("""INSERT INTO official_price_quote
          (document_id,source_locator,parser_version,quote_key,product_id,product_name,
           category,publisher,series,basis,currency,unit,market,observed_on,price,
           min_price,max_price,details)
          VALUES(%s,%s,%s,%s,'limon-tahiti','Limón Tahití','Frutas frescas',
          'DANE · SIPSA','dane-weekly','Precio mayorista semanal','COP','kg',
          'Medellín, Plaza Minorista',%s,%s,%s,%s,'{}')""",
          (did, locator, version, key, day, amount, amount, amount))

    def seed(self, old_day="2017-01-27", key=KEY):
        for did in (OLD, PRIOR, CURRENT):
            self.doc(did)
        self.quote(OLD, "PDF page 16,table 1,column 2,line 62", "old", old_day, 1063, key)
        self.quote(PRIOR, "prior", "current", "2019-02-15", 1400, key)
        self.quote(CURRENT, "current", "current", "2026-10-02", 3775, key)
        official_catalog.refresh_keys(self.db, [key])
        return self.db.execute("SELECT payload FROM official_catalog_current WHERE quote_key=%s", (key,)).fetchone()[0]

    def entry(self, key=KEY):
        return self.db.execute("""SELECT dirty,payload,winner_observed_on,
          previous_observed_on FROM official_catalog_current WHERE quote_key=%s""", (key,)).fetchone()

    def test_fully_validated_same_locator_old_reparse_stays_visible_and_retained(self):
        identity = {"product_id": "limon-tahiti", "series": "dane-weekly",
          "market": "Medellín, Plaza Minorista", "currency": "COP", "unit": "kg",
          "basis": "Precio mayorista semanal", "dimensions": {}}
        key = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        payload = self.seed(key=key)
        row = {"source_locator": "PDF page 16,table 1,column 2,line 62",
          "product_id": "limon-tahiti", "product_name": "Limón Tahití",
          "category": "Frutas frescas", "publisher": "DANE · SIPSA",
          "series": "dane-weekly", "basis": "Precio mayorista semanal",
          "currency": "COP", "unit": "kg", "market": "Medellín, Plaza Minorista",
          "date": "2017-01-27", "price": 1063, "min": 1063, "max": 1063,
          "details": {}}
        count = official_sources.publish_rows(self.db, [row], OLD, "dane-weekly-xlsx",
                                             source_url=f"https://example.invalid/{OLD}.pdf")
        self.assertEqual(count, 1)
        dirty, after, winner, previous = self.entry(key)
        self.assertFalse(dirty)
        self.assertEqual(after, payload)
        self.assertEqual((winner, previous), (date(2026, 10, 2), date(2019, 2, 15)))
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (OLD,)).fetchone()[0], 2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s", (OLD,)).fetchone()[0], 0)
        self.assertTrue(self.db.execute("SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s AND step='official:complete'", (OLD,)).fetchone())

    def test_equal_previous_and_missing_prior_fail_closed(self):
        self.seed(old_day="2019-02-15")
        official_catalog.mark_document_dirty(self.db, OLD, "revision-equal", older_only=True)
        self.assertTrue(self.entry()[0])
        official_catalog.refresh_keys(self.db, [KEY])
        self.db.execute("UPDATE official_catalog_current SET previous_observed_on=NULL WHERE quote_key=%s", (KEY,))
        official_catalog.mark_document_dirty(self.db, OLD, "revision-null", older_only=True)
        self.assertTrue(self.entry()[0])

    def test_review_or_direct_caller_never_uses_older_guard(self):
        self.seed()
        official_catalog.mark_document_dirty(self.db, OLD, "review-revision", older_only=False)
        self.assertTrue(self.entry()[0])
        official_catalog.refresh_keys(self.db, [KEY])
        official_catalog.mark_document_dirty(self.db, OLD)
        self.assertTrue(self.entry()[0])

    def test_new_source_quote_that_can_affect_prior_is_dirtied_by_trigger(self):
        self.seed()
        official_catalog.mark_document_dirty(self.db, OLD, "new-source", older_only=True)
        self.assertFalse(self.entry()[0])
        self.quote(OLD, "new previous", "new-source", "2020-02-15", 1900)
        self.assertTrue(self.entry()[0])
        official_catalog.refresh_document(self.db, OLD, "new-source", older_only=True)
        dirty, payload, winner, previous = self.entry()
        self.assertFalse(dirty)
        self.assertEqual((winner, previous), (date(2026, 10, 2), date(2020, 2, 15)))
        self.assertEqual(payload["previous_price"], 1900)

    def test_old_identity_that_can_affect_current_is_dirty_before_replacement(self):
        self.seed(old_day="2026-10-02")
        official_catalog.mark_document_dirty(self.db, OLD, "identity-reassignment", older_only=True)
        self.assertTrue(self.entry()[0], "old source identity must be withheld before the first revised quote batch")
        new_key = "b" * 64
        self.quote(OLD, "PDF page 16,table 1,column 2,line 62", "identity-reassignment",
                   "2026-10-02", 1063, new_key)
        self.assertTrue(self.entry(new_key)[0], "insert trigger must independently invalidate new identity")
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (OLD,)).fetchone()[0], 2)

    def test_new_phase_marker_and_retry_preserve_clean_safe_key(self):
        payload = self.seed()
        official_catalog.mark_document_dirty(self.db, OLD, "safe-revision", older_only=True)
        self.assertEqual(official_catalog.refresh_document(self.db, OLD, "safe-revision", older_only=True), 0)
        self.assertFalse(self.entry()[0])
        self.assertEqual(self.entry()[1], payload)
        marker = self.db.execute("""SELECT step,records FROM ingestion_checkpoint
          WHERE document_id=%s AND processor_version='safe-revision'
          AND step LIKE 'official:catalog-start:%%'""", (OLD,)).fetchone()
        self.assertEqual(marker[1], 1)
        self.assertEqual(official_catalog.refresh_document(self.db, OLD, "safe-revision", older_only=True), 0)
        self.assertEqual(self.entry()[1], payload)

    def test_review_trigger_keeps_strictly_older_source_current_clean(self):
        self.seed()
        official_catalog.mark_document_dirty(self.db, OLD, "old-source", older_only=True)
        self.assertFalse(self.entry()[0])
        self.db.execute("""INSERT INTO official_source_review
          (document_id,source_locator,parser_version,record,reason)
          VALUES(%s,'PDF page 16,table 1,column 2,line 62','review','{}',
                 'Native cell withheld')""", (OLD,))
        self.assertFalse(self.entry()[0])

    def test_validated_review_publication_keeps_strictly_older_key_clean(self):
        self.seed()
        review = {"source_locator": "PDF page 16,table 1,column 2,line 62",
                  "price": None, "details": {"quality_issue": "Native cell withheld"}}
        original_refresh = official_catalog.refresh_document
        observed = []
        def refresh_after_review(db, did, revision, *, older_only=False):
            observed.append((self.entry()[0], older_only))
            return original_refresh(db, did, revision, older_only=older_only)
        with patch.object(official_catalog, "refresh_document", side_effect=refresh_after_review):
            self.assertEqual(official_sources.publish_rows(self.db, [review], OLD,
                             "dane-weekly-xlsx", source_url=f"https://example.invalid/{OLD}.pdf"), 0)
        self.assertEqual(observed, [(False, True)])
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s", (OLD,)).fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (OLD,)).fetchone()[0], 1)

    def test_interrupted_mixed_source_retains_safe_key_and_resumes_risky_key(self):
        safe_payload = self.seed()
        risky = "b" * 64
        self.quote(OLD, "second source", "old", "2019-02-15", 1401, risky)
        self.quote(PRIOR, "prior b", "prior", "2019-02-15", 1400, risky)
        self.quote(CURRENT, "current b", "current", "2026-10-02", 3775, risky)
        official_catalog.refresh_keys(self.db, [risky])
        official_catalog.mark_document_dirty(self.db, OLD, "mixed-revision", older_only=True)
        self.assertFalse(self.entry()[0])
        self.assertTrue(self.entry(risky)[0])
        token = worker.RUN_DEADLINE.set(time.monotonic() - 1)
        try:
            with self.assertRaisesRegex(Exception, "Official catalog refresh deferred"):
                official_catalog.refresh_document(self.db, OLD, "mixed-revision", older_only=True)
        finally:
            worker.RUN_DEADLINE.reset(token)
        self.assertFalse(self.entry()[0])
        self.assertEqual(self.entry()[1], safe_payload)
        self.assertTrue(self.entry(risky)[0])
        self.assertTrue(self.db.execute("SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s AND processor_version='mixed-revision' AND step LIKE 'official:catalog-start:%%'", (OLD,)).fetchone())
        self.assertEqual(official_catalog.refresh_document(self.db, OLD, "mixed-revision", older_only=True), 1)
        self.assertFalse(self.entry()[0])
        self.assertFalse(self.entry(risky)[0])

    def test_guard_reads_cache_state_after_concurrent_row_lock(self):
        self.seed()
        second = psycopg.connect(self.dsn, autocommit=True)
        self.addCleanup(second.close)
        second.execute(f"SET search_path={self.schema},public")
        errors = []
        elapsed = []
        def guarded_mark():
            try:
                begun = time.monotonic()
                official_catalog.mark_document_dirty(second, OLD, "locked-revision", older_only=True)
                elapsed.append(time.monotonic() - begun)
            except Exception as exc:
                errors.append(exc)
        with self.db.transaction():
            self.db.execute("UPDATE official_catalog_current SET refreshed_at=refreshed_at-interval '1 day' WHERE quote_key=%s", (KEY,))
            thread = threading.Thread(target=guarded_mark)
            thread.start()
            time.sleep(0.15)
            self.assertTrue(thread.is_alive(), "guard should wait on the cache row lock")
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertGreaterEqual(elapsed[0], 0.1)
        self.assertTrue(self.entry()[0], "post-lock stale cache must fail closed")

    def test_stale_day_and_version_fail_closed(self):
        self.seed()
        self.db.execute("UPDATE official_catalog_current SET refreshed_at=refreshed_at-interval '1 day' WHERE quote_key=%s", (KEY,))
        official_catalog.mark_document_dirty(self.db, OLD, "stale-day", older_only=True)
        self.assertTrue(self.entry()[0])
        official_catalog.refresh_keys(self.db, [KEY])
        self.db.execute("UPDATE official_catalog_current SET version='previous' WHERE quote_key=%s", (KEY,))
        official_catalog.mark_document_dirty(self.db, OLD, "stale-version", older_only=True)
        self.assertTrue(self.entry()[0])


if __name__ == "__main__":
    unittest.main()

"""Private PostgreSQL controls for exact-source catalog repair priority."""

import os
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg

from . import catalog_repair_priority, official_catalog, worker
from .resumable_inputs import WorkDeferred


URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_01abr_al_05abr_2023.pdf"
KIND = worker.URL_SOURCE_REPAIR_VERSIONS[URL][0]
DOC = "a" * 64
EQUAL_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana4_junio_2012.pdf"


def _dsn():
    value = os.environ.get("AGRO_REFERENCE_TEST_DSN")
    if not value:
        raise RuntimeError("AGRO_REFERENCE_TEST_DSN private socket is required")
    return value


class CatalogRepairPriorityPostgres(unittest.TestCase):
    def setUp(self):
        self.db = psycopg.connect(_dsn(), autocommit=True)
        if not str(self.db.info.host).startswith("/tmp/agro-"):
            self.db.close()
            raise RuntimeError("Only isolated private PostgreSQL is allowed")
        self.schema = "qa_priority_" + uuid.uuid4().hex[:12]
        self.db.execute(f"CREATE SCHEMA {self.schema}")
        self.db.execute(f"SET search_path={self.schema},public")
        for table in ("source_document", "ingestion_asset", "ingestion_checkpoint",
                      "official_price_quote", "official_catalog_current"):
            self.db.execute(f"CREATE TABLE {table} (LIKE public.{table} INCLUDING ALL)")
        self.db.execute((Path(__file__).parent / "migrations/20261005_055_official_catalog_dirty_fifo.sql").read_text())
        self.asset_version = worker.asset_parser_version(KIND, URL)
        self.quote_version = worker.parser_version(KIND, URL)

    def tearDown(self):
        self.db.execute(f"DROP SCHEMA {self.schema} CASCADE")
        self.db.close()

    def document(self, did=DOC, url=URL):
        self.db.execute("""INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content)
          VALUES(%s,'source','DANE',%s,'application/pdf','original','',%s)
          ON CONFLICT DO NOTHING""", (did, url, b"source"))

    def asset(self, *, did=DOC, url=URL, kind=KIND, status="complete", version=None):
        self.db.execute("""INSERT INTO ingestion_asset
          (url,kind,status,document_id,processor_version)
          VALUES(%s,%s,%s,%s,%s) ON CONFLICT(url) DO UPDATE
          SET kind=excluded.kind,status=excluded.status,
              document_id=excluded.document_id,processor_version=excluded.processor_version""",
          (url, kind, status, did, self.asset_version if version is None else version))

    def checkpoint(self, did=DOC, version=None):
        self.db.execute("""INSERT INTO ingestion_checkpoint
          (document_id,processor_version,step,records)
          VALUES(%s,%s,'official:complete',1) ON CONFLICT DO NOTHING""",
          (did, self.quote_version if version is None else version))

    def quote(self, locator, version, key, parsed_at, *, did=DOC):
        self.db.execute("""INSERT INTO official_price_quote
          (document_id,source_locator,parser_version,quote_key,product_id,
           product_name,category,publisher,series,basis,currency,unit,market,
           observed_on,price,details,parsed_at)
          VALUES(%s,%s,%s,%s,'limon','Limón Tahití','Frutas frescas',
            'DANE','dane-weekly','Precio mayorista semanal','COP','kg',
            'Manizales','2017-01-27',838,'{}',%s)""",
          (did, locator, version, key, parsed_at))

    def catalog(self, key, refreshed="2026-10-04 00:00:00+00"):
        self.db.execute("""INSERT INTO official_catalog_current
          (quote_key,dirty,version,refreshed_at) VALUES(%s,true,%s,%s)
          ON CONFLICT(quote_key) DO UPDATE SET dirty=true""",
          (key, official_catalog.VERSION, refreshed))

    def priority(self, *, deadline=None):
        return catalog_repair_priority.changed_identity_priority(
            self.db, {URL: (KIND, ":repair")}, worker.asset_parser_version,
            worker.parser_version, catalog_version=official_catalog.VERSION,
            deadline=deadline,
        )

    def seed_changed(self, n=1):
        self.document()
        self.asset()
        self.checkpoint()
        for index in range(n):
            locator = f"PDF page 16,row {index}"
            old, new = f"{index+1000:064x}", f"{index+2000:064x}"
            self.quote(locator, "old-revision", old, "2026-10-01 00:00:00+00")
            self.quote(locator, self.quote_version, new, "2026-10-02 00:00:00+00")
            self.catalog(new, f"2026-10-03 00:00:{index:02d}+00")
        return tuple(f"{index+2000:064x}" for index in range(n))

    def test_exact_completed_pointer_and_revision_guards(self):
        self.assertNotEqual(self.asset_version, self.quote_version,
                            "asset URL repair version and official quote revision are separate gates")
        key, = self.seed_changed()
        self.assertEqual(self.priority(), (key,))
        for sql, values in (
            ("UPDATE ingestion_asset SET status='failed'", ()),
            ("UPDATE ingestion_asset SET processor_version='old'", ()),
            ("UPDATE ingestion_asset SET kind='daily-pdf'", ()),
            ("UPDATE ingestion_asset SET document_id=%s", ("b" * 64,)),
            ("DELETE FROM ingestion_checkpoint", ()),
        ):
            with self.subTest(sql=sql):
                self.db.execute(sql, values)
                self.assertEqual(self.priority(), ())
                self.db.execute("UPDATE ingestion_asset SET status='complete',kind=%s,document_id=%s,processor_version=%s",
                                (KIND, DOC, self.asset_version))
                self.checkpoint()
        self.db.execute("UPDATE source_document SET source_url='https://example.invalid/other.pdf'")
        self.assertEqual(self.priority(), ())
        self.db.execute("UPDATE source_document SET source_url=%s", (URL,))
        self.db.execute("DELETE FROM ingestion_checkpoint")
        self.checkpoint(version="obsolete-publication")
        self.assertEqual(self.priority(), (), "an old completion cannot certify this publication")

    def test_equal_asset_and_quote_version_still_require_both_independent_gates(self):
        kind = worker.URL_SOURCE_REPAIR_VERSIONS[EQUAL_URL][0]
        asset_version = worker.asset_parser_version(kind, EQUAL_URL)
        quote_version = worker.parser_version(kind, EQUAL_URL)
        self.assertEqual(asset_version, quote_version)
        self.document(url=EQUAL_URL)
        self.asset(url=EQUAL_URL, kind=kind, version=asset_version)
        self.checkpoint(version=quote_version)
        old_key, new_key = "7" * 64, "8" * 64
        self.quote("PDF page 16,row 1", "old", old_key, "2026-10-01 00:00:00+00")
        self.quote("PDF page 16,row 1", quote_version, new_key, "2026-10-02 00:00:00+00")
        self.catalog(new_key)
        def candidates():
            return catalog_repair_priority.changed_identity_priority(
                self.db, {EQUAL_URL: (kind, ":repair")}, worker.asset_parser_version,
                worker.parser_version, catalog_version=official_catalog.VERSION,
            )
        self.assertEqual(candidates(), (new_key,))
        self.db.execute("UPDATE ingestion_asset SET processor_version='old'")
        self.assertEqual(candidates(), ())
        self.db.execute("UPDATE ingestion_asset SET processor_version=%s", (asset_version,))
        self.db.execute("DELETE FROM ingestion_checkpoint")
        self.assertEqual(candidates(), ())

    def test_other_document_and_incomplete_current_quote_never_promoted(self):
        self.document()
        self.asset()
        self.checkpoint()
        other = "b" * 64
        self.document(other, "https://example.invalid/other.pdf")
        key = "9" * 64
        self.quote("same locator", "old", "8" * 64, "2026-10-01 00:00:00+00")
        self.quote("same locator", self.quote_version, key,
                   "2026-10-02 00:00:00+00", did=other)
        self.catalog(key)
        self.assertEqual(self.priority(), (), "a different immutable original is not a revision")
        self.quote("same locator", "unfinished-parser", key,
                   "2026-10-03 00:00:00+00")
        self.assertEqual(self.priority(), (), "a newer uncompleted parse supersedes the current row")

    def test_unchanged_identity_and_raw_rows_retained(self):
        key, = self.seed_changed()
        self.quote("same-key", "old", key, "2026-10-01 00:00:00+00")
        self.quote("same-key", self.quote_version, key, "2026-10-02 00:00:00+00")
        before = self.db.execute("""SELECT document_id,source_locator,parser_version,
          quote_key,product_name,market,observed_on,price,min_price,max_price,details
          FROM official_price_quote ORDER BY source_locator,parser_version""").fetchall()
        self.assertEqual(self.priority(), (key,))
        self.db.execute("UPDATE official_catalog_current SET dirty=false WHERE quote_key=%s", (key,))
        self.assertEqual(self.priority(), ())
        after = self.db.execute("""SELECT document_id,source_locator,parser_version,
          quote_key,product_name,market,observed_on,price,min_price,max_price,details
          FROM official_price_quote ORDER BY source_locator,parser_version""").fetchall()
        self.assertEqual(after, before, "priority reads must preserve every raw quote field")

    def test_later_old_file_repair_rediscovered_and_four_plus_fifo(self):
        keys = self.seed_changed(5)
        self.assertEqual(self.priority(), keys[:4])
        self.db.execute("UPDATE official_catalog_current SET dirty=false WHERE quote_key=%s", (keys[0],))
        self.assertEqual(self.priority(), keys[1:5])
        # A later old-file correction dirties an identity again; no one-shot
        # completion marker suppresses the source-backed changed key. Its new
        # dirty transition goes after the four identities already waiting.
        self.db.execute("UPDATE official_catalog_current SET dirty=true WHERE quote_key=%s", (keys[0],))
        self.assertEqual(self.priority(), keys[1:5])
        for n in range(96):
            self.catalog(f"{10000+n:064x}", "2026-10-02 00:00:00+00")
        batches = []
        with patch.object(official_catalog, "refresh_keys", side_effect=lambda _db, ks: batches.append(tuple(ks)) or len(ks)):
            count = official_catalog.refresh_dirty(self.db, limit=100, priority_keys=self.priority())
        self.assertEqual(count, 100)
        self.assertEqual(batches[0], keys[1:5])
        self.assertEqual(len(batches[1]), 96)
        self.assertIn(keys[0], batches[1])

    def test_deadline_and_sql_failure_are_explicit(self):
        self.seed_changed()
        with self.assertRaises(WorkDeferred):
            self.priority(deadline=time.monotonic() - 1)
        self.db.execute("ALTER TABLE ingestion_checkpoint RENAME COLUMN processor_version TO previous_processor_version")
        with self.assertRaises(psycopg.Error):
            self.priority()

    def test_equal_timestamp_different_key_does_not_forge_previous(self):
        self.document()
        self.asset()
        self.checkpoint()
        old, new = "1" * 64, "2" * 64
        self.quote("loc", "same-time", old, "2026-10-02 00:00:00+00")
        self.quote("loc", self.quote_version, new, "2026-10-02 00:00:00+00")
        self.catalog(new)
        self.assertEqual(self.priority(), (), "a changed key at the same timestamp is not a prior revision")

    def test_old_difference_persists_across_matching_intermediate(self):
        self.document()
        self.asset()
        self.checkpoint()
        old, new = "3" * 64, "4" * 64
        self.quote("loc", "old", old, "2026-10-01 00:00:00+00")
        self.quote("loc", "middle", new, "2026-10-02 00:00:00+00")
        self.quote("loc", self.quote_version, new, "2026-10-03 00:00:00+00")
        self.catalog(new)
        self.assertEqual(self.priority(), (new,), "any strictly older different key still qualifies")

    def test_newer_uncompleted_version_blocks_a_dirty_key(self):
        key, = self.seed_changed()
        self.quote("PDF page 16,row 0", "uncompleted", key, "2026-10-04 00:00:00+00")
        self.assertEqual(self.priority(), (), "a newer parse cannot be bypassed by the coarse prefilter")

    def test_same_key_only_and_cross_document_are_inert(self):
        self.document()
        self.asset()
        self.checkpoint()
        key = "5" * 64
        self.quote("loc", "old", key, "2026-10-01 00:00:00+00")
        self.quote("loc", self.quote_version, key, "2026-10-02 00:00:00+00")
        self.catalog(key)
        other = "b" * 64
        self.document(other, "https://example.invalid/other.pdf")
        self.quote("loc", "other-doc", "6" * 64, "2026-09-01 00:00:00+00", did=other)
        self.assertEqual(self.priority(), (), "only changes at one exact original and locator count")

    def test_bad_asset_or_checkpoint_does_not_bypass_source_guard(self):
        self.seed_changed()
        self.db.execute("UPDATE ingestion_asset SET processor_version='obsolete'")
        self.assertEqual(self.priority(), ())
        self.db.execute("UPDATE ingestion_asset SET processor_version=%s", (self.asset_version,))
        self.db.execute("DELETE FROM ingestion_checkpoint")
        self.assertEqual(self.priority(), ())


if __name__ == "__main__":
    unittest.main()

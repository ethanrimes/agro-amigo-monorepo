"""Owned full-schema, real-worker test for native daily prose candidates.

Run only against a fresh, dedicated Unix PostgreSQL database with all current
schema/migrations. No DANE, OCR provider, Blob, production DB or timers.
"""

import hashlib
import os
import re
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import queue_plan, worker
from .daily_prose import review_unbound_daily_prose
from .daily_prose_generic import (
    OLD_UNBOUND_ASSET_VERSION, VERSION, parse_generic, retained_unbound_original,
)


URLS = (
    ("2026-10-01", "89f1bd8d6c27f92daeacdea07914ad8f5f93cf85886ea97082fcdee2d699b8c7"),
    ("2026-10-02", "e176e5f6134d19a2797f364e4d2bd472981ec5ba91b7f3e828839313cad79f37"),
    ("2026-10-05", "c220e350191e8fc30199cd3994b5c093bc0716d7df498edf17953e7224d1e543"),
    ("2026-10-06", "60087dcd12480c65a3901075e3ae8fd36bbbfd922b419f497d9ff8d22858b51f"),
    ("2026-10-07", "fb0c840f6ea8c38d8fe810ae88ff2bbaf97c713a1ad4d3b2fc69500aca32feb9"),
)
FIXTURES = Path(__file__).parent / "testdata/daily_prose_generic"


def url_for(day):
    parsed = date.fromisoformat(day)
    months = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
    return ("https://www.dane.gov.co/files/operaciones/SIPSA/"
            f"bol-SIPSADiario-{parsed.day:02d}{months[parsed.month-1]}{parsed.year}.pdf")


@unittest.skipUnless(os.environ.get("AGRO_DAILY_PROSE_GENERIC_TEST_DSN"),
                     "Fresh owned full-schema daily-prose PostgreSQL required")
class DailyProseGenericWorkerPG(unittest.TestCase):
    def test_five_reviewed_originals_atomic_replay_and_source_retention(self):
        db = psycopg.connect(os.environ["AGRO_DAILY_PROSE_GENERIC_TEST_DSN"], autocommit=True)
        self.addCleanup(db.close)
        if (not db.info.host.startswith("/tmp/agro-daily-prose-")
                or not db.info.dbname.startswith("agro_daily_prose_generic_")
                or db.execute("SELECT inet_server_addr()").fetchone()[0] is not None):
            raise RuntimeError("Daily prose test requires its owned local Unix database")
        self.assertEqual(db.execute("SELECT count(*) FROM source_document").fetchone()[0], 0)
        # The disposable bootstrap creates roles without the Function App's
        # configured worker ACL. Mirror only rights used by this publisher;
        # a separate live read-only ACL check remains required before release.
        db.execute("GRANT SELECT,INSERT ON source_document,historical_price,"
                   "official_source_review,ingestion_checkpoint TO agro_ingestor")
        db.execute("GRANT SELECT,INSERT,UPDATE ON ingestion_asset,daily_price "
                   "TO agro_ingestor")
        db.execute("GRANT SELECT,INSERT,UPDATE ON document_alias TO agro_ingestor")
        db.execute("GRANT SELECT,INSERT ON source_pdf_page TO agro_ingestor")
        db.execute("GRANT SELECT,INSERT ON source_ocr_scan TO agro_ingestor")
        db.execute("GRANT SELECT,INSERT,UPDATE ON source_ocr_task TO agro_ingestor")
        db.execute("GRANT SELECT ON official_price_quote TO agro_ingestor")
        db.execute("GRANT SELECT,UPDATE ON official_catalog_current TO agro_ingestor")
        db.execute("GRANT SELECT,INSERT ON retained_record TO agro_ingestor")
        db.execute("GRANT SELECT,INSERT ON product TO agro_ingestor")
        db.execute("GRANT SELECT ON published_historical_price TO agro_ingestor")
        expected = {}
        old_reviews = {}
        source_xmins = {}
        for day, did in URLS:
            url = url_for(day)
            body = (FIXTURES / (did + ".pdf")).read_bytes()
            self.assertEqual(hashlib.sha256(body).hexdigest(), did)
            parsed = date.fromisoformat(day)
            proposed, remaining = parse_generic(body, url, did, parsed)
            expected[did] = (url, body, parsed, proposed, remaining)
            prior = review_unbound_daily_prose(body, url, did, parsed)
            old_reviews[did] = prior
            db.execute("""INSERT INTO source_document
              (id,title,publisher,source_url,media_type,kind,reference_period,
               page_count,content,metadata)
              VALUES(%s,%s,'DANE',%s,'application/pdf','original',%s,
                     %s,%s,%s)""",
              (did, "DANE - " + url.rsplit("/", 1)[-1], url, day,
               {"2026-10-01": 6, "2026-10-02": 6, "2026-10-05": 6,
                "2026-10-06": 6, "2026-10-07": 6}[day], body,
               Jsonb({"ingestion_kind": "daily-pdf", "retention": "permanent",
                      "original_filename": url.rsplit("/", 1)[-1]})))
            db.execute("""INSERT INTO ingestion_asset
              (url,kind,observed_on,status,document_id,records,processor_version,
               checked_at,error)
              VALUES(%s,'daily-pdf',%s,'review',%s,0,%s,now()-interval '7 hours',%s)""",
              (url, parsed, did, OLD_UNBOUND_ASSET_VERSION,
               f"Native prose requires review for {len(prior)} monetary spans"))
            for locator, record, reason in prior:
                db.execute("""INSERT INTO official_source_review
                  (document_id,source_locator,parser_version,record,reason)
                  VALUES(%s,%s,'daily-pdf-prose-v1',%s,%s)""",
                  (did, locator, Jsonb(record), reason))
            source_xmins[did] = db.execute(
                "SELECT xmin::text FROM source_document WHERE id=%s", (did,)).fetchone()[0]
        db.execute("SET ROLE agro_ingestor")
        self.addCleanup(lambda: db.execute("RESET ROLE"))
        self.assertEqual(db.execute("SELECT current_user").fetchone()[0], "agro_ingestor")
        self.assertEqual(
            queue_plan.expected_versions().obj["daily-pdf-generic"],
            worker.asset_parser_version("daily-pdf", url_for(URLS[0][0])),
        )
        self.assertEqual(worker.asset_parser_version("daily-pdf", url_for(URLS[0][0])),
                         OLD_UNBOUND_ASSET_VERSION + ":" + VERSION)
        audited = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-21ago2026.pdf"
        self.assertTrue(worker.asset_parser_version("daily-pdf", audited).endswith(
            ":daily-prose-two-originals-v1"))
        first_did = URLS[0][1]
        first_url, first_body, first_day, first_rows, first_remaining = expected[first_did]
        self.assertIn((first_url, "daily-pdf", first_day),
                      queue_plan.backfill_candidates(db, 1000))
        self.assertIn((first_url, "daily-pdf", first_day),
                      queue_plan.daily_candidates(db, date(2026, 10, 7)))
        self.assertTrue(worker.retained_reparse_during_host_cooldown(db, first_url, "daily-pdf"))
        self.assertEqual(retained_unbound_original(
            db, first_url, "daily-pdf", OLD_UNBOUND_ASSET_VERSION + ":" + VERSION), first_body)
        self.assertIsNone(retained_unbound_original(
            db, first_url, "daily-pdf", OLD_UNBOUND_ASSET_VERSION))
        self.assertIsNone(retained_unbound_original(
            db, first_url, "city-pdf", OLD_UNBOUND_ASSET_VERSION + ":" + VERSION))
        self.assertIsNone(retained_unbound_original(
            db, first_url.replace("01oct", "08oct"), "daily-pdf",
            OLD_UNBOUND_ASSET_VERSION + ":" + VERSION))
        with self.assertRaisesRegex(RuntimeError, "rollback status fixture"):
            with db.transaction():
                db.execute("UPDATE ingestion_asset SET status='pending' WHERE url=%s", (first_url,))
                self.assertIsNone(retained_unbound_original(
                    db, first_url, "daily-pdf", OLD_UNBOUND_ASSET_VERSION + ":" + VERSION))
                raise RuntimeError("rollback status fixture")
        # An existing product ID with a different full caption must never
        # absorb a new source-literal variety or partially publish the PDF.
        with self.assertRaisesRegex(RuntimeError, "rollback collision fixture"):
            with db.transaction():
                db.execute("INSERT INTO product(id,name,category) VALUES"
                           "('guayaba','Guayaba pera','Productos agrícolas')")
                with patch.object(worker, "fetch_asset", side_effect=AssertionError("HTTP forbidden")), \
                     patch.object(worker, "_get", side_effect=AssertionError("HTTP forbidden")):
                    with self.assertRaisesRegex(ValueError, "already names another product"):
                        worker.process_asset(db, first_url, "daily-pdf", first_day)
                self.assertEqual(db.execute("SELECT count(*) FROM historical_price WHERE document_id=%s",
                                            (first_did,)).fetchone()[0], 0)
                raise RuntimeError("rollback collision fixture")
        self.assertEqual(db.execute("SELECT count(*) FROM product WHERE id='guayaba'").fetchone()[0], 0)
        with patch.object(worker, "fetch_asset", side_effect=AssertionError("HTTP forbidden")), \
             patch.object(worker, "_get", side_effect=AssertionError("HTTP forbidden")), \
             patch.object(worker, "project", side_effect=RuntimeError("injected before projection")):
            with self.assertRaisesRegex(RuntimeError, "injected before projection"):
                worker.process_asset(db, first_url, "daily-pdf", first_day)
        self.assertEqual(db.execute("SELECT count(*) FROM historical_price WHERE document_id=%s",
                                    (first_did,)).fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT count(*) FROM daily_price WHERE document_id=%s",
                                    (first_did,)).fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT status,records,processor_version FROM ingestion_asset WHERE url=%s",
                                    (first_url,)).fetchone(),
                         ("review", 0, OLD_UNBOUND_ASSET_VERSION))
        self.assertEqual(db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s",
                                    (first_did,)).fetchone()[0], len(old_reviews[first_did]))
        with patch.object(worker, "fetch_asset", side_effect=AssertionError("HTTP forbidden")), \
             patch.object(worker, "_get", side_effect=AssertionError("HTTP forbidden")):
            for did, (url, body, day, rows, remaining) in expected.items():
                self.assertEqual(worker.process_asset(db, url, "daily-pdf", day), len(rows))
        self.assertEqual(db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 72)
        self.assertEqual(db.execute("SELECT count(*) FROM daily_price").fetchone()[0], 72)
        self.assertEqual(db.execute("SELECT count(*) FROM daily_price WHERE product_id IS NULL").fetchone()[0], 0)
        self.assertTrue(all((url, "daily-pdf", day) not in
                            queue_plan.backfill_candidates(db, 1000)
                            for did, (url, _body, day, _rows, _review) in expected.items()))
        self.assertTrue(all((url, "daily-pdf", day) not in
                            queue_plan.daily_candidates(db, date(2026, 10, 7))
                            for did, (url, _body, day, _rows, _review) in expected.items()))
        self.assertEqual(db.execute("SELECT count(*) FROM official_source_review").fetchone()[0], 168)
        for did, (url, body, day, rows, remaining) in expected.items():
            actual_raw = db.execute("""SELECT source_locator,series,observed_on,
              product_name,market_name,unit,price,change_percent,details
              FROM historical_price WHERE document_id=%s ORDER BY source_locator""",
              (did,)).fetchall()
            self.assertEqual(actual_raw, sorted(rows, key=lambda row: row[0]))
            self.assertEqual(db.execute("SELECT count(*) FROM daily_price WHERE document_id=%s",
                                        (did,)).fetchone()[0], len(rows))
            self.assertEqual(db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s",
                                        (did,)).fetchone()[0],
                             len(old_reviews[did]) + len(remaining))
            status = db.execute("SELECT status,records,error FROM ingestion_asset WHERE url=%s",
                                (url,)).fetchone()
            self.assertEqual(status[0:2], ("complete", len(rows)))
            self.assertIn(f"{len(remaining)} monetary spans", status[2])
            self.assertEqual(db.execute("SELECT xmin::text FROM source_document WHERE id=%s",
                                        (did,)).fetchone()[0], source_xmins[did])
        # A second same-body attempt may fetch the same *local fixture* but may
        # never replace immutable rows or the distinct unknown caption.
        before = db.execute("SELECT document_id,source_locator,xmin::text FROM historical_price ORDER BY 1,2").fetchall()
        with patch.object(worker, "fetch_asset", return_value=first_body), \
             patch.object(worker, "_get", side_effect=AssertionError("HTTP forbidden")):
            worker.process_asset(db, first_url, "daily-pdf", first_day)
        self.assertEqual(db.execute("SELECT document_id,source_locator,xmin::text FROM historical_price ORDER BY 1,2").fetchall(), before)
        self.assertEqual(db.execute("SELECT price FROM daily_price WHERE document_id=%s AND product_name='maracuyá'",
                                    (first_did,)).fetchone(), None)
        self.assertEqual(db.execute("SELECT price FROM daily_price WHERE document_id=%s AND product_name='Maracuyá'",
                                    (first_did,)).fetchone()[0], 4800)
        self.assertEqual(db.execute("SELECT count(*) FROM daily_price WHERE product_name='guayaba' AND product_id='guayaba'").fetchone()[0], 4)
        self.assertEqual(db.execute("SELECT name FROM product WHERE id='guayaba'").fetchone()[0], "guayaba")
        self.assertEqual(db.execute("SELECT count(*) FROM historical_price WHERE details->>'source_product_caption'='guayaba'").fetchone()[0], 4)

    def test_legacy_audited_sources_pending_firstload_and_retained_review_replay(self):
        from .test_daily_prose import SOURCES as LEGACY_SOURCES, source_case
        from .daily_prose import AUDITED, VERSION as LEGACY_VERSION, parse_exact_daily_prose

        db = psycopg.connect(os.environ["AGRO_DAILY_PROSE_GENERIC_TEST_DSN"], autocommit=True)
        self.addCleanup(db.close)
        if (not db.info.host.startswith("/tmp/agro-daily-prose-")
                or not db.info.dbname.startswith("agro_daily_prose_generic_")
                or db.execute("SELECT inet_server_addr()").fetchone()[0] is not None):
            raise RuntimeError("Legacy daily prose test requires its owned local full-schema DB")
        # Mirror only the source and projection rights used by process_asset.
        db.execute("GRANT SELECT,INSERT ON source_document,historical_price,official_source_review,ingestion_checkpoint TO agro_ingestor")
        db.execute("GRANT SELECT,INSERT,UPDATE ON ingestion_asset,daily_price,document_alias TO agro_ingestor")
        db.execute("GRANT SELECT,INSERT ON source_pdf_page,source_ocr_scan,product TO agro_ingestor")
        db.execute("GRANT SELECT,INSERT,UPDATE ON source_ocr_task TO agro_ingestor")
        db.execute("GRANT SELECT ON official_price_quote,published_historical_price TO agro_ingestor")
        db.execute("GRANT SELECT,UPDATE ON official_catalog_current TO agro_ingestor")
        db.execute("GRANT SELECT,INSERT ON retained_record TO agro_ingestor")
        ids = [AUDITED[url][0] for _, _, url in LEGACY_SOURCES]
        self.assertEqual(db.execute("SELECT count(*) FROM source_document WHERE id=ANY(%s)", (ids,)).fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT count(*) FROM ingestion_asset WHERE url=ANY(%s)",
                                    ([url for _, _, url in LEGACY_SOURCES],)).fetchone()[0], 0)

        class NoDatabase:
            def execute(self, *_args, **_kwargs):
                raise AssertionError("invalid source guard queried before rejecting")

        bad_body, bad_sha, bad_day = source_case(*LEGACY_SOURCES[0][::2])
        exact_rows, _ = parse_exact_daily_prose(bad_body, LEGACY_SOURCES[0][2], bad_sha, bad_day)
        unknown = list(exact_rows[0])
        unknown[-1] = dict(unknown[-1], parser_version="daily-pdf-prose-unknown-v9")
        with self.assertRaisesRegex(ValueError, "not source-bound"):
            worker.project(NoDatabase(), bad_sha, LEGACY_SOURCES[0][2],
                           "daily-pdf", source_rows=[tuple(unknown)])
        with self.assertRaisesRegex(ValueError, "exact URL, SHA, and day"):
            worker.project(NoDatabase(), "f" * 64, LEGACY_SOURCES[0][2],
                           "daily-pdf", source_rows=[exact_rows[0]])

        db.execute("SET ROLE agro_ingestor")
        self.addCleanup(lambda: db.execute("RESET ROLE"))
        total_rows = total_reviews = 0
        for filename, _oracle, url in LEGACY_SOURCES:
            body, sha, day = source_case(filename, url)
            rows, reviews = parse_exact_daily_prose(body, url, sha, day)
            total_rows += len(rows)
            total_reviews += len(reviews)
            old_asset_version = "daily-pdf-v6:supply-daily-pdf-summary-v1"
            db.execute("""INSERT INTO ingestion_asset
              (url,kind,observed_on,status,processor_version,records)
              VALUES(%s,'daily-pdf',%s,'pending',%s,0)""", (url, day, old_asset_version))
            initial = db.execute("SELECT document_id,status,processor_version,observed_on FROM ingestion_asset WHERE url=%s", (url,)).fetchone()
            self.assertEqual(initial, (None, "pending", old_asset_version, day))
            with patch.object(worker, "fetch_asset", return_value=body), \
                 patch.object(worker, "_get", side_effect=AssertionError("network forbidden")):
                self.assertEqual(worker.process_asset(db, url, "daily-pdf", day), len(rows))
            expected_version = worker.asset_parser_version("daily-pdf", url)
            asset = db.execute("SELECT document_id,status,records,processor_version,observed_on FROM ingestion_asset WHERE url=%s", (url,)).fetchone()
            self.assertEqual(asset, (sha, "complete", len(rows), expected_version, day))
            self.assertEqual(db.execute("""SELECT source_url,media_type,kind,metadata->>'ingestion_kind'
              FROM source_document WHERE id=%s""", (sha,)).fetchone(),
              (url, "application/pdf", "original", "daily-pdf"))
            counts = db.execute("""SELECT
              (SELECT count(*) FROM historical_price WHERE document_id=%s),
              (SELECT count(*) FROM daily_price WHERE document_id=%s),
              (SELECT count(*) FROM official_source_review WHERE document_id=%s)""",
                                (sha, sha, sha)).fetchone()
            self.assertEqual(counts, (len(rows), len(rows), len(reviews)))
            actual_raw = db.execute("""SELECT source_locator,series,observed_on,product_name,
              market_name,unit,price,change_percent,details FROM historical_price
              WHERE document_id=%s ORDER BY source_locator""", (sha,)).fetchall()
            expected_raw = sorted(rows, key=lambda row: row[0])
            self.assertEqual(len(actual_raw), len(expected_raw))
            for actual, expected in zip(actual_raw, expected_raw):
                self.assertEqual(actual[:6], expected[:6])
                self.assertEqual(float(actual[6]), float(expected[6]))
                self.assertEqual(None if actual[7] is None else float(actual[7]),
                                 None if expected[7] is None else float(expected[7]))
                self.assertEqual(actual[8], expected[8])
            raw_before = db.execute("SELECT source_locator,xmin::text FROM historical_price WHERE document_id=%s ORDER BY 1", (sha,)).fetchall()
            daily_before = db.execute("SELECT observed_on,product_name,market_name,price,document_id,xmin::text FROM daily_price WHERE document_id=%s ORDER BY 1,2,3", (sha,)).fetchall()
            review_before = db.execute("SELECT source_locator,parser_version,reason,xmin::text FROM official_source_review WHERE document_id=%s ORDER BY 1", (sha,)).fetchall()
            doc_xmin = db.execute("SELECT xmin::text FROM source_document WHERE id=%s", (sha,)).fetchone()[0]

            db.execute("UPDATE ingestion_asset SET status='review',records=0,processor_version=%s WHERE url=%s",
                       (old_asset_version, url))
            def retained_fetch(db_arg, requested_url, **_kwargs):
                self.assertEqual(requested_url, url)
                original = db_arg.execute("""SELECT d.content FROM ingestion_asset a
                  JOIN source_document d ON d.id=a.document_id
                  WHERE a.url=%s AND a.kind='daily-pdf' AND a.document_id=%s
                    AND a.observed_on=%s AND d.source_url=a.url AND d.kind='original'
                    AND d.media_type='application/pdf'
                    AND d.metadata->>'ingestion_kind'='daily-pdf'""", (url, sha, day)).fetchone()
                self.assertIsNotNone(original)
                self.assertEqual(bytes(original[0]), body)
                return bytes(original[0])
            with patch.object(worker, "fetch_asset", side_effect=retained_fetch), \
                 patch.object(worker, "_get", side_effect=AssertionError("network forbidden")):
                self.assertEqual(worker.process_asset(db, url, "daily-pdf", day), len(rows))
            replay_asset = db.execute("SELECT document_id,status,records,processor_version,observed_on FROM ingestion_asset WHERE url=%s", (url,)).fetchone()
            self.assertEqual(replay_asset, (sha, "complete", len(rows), expected_version, day))
            self.assertEqual(db.execute("SELECT source_locator,xmin::text FROM historical_price WHERE document_id=%s ORDER BY 1", (sha,)).fetchall(), raw_before)
            self.assertEqual(db.execute("SELECT observed_on,product_name,market_name,price,document_id,xmin::text FROM daily_price WHERE document_id=%s ORDER BY 1,2,3", (sha,)).fetchall(), daily_before)
            self.assertEqual(db.execute("SELECT source_locator,parser_version,reason,xmin::text FROM official_source_review WHERE document_id=%s ORDER BY 1", (sha,)).fetchall(), review_before)
            self.assertEqual(db.execute("SELECT xmin::text FROM source_document WHERE id=%s", (sha,)).fetchone()[0], doc_xmin)
        self.assertEqual((total_rows, total_reviews), (48, 2))
        self.assertEqual(db.execute("SELECT count(*) FROM historical_price WHERE document_id=ANY(%s)", (ids,)).fetchone()[0], 48)
        self.assertEqual(db.execute("SELECT count(*) FROM daily_price WHERE document_id=ANY(%s)", (ids,)).fetchone()[0], 48)
        self.assertEqual(db.execute("SELECT count(*) FROM official_source_review WHERE document_id=ANY(%s)", (ids,)).fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()

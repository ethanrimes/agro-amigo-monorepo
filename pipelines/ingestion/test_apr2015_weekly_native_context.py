"""Exact-source tests for the April 2015 native XLS review."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "testdata" / "weekly_native_context_review"
URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_13_17abr_2015.xls"
BODY_PATH = FIXTURES / "official-Anexo_13_17abr_2015.xls"
BODY = BODY_PATH.read_bytes()
DID = "e40c3580914f8dd1bac08e62483f2cf957ab999f3a103e392f2560082baa2553"
METADATA = {
    "retention": "permanent",
    "ingestion_kind": "dane-weekly-xlsx",
    "original_filename": "Anexo_13_17abr_2015.xls",
}
ROLE_INSTALLER = ROOT / "pipelines/ingestion/test_input_pdf_v17_role.py"

from pipelines.ingestion import reviewed_weekly_native_context as candidate
from pipelines.ingestion import dane_weekly, queue_plan, worker


class ExactApril2015CandidatePure(unittest.TestCase):
    def test_exact_body_is_reviewed_without_typing_prices_period_or_unit(self):
        self.assertEqual(hashlib.sha256(BODY).hexdigest(), DID)
        review = candidate.inspect_original(BODY, URL, DID)
        self.assertIsNotNone(review)
        self.assertIsNone(review["price"])
        details = review["details"]
        self.assertEqual(details["original_sha256"], DID)
        self.assertEqual(details["native_layout"], "compact-product-min-max-mean-short-trend")
        self.assertEqual(details["native_workbook_format"], "ole-biff")
        self.assertEqual(details["native_numeric_rows_untyped"], 4503)
        self.assertEqual(details["typed_price_rows"], 0)
        self.assertIsNone(details["source_period"])
        self.assertIsNone(details["literal_unit_heading"])
        self.assertNotIn("unit", review)
        self.assertNotIn("date", details)

    def test_changed_body_wrong_url_and_wrong_document_id_fail_closed(self):
        changed = BODY + b"changed"
        self.assertIsNone(candidate.inspect_original(changed, URL, hashlib.sha256(changed).hexdigest()))
        self.assertIsNone(candidate.inspect_original(BODY, URL + "?alternate=1", DID))
        with self.assertRaisesRegex(ValueError, "document identity changed"):
            candidate.inspect_original(BODY, URL, "0" * 64)

    def test_exact_url_is_in_worker_and_queue_revision_routes(self):
        version = worker.asset_parser_version("dane-weekly-xlsx", URL)
        self.assertTrue(version.endswith(candidate.VERSION_SUFFIX + ":dane-weekly-v24"))
        self.assertIn(URL, candidate.URLS)
        self.assertEqual(queue_plan.expected_versions().obj["url:" + URL], version)


@unittest.skipUnless(os.environ.get("AGRO_APR2015_NATIVE_CONTEXT_TEST_DSN"),
                     "dedicated fresh full-schema owned PostgreSQL required")
class ExactApril2015CandidateWorkerPG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn_value = os.environ["AGRO_APR2015_NATIVE_CONTEXT_TEST_DSN"]
        cls.db = psycopg.connect(dsn_value, autocommit=True)
        if (not str(cls.db.info.host).startswith("/tmp/agro-weekly-apr2015-integrated-socket-")
                or cls.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None
                or not cls.db.execute("SHOW server_version").fetchone()[0].startswith("16.")):
            cls.db.close()
            raise RuntimeError("candidate worker tests require the exact owned Unix-socket PostgreSQL 16")
        cls.db.execute("SET ROLE agro_ingestor")
        if cls.db.execute("SELECT current_user").fetchone()[0] != "agro_ingestor":
            cls.db.close()
            raise RuntimeError("candidate worker test role must be agro_ingestor")
        cls.db.execute("SET TIME ZONE 'UTC'; SET statement_timeout='90s'; SET lock_timeout='2s'")
        for table in ("source_document", "official_price_quote", "official_source_review",
                      "ingestion_checkpoint", "ingestion_asset", "source_ocr_task", "source_ocr_scan"):
            if cls.db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]:
                cls.db.close()
                raise RuntimeError("owned candidate full-schema database must start empty")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.db = self.__class__.db
        self.db.execute("BEGIN")
        self.db.execute("SET LOCAL statement_timeout='90s'; SET LOCAL lock_timeout='2s'")

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def seed_source(self, *, metadata=None, source_url=URL, body=BODY, did=DID):
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
            "reference_period,content,metadata) VALUES(%s,%s,'DANE · SIPSA',%s,'application/vnd.ms-excel',"
            "'original','Serie histórica completa',%s,%s)",
            (did, "Anexo_13_17abr_2015.xls", source_url, body,
             Jsonb(METADATA if metadata is None else metadata)),
        )
        return did

    def seed_asset(self, *, url=URL, did=DID):
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,observed_on,status,document_id,records,error,"
            "processor_version,checked_at) VALUES(%s,'dane-weekly-xlsx',DATE '2026-10-16',"
            "'failed',%s,0,'ValueError: unsupported compact native workbook',%s,now()-interval '1 day')",
            (url, did, worker.parser_version("dane-weekly-xlsx")),
        )

    def process_without_network_or_archive_writes(self, *, body=BODY, did=DID, url=URL):
        def retained_archive(_db, requested_url, requested_body, _kind, _day, **_kwargs):
            self.assertEqual(requested_url, url)
            self.assertEqual(hashlib.sha256(requested_body).hexdigest(), did)
            retained = self.db.execute(
                "SELECT id,source_url,content FROM source_document WHERE id=%s", (did,)
            ).fetchone()
            self.assertEqual(retained, (did, url, requested_body))
            return did

        with patch.object(worker, "fetch_asset", return_value=body), \
             patch.object(worker, "archive", side_effect=retained_archive), \
             patch("pipelines.ingestion.ocr.scan_document", side_effect=AssertionError("OCR is prohibited")) as ocr, \
             patch("requests.Session.request", side_effect=AssertionError("network is prohibited")), \
             patch.object(worker, "enqueue_failed_workbook", side_effect=AssertionError("OCR enqueue is prohibited")):
            result = worker.process_asset(self.db, url, "dane-weekly-xlsx", date(2026, 10, 16))
        ocr.assert_not_called()
        return result

    def test_real_worker_reviews_exact_retained_workbook_and_replay_preserves_history_xmins(self):
        self.seed_source()
        self.seed_asset()
        # A synthetic, separately keyed pre-existing quote acts only as a
        # history-preservation sentinel; it is not a source observation.
        sentinel_bytes = b"private fixture-only prior quote source"
        sentinel_id = hashlib.sha256(sentinel_bytes).hexdigest()
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
            "reference_period,content,metadata) VALUES(%s,'fixture sentinel','DANE',"
            "'https://fixture.invalid/prior.xls','application/vnd.ms-excel','original','2014',%s,%s)",
            (sentinel_id, sentinel_bytes, Jsonb({"retention": "permanent", "fixture_only": True})),
        )
        self.db.execute(
            "INSERT INTO official_price_quote(document_id,source_locator,parser_version,quote_key,"
            "product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,"
            "price,min_price,max_price,details) VALUES(%s,'fixture sentinel row','fixture-v1',%s,"
            "'fixture-papa','Papa capira','fixture-only','DANE','dane-weekly','wholesale','COP','kg',"
            "'fixture market',DATE '2014-11-07',1000,900,1100,%s)",
            (sentinel_id, hashlib.sha256(b"fixture quote identity").hexdigest(), Jsonb({"fixture_only": True})),
        )
        original_before = self.db.execute(
            "SELECT xmin::text,source_url,media_type,kind,reference_period,metadata,content "
            "FROM source_document WHERE id=%s", (DID,),
        ).fetchone()
        sentinel_before = self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,quote_key,product_id,observed_on,"
            "price,min_price,max_price,details FROM official_price_quote WHERE document_id=%s",
            (sentinel_id,),
        ).fetchall()
        version = worker.asset_parser_version("dane-weekly-xlsx", URL)
        self.assertEqual(self.process_without_network_or_archive_writes(), 0)
        first_asset = self.db.execute(
            "SELECT status,records,error,document_id,processor_version,attempts "
            "FROM ingestion_asset WHERE url=%s", (URL,),
        ).fetchone()
        self.assertEqual(first_asset, ("review", 0, candidate.REVIEW_MARKER, DID, version, 1))
        review_before = self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,record,reason "
            "FROM official_source_review WHERE document_id=%s", (DID,),
        ).fetchall()
        self.assertEqual(len(review_before), 1)
        locator, revision, record, reason = review_before[0][1:]
        self.assertEqual((locator, revision, reason), (candidate.REVIEW_LOCATOR, version, candidate.REVIEW_MARKER))
        self.assertIsNone(record["price"])
        self.assertEqual(record["details"]["native_numeric_rows_untyped"], 4503)
        self.assertEqual(record["details"]["typed_price_rows"], 0)
        self.assertIsNone(record["details"]["source_period"])
        self.assertIsNone(record["details"]["literal_unit_heading"])
        self.assertNotIn("unit", record)
        self.assertFalse(any(key in record["details"] for key in ("date", "period_start", "period_end")))
        self.assertEqual(self.db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='official:complete'", (DID, version),
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (DID,),
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM source_ocr_task WHERE document_id=%s", (DID,),
        ).fetchone(), (0,))
        self.assertEqual(queue_plan.expected_versions().obj["url:" + URL], version)
        self.assertNotIn(URL, [row[0] for row in queue_plan.backfill_candidates(self.db, 100)])
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,source_url,media_type,kind,reference_period,metadata,content "
            "FROM source_document WHERE id=%s", (DID,),
        ).fetchone(), original_before)
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,quote_key,product_id,observed_on,"
            "price,min_price,max_price,details FROM official_price_quote WHERE document_id=%s",
            (sentinel_id,),
        ).fetchall(), sentinel_before)

        self.assertEqual(self.process_without_network_or_archive_writes(), 0)
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,record,reason "
            "FROM official_source_review WHERE document_id=%s", (DID,),
        ).fetchall(), review_before)
        self.assertEqual(self.db.execute(
            "SELECT status,records,error,document_id,processor_version,attempts "
            "FROM ingestion_asset WHERE url=%s", (URL,),
        ).fetchone(), ("review", 0, candidate.REVIEW_MARKER, DID, version, 2))
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,quote_key,product_id,observed_on,"
            "price,min_price,max_price,details FROM official_price_quote WHERE document_id=%s",
            (sentinel_id,),
        ).fetchall(), sentinel_before)

    def test_wrong_retained_metadata_rejects_candidate_without_review_or_ocr(self):
        metadata = {**METADATA, "unexpected": {"must": "fail closed"}}
        self.seed_source(metadata=metadata)
        self.seed_asset()
        with patch.object(worker, "fetch_asset", return_value=BODY), \
             patch.object(worker, "archive", return_value=DID), \
             patch("pipelines.ingestion.ocr.scan_document", side_effect=AssertionError("OCR is prohibited")) as ocr, \
             patch("requests.Session.request", side_effect=AssertionError("network is prohibited")), \
             patch.object(worker, "enqueue_failed_workbook", side_effect=AssertionError("OCR enqueue is prohibited")):
            with self.assertRaisesRegex(ValueError, "retained source metadata or body changed"):
                worker.process_asset(self.db, URL, "dane-weekly-xlsx", date(2026, 10, 16))
        ocr.assert_not_called()
        self.assertEqual(self.db.execute(
            "SELECT status,document_id FROM ingestion_asset WHERE url=%s", (URL,),
        ).fetchone(), ("failed", DID))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s", (DID,),
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (DID,),
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s", (DID,),
        ).fetchone(), (0,))


if __name__ == "__main__":
    unittest.main(verbosity=2)

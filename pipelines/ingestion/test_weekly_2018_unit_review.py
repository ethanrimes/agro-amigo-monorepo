"""Exact archived 2018 XLSX unit reviews; never transfer PDF kg by guess."""

import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from psycopg.types.json import Jsonb

from . import dane_weekly, queue_plan, worker


HERE = Path(__file__).parent / "testdata"
MANIFEST = json.loads((HERE.parent / "weekly_2018_unit_reviews.json").read_text())


def original(entry):
    body = (HERE / "weekly_2018_unit_originals" / (entry["sha256"] + ".xlsx")).read_bytes()
    assert hashlib.sha256(body).hexdigest() == entry["sha256"]
    return body


class AuditedUnitOriginals(unittest.TestCase):
    def test_all_31_exact_originals_are_one_document_review_without_typed_price(self):
        docs = MANIFEST["documents"]
        self.assertEqual(len(docs), 31)
        self.assertEqual(sum(d["native_numeric_rows"] for d in docs), 144290)
        self.assertEqual(sum(d["unmatched_pdf_identity"] for d in docs), 9283)
        self.assertEqual(sum(d["same_identity_different_amount"] for d in docs), 4)
        self.assertEqual(sum(d["unmatched_pdf_identity"] for d in docs if not d["paired_pdf_date_conflict"]), 4615)
        for entry in docs:
            with self.subTest(sha=entry["sha256"]):
                body = original(entry)
                rows = dane_weekly.parse_workbook(body, entry["url"])
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertIsNone(row["price"])
                self.assertEqual(row["source_locator"], dane_weekly.UNIT_REVIEW_LOCATOR)
                self.assertEqual(row["details"]["native_numeric_rows_untyped"], entry["native_numeric_rows"])
                self.assertEqual(row["details"]["paired_pdf_sha256"], entry["paired_pdf_sha256"])
                self.assertEqual(row["details"]["prior_error"], entry["prior_error"])
                self.assertNotIn("unit", row)

    def test_other_url_or_changed_original_cannot_inherit_review(self):
        entry = MANIFEST["documents"][0]
        body = original(entry)
        with self.assertRaisesRegex(ValueError, "identity or monetary unit changed"):
            dane_weekly.parse_workbook(body, entry["url"].replace("2018.xlsx", "2019.xlsx"))
        with self.assertRaisesRegex(ValueError, "no supported monetary tables"):
            dane_weekly.parse_workbook(body + b"changed", entry["url"])


@unittest.skipUnless(os.environ.get("AGRO_SOURCE_RECOVERY_POSTGRES_TEST") == "1",
                     "Explicit opt-in for isolated PostgreSQL TEMP tables")
class AuditedUnitPostgres(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp; SET statement_timeout='60s'")
        for table in ("source_document", "official_price_quote", "official_source_review",
                      "ingestion_asset", "ingestion_checkpoint", "official_catalog_current"):
            self.db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")
        self.enterContext(patch("pipelines.ingestion.official_catalog.refresh_document", return_value=0))
        self.enterContext(patch("pipelines.ingestion.write_pacing.pause_between_batches"))
        self.entry = MANIFEST["documents"][0]
        self.body = original(self.entry)
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,records,error,processor_version,checked_at,observed_on) "
            "VALUES(%s,'dane-weekly-xlsx','failed',0,%s,%s,now()-interval '2 days',%s)",
            (self.entry["url"], self.entry["prior_error"], "official-v2:dane-weekly-v16", self.entry["source_date"]),
        )

        def archive_temp(db, url, body, kind, day):
            self.assertEqual(body, self.body)
            db.execute(
                "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) "
                "VALUES(%s,'2018 audited workbook','DANE · SIPSA',%s,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',"
                "'original',%s,%s,%s) ON CONFLICT DO NOTHING",
                (self.entry["sha256"], url, self.entry["source_date"], body,
                 Jsonb({"ingestion_kind": kind})),
            )
            return self.entry["sha256"]

        self.enterContext(patch.object(worker, "fetch_asset", return_value=self.body))
        self.enterContext(patch.object(worker, "archive", side_effect=archive_temp))
        token = worker.RUN_DEADLINE.set(None)
        self.addCleanup(worker.RUN_DEADLINE.reset, token)

    def test_atomic_review_checkpoint_replay_and_bounded_queue(self):
        url = self.entry["url"]
        with self.assertRaisesRegex(RuntimeError, "rollback probe"):
            with self.db.transaction():
                worker.process_asset(self.db, url, "dane-weekly-xlsx", worker.today())
                raise RuntimeError("rollback probe")
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review").fetchone(), (0,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone(), (0,))

        self.assertEqual(worker.process_asset(self.db, url, "dane-weekly-xlsx", worker.today()), 0)
        status, records, error, version = self.db.execute(
            "SELECT status,records,error,processor_version FROM ingestion_asset WHERE url=%s", (url,)
        ).fetchone()
        self.assertEqual((status, records, version), ("review", 0, worker.parser_version("dane-weekly-xlsx")))
        self.assertIn(self.entry["prior_error"], error)
        self.assertIn(dane_weekly.UNIT_REVIEW_MARKER, error)
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_price_quote").fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='official:complete'",
            (self.entry["sha256"], version)).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT record->'details'->>'original_sha256' FROM official_source_review WHERE document_id=%s AND parser_version=%s",
            (self.entry["sha256"], version)).fetchone(), (self.entry["sha256"],))
        self.assertNotIn(url, [r[0] for r in queue_plan.backfill_candidates(self.db, 50)])
        self.assertNotIn(url, [r[0] for r in queue_plan.daily_candidates(self.db, worker.today())])
        other = "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSASemanal-19sep25sep-2026.xlsx"
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,error,processor_version,checked_at,observed_on) "
            "VALUES(%s,'dane-weekly-xlsx','review',%s,%s,now()-interval '31 days',%s)",
            (other, dane_weekly.UNIT_REVIEW_MARKER, version, worker.today()),
        )
        self.assertIn(other, [r[0] for r in queue_plan.backfill_candidates(self.db, 50)])
        self.assertIn(other, [r[0] for r in queue_plan.daily_candidates(self.db, worker.today())])

        self.assertEqual(worker.process_asset(self.db, url, "dane-weekly-xlsx", worker.today()), 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review").fetchone(), (1,))
        self.db.execute("UPDATE ingestion_asset SET processor_version='older-version' WHERE url=%s", (url,))
        self.assertIn(url, [r[0] for r in queue_plan.backfill_candidates(self.db, 50)])
        self.db.execute("UPDATE ingestion_asset SET processor_version=%s,checked_at=now()-interval '31 days' WHERE url=%s",
                        (version, url))
        self.assertIn(url, [r[0] for r in queue_plan.backfill_candidates(self.db, 50)])

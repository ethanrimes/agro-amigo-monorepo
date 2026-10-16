"""Opt-in full worker replay of four originals on an empty disposable PostgreSQL.

Set AGRO_DATE_REPAIR_TEST_DSN to a fully provisioned, empty `agro_date_repair_*`
database on a `/tmp/agro-*` Unix socket. The test retains its SQL evidence.
"""

import hashlib
import os
import unittest
from datetime import date
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import (
    dane_weekly, official_catalog, official_sources, query_publication,
    queue_plan, weekly_boundary_review, worker, write_pacing,
)
from .resumable_inputs import WorkDeferred
from .retained_date_repairs import BASE, REPAIRS, retained_exact_date_repair
from .test_dane_date_repairs import FIXTURES, original


DAYS = {
    "mayoristas_agosto_12_2019.xlsx": date(2019, 8, 12),
    "Semana_16jun_20jun_2014.pdf": date(2014, 6, 20),
    "Semana_16nov_22nov_2013.pdf": date(2013, 11, 22),
    "Semana_29nov_6dic_2013.pdf": date(2013, 12, 6),
    "Semana_6dic_13dic_2013.pdf": date(2013, 12, 13),
    "mayoristas_febrero_20_2017.xls": date(2017, 2, 20),
}
EXPECTED = {
    "mayoristas_agosto_12_2019.xlsx": (391, 0, 0),
    "Semana_16jun_20jun_2014.pdf": (4369, 207, 75),
    "Semana_16nov_22nov_2013.pdf": (4342, 191, 47),
    "Semana_29nov_6dic_2013.pdf": (4247, 135, 45),
    "Semana_6dic_13dic_2013.pdf": (4250, 158, 45),
    "mayoristas_febrero_20_2017.xls": (393, 0, 0),
}


def no_http(*_args, **_kwargs):
    raise AssertionError("DANE source/provider HTTP escaped the retained-byte route")


@unittest.skipUnless(os.environ.get("AGRO_DATE_REPAIR_TEST_DSN"), "Explicit private PostgreSQL DSN required")
class DaneDateRepairPostgres(unittest.TestCase):
    def setUp(self):
        self.db = psycopg.connect(os.environ["AGRO_DATE_REPAIR_TEST_DSN"], autocommit=True)
        self.addCleanup(self.db.close)
        if (not self.db.info.host.startswith("/tmp/agro-")
                or not self.db.info.dbname.startswith("agro_date_repair_")
                or self.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None):
            raise RuntimeError("Only owned local agro_date_repair_* PostgreSQL is allowed")

    def test_exact_retained_bytes_queue_and_host_cooldown_guards(self):
        db = self.db
        for name in ("source_document", "ingestion_asset", "ingestion_checkpoint", "historical_price"):
            db.execute(f"CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING ALL)")
        for url, (kind, sha, media, _) in REPAIRS.items():
            name = url.rsplit("/", 1)[1]
            body = original(sha, ".pdf" if media == "application/pdf" else ".xlsx" if media.endswith("spreadsheetml.sheet") else ".xls")
            status = "pending" if "16nov" in name else "failed" if kind == "dane-weekly-pdf" else "review"
            previous = "" if status == "pending" else worker.parser_version(kind)
            error = ("Official catalog refresh deferred after 128 of 4295 identities"
                     if status == "pending" else
                     "ValueError: Weekly PDF page 43 has conflicting printed periods"
                     if status == "failed" else
                     "SourceDateMismatch: Daily link date 2017-02-20 differs from workbook 2017-01-20")
            db.execute("""INSERT INTO source_document
              (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
              VALUES(%s,%s,'DANE',%s,%s,'original',%s,%s,%s)""",
              (sha, name, url, media, DAYS[name].isoformat(), body, Jsonb({"ingestion_kind": kind})))
            db.execute("""INSERT INTO ingestion_asset
              (url,kind,observed_on,status,document_id,records,processor_version,checked_at,error)
              VALUES(%s,%s,%s,%s,%s,0,%s,now()-interval '7 hours',%s)""",
              (url, kind, DAYS[name], status, sha, previous, error))
            current = worker.asset_parser_version(kind, url)
            self.assertEqual(retained_exact_date_repair(db, url, kind, current), body)
            self.assertTrue(worker.retained_reparse_during_host_cooldown(db, url, kind))
            self.assertIsNone(retained_exact_date_repair(db, url + "?changed", kind, current))
            self.assertIsNone(retained_exact_date_repair(db, url, "daily" if kind != "daily" else "dane-weekly-pdf", current))
        nov16 = BASE + "Semana_16nov_22nov_2013.pdf"
        nov29 = BASE + "Semana_29nov_6dic_2013.pdf"
        daily = BASE + "mayoristas_febrero_20_2017.xls"
        # The queue reserves one turn per kind. Cool other weekly sources so
        # this assertion proves the exact pending branch, not queue order.
        db.execute("UPDATE ingestion_asset SET checked_at=now() WHERE kind='dane-weekly-pdf' AND url<>%s", (nov16,))
        self.assertIn(nov16, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        self.assertIn(daily, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        db.execute("UPDATE ingestion_asset SET checked_at=now() WHERE url=%s", (nov16,))
        self.assertNotIn(nov16, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '7 hours',error='unreviewed error' WHERE url=%s", (nov16,))
        self.assertNotIn(nov16, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        db.execute("UPDATE ingestion_asset SET error=NULL,records=1 WHERE url=%s", (nov16,))
        self.assertNotIn(nov16, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        db.execute("UPDATE ingestion_asset SET records=0,processor_version='unexpected' WHERE url=%s", (nov16,))
        self.assertNotIn(nov16, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        db.execute("UPDATE ingestion_asset SET processor_version='' WHERE url=%s", (nov16,))
        db.execute("UPDATE source_document SET metadata='{}'::jsonb WHERE id=%s", (REPAIRS[nov16][1],))
        self.assertNotIn(nov16, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        self.assertIsNone(retained_exact_date_repair(db, nov16, "dane-weekly-pdf", worker.asset_parser_version("dane-weekly-pdf", nov16)))
        db.execute("UPDATE source_document SET metadata=%s WHERE id=%s", (Jsonb({"ingestion_kind": "dane-weekly-pdf"}), REPAIRS[nov16][1]))
        for field, bad in (("source_url", nov16 + "?alias"),
                           ("media_type", "application/octet-stream"),
                           ("kind", "extract")):
            good = db.execute(f"SELECT {field} FROM source_document WHERE id=%s", (REPAIRS[nov16][1],)).fetchone()[0]
            db.execute(f"UPDATE source_document SET {field}=%s WHERE id=%s", (bad, REPAIRS[nov16][1]))
            self.assertNotIn(nov16, [row[0] for row in queue_plan.repair_candidates(db, 8)])
            self.assertIsNone(retained_exact_date_repair(db, nov16, "dane-weekly-pdf", worker.asset_parser_version("dane-weekly-pdf", nov16)))
            db.execute(f"UPDATE source_document SET {field}=%s WHERE id=%s", (good, REPAIRS[nov16][1]))
        db.execute("INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) VALUES(%s,'official-v2:dane-weekly-v24','official:complete',4342)", (REPAIRS[nov16][1],))
        self.assertNotIn(nov16, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        db.execute("DELETE FROM ingestion_checkpoint WHERE document_id=%s", (REPAIRS[nov16][1],))
        self.assertIn(nov16, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        changed_sha = "f" * 64
        db.execute("""INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
          SELECT %s,title,publisher,source_url,media_type,kind,reference_period,content,metadata
          FROM source_document WHERE id=%s""", (changed_sha, REPAIRS[nov16][1]))
        db.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (changed_sha, nov16))
        self.assertNotIn(nov16, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        self.assertIsNone(retained_exact_date_repair(db, nov16, "dane-weekly-pdf", worker.asset_parser_version("dane-weekly-pdf", nov16)))
        db.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (REPAIRS[nov16][1], nov16))
        db.execute("UPDATE source_document SET content=content||decode('00','hex') WHERE id=%s", (REPAIRS[nov16][1],))
        with self.assertRaisesRegex(ValueError, "SHA mismatch"):
            retained_exact_date_repair(db, nov16, "dane-weekly-pdf", worker.asset_parser_version("dane-weekly-pdf", nov16))
        self.assertTrue(worker.retained_reparse_during_host_cooldown(db, nov16, "dane-weekly-pdf"))
        db.execute("UPDATE ingestion_asset SET status='pending',processor_version='official-v2:dane-weekly-v24',checked_at=now()-interval '7 hours',error='Official source validated; committed quote batches will resume' WHERE url=%s", (nov29,))
        db.execute("UPDATE ingestion_asset SET status='complete',processor_version=%s WHERE url=%s", (worker.asset_parser_version("dane-weekly-pdf", nov16), nov16))
        self.assertIn(nov29, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        db.execute("UPDATE ingestion_asset SET processor_version=%s WHERE url=%s", (worker.asset_parser_version("dane-weekly-pdf", nov29), nov29))
        self.assertNotIn(nov29, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        self.assertIsNone(retained_exact_date_repair(db, nov29, "dane-weekly-pdf", worker.asset_parser_version("dane-weekly-pdf", nov29)))
        ordinary_url = daily + "?ordinary"
        ordinary_sha = "e" * 64
        db.execute("""INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
          SELECT %s,title,publisher,%s,media_type,kind,reference_period,content,metadata
          FROM source_document WHERE id=%s""", (ordinary_sha, ordinary_url, REPAIRS[daily][1]))
        db.execute("""INSERT INTO ingestion_asset
          (url,kind,observed_on,status,document_id,records,processor_version,checked_at)
          VALUES(%s,'daily',%s,'review',%s,0,'old',now()-interval '10 hours')""",
          (ordinary_url, DAYS[daily.rsplit("/", 1)[1]], ordinary_sha))
        self.assertIn(daily, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        db.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (ordinary_sha, daily))
        self.assertNotIn(daily, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        self.assertIn(ordinary_url, [row[0] for row in queue_plan.repair_candidates(db, 8)])
        self.assertIsNone(retained_exact_date_repair(db, daily, "daily", worker.asset_parser_version("daily", daily)))

    def test_full_worker_dispatch_rollback_resume_and_immutable_rerun(self):
        db = self.db
        self.assertEqual(db.execute("SELECT count(*) FROM source_document").fetchone()[0], 0,
                         "Use a fresh, empty owned database for the full worker control")
        for url, (kind, sha, media, _) in REPAIRS.items():
            name = url.rsplit("/", 1)[1]
            body = original(sha, ".pdf" if media == "application/pdf" else ".xlsx" if media.endswith("spreadsheetml.sheet") else ".xls")
            status = "pending" if "16nov" in name else "failed" if kind == "dane-weekly-pdf" else "review"
            previous = "" if status == "pending" else worker.parser_version(kind)
            error = ("Official catalog refresh deferred after 128 of 4295 identities"
                     if status == "pending" else
                     "ValueError: Weekly PDF page 43 has conflicting printed periods"
                     if status == "failed" else
                     "SourceDateMismatch: Daily link date 2017-02-20 differs from workbook 2017-01-20")
            db.execute("""INSERT INTO source_document
              (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
              VALUES(%s,%s,'DANE',%s,%s,'original',%s,%s,%s)""",
              (sha, name, url, media, DAYS[name].isoformat(), body,
               Jsonb({"ingestion_kind": kind, "retention": "permanent", "original_filename": name})))
            db.execute("""INSERT INTO ingestion_asset
              (url,kind,observed_on,status,document_id,records,processor_version,checked_at,error)
              VALUES(%s,%s,%s,%s,%s,0,%s,now()-interval '7 hours',%s)""",
              (url, kind, DAYS[name], status, sha, previous, error))

        nov16 = BASE + "Semana_16nov_22nov_2013.pdf"
        sha16 = REPAIRS[nov16][1]
        with patch.object(weekly_boundary_review, "reviewed_article_bottom", side_effect=lambda _u, _s, _p, _w, _t, b: b):
            baseline = dane_weekly.parse_pdf(original(sha16, ".pdf"), nov16)
        self.assertEqual((len(baseline), sum(r["price"] is not None for r in baseline)), (4486, 4295))
        with patch.object(official_catalog, "refresh_document", side_effect=WorkDeferred("controlled old catalog defer")):
            with self.assertRaises(WorkDeferred):
                official_sources.publish_rows(db, baseline, sha16, "dane-weekly-pdf")
        old_quotes = db.execute("SELECT source_locator,xmin::text FROM official_price_quote WHERE document_id=%s ORDER BY 1", (sha16,)).fetchall()
        old_reviews = db.execute("SELECT source_locator,xmin::text FROM official_source_review WHERE document_id=%s ORDER BY 1", (sha16,)).fetchall()
        self.assertEqual((len(old_quotes), len(old_reviews)), (4295, 191))
        self.assertIn(nov16, [row[0] for row in queue_plan.repair_candidates(db, 8)])

        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}), \
             patch.object(worker, "fetch_asset", side_effect=no_http), \
             patch.object(worker, "_request", side_effect=no_http), \
             patch.object(query_publication, "recover", return_value=None), \
             patch.object(write_pacing, "pause_between_batches", return_value=None), \
             patch.object(write_pacing, "yield_to_active_readers", return_value=None), \
             patch.object(official_catalog, "_sleep", return_value=None), \
             patch.object(official_catalog, "DOCUMENT_BATCH_SIZE", 512):
            for url, (kind, sha, media, _) in REPAIRS.items():
                name = url.rsplit("/", 1)[1]
                day = DAYS[name]
                self.assertTrue(worker.retained_reparse_during_host_cooldown(db, url, kind))
                if "29nov" in name:
                    def defer_after_batch(*_args, **_kwargs):
                        raise WorkDeferred("Official source validated; committed quote batches will resume")
                    with patch.object(write_pacing, "pause_between_batches", side_effect=defer_after_batch):
                        with self.assertRaises(WorkDeferred):
                            worker.process_asset(db, url, kind, day)
                    self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (sha,)).fetchone()[0], 256)
                    db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '7 hours',error='Official source validated; committed quote batches will resume' WHERE url=%s", (url,))
                    try:
                        with db.transaction():
                            db.execute("UPDATE ingestion_asset SET checked_at=now() WHERE kind='dane-weekly-pdf' AND url<>%s", (url,))
                            self.assertIn(url, [row[0] for row in queue_plan.repair_candidates(db, 8)])
                            raise RuntimeError("rollback queue-order fixture")
                    except RuntimeError as exc:
                        self.assertEqual(str(exc), "rollback queue-order fixture")
                if kind == "daily":
                    with patch.object(worker, "project", side_effect=RuntimeError("controlled daily rollback")):
                        with self.assertRaisesRegex(RuntimeError, "controlled daily rollback"):
                            worker.process_asset(db, url, kind, day)
                    self.assertEqual(db.execute("SELECT count(*) FROM historical_price WHERE document_id=%s", (sha,)).fetchone()[0], 0)
                    self.assertEqual(db.execute("SELECT count(*) FROM daily_price WHERE document_id=%s", (sha,)).fetchone()[0], 0)
                    self.assertEqual(db.execute("SELECT count(*) FROM retained_record WHERE table_name='source_date_resolution' AND record->>'document_id'=%s", (sha,)).fetchone()[0], 0)
                expected, reviews, page43 = EXPECTED[name]
                self.assertEqual(worker.process_asset(db, url, kind, day), expected)
                asset = db.execute("SELECT status,records,processor_version,document_id,observed_on FROM ingestion_asset WHERE url=%s", (url,)).fetchone()
                self.assertEqual(asset, ("complete", expected, worker.asset_parser_version(kind, url), sha, day))
                if kind == "daily":
                    self.assertEqual(db.execute("SELECT count(*) FROM historical_price WHERE document_id=%s", (sha,)).fetchone()[0], 393)
                    self.assertEqual(db.execute("SELECT count(*) FROM daily_price WHERE document_id=%s", (sha,)).fetchone()[0], 393)
                    self.assertEqual(db.execute("SELECT count(*) FROM retained_record WHERE table_name='source_date_resolution' AND record->>'document_id'=%s", (sha,)).fetchone()[0], 1)
                    tables = ("historical_price", "daily_price")
                else:
                    self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (sha,)).fetchone()[0], expected)
                    self.assertEqual(db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s", (sha,)).fetchone()[0], reviews)
                    self.assertEqual(db.execute("SELECT count(*) FROM published_official_price WHERE document_id=%s AND source_page=43", (sha,)).fetchone()[0], page43)
                    if name == "Semana_16jun_20jun_2014.pdf":
                        self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s AND series='dane-weekly'", (sha,)).fetchone()[0], 4309)
                        self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s AND series='dane-panela-article'", (sha,)).fetchone()[0], 60)
                    self.assertEqual(db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s AND step='official:complete'", (sha,)).fetchone()[0], 1)
                    tables = ("official_price_quote", "official_source_review", "ingestion_checkpoint")
                before = {table: db.execute(f"SELECT xmin::text FROM {table} WHERE document_id=%s ORDER BY xmin::text", (sha,)).fetchall() for table in tables}
                body = original(sha, ".pdf" if media == "application/pdf" else ".xlsx" if media.endswith("spreadsheetml.sheet") else ".xls")
                with patch.object(worker, "fetch_asset", return_value=body):
                    self.assertEqual(worker.process_asset(db, url, kind, day), 0 if kind == "daily" else expected)
                for table in tables:
                    self.assertEqual(db.execute(f"SELECT xmin::text FROM {table} WHERE document_id=%s ORDER BY xmin::text", (sha,)).fetchall(), before[table])
                stored = db.execute("SELECT content,source_url,media_type,kind FROM source_document WHERE id=%s", (sha,)).fetchone()
                self.assertEqual((hashlib.sha256(bytes(stored[0])).hexdigest(), *stored[1:]),
                                 (sha, url, media, "original"))
        self.assertEqual(db.execute("SELECT count(*) FROM official_catalog_current WHERE dirty").fetchone()[0], 0)
        self.assertEqual(old_quotes, db.execute("SELECT source_locator,xmin::text FROM official_price_quote WHERE document_id=%s AND source_page<>43 ORDER BY 1", (sha16,)).fetchall())
        self.assertEqual(old_reviews, db.execute("SELECT source_locator,xmin::text FROM official_source_review WHERE document_id=%s ORDER BY 1", (sha16,)).fetchall())

"""Original-bound V22 queue and OCR retirement regressions in disposable PostgreSQL."""

import getpass
import hashlib
import random
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import pdf_sources, queue_plan, worker


FIXTURES = Path(__file__).parent / "testdata"
WEEKLY_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_21feb_27feb_2015.xls"
WEEKLY_SHA = "30d900d3c1d2ee3ca4f32bd09649b682b16f9bd23a177c7200de518b8dc2bcbd"
WEEKLY_OLD = "official-v2:audited-unit-review-2018-v1:dane-weekly-v20"
WEEKLY_ERROR = "ValueError: Weekly grouped workbook has incomplete monetary cells"
PDF_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_18_2019.pdf"
PDF_SHA = "4e0ddac5f22c1c852be933d1056a66c45b67a63886aab9a2cbd7fba688a1b3ac"
PDF_DAY = date(2019, 2, 18)
PDF_V21 = "daily-pdf-v6:supply-daily-pdf-summary-v1:feb2019-verified-cover-v1"


class ExactSourceRepairsPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-v22-exact-repair-pg-", dir="/tmp"))
        cls.cluster = cls.directory / "data"
        cls.port = random.randrange(41000, 49000)
        try:
            subprocess.run(["initdb", "-D", str(cls.cluster), "--auth=trust", "--no-locale",
                            "--encoding=UTF8"], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["pg_ctl", "-D", str(cls.cluster),
                            "-l", str(cls.directory / "postgres.log"),
                            "-o", f'-k {cls.directory} -p {cls.port} -h ""',
                            "-w", "start"], check=True, stdout=subprocess.DEVNULL)
            cls.db = psycopg.connect(
                f"host={cls.directory} port={cls.port} dbname=postgres user={getpass.getuser()}",
                autocommit=True,
            )
            assert str(cls.db.info.host).startswith("/tmp/agro-v22-exact-repair-pg-")
            cls.db.execute("SET search_path=pg_temp; SET statement_timeout='30s'")
            cls.db.execute("""CREATE TEMP TABLE ingestion_checkpoint(
                document_id text,processor_version text,step text,records integer DEFAULT 0,
                created_at timestamptz DEFAULT now(),PRIMARY KEY(document_id,processor_version,step))""")
            cls.db.execute("""CREATE TEMP TABLE source_document(
                id text PRIMARY KEY,kind text,source_url text,media_type text,
                metadata jsonb,title text,publisher text,page_count integer,content bytea,reference_period text)""")
            cls.db.execute("CREATE TEMP TABLE historical_price(document_id text,series text,details jsonb)")
            cls.db.execute("""CREATE TEMP TABLE ingestion_asset(
                url text PRIMARY KEY,kind text,status text,processor_version text,
                document_id text,observed_on date,checked_at timestamptz,
                error text,attempts integer DEFAULT 0,records integer DEFAULT 0)""")
            cls.db.execute("""CREATE TEMP TABLE source_ocr_task(
                document_id text,source_kind text,source_page integer,
                source_locator text,image_id text,status text,error text,
                checked_at timestamptz,
                PRIMARY KEY(document_id,source_locator,image_id))""")
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "db", None) is not None:
            cls.db.close()
        if getattr(cls, "cluster", None) is not None and cls.cluster.exists():
            subprocess.run(["pg_ctl", "-D", str(cls.cluster), "-m", "fast", "-w", "stop"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if getattr(cls, "directory", None) is not None:
            shutil.rmtree(cls.directory, ignore_errors=True)

    def setUp(self):
        self.db.execute("BEGIN")

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def weekly_original(self):
        body = (FIXTURES / "dane_weekly_2015_02_27_schematic_header_original.xls").read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), WEEKLY_SHA)
        self.db.execute("""INSERT INTO source_document VALUES
            (%s,'original',%s,'application/vnd.ms-excel',%s)""",
            (WEEKLY_SHA, WEEKLY_URL, Jsonb({"ingestion_kind": "dane-weekly-xlsx"})))
        self.db.execute("""INSERT INTO ingestion_asset VALUES
            (%s,'dane-weekly-xlsx','failed',%s,%s,'2015-02-27',
             now()-interval '1 hour',%s,1,0)""",
            (WEEKLY_URL, WEEKLY_OLD, WEEKLY_SHA, WEEKLY_ERROR))
        return body

    def pdf_original(self):
        body = (FIXTURES / "dane_daily_2019_02_18_decorative_covers_original.pdf").read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), PDF_SHA)
        for page, status in ((1, "review"), (2, "review"), (4, "pending"),
                             (5, "deferred"), (6, "pending")):
            self.db.execute("""INSERT INTO source_ocr_task
                (document_id,source_kind,source_page,source_locator,image_id,status)
                VALUES(%s,'daily-pdf',%s,%s,%s,%s)""",
                (PDF_SHA, page, f"PDF page {page}",
                 hashlib.sha256(f"image-{page}".encode()).hexdigest(), status))
        return body

    def register_processed_pdf(self, body):
        self.db.execute("""INSERT INTO source_document VALUES
            (%s,'original',%s,'application/pdf',%s)""",
            (PDF_SHA, PDF_URL, Jsonb({"ingestion_kind": "daily-pdf"})))
        self.db.execute("""INSERT INTO ingestion_asset VALUES
            (%s,'daily-pdf','processed',%s,%s,%s,now()-interval '1 hour',
             'No supported monetary price grid',5,0)""",
            (PDF_URL, PDF_V21, PDF_SHA, PDF_DAY))
        self.assertEqual(hashlib.sha256(body).hexdigest(), PDF_SHA)

    def task_rows(self):
        return self.db.execute("""SELECT source_page,source_locator,image_id,status,error
            FROM source_ocr_task ORDER BY source_page""").fetchall()

    def retire(self, body, **overrides):
        args = dict(url=PDF_URL, did=PDF_SHA, day=PDF_DAY, data=body,
                    monetary_count=0, asset_status="processed")
        args.update(overrides)
        return worker.retire_verified_feb2019_decorative_ocr_tasks(self.db, **args)

    def test_exact_failed_workbook_has_immediate_bounded_turn_then_closes_on_failure(self):
        self.weekly_original()
        with self.db.cursor() as cur:
            with cur.copy("COPY ingestion_asset(url,kind,status,processor_version) FROM STDIN") as copy:
                for n in range(2409):
                    copy.write_row((f"https://example.invalid/pending-{n}",
                                    "dane-weekly-xlsx", "pending", WEEKLY_OLD))
        selected = queue_plan.repair_candidates(self.db, 8)
        self.assertEqual([row[0] for row in selected], [WEEKLY_URL])
        self.assertFalse(worker.retained_reparse_during_host_cooldown(
            self.db, WEEKLY_URL, "dane-weekly-xlsx"))
        target = worker.asset_parser_version("dane-weekly-xlsx", WEEKLY_URL)
        self.assertNotEqual(target, WEEKLY_OLD)
        # This mirrors worker.run's exception branch: the attempted version is
        # durable even if the corrected parser still fails.
        self.db.execute("""UPDATE ingestion_asset SET status='failed',attempts=attempts+1,
            checked_at=now(),error='ValueError: new failure',processor_version=%s
            WHERE url=%s""", (target, WEEKLY_URL))
        self.assertNotIn(WEEKLY_URL,
                         [row[0] for row in queue_plan.repair_candidates(self.db, 8)])

    def test_changed_original_error_media_and_transport_do_not_bypass_cooldown(self):
        self.weekly_original()
        for column, value in (("error", "RetryError: HTTP 429"),
                              ("document_id", "0" * 64),
                              ("processor_version", worker.asset_parser_version(
                                  "dane-weekly-xlsx", WEEKLY_URL))):
            self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s",
                            (value, WEEKLY_URL))
            self.assertNotIn(WEEKLY_URL,
                             [row[0] for row in queue_plan.repair_candidates(self.db, 8)])
            self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s",
                            ({"error": WEEKLY_ERROR, "document_id": WEEKLY_SHA,
                              "processor_version": WEEKLY_OLD}[column], WEEKLY_URL))
        for column, value in (("source_url", WEEKLY_URL + "-changed"),
                              ("media_type", "application/octet-stream")):
            self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s",
                            (value, WEEKLY_SHA))
            self.assertNotIn(WEEKLY_URL,
                             [row[0] for row in queue_plan.repair_candidates(self.db, 8)])
            self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s",
                            ({"source_url": WEEKLY_URL,
                              "media_type": "application/vnd.ms-excel"}[column], WEEKLY_SHA))

    def test_exact_decorative_tasks_retire_atomically_without_losing_evidence(self):
        body = self.pdf_original()
        before = self.task_rows()
        for page in (4, 5):
            self.assertFalse(pdf_sources.queued_price_page_needs_ocr(
                body, PDF_DAY, "daily-pdf", page))
        with self.assertRaisesRegex(RuntimeError, "simulated publication failure"):
            with self.db.transaction():
                self.assertEqual(self.retire(body), 2)
                raise RuntimeError("simulated publication failure")
        self.assertEqual(self.task_rows(), before)
        self.assertEqual(self.retire(body), 2)
        self.assertEqual(self.retire(body), 0)
        after = self.task_rows()
        self.assertEqual([(r[0], r[3]) for r in after],
                         [(1, "review"), (2, "review"), (4, "review"),
                          (5, "review"), (6, "pending")])
        self.assertEqual([(r[0], r[1], r[2]) for r in after],
                         [(r[0], r[1], r[2]) for r in before])
        from .ocr import NATIVE_DAILY_REVIEW_REASON
        self.assertTrue(all(r[4] == NATIVE_DAILY_REVIEW_REASON
                            for r in after if r[0] in (4, 5)))

    def test_processed_v21_pdf_gets_one_immediate_v22_turn_then_current_version_exits(self):
        body = self.pdf_original()
        self.register_processed_pdf(body)
        target = worker.asset_parser_version("daily-pdf", PDF_URL)
        self.assertNotEqual(target, PDF_V21)
        self.assertEqual([r[0] for r in queue_plan.repair_candidates(self.db, 8)], [PDF_URL])
        self.db.execute("UPDATE ingestion_asset SET processor_version=%s WHERE url=%s",
                        (target, PDF_URL))
        self.assertNotIn(PDF_URL,
                         [r[0] for r in queue_plan.repair_candidates(self.db, 8)])

    def test_processed_pdf_changed_pointer_or_monetary_rows_loses_priority(self):
        body = self.pdf_original()
        self.register_processed_pdf(body)
        for column, value in (("document_id", "0" * 64),
                              ("records", 1),
                              ("status", "pending")):
            self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s",
                            (value, PDF_URL))
            self.assertNotIn(PDF_URL,
                             [r[0] for r in queue_plan.repair_candidates(self.db, 8)])
            self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s",
                            ({"document_id": PDF_SHA, "records": 0,
                              "status": "processed"}[column], PDF_URL))

    def test_changed_bytes_rows_url_date_and_version_cannot_retire_tasks(self):
        body = self.pdf_original()
        before = self.task_rows()
        for kwargs in ({"data": body + b"changed"},
                       {"url": PDF_URL + "-changed"},
                       {"did": "0" * 64},
                       {"day": date(2019, 2, 19)},
                       {"monetary_count": 1},
                       {"asset_status": "complete"}):
            if "data" in kwargs:
                with self.assertRaisesRegex(ValueError, "SHA changed"):
                    self.retire(body, **kwargs)
            else:
                self.assertEqual(self.retire(body, **kwargs), 0)
            self.assertEqual(self.task_rows(), before)
        with patch.dict(worker.URL_SOURCE_REPAIR_VERSIONS,
                        {PDF_URL: ("daily-pdf", ":future-native-v2")}):
            self.assertEqual(self.retire(body), 0)
        self.assertEqual(self.task_rows(), before)

    def test_new_monetary_raster_keeps_ocr_mandatory(self):
        body = self.pdf_original()
        before = self.task_rows()
        with patch.object(pdf_sources, "queued_price_page_needs_ocr",
                          side_effect=lambda _body, _day, _kind, page: page == 4):
            with self.assertRaisesRegex(ValueError, "now needs OCR"):
                self.retire(body)
        self.assertEqual(self.task_rows(), before)


if __name__ == "__main__":
    unittest.main()

"""Exact 2015/2016 DANE and 2024 Porkcolombia source regressions."""

import hashlib
import io
import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pdfplumber
import xlrd
from psycopg.types.json import Jsonb

from . import blob_archive, colombia_sources, daily_recovery, dane_weekly, ocr, official_sources, pdf_sources, queue_plan, worker

FIX = Path(__file__).parent / "testdata"
PORK = "1386adec00a45eded951ff1466127f4f9a64d6243ee1639f5ff11f46a86b5450"
DAILY = "bbb69b2938848e95c9728a34c9204dd9fb19e720d54b05dd2f9b8289079a0f0f"
DAILY_PDF = "8504efb990294f3d77f092e4e1fb48b16a15be4dab43a1ec52020e8a0e653e7e"
JUNE_PDF = "c3192584b35f69b03e8ba93872f9807f04109631d87fa76fc4671d06c05f4a64"
WUXAL = "cb2289b8dad52378bc04a9787c7560a93a1feccfd47c64a41e010a33a499f5ab"
WUXAL_2015 = "58b12b179a9293e584e22473f60a97fab1b632cee35f27318953dc7de10e866c"
PORK_OLD = "PDF page 3, Cerdo en pie, y 426.0, market Antioquia"
PORK_CURRENT = "PDF page 1, current prices column 1, y 471.0"
JUNE_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_09jun__15jun_2018.pdf"


def original(sha, suffix):
    body = (FIX / (sha + suffix)).read_bytes()
    assert hashlib.sha256(body).hexdigest() == sha
    return body


class V7Originals(unittest.TestCase):
    def test_december_xls_date_typo_has_independent_dated_pdf_and_316_native_rows(self):
        body = original(DAILY, ".xls")
        book = xlrd.open_workbook(file_contents=body)
        sheet = book.sheet_by_index(0)
        self.assertEqual(sheet.cell_value(1, 0), "Martes 1 de dciembre de 2015")
        self.assertEqual((sheet.cell_value(11, 0), sheet.cell_value(11, 1)), ("Habichuela", 1080.0))
        with pdfplumber.open(io.BytesIO(original(DAILY_PDF, ".pdf"))) as pdf:
            text = pdf.pages[0].extract_text() or ""
        self.assertIn("1 de diciembre de 2015", text)
        self.assertIn("Armenia, Mercar", text)
        self.assertIn("$1.080", text)
        result = daily_recovery.parse_daily(body, date(2015, 12, 1))
        self.assertEqual((len(result["rows"]), len(result["reviews"]), len(result["date_resolutions"])), (316, 0, 1))
        self.assertEqual(result["date_resolutions"][0]["corroborating_sha256"], DAILY_PDF)
        self.assertTrue(any(row[3] == "Habichuela" and row[4] == "Armenia, Mercar"
                            and row[6] == 1080 for row in result["rows"]))
        with self.assertRaisesRegex(worker.SourceDateMismatch, "different archive date"):
            daily_recovery.parse_daily(body, date(2015, 12, 2))

    def test_undecodable_embedded_jpeg_is_retained_as_exact_review_not_bin(self):
        body = original(DAILY, ".xls")
        images = list(ocr.spreadsheet_images(body, failed_only=True, normal_extraction_failed=True))
        self.assertEqual(len(images), 1)
        locator, content = images[0]
        self.assertEqual(locator, "XLS Workbook image at byte 12358")
        self.assertEqual(hashlib.sha256(content).hexdigest(), "ca9dc363f568289b9eb1106e751e2576bbab9fbd4e8d8c3b6faecd5c5da95cf7")
        self.assertTrue(content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9"))
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}):
            self.assertFalse(blob_archive.retain_original_blob(hashlib.sha256(content).hexdigest(), content, ".jpg", "image/jpeg"))
            with self.assertRaisesRegex(ValueError, "Unsupported original archive suffix"):
                blob_archive.retain_original_blob(hashlib.sha256(content).hexdigest(), content, ".bin", "application/octet-stream")
            with self.assertRaisesRegex(ValueError, "JPEG original archive signature changed"):
                blob_archive.retain_original_blob(hashlib.sha256(b"wrong").hexdigest(), b"wrong", ".jpg", "image/jpeg")
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (
            "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_diciembre_1_2015.xls", "DANE")
        with patch.object(worker, "archive", return_value="embedded-image-id") as archived:
            ocr.scan_document(db, body, DAILY, "daily", normal_extraction_failed=True)
        self.assertEqual(archived.call_args.kwargs["filename"], "embedded-image.jpg")
        self.assertEqual(archived.call_args.kwargs["parents"], [DAILY])
        self.assertTrue(any("'review'" in call.args[0] for call in db.execute.call_args_list))

    def test_pork_semena23_old_cell_is_explicit_review_of_exact_current_quote(self):
        rows = colombia_sources.parse_pork(original(PORK, ".pdf"))
        old = next(row for row in rows if row["source_locator"] == PORK_OLD)
        current = next(row for row in rows if row["source_locator"] == PORK_CURRENT)
        self.assertEqual((old["date"], old["market"], old["unit"], old["price"]),
                         ("2024-06-07", "Antioquia", "kg en pie", None))
        self.assertEqual((current["date"], current["market"], current["unit"], current["price"]),
                         ("2024-06-07", "Antioquia", "kg en pie", 9173.0))
        self.assertEqual(old["details"]["original_price"], "9.173")
        self.assertEqual(old["details"]["duplicate_of"], PORK_CURRENT)
        self.assertEqual(old["details"]["original_sha256"], PORK)
        self.assertEqual(len([r for r in rows if r["source_locator"] == PORK_OLD]), 1)

    def test_wuxal_continuation_is_not_presentation_and_2015_typo_is_literal(self):
        oracle = json.loads((FIX / "wuxal_2015_2016_independent_rows.json").read_text())
        self.assertEqual(oracle["rows"][1]["price"], 34025)
        self.assertEqual(oracle["rows"][1]["presentation"], "1 litro")
        rows = pdf_sources.parse_input_pdf(original(WUXAL, ".pdf"), date(2016, 2, 29), last_page=20)
        target = next(row for row in rows if "PDF page 20,col 1,y 158.3" in row[0])
        self.assertEqual((target[3], target[4], target[5], target[6]),
                         ("Wuxal Tapa Negra", "Armenia", "1 litro", 34025))
        self.assertEqual(target[-1]["printed_heading_suffix"], "(continaución)")
        self.assertEqual(target[-1]["source_heading_literal"], "Wuxal Tapa Negra, 1 litro (continaución)")
        with pdfplumber.open(io.BytesIO(original(WUXAL_2015, ".pdf"))) as pdf:
            text = pdf.pages[20].extract_text() or ""
        self.assertIn("Wuxal tapa Nnegra, 1 litro", text)
        self.assertEqual(oracle["rows"][0]["price"], 30550)

    def test_june15_pdf_remains_a_printed_date_conflict(self):
        body = original(JUNE_PDF, ".pdf")
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            self.assertIn("15 de junio", pdf.pages[0].extract_text() or "")
            self.assertIn("26 de mayo al 1 de junio", pdf.pages[8].extract_text() or "")
        with self.assertRaisesRegex(worker.SourceDateMismatch, "printed period conflicts"):
            dane_weekly.parse_pdf(body, JUNE_URL)


@unittest.skipUnless(os.environ.get("AGRO_SOURCE_RECOVERY_POSTGRES_TEST") == "1",
                     "Explicit isolated PostgreSQL TEMP-table opt-in")
class V7QueuePostgres(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp")
        for table in ("ingestion_asset", "official_source_review"):
            self.db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")

    def test_june_conflict_retired_only_for_exact_current_version_and_recent_original(self):
        version = worker.parser_version("dane-weekly-pdf")
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,document_id,status,error,processor_version,checked_at,observed_on) "
            "VALUES(%s,'dane-weekly-pdf',%s,'review',%s,%s,now()-interval '2 days','2018-06-15')",
            (JUNE_URL, JUNE_PDF, "SourceDateMismatch: Weekly printed period conflicts with the dated source URL", version),
        )
        self.assertNotIn(JUNE_URL, [r[0] for r in queue_plan.backfill_candidates(self.db, 50)])
        self.db.execute("UPDATE ingestion_asset SET processor_version='older-parser' WHERE url=%s", (JUNE_URL,))
        self.assertIn(JUNE_URL, [r[0] for r in queue_plan.backfill_candidates(self.db, 50)])
        self.db.execute("UPDATE ingestion_asset SET processor_version=%s,checked_at=now()-interval '31 days' WHERE url=%s", (version, JUNE_URL))
        self.assertIn(JUNE_URL, [r[0] for r in queue_plan.backfill_candidates(self.db, 50)])
        other = JUNE_URL.replace("15jun", "22jun")
        self.db.execute("UPDATE ingestion_asset SET url=%s,document_id='another-original',status='failed',checked_at=now()-interval '2 days' WHERE url=%s", (other, JUNE_URL))
        self.assertIn(other, [r[0] for r in queue_plan.backfill_candidates(self.db, 50)])


@unittest.skipUnless(os.environ.get("AGRO_SOURCE_RECOVERY_POSTGRES_TEST") == "1",
                     "Explicit isolated PostgreSQL TEMP-table opt-in")
class V7PorkPostgres(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp; SET statement_timeout='60s'")
        for table in ("source_document", "official_price_quote", "official_source_review",
                      "ingestion_asset", "ingestion_checkpoint", "official_catalog_current"):
            self.db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")
        self.enterContext(patch("pipelines.ingestion.official_catalog.refresh_document", return_value=0))
        self.enterContext(patch("pipelines.ingestion.write_pacing.pause_between_batches"))
        token = worker.RUN_DEADLINE.set(None)
        self.addCleanup(worker.RUN_DEADLINE.reset, token)

    def test_old_page3_quote_retained_and_reviewed_atomically_after_page1_validation(self):
        body = original(PORK, ".pdf")
        url = "https://porkcolombia.co/wp-content/uploads/2024/06/Semana23de2024.pdf"
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) "
            "VALUES(%s,'Semana 23','Porkcolombia / FNP',%s,'application/pdf','original','2024-06',%s,%s)",
            (PORK, url, body, Jsonb({"ingestion_kind": "colombia-pork-pdf"})))
        self.db.execute("INSERT INTO ingestion_asset(url,kind,document_id,status) "
                        "VALUES(%s,'colombia-pork-pdf',%s,'complete')", (url, PORK))
        rows = colombia_sources.parse_pork(body)
        official_sources.publish_rows(self.db, [r for r in rows if r["source_locator"] != PORK_OLD], PORK, "colombia-pork-pdf")
        self.db.execute(
            "INSERT INTO official_price_quote(document_id,source_locator,parser_version,quote_key,"
            "product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,"
            "period_start,price,min_price,max_price,source_page,details) "
            "SELECT document_id,%s,'legacy-pork-v2',quote_key,product_id,product_name,category,"
            "publisher,series,basis,currency,unit,market,observed_on,period_start,price,min_price,"
            "max_price,3,details FROM official_price_quote WHERE document_id=%s AND source_locator=%s",
            (PORK_OLD, PORK, PORK_CURRENT))
        with self.assertRaisesRegex(RuntimeError, "rollback probe"):
            with self.db.transaction():
                official_sources.publish_rows(self.db, rows, PORK, "colombia-pork-pdf")
                raise RuntimeError("rollback probe")
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review WHERE source_locator=%s",
                                         (PORK_OLD,)).fetchone(), (0,))
        official_sources.publish_rows(self.db, rows, PORK, "colombia-pork-pdf")
        self.assertEqual(self.db.execute(
            "SELECT price,market,unit FROM official_price_quote WHERE document_id=%s "
            "AND source_locator=%s AND parser_version='legacy-pork-v2'", (PORK, PORK_OLD)
        ).fetchone(), (9173, "Antioquia", "kg en pie"))
        self.assertEqual(self.db.execute(
            "SELECT record->>'price',record->'details'->>'duplicate_of' FROM official_source_review "
            "WHERE document_id=%s AND source_locator=%s AND parser_version=%s",
            (PORK, PORK_OLD, worker.parser_version("colombia-pork-pdf"))
        ).fetchone(), (None, PORK_CURRENT))
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review WHERE source_locator=%s",
                                         (PORK_OLD,)).fetchone(), (1,))

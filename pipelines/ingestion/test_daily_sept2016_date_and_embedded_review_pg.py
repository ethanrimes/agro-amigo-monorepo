"""Exact DANE Sept 5 2016 date recovery and fail-closed embedded-image reviews."""

import getpass
import hashlib
import io
import os
import random
import re
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pdfplumber
import psycopg
import xlrd
from PIL import UnidentifiedImageError
from psycopg.types.json import Jsonb

from . import daily_recovery, ocr, worker


XLS_SHA = "dde84100bdbe8f0eb0521361d4724ce8481cd3ecd5032dfd64de0b82b1ad47fe"
PDF_SHA = "5ccb7c57c04dab61862a20e53695ae0c4e039945117789ad1c4692599c122b5f"
IMAGE_SHA = "ca9dc363f568289b9eb1106e751e2576bbab9fbd4e8d8c3b6faecd5c5da95cf7"
URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_septiembre_5_2016.xls"
FIXTURES = Path(__file__).parent / "testdata" / "daily_sept2016"
XLS = FIXTURES / (XLS_SHA + ".xls")
PDF = FIXTURES / (PDF_SHA + ".pdf")
DAY = date(2016, 9, 5)


class Sept2016NativeDate(unittest.TestCase):
    def test_two_exact_originals_and_three_independent_cell_pairs(self):
        xls, pdf = XLS.read_bytes(), PDF.read_bytes()
        self.assertEqual(hashlib.sha256(xls).hexdigest(), XLS_SHA)
        self.assertEqual(hashlib.sha256(pdf).hexdigest(), PDF_SHA)
        evidence = daily_recovery.VERIFIED_DATE_RECOVERIES[XLS_SHA]
        self.assertEqual(evidence["corroborating_sha256"], PDF_SHA)
        self.assertEqual(evidence["printed_heading"], "Lunes 5 de 2016 de 2016")
        book = xlrd.open_workbook(file_contents=xls)
        sheet = book.sheet_by_name("Boletín diario")
        self.assertEqual(sheet.cell_value(1, 0), evidence["printed_heading"])
        self.assertEqual((sheet.nrows, sheet.ncols), (46, 29))
        self.assertEqual(sheet.cell_value(2, 0), "Precio $/Kg")
        self.assertEqual(sheet.cell_value(11, 0), "Habichuela")
        with pdfplumber.open(io.BytesIO(pdf)) as source:
            printed = source.pages[0].extract_text()
        self.assertTrue(printed.startswith("5 de septiembre de 2016"))
        literal_pairs = (
            (7, "Cali, \nCavasa", 2450, 78,
             r"Cali, Cavasa, el kilo.*?\$2\.450.*?alza del 78%"),
            (9, "Cartagena, Bazurto", 2500, 72,
             r"Cartagena, Bazurto, en donde.*?\$2\.500.*?aumentaron un 72%"),
            (27, "Villavicencio, CAV", 1750, 40,
             r"Villavicencio, CAV, también subió un\s+40%.*?\$1\.750"),
        )
        self.assertEqual(len(evidence["corroborating_cells"]), len(literal_pairs))
        for column, market, price, change, text_pattern in literal_pairs:
            with self.subTest(market=market):
                self.assertEqual(sheet.cell_value(2, column), market)
                self.assertEqual((sheet.cell_value(3, column),
                                  sheet.cell_value(3, column + 1)), ("Precio", "Var %"))
                self.assertEqual(sheet.cell_value(11, column), price)
                self.assertEqual(sheet.cell_value(11, column + 1) * 100, change)
                self.assertIsNotNone(re.search(text_pattern, printed, re.DOTALL))

    def test_all_398_native_rows_and_no_image_ocr_on_readable_grid(self):
        body = XLS.read_bytes()
        self.assertEqual(list(ocr.spreadsheet_images(
            body, failed_only=True, normal_extraction_failed=False)), [])
        result = daily_recovery.parse_daily(body, DAY)
        self.assertEqual((len(result["rows"]), len(result["reviews"]),
                          len(result["date_resolutions"])), (398, 0, 1))
        self.assertEqual(result["date_resolutions"][0]["corroborating_sha256"], PDF_SHA)
        expected = {
            "Cali, Cavasa": ("Boletín diario!row 12,col 8", 2450, 78),
            "Cartagena, Bazurto": ("Boletín diario!row 12,col 10", 2500, 72),
            "Villavicencio, CAV": ("Boletín diario!row 12,col 28", 1750, 40),
        }
        actual = {r[4]: (r[0], r[6], r[7]) for r in result["rows"]
                  if r[3] == "Habichuela" and r[4] in expected}
        self.assertEqual(actual, expected)
        self.assertTrue(all(r[-1]["date_resolution"]["corroborating_sha256"] == PDF_SHA
                            for r in result["rows"]))

    def test_changed_heading_sha_date_or_pdf_pair_fails_closed(self):
        body = XLS.read_bytes()
        book = xlrd.open_workbook(file_contents=body)
        rows = [[c.value for c in book.sheet_by_index(0).row(i)] for i in range(4)]
        rows[1][0] = "Lunes 5 de enero de 2016"
        with self.assertRaises(worker.SourceDateMismatch):
            daily_recovery._publication_day(body, rows, DAY)
        with self.assertRaises(ValueError):
            daily_recovery._publication_day(body + b"changed bytes", rows[:1], DAY)
        with self.assertRaises(worker.SourceDateMismatch):
            daily_recovery.parse_daily(body, date(2016, 9, 6))
        pdf = PDF.read_bytes()
        self.assertNotEqual(hashlib.sha256(pdf + b"changed").hexdigest(), PDF_SHA)
        with pdfplumber.open(io.BytesIO(pdf)) as source:
            text = source.pages[0].extract_text()
        self.assertIsNone(re.search(r"Cali, Cavasa, el kilo.*?\$2\.450.*?alza del 78%",
                                    text.replace("$2.450", "$2.451"), re.DOTALL))


class EmbeddedImagePostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-sept2016-image-pg-", dir="/tmp"))
        cls.cluster = cls.directory / "data"
        cls.port = random.randrange(41000, 49000)
        try:
            subprocess.run(["initdb", "-D", str(cls.cluster), "--auth=trust", "--no-locale",
                            "--encoding=UTF8"], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["pg_ctl", "-D", str(cls.cluster), "-l", str(cls.directory / "postgres.log"),
                            "-o", f'-k {cls.directory} -p {cls.port} -h ""', "-w", "start"],
                           check=True, stdout=subprocess.DEVNULL)
            cls.db = psycopg.connect(
                f"host={cls.directory} port={cls.port} dbname=postgres user={getpass.getuser()}",
                autocommit=True)
            assert str(cls.db.info.host).startswith("/tmp/agro-sept2016-image-pg-")
            cls.db.execute("SET search_path=pg_temp")
            cls.db.execute("""CREATE TEMP TABLE source_document(
                id text PRIMARY KEY,title text,publisher text,source_url text,media_type text,
                kind text,reference_period text,page_count integer,content bytea,
                metadata jsonb NOT NULL DEFAULT '{}'::jsonb)""")
            cls.db.execute("""CREATE TEMP TABLE ingestion_asset(
                url text PRIMARY KEY,kind text,observed_on date,status text,
                processor_version text,document_id text,records integer,
                checked_at timestamptz,attempts integer,error text)""")
            cls.db.execute("""CREATE TEMP TABLE source_ocr_scan(
                document_id text,version text,scanned_at timestamptz DEFAULT now(),
                PRIMARY KEY(document_id,version))""")
            cls.db.execute("""CREATE TEMP TABLE source_ocr_task(
                document_id text,source_locator text,image_id text,source_kind text,
                source_page integer,status text DEFAULT 'pending',checked_at timestamptz,
                error text,PRIMARY KEY(document_id,source_locator))""")
            cls.db.execute("""CREATE TEMP TABLE official_source_review(
                document_id text,source_locator text,parser_version text,
                record jsonb NOT NULL,reason text NOT NULL,
                PRIMARY KEY(document_id,source_locator,parser_version))""")
            cls.db.execute("""CREATE TEMP TABLE historical_price(
                document_id text,source_locator text,price numeric,
                PRIMARY KEY(document_id,source_locator))""")
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "db", None) is not None:
            cls.db.close()
        if getattr(cls, "cluster", None) is not None and cls.cluster.exists():
            subprocess.run(["pg_ctl", "-D", str(cls.cluster), "-m", "fast", "-w", "stop"],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if getattr(cls, "directory", None) is not None:
            shutil.rmtree(cls.directory, ignore_errors=True)

    def setUp(self):
        self.db.execute("TRUNCATE source_ocr_task,source_ocr_scan,official_source_review,"
                        "historical_price,ingestion_asset,source_document")
        self.db.execute("""INSERT INTO source_document
            (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
            VALUES(%s,'Sept 5 XLS','DANE',%s,'application/vnd.ms-excel','original',
                   '2016-09-05',%s,%s)""",
                        (XLS_SHA, URL, XLS.read_bytes(), Jsonb({"ingestion_kind": "daily"})))
        self.db.execute("""INSERT INTO ingestion_asset
            (url,kind,observed_on,status,processor_version,document_id,records,attempts)
            VALUES(%s,'daily',%s,'pending','daily-units-v6',%s,0,0)""",
                        (URL, DAY, XLS_SHA))

    def test_complete_corrupt_jpeg_is_retained_with_real_parent_and_review(self):
        body = XLS.read_bytes()
        image_pairs = list(ocr.spreadsheet_images(body, failed_only=True,
                                                  normal_extraction_failed=True))
        self.assertEqual(len(image_pairs), 1)
        self.assertEqual(hashlib.sha256(image_pairs[0][1]).hexdigest(), IMAGE_SHA)
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}):
            ocr.scan_document(self.db, body, XLS_SHA, "daily", normal_extraction_failed=True)
        child = self.db.execute("""SELECT kind,media_type,octet_length(content),metadata
            FROM source_document WHERE id=%s""", (IMAGE_SHA,)).fetchone()
        self.assertEqual(child[:3], ("extract", "image/jpeg", len(image_pairs[0][1])))
        self.assertEqual(child[3]["parents"], [XLS_SHA])
        self.assertEqual(child[3]["original_filename"], "embedded-image.jpg")
        task = self.db.execute("""SELECT source_locator,image_id,status,error
            FROM source_ocr_task WHERE document_id=%s""", (XLS_SHA,)).fetchone()
        self.assertEqual(task[0:3], ("XLS Workbook image at byte 12358", IMAGE_SHA, "review"))
        self.assertIn("Unsupported embedded image encoding", task[3])
        self.assertEqual(self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 0)
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}):
            ocr.scan_document(self.db, body, XLS_SHA, "daily", normal_extraction_failed=True)
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_task").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_document").fetchone()[0], 2)

    def test_unknown_bytes_review_persists_without_masking_native_error(self):
        content = b"WMF\x00unrecognized vector image payload"
        locator = "XLS Workbook image at byte 2350"
        def unknown(*_args, **_kwargs):
            yield locator, content
        native_error = "Daily workbook has no verifiable publication date"
        with patch.object(worker, "_process_asset", side_effect=ValueError(native_error)):
            with patch.object(ocr, "spreadsheet_images", side_effect=unknown):
                with patch.object(ocr.Image, "open", side_effect=UnidentifiedImageError("unknown")):
                    with patch.object(worker, "archive", side_effect=AssertionError("fake child archive")):
                        with self.assertRaisesRegex(ValueError, native_error):
                            worker.process_asset(self.db, URL, "daily", DAY)
                        with self.assertRaisesRegex(ValueError, native_error):
                            worker.process_asset(self.db, URL, "daily", DAY)
        reviews = self.db.execute("""SELECT document_id,source_locator,parser_version,
            record,reason FROM official_source_review""").fetchall()
        self.assertEqual(len(reviews), 1)
        did, source_locator, version, record, reason = reviews[0]
        self.assertEqual((did, source_locator), (XLS_SHA, locator))
        self.assertEqual(version, ocr.VERSION + ":unsupported-embedded-image-v1")
        self.assertEqual(record["embedded_sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(record["embedded_bytes"], len(content))
        self.assertTrue(record["retained_in_parent_workbook"])
        self.assertFalse(record["typed_prices"])
        self.assertIn("immutable workbook", reason)
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_document").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_task").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT status FROM ingestion_asset WHERE url=%s", (URL,)).fetchone()[0],
                         "pending")


if __name__ == "__main__":
    unittest.main()

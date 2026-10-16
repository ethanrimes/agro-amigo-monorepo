"""Original-bound V21 repairs retain monetary uncertainty and scanned-grid OCR."""

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

import pdfplumber
import psycopg
from psycopg.types.json import Jsonb

from . import dane_weekly, pdf_sources, queue_plan, worker


HERE = Path(__file__).parent
WEEKLY_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_21feb_27feb_2015.xls"
WEEKLY_SHA = "30d900d3c1d2ee3ca4f32bd09649b682b16f9bd23a177c7200de518b8dc2bcbd"
WEEKLY_BODY = (HERE / "testdata/dane_weekly_2015_02_27_schematic_header_original.xls").read_bytes()
DAILY_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_18_2019.pdf"
DAILY_SHA = "4e0ddac5f22c1c852be933d1056a66c45b67a63886aab9a2cbd7fba688a1b3ac"
DAILY_PATH = HERE / "testdata/dane_daily_2019_02_18_decorative_covers_original.pdf"
DAILY_BODY = DAILY_PATH.read_bytes()


class ExactNativeOriginals(unittest.TestCase):
    def test_2015_schematic_header_keeps_all_literals_unverified(self):
        self.assertEqual(hashlib.sha256(WEEKLY_BODY).hexdigest(), WEEKLY_SHA)
        rows = dane_weekly.parse_workbook(WEEKLY_BODY, WEEKLY_URL)
        self.assertEqual(len(rows), 4578)
        self.assertEqual(sum(row["price"] is not None for row in rows), 0)
        self.assertEqual({row["unit"] for row in rows}, {"unverified"})
        by_locator = {row["source_locator"]: row for row in rows}
        self.assertNotIn("Información Boletin!row 3,cols B:D", by_locator)
        for locator, product, market, expected in (
            ("Información Boletin!row 5,cols B:D", "Acelga", "Armenia, Mercar", (1467, 1467, 1467)),
            ("Información Boletin!row 7,cols B:D", "Acelga", "Bogotá, D.C., Corabastos", (800, 1500, 1048)),
            ("Información Boletin!row 2961,cols B:D", "Huevo blanco A", "Buenaventura (Valle del Cauca)", (267, 280, 273)),
        ):
            with self.subTest(locator=locator):
                row = by_locator[locator]
                self.assertEqual((row["product_name"], row["market"]), (product, market))
                self.assertEqual((row["min"], row["max"], row["details"]["literal_mean"]), expected)
                self.assertIsNone(row["price"])

    def test_2015_changed_original_or_other_malformed_market_still_fails(self):
        sheets = [(name, list(rows)) for name, rows in worker.workbooks(WEEKLY_BODY)]
        with patch.object(worker, "workbooks", return_value=sheets):
            with self.assertRaisesRegex(ValueError, "incomplete monetary cells"):
                dane_weekly.parse_workbook(WEEKLY_BODY + b"changed", WEEKLY_URL)
        with patch.object(worker, "workbooks", return_value=sheets):
            with self.assertRaisesRegex(ValueError, "incomplete monetary cells"):
                dane_weekly.parse_workbook(WEEKLY_BODY, WEEKLY_URL.replace("www.dane.gov.co", "other.example"))
        name, rows = sheets[0]
        rows[6] = list(rows[6])
        rows[6][2] = "unreadable price"
        with patch.object(worker, "workbooks", return_value=[(name, rows)]):
            with self.assertRaisesRegex(ValueError, "incomplete monetary cells"):
                dane_weekly.parse_workbook(WEEKLY_BODY, WEEKLY_URL)

    def test_2019_exact_artwork_needs_no_ocr_and_no_price(self):
        self.assertEqual(hashlib.sha256(DAILY_BODY).hexdigest(), DAILY_SHA)
        expected = {
            4: "5863f18041a7eed718cef551a819f2bf50ecdc08c69726681dea44ee896da3ce",
            5: "8b10815133e6a3c2e1f46cd25e327fc2ec5e99afaa61e7bc92a2c8a8e2d2ef56",
        }
        with pdfplumber.open(DAILY_PATH) as pdf:
            for number, image_sha in expected.items():
                with self.subTest(page=number):
                    page = pdf.pages[number - 1]
                    self.assertEqual(len(page.images), 1)
                    self.assertEqual(hashlib.sha256(page.images[0]["stream"].get_data()).hexdigest(), image_sha)
                    self.assertEqual((page.extract_text() or "").strip(), "")
                    self.assertFalse(pdf_sources.native_price_page_failure(page, "", []))
                    with patch.object(pdf_sources, "VERIFIED_DECORATIVE_IMAGE_SHA256", frozenset()):
                        self.assertTrue(pdf_sources.native_price_page_failure(page, "", []))
                    self.assertFalse(pdf_sources.queued_price_page_needs_ocr(
                        DAILY_BODY, date(2019, 2, 18), "daily-pdf", number
                    ))
        # The worker maps this exact native no-grid result to processed/0;
        # the parser must no longer queue a decorative page for OCR.
        with self.assertRaisesRegex(ValueError, "No supported price grids"):
            list(pdf_sources.parse_archived_price_pdf(
                None, DAILY_BODY, DAILY_SHA, date(2019, 2, 18), "daily-pdf"
            ))


class ExactAutomaticRepairLane(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-v21-exact-pg-", dir="/tmp"))
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
                autocommit=True,
            )
            cls.db.execute("SET search_path=pg_temp; SET statement_timeout='30s'")
            cls.db.execute("""CREATE TEMP TABLE ingestion_checkpoint(
                document_id text,processor_version text,step text,records integer DEFAULT 0,
                created_at timestamptz DEFAULT now(),PRIMARY KEY(document_id,processor_version,step))""")
            cls.db.execute("""CREATE TEMP TABLE source_document(
                id text PRIMARY KEY,source_url text,kind text,media_type text,
                metadata jsonb,content bytea,title text,publisher text,page_count integer,reference_period text)""")
            cls.db.execute("CREATE TEMP TABLE historical_price(document_id text,series text,details jsonb)")
            cls.db.execute("""CREATE TEMP TABLE ingestion_asset(
                url text PRIMARY KEY,kind text,status text,processor_version text,
                document_id text,observed_on date,checked_at timestamptz,
                attempts integer DEFAULT 0,records integer DEFAULT 0,error text)""")
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
        self.db.execute("TRUNCATE ingestion_asset,source_document")
        for sha, url, kind, media, body, day, status, error in (
            (WEEKLY_SHA, WEEKLY_URL, "dane-weekly-xlsx", "application/vnd.ms-excel",
             WEEKLY_BODY, date(2015, 2, 27), "failed", "ValueError: Weekly grouped workbook has incomplete monetary cells"),
            (DAILY_SHA, DAILY_URL, "daily-pdf", "application/pdf",
             DAILY_BODY, date(2019, 2, 18), "awaiting-ocr", "Price PDF pages [4, 5] await agreeing OCR readings"),
        ):
            self.db.execute("INSERT INTO source_document(id,source_url,kind,media_type,metadata,content) VALUES(%s,%s,'original',%s,%s,%s)",
                            (sha, url, media, Jsonb({"ingestion_kind": kind}), body))
            self.db.execute("""INSERT INTO ingestion_asset
                (url,kind,status,processor_version,document_id,observed_on,checked_at,error)
                VALUES(%s,%s,%s,%s,%s,%s,now()-interval '7 hours',%s)""",
                (url, kind, status, worker.parser_version(kind), sha, day, error))

    def test_two_exact_repairs_selected_ahead_of_large_pending_backlog(self):
        self.assertEqual(queue_plan.expected_versions().obj["url:" + WEEKLY_URL],
                         worker.asset_parser_version("dane-weekly-xlsx", WEEKLY_URL))
        self.assertEqual(queue_plan.expected_versions().obj["url:" + DAILY_URL],
                         worker.asset_parser_version("daily-pdf", DAILY_URL))
        with self.db.cursor() as cur:
            with cur.copy("COPY ingestion_asset(url,kind,status,processor_version) FROM STDIN") as copy:
                for n in range(2409):
                    copy.write_row((f"https://example.invalid/weekly-{n}.xls", "dane-weekly-xlsx",
                                    "pending", worker.parser_version("dane-weekly-xlsx")))
        selected = {row[0] for row in queue_plan.repair_candidates(self.db, 8)}
        self.assertEqual(selected, {WEEKLY_URL, DAILY_URL})
        self.db.execute("UPDATE ingestion_asset SET processor_version=%s WHERE url=%s",
                        (worker.asset_parser_version("daily-pdf", DAILY_URL), DAILY_URL))
        self.assertEqual({row[0] for row in queue_plan.repair_candidates(self.db, 8)}, {WEEKLY_URL})

    def test_changed_source_pointer_and_recent_cooldown_fail_closed(self):
        self.db.execute("UPDATE ingestion_asset SET document_id='changed-sha' WHERE url=%s", (DAILY_URL,))
        self.assertNotIn(DAILY_URL, {row[0] for row in queue_plan.repair_candidates(self.db, 8)})
        self.db.execute("UPDATE ingestion_asset SET document_id=%s,checked_at=now()-interval '1 minute' WHERE url=%s",
                        (DAILY_SHA, DAILY_URL))
        self.assertNotIn(DAILY_URL, {row[0] for row in queue_plan.repair_candidates(self.db, 8)})
        self.db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '7 hours' WHERE url=%s", (DAILY_URL,))
        self.db.execute("UPDATE source_document SET source_url='https://example.invalid/wrong.pdf' WHERE id=%s", (DAILY_SHA,))
        self.assertNotIn(DAILY_URL, {row[0] for row in queue_plan.repair_candidates(self.db, 8)})


if __name__ == "__main__":
    unittest.main()

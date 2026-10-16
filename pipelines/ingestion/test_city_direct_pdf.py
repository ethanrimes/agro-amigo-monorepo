"""Source-bound direct city-PDF regression on disposable PostgreSQL."""

import datetime
import copy
import getpass
import hashlib
import io
import json
import os
import random
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import psycopg
import pdfplumber
from psycopg.types.json import Jsonb

from . import city_direct_pdf as subject
from . import city_exact_source_dispatch_v44_b as dispatcher
from . import city_reports, ocr, pdf_sources, queue_plan, reviewed_city_dates, worker

HERE = Path(__file__).parent / "testdata/city_direct_pdf_20240518"
NEXTDAY = Path(__file__).parent / "testdata/city_reviewed_dates_nextday"
URL = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-18may2024.pdf"
DAY = datetime.date(2024, 5, 18)
DID = "8b09cf35ef1f4506f164742f890ea13c3eb8c305bb2b40f7c08be715205fc471"
BODY = (HERE / (DID + ".pdf")).read_bytes()
assert hashlib.sha256(BODY).hexdigest() == DID

# These 37 dates are the bounded, already-discovered untouched pending assets
# captured before the routing change. They are not URLs created by ingestion.
DISCOVERED_DATE_STEMS = (
    "02nov2024", "04oct2025", "06abr2024", "07dic2024", "07sep2024",
    "09ago2025", "09mar2024", "09nov2024", "10ago2024", "11may2024",
    "12sep2025", "13jul2024", "13may2024", "14dic2024", "16mar2024",
    "16nov2024", "17ago2024", "18may2024", "19oct2024", "20jul2024",
    "20sep2025", "21dic2024", "21sep2024", "22jun2024", "23mar2024",
    "23nov2024", "24ago2024", "25mar2024", "26oct2024", "27jul2024",
    "27sep2025", "28dic2024", "28sep2024", "30nov2024", "31ago2024",
    "3ago2024", "6jul2024",
)
DIRECT_PREFIX = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-"
INDEX_CITY_LINKS = (
    ("Informes por ciudades", "25mar2024"),
    ("Informes por ciudades", "23mar2024"),
    ("Informes por ciudades", "16mar2024"),
    ("Informes por ciudades", "09mar2024"),
    ("Boletín regional Bogotá", "18may2024"),
    ("Boletín regional Bogotá", "13may2024"),
    ("Boletín regional Bogotá", "11may2024"),
)
NEXTDAY_CASES = tuple(
    review for review in json.loads((Path(__file__).parent / "reviewed_city_dates.json").read_text())["archives"]
    if review["archive_id"] in {
        "51c4a6fdf9440ffdf95daab2c8f81afe092f956f366dea493181604ef784855b",
        "584bc4da5ed1c9f5fa44cf93f7a2e1a8c2e2606616aa1bb7024e99db55e07dda",
        "563c1c05f36a3db36404d85ddefe974c595d0c4833ec8b485c14bde7cf7bf785",
    }
)


class DirectCityPdfDisposablePostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-direct-city-pg-", dir="/tmp"))
        cls.cluster = cls.directory / "data"
        cls.port = random.randrange(41000, 49000)
        try:
            subprocess.run(
                ["initdb", "-D", str(cls.cluster), "--auth=trust", "--no-locale", "--encoding=UTF8"],
                check=True, stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                ["pg_ctl", "-D", str(cls.cluster), "-l", str(cls.directory / "postgres.log"),
                 "-o", f'-k {cls.directory} -p {cls.port} -h ""', "-w", "start"],
                check=True, stdout=subprocess.DEVNULL,
            )
            cls.db = psycopg.connect(
                f"host={cls.directory} port={cls.port} dbname=postgres user={getpass.getuser()}",
                autocommit=True,
            )
            assert cls.db.info.host.startswith("/tmp/agro-direct-city-pg-")
            assert cls.db.execute("SELECT inet_server_addr()").fetchone() == (None,)
            cls.db.execute("SET search_path=pg_temp; SET statement_timeout='60s'")
            for statement in (
                "CREATE TEMP TABLE source_document(id text PRIMARY KEY,title text,publisher text,source_url text,media_type text,kind text,reference_period text,page_count integer,content bytea,metadata jsonb,retrieved_at timestamptz DEFAULT now())",
                "CREATE TEMP TABLE ingestion_asset(url text PRIMARY KEY,kind text,observed_on date,status text DEFAULT 'pending',processor_version text DEFAULT '',records integer DEFAULT 0,document_id text,checked_at timestamptz,discovered_at timestamptz DEFAULT now(),attempts integer DEFAULT 0,error text)",
                "CREATE TEMP TABLE source_archive_member(archive_id text,entry_name text,document_id text,PRIMARY KEY(archive_id,entry_name))",
                "CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text,records integer,PRIMARY KEY(document_id,processor_version,step))",
                "CREATE TEMP TABLE regional_price(document_id text,source_locator text,observed_on date,product_id text,product_name text,market_name text,category text,presentation text,quantity numeric,source_unit text,round integer,round_label text,min_price numeric,max_price numeric,unit text,min_unit_price numeric,max_unit_price numeric,source_page integer,PRIMARY KEY(document_id,source_locator))",
                "CREATE TEMP TABLE regional_classification(document_id text,source_locator text,category_path text[],PRIMARY KEY(document_id,source_locator))",
                "CREATE TEMP TABLE regional_price_product_correction(document_id text,source_locator text,corrected_product_id text,corrected_product_name text)",
                "CREATE TEMP TABLE city_pdf_publication_conflict(document_id text,archive_id text,entry_name text,processor_version text,native_sha256 text,stored_sha256 text,details jsonb,UNIQUE(document_id,processor_version))",
                "CREATE TEMP VIEW unresolved_city_pdf_publication_conflict AS SELECT * FROM city_pdf_publication_conflict",
                "CREATE TEMP VIEW published_regional_price AS SELECT r.* FROM regional_price r WHERE NOT EXISTS(SELECT 1 FROM city_pdf_publication_conflict c WHERE c.document_id=r.document_id)",
                "CREATE TEMP TABLE market(id text PRIMARY KEY,name text,city text,region text,municipality_id text)",
                "CREATE TEMP TABLE municipality(id text,name text,department text)",
                "CREATE TEMP TABLE product(id text PRIMARY KEY,name text,category text)",
                "CREATE TEMP TABLE source_ocr_task(document_id text,source_locator text,image_id text,source_kind text,source_page integer,status text DEFAULT 'pending',checked_at timestamptz,error text,PRIMARY KEY(document_id,source_locator))",
                "CREATE TEMP TABLE source_ocr_result(image_id text,version text,reading integer,result jsonb)",
                "CREATE TEMP TABLE source_pdf_page(document_id text,source_page integer)",
                "CREATE TEMP TABLE source_ocr_scan(document_id text,version text)",
                "CREATE TEMP TABLE official_source_review(document_id text,parser_version text,source_locator text,record jsonb)",
            ):
                cls.db.execute(statement)
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "db", None) is not None:
            cls.db.close()
        if getattr(cls, "cluster", None) is not None and cls.cluster.exists():
            subprocess.run(
                ["pg_ctl", "-D", str(cls.cluster), "-m", "fast", "-w", "stop"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        if getattr(cls, "directory", None) is not None:
            shutil.rmtree(cls.directory, ignore_errors=True)

    def setUp(self):
        self.db.execute("BEGIN")
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,observed_on,status,processor_version,records,document_id) "
            "VALUES(%s,%s,%s,'pending','',0,NULL)", (URL, subject.KIND, DAY),
        )

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def process(self, body=BODY, day=DAY):
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}), patch(
            "pipelines.ingestion.blob_archive.retain_original_blob", return_value=False,
        ), patch.object(subject, "extract_pages", return_value=0):
            return subject.process_direct_city_pdf(self.db, URL, body, day)

    def test_central_worker_discovery_retypes_saved_assets_and_processes_actual_pdf(self):
        self.assertEqual(len(DISCOVERED_DATE_STEMS), 37)
        self.db.execute("DELETE FROM ingestion_asset WHERE url=%s", (URL,))
        for stem in DISCOVERED_DATE_STEMS:
            url = DIRECT_PREFIX + stem + ".pdf"
            self.db.execute(
                "INSERT INTO ingestion_asset(url,kind,observed_on,status,processor_version,records,document_id,attempts) "
                "VALUES(%s,'daily-pdf',%s,'pending','',0,NULL,0)",
                (url, worker.date_from_text(url)),
            )
        official_links = [(label, DIRECT_PREFIX + stem + ".pdf") for label, stem in INDEX_CITY_LINKS]
        with patch.object(worker, "links", return_value=official_links):
            self.assertEqual(worker.discover_daily(self.db, "https://www.dane.gov.co/official-index"), 7)
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_asset WHERE kind='city-pdf'").fetchone(), (37,))
        self.assertEqual(worker.asset_parser_version("city-pdf", URL), subject.VERSION)
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}
        ), patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=False), patch.object(
            worker, "fetch_asset", return_value=BODY,
        ), patch.object(subject, "extract_pages", return_value=0):
            self.assertEqual(worker.process_asset(self.db, URL, "city-pdf", DAY), 200)
        self.assertEqual(self.db.execute("SELECT status,records,document_id FROM ingestion_asset WHERE url=%s", (URL,)).fetchone(), ("complete", 200, DID))
        self.assertEqual(self.db.execute("SELECT count(*) FROM product").fetchone()[0] > 0, True)
        self.assertEqual(self.db.execute("SELECT count(*) FROM market").fetchone()[0] > 0, True)
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (200,))
        self.db.execute("INSERT INTO source_pdf_page(document_id,source_page) VALUES(%s,1)", (DID,))
        with patch.object(
            worker, "fetch_asset", return_value=BODY,
        ):
            self.assertEqual(worker.process_asset(self.db, URL, "city-pdf", DAY), 0)
        self.db.execute("UPDATE regional_price SET min_price=min_price+1 WHERE document_id=%s AND source_locator=(SELECT min(source_locator) FROM regional_price WHERE document_id=%s)", (DID,DID))
        with patch.object(
            worker, "fetch_asset", return_value=BODY,
        ):
            with self.assertRaisesRegex(ValueError, "publication conflict"):
                worker.process_asset(self.db, URL, "city-pdf", DAY)
        self.assertEqual(self.db.execute("SELECT count(*) FROM city_pdf_publication_conflict WHERE document_id=%s", (DID,)).fetchone(), (1,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_regional_price WHERE document_id=%s", (DID,)).fetchone(), (0,))

    def test_central_ocr_drain_routes_direct_asset_to_whole_source_replay(self):
        visited = []
        def needs_only_page_two(page, text):
            return page.page_number == 2
        def queue_failed_page(db, did, locator, image, kind, number):
            visited.append(number)
            self.assertEqual((did, locator, kind), (DID, "PDF page 2", "city-pdf"))
            db.execute(
                "INSERT INTO source_ocr_task(document_id,source_locator,image_id,source_kind,source_page,status) "
                "VALUES(%s,%s,'test-image',%s,%s,'pending')",
                (did, locator, kind, number),
            )
            return True
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}), patch(
            "pipelines.ingestion.blob_archive.retain_original_blob", return_value=False,
        ), patch.object(subject, "extract_pages", return_value=0), patch.object(
            ocr, "needs_ocr", side_effect=needs_only_page_two,
        ), patch.object(ocr, "enqueue_image", side_effect=queue_failed_page):
            self.assertEqual(subject.process_direct_city_pdf(self.db, URL, BODY, DAY)["status"], "awaiting-ocr")
        self.assertEqual(visited, [2])

        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (0,))
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata) "
            "VALUES('test-image','test-image','DANE',%s,'image/png','extract',%s,NULL,%s,%s)",
            (URL, str(DAY), b'cached-test-image', Jsonb({"ingestion_kind": "ocr-image"})),
        )
        scheduled = [(DID, "PDF page 2", "test-image", "city-pdf", 2)]
        fake_reading = {"tables": [{"rows": [["source", "verified"]]}]}
        with patch.dict(
            os.environ, {"AzureWebJobsStorage": ""},
        ), patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=False), patch.object(
            subject, "extract_pages", return_value=0,
        ), patch.object(ocr, "needs_ocr", side_effect=needs_only_page_two), patch.object(
            pdf_sources, "verified_page", side_effect=lambda db, page, did, kind, number: page,
        ), patch.object(ocr, "retire_audited_decorative_pdf_pages", return_value=0), patch.object(
            ocr, "requeue_cached_typed_reviews", return_value={"checked": 0, "requeued_documents": 0, "requeued_tasks": 0},
        ), patch.object(ocr, "_priority_snapshot", return_value=(0, 0, 0, 40, 40, scheduled)), patch.object(
            ocr, "_reading_budget", return_value=([(fake_reading,), (fake_reading,)], 0, True),
        ), patch.object(ocr, "compare_typed_task_readings", return_value=True):
            result = ocr.drain(self.db, limit=1, scan_limit=0, document_id=DID, cached_only=True)
        self.assertEqual(result["processed"], 1)
        self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id=%s", (DID,)).fetchone(), ("published",))
        self.assertEqual(self.db.execute("SELECT status,records FROM ingestion_asset WHERE url=%s", (URL,)).fetchone(), ("complete", 200))
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (200,))
        self.assertEqual(visited, [2])

    def test_central_queue_historical_lane_selects_pending_direct_pdf(self):
        with patch.object(queue_plan, "expected_versions", return_value=Jsonb({"city-pdf": subject.VERSION})):
            selected = queue_plan.historical_candidates(self.db, limit=5)
        self.assertIn((URL, "city-pdf", DAY), selected)

    def test_official_direct_city_links_and_negative_daily_link(self):
        self.assertEqual(subject.linked_city_pdf_day(URL, "Boletín regional Bogotá"), DAY)
        observed = []
        for label, stem in INDEX_CITY_LINKS:
            url = DIRECT_PREFIX + stem + ".pdf"
            parsed = subject.linked_city_pdf_day(url, label)
            self.assertIsNotNone(parsed, url)
            observed.append(url)
        self.assertEqual(len(observed), 7)
        self.assertIsNone(subject.linked_city_pdf_day(URL, "Boletín diario"))
        self.assertIsNone(subject.linked_city_pdf_day(URL.replace("www.dane.gov.co", "example.com"), "Boletín regional Bogotá"))
        self.assertIsNone(subject.linked_city_pdf_day(URL.replace("regionales-", ""), "Boletín regional Bogotá"))
        self.assertIsNone(subject.linked_city_pdf_day(URL.replace("18may2024", "18may2099"), "Boletín regional Bogotá"))
        self.assertIsNone(subject.linked_city_pdf_day(URL.replace("regionales-18may2024", "21may2024"), "Boletín diario Bogotá"))
        self.assertIsNone(subject.linked_city_pdf_day(URL.replace("18may2024", "31feb2024"), "Boletín regional Bogotá"))
        older = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol-reg-07-09-2023.pdf"
        self.assertEqual(subject.linked_city_pdf_day(older, "Informes por ciudades"), datetime.date(2023, 9, 7))

    def test_atomic_queue_migrates_only_untouched_pending_daily_pdf(self):
        self.db.execute("UPDATE ingestion_asset SET kind='daily-pdf' WHERE url=%s", (URL,))
        self.assertTrue(subject.queue_linked_city_pdf(self.db, URL, DAY))
        self.assertEqual(self.db.execute("SELECT kind,status,document_id FROM ingestion_asset WHERE url=%s", (URL,)).fetchone(), ("city-pdf", "pending", None))
        self.assertTrue(subject.queue_linked_city_pdf(self.db, URL, DAY))
        self.db.execute("UPDATE ingestion_asset SET kind='daily-pdf',status='processed' WHERE url=%s", (URL,))
        self.assertFalse(subject.queue_linked_city_pdf(self.db, URL, DAY))
        self.db.execute("UPDATE ingestion_asset SET status='pending',document_id=%s WHERE url=%s", (DID, URL))
        self.assertFalse(subject.queue_linked_city_pdf(self.db, URL, DAY))
        self.db.execute("UPDATE ingestion_asset SET document_id=NULL,observed_on=%s WHERE url=%s", (DAY - datetime.timedelta(days=1), URL))
        self.assertFalse(subject.queue_linked_city_pdf(self.db, URL, DAY))
        fresh = URL.replace('18may2024', '19may2024')
        self.assertTrue(subject.queue_linked_city_pdf(self.db, fresh, DAY + datetime.timedelta(days=1)))
        self.assertEqual(self.db.execute("SELECT kind,status,records FROM ingestion_asset WHERE url=%s", (fresh,)).fetchone(), ("city-pdf", "pending", 0))

    def test_all_37_saved_misclassified_assets_migrate_without_guessing_urls(self):
        self.assertEqual(len(DISCOVERED_DATE_STEMS), 37)
        self.db.execute("DELETE FROM ingestion_asset WHERE url=%s", (URL,))
        by_url = {}
        for stem in DISCOVERED_DATE_STEMS:
            url = DIRECT_PREFIX + stem + ".pdf"
            day = worker.date_from_text(url)
            by_url[url] = day
            self.db.execute(
                "INSERT INTO ingestion_asset(url,kind,observed_on,status,processor_version,records,document_id,attempts) "
                "VALUES(%s,'daily-pdf',%s,'pending','',0,NULL,0)", (url, day),
            )
        self.assertEqual(subject.migrate_discovered_city_pdf_assets(self.db), 37)
        self.assertEqual(subject.migrate_discovered_city_pdf_assets(self.db), 0)
        self.assertEqual(subject.migrate_discovered_city_pdf_assets(self.db, limit=0), 0)
        self.assertEqual(subject.migrate_discovered_city_pdf_assets(self.db, limit=1000000), 0)
        rows = self.db.execute(
            "SELECT url,kind,observed_on,status,records,document_id,attempts "
            "FROM ingestion_asset ORDER BY url"
        ).fetchall()
        self.assertEqual(len(rows), 37)
        for url, kind, day, status, records, did, attempts in rows:
            self.assertEqual((kind, day, status, records, did, attempts),
                             ("city-pdf", by_url[url], "pending", 0, None, 0))
        # A malformed or mismatched recorded day is never silently retyped.
        wrong = URL.replace("18may2024", "18jun2024")
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,observed_on) VALUES(%s,'daily-pdf',%s)",
            (wrong, DAY),
        )
        self.assertEqual(subject.migrate_discovered_city_pdf_assets(self.db), 0)
        self.assertEqual(self.db.execute("SELECT kind FROM ingestion_asset WHERE url=%s", (wrong,)).fetchone(), ("daily-pdf",))
        invalid = URL.replace("18may2024", "31feb2024")
        self.db.execute("INSERT INTO ingestion_asset(url,kind,observed_on) VALUES(%s,'daily-pdf',%s)", (invalid, DAY))
        self.assertEqual(subject.migrate_discovered_city_pdf_assets(self.db), 0)
        self.assertEqual(self.db.execute("SELECT kind FROM ingestion_asset WHERE url=%s", (invalid,)).fetchone(), ("daily-pdf",))

    def test_worker_prearchived_handoff_and_completed_ocr_task_does_not_enter_zip_route(self):
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}), patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=False):
            did = worker.archive(self.db, URL, BODY, subject.KIND, DAY)
        self.assertEqual(did, DID)
        with patch.object(subject, "extract_pages", return_value=0), patch.object(worker, "archive", side_effect=AssertionError("double archival")):
            result = subject.process_direct_city_pdf(self.db, URL, BODY, DAY, archived_did=did)
        self.assertEqual(result["rows"], 200)
        self.assertEqual(subject.resume_after_ocr(self.db, DID), {"status": "complete", "rows": 200, "document_id": DID})
        self.db.execute("DELETE FROM ingestion_checkpoint WHERE document_id=%s", (DID,))
        with self.assertRaisesRegex(ValueError, "matching whole-source checkpoint"):
            subject.resume_after_ocr(self.db, DID)
        self.db.execute("UPDATE source_document SET source_url='https://wrong.invalid/original.pdf' WHERE id=%s", (DID,))
        with self.assertRaisesRegex(ValueError, "retained source identity"):
            subject.resume_after_ocr(self.db, DID)

    def test_full_native_publication_and_idempotent_replay(self):
        first = self.process()
        self.assertEqual(first, {"status": "complete", "rows": 200, "document_id": DID})
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (200,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_classification").fetchone(), (200,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_regional_price").fetchone(), (200,))
        self.assertEqual(self.db.execute("SELECT count(DISTINCT source_locator),count(DISTINCT round),count(DISTINCT source_page) FROM regional_price").fetchone(), (200, 2, 3))
        native = list(city_reports.parse_city_pdf(BODY, DAY))
        oracle = json.loads((HERE / "direct-pdf-full17-native.json").read_text())
        self.assertEqual(len(oracle), 200)
        self.assertTrue(all(len(row) == 17 for row in oracle))
        self.assertEqual(reviewed_city_dates.rows_digest(native), reviewed_city_dates.rows_digest(oracle))
        money = json.loads((HERE / "direct-pdf-money-cell-parity.json").read_text())
        self.assertEqual(len(money), 200)
        by_locator = {row[0]: row for row in native}
        for cell in money:
            self.assertTrue(cell["match"])
            source_min, source_max = (int(value.replace(".", "")) for value in cell["printed"])
            self.assertEqual((by_locator[cell["locator"]][11], by_locator[cell["locator"]][12]),
                             (source_min, source_max))
        stored = self.db.execute("SELECT source_locator,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page FROM regional_price WHERE document_id=%s", (DID,)).fetchall()
        self.assertEqual(reviewed_city_dates.rows_digest(native), reviewed_city_dates.rows_digest(stored))
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price r JOIN regional_classification c USING(document_id,source_locator) WHERE c.category_path=string_to_array(r.category,' > ')").fetchone(), (200,))
        self.assertEqual(self.db.execute("SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step=%s", (DID, subject.VERSION, subject.COMPLETE_STEP)).fetchone(), (200,))
        self.assertTrue(subject.completed_source_is_still_valid(self.db, URL, DAY, DID, 200))
        row = self.db.execute("SELECT source_url,media_type,metadata,page_count,content FROM source_document WHERE id=%s", (DID,)).fetchone()
        self.assertEqual(row[:2], (URL, "application/pdf"))
        self.assertEqual(row[2]["ingestion_kind"], "city-pdf")
        self.assertNotIn("parents", row[2])
        self.assertNotIn("archive_entry", row[2])
        self.assertEqual(row[3], 3)
        self.assertEqual(hashlib.sha256(bytes(row[4])).hexdigest(), DID)
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_archive_member").fetchone(), (0,))
        self.assertIsNone(subject.retained_replay(self.db, URL, DAY))
        self.assertEqual(self.process(), first)
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (200,))

    def test_retained_pending_resume_and_corrupt_pointer_fail_closed(self):
        self.process()
        self.db.execute("UPDATE ingestion_asset SET status='pending' WHERE url=%s", (URL,))
        self.db.execute("DELETE FROM ingestion_checkpoint")
        self.assertEqual(subject.retained_replay(self.db, URL, DAY), BODY)
        self.assertEqual(self.process(), {"status": "complete", "rows": 200, "document_id": DID})
        self.db.execute("UPDATE ingestion_asset SET status='pending' WHERE url=%s", (URL,))
        self.db.execute("DELETE FROM ingestion_checkpoint")
        self.db.execute("UPDATE source_document SET media_type='text/html' WHERE id=%s", (DID,))
        with self.assertRaisesRegex(ValueError, "retained source identity"):
            subject.retained_replay(self.db, URL, DAY)

    def test_reviewed_mutable_link_can_revalidate_but_source_binding_is_checked(self):
        self.process()
        for status in ("review", "failed"):
            self.db.execute("UPDATE ingestion_asset SET status=%s WHERE url=%s", (status, URL))
            self.assertIsNone(subject.retained_replay(self.db, URL, DAY))
        self.db.execute("UPDATE source_document SET source_url='https://wrong.invalid/source.pdf' WHERE id=%s", (DID,))
        with self.assertRaisesRegex(ValueError, "retained source identity"):
            subject.retained_replay(self.db, URL, DAY)

    def test_existing_wrong_price_blocks_whole_source(self):
        native = list(city_reports.parse_city_pdf(BODY, DAY))
        wrong = list(native[0])
        wrong[11] = wrong[11] + 1
        cols = city_reports._BULK_TABLES["regional_price"][0]
        self.db.execute(f"INSERT INTO regional_price({cols}) VALUES(" + ",".join(["%s"] * 18) + ")", (DID, *wrong))
        result = self.process()
        self.assertEqual(result["status"], "review")
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (1,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_regional_price").fetchone(), (0,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM city_pdf_publication_conflict").fetchone(), (1,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone(), (0,))

    def test_transaction_rollback_keeps_retained_source_and_no_partial_prices(self):
        original = city_reports._bulk_insert
        def fail_on_price(db, table, rows):
            if table == "regional_price":
                raise RuntimeError("private rollback probe")
            return original(db, table, rows)
        with patch.object(city_reports, "_bulk_insert", side_effect=fail_on_price):
            with self.assertRaisesRegex(RuntimeError, "private rollback probe"):
                self.process()
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_document WHERE id=%s", (DID,)).fetchone(), (1,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_classification").fetchone(), (0,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (0,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone(), (0,))

    def test_date_conflict_is_review_and_source_remains_exact(self):
        wrong_day = DAY - datetime.timedelta(days=1)
        self.db.execute("UPDATE ingestion_asset SET observed_on=%s WHERE url=%s", (wrong_day, URL))
        result = self.process(day=wrong_day)
        self.assertEqual(result["status"], "review")
        self.assertIn("date", result["error"].lower())
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (0,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_document WHERE id=%s", (DID,)).fetchone(), (1,))

    def test_same_url_revised_bytes_append_a_distinct_complete_document(self):
        self.assertEqual(self.process()["rows"], 200)
        revised = BODY + b"\n%publisher-revision-bytes-private-test\n"
        revised_id = hashlib.sha256(revised).hexdigest()
        self.assertNotEqual(revised_id, DID)
        self.assertEqual(self.process(body=revised)["rows"], 200)
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_document").fetchone(), (2,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (400,))
        self.assertEqual(self.db.execute("SELECT document_id FROM ingestion_asset WHERE url=%s", (URL,)).fetchone(), (revised_id,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone(), (2,))

    def test_only_failed_native_page_enters_ocr_then_whole_source_reconciles(self):
        seen = []
        def needs_ocr(page, text):
            return page.page_number == 2
        def enqueue_only_failed(db, did, locator, image, kind, number):
            seen.append(number)
            self.assertEqual((did, locator, kind), (DID, "PDF page 2", "city-pdf"))
            db.execute("INSERT INTO source_ocr_task(document_id,source_locator,image_id,source_kind,source_page,status) VALUES(%s,%s,'test-image',%s,%s,'pending')", (did, locator, kind, number))
            return True
        with patch.object(ocr, "needs_ocr", side_effect=needs_ocr), patch.object(ocr, "enqueue_image", side_effect=enqueue_only_failed):
            first = self.process()
        self.assertEqual(first["status"], "awaiting-ocr")
        self.assertEqual(seen, [2])
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (0,))
        self.assertEqual(subject.retained_replay(self.db, URL, DAY), BODY)
        self.db.execute("UPDATE source_ocr_task SET status='verified' WHERE document_id=%s", (DID,))
        def agreeing_page(db, page, did, kind, number):
            seen.append(number)
            return page
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}), patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=False), patch.object(subject, "extract_pages", return_value=0), patch.object(ocr, "needs_ocr", side_effect=needs_ocr), patch.object(pdf_sources, "verified_page", side_effect=agreeing_page):
            completed = subject.resume_after_ocr(self.db, DID)
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(seen, [2, 2])
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (200,))
        self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id=%s", (DID,)).fetchone(), ("published",))

    def test_three_reviewed_dates_whole_parent_replay_and_adversarial_bindings(self):
        self.assertEqual(len(json.loads((Path(__file__).parent / "reviewed_city_dates.json").read_text())["archives"]), 6)
        expected = {
            "2023-10-20": 1974,
            "2024-03-30": 875,
            "2024-05-17": 2034,
        }
        self.assertEqual(len(NEXTDAY_CASES), 3)
        self.db.execute("DELETE FROM ingestion_asset WHERE url=%s", (URL,))
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}), patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=False), patch("pipelines.ingestion.pdf_sources.extract_pages", return_value=0):
            for case in NEXTDAY_CASES:
                parent_bytes = (NEXTDAY / (case["archive_id"] + ".zip")).read_bytes()
                day = datetime.date.fromisoformat(case["archive_day"])
                assert hashlib.sha256(parent_bytes).hexdigest() == case["archive_id"]
                self.assertIsNone(reviewed_city_dates.reviewed_parent(parent_bytes, case["archive_id"], case["url"] + "-wrong", day))
                self.assertIsNone(reviewed_city_dates.reviewed_parent(parent_bytes + b"changed", case["archive_id"], case["url"], day))
                self.assertIsNone(reviewed_city_dates.reviewed_parent(parent_bytes, case["archive_id"], case["url"], day + datetime.timedelta(days=1)))
                parent = reviewed_city_dates.reviewed_parent(parent_bytes, case["archive_id"], case["url"], day)
                self.assertIsNotNone(parent)
                member = case["members"][0]
                with zipfile.ZipFile(io.BytesIO(parent_bytes)) as archive:
                    child_bytes = archive.read(member["entry_name"])
                self.assertEqual(reviewed_city_dates.reviewed_member(parent, member["entry_name"], child_bytes), member)
                self.assertIsNone(reviewed_city_dates.reviewed_member(parent, member["entry_name"], child_bytes + b"changed"))
                rows = list(city_reports.parse_city_pdf(child_bytes, datetime.date.fromisoformat(member["printed_day"])))
                reviewed_city_dates.validate_rows(member, rows)
                changed = list(rows[0])
                changed[11] += 1
                with self.assertRaisesRegex(ValueError, "native price grid changed"):
                    reviewed_city_dates.validate_rows(member, [changed, *rows[1:]])
                parent_id = worker.archive(self.db, case["url"], parent_bytes, "city-zip", day, register_alias=False)
                self.assertEqual(parent_id, case["archive_id"])
                self.db.execute("INSERT INTO ingestion_asset(url,kind,observed_on,status,processor_version,records,document_id) VALUES(%s,'city-zip',%s,'pending','',0,%s)", (case["url"], day, parent_id))
                version = worker.asset_parser_version("city-zip", case["url"])
                self.assertIn("reviewed-", version)
                self.assertEqual(dispatcher.retained_exact_city_zip(self.db, case["url"], "city-zip", version), parent_bytes)
                with self.assertRaises(city_reports.CityZipPartialReview) as caught:
                    city_reports.publish_city_zip(self.db, parent_bytes, parent_id, case["url"], day, processor_version=version)
                self.assertEqual(caught.exception.count, expected[case["archive_day"]])
                self.assertEqual(len(caught.exception.failures), 1)
                self.assertEqual(caught.exception.failures[0]["document_id"], member["document_id"])
                child_count = self.db.execute("SELECT count(*) FROM regional_price WHERE document_id=%s", (member["document_id"],)).fetchone()[0]
                self.assertEqual(child_count, member["rows"])
                self.assertEqual(self.db.execute("SELECT count(*) FROM regional_classification WHERE document_id=%s", (member["document_id"],)).fetchone(), (member["rows"],))
                self.assertEqual(self.db.execute("SELECT count(*) FROM city_pdf_publication_conflict WHERE document_id=%s", (member["document_id"],)).fetchone(), (0,))
                self.assertEqual(self.db.execute("SELECT count(*) FROM source_archive_member WHERE archive_id=%s AND document_id=%s", (parent_id, member["document_id"])).fetchone(), (1,))
                # The generic processor recognizes every other member under
                # the integrated registry without duplicating prices.
                with self.assertRaises(city_reports.CityZipPartialReview) as replay:
                    city_reports.publish_city_zip(self.db, parent_bytes, parent_id, case["url"], day, processor_version=version)
                self.assertEqual(replay.exception.count, expected[case["archive_day"]])
                self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price r JOIN source_archive_member m ON m.document_id=r.document_id WHERE m.archive_id=%s", (parent_id,)).fetchone(), (expected[case["archive_day"]],))
                self.db.execute("UPDATE ingestion_asset SET status='review',processor_version=%s,records=%s WHERE url=%s", (version, expected[case["archive_day"]], case["url"]))
                self.assertIsNone(dispatcher.retained_exact_city_zip(self.db, case["url"], "city-zip", version))
                step, step_records = self.db.execute("SELECT step,records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step LIKE 'city-member:%%' ORDER BY step LIMIT 1", (parent_id,version)).fetchone()
                self.db.execute("DELETE FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step=%s", (parent_id,version,step))
                self.assertEqual(dispatcher.retained_exact_city_zip(self.db, case["url"], "city-zip", version), parent_bytes)
                self.db.execute("INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) VALUES(%s,%s,%s,%s)", (parent_id,version,step,step_records))
                self.db.execute("UPDATE source_document SET media_type='text/html' WHERE id=%s", (parent_id,))
                with self.assertRaisesRegex(ValueError, "source binding changed"):
                    dispatcher.retained_exact_city_zip(self.db, case["url"], "city-zip", version)
                self.db.execute("UPDATE source_document SET media_type='application/zip' WHERE id=%s", (parent_id,))
                revised = parent_bytes + b"\nprivate-disposable-mutable-zip-revision\n"
                revised_id = worker.archive(self.db, case["url"], revised, "city-zip", day, register_alias=False)
                self.assertNotEqual(revised_id, parent_id)
                self.db.execute("UPDATE ingestion_asset SET document_id=%s,status='complete',records=0 WHERE url=%s", (revised_id,case["url"]))
                self.assertIsNone(dispatcher.retained_exact_city_zip(self.db, case["url"], "city-zip", version))
                with patch.object(
                    worker, "fetch_asset", side_effect=RuntimeError("publisher fetch reached"),
                ) as fetch_probe:
                    with self.assertRaisesRegex(RuntimeError, "publisher fetch reached"):
                        worker.process_asset(self.db, case["url"], "city-zip", day)
                    fetch_probe.assert_called_once_with(self.db, case["url"], force=False)
                self.db.execute("UPDATE source_document SET source_url='https://wrong.invalid/revision.zip' WHERE id=%s", (revised_id,))
                with self.assertRaisesRegex(ValueError, "source binding changed"):
                    dispatcher.retained_exact_city_zip(self.db, case["url"], "city-zip", version)
                self.db.execute("UPDATE source_document SET source_url=%s WHERE id=%s", (case["url"],revised_id))

    def test_two_failed_pages_stay_unpublished_until_both_ocr_pages_agree(self):
        queued = []
        def needs_ocr(page, text):
            return page.page_number in (2, 3)
        def enqueue(db, did, locator, image, kind, number):
            queued.append(number)
            db.execute("INSERT INTO source_ocr_task(document_id,source_locator,image_id,source_kind,source_page,status) VALUES(%s,%s,%s,%s,%s,'pending') ON CONFLICT DO NOTHING", (did, locator, f'test-image-{number}', kind, number))
            return True
        with patch.object(ocr, "needs_ocr", side_effect=needs_ocr), patch.object(ocr, "enqueue_image", side_effect=enqueue):
            self.assertEqual(self.process()["status"], "awaiting-ocr")
        self.assertEqual(queued, [2, 3])
        with pdfplumber.open(io.BytesIO(BODY)) as pdf:
            readings = {
                number: {"text": pdf.pages[number - 1].extract_text(), "tables": pdf.pages[number - 1].extract_tables(), "review_notes": []}
                for number in (2, 3)
            }
        wrong = copy.deepcopy(readings[2])
        wrong["tables"][0][5][3] = "1"
        self.db.execute("INSERT INTO source_ocr_result(image_id,version,reading,result) VALUES('test-image-2',%s,0,%s),('test-image-2',%s,1,%s)", (ocr.VERSION, Jsonb(readings[2]), ocr.VERSION, Jsonb(wrong)))
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}), patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=False), patch.object(subject, "extract_pages", return_value=0), patch.object(ocr, "needs_ocr", side_effect=needs_ocr), patch.object(ocr, "enqueue_image", side_effect=enqueue):
            self.assertEqual(subject.resume_after_ocr(self.db, DID)["status"], "awaiting-ocr")
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (0,))
        self.db.execute("UPDATE source_ocr_result SET result=%s WHERE image_id='test-image-2' AND reading=1", (Jsonb(readings[2]),))
        self.db.execute("UPDATE source_ocr_task SET status='verified' WHERE document_id=%s AND source_page=2", (DID,))
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}), patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=False), patch.object(subject, "extract_pages", return_value=0), patch.object(ocr, "needs_ocr", side_effect=needs_ocr), patch.object(ocr, "enqueue_image", side_effect=enqueue):
            self.assertEqual(subject.resume_after_ocr(self.db, DID)["status"], "awaiting-ocr")
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (0,))
        self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id=%s AND source_page=2", (DID,)).fetchone(), ("verified",))
        self.db.execute("INSERT INTO source_ocr_result(image_id,version,reading,result) VALUES('test-image-3',%s,0,%s),('test-image-3',%s,1,%s)", (ocr.VERSION, Jsonb(readings[3]), ocr.VERSION, Jsonb(readings[3])))
        self.db.execute("UPDATE source_ocr_task SET status='verified' WHERE document_id=%s AND source_page=3", (DID,))
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}), patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=False), patch.object(subject, "extract_pages", return_value=0), patch.object(ocr, "needs_ocr", side_effect=needs_ocr):
            self.assertEqual(subject.resume_after_ocr(self.db, DID)["status"], "complete")
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (200,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_task WHERE document_id=%s AND status='published'", (DID,)).fetchone(), (2,))


if __name__ == "__main__":
    unittest.main(verbosity=2)

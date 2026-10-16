"""Exact-pointer retained parser upgrades, without publisher HTTP or lost history."""

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

from .retained_pdf_upgrade import retained_pdf_upgrade
from . import worker

URL = "https://www.dane.gov.co/files/original.pdf"
DAY = date(2012, 6, 27)
BODY = (Path(__file__).parent / "testdata/daily_pdf_variation" /
        "da15a9fe32bec70592853c7c50d24a7500d68c743021d1e206a2f9c3854d21f2.pdf").read_bytes()
DID = hashlib.sha256(BODY).hexdigest()


class RetainedPDFUpgradePostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-retained-pdf-pg-", dir="/tmp"))
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
            assert str(cls.db.info.host).startswith("/tmp/agro-retained-pdf-pg-")
            cls.db.execute("SET search_path=pg_temp")
            cls.db.execute("""CREATE TEMP TABLE source_document(
                id text PRIMARY KEY,source_url text,kind text,media_type text,
                metadata jsonb,content bytea)""")
            cls.db.execute("""CREATE TEMP TABLE ingestion_asset(
                url text PRIMARY KEY,kind text,status text,processor_version text,
                document_id text,checked_at timestamptz,attempts integer DEFAULT 0,
                records integer DEFAULT 0,error text)""")
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
        self.db.execute("INSERT INTO source_document VALUES(%s,%s,'original','application/pdf',%s,%s)",
                        (DID, URL, Jsonb({"ingestion_kind": "monthly-pdf"}), BODY))
        self.db.execute("""INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id)
            VALUES(%s,'monthly-pdf','complete','monthly-pdf-v4',%s)""", (URL, DID))

    def test_exact_complete_outdated_original_is_replayed(self):
        self.assertEqual(retained_pdf_upgrade(self.db, URL, "monthly-pdf", "monthly-pdf-v5"), BODY)
        self.db.execute("UPDATE ingestion_asset SET processor_version=NULL")
        self.assertEqual(retained_pdf_upgrade(self.db, URL, "monthly-pdf", "monthly-pdf-v5"), BODY)

    def test_current_version_keeps_normal_http_refresh(self):
        self.db.execute("UPDATE ingestion_asset SET processor_version='monthly-pdf-v5'")
        self.assertIsNone(retained_pdf_upgrade(self.db, URL, "monthly-pdf", "monthly-pdf-v5"))
        with patch.object(worker, "fetch_asset", return_value=None) as fetch:
            self.assertEqual(worker._process_asset(self.db, URL, "monthly-pdf", DAY), 0)
        fetch.assert_called_once_with(self.db, URL, force=False)

    def test_daily_upgrade_has_the_same_original_guards(self):
        self.db.execute("UPDATE ingestion_asset SET kind='daily-pdf',processor_version='daily-pdf-v5'")
        self.db.execute("UPDATE source_document SET metadata=%s", (Jsonb({"ingestion_kind": "daily-pdf"}),))
        self.assertEqual(retained_pdf_upgrade(self.db, URL, "daily-pdf", "daily-pdf-v6"), BODY)
        self.db.execute("UPDATE ingestion_asset SET processor_version='daily-pdf-v6'")
        self.assertIsNone(retained_pdf_upgrade(self.db, URL, "daily-pdf", "daily-pdf-v6"))

    def test_pending_review_failed_and_ocr_paths_are_not_upgrades(self):
        for status in ("pending", "review", "failed", "awaiting-ocr", "processed", "archived"):
            with self.subTest(status=status):
                self.db.execute("UPDATE ingestion_asset SET status=%s", (status,))
                self.assertIsNone(retained_pdf_upgrade(self.db, URL, "monthly-pdf", "monthly-pdf-v5"))

    def test_changed_pointer_or_absent_pointer_is_not_recovered(self):
        for pointer in (None, "unknown-other-document"):
            with self.subTest(pointer=pointer):
                self.db.execute("UPDATE ingestion_asset SET document_id=%s", (pointer,))
                self.assertIsNone(retained_pdf_upgrade(self.db, URL, "monthly-pdf", "monthly-pdf-v5"))

    def test_source_url_kind_and_media_must_match_exactly(self):
        mutations = (
            ("source_url", "https://www.dane.gov.co/files/redirected.pdf"),
            ("kind", "extract"), ("media_type", "application/octet-stream"),
        )
        for column, value in mutations:
            with self.subTest(column=column):
                self.setUp()
                self.db.execute(f"UPDATE source_document SET {column}=%s", (value,))
                self.assertIsNone(retained_pdf_upgrade(self.db, URL, "monthly-pdf", "monthly-pdf-v5"))
        self.setUp()
        self.db.execute("UPDATE source_document SET metadata=%s", (Jsonb({"ingestion_kind": "daily-pdf"}),))
        self.assertIsNone(retained_pdf_upgrade(self.db, URL, "monthly-pdf", "monthly-pdf-v5"))
        self.assertIsNone(retained_pdf_upgrade(self.db, URL, "inputs-pdf", "inputs-pdf-v9"))

    def test_corrupt_selected_bytes_raise_without_replacing_original(self):
        self.db.execute("UPDATE source_document SET content=%s", (BODY + b"corrupted",))
        with patch.object(worker, "fetch_asset") as fetch:
            with self.assertRaisesRegex(ValueError, "invalid original SHA"):
                worker._process_asset(self.db, URL, "monthly-pdf", DAY)
        fetch.assert_not_called()
        self.assertEqual(self.db.execute("SELECT content FROM source_document").fetchone()[0], BODY + b"corrupted")
        self.assertEqual(self.db.execute("SELECT status,processor_version FROM ingestion_asset").fetchone(),
                         ("complete", "monthly-pdf-v4"))

    def test_wrong_pdf_signature_even_with_matching_hash_is_rejected(self):
        invalid = b"not-pdf"
        invalid_id = hashlib.sha256(invalid).hexdigest()
        self.db.execute("UPDATE source_document SET id=%s,content=%s", (invalid_id, invalid))
        self.db.execute("UPDATE ingestion_asset SET document_id=%s", (invalid_id,))
        with self.assertRaisesRegex(ValueError, "PDF signature"):
            retained_pdf_upgrade(self.db, URL, "monthly-pdf", "monthly-pdf-v5")

    def test_worker_publication_uses_retained_bytes_without_http(self):
        row = ("PDF page 1,table 1,row 6,col 2; monthly-pdf-v5", "dane-monthly-summary",
               DAY, "Ahuyama", "Bogotá", "kg", 775.0, -1.0, {})
        with patch.object(worker, "fetch_asset") as fetch, \
             patch.object(worker, "archive", return_value=DID) as archive, \
             patch("pipelines.ingestion.pdf_sources.extract_pages"), \
             patch("pipelines.ingestion.pdf_sources.parse_archived_price_pdf", return_value=[row]), \
             patch.object(worker, "save_rows", return_value=1), \
             patch.object(worker, "retire_monthly_pdf_v4_cells") as retire, \
             patch.object(worker, "project", return_value=0):
            self.assertEqual(worker.process_asset(self.db, URL, "monthly-pdf", DAY), 1)
        fetch.assert_not_called()
        archive.assert_called_once_with(self.db, URL, BODY, "monthly-pdf", DAY)
        retire.assert_called_once_with(self.db, DID)
        self.assertEqual(self.db.execute("SELECT status,processor_version,document_id FROM ingestion_asset").fetchone(),
                         ("complete", "monthly-pdf-v5", DID))
        self.assertEqual(self.db.execute("SELECT content FROM source_document").fetchone()[0], BODY)
        self.assertIsNone(retained_pdf_upgrade(self.db, URL, "monthly-pdf", "monthly-pdf-v5"))


if __name__ == "__main__":
    unittest.main()

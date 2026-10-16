"""Exact failed Sept 2016 daily original advances automatically without HTTP/OCR."""

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

from . import daily_recovery, queue_plan, worker


URL = worker.SEPT2016_RETAINED_URL
DID = worker.SEPT2016_RETAINED_SHA
DAY = date(2016, 9, 5)
BODY = (Path(__file__).parent / "testdata/daily_sept2016" / (DID + ".xls")).read_bytes()


class Sept2016RetainedAutomaticRepair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(BODY).hexdigest() == DID
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-sept2016-auto-pg-", dir="/tmp"))
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
            assert str(cls.db.info.host).startswith("/tmp/agro-sept2016-auto-pg-")
            cls.db.execute("SET search_path=pg_temp; SET statement_timeout='30s'")
            cls.db.execute("""CREATE TEMP TABLE ingestion_checkpoint(
                document_id text,processor_version text,step text,records integer DEFAULT 0,
                created_at timestamptz DEFAULT now(),PRIMARY KEY(document_id,processor_version,step))""")
            cls.db.execute("""CREATE TEMP TABLE source_document(
                id text PRIMARY KEY,source_url text,kind text,media_type text,
                metadata jsonb,content bytea,title text,publisher text,
                reference_period text,page_count integer)""")
            cls.db.execute("""CREATE TEMP TABLE ingestion_asset(
                url text PRIMARY KEY,kind text,status text,processor_version text,
                document_id text,observed_on date,checked_at timestamptz,
                attempts integer DEFAULT 0,records integer DEFAULT 0,error text)""")
            cls.db.execute("""CREATE TEMP TABLE historical_price(
                document_id text,source_locator text,price integer,
                series text,details jsonb,
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
        self.db.execute("TRUNCATE historical_price,ingestion_asset,source_document")
        self.db.execute("""INSERT INTO source_document
            (id,source_url,kind,media_type,metadata,content)
            VALUES(%s,%s,'original','application/vnd.ms-excel',%s,%s)""",
            (DID, URL, Jsonb({"ingestion_kind": "daily"}), BODY))
        self.db.execute("""INSERT INTO ingestion_asset
            (url,kind,status,processor_version,document_id,observed_on,checked_at,error)
            VALUES(%s,'daily','failed',%s,%s,%s,now()-interval '1 minute',%s)""",
            (URL, worker.parser_version("daily"), DID, DAY, worker.SEPT2016_RETAINED_ERROR))

    def test_current_version_suffix_and_exact_failed_original_win_crowded_lane(self):
        self.assertEqual(worker.asset_parser_version("daily", URL),
                         worker.parser_version("daily") + ":sept2016-native-date-v1")
        self.assertEqual(queue_plan.expected_versions().obj["url:" + URL],
                         worker.asset_parser_version("daily", URL))
        with self.db.cursor() as cur:
            with cur.copy("COPY ingestion_asset(url,kind,status,processor_version) FROM STDIN") as copy:
                for i in range(2409):
                    copy.write_row((f"https://example.invalid/unchecked-daily-{i}.xls", "daily",
                                    "pending", worker.parser_version("daily")))
        selected = queue_plan.repair_candidates(self.db, 8)
        self.assertEqual([row[0] for row in selected], [URL])
        self.db.execute("UPDATE ingestion_asset SET error='HTTP 429' WHERE url=%s", (URL,))
        self.assertEqual(queue_plan.repair_candidates(self.db, 8), [])
        self.assertFalse(worker.retained_reparse_during_host_cooldown(self.db, URL, "daily"))
        self.db.execute("UPDATE ingestion_asset SET error=%s,processor_version=%s WHERE url=%s",
                        (worker.SEPT2016_RETAINED_ERROR,
                         worker.asset_parser_version("daily", URL), URL))
        self.assertEqual(queue_plan.repair_candidates(self.db, 8), [])

    def test_pointer_kind_error_version_and_bytes_fail_closed(self):
        self.assertEqual(worker.retained_sept2016_daily_repair(self.db, URL, "daily"), BODY)
        self.assertTrue(worker.retained_reparse_during_host_cooldown(self.db, URL, "daily"))
        self.assertFalse(worker.retained_reparse_during_host_cooldown(self.db, URL + "-changed", "daily"))
        self.assertIsNone(worker.retained_sept2016_daily_repair(self.db, URL + "-changed", "daily"))
        self.assertIsNone(worker.retained_sept2016_daily_repair(self.db, URL, "daily-pdf"))
        for column, value in (("status", "review"), ("error", "HTTP 429"),
                              ("processor_version", worker.asset_parser_version("daily", URL)),
                              ("document_id", "changed-pointer"), ("kind", "daily-pdf")):
            with self.subTest(column=column):
                self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s", (value, URL))
                self.assertIsNone(worker.retained_sept2016_daily_repair(self.db, URL, "daily"))
                self.setUp()
        for column, value in (("source_url", URL + "-changed"), ("kind", "extract"),
                              ("media_type", "application/octet-stream"),
                              ("metadata", Jsonb({"ingestion_kind": "daily-pdf"}))):
            with self.subTest(column=column):
                self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s", (value, DID))
                self.assertIsNone(worker.retained_sept2016_daily_repair(self.db, URL, "daily"))
                self.setUp()
        self.db.execute("UPDATE source_document SET content=%s WHERE id=%s", (BODY + b"changed", DID))
        with self.assertRaisesRegex(ValueError, "original SHA mismatch"):
            worker.retained_sept2016_daily_repair(self.db, URL, "daily")
        self.assertTrue(worker.retained_reparse_during_host_cooldown(self.db, URL, "daily"))
        with patch.object(worker, "fetch_asset", side_effect=AssertionError("unexpected HTTP")) as fetch:
            with self.assertRaisesRegex(ValueError, "original SHA mismatch"):
                worker._process_asset(self.db, URL, "daily", DAY)
        fetch.assert_not_called()

    def test_native_398_rows_publish_from_retained_original_without_http_or_ocr(self):
        parsed = daily_recovery.parse_daily(BODY, DAY)
        self.assertEqual((len(parsed["rows"]), len(parsed["reviews"])), (398, 0))
        # This is the exact local-reparse predicate used by run() while an
        # unrelated source on the same DANE host has an active 429 cooldown.
        self.assertTrue(worker.retained_reparse_during_host_cooldown(self.db, URL, "daily"))

        def publish(db, body, did, url, day):
            self.assertEqual((body, did, url, day), (BODY, DID, URL, DAY))
            db.execute("UPDATE ingestion_asset SET status='complete',records=398,error=NULL WHERE url=%s", (URL,))
            return len(parsed["rows"])

        with patch.object(worker, "fetch_asset", side_effect=AssertionError("unexpected HTTP")) as fetch, \
             patch.object(worker, "archive", return_value=DID) as archive, \
             patch("pipelines.ingestion.ocr.scan_document", side_effect=AssertionError("unexpected OCR")) as scan, \
             patch("pipelines.ingestion.daily_publication.publish", side_effect=publish), \
             patch("pipelines.ingestion.query_publication.recover", return_value=None):
            self.assertEqual(worker.process_asset(self.db, URL, "daily", DAY), 398)
        fetch.assert_not_called()
        scan.assert_not_called()
        archive.assert_called_once_with(self.db, URL, BODY, "daily", DAY)
        self.assertEqual(self.db.execute(
            "SELECT status,processor_version,records FROM ingestion_asset WHERE url=%s", (URL,)).fetchone(),
            ("complete", worker.asset_parser_version("daily", URL), 398))
        self.assertEqual(self.db.execute("SELECT content FROM source_document WHERE id=%s", (DID,)).fetchone()[0], BODY)
        self.assertIsNone(worker.retained_sept2016_daily_repair(self.db, URL, "daily"))
        with patch.object(worker, "fetch_asset", return_value=None) as normal_fetch:
            self.assertEqual(worker.process_asset(self.db, URL, "daily", DAY), 0)
        normal_fetch.assert_called_once_with(self.db, URL, force=False)

    def test_publication_failure_keeps_retained_history_and_original(self):
        self.db.execute("INSERT INTO historical_price(document_id,source_locator,price) VALUES(%s,'literal old row',2450)", (DID,))
        with patch.object(worker, "fetch_asset", side_effect=AssertionError("unexpected HTTP")), \
             patch.object(worker, "archive", return_value=DID), \
             patch("pipelines.ingestion.ocr.scan_document", side_effect=AssertionError("unexpected OCR")), \
             patch("pipelines.ingestion.daily_publication.publish", side_effect=ValueError("invalid changed heading")):
            with self.assertRaisesRegex(ValueError, "invalid changed heading"):
                worker._process_asset(self.db, URL, "daily", DAY)
        self.assertEqual(self.db.execute("SELECT source_locator,price FROM historical_price").fetchone(),
                         ("literal old row", 2450))
        self.assertEqual(self.db.execute("SELECT content FROM source_document WHERE id=%s", (DID,)).fetchone()[0], BODY)


if __name__ == "__main__":
    unittest.main()

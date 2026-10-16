"""Exact retained native weekly repairs and decorative OCR review in TEMP PG."""

import hashlib
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import ocr, official_sources, queue_plan, worker
from .retained_pdf_upgrade import retained_pdf_upgrade


ORIGINALS = (
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_01abr_al_05abr_2023.pdf",
     "ec95dc1b92689e54b52000a621dc87bad18d54392522bce748a56ce6003688e0",
     "dane_weekly_2023_04_01_native_layout.pdf"),
    ("https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_09jul_al_15jul_2022.pdf",
     "2ab314d876e586aafd8017a50d26762a1a96cbb489a57cc45a51007d63158304",
     "dane_weekly_2022_07_09_native_layout.pdf"),
)
DATA = Path(__file__).parent / "testdata"


class ExactNativeRecoveryPostgres(unittest.TestCase):
    def setUp(self):
        dsn = os.environ.get("AGRO_REFERENCE_TEST_DSN")
        if not dsn:
            raise RuntimeError("Explicit private PostgreSQL DSN required")
        self.db = psycopg.connect(dsn, autocommit=True)
        self.addCleanup(self.db.close)
        if not str(self.db.info.host).startswith("/tmp/agro-"):
            raise RuntimeError("Private socket required")
        self.db.execute("SET search_path=pg_temp; SET statement_timeout='30s'")
        for table in ("source_document", "ingestion_asset", "source_ocr_task", "ingestion_checkpoint", "historical_price"):
            self.db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")

    def add_original(self, index=0):
        url, did, filename = ORIGINALS[index]
        body = (DATA / filename).read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), did)
        self.db.execute(
            """INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,
               reference_period,content,metadata)
               VALUES(%s,'DANE weekly','DANE',%s,'application/pdf','original',%s,%s,%s)""",
            (did, url, "2023-04-05" if index == 0 else "2022-07-15", body,
             Jsonb({"ingestion_kind": "dane-weekly-pdf"})),
        )
        self.db.execute(
            """INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,
               observed_on,checked_at,records) VALUES(%s,'dane-weekly-pdf','awaiting-ocr',
               'official-v2:dane-weekly-v23',%s,%s,now()-interval '7 hours',0)""",
            (url, did, "2023-04-05" if index == 0 else "2022-07-15"),
        )
        return url, did, body

    def test_both_exact_pending_originals_advance_without_source_http(self):
        for index in range(2):
            url, did, body = self.add_original(index)
            version = worker.asset_parser_version("dane-weekly-pdf", url)
            self.assertEqual(version, "official-v2:dane-weekly-v24:native-readable-layout-v1")
            self.assertEqual(retained_pdf_upgrade(self.db, url, "dane-weekly-pdf", version), body)
            self.assertTrue(worker.retained_reparse_during_host_cooldown(self.db, url, "dane-weekly-pdf"))
        # The bounded repair lane chooses one stale original per kind. Once the
        # first is complete, the other must advance rather than be stranded.
        selected = {row[0] for row in queue_plan.repair_candidates(self.db)}
        self.assertEqual(selected, {ORIGINALS[0][0]})
        self.db.execute("UPDATE ingestion_asset SET processor_version=%s WHERE url=%s",
                        (worker.asset_parser_version("dane-weekly-pdf", ORIGINALS[0][0]), ORIGINALS[0][0]))
        selected = {row[0] for row in queue_plan.repair_candidates(self.db)}
        self.assertEqual(selected, {ORIGINALS[1][0]})

    def test_changed_pointer_status_version_and_metadata_fail_closed(self):
        url, did, body = self.add_original()
        version = worker.asset_parser_version("dane-weekly-pdf", url)
        for column, value in (
            ("status", "failed"), ("records", 1), ("document_id", "other"),
            ("processor_version", version),
        ):
            with self.subTest(column=column):
                self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s", (value, url))
                self.assertIsNone(retained_pdf_upgrade(self.db, url, "dane-weekly-pdf", version))
                self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s",
                                ({"status":"awaiting-ocr", "records":0, "document_id":did,
                                  "processor_version":"official-v2:dane-weekly-v23"}[column], url))
        for column, value, original in (
            ("source_url", "https://example.invalid/other.pdf", url),
            ("media_type", "application/octet-stream", "application/pdf"),
            ("metadata", Jsonb({"ingestion_kind":"daily-pdf"}), Jsonb({"ingestion_kind":"dane-weekly-pdf"})),
        ):
            with self.subTest(column=column):
                self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s", (value, did))
                self.assertIsNone(retained_pdf_upgrade(self.db, url, "dane-weekly-pdf", version))
                self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s", (original, did))
        self.db.execute("UPDATE source_document SET content=%s WHERE id=%s", (body+b"changed", did))
        with self.assertRaisesRegex(ValueError, "invalid original SHA"):
            retained_pdf_upgrade(self.db, url, "dane-weekly-pdf", version)

    def test_worker_uses_retained_native_pdf_before_ocr_or_http(self):
        url, did, body = self.add_original()
        with (patch.object(worker, "fetch_asset") as fetch,
              patch.object(worker, "archive", return_value=did) as archive,
              patch.object(official_sources, "process", return_value=3629) as process):
            self.assertEqual(worker.process_asset(
                self.db, url, "dane-weekly-pdf", date(2023, 4, 5)), 3629)
        fetch.assert_not_called()
        archive.assert_called_once_with(self.db, url, body, "dane-weekly-pdf", date(2023, 4, 5))
        process.assert_called_once_with(self.db, body, did, url, "dane-weekly-pdf")
        self.assertEqual(self.db.execute(
            "SELECT status,records,document_id,processor_version FROM ingestion_asset WHERE url=%s", (url,)
        ).fetchone(), ("complete", 3629, did, worker.asset_parser_version("dane-weekly-pdf", url)))

    def test_decorative_review_is_page_only_and_preserves_parent(self):
        url, did, body = self.add_original()
        original_map = ocr.AUDITED_DECORATIVE_PDF_PAGES
        ocr.AUDITED_DECORATIVE_PDF_PAGES = ((did, url, "dane-weekly-pdf", 55),)
        self.addCleanup(setattr, ocr, "AUDITED_DECORATIVE_PDF_PAGES", original_map)
        for page in (55, 56):
            self.db.execute(
                "INSERT INTO source_ocr_task(document_id,source_locator,image_id,source_kind,source_page,status) "
                "VALUES(%s,%s,%s,'dane-weekly-pdf',%s,'pending')",
                (did, f"PDF page {page}", did, page),
            )
        self.assertEqual(ocr.retire_audited_decorative_pdf_pages(self.db), 1)
        self.assertEqual(ocr.retire_audited_decorative_pdf_pages(self.db), 0)
        rows = self.db.execute("SELECT source_page,status,error FROM source_ocr_task ORDER BY source_page").fetchall()
        self.assertEqual([(r[0],r[1]) for r in rows], [(55,"review"),(56,"pending")])
        self.assertIn("Other pages and source publication remain pending", rows[0][2])
        self.assertEqual(self.db.execute("SELECT status,records FROM ingestion_asset WHERE url=%s", (url,)).fetchone(), ("awaiting-ocr",0))
        self.db.execute("UPDATE source_ocr_task SET status='pending' WHERE source_page=55")
        self.db.execute("UPDATE source_document SET content=%s WHERE id=%s", (body+b"changed",did))
        with self.assertRaisesRegex(ValueError, "original changed"):
            ocr.retire_audited_decorative_pdf_pages(self.db)
        self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE source_page=55").fetchone(), ("pending",))


if __name__ == "__main__":
    unittest.main()

"""Exact archived Corabastos PDF envelope and append-only scan replay."""
import hashlib
import io
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pdfplumber
import psycopg

from pipelines.ingestion import city_product_backfill as backfill
from pipelines.ingestion import city_product_corrections as corrections
from pipelines.ingestion import city_reports
from pipelines.ingestion.test_city_product_corrections import (
    PDF_SHA, REGIONAL_COLUMNS, SOURCE_URL,
)

HERE = Path(__file__).parent
DID = "373bd8410358196648af87471c9f6a061960b0d06e85ee612c1409e7635dd776"
URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "sipsa-16-08-2021.zip"
)
FIXTURE = HERE / "testdata/city_corabastos_20210816_rtfd_wrapped.pdf"


def original():
    body = FIXTURE.read_bytes()
    assert len(body) == 163897 and hashlib.sha256(body).hexdigest() == DID
    return body


def old_rows(body):
    with patch.object(city_reports, "_city_tables", side_effect=lambda page: page.extract_tables()):
        return list(city_reports.parse_city_pdf(body))


class WrappedCitySourceEvidence(unittest.TestCase):
    def test_exact_full_original_has_three_page_pdf_at_reviewed_offset_and_192_native_rows(self):
        body = original()
        self.assertEqual(body[:4], b"rtfd")
        self.assertEqual(body.find(b"%PDF"), 16384)
        self.assertEqual(body.rfind(b"%%EOF"), 163757)
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            self.assertEqual(len(pdf.pages), 3)
        rows = old_rows(body)
        self.assertEqual(len(rows), 192)
        self.assertEqual(len({row[0] for row in rows}), 192)
        self.assertEqual(
            corrections.verified_corrections(
                body, DID, URL, [dict(zip(REGIONAL_COLUMNS, row)) for row in rows]
            ), [],
        )


@unittest.skipUnless(os.environ.get("AGRO_CITY_CORRECTION_TEST_DSN"),
                     "explicit owned local PostgreSQL TEMP-only DSN required")
class WrappedCitySourcePostgres(unittest.TestCase):
    def setUp(self):
        from pipelines.ingestion.test_city_product_corrections import CityProductCorrectionPostgres
        fixture = CityProductCorrectionPostgres("test_hourly_scan_commits_corrections_and_checkpoint_once")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.db = fixture.db
        self.body = original()
        self.db.execute(
            "INSERT INTO source_document(id,source_url,metadata,content) VALUES(%s,%s,%s,%s)",
            (DID, URL, '{"ingestion_kind":"city-pdf"}', self.body),
        )
        rows = old_rows(self.body)
        self.assertEqual(len(rows), 192)
        for row in rows:
            self.db.execute("INSERT INTO regional_price VALUES(" + ",".join(["%s"] * 18) + ")", (DID, *row))
        self.db.execute(
            """INSERT INTO city_product_scan(document_id,scan_version,status,source_sha256,source_url)
            VALUES(%s,%s,'complete',%s,%s)""",
            (PDF_SHA, backfill.VERSION, PDF_SHA, SOURCE_URL),
        )
        self.db.execute(
            """INSERT INTO city_product_scan(document_id,scan_version,status,source_sha256,source_url,reason_code)
            VALUES(%s,%s,'review',%s,%s,%s)""",
            (DID, backfill.VERSION, DID, URL, backfill.WRAPPED_PDF_OLD_REASON),
        )

    def blob(self, body):
        blob = Mock()
        blob.get_blob_properties.return_value.size = len(body)
        blob.download_blob.return_value.readall.return_value = body
        service = Mock()
        service.get_blob_client.return_value = blob
        return service

    def test_actual_blob_loader_retry_then_exact_revision_resumes_without_raw_change(self):
        old = self.db.execute(
            "SELECT source_locator,xmin::text FROM regional_price WHERE document_id=%s ORDER BY source_locator",
            (DID,),
        ).fetchall()
        self.assertEqual(len(old), 192)
        with patch("azure.storage.blob.BlobServiceClient.from_connection_string",
                   return_value=self.blob(self.body)):
            with patch.object(backfill, "apply_corrections", side_effect=RuntimeError("injected before commit")):
                first = backfill.drain(self.db, storage_connection="test", limit=1)
            self.assertEqual((first["retry"], first["completed"]), (1, 0))
            with patch.object(backfill, "COOLDOWN_SECONDS", 0):
                second = backfill.drain(self.db, storage_connection="test", limit=1)
                third = backfill.drain(self.db, storage_connection="test", limit=1)
        self.assertEqual((second["completed"], second["review"], second["corrections"]), (1, 0, 0))
        self.assertEqual(third["selected"], 0)
        self.assertEqual(
            self.db.execute("SELECT scan_version,status FROM city_product_scan WHERE document_id=%s ORDER BY id",(DID,)).fetchall(),
            [(backfill.VERSION,"review"), (backfill.WRAPPED_PDF_RECOVERY_VERSION,"retry"),
             (backfill.WRAPPED_PDF_RECOVERY_VERSION,"complete")],
        )
        self.assertEqual(
            self.db.execute("SELECT source_locator,xmin::text FROM regional_price WHERE document_id=%s ORDER BY source_locator",(DID,)).fetchall(),
            old,
        )
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM regional_price_product_correction WHERE document_id=%s",(DID,)
        ).fetchone(), (0,))
        self.assertIsNone(backfill.select_integrity_recovery(self.db))

    def test_wrong_url_owner_media_and_any_changed_body_fail_closed(self):
        with patch("azure.storage.blob.BlobServiceClient.from_connection_string",
                   return_value=self.blob(self.body)):
            with self.assertRaisesRegex(ValueError,"reviewed PDF header"):
                corrections.load_original(self.db,DID,storage_connection="test",expected_source_url=URL+"?changed")
            self.db.execute("UPDATE source_document SET media_type='application/octet-stream' WHERE id=%s",(DID,))
            with self.assertRaisesRegex(ValueError,"reviewed PDF header"):
                corrections.load_original(self.db,DID,storage_connection="test",expected_source_url=URL)
            self.db.execute("UPDATE source_document SET media_type='application/pdf' WHERE id=%s",(DID,))
            self.db.execute("UPDATE source_document SET publisher='other' WHERE id=%s",(DID,))
            with self.assertRaisesRegex(ValueError,"reviewed PDF header"):
                corrections.load_original(self.db,DID,storage_connection="test",expected_source_url=URL)
            self.db.execute("UPDATE source_document SET publisher='DANE' WHERE id=%s",(DID,))
        changed = bytearray(self.body)
        changed[42] ^= 1
        with patch("azure.storage.blob.BlobServiceClient.from_connection_string",
                   return_value=self.blob(bytes(changed))):
            with self.assertRaisesRegex(ValueError,"SHA-256"):
                corrections.load_original(self.db,DID,storage_connection="test",expected_source_url=URL)
        with patch("azure.storage.blob.BlobServiceClient.from_connection_string",
                   return_value=self.blob(self.body)):
            with self.assertRaisesRegex(ValueError,"provenance"):
                corrections.load_original(None,DID,storage_connection="test",expected_source_url=URL)


if __name__ == "__main__":
    unittest.main()

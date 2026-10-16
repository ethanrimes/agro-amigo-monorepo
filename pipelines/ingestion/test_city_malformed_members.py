"""A real mixed DANE ZIP retains malformed children without losing valid peers."""

import io
import json
import os
import unittest
import zipfile
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import psycopg

from . import city_reports, worker
from .resumable_inputs import WorkDeferred
from . import test_city_publication as publication_tests


ORIGINAL = Path(__file__).parent / "testdata/city_regionales_06may2021_malformed.zip"
URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-06-05-2021.zip"
ZIP_SHA = "65f5c97a8c3809e5972549d312bb9537cfb9ada776c69bfc98408041537b7068"
HTML_NAME = "Cúcuta, Cenabastos-06-05-2021.pdf"
HTML_SHA = "9a07b684dff0f920fca0f0b1a5afe73b40d77f103c266ea0f324e44b7f44f84c"
BOGOTA_NAME = "Bogotá, D.C., Corabastos-06-05-2021.pdf"
BOGOTA_SHA = "7bb8c5ec81fa0a7a19884697bf5d56d999d9c6b4afccc29f865e43fe7c64e397"
DAY = date(2021, 5, 6)
REAL_ARCHIVE = worker.archive


@unittest.skipUnless(os.environ.get("AGRO_CITY_POSTGRES_TEST") == "1",
                     "Explicit private PostgreSQL city publication opt-in")
class CityMalformedMemberPostgres(unittest.TestCase):
    local_archive = staticmethod(publication_tests.CityPublicationPostgresTests.local_archive)

    def setUp(self):
        publication_tests.CityPublicationPostgresTests.setUp(self)
        self.assertIsNone(self.db.execute("SELECT inet_server_addr()").fetchone()[0])
        self.assertTrue(self.db.info.host.startswith("/tmp/agro-"))
        self.payload = ORIGINAL.read_bytes()
        self.assertEqual(len(self.payload), 177044)
        self.assertEqual(sha256(self.payload).hexdigest(), ZIP_SHA)
        with zipfile.ZipFile(io.BytesIO(self.payload)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(len(archive.infolist()), 12)
            self.html = archive.read(HTML_NAME)
            self.bogota = archive.read(BOGOTA_NAME)
            self.templates = [archive.read(m) for m in archive.namelist()
                              if m not in (HTML_NAME, BOGOTA_NAME)]
        self.assertEqual(sha256(self.html).hexdigest(), HTML_SHA)
        self.assertEqual(sha256(self.bogota).hexdigest(), BOGOTA_SHA)
        self.assertEqual(len(self.templates), 10)
        self.assertEqual({len(body) for body in self.templates}, {19541})
        self.assertEqual(len({sha256(body).hexdigest() for body in self.templates}), 10)
        self.assertTrue(self.html.lstrip().lower().startswith(b"<!doctype html"))
        self.assertEqual(len(list(city_reports.parse_city_pdf(self.bogota, DAY))), 119)

    def _publish(self, payload, url, *, version="city-v7-malformed-test"):
        did = REAL_ARCHIVE(self.db, url, payload, "city-zip", DAY)
        try:
            result = city_reports.publish_city_zip(
                self.db, payload, did, url, DAY, processor_version=version)
        except city_reports.CityZipPartialReview as exc:
            result = exc
        return did, result

    def _counts(self, did, version):
        return self.db.execute(
            "SELECT count(*) FILTER(WHERE step LIKE 'city-member:%%'),"
            "count(*) FILTER(WHERE step LIKE 'review:%%') "
            "FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s",
            (did, version),
        ).fetchone()

    def test_official_mixed_zip_publishes_only_119_real_bogota_ranges_and_reviews_11(self):
        with (patch.object(worker, "archive", side_effect=REAL_ARCHIVE),
              patch("pipelines.ingestion.blob_archive.retain_original_blob") as blob):
            did, result = self._publish(self.payload, URL)
            self.assertIsInstance(result, city_reports.CityZipPartialReview)
            self.assertEqual(result.count, 119)
            self.assertEqual(len(result.failures), 11)
            self.assertEqual(
                {f["filename"]: f["error_type"] for f in result.failures}[HTML_NAME],
                "ValueError",
            )
            self.assertEqual(
                sum(f["error_type"] == "SourceDateMismatch" for f in result.failures),
                10,
            )
            self.assertEqual(self._counts(did, "city-v7-malformed-test"), (1, 11))
            self.assertEqual(self.db.execute(
                "SELECT count(*) FROM source_archive_member WHERE archive_id=%s", (did,)
            ).fetchone()[0], 12)
            html_row = self.db.execute(
                "SELECT media_type,page_count,content,metadata FROM source_document WHERE id=%s",
                (HTML_SHA,),
            ).fetchone()
            self.assertEqual(html_row[0:2], ("text/html", None))
            self.assertEqual(bytes(html_row[2]), self.html)
            self.assertEqual(html_row[3]["original_filename"], HTML_NAME)
            self.assertEqual(html_row[3]["archive_entry"], HTML_NAME)
            self.assertIn(did, html_row[3]["parents"])
            self.assertIn((HTML_SHA, self.html, ".html", "text/html"),
                          [c.args for c in blob.call_args_list])
            self.assertEqual(self.db.execute(
                "SELECT count(*) FROM regional_price WHERE document_id=%s",
                (BOGOTA_SHA,),
            ).fetchone()[0], 119)
            self.assertEqual(self.db.execute(
                "SELECT count(*) FROM regional_classification WHERE document_id=%s",
                (BOGOTA_SHA,),
            ).fetchone()[0], 119)
            self.assertEqual(self.db.execute(
                "SELECT count(*) FROM published_regional_price WHERE document_id=%s",
                (BOGOTA_SHA,),
            ).fetchone()[0], 119)
            native = {r[0]: r for r in city_reports.parse_city_pdf(self.bogota, DAY)}
            columns = city_reports._BULK_TABLES["regional_price"][0].split(",")[1:]
            stored = self.db.execute(
                "SELECT " + ",".join(columns) + " FROM regional_price WHERE document_id=%s",
                (BOGOTA_SHA,),
            ).fetchall()
            self.assertEqual({r[0]: r for r in stored}, native)
            literal = self.db.execute(
                "SELECT product_name,market_name,presentation,quantity,source_unit,"
                "min_price,max_price FROM regional_price "
                "WHERE document_id=%s AND source_locator=%s",
                (BOGOTA_SHA, "PDF page 1,table 1,row 7,round 1"),
            ).fetchone()
            self.assertEqual(literal, ("Mandarina arrayana", "Bogotá, D.C., Corabastos",
                                       "Canastilla", Decimal(22), "Kilogramo",
                                       Decimal(105000), Decimal(115000)))
            self.assertEqual(self.db.execute(
                "SELECT count(*) FROM city_pdf_publication_conflict"
            ).fetchone()[0], 0)
            again_did, again = self._publish(self.payload, URL)
            self.assertEqual(again_did, did)
            self.assertIsInstance(again, city_reports.CityZipPartialReview)
            self.assertEqual((again.count, len(again.failures)), (119, 11))
            self.assertEqual(self._counts(did, "city-v7-malformed-test"), (1, 11))
            self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone()[0], 119)
            self.assertEqual(self.db.execute(
                "SELECT " + ",".join(columns) + " FROM regional_price WHERE document_id=%s",
                (BOGOTA_SHA,),
            ).fetchall(), stored)

    def test_malformed_html_and_pdf_after_valid_sibling_preserve_committed_prices(self):
        broken = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        entries = [(BOGOTA_NAME, self.bogota), (HTML_NAME, self.html),
                   ("Malformed structural PDF.pdf", broken)]
        payload = publication_tests.bundle(entries)
        url = "https://example.invalid/city-malformed-after-valid.zip"
        with (patch.object(worker, "archive", side_effect=REAL_ARCHIVE),
              patch("pipelines.ingestion.blob_archive.retain_original_blob")):
            did, result = self._publish(payload, url)
        self.assertIsInstance(result, city_reports.CityZipPartialReview)
        self.assertEqual(result.count, 119)
        self.assertEqual(len(result.failures), 2)
        self.assertEqual({f["error_type"] for f in result.failures},
                         {"ValueError", "PDFSyntaxError"})
        self.assertEqual(self._counts(did, "city-v7-malformed-test"), (1, 2))
        malformed_id = sha256(broken).hexdigest()
        self.assertEqual(self.db.execute(
            "SELECT media_type,page_count,content FROM source_document WHERE id=%s",
            (malformed_id,),
        ).fetchone(), ("application/pdf", None, broken))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM published_regional_price WHERE document_id=%s",
            (BOGOTA_SHA,),
        ).fetchone()[0], 119)

    def test_unrelated_programming_and_deadline_errors_propagate_without_false_review(self):
        payload = publication_tests.bundle([(BOGOTA_NAME, self.bogota)])
        url = "https://example.invalid/city-unrelated-error.zip"
        with (patch.object(worker, "archive", side_effect=REAL_ARCHIVE),
              patch("pipelines.ingestion.blob_archive.retain_original_blob"),
              patch.object(city_reports, "parse_archived_city_pdf",
                           side_effect=RuntimeError("programming bug"))):
            with self.assertRaisesRegex(RuntimeError, "programming bug"):
                self._publish(payload, url)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE step LIKE 'review:%%'"
        ).fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone()[0], 0)

        with (patch.object(worker, "archive", side_effect=REAL_ARCHIVE),
              patch("pipelines.ingestion.blob_archive.retain_original_blob"),
              patch.object(city_reports, "parse_archived_city_pdf",
                           side_effect=WorkDeferred("budget expired"))):
            with self.assertRaises(WorkDeferred):
                self._publish(payload, url, version="city-v7-deferred-test")
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE step LIKE 'review:%%'"
        ).fetchone()[0], 0)

        with (patch.object(worker, "archive", side_effect=REAL_ARCHIVE),
              patch("pipelines.ingestion.blob_archive.retain_original_blob"),
              patch.object(city_reports, "save_classifications",
                           side_effect=psycopg.ProgrammingError("database defect"))):
            with self.assertRaisesRegex(psycopg.ProgrammingError, "database defect"):
                self._publish(payload, url, version="city-v7-db-error-test")
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE step LIKE 'review:%%'"
        ).fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()

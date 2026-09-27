"""Resumable city publication in isolated PostgreSQL TEMP tables.

The opt-in runner snapshots production column constraints, never production
rows. Network/Blob archiving is replaced at its edge; native PDF parsing,
classification, COPY, checkpoints and transaction rollback run unchanged.
"""

import io
import os
import unittest
import zipfile
from datetime import date
from hashlib import sha256
from pathlib import Path
from unittest.mock import Mock, patch

from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb
from reportlab.pdfgen import canvas

from . import city_reports, worker
from .resumable_inputs import WorkDeferred
from .test_city_ocr_fallback import HEAD, TABLE, draw_table

TABLES = (
    "source_document",
    "source_archive_member",
    "source_pdf_page",
    "regional_price",
    "regional_classification",
    "market",
    "municipality",
    "product",
    "ingestion_checkpoint",
)
DAY = date(2026, 9, 7)
ROOT = Path(__file__).resolve().parents[2]


def native_pdf(name="Limón tahití"):
    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=(612, 792))
    c.setFont("Helvetica", 12)
    for index, line in enumerate(HEAD.splitlines()):
        c.drawString(36, 760 - 18 * index, line)
    table = [list(row) for row in TABLE]
    table[-1][0] = name
    # Preserve both rounds as independent source locators/price pairs.
    table[-1][-2:] = ["88.000", "89.000"]
    draw_table(c, table)
    c.save()
    return output.getvalue()


def bundle(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return output.getvalue()


@unittest.skipUnless(
    os.environ.get("AGRO_CITY_POSTGRES_TEST") == "1",
    "Explicit opt-in for isolated PostgreSQL TEMP-table city checks",
)
class CityPublicationPostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.autocommit)
        self.db.execute("SET search_path=pg_temp")
        self.db.execute("SET statement_timeout='30s'")
        for table in TABLES:
            self.db.execute(
                f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"
            )
            self.assertEqual(
                self.db.execute(
                    "SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)",
                    (table,),
                ).fetchone(),
                ("t",),
            )
        self.db.execute(
            "CREATE TRIGGER demo_window BEFORE INSERT OR UPDATE ON regional_price FOR EACH ROW EXECUTE FUNCTION public.enforce_demo_window()"
        )
        self.db.execute("""CREATE TEMP TABLE city_insert_attempt(document_id text,source_locator text);
            CREATE FUNCTION pg_temp.track_city_insert() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
              INSERT INTO pg_temp.city_insert_attempt VALUES(NEW.document_id,NEW.source_locator); RETURN NEW;
            END $$;
            CREATE TRIGGER track_insert BEFORE INSERT ON regional_price FOR EACH ROW EXECUTE FUNCTION pg_temp.track_city_insert();""")
        token = worker.RUN_DEADLINE.set(None)
        self.addCleanup(worker.RUN_DEADLINE.reset, token)
        self.archive = self.enterContext(
            patch.object(worker, "archive", side_effect=self.local_archive)
        )
        # OCR provider/network work is outside this SQL test; mixed native/OCR
        # reconstruction has a separate real-PDF regression suite.
        self.enterContext(patch("pipelines.ingestion.ocr.scan_document"))
        self.entries = [
            ("first.pdf", native_pdf()),
            ("second.pdf", native_pdf("Naranja valencia")),
        ]
        self.data = bundle(self.entries)
        self.did = self.local_archive(
            self.db, "https://www.dane.gov.co/test.zip", self.data, "city-zip"
        )

    @staticmethod
    def local_archive(db, url, data, kind, *args, filename=None, **kwargs):
        did = sha256(data).hexdigest()
        db.execute(
            """INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
            VALUES(%s,%s,'DANE',%s,%s,%s,'',%s,%s) ON CONFLICT DO NOTHING""",
            (
                did,
                filename or kind,
                url,
                "application/pdf" if kind == "city-pdf" else "application/zip",
                "original",
                data,
                Jsonb({"ingestion_kind": kind}),
            ),
        )
        return did

    def count(self, table):
        return self.db.execute(f"SELECT count(*) FROM pg_temp.{table}").fetchone()[0]

    def publish(self, day=DAY, version="city-test-v1"):
        return city_reports.publish_city_zip(
            self.db,
            self.data,
            self.did,
            "https://www.dane.gov.co/test.zip",
            day,
            processor_version=version,
        )

    def test_deadline_before_first_member_keeps_only_original_zip(self):
        worker.RUN_DEADLINE.set(150)
        with (
            patch.object(city_reports.time, "monotonic", return_value=200),
            self.assertRaises(WorkDeferred),
        ):
            self.publish()
        self.archive.assert_not_called()
        self.assertEqual(self.count("source_document"), 1)
        self.assertEqual(self.count("ingestion_checkpoint"), 0)
        self.assertEqual(self.count("regional_price"), 0)

    def test_deadline_resumes_remaining_member_without_repeating_completed_pdf(self):
        worker.RUN_DEADLINE.set(150)
        clock = Mock(side_effect=[100, 200])
        with (
            patch.object(city_reports.time, "monotonic", clock),
            self.assertRaises(WorkDeferred),
        ):
            self.publish()
        self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
        self.assertEqual(self.count("regional_price"), 2)
        self.assertEqual(self.count("regional_classification"), 2)
        self.assertEqual(self.count("ingestion_checkpoint"), 1)
        self.assertEqual(self.count("city_insert_attempt"), 2)
        self.db.rollback()
        worker.RUN_DEADLINE.set(None)
        self.archive.reset_mock()
        self.assertEqual(self.publish(), 4)
        self.assertEqual(self.archive.call_count, 1)
        self.assertEqual(self.archive.call_args.kwargs["filename"], "second.pdf")
        self.assertEqual(self.count("regional_price"), 4)
        self.assertEqual(self.count("regional_classification"), 4)
        self.assertEqual(self.count("city_insert_attempt"), 4)
        self.assertEqual(self.count("ingestion_checkpoint"), 2)
        self.assertEqual(self.count("source_archive_member"), 2)
        self.assertEqual(self.count("source_document"), 3)
        self.assertEqual(self.count("source_pdf_page"), 2)
        self.archive.reset_mock()
        self.assertEqual(self.publish(), 4)
        self.archive.assert_not_called()
        self.assertEqual(self.count("city_insert_attempt"), 4)

    def test_member_failure_rolls_back_prices_classification_and_success_checkpoint(
        self,
    ):
        original = city_reports._bulk_insert

        def fail_after_prices(db, table, rows):
            original(db, table, rows)
            if table == "regional_price":
                raise RuntimeError("Simulated crash after price insertion")

        with (
            patch.object(city_reports, "_bulk_insert", side_effect=fail_after_prices),
            self.assertRaisesRegex(RuntimeError, "Simulated crash"),
        ):
            self.publish()
        for table in (
            "regional_price",
            "regional_classification",
            "product",
            "market",
            "ingestion_checkpoint",
            "city_insert_attempt",
        ):
            self.assertEqual(self.count(table), 0, table)
        self.assertEqual(self.count("source_document"), 2)
        self.assertEqual(self.count("source_archive_member"), 1)
        self.assertEqual(self.count("source_pdf_page"), 1)
        self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
        self.assertEqual(self.publish(), 4)

    def test_new_parser_rechecks_but_never_rewrites_unchanged_prices(self):
        self.assertEqual(self.publish(), 4)
        before = self.db.execute(
            "SELECT document_id,source_locator,xmin::text FROM regional_price ORDER BY 1,2"
        ).fetchall()
        self.archive.reset_mock()
        self.assertEqual(self.publish(version="city-test-v2"), 4)
        self.assertEqual(self.archive.call_count, 2)
        self.assertEqual(self.count("city_insert_attempt"), 4)
        self.assertEqual(self.count("ingestion_checkpoint"), 4)
        self.assertEqual(
            before,
            self.db.execute(
                "SELECT document_id,source_locator,xmin::text FROM regional_price ORDER BY 1,2"
            ).fetchall(),
        )

    def test_different_archive_date_context_rechecks_and_retains_review_siblings(self):
        self.assertEqual(self.publish(), 4)
        self.archive.reset_mock()
        with self.assertRaises(city_reports.CityZipPartialReview) as failure:
            self.publish(day=date(2026, 9, 6))
        self.assertEqual(failure.exception.count, 0)
        self.assertEqual(len(failure.exception.failures), 2)
        self.assertEqual(self.archive.call_count, 2)
        self.assertEqual(self.count("regional_price"), 4)
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM ingestion_checkpoint WHERE step LIKE 'review:%'"
            ).fetchone(),
            (2,),
        )
        self.assertEqual(self.publish(), 4)

    def test_valid_member_survives_failed_peer_and_resume_checks_only_failed_peer(self):
        # A readable invalid PDF is still archived with native page evidence.
        bad = native_pdf()
        self.data = bundle([self.entries[0], ("bad.pdf", bad), self.entries[1]])
        self.did = self.local_archive(
            self.db, "https://www.dane.gov.co/test.zip", self.data, "city-zip"
        )
        native = city_reports.parse_archived_city_pdf

        def reject(db, data, did, day):
            if self.archive.call_args.kwargs.get("filename") == "bad.pdf":
                raise worker.SourceDateMismatch("Explicit fixture date conflict")
            return native(db, data, did, day)

        with patch.object(city_reports, "parse_archived_city_pdf", side_effect=reject):
            with self.assertRaises(city_reports.CityZipPartialReview) as failure:
                self.publish()
            self.assertEqual(failure.exception.count, 4)
            self.archive.reset_mock()
            with self.assertRaises(city_reports.CityZipPartialReview) as failure:
                self.publish()
            self.assertEqual(failure.exception.count, 4)
            self.assertEqual(self.archive.call_count, 1)
            self.assertEqual(self.archive.call_args.kwargs["filename"], "bad.pdf")
        self.assertEqual(self.count("regional_price"), 4)
        self.assertEqual(self.count("city_insert_attempt"), 4)

    def test_actual_september_26_archive_matches_every_native_price_and_original(self):
        path = (
            ROOT
            / "artifacts/automation-audit-2026-09-26/dane/originals/bol-SIPSADiario-regionales-26sep2026.zip"
        )
        if not path.exists():
            self.skipTest("Archived official September 26 city ZIP is not present")
        self.data = path.read_bytes()
        self.assertEqual(
            sha256(self.data).hexdigest(),
            "513d39ea9b6f300a4ab170661a3ab52041e32d72382e448195e53760e3183a13",
        )
        self.did = self.local_archive(
            self.db,
            "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-26sep2026.zip",
            self.data,
            "city-zip",
        )
        expected = []
        with zipfile.ZipFile(io.BytesIO(self.data)) as archive:
            for entry in archive.infolist():
                if entry.filename.lower().endswith(".pdf"):
                    data = archive.read(entry)
                    did = sha256(data).hexdigest()
                    expected.extend(
                        (did, *row)
                        for row in city_reports.parse_city_pdf(data, date(2026, 9, 26))
                    )
        self.assertEqual(len(expected), 202)
        self.assertEqual(self.publish(day=date(2026, 9, 26)), 202)
        columns = city_reports._BULK_TABLES["regional_price"][0]
        actual = self.db.execute(f"SELECT {columns} FROM regional_price").fetchall()
        self.assertEqual(sorted(actual), sorted(expected))
        self.assertEqual(self.count("regional_classification"), 202)
        self.assertGreater(self.count("source_pdf_page"), 0)
        for did, content in self.db.execute(
            "SELECT id,content FROM source_document"
        ).fetchall():
            self.assertEqual(sha256(content).hexdigest(), did)
        self.archive.reset_mock()
        self.assertEqual(self.publish(day=date(2026, 9, 26)), 202)
        self.archive.assert_not_called()
        self.assertEqual(self.count("city_insert_attempt"), 202)


if __name__ == "__main__":
    unittest.main()

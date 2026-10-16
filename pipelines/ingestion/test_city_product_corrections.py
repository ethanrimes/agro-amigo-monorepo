"""Exact archived PDF correction evidence and append-only SQL projection."""

import copy
import hashlib
import os
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import psycopg

from . import city_product_backfill as backfill
from . import city_reports
from .city_product_corrections import (
    REGIONAL_COLUMNS,
    apply_corrections,
    load_original,
    run,
    select_documents,
    verified_corrections,
)

HERE = Path(__file__).parent
PDF_SHA = "cc71efadfbc26dab14a6ae3e0bc6edabe9dee8ad2403bbf5ddad53e56c1335c4"
SOURCE_URL = (
    "https://www.dane.gov.co/files/operaciones/SIPSA/"
    "bol-SIPSADiario-regionales-29jul2024.zip"
)


def fixture():
    with zipfile.ZipFile(HERE / "testdata/city_joined_product_labels.zip") as z:
        body = z.read("papa_criolla_sucia.pdf")
    assert hashlib.sha256(body).hexdigest() == PDF_SHA
    with patch.object(city_reports, "_city_tables", side_effect=lambda page: page.extract_tables()):
        old = list(city_reports.parse_city_pdf(body))
    originals = [dict(zip(REGIONAL_COLUMNS, row)) for row in old]
    return body, originals


class CityProductCorrectionEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body, cls.originals = fixture()

    def test_native_pdf_changes_only_two_original_price_row_names(self):
        changes = verified_corrections(
            self.body, PDF_SHA, SOURCE_URL, self.originals
        )
        self.assertEqual(len(changes), 2)
        self.assertEqual(
            [item["source_locator"] for item in changes],
            [
                "PDF page 1,table 1,row 48,round 1",
                "PDF page 1,table 1,row 48,round 2",
            ],
        )
        for item in changes:
            self.assertEqual(item["old_product_name"], "Papacriollasucia")
            self.assertEqual(item["corrected_product_name"], "Papa criolla sucia")
            self.assertEqual(item["corrected_product_id"], "papa-criolla-sucia")
            self.assertEqual(item["source_sha256"], PDF_SHA)
            self.assertEqual(item["verification"]["method"], "native-pdf-glyph-spacing")

    def test_price_or_original_identity_mismatch_rejects_correction(self):
        for field, changed in (
            ("min_price", 1),
            ("source_unit", "litre"),
            ("observed_on", None),
            ("product_name", "Different original"),
        ):
            with self.subTest(field=field):
                rows = copy.deepcopy(self.originals)
                target = next(
                    row for row in rows if row["source_locator"].endswith("row 48,round 1")
                )
                target[field] = changed
                with self.assertRaisesRegex(ValueError, "differs"):
                    verified_corrections(self.body, PDF_SHA, SOURCE_URL, rows)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            verified_corrections(self.body, "0" * 64, SOURCE_URL, self.originals)

    def test_already_corrected_original_needs_no_overlay(self):
        rows = copy.deepcopy(self.originals)
        for row in rows:
            if "row 48," in row["source_locator"]:
                row["product_id"] = "papa-criolla-sucia"
                row["product_name"] = "Papa criolla sucia"
        self.assertEqual(
            verified_corrections(self.body, PDF_SHA, SOURCE_URL, rows), []
        )

    def test_unaffected_native_pdf_needs_no_correction(self):
        with zipfile.ZipFile(HERE / "testdata/city_regionales_05nov2025.zip") as z:
            body = z.read("Ancuya (Nariño)-05-11-2025.pdf")
        self.assertEqual(
            verified_corrections(
                body,
                hashlib.sha256(body).hexdigest(),
                "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-05nov2025.zip",
                [],
            ),
            [],
        )

    def test_category_heading_spacing_is_not_an_unmatched_price_row(self):
        body = (HERE / "testdata/city_las_flores_2024_07_30.pdf").read_bytes()
        did = "09e29b361217ee19f9f3d9837ade6ed1237efe88c3dd92bdcf3240ed1f00917f"
        self.assertEqual(hashlib.sha256(body).hexdigest(), did)
        rows = [dict(zip(REGIONAL_COLUMNS, row)) for row in city_reports.parse_city_pdf(body)]
        self.assertEqual(len(rows), 62)
        oil = next(row for row in rows if row["product_name"] == "Aceite soya")
        # Visually checked physical page 2: the category has no prices;
        # the following 3-litre bottle has the printed 21,500–22,000 range.
        self.assertEqual((oil["quantity"], oil["source_unit"], oil["min_price"], oil["max_price"]), (3, "Litro", 21500, 22000))
        self.assertEqual(verified_corrections(body, did,
            "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-30jul2024.zip", rows), [])

    def test_unmatched_product_with_price_cells_still_blocks_correction(self):
        with patch("pipelines.ingestion.city_product_corrections.parse_city_pdf", return_value=[]):
            with self.assertRaisesRegex(ValueError, "no parsed price locator"):
                verified_corrections(self.body, PDF_SHA, SOURCE_URL, self.originals)

    def test_document_limit_and_exact_hash_are_required(self):
        class NoDB:
            def execute(self, *_):
                raise AssertionError("invalid request reached database")

        with self.assertRaisesRegex(ValueError, "limit"):
            select_documents(NoDB(), limit=101)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            select_documents(NoDB(), limit=1, document_ids=("not-a-hash",))

    def test_blob_original_is_hash_verified_before_reparse(self):
        blob = Mock()
        blob.get_blob_properties.return_value.size = len(self.body)
        blob.download_blob.return_value.readall.return_value = self.body
        service = Mock()
        service.get_blob_client.return_value = blob
        with patch(
            "azure.storage.blob.BlobServiceClient.from_connection_string",
            return_value=service,
        ):
            body, storage = load_original(None, PDF_SHA, storage_connection="test")
            self.assertEqual((body, storage), (self.body, "azure-blob"))
            service.get_blob_client.assert_called_with("source-archive", PDF_SHA + ".pdf")
            blob.download_blob.return_value.readall.return_value = b"%PDF-other"
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                load_original(None, PDF_SHA, storage_connection="test")


@unittest.skipUnless(
    os.environ.get("AGRO_CITY_CORRECTION_TEST_DSN"),
    "explicit local PostgreSQL TEMP-only integration DSN required",
)
class CityProductCorrectionPostgres(unittest.TestCase):
    def setUp(self):
        self.db = psycopg.connect(
            os.environ["AGRO_CITY_CORRECTION_TEST_DSN"], autocommit=True
        )
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp")
        self.db.execute("CREATE TEMP TABLE source_document(id text PRIMARY KEY,source_url text,metadata jsonb,content bytea,kind text NOT NULL DEFAULT 'original',publisher text NOT NULL DEFAULT 'DANE',media_type text NOT NULL DEFAULT 'application/pdf')")
        self.db.execute("CREATE TEMP TABLE product(id text PRIMARY KEY,name text,category text)")
        self.db.execute(
            """CREATE TEMP TABLE regional_price(
            document_id text,source_locator text,observed_on date,product_id text,
            product_name text,market_name text,category text,presentation text,
            quantity numeric,source_unit text,round integer,round_label text,
            min_price numeric,max_price numeric,unit text,min_unit_price numeric,
            max_unit_price numeric,source_page integer,
            PRIMARY KEY(document_id,source_locator))"""
        )
        self.db.execute("CREATE INDEX ON regional_price(product_id,market_name,observed_on DESC)")
        self.db.execute(
            """CREATE FUNCTION pg_temp.prevent_history_removal() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable'; END $$"""
        )
        migration = (
            HERE / "migrations/20260928_022_city_product_corrections.sql"
        ).read_text()
        migration = migration.split("GRANT SELECT ON regional_price_product_correction")[0]
        migration = migration.replace(
            "CREATE TABLE IF NOT EXISTS regional_price_product_correction",
            "CREATE TEMP TABLE regional_price_product_correction",
        ).replace("CREATE OR REPLACE VIEW", "CREATE OR REPLACE TEMP VIEW")
        migration = migration.replace(
            "FUNCTION validate_regional_price_product_correction()",
            "FUNCTION pg_temp.validate_regional_price_product_correction()",
        ).replace(
            "FUNCTION prevent_history_removal()",
            "FUNCTION pg_temp.prevent_history_removal()",
        )
        self.db.execute(migration)
        self.db.execute(
            "CREATE TEMP TABLE ingestion_asset(url text PRIMARY KEY,status text,document_id text)"
        )
        scan_migration = (
            HERE / "migrations/20260928_023_city_product_scan.sql"
        ).read_text().split("GRANT SELECT ON city_product_scan")[0]
        scan_migration = scan_migration.replace(
            "CREATE TABLE IF NOT EXISTS city_product_scan",
            "CREATE TEMP TABLE city_product_scan",
        ).replace(
            "FUNCTION prevent_history_removal()",
            "FUNCTION pg_temp.prevent_history_removal()",
        )
        self.db.execute(scan_migration)
        self.body, self.originals = fixture()
        self.db.execute(
            "INSERT INTO source_document(id,source_url,metadata,content) VALUES(%s,%s,%s,%s)",
            (PDF_SHA, SOURCE_URL, '{"ingestion_kind":"city-pdf"}', self.body),
        )
        for row in self.originals:
            self.db.execute(
                "INSERT INTO regional_price VALUES(" + ",".join(["%s"] * 18) + ")",
                (PDF_SHA, *(row[name] for name in REGIONAL_COLUMNS)),
            )

    def test_exact_overlay_preserves_original_and_untouched_rows(self):
        columns = lambda relation: self.db.execute(
            """SELECT attname,atttypid,atttypmod FROM pg_attribute
            WHERE attrelid=to_regclass(%s) AND attnum>0 AND NOT attisdropped
            ORDER BY attnum""",
            (relation,),
        ).fetchall()
        self.assertEqual(columns("regional_price"), columns("resolved_regional_price"))
        candidates = verified_corrections(
            self.body, PDF_SHA, SOURCE_URL, self.originals
        )
        self.assertEqual(apply_corrections(self.db, candidates), 2)
        self.assertEqual(apply_corrections(self.db, candidates), 0)
        old = self.db.execute(
            "SELECT product_name FROM regional_price WHERE source_locator=%s",
            (candidates[0]["source_locator"],),
        ).fetchone()[0]
        resolved = self.db.execute(
            "SELECT product_name FROM resolved_regional_price WHERE source_locator=%s",
            (candidates[0]["source_locator"],),
        ).fetchone()[0]
        self.assertEqual((old, resolved), ("Papacriollasucia", "Papa criolla sucia"))
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM regional_price").fetchone(),
            self.db.execute("SELECT count(*) FROM resolved_regional_price").fetchone(),
        )
        untouched = next(
            row for row in self.originals if "row 48," not in row["source_locator"]
        )
        self.assertEqual(
            self.db.execute(
                "SELECT * FROM regional_price WHERE source_locator=%s",
                (untouched["source_locator"],),
            ).fetchone(),
            self.db.execute(
                "SELECT * FROM resolved_regional_price WHERE source_locator=%s",
                (untouched["source_locator"],),
            ).fetchone(),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT name FROM product WHERE id='papa-criolla-sucia'"
            ).fetchone(),
            ("Papa criolla sucia",),
        )

    def test_sql_rejects_wrong_old_identity_and_immutable_change(self):
        candidate = verified_corrections(
            self.body, PDF_SHA, SOURCE_URL, self.originals
        )[0]
        wrong = dict(candidate, old_product_name="Incorrect old name")
        with self.assertRaises(psycopg.Error):
            apply_corrections(self.db, [wrong])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM regional_price_product_correction").fetchone(),
            (0,),
        )
        apply_corrections(self.db, [candidate])
        with self.assertRaises(psycopg.Error):
            self.db.execute("UPDATE regional_price_product_correction SET source_url='changed'")
        with self.assertRaises(psycopg.Error):
            self.db.execute("DELETE FROM regional_price_product_correction")

    def test_bounded_dry_run_reports_without_database_writes(self):
        report = run(self.db, limit=1, document_ids=(PDF_SHA,))
        self.assertTrue(report["dry_run"])
        self.assertEqual((report["corrections"], report["inserted"]), (2, 0))
        self.assertEqual(report["documents"][0]["storage"], "database-archive")
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM regional_price_product_correction").fetchone(),
            (0,),
        )
        self.assertEqual(
            self.db.execute("SHOW default_transaction_read_only").fetchone(),
            ("on",),
        )

    def test_one_failed_document_does_not_block_next_keyset_member(self):
        with zipfile.ZipFile(HERE / "testdata/city_joined_product_labels.zip") as z:
            other_body = z.read("papa_parda_pastusa.pdf")
        other_sha = hashlib.sha256(other_body).hexdigest()
        with patch.object(city_reports, "_city_tables", side_effect=lambda page: page.extract_tables()):
            other_rows = list(city_reports.parse_city_pdf(other_body))
        other_url = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-24jun2024.zip"
        self.db.execute(
            "INSERT INTO source_document(id,source_url,metadata,content) VALUES(%s,%s,%s,%s)",
            (other_sha, other_url, '{"ingestion_kind":"city-pdf"}', other_body),
        )
        for row in other_rows:
            self.db.execute(
                "INSERT INTO regional_price VALUES(" + ",".join(["%s"] * 18) + ")",
                (other_sha, *row),
            )
        # The first document is no longer equal to its archived range.
        self.db.execute(
            """UPDATE regional_price SET min_price=min_price+1
            WHERE document_id=%s AND source_locator='PDF page 1,table 1,row 48,round 1'""",
            (other_sha,),
        )
        report = run(self.db, limit=2, document_ids=(PDF_SHA, other_sha), apply=True)
        self.assertEqual(report["review_errors"], 1)
        self.assertEqual(report["inserted"], 2)
        self.assertIsNone(report["next_after"])
        by_id = {entry["document_id"]: entry for entry in report["documents"]}
        self.assertEqual(by_id[other_sha]["status"], "review")
        self.assertEqual(by_id[other_sha]["inserted"], 0)
        self.assertEqual(by_id[PDF_SHA]["status"], "verified")
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM regional_price_product_correction WHERE document_id=%s",
                (other_sha,),
            ).fetchone(),
            (0,),
        )
        keyset = run(self.db, limit=2, after="", apply=True)
        self.assertEqual(keyset["next_after"], max(PDF_SHA, other_sha))
        self.assertEqual(keyset["review_errors"], 1)

    def test_failed_second_insert_rolls_back_first_for_same_pdf(self):
        candidates = verified_corrections(
            self.body, PDF_SHA, SOURCE_URL, self.originals
        )
        invalid = dict(candidates[1], source_page=2)
        with self.assertRaises(psycopg.Error):
            apply_corrections(self.db, [candidates[0], invalid])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM regional_price_product_correction").fetchone(),
            (0,),
        )

    def test_hourly_scan_commits_corrections_and_checkpoint_once(self):
        self.db.execute(
            "INSERT INTO ingestion_asset VALUES(%s,'complete',%s)",
            (SOURCE_URL, PDF_SHA),
        )
        with patch.object(backfill, "load_original", return_value=(self.body, "azure-blob")):
            first = backfill.drain(self.db, storage_connection="test", limit=1)
            second = backfill.drain(self.db, storage_connection="test", limit=1)
        self.assertEqual((first["completed"], first["corrections"]), (1, 2))
        self.assertEqual(first["errors"], [])
        self.assertEqual(second["errors"], [])
        self.assertEqual(second["selected"], 0)
        self.assertEqual(
            self.db.execute(
                "SELECT status,candidate_rows,inserted_rows FROM city_product_scan"
            ).fetchall(),
            [("complete", 2, 2)],
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM regional_price_product_correction").fetchone(),
            (2,),
        )

    def test_hourly_scan_review_isolated_and_transport_retry_cools_down(self):
        with zipfile.ZipFile(HERE / "testdata/city_joined_product_labels.zip") as z:
            other_body = z.read("papa_parda_pastusa.pdf")
        other_sha = hashlib.sha256(other_body).hexdigest()
        with patch.object(city_reports, "_city_tables", side_effect=lambda page: page.extract_tables()):
            other_rows = list(city_reports.parse_city_pdf(other_body))
        self.db.execute(
            "INSERT INTO source_document(id,source_url,metadata,content) VALUES(%s,%s,%s,%s)",
            (other_sha, SOURCE_URL + "?other", '{"ingestion_kind":"city-pdf"}', other_body),
        )
        for row in other_rows:
            self.db.execute(
                "INSERT INTO regional_price VALUES(" + ",".join(["%s"] * 18) + ")",
                (other_sha, *row),
            )
        # A source/price mismatch must not leave a partial correction for this PDF.
        self.db.execute(
            "UPDATE regional_price SET min_price=min_price+1 WHERE document_id=%s "
            "AND source_locator='PDF page 1,table 1,row 48,round 1'",
            (other_sha,),
        )
        bodies = {PDF_SHA: self.body, other_sha: other_body}
        with patch.object(
            backfill, "load_original",
            side_effect=lambda db, did, **kw: (bodies[did], "azure-blob"),
        ):
            report = backfill.drain(self.db, storage_connection="test", limit=2)
        self.assertEqual((report["completed"], report["review"]), (1, 1))
        self.assertEqual(
            dict(self.db.execute("SELECT document_id,status FROM city_product_scan").fetchall()),
            {PDF_SHA: "complete", other_sha: "review"},
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM regional_price_product_correction WHERE document_id=%s",
                (other_sha,),
            ).fetchone(),
            (0,),
        )
        with self.assertRaises(psycopg.Error):
            self.db.execute("DELETE FROM city_product_scan")

    def test_hourly_scan_transport_failure_is_retryable_after_cooldown(self):
        from azure.core.exceptions import ServiceRequestError

        with patch.object(
            backfill, "load_original", side_effect=ServiceRequestError("private endpoint")
        ):
            report = backfill.drain(self.db, storage_connection="test", limit=1)
        self.assertEqual((report["retry"], report["review"]), (1, 0))
        self.assertEqual(backfill.drain(self.db, storage_connection="test", limit=1)["selected"], 0)
        self.assertEqual(
            self.db.execute(*backfill.candidate_query(1, cooldown_seconds=0)).fetchall(),
            [(PDF_SHA, SOURCE_URL)],
        )

    def test_hourly_scan_statement_timeout_rolls_back_and_continues_next_original(self):
        with zipfile.ZipFile(HERE / "testdata/city_joined_product_labels.zip") as archive:
            other_body = archive.read("papa_parda_pastusa.pdf")
        other_sha = hashlib.sha256(other_body).hexdigest()
        other_url = SOURCE_URL + "?second-original"
        with patch.object(city_reports, "_city_tables", side_effect=lambda page: page.extract_tables()):
            other_rows = list(city_reports.parse_city_pdf(other_body))
        self.db.execute(
            "INSERT INTO source_document(id,source_url,metadata,content) VALUES(%s,%s,%s,%s)",
            (other_sha, other_url, '{"ingestion_kind":"city-pdf"}', other_body),
        )
        for row in other_rows:
            self.db.execute(
                "INSERT INTO regional_price VALUES(" + ",".join(["%s"] * 18) + ")",
                (other_sha, *row),
            )
        before_sources = self.db.execute(
            "SELECT id,content,xmin::text FROM source_document ORDER BY id"
        ).fetchall()
        before_prices = self.db.execute(
            "SELECT *,xmin::text FROM regional_price ORDER BY document_id,source_locator"
        ).fetchall()
        original_apply = backfill.apply_corrections
        calls = 0

        def timeout_after_first_inserts(db, corrections):
            nonlocal calls
            calls += 1
            inserted = original_apply(db, corrections)
            if calls == 1:
                db.execute("SELECT set_config('statement_timeout','20',true)")
                db.execute("SELECT pg_sleep(0.2)")
            return inserted

        bodies = {PDF_SHA: self.body, other_sha: other_body}
        with patch.object(backfill, "select_integrity_recovery", return_value=None), \
             patch.object(backfill, "select_candidates", return_value=(
                 [(PDF_SHA, SOURCE_URL), (other_sha, other_url)], None)), \
             patch.object(backfill, "load_original", side_effect=lambda db, did, **kw: (bodies[did], "azure-blob")), \
             patch.object(backfill, "apply_corrections", side_effect=timeout_after_first_inserts):
            report = backfill.drain(self.db, storage_connection="test", limit=2)
        self.assertEqual((report["retry"], report["completed"], report["review"]), (1, 1, 0))
        self.assertEqual(report["errors"], [{
            "document_id": PDF_SHA, "status": "retry", "reason": "QueryCanceled",
        }])
        self.assertEqual(dict(self.db.execute(
            "SELECT document_id,status FROM city_product_scan"
        ).fetchall()), {PDF_SHA: "retry", other_sha: "complete"})
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM regional_price_product_correction WHERE document_id=%s",
            (PDF_SHA,),
        ).fetchone(), (0,))
        self.assertGreater(self.db.execute(
            "SELECT count(*) FROM regional_price_product_correction WHERE document_id=%s",
            (other_sha,),
        ).fetchone()[0], 0)
        self.assertEqual(self.db.execute(
            "SELECT id,content,xmin::text FROM source_document ORDER BY id"
        ).fetchall(), before_sources)
        self.assertEqual(self.db.execute(
            "SELECT *,xmin::text FROM regional_price ORDER BY document_id,source_locator"
        ).fetchall(), before_prices)
        self.assertNotIn((PDF_SHA, SOURCE_URL),
                         self.db.execute(*backfill.candidate_query(2)).fetchall())
        self.assertIn((PDF_SHA, SOURCE_URL), self.db.execute(
            *backfill.candidate_query(2, cooldown_seconds=0)
        ).fetchall())

    def test_hourly_scan_connection_failures_still_propagate(self):
        for error in (psycopg.OperationalError("connection lost"),
                      psycopg.InterfaceError("connection closed")):
            with self.subTest(error=type(error).__name__), \
                 patch.object(backfill, "load_original", side_effect=error):
                with self.assertRaises(type(error)):
                    backfill.drain(self.db, storage_connection="test", limit=1)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM city_product_scan"
        ).fetchone(), (0,))


if __name__ == "__main__":
    unittest.main()

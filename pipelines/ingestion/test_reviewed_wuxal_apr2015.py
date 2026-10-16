"""Exact April 2015 Wuxal PDF identity repair, including real-PG publication."""

import hashlib
import json
import os
import unittest
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from unittest.mock import patch

from . import inputs, pdf_sources, worker
from .input_pdf_v17_replay import VERSION as GENERIC_INPUT_VERSION
from .reviewed_wuxal_apr2015 import (
    CATEGORY, COMMERCIAL_NAME, DAY, FULL_PDF_ROWS, MARKET_PRICES,
    OLD_VERSION, PAGE, PRESENTATION, PRINTED_HEADING, PRINTED_NAME,
    SHA256, URL, VERSION, parse_reviewed_wuxal_apr2015,
    retained_exact_wuxal_pdf,
    validate_reviewed_rows,
)

HERE = Path(__file__).parent
PDF = HERE / "testdata" / f"{SHA256}.pdf"
ORACLE = HERE / "testdata" / "wuxal_apr2015_full_market_vector.json"
ORACLE_SHA256 = "3cf0a91db736511a7f4343caa23fda98bdbd0978af5322e39daa72de84ee9edc"
XLS_SHA256 = "d1009999ad97fd1397713c5ada088d5f1698d44d19c13db99580fc831522dec5"


def require_private_temp_postgres(db):
    """Permit only the disposable local sockets used by isolated TEMP tests."""
    host = db.info.host or ""
    allowed = host.startswith("/tmp/agro-wuxal-") or host == "/tmp/agro-unified-catalog-pg-v24-20261004"
    if not allowed or f"host={host}" not in os.environ.get("DATABASE_URL", ""):
        raise AssertionError("Wuxal TEMP test requires its explicit disposable local PostgreSQL socket")
    if db.execute("SELECT inet_server_addr()").fetchone()[0] is not None:
        raise AssertionError("Wuxal TEMP test reached a network PostgreSQL server")


class ReviewedWuxalOriginal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = PDF.read_bytes()
        assert hashlib.sha256(cls.body).hexdigest() == SHA256
        oracle_bytes = ORACLE.read_bytes()
        assert hashlib.sha256(oracle_bytes).hexdigest() == ORACLE_SHA256
        cls.oracle = json.loads(oracle_bytes)
        cls.rows = parse_reviewed_wuxal_apr2015(cls.body, DAY, URL)

    def test_full_original_and_independent_workbook_vector(self):
        self.assertEqual(self.oracle["pdf_sha256"], SHA256)
        self.assertEqual(self.oracle["xlsx_sha256"], XLS_SHA256)
        self.assertEqual(self.oracle["pdf_heading"], PRINTED_HEADING)
        self.assertEqual(self.oracle["pdf_page"], PAGE)
        self.assertEqual(self.oracle["pdf_count"], 47)
        self.assertEqual(self.oracle["workbook_count"], 47)
        self.assertEqual(len(self.rows), FULL_PDF_ROWS)
        self.assertEqual({r[-1]["parser_version"] for r in self.rows}, {VERSION})
        expected = Counter(
            (r["market"], r["department"], r["printed_price"])
            for r in self.oracle["workbook_rows"]
        )
        self.assertEqual(expected, Counter(MARKET_PRICES))
        self.assertEqual(
            [r for r in self.oracle["workbook_rows"]
             if Decimal(r["raw_price"]).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
             != r["printed_price"]],
            [],
        )
        target = [r for r in self.rows if r[-1].get("printed_heading") == PRINTED_HEADING]
        self.assertEqual(len(target), 47)
        self.assertEqual({(r[3], r[5], r[-1]["category"]) for r in target},
                         {(COMMERCIAL_NAME, PRESENTATION, CATEGORY)})
        self.assertEqual(Counter((r[4], r[-1]["department"], int(r[6])) for r in target), expected)
        self.assertTrue(all(r[0].endswith("; " + VERSION) for r in target))
        self.assertTrue(all(r[-1]["printed_heading_lines"] == [PRINTED_HEADING] for r in target))
        self.assertEqual(len([r for r in self.rows if r[3] == PRINTED_NAME]), 0)
        self.assertTrue(all(r[3] != COMMERCIAL_NAME for r in self.rows if r not in target))

    def test_wrong_bytes_date_url_and_non_pdf_fail_closed(self):
        for body, day, url in (
            (self.body + b"x", DAY, URL),
            (b"not a PDF", DAY, URL),
            (self.body, DAY.replace(day=29), URL),
            (self.body, DAY, URL + "?changed=1"),
        ):
            with self.subTest(day=day, url=url, size=len(body)):
                with self.assertRaisesRegex(ValueError, "exact URL, date and PDF SHA"):
                    parse_reviewed_wuxal_apr2015(body, day, url)

    def test_direct_parser_override_above_v14_is_exact_source_only(self):
        for body, day, version in (
            (self.body, DAY, "inputs-pdf-v16"),
            (self.body + b"changed", DAY, VERSION),
            (b"%PDF-other-source", DAY, VERSION),
            (self.body, DAY.replace(day=29), VERSION),
        ):
            with self.subTest(day=day, version=version, size=len(body)):
                with self.assertRaisesRegex(ValueError, "exact reviewed original and date"):
                    list(pdf_sources.parse_input_pdf(body, day, parser_version=version))
        self.assertEqual(pdf_sources.INPUT_PDF_VERSION, OLD_VERSION)

    def test_changed_heading_market_money_package_or_rowcount_fail_closed(self):
        raw = [
            (*r[:3], PRINTED_NAME, *r[4:]) if r[-1].get("printed_heading") == PRINTED_HEADING
            else r for r in self.rows
        ]
        target_index = next(i for i, r in enumerate(raw) if r[-1].get("printed_heading") == PRINTED_HEADING)
        for changed in (
            lambda r: (*r[:-1], {**r[-1], "printed_heading": "other"}),
            lambda r: (*r[:4], "Wrong market", *r[5:]),
            lambda r: (*r[:6], r[6] + 1, *r[7:]),
            lambda r: (*r[:5], "2 litros", *r[6:]),
            lambda r: (*r[:2], DAY.replace(day=29), *r[3:]),
        ):
            mutation = raw.copy()
            mutation[target_index] = changed(mutation[target_index])
            with self.assertRaises(ValueError):
                validate_reviewed_rows(mutation)
        with self.assertRaises(ValueError):
            validate_reviewed_rows(raw[:-1])

    def test_other_wuxal_formulas_and_brands_remain_distinct(self):
        names = {r[3] for r in self.rows}
        for other in ("Wuxal", "Wuxal Calcio", "Wuxal Tapa Roja", "Wuxal 16-16-12"):
            self.assertNotEqual(other, COMMERCIAL_NAME)
        self.assertEqual(len([r for r in self.rows if r[-1].get("printed_heading") == PRINTED_HEADING
                              and r[3] == COMMERCIAL_NAME]), 47)
        self.assertNotIn(PRINTED_NAME, names)
        self.assertEqual(inputs.input_pdf_version_for_document(SHA256, URL), VERSION)
        with self.assertRaisesRegex(ValueError, "exact source URL"):
            inputs.input_pdf_version_for_document(SHA256, URL + "?changed=1")
        self.assertEqual(inputs.input_pdf_version_for_document("another-source"), GENERIC_INPUT_VERSION)


@unittest.skipUnless(
    os.environ.get("AGRO_WUXAL_APR2015_POSTGRES_TEST") == "1",
    "Explicit private PostgreSQL TEMP-only opt-in",
)
class ReviewedWuxalPublication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        body = PDF.read_bytes()
        assert hashlib.sha256(body).hexdigest() == SHA256
        cls.new_rows = parse_reviewed_wuxal_apr2015(body, DAY, URL)
        cls.old_rows = [
            (
                r[0].replace("; " + VERSION, "; " + OLD_VERSION),
                *r[1:3],
                PRINTED_NAME if r[-1].get("printed_heading") == PRINTED_HEADING else r[3],
                *r[4:-1],
                {**r[-1], "parser_version": OLD_VERSION},
            ) for r in cls.new_rows
        ]

    def setUp(self):
        from .test_input_pdf_publication import InputPDFPublication

        dsn = os.environ.get("DATABASE_URL", "")
        self.assertTrue("host=/tmp/agro-wuxal-" in dsn or
                        "host=/tmp/agro-unified-catalog-pg-v24-20261004" in dsn)
        InputPDFPublication.setUp(self)
        require_private_temp_postgres(self.db)
        self.db.execute("SET statement_timeout='180s'")
        self.db.execute("CREATE TEMP TABLE input_identity_alias(legacy_id text,id text,PRIMARY KEY(legacy_id,id))")
        self.db.execute("INSERT INTO source_document VALUES(%s,'2026-09-01T00:00:00Z'),(%s,'2026-09-02T00:00:00Z')",
                        (SHA256, XLS_SHA256))

    def _count(self, table, where="TRUE", params=()):
        return self.db.execute(f"SELECT count(*) FROM {table} WHERE {where}", params).fetchone()[0]

    def test_whole_pdf_transaction_rollback_resume_and_xls_precision(self):
        with patch.object(inputs, "input_pdf_version_for_document", return_value=OLD_VERSION):
            with self.db.transaction():
                self.assertEqual(worker.save_rows(self.db, SHA256, self.old_rows), FULL_PDF_ROWS)
                inputs.project_pdf_inputs(self.db, SHA256, source_url=URL)
        self.assertEqual(self._count("published_input_municipal_price", "name=%s", (PRINTED_NAME,)), 47)
        self.assertEqual(self._count("historical_price", "document_id=%s AND details->>'parser_version'=%s", (SHA256, OLD_VERSION)), FULL_PDF_ROWS)

        # The structured original has a fractional price and its own locator.
        xls = worker.record(
            "dane-inputs-municipal", DAY, COMMERCIAL_NAME, "Andes", PRESENTATION,
            33176.75, "1.2!row 20469",
            details={"sheet": "1.2", "category": CATEGORY, "presentation": PRESENTATION,
                     "department": "Antioquia", "municipality": "Andes", "brand": "", "ica": ""},
        )
        with self.db.transaction():
            worker.save_rows(self.db, XLS_SHA256, [xls])
            inputs.project_inputs(self.db, XLS_SHA256)
        xls_before = self.db.execute(
            "SELECT price,document_id,source_locator FROM published_input_municipal_price "
            "WHERE id='wuxal-tapa-negra-1-litro' AND department='Antioquia' AND municipality='Andes'"
        ).fetchone()
        self.assertEqual(xls_before, (Decimal("33176.75"), XLS_SHA256, "1.2!row 20469"))

        with self.assertRaisesRegex(RuntimeError, "forced post-COPY crash"):
            with self.db.transaction():
                worker.save_rows(self.db, SHA256, self.new_rows)
                inputs.project_pdf_inputs(self.db, SHA256, source_url=URL)
                raise RuntimeError("forced post-COPY crash")
        self.assertEqual(self._count("historical_price", "document_id=%s", (SHA256,)), FULL_PDF_ROWS)
        self.assertEqual(self._count("ingestion_checkpoint", "document_id=%s AND processor_version=%s", (SHA256, VERSION)), 0)
        self.assertEqual(self._count("published_input_municipal_price", "name=%s", (PRINTED_NAME,)), 47)
        self.assertEqual(self.db.execute(
            "SELECT price,document_id,source_locator FROM published_input_municipal_price "
            "WHERE id='wuxal-tapa-negra-1-litro' AND department='Antioquia' AND municipality='Andes'"
        ).fetchone(), xls_before)

        with self.db.transaction():
            self.assertEqual(worker.save_rows(self.db, SHA256, self.new_rows), FULL_PDF_ROWS)
            inputs.project_pdf_inputs(self.db, SHA256, source_url=URL)
        self.assertEqual(self._count("historical_price", "document_id=%s", (SHA256,)), 2 * FULL_PDF_ROWS)
        self.assertEqual(self._count("published_input_municipal_price", "name=%s", (PRINTED_NAME,)), 0)
        self.assertEqual(self._count("published_input_municipal_price", "name=%s", (COMMERCIAL_NAME,)), 47)

        self.assertEqual(self._count("input_municipal_price", "name=%s", (PRINTED_NAME,)), 47)
        self.assertEqual(self._count("historical_price", "document_id=%s AND product_name=%s AND details->>'parser_version'=%s", (SHA256, PRINTED_NAME, OLD_VERSION)), 47)
        self.assertEqual(self._count("historical_price", "document_id=%s AND product_name=%s AND details->>'parser_version'=%s", (SHA256, COMMERCIAL_NAME, VERSION)), 47)
        published = self.db.execute(
            "SELECT municipality,department,price,document_id,source_locator "
            "FROM published_input_municipal_price WHERE name=%s", (COMMERCIAL_NAME,)
        ).fetchall()
        self.assertEqual(
            Counter((market, department, int(Decimal(price).quantize(Decimal('1'), rounding=ROUND_HALF_UP)))
                    for market, department, price, _, _ in published),
            Counter(MARKET_PRICES),
        )
        self.assertTrue(all(did in (SHA256, XLS_SHA256) for _, _, _, did, _ in published))
        self.assertEqual(self._count("ingestion_checkpoint", "document_id=%s AND processor_version=%s AND step='inputs-pdf:published' AND records=%s", (SHA256, VERSION, FULL_PDF_ROWS)), 1)
        self.assertEqual(self.db.execute(
            "SELECT price,document_id,source_locator FROM published_input_municipal_price "
            "WHERE id='wuxal-tapa-negra-1-litro' AND department='Antioquia' AND municipality='Andes'"
        ).fetchone(), xls_before)
        self.assertEqual(self._count("input_identity_alias"), 0)

        before = self._count("input_attempt")
        with self.db.transaction():
            worker.save_rows(self.db, SHA256, self.new_rows)
            inputs.project_pdf_inputs(self.db, SHA256, source_url=URL)
        self.assertEqual(self._count("input_attempt"), before)
        self.assertEqual(self._count("historical_price", "document_id=%s", (SHA256,)), 2 * FULL_PDF_ROWS)
        self.assertEqual(self._count("ingestion_checkpoint", "document_id=%s AND processor_version=%s AND step='inputs-pdf:published'", (SHA256, VERSION)), 1)
        with patch.object(inputs, "input_pdf_version_for_document", return_value=OLD_VERSION):
            with self.db.transaction():
                inputs.project_pdf_inputs(self.db, SHA256, source_url=URL)
        self.assertEqual(self._count("published_input_municipal_price", "name=%s", (PRINTED_NAME,)), 0)
        with self.assertRaisesRegex(ValueError, "exact source URL"):
            inputs.project_pdf_inputs(self.db, SHA256, source_url=URL + "?alias=1")
        with self.assertRaisesRegex(RuntimeError, "rollback checkpoint probe"):
            with self.db.transaction():
                self.db.execute(
                    "INSERT INTO ingestion_checkpoint VALUES(%s,'inputs-pdf-v16','inputs-pdf:published',0)",
                    (SHA256,),
                )
                self.assertEqual(inputs.project_pdf_inputs(self.db, SHA256, source_url=URL), 0)
                raise RuntimeError("rollback checkpoint probe")
        self.assertEqual(self._count("published_input_municipal_price", "name=%s", (COMMERCIAL_NAME,)), 47)


@unittest.skipUnless(
    os.environ.get("AGRO_WUXAL_APR2015_POSTGRES_TEST") == "1",
    "Explicit private PostgreSQL TEMP-only opt-in",
)
class RetainedWuxalOriginal(unittest.TestCase):
    def setUp(self):
        dsn = os.environ.get("DATABASE_URL", "")
        self.assertTrue("host=/tmp/agro-wuxal-" in dsn or
                        "host=/tmp/agro-unified-catalog-pg-v24-20261004" in dsn)
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        require_private_temp_postgres(self.db)
        self.db.execute("SET search_path=pg_temp")
        self.db.execute("""CREATE TEMP TABLE source_document(
            id text PRIMARY KEY,content bytea,kind text,source_url text,
            media_type text,metadata jsonb);
          CREATE TEMP TABLE ingestion_asset(
            url text PRIMARY KEY,kind text,observed_on date,document_id text,
            status text,processor_version text);
          CREATE TEMP TABLE ingestion_checkpoint(
            document_id text,processor_version text,step text,records bigint,
            PRIMARY KEY(document_id,processor_version,step));""")
        self.body = PDF.read_bytes()
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), SHA256)
        self.db.execute(
            "INSERT INTO source_document VALUES(%s,%s,'original',%s,'application/pdf',"
            "'{\"ingestion_kind\":\"inputs-pdf\"}'::jsonb)",
            (SHA256, self.body, URL),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset VALUES(%s,'inputs-pdf',%s,%s,'complete',%s)",
            (URL, DAY, SHA256, OLD_VERSION),
        )

    def replay(self, url=URL, kind="inputs-pdf", version=VERSION):
        return retained_exact_wuxal_pdf(self.db, url, kind, version)

    def test_exact_outdated_and_partial_current_replay_without_network(self):
        with patch("requests.sessions.Session.request") as request:
            self.assertEqual(self.replay(), self.body)
            for status in ("complete", "review", "failed", "pending"):
                self.db.execute("UPDATE ingestion_asset SET status=%s,processor_version=%s",
                                (status, VERSION))
                self.assertEqual(self.replay(), self.body, status)
            self.db.execute("UPDATE ingestion_asset SET status='pending',processor_version=NULL")
            self.assertEqual(self.replay(), self.body)
            self.db.execute("INSERT INTO ingestion_checkpoint VALUES(%s,%s,'inputs-pdf:published',1)",
                            (SHA256, OLD_VERSION))
            self.assertEqual(self.replay(), self.body)
            request.assert_not_called()

    def test_checkpoint_and_higher_asset_version_stop_replay(self):
        self.db.execute("UPDATE ingestion_asset SET processor_version='inputs-pdf-v16'")
        self.assertIsNone(self.replay())
        self.db.execute("UPDATE ingestion_asset SET processor_version=%s", (VERSION,))
        for version in (VERSION, "inputs-pdf-v16"):
            self.db.execute("INSERT INTO ingestion_checkpoint VALUES(%s,%s,'inputs-pdf:published',6085)",
                            (SHA256, version))
            self.assertIsNone(self.replay())
            self.db.execute("DELETE FROM ingestion_checkpoint")
        self.assertEqual(self.replay(), self.body)

    def test_wrong_url_kind_version_day_pointer_media_metadata_or_status_is_ineligible(self):
        for args in ((URL + "?alias=1", "inputs-pdf", VERSION),
                     (URL, "daily-pdf", VERSION), (URL, "inputs-pdf", OLD_VERSION)):
            self.assertIsNone(self.replay(*args))
        changes = (
            ("ingestion_asset", "observed_on", DAY.replace(day=29), DAY),
            ("ingestion_asset", "document_id", "another-original", SHA256),
            ("ingestion_asset", "status", "processed", "complete"),
            ("source_document", "kind", "image", "original"),
            ("source_document", "source_url", URL + "?redirect=1", URL),
            ("source_document", "media_type", "text/plain", "application/pdf"),
            ("source_document", "metadata", '{"ingestion_kind":"daily-pdf"}',
             '{"ingestion_kind":"inputs-pdf"}'),
        )
        for table, column, wrong, correct in changes:
            with self.subTest(table=table, column=column):
                self.db.execute(f"UPDATE {table} SET {column}=%s", (wrong,))
                self.assertIsNone(self.replay())
                self.db.execute(f"UPDATE {table} SET {column}=%s", (correct,))
                self.assertEqual(self.replay(), self.body)

    def test_corrupt_retained_bytes_raise_instead_of_http_fallback(self):
        self.db.execute("UPDATE source_document SET content=%s", (self.body[:-1],))
        with self.assertRaisesRegex(ValueError, "source SHA"):
            self.replay()

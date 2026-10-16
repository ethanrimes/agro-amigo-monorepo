"""Full-schema lifecycle tests for untyped weekly XLS review."""
import hashlib
import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
from openpyxl import Workbook
from psycopg.types.json import Jsonb

from . import dane_weekly, official_sources, queue_plan, worker
from . import reviewed_weekly_native_context as weekly_native_context
from .reviewed_weekly_native_context import (
    ORIGINALS, REVIEW_LOCATOR, REVIEW_MARKER, inspect_original,
    GENERIC_REVIEW_LOCATOR, GENERIC_REVIEW_MARKER,
)


FIXTURES = Path(__file__).parent / "testdata" / "weekly_native_context_review"
EVIDENCE = json.loads((FIXTURES / "manifest.json").read_text())["source_workbooks"]

ALL_AUDITED_FIXTURES = FIXTURES / "all_audited_sources"
AUDIT = ALL_AUDITED_FIXTURES / "native_audit.json"
METADATA = ALL_AUDITED_FIXTURES / "source_metadata.json"

PDFS = {
    "nov01": (
        "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_01nov_07nov_2014.pdf",
        "9138aff02914b42392eb8233279240a36277c0575a592c2797dce0657509d182",
        "nov01.pdf",
    ),
    "nov08": (
        "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_08nov_14nov_2014.pdf",
        "ee0af42d6361ae3b07c2861bd6d047dc724e52deacfef8ba99245132e702d9ca",
        "nov08.pdf",
    ),
}


def media_type(body):
    return "application/vnd.ms-excel"


def native_typed_update(*, include_context=True):
    """Small genuine workbook for the mutable-URL normal-parser regression."""
    book = Workbook()
    sheet = book.active
    sheet.title = "Información Boletin"
    if include_context:
        sheet.append(["Semana del 8 al 14 de noviembre de 2014"])
        sheet.append(["Precios publicados en pesos por kilogramo"])
    else:
        sheet.append(["Boletín semanal actualizado"])
    sheet.append(["Cuadro 1. Mercados mayoristas. Precios de venta de frutas"])
    sheet.append(["Productos y mercados", "Precio mínimo", "Precio máximo", "Precio medio"])
    sheet.append(["Limón Tahití"])
    sheet.append(["Corabastos (Bogotá)", 1000, 1200, 1100, "Estable"])
    import io

    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def native_no_monetary_table():
    book = Workbook()
    sheet = book.active
    sheet.title = "Información Boletin"
    sheet.append(["Updated bulletin", "No supported monetary table"])
    import io

    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


@unittest.skipUnless(os.environ.get("AGRO_WEEKLY_NATIVE_CONTEXT_TEST_DSN"),
                     "Dedicated fresh full-schema weekly-native-context PostgreSQL DSN required")
class WeeklyNativeContextFullSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ["AGRO_WEEKLY_NATIVE_CONTEXT_TEST_DSN"]
        cls.db = psycopg.connect(dsn, autocommit=True)
        if (not str(cls.db.info.host).startswith("/tmp/agro-")
                or cls.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None
                or not cls.db.execute("SHOW server_version").fetchone()[0].startswith("16.")):
            cls.db.close()
            raise RuntimeError("Only the full-suite-owned Unix-socket PostgreSQL 16 database is allowed")
        cls.db.execute("SET ROLE agro_ingestor")
        if cls.db.execute("SELECT current_user").fetchone()[0] != "agro_ingestor":
            cls.db.close()
            raise RuntimeError("Weekly native test must use the canonical agro_ingestor role")
        cls.db.execute("SET TIME ZONE 'UTC'")
        cls.db.execute("SET statement_timeout='90s'")
        for table in ("source_document", "official_price_quote", "official_source_review",
                      "ingestion_checkpoint", "ingestion_asset", "source_ocr_task", "source_ocr_scan"):
            if cls.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                cls.db.close()
                raise RuntimeError("Dedicated weekly-native-context full-schema database must start empty")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        # The dedicated DB is reused across cases; rollback makes each case
        # independent while exercising the production worker role/grants.
        self.db.execute("BEGIN")
        self.db.execute("SET LOCAL statement_timeout='90s'")

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def _source(self, url, body, *, expected_metadata=None, doc_id=None, retained_url=None):
        did = doc_id or hashlib.sha256(body).hexdigest()
        filename = url.rsplit("/", 1)[-1]
        metadata = expected_metadata or {
            "retention": "permanent",
            "ingestion_kind": "dane-weekly-xlsx",
            "original_filename": filename,
        }
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
            "reference_period,content,metadata) VALUES(%s,%s,'DANE · SIPSA',%s,%s,'original',%s,%s,%s)",
            (did, filename, retained_url or url, media_type(body), "Serie histórica completa", body, Jsonb(metadata)),
        )
        return did

    def _archive_local(self, db, url, body, kind, day=None, **kwargs):
        did = hashlib.sha256(body).hexdigest()
        existing = db.execute("SELECT 1 FROM source_document WHERE id=%s", (did,)).fetchone()
        if not existing:
            if kind == "ocr-image":
                self.db.execute(
                    "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
                    "reference_period,content,metadata) VALUES(%s,'rendered-source.png',"
                    "'DANE · SIPSA',%s,'image/png','original','2014',%s,%s)",
                    (did, url, body, Jsonb({"retention": "permanent", "ingestion_kind": "ocr-image"})),
                )
            else:
                self._source(url, body, doc_id=did)
        return did

    def _asset(self, url, did, *, status="failed", version=None, checked_sql="now()-interval '2 days'"):
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,observed_on,status,document_id,records,error,"
            "processor_version,checked_at) VALUES(%s,'dane-weekly-xlsx',%s,%s,%s,0,%s,%s," + checked_sql + ")",
            (url, date(2014, 11, 7) if "nov01" in url else date(2014, 11, 14),
             status, did, "Weekly grouped workbook has no explicit period in cells or URL",
             version or worker.parser_version("dane-weekly-xlsx")),
        )

    def _process(self, url, body, day):
        with patch.object(worker, "fetch_asset", return_value=body), \
             patch.object(worker, "archive", side_effect=self._archive_local), \
             patch("pipelines.ingestion.ocr.scan_document") as scan:
            try:
                count = worker.process_asset(self.db, url, "dane-weekly-xlsx", day)
            except Exception as exc:
                exc.private_ocr_scan = scan
                raise
        return count, scan

    def _insert_pdf_and_quote(self, name):
        url, did, filename = PDFS[name]
        body = (FIXTURES / filename).read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), did)
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
            "reference_period,content,metadata) VALUES(%s,%s,'DANE · SIPSA',%s,'application/pdf',"
            "'original',%s,%s,%s)",
            (did, filename, url, "2014", body, Jsonb({"retention": "permanent", "ingestion_kind": "dane-weekly-pdf"})),
        )
        rows = dane_weekly.parse(body, url, "dane-weekly-pdf")
        row = next(row for row in rows if row.get("price") is not None)
        self.assertEqual(official_sources.publish_rows(self.db, [row], did, "dane-weekly-pdf"), 1)
        return did

    def test_a_two_independent_clean_sources_review_idempotently_without_ocr_or_prices(self):
        pdf_ids = [self._insert_pdf_and_quote(name) for name in ("nov01", "nov08")]
        pdf_before = {
            did: self.db.execute(
                "SELECT xmin::text,source_locator,parser_version,quote_key,product_id,observed_on,"
                "price,min_price,max_price,details FROM official_price_quote WHERE document_id=%s",
                (did,),
            ).fetchall()
            for did in pdf_ids
        }
        self.assertTrue(set(EVIDENCE).issubset(ORIGINALS))
        for index, url in enumerate(EVIDENCE):
            registry = ORIGINALS[url]
            expected = EVIDENCE[url]
            with self.subTest(url=url):
                body = (FIXTURES / ("nov01.xls" if index == 0 else "nov08.xls")).read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), expected["sha256"])
                self.assertEqual(len(body), expected["bytes"])
                for field in ("sha256", "bytes", "native_rows", "format"):
                    self.assertEqual(registry[field], expected[field])
                did = self._source(url, body)
                self._asset(url, did)
                original_before = self.db.execute(
                    "SELECT xmin::text,source_url,media_type,kind,reference_period,metadata,"
                    "octet_length(content),content FROM source_document WHERE id=%s", (did,)
                ).fetchone()
                self.assertEqual(inspect_original(body, url, did)["details"]["native_numeric_rows_untyped"],
                                 expected["native_rows"])
                day = date(2014, 11, 7) if index == 0 else date(2014, 11, 14)
                count, scan = self._process(url, body, day)
                self.assertEqual(count, 0)
                scan.assert_not_called()
                asset = self.db.execute(
                    "SELECT status,records,error,document_id,processor_version,attempts FROM ingestion_asset WHERE url=%s",
                    (url,),
                ).fetchone()
                version = worker.asset_parser_version("dane-weekly-xlsx", url)
                self.assertEqual(asset[:2], ("review", 0))
                self.assertEqual(asset[2:], (REVIEW_MARKER, did, version, 1))
                self.assertNotIn(url, [row[0] for row in queue_plan.backfill_candidates(self.db, 100)])
                review = self.db.execute(
                    "SELECT source_locator,parser_version,record,reason FROM official_source_review WHERE document_id=%s",
                    (did,),
                ).fetchall()
                self.assertEqual(len(review), 1)
                self.assertEqual(review[0][:2], (REVIEW_LOCATOR, version))
                self.assertEqual(review[0][3], REVIEW_MARKER)
                record = review[0][2]
                self.assertIsNone(record["price"])
                details = record["details"]
                self.assertEqual(details["original_sha256"], did)
                self.assertEqual(details["native_numeric_rows_untyped"], expected["native_rows"])
                self.assertEqual(details["typed_price_rows"], 0)
                self.assertIsNone(details["source_period"])
                self.assertIsNone(details["literal_unit_heading"])
                self.assertNotIn("unit", record)
                self.assertFalse(any(key in details for key in ("date", "period_start", "period_end", "currency")))
                self.assertEqual(self.db.execute(
                    "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)
                ).fetchone(), (0,))
                self.assertEqual(self.db.execute(
                    "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
                    "AND processor_version=%s AND step='official:complete'", (did, version)
                ).fetchone(), (0,))
                self.assertNotIn(url, [row[0] for row in queue_plan.backfill_candidates(self.db, 100)])
                original = self.db.execute(
                    "SELECT xmin::text,source_url,media_type,kind,reference_period,metadata,"
                    "octet_length(content),content FROM source_document WHERE id=%s", (did,)
                ).fetchone()
                self.assertEqual(original, original_before)
                self.assertEqual(hashlib.sha256(bytes(original[7])).hexdigest(), did)
                self.assertEqual(original[1], url)
                # Idempotent normal-worker retry, with no HTTP, OCR, or archive service.
                with patch.object(worker, "enqueue_failed_workbook", wraps=worker.enqueue_failed_workbook) as failure_gate:
                    count, scan = self._process(url, body, day)
                failure_gate.assert_not_called()
                self.assertEqual(count, 0)
                scan.assert_not_called()
                self.assertEqual(self.db.execute(
                    "SELECT attempts,error,status,processor_version FROM ingestion_asset WHERE url=%s",
                    (url,),
                ).fetchone(), (2, REVIEW_MARKER, "review", version))
                self.assertEqual(self.db.execute(
                    "SELECT count(*) FROM official_source_review WHERE document_id=%s", (did,)
                ).fetchone(), (1,))
                self.assertEqual(self.db.execute(
                    "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)
                ).fetchone(), (0,))
                self.db.execute(
                    "UPDATE ingestion_asset SET checked_at=now()-interval '31 days' WHERE url=%s",
                    (url,),
                )
                self.assertIn(url, [row[0] for row in queue_plan.backfill_candidates(self.db, 100)])
                self.db.execute(
                    "UPDATE ingestion_asset SET processor_version=%s,checked_at=now() WHERE url=%s",
                    (worker.parser_version("dane-weekly-xlsx"), url),
                )
                self.assertIn(url, [row[0] for row in queue_plan.backfill_candidates(self.db, 100)])
                self.assertEqual(self.db.execute(
                    "SELECT xmin::text,source_locator,parser_version,quote_key,product_id,observed_on,"
                    "price,min_price,max_price,details FROM official_price_quote WHERE document_id=%s",
                    (pdf_ids[index],),
                ).fetchall(), pdf_before[pdf_ids[index]])

    def test_b_prior_document_id_quote_history_blocks_review_without_mutating_old_rows(self):
        url = next(iter(EVIDENCE))
        body = (FIXTURES / "nov01.xls").read_bytes()
        did = hashlib.sha256(body).hexdigest()
        old_body = b"older immutable workbook bytes"
        old_id = hashlib.sha256(old_body).hexdigest()
        self._source(url, old_body, doc_id=old_id,
                     retained_url="https://archive.example.test/prior-weekly-original.xls")
        self._asset(url, old_id)
        self.db.execute(
            "INSERT INTO official_price_quote(document_id,source_locator,parser_version,quote_key,"
            "product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,"
            "price,details) VALUES(%s,'old native row','old-v1','old-key','old-product','Old product',"
            "'Vegetales','DANE','dane-weekly','wholesale','COP','kg','Bogotá',DATE '2014-11-07',1000,'{}')",
            (old_id,),
        )
        old_quote = self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,quote_key,product_id,observed_on,price,details "
            "FROM official_price_quote WHERE document_id=%s", (old_id,),
        ).fetchone()
        before_reviews = self.db.execute("SELECT count(*) FROM official_source_review").fetchone()
        before_cp = self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone()
        with self.assertRaisesRegex(ValueError, "blocked by prior quote history"):
            self._process(url, body, date(2014, 11, 7))
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,quote_key,product_id,observed_on,price,details "
            "FROM official_price_quote WHERE document_id=%s", (old_id,),
        ).fetchone(), old_quote)
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review").fetchone(), before_reviews)
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone(), before_cp)
        self.assertEqual(self.db.execute(
            "SELECT status,document_id FROM ingestion_asset WHERE url=%s", (url,)
        ).fetchone(), ("failed", did))
        self.assertEqual(self.db.execute(
            "SELECT content FROM source_document WHERE id=%s", (old_id,)
        ).fetchone(), (old_body,))

    def test_c_changed_readable_contextless_body_is_retained_untyped_and_can_refresh_later(self):
        url = next(iter(EVIDENCE))
        old_body = (FIXTURES / "nov01.xls").read_bytes()
        old_id = self._source(url, old_body)
        self._asset(url, old_id, status="review", version=worker.asset_parser_version("dane-weekly-xlsx", url))
        old_source_before = self.db.execute(
            "SELECT xmin::text,source_url,media_type,kind,reference_period,metadata,content "
            "FROM source_document WHERE id=%s", (old_id,),
        ).fetchone()
        old_reviews_before = self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,record,reason FROM official_source_review "
            "WHERE document_id=%s ORDER BY source_locator,parser_version", (old_id,),
        ).fetchall()
        old_checkpoints_before = self.db.execute(
            "SELECT xmin::text,processor_version,step,records FROM ingestion_checkpoint "
            "WHERE document_id=%s ORDER BY processor_version,step", (old_id,),
        ).fetchall()
        altered = native_typed_update(include_context=False)
        review_id = hashlib.sha256(altered).hexdigest()
        version = worker.asset_parser_version("dane-weekly-xlsx", url)
        with patch.object(worker, "enqueue_failed_workbook", wraps=worker.enqueue_failed_workbook) as failure_gate:
            count, scan = self._process(url, altered, date(2014, 11, 7))
        self.assertEqual(count, 0)
        failure_gate.assert_not_called()
        scan.assert_not_called()

        # The retained original remains byte-for-byte immutable; the changed
        # body is retained separately and represented only as an untyped review.
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,source_url,media_type,kind,reference_period,metadata,content "
            "FROM source_document WHERE id=%s", (old_id,),
        ).fetchone(), old_source_before)
        source = self.db.execute(
            "SELECT source_url,media_type,kind,reference_period,metadata,content "
            "FROM source_document WHERE id=%s", (review_id,),
        ).fetchone()
        self.assertEqual(source, (
            url, "application/vnd.ms-excel", "original", "Serie histórica completa",
            {"retention": "permanent", "ingestion_kind": "dane-weekly-xlsx",
             "original_filename": url.rsplit("/", 1)[-1]}, altered,
        ))
        asset = self.db.execute(
            "SELECT status,records,error,document_id,processor_version,attempts "
            "FROM ingestion_asset WHERE url=%s", (url,),
        ).fetchone()
        self.assertEqual(asset, ("review", 0, GENERIC_REVIEW_MARKER, review_id, version, 1))
        reviews = self.db.execute(
            "SELECT source_locator,parser_version,record,reason FROM official_source_review "
            "WHERE document_id=%s ORDER BY source_locator,parser_version", (review_id,),
        ).fetchall()
        self.assertEqual(len(reviews), 1)
        locator, review_version, record, reason = reviews[0]
        self.assertEqual((locator, review_version, reason),
                         (GENERIC_REVIEW_LOCATOR, version, GENERIC_REVIEW_MARKER))
        self.assertIsNone(record["price"])
        details = record["details"]
        self.assertEqual(details["original_sha256"], review_id)
        self.assertEqual(details["native_layout"], "grouped-min-max-mean")
        self.assertEqual(details["native_grouped_headers"], 1)
        self.assertEqual(details["native_numeric_rows_untyped"], 1)
        self.assertEqual(details["typed_price_rows"], 0)
        self.assertIsNone(details["source_period"])
        self.assertIsNone(details["literal_unit_heading"])
        self.assertNotIn("unit", record)
        self.assertFalse(any(key in details for key in ("date", "period_start", "period_end", "currency")))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=ANY(%s::text[])",
            ([old_id, review_id],),
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT processor_version,step,records FROM ingestion_checkpoint WHERE document_id=%s "
            "ORDER BY processor_version,step", (review_id,),
        ).fetchall(), [(version, "official:complete", 0)])
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,processor_version,step,records FROM ingestion_checkpoint "
            "WHERE document_id=%s ORDER BY processor_version,step", (old_id,),
        ).fetchall(), old_checkpoints_before)
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,record,reason FROM official_source_review "
            "WHERE document_id=%s ORDER BY source_locator,parser_version", (old_id,),
        ).fetchall(), old_reviews_before)
        self.assertNotIn(url, [row[0] for row in queue_plan.backfill_candidates(self.db, 100)])

        # A later valid workbook at this mutable URL follows ordinary native
        # publication while the earlier untyped review and both originals stay.
        corrected = native_typed_update(include_context=True)
        corrected_id = hashlib.sha256(corrected).hexdigest()
        count, scan = self._process(url, corrected, date(2014, 11, 14))
        self.assertEqual(count, 1)
        scan.assert_not_called()
        self.assertEqual(self.db.execute(
            "SELECT content FROM source_document WHERE id=%s", (review_id,),
        ).fetchone(), (altered,))
        self.assertEqual(self.db.execute(
            "SELECT source_url,content FROM source_document WHERE id=%s", (corrected_id,),
        ).fetchone(), (url, corrected))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s", (review_id,),
        ).fetchone(), (1,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (corrected_id,),
        ).fetchone(), (1,))
        self.assertEqual(self.db.execute(
            "SELECT product_name,unit,market,observed_on,price,min_price,max_price "
            "FROM official_price_quote WHERE document_id=%s", (corrected_id,),
        ).fetchone(), ("Limón Tahití", "kg", "Corabastos (Bogotá)", date(2014, 11, 14),
                      1100.0, 1000.0, 1200.0))

        # Unknown layouts still fail closed instead of entering the typed path.
        unknown = url + ".unknown-layout"
        self.assertIsNone(inspect_original(old_body, unknown, old_id))
        with self.assertRaisesRegex(ValueError, "no explicit period"):
            dane_weekly.parse_workbook(old_body, unknown)

    def test_d_retained_source_metadata_mismatch_fails_without_review_or_checkpoint(self):
        url = next(iter(EVIDENCE))
        body = (FIXTURES / "nov01.xls").read_bytes()
        did = hashlib.sha256(body).hexdigest()
        metadata = {
            "retention": "permanent",
            "ingestion_kind": "dane-weekly-xlsx",
            "original_filename": url.rsplit("/", 1)[-1],
            "unexpected_nested_field": {"value": "must remain visible to the guard"},
        }
        self._source(url, body, expected_metadata=metadata, doc_id=did)
        self._asset(url, did)
        original_before = self.db.execute(
            "SELECT xmin::text,source_url,media_type,kind,reference_period,metadata,content "
            "FROM source_document WHERE id=%s", (did,),
        ).fetchone()
        with self.assertRaisesRegex(ValueError, "metadata or body changed"):
            self._process(url, body, date(2014, 11, 7))
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,source_url,media_type,kind,reference_period,metadata,content "
            "FROM source_document WHERE id=%s", (did,),
        ).fetchone(), original_before)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s", (did,)
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s", (did,)
        ).fetchone(), (0,))

    def test_e_valid_changed_body_uses_normal_native_publication_and_preserves_old_review(self):
        url = next(iter(EVIDENCE))
        old_body = (FIXTURES / "nov01.xls").read_bytes()
        old_id = self._source(url, old_body)
        self._asset(url, old_id)
        self.assertEqual(self._process(url, old_body, date(2014, 11, 7))[0], 0)

        old_source = self.db.execute(
            "SELECT xmin::text,source_url,media_type,kind,reference_period,metadata,content "
            "FROM source_document WHERE id=%s", (old_id,),
        ).fetchone()
        old_review = self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,record,reason "
            "FROM official_source_review WHERE document_id=%s", (old_id,),
        ).fetchall()
        old_checkpoint = self.db.execute(
            "SELECT xmin::text,processor_version,step,records FROM ingestion_checkpoint "
            "WHERE document_id=%s", (old_id,),
        ).fetchall()
        prior_attempts = self.db.execute(
            "SELECT attempts FROM ingestion_asset WHERE url=%s", (url,),
        ).fetchone()[0]
        self.assertEqual(len(old_review), 1)
        self.assertEqual(old_checkpoint[0][2:], ("official:complete", 0))

        corrected = native_typed_update(include_context=True)
        corrected_id = hashlib.sha256(corrected).hexdigest()
        count, scan = self._process(url, corrected, date(2014, 11, 14))
        self.assertEqual(count, 1)
        scan.assert_not_called()

        source = self.db.execute(
            "SELECT source_url,media_type,kind,metadata,content FROM source_document WHERE id=%s",
            (corrected_id,),
        ).fetchone()
        self.assertEqual(source[0], url)
        self.assertEqual(source[1:3], ("application/vnd.ms-excel", "original"))
        self.assertEqual(source[3]["ingestion_kind"], "dane-weekly-xlsx")
        self.assertEqual(bytes(source[4]), corrected)
        quote = self.db.execute(
            "SELECT product_name,unit,market,observed_on,price,min_price,max_price,parser_version "
            "FROM official_price_quote WHERE document_id=%s", (corrected_id,),
        ).fetchall()
        self.assertEqual(len(quote), 1)
        self.assertEqual(quote[0][:7], ("Limón Tahití", "kg", "Corabastos (Bogotá)",
                                        date(2014, 11, 14), 1100.0, 1000.0, 1200.0))
        self.assertEqual(quote[0][7], worker.asset_parser_version("dane-weekly-xlsx", url))
        self.assertEqual(self.db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='official:complete'",
            (corrected_id, worker.asset_parser_version("dane-weekly-xlsx", url)),
        ).fetchone(), (1,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s", (corrected_id,),
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,source_url,media_type,kind,reference_period,metadata,content "
            "FROM source_document WHERE id=%s", (old_id,),
        ).fetchone(), old_source)
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,record,reason "
            "FROM official_source_review WHERE document_id=%s", (old_id,),
        ).fetchall(), old_review)
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,processor_version,step,records FROM ingestion_checkpoint "
            "WHERE document_id=%s", (old_id,),
        ).fetchall(), old_checkpoint)
        asset = self.db.execute(
            "SELECT status,records,error,document_id,processor_version,attempts "
            "FROM ingestion_asset WHERE url=%s", (url,),
        ).fetchone()
        self.assertEqual(asset, ("complete", 1, None, corrected_id,
                                 worker.asset_parser_version("dane-weekly-xlsx", url),
                                 prior_attempts + 1))

    def test_f_changed_native_extraction_failure_uses_standard_gate_without_review_or_ocr(self):
        url = next(iter(EVIDENCE))
        old_body = (FIXTURES / "nov01.xls").read_bytes()
        old_id = self._source(url, old_body)
        self._asset(url, old_id)
        self.assertEqual(self._process(url, old_body, date(2014, 11, 7))[0], 0)
        before_review = self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,record,reason "
            "FROM official_source_review WHERE document_id=%s", (old_id,),
        ).fetchall()
        before_checkpoint = self.db.execute(
            "SELECT xmin::text,processor_version,step,records FROM ingestion_checkpoint "
            "WHERE document_id=%s", (old_id,),
        ).fetchall()

        broken = native_no_monetary_table()
        broken_id = hashlib.sha256(broken).hexdigest()
        with patch.object(worker, "enqueue_failed_workbook", wraps=worker.enqueue_failed_workbook) as gate:
            with self.assertRaisesRegex(ValueError, "native extraction failed") as failure:
                self._process(url, broken, date(2014, 11, 7))
        gate.assert_called_once()
        failure.exception.private_ocr_scan.assert_not_called()
        self.assertEqual(self.db.execute(
            "SELECT status,document_id FROM ingestion_asset WHERE url=%s", (url,),
        ).fetchone(), ("failed", broken_id))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s", (broken_id,),
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (broken_id,),
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s", (broken_id,),
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,record,reason "
            "FROM official_source_review WHERE document_id=%s", (old_id,),
        ).fetchall(), before_review)
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,processor_version,step,records FROM ingestion_checkpoint "
            "WHERE document_id=%s", (old_id,),
        ).fetchall(), before_checkpoint)


    def test_g_changed_failed_layout_with_embedded_image_queues_one_versioned_ocr_task(self):
        url = next(iter(EVIDENCE))
        old_body = (FIXTURES / "nov01.xls").read_bytes()
        old_id = self._source(url, old_body)
        self._asset(url, old_id)
        self.assertEqual(self._process(url, old_body, date(2014, 11, 7))[0], 0)
        old_review = self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,record,reason "
            "FROM official_source_review WHERE document_id=%s", (old_id,),
        ).fetchall()
        old_checkpoint = self.db.execute(
            "SELECT xmin::text,processor_version,step,records FROM ingestion_checkpoint "
            "WHERE document_id=%s", (old_id,),
        ).fetchall()

        broken = native_no_monetary_table()
        broken_id = hashlib.sha256(broken).hexdigest()
        from io import BytesIO
        from PIL import Image
        buffer = BytesIO()
        Image.new("RGB", (300, 200), "white").save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
        # Model one embedded image locally so the real scan/enqueue branch is
        # exercised without OCR inference, providers, or network access.
        with patch("pipelines.ingestion.official_sources.process",
                   side_effect=ValueError("No input price rows")), \
             patch("pipelines.ingestion.ocr.spreadsheet_images",
                   return_value=[("Información Boletin!image 1,anchor row 2,col 1", image_bytes)]):
            with patch.object(worker, "fetch_asset", return_value=broken), \
                 patch.object(worker, "archive", side_effect=self._archive_local):
                count = worker.process_asset(self.db, url, "dane-weekly-xlsx", date(2014, 11, 7))
        self.assertEqual(count, 0)
        version = worker.asset_parser_version("dane-weekly-xlsx", url)
        asset = self.db.execute(
            "SELECT status,records,error,document_id,processor_version,attempts "
            "FROM ingestion_asset WHERE url=%s", (url,),
        ).fetchone()
        self.assertEqual(asset[0], "awaiting-ocr")
        self.assertEqual(asset[1], 0)
        self.assertIn("No input price rows", asset[2])
        self.assertEqual(asset[3:], (broken_id, version, 2))
        task = self.db.execute(
            "SELECT t.status,t.source_kind,t.source_locator,d.kind,d.media_type,"
            "octet_length(d.content),d.content FROM source_ocr_task t "
            "JOIN source_document d ON d.id=t.image_id WHERE t.document_id=%s",
            (broken_id,),
        ).fetchall()
        self.assertEqual(len(task), 1)
        self.assertEqual(task[0][:5], (
            "pending", "dane-weekly-xlsx", "Información Boletin!image 1,anchor row 2,col 1",
            "original", "image/png",
        ))
        self.assertEqual(bytes(task[0][6]), image_bytes)
        from . import ocr
        self.assertEqual(self.db.execute(
            "SELECT version FROM source_ocr_scan WHERE document_id=%s", (broken_id,),
        ).fetchone(), (ocr.VERSION,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s", (broken_id,),
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (broken_id,),
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s", (broken_id,),
        ).fetchone(), (0,))
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,source_locator,parser_version,record,reason "
            "FROM official_source_review WHERE document_id=%s", (old_id,),
        ).fetchall(), old_review)
        self.assertEqual(self.db.execute(
            "SELECT xmin::text,processor_version,step,records FROM ingestion_checkpoint "
            "WHERE document_id=%s", (old_id,),
        ).fetchall(), old_checkpoint)
        # It is held by the pending OCR task, not ordinary source backfill.
        self.assertNotIn(url, [row[0] for row in queue_plan.backfill_candidates(self.db, 100)])


    def test_h_all_fifty_three_actual_readable_sources_review_without_ocr_and_repeat(self):
        self.assertEqual(hashlib.sha256(AUDIT.read_bytes()).hexdigest(), "d3ef4d3540eedec4289eae99fdfbdb909fc46d059a60612e0038057881aa60c8")
        self.assertEqual(hashlib.sha256(METADATA.read_bytes()).hexdigest(), "f5d516325603ad2ae9483ae65eadc740ec1a7ebe0e9ccb05428326585ec6ea06")
        audit = json.loads(AUDIT.read_text())
        evidence = {c["asset"]["url"]: c for c in json.loads(METADATA.read_text())["cases"]}
        self.assertTrue(audit["complete"])
        self.assertEqual(len(audit["cases"]), 53)
        # Keep the original 53-source audit and its loop immutable. The April
        # 2015 workbook has a separate, exact-source native-layout qualification.
        april_2015_url = (
            "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
            "Anexo_13_17abr_2015.xls"
        )
        self.assertEqual(set(ORIGINALS) - {april_2015_url}, set(evidence))
        self.assertEqual(len(weekly_native_context.ORIGINALS), 54)
        self.assertIn(april_2015_url, weekly_native_context.ORIGINALS)
        self.assertEqual(sum(c["native_price_rows"] for c in audit["cases"]), 242830)
        self.assertEqual(sum(c["partial_price_cells"] for c in audit["cases"]), 2)
        for c in audit["cases"]:
            with self.subTest(url=c["url"]):
                original = evidence[c["url"]]["source"]
                asset = evidence[c["url"]]["asset"]
                body = (ALL_AUDITED_FIXTURES / c["source"]).read_bytes()
                did, url = original["id"], original["source_url"]
                self.assertEqual(hashlib.sha256(body).hexdigest(), did)
                self.assertEqual(len(body), original["bytes"])
                self.assertFalse(c["native_periods"])
                self.assertFalse(c["declared_kg"])
                self.assertIsNone(c["url_period"])
                self.db.execute(
                    "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
                    "reference_period,content,metadata) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (did, original["title"], original["publisher"], url, original["media_type"],
                     original["kind"], original["reference_period"], body, Jsonb(original["metadata"])),
                )
                self.db.execute(
                    "INSERT INTO ingestion_asset(url,kind,observed_on,status,document_id,records,error,"
                    "processor_version,checked_at) VALUES(%s,'dane-weekly-xlsx',%s,'failed',%s,%s,%s,%s,now()-interval '2 days')",
                    (url, asset["observed_on"], did, asset["records"], asset["error"], asset["processor_version"]),
                )
                before = self.db.execute(
                    "SELECT xmin::text,title,publisher,source_url,media_type,kind,reference_period,metadata,content "
                    "FROM source_document WHERE id=%s", (did,),
                ).fetchone()
                for repetition in (1, 2):
                    with patch.object(worker, "fetch_asset", return_value=body) as fetch, \
                         patch.object(worker, "archive", return_value=did) as archive, \
                         patch("pipelines.ingestion.ocr.scan_document", side_effect=AssertionError("No OCR for readable ambiguous native text")) as scan, \
                         patch.object(worker, "enqueue_failed_workbook", wraps=worker.enqueue_failed_workbook) as gate:
                        count = worker.process_asset(self.db, url, "dane-weekly-xlsx", asset["observed_on"])
                    self.assertEqual(count, 0)
                    fetch.assert_called_once()
                    archive.assert_called_once()
                    scan.assert_not_called()
                    gate.assert_not_called()
                    version = worker.asset_parser_version("dane-weekly-xlsx", url)
                    self.assertIn(weekly_native_context.VERSION_SUFFIX, version)
                    self.assertEqual(self.db.execute(
                        "SELECT status,records,error,document_id,processor_version,attempts FROM ingestion_asset WHERE url=%s",
                        (url,),
                    ).fetchone(), ("review", 0, weekly_native_context.REVIEW_MARKER, did, version, repetition))
                    reviews = self.db.execute(
                        "SELECT source_locator,parser_version,record,reason,xmin::text FROM official_source_review WHERE document_id=%s",
                        (did,),
                    ).fetchall()
                    self.assertEqual(len(reviews), 1)
                    review = reviews[0]
                    self.assertEqual(review[:2], (weekly_native_context.REVIEW_LOCATOR, version))
                    self.assertEqual(review[3], weekly_native_context.REVIEW_MARKER)
                    self.assertEqual(review[2], weekly_native_context.inspect_original(body, url, did))
                    self.assertEqual(review[2]["details"]["native_numeric_rows_untyped"], c["native_price_rows"])
                    self.assertEqual(review[2]["details"].get("native_partial_rows_untyped", 0), c["partial_price_cells"])
                    self.assertEqual(review[2]["details"]["typed_price_rows"], 0)
                    self.assertIsNone(review[2]["price"])
                    self.assertNotIn("unit", review[2])
                    self.assertEqual(self.db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)).fetchone(), (0,))
                    cp = self.db.execute(
                        "SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='official:complete'",
                        (did, version),
                    ).fetchone()
                    self.assertEqual(cp[0], 0)
                    self.assertEqual(self.db.execute(
                        "SELECT xmin::text,title,publisher,source_url,media_type,kind,reference_period,metadata,content FROM source_document WHERE id=%s",
                        (did,),
                    ).fetchone(), before)
                    self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_task WHERE document_id=%s", (did,)).fetchone(), (0,))
                    self.assertNotIn(url, [row[0] for row in queue_plan.backfill_candidates(self.db, 100)])
                    if repetition == 1:
                        first_review, first_cp = reviews, cp
                    else:
                        self.assertEqual(reviews, first_review)
                        self.assertEqual(cp, first_cp)


if __name__ == "__main__":
    unittest.main(verbosity=2)

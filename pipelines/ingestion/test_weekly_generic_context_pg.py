"""Full-schema regression for native weekly workbooks with missing source context."""
import hashlib
import io
import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
from openpyxl import Workbook
from psycopg.types.json import Jsonb

from . import official_sources, queue_plan, worker
from . import reviewed_weekly_native_context as context

KIND = "dane-weekly-xlsx"
URL_ROOT = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
FIXTURES = Path(__file__).parent / "testdata" / "weekly_generic_context"
ORIGINALS = FIXTURES
AUDIT = json.loads((FIXTURES / "NATIVE_AUDIT_FIRST_A.json").read_text())
METADATA = json.loads((FIXTURES / "METADATA_FIRST_A.json").read_text())
AUDIT_BY_URL = {row["url"]: row for row in AUDIT["cases"]}
META_BY_URL = {row["asset"]["url"]: row for row in METADATA["cases"]}
URLS = tuple(AUDIT_BY_URL)


def media(url):
    return ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if url.lower().endswith(".xlsx") else "application/vnd.ms-excel")


def make_untyped(unit_heading=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "Información Boletin"
    ws.append(["Cuadro 1. Mercados mayoristas. Precios de venta de frutas"])
    if unit_heading:
        ws.append([unit_heading])
    ws.append(["Productos y mercados", "Precio mínimo", "Precio máximo", "Precio medio"])
    ws.append(["Limón Tahití"])
    ws.append(["Corabastos (Bogotá)", 1000, 1200, 1100])
    out = io.BytesIO(); wb.save(out); wb.close()
    return out.getvalue()


class _Response:
    def __init__(self, content, headers=None):
        self.status_code = 200
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self):
        return None


def make_typed():
    wb = Workbook()
    ws = wb.active
    ws.title = "Información Boletin"
    ws.append(["Semana del 8 al 14 de noviembre de 2014"])
    ws.append(["Precios publicados en pesos por kilogramo"])
    ws.append(["Cuadro 1. Mercados mayoristas. Precios de venta de frutas"])
    ws.append(["Productos y mercados", "Precio mínimo", "Precio máximo", "Precio medio"])
    ws.append(["Limón Tahití"])
    ws.append(["Corabastos (Bogotá)", 1000, 1200, 1100, "Estable"])
    out = io.BytesIO(); wb.save(out); wb.close()
    return out.getvalue()


@unittest.skipUnless(os.environ.get("AGRO_GENERIC_WEEKLY_TEST_DSN"), "owned full-schema PG16 DSN required")
class GenericWeeklyContextCandidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = psycopg.connect(os.environ["AGRO_GENERIC_WEEKLY_TEST_DSN"], autocommit=True)
        if (not str(cls.db.info.host).startswith("/tmp/agro-weekly-generic-")
                or cls.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None
                or not cls.db.execute("SHOW server_version").fetchone()[0].startswith("16.")):
            cls.db.close(); raise RuntimeError("not the owned Unix-socket PG16 test database")
        cls.db.execute("SET ROLE agro_ingestor")
        if cls.db.execute("SELECT current_user").fetchone()[0] != "agro_ingestor":
            cls.db.close(); raise RuntimeError("canonical agro_ingestor grant not active")
        cls.db.execute("SET TIME ZONE 'UTC'")
        cls.db.execute("SET statement_timeout='90s'")
        for table in ("source_document", "official_price_quote", "official_source_review", "ingestion_checkpoint", "ingestion_asset", "source_ocr_task", "source_ocr_scan"):
            if cls.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                cls.db.close(); raise RuntimeError("owned test database must begin empty")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.db.execute("BEGIN")

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def _insert_source(self, url, body, *, metadata=None, document_id=None, source_url=None):
        did = document_id or hashlib.sha256(body).hexdigest()
        filename = url.rsplit("/", 1)[-1]
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) "
            "VALUES(%s,%s,'DANE · SIPSA',%s,%s,'original','Serie histórica completa',%s,%s)",
            (did, filename, source_url or url, media(url), body,
             Jsonb(metadata or {"retention":"permanent","ingestion_kind":KIND,"original_filename":filename})),
        )
        return did

    def _insert_asset(self, url, did, status="failed"):
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,observed_on,status,document_id,records,error,processor_version,checked_at) "
            "VALUES(%s,%s,NULL,%s,%s,0,%s,%s,now()-interval '2 days')",
            (url, KIND, status, did, "Weekly grouped workbook has no explicit period in cells or URL", worker.asset_parser_version(KIND,url)),
        )

    def _run(self, url, body, did=None, archive_id=None):
        did = did or hashlib.sha256(body).hexdigest()
        with patch.object(worker, "fetch_asset", return_value=body) as fetch, \
             patch.object(worker, "archive", return_value=archive_id or did) as archive, \
             patch("pipelines.ingestion.ocr.scan_document") as scan, \
             patch.object(worker, "enqueue_failed_workbook", wraps=worker.enqueue_failed_workbook) as enqueue:
            count = worker.process_asset(self.db, url, KIND, date(2026,10,8))
        return count, fetch, archive, scan, enqueue

    def test_three_retained_originals_review_without_typed_prices_and_repeat_preserves_xmins(self):
        before_registry = set(context.URLS)
        total = 0
        for url in URLS:
            case = AUDIT_BY_URL[url]
            meta = META_BY_URL[url]
            body = (ORIGINALS / Path(case["source"]).name).read_bytes()
            did = hashlib.sha256(body).hexdigest()
            self.assertEqual(did, meta["source"]["id"])
            self.assertEqual(len(body), meta["source"]["bytes"])
            self.assertEqual(context.inspect_generic(body,url,did)["details"]["native_numeric_rows_untyped"], case["native_price_rows"])
            self._insert_source(url, body, metadata=meta["source"]["metadata"])
            self._insert_asset(url,did)
            source_before = self.db.execute("SELECT xmin::text,source_url,media_type,kind,reference_period,metadata,content FROM source_document WHERE id=%s",(did,)).fetchone()
            for attempt in (1,2):
                count, fetch, archive, scan, enqueue = self._run(url,body,did)
                self.assertEqual(count,0); fetch.assert_called_once(); archive.assert_called_once()
                scan.assert_not_called(); enqueue.assert_not_called()
                version=worker.asset_parser_version(KIND,url)
                asset=self.db.execute("SELECT status,records,error,document_id,processor_version,attempts FROM ingestion_asset WHERE url=%s",(url,)).fetchone()
                self.assertEqual(asset,("review",0,context.GENERIC_REVIEW_MARKER,did,version,attempt))
                reviews=self.db.execute("SELECT source_locator,parser_version,record,reason,xmin::text FROM official_source_review WHERE document_id=%s",(did,)).fetchall()
                self.assertEqual(len(reviews),1)
                self.assertEqual(reviews[0][:2],(context.GENERIC_REVIEW_LOCATOR,version))
                self.assertEqual(reviews[0][3],context.GENERIC_REVIEW_MARKER)
                detail=reviews[0][2]["details"]
                self.assertEqual(detail["native_numeric_rows_untyped"],case["native_price_rows"])
                self.assertEqual(detail["typed_price_rows"],0)
                self.assertIsNone(reviews[0][2]["price"])
                self.assertNotIn("unit",reviews[0][2])
                self.assertEqual(self.db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s",(did,)).fetchone()[0],0)
                cp=self.db.execute("SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='official:complete'",(did,version)).fetchone()
                self.assertEqual(cp[0],0)
                self.assertEqual(self.db.execute("SELECT xmin::text,source_url,media_type,kind,reference_period,metadata,content FROM source_document WHERE id=%s",(did,)).fetchone(),source_before)
                self.assertNotIn(url,[r[0] for r in queue_plan.backfill_candidates(self.db,100)])
                if attempt==1: first_review,first_cp=reviews,cp
                else: self.assertEqual(reviews,first_review); self.assertEqual(cp,first_cp)
            total += case["native_price_rows"]
        self.assertEqual(total,12837)
        self.assertEqual(set(context.URLS),before_registry)

    def test_unregistered_native_workbook_is_reviewed_structurally_without_registry_entry(self):
        url=URL_ROOT+"synthetic_unregistered_weekly.xlsx"; body=make_untyped(); did=hashlib.sha256(body).hexdigest()
        self.assertNotIn(url,context.URLS)
        self._insert_source(url,body); self._insert_asset(url,did)
        count,_,_,scan,enqueue=self._run(url,body,did)
        self.assertEqual(count,0); scan.assert_not_called(); enqueue.assert_not_called()
        self.assertEqual(self.db.execute("SELECT status,records,error FROM ingestion_asset WHERE url=%s",(url,)).fetchone(),("review",0,context.GENERIC_REVIEW_MARKER))
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s",(did,)).fetchone()[0],0)

    def test_wrong_metadata_or_archive_sha_fails_closed_without_review_or_checkpoint(self):
        body=make_untyped(); url=URL_ROOT+"metadata_guard.xls"; did=hashlib.sha256(body).hexdigest()
        self._insert_source(url,body,metadata={"retention":"temporary","ingestion_kind":KIND,"original_filename":"wrong.xls"}); self._insert_asset(url,did)
        with self.assertRaisesRegex(ValueError,"retained source metadata"):
            self._run(url,body,did)
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s",(did,)).fetchone()[0],0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s",(did,)).fetchone()[0],0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s",(did,)).fetchone()[0],0)
        # Separate wrong archive binding proves content-address checks on the lifecycle.
        url2=URL_ROOT+"wrong_sha_binding.xls"; bad_id="f"*64
        self._insert_source(url2,body,document_id=bad_id); self._insert_asset(url2,bad_id)
        with self.assertRaisesRegex(ValueError,"not content-addressed"):
            self._run(url2,body,bad_id,archive_id=bad_id)
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s",(bad_id,)).fetchone()[0],0)

    def test_prior_quote_history_blocks_generic_review(self):
        url=URL_ROOT+"history_guard.xls"; old_body=make_typed(); oldid=self._insert_source(url,old_body)
        rows=__import__("pipelines.ingestion.dane_weekly",fromlist=["parse"]).parse(old_body,url,KIND)
        self.assertTrue(rows)
        self.assertGreater(official_sources.publish_rows(self.db,rows,oldid,KIND,source_url=url),0)
        body=make_untyped(); did=self._insert_source(url,body); self._insert_asset(url,did)
        with self.assertRaisesRegex(ValueError,"blocked by prior quote history"):
            self._run(url,body,did)
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s",(did,)).fetchone()[0],0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s",(did,)).fetchone()[0],0)

    def test_poisoned_review_is_rejected_without_update_privilege(self):
        url=URL_ROOT+"poisoned_review.xls"; body=make_untyped(); did=self._insert_source(url,body); self._insert_asset(url,did)
        row=context.inspect_generic(body,url,did)
        self.db.execute("INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) VALUES(%s,%s,%s,%s,'poisoned')",
            (did,context.GENERIC_REVIEW_LOCATOR,worker.asset_parser_version(KIND,url),Jsonb(row)))
        with self.assertRaisesRegex(ValueError,"review differs"):
            self._run(url,body,did)
        self.assertEqual(self.db.execute("SELECT reason FROM official_source_review WHERE document_id=%s",(did,)).fetchone(),("poisoned",))
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s",(did,)).fetchone()[0],0)

    def test_mutable_typed_replacement_uses_normal_parser_and_keeps_old_original_review(self):
        url=URL_ROOT+"mutable_unregistered.xls"; body=make_untyped(); did=self._insert_source(url,body); self._insert_asset(url,did)
        self.assertEqual(self._run(url,body,did)[0],0)
        # New bytes at the same URL carry their own explicit week and unit; they enter normal typed publication.
        typed=make_typed(); typed_id=hashlib.sha256(typed).hexdigest()
        self._insert_source(url,typed,document_id=typed_id)
        count,_,_,scan,enqueue=self._run(url,typed,archive_id=typed_id)
        self.assertGreater(count,0); scan.assert_not_called(); enqueue.assert_not_called()
        self.assertEqual(self.db.execute("SELECT status,records,document_id FROM ingestion_asset WHERE url=%s",(url,)).fetchone(),("complete",count,typed_id))
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_document WHERE source_url=%s AND kind='original'",(url,)).fetchone()[0],2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s",(did,)).fetchone()[0],1)

    def test_unknown_native_xls_and_xlsx_remain_untyped_and_never_enter_ocr(self):
        # The audit stores the original location separately; locate its same-hash private fixture.
        ole_body = None
        for path in ORIGINALS.glob("*.xls"):
            if path.read_bytes()[:4] == b"\xd0\xcf\x11\xe0":
                ole_body = path.read_bytes()
                break
        self.assertIsNotNone(ole_body, "self-contained native OLE .xls fixture required")
        cases = (
            (URL_ROOT + "synthetic_unregistered_ole.xls", ole_body),
            (URL_ROOT + "synthetic_unregistered_ooxml.xlsx", make_untyped()),
        )
        for url, body in cases:
            with self.subTest(url=url):
                did = hashlib.sha256(body).hexdigest()
                self._insert_source(url, body)
                self._insert_asset(url, did)
                count, _, _, scan, enqueue = self._run(url, body, did)
                self.assertEqual(count, 0)
                scan.assert_not_called()
                enqueue.assert_not_called()
                self.assertEqual(self.db.execute(
                    "SELECT status,records,error FROM ingestion_asset WHERE url=%s", (url,)
                ).fetchone(), ("review", 0, context.GENERIC_REVIEW_MARKER))
                self.assertEqual(self.db.execute(
                    "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)
                ).fetchone()[0], 0)

    def test_operation_scope_and_encoded_filename_follow_archive_binding(self):
        url = "https://www.dane.gov.co/files/operaciones/SIPSA/Native%20review.xls"
        body = make_untyped()
        did = self._insert_source(url, body)
        self._insert_asset(url, did)
        count, _, _, scan, enqueue = self._run(url, body, did)
        self.assertEqual(count, 0)
        scan.assert_not_called()
        enqueue.assert_not_called()
        review = self.db.execute(
            "SELECT record FROM official_source_review WHERE document_id=%s", (did,)
        ).fetchone()[0]
        self.assertEqual(self.db.execute(
            "SELECT metadata->>'original_filename' FROM source_document WHERE id=%s", (did,)
        ).fetchone()[0], "Native%20review.xls")
        self.assertEqual(self.db.execute(
            "SELECT status,records FROM ingestion_asset WHERE url=%s", (url,)
        ).fetchone(), ("review", 0))

    def test_changed_native_body_at_source_specific_url_uses_generic_review(self):
        from . import reviewed_weekly_native_context
        url = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_Bol_Semanal_nov01_2014.xls"
        original_id = reviewed_weekly_native_context.ORIGINALS[url]["sha256"]
        original_path = (Path(__file__).parent / "testdata" / "weekly_native_context_review"
                         / "all_audited_sources" / (original_id + ".xls"))
        original = original_path.read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), original_id)
        self._insert_source(url, original)
        self._insert_asset(url, original_id)
        changed = make_untyped()
        changed_id = hashlib.sha256(changed).hexdigest()
        self._insert_source(url, changed, document_id=changed_id)
        count, _, _, scan, enqueue = self._run(url, changed, changed_id)
        self.assertEqual(count, 0)
        scan.assert_not_called()
        enqueue.assert_not_called()
        self.assertEqual(self.db.execute(
            "SELECT status,records,document_id FROM ingestion_asset WHERE url=%s", (url,)
        ).fetchone(), ("review", 0, changed_id))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s", (changed_id,)
        ).fetchone()[0], 1)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (changed_id,)
        ).fetchone()[0], 0)

    def test_explicit_unit_is_retained_even_when_period_is_missing(self):
        from . import dane_weekly
        body = make_untyped("Precios publicados en pesos por kilogramo")
        url = URL_ROOT + "period_gap_with_explicit_unit.xls"
        did = hashlib.sha256(body).hexdigest()
        review = context.inspect_generic(body, url, did)
        self.assertEqual(review["details"]["literal_unit_heading"],
                         "Precios publicados en pesos por kilogramo")
        self.assertIsNone(review["details"]["source_period"])
        self.assertIsNone(review["price"])
        self.assertNotIn("unit", review)
        self.assertIsNotNone(dane_weekly.WeeklyNativeContextIncomplete)

    def test_displaced_asset_pointer_is_rejected_without_clobbering_newer_revision(self):
        from . import dane_weekly
        url = URL_ROOT + "concurrent_pointer_change.xls"
        body = make_untyped()
        did = self._insert_source(url, body)
        self._insert_asset(url, did)
        newer_id = self._insert_source(url, make_typed())

        def move_pointer_then_raise(*args, **kwargs):
            self.db.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s",
                            (newer_id, url))
            raise dane_weekly.WeeklyNativeContextIncomplete(
                "Weekly grouped workbook has no explicit period in cells or URL")

        with patch.object(worker, "fetch_asset", return_value=body), \
             patch.object(worker, "archive", return_value=did), \
             patch.object(dane_weekly, "parse", side_effect=move_pointer_then_raise), \
             patch("pipelines.ingestion.ocr.scan_document") as scan, \
             patch.object(worker, "enqueue_failed_workbook", wraps=worker.enqueue_failed_workbook) as enqueue:
            with self.assertRaisesRegex(ValueError, "document pointer changed"):
                worker.process_asset(self.db, url, KIND, date(2026, 10, 8))
        scan.assert_not_called()
        enqueue.assert_not_called()
        self.assertEqual(self.db.execute(
            "SELECT document_id FROM ingestion_asset WHERE url=%s", (url,)
        ).fetchone()[0], newer_id)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s", (did,)
        ).fetchone()[0], 0)

    def test_normal_index_discovery_and_due_refresh_handle_mutable_body(self):
        from . import dane_weekly
        index_url = dane_weekly.WEEKLY
        filename = "Anex_Bol_Semanal_sin_periodo.xls"
        child_url = URL_ROOT + filename
        html = f'<html><a href="{child_url}">Anexo semanal</a></html>'.encode()
        worker.queue(self.db, index_url, "dane-weekly-index")
        with patch.object(worker, "_get", return_value=_Response(html)) as index_get:
            worker.process_asset(self.db, index_url, "dane-weekly-index", date(2026, 10, 8))
        index_get.assert_called_once()
        self.assertEqual(self.db.execute(
            "SELECT observed_on,status FROM ingestion_asset WHERE url=%s AND kind=%s",
            (child_url, KIND),
        ).fetchone(), (None, "pending"))

        old_body = make_untyped()
        with patch.object(worker, "_get", return_value=_Response(old_body)) as old_get:
            worker.process_asset(self.db, child_url, KIND, None)
        old_get.assert_called_once()
        old_id = hashlib.sha256(old_body).hexdigest()
        self.assertEqual(self.db.execute(
            "SELECT status,document_id FROM ingestion_asset WHERE url=%s", (child_url,)
        ).fetchone(), ("review", old_id))
        self.assertNotIn(child_url, [r[0] for r in queue_plan.backfill_candidates(self.db, 1000)])

        # Fresh reviews are held out of normal backfill for 30 days; once due,
        # the normal planner schedules the mutable URL for ordinary retrieval.
        self.db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '31 days' WHERE url=%s",
                        (child_url,))
        planned = [r for r in queue_plan.backfill_candidates(self.db, 1000) if r[0] == child_url]
        self.assertEqual(len(planned), 1)
        changed_body = make_typed()
        with patch.object(worker, "_get", return_value=_Response(changed_body, {"ETag": '"typed-v2"'})) as refresh_get, \
             patch("pipelines.ingestion.ocr.scan_document") as scan, \
             patch.object(worker, "enqueue_failed_workbook", wraps=worker.enqueue_failed_workbook) as enqueue:
            count = worker.process_asset(self.db, planned[0][0], planned[0][1], planned[0][2])
        refresh_get.assert_called_once()
        scan.assert_not_called()
        enqueue.assert_not_called()
        new_id = hashlib.sha256(changed_body).hexdigest()
        self.assertGreater(count, 0)
        self.assertEqual(self.db.execute(
            "SELECT status,records,document_id FROM ingestion_asset WHERE url=%s", (child_url,)
        ).fetchone(), ("complete", count, new_id))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s", (old_id,)
        ).fetchone()[0], 1)
        self.assertGreater(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (new_id,)
        ).fetchone()[0], 0)

    def test_generic_publication_rolls_back_atomically_on_interruption(self):
        url = URL_ROOT + "interrupted_generic_publication.xls"
        body = make_untyped()
        did = self._insert_source(url, body)
        self._insert_asset(url, did)
        publisher = official_sources.publish_rows

        def publish_then_interrupt(*args, **kwargs):
            publisher(*args, **kwargs)
            raise RuntimeError("synthetic interruption after review insert")

        with patch.object(worker, "fetch_asset", return_value=body), \
             patch.object(worker, "archive", return_value=did), \
             patch.object(official_sources, "publish_rows", side_effect=publish_then_interrupt), \
             patch("pipelines.ingestion.ocr.scan_document") as scan, \
             patch.object(worker, "enqueue_failed_workbook", wraps=worker.enqueue_failed_workbook) as enqueue:
            with self.assertRaisesRegex(RuntimeError, "synthetic interruption"):
                worker.process_asset(self.db, url, KIND, date(2026, 10, 8))
        scan.assert_not_called()
        enqueue.assert_not_called()
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s", (did,)
        ).fetchone()[0], 0)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s", (did,)
        ).fetchone()[0], 0)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)
        ).fetchone()[0], 0)
        self.assertEqual(self.db.execute(
            "SELECT status,document_id FROM ingestion_asset WHERE url=%s", (url,)
        ).fetchone(), ("pending", did))

if __name__ == "__main__":
    unittest.main(verbosity=2)

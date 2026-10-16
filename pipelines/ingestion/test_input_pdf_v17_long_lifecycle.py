import importlib.util
import pathlib
import sys
import unittest
from contextlib import nullcontext
from datetime import date
from types import SimpleNamespace

from pipelines.ingestion import input_pdf_v17_replay as replay


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.row or []


class SpyDB:
    def __init__(self, handler):
        self.handler = handler
        self.sql = []

    def transaction(self):
        return nullcontext()

    def execute(self, sql, params=()):
        self.sql.append((" ".join(sql.split()), params))
        return Result(self.handler(sql, params))


class LifecycleQuerySpyTests(unittest.TestCase):
    def test_january_v14_initial_states_fall_through(self):
        day = date(2019, 1, 31)
        did = replay.JAN2019_CONTEXT_DID
        for state, status in (("complete-v14", "complete"), ("pending-v14", "pending")):
            with self.subTest(state=state):
                asset = ("inputs-pdf", day, did, status, replay.OLD_VERSION,
                         replay.JAN2019_CONTEXT_RAW_ROWS, None)
                def respond(sql, params):
                    if "ingestion_checkpoint" in sql and params and replay.VERSION in params:
                        return None
                    return asset
                db = SpyDB(respond)
                self.assertIsNone(replay.complete_jan2019_sibling_asset(
                    db, replay.JAN2019_CONTEXT_URL, "inputs-pdf", day))
                self.assertEqual(len(db.sql), 2)
                self.assertIn("FOR UPDATE", db.sql[0][0])
                self.assertIn("ingestion_checkpoint", db.sql[1][0])

    def test_january_changed_body_falls_through_to_replacement_guards(self):
        day = date(2019, 1, 31)
        changed_did = "a" * 64
        asset = ("inputs-pdf", day, changed_did, "pending", replay.VERSION, 1,
                 replay.WORK_DEFERRED_RETRY_ERROR)
        db = SpyDB(lambda sql, params: asset)
        self.assertIsNone(replay.complete_jan2019_sibling_asset(
            db, replay.JAN2019_CONTEXT_URL, "inputs-pdf", day))
        self.assertEqual(len(db.sql), 1)

    def test_january_registered_page_count_retry_uses_generic_context_guard(self):
        url = replay.JAN2019_CONTEXT_URL
        did = replay.JAN2019_CONTEXT_DID
        day = date(2019, 1, 31)
        asset = ("inputs-pdf", day, did, "failed", replay.VERSION,
                 replay.JAN2019_CONTEXT_RAW_ROWS,
                 "ValueError: Retained input PDF page count mismatch")
        filename = url.rsplit("/", 1)[-1]
        metadata = {"retention": "permanent", "ingestion_kind": "context-pdf",
                    "original_filename": filename}
        body = b"jan source bytes"

        def respond(sql, params):
            normalized = " ".join(sql.split())
            if normalized.startswith("SELECT kind,observed_on,document_id,status,processor_version,records,error"):
                return asset
            if "metadata->>'ingestion_kind'='context-pdf'" in normalized:
                return [(did,)]
            if normalized.startswith("SELECT kind,metadata FROM source_document"):
                return ("original", metadata)
            if normalized.startswith("SELECT error FROM ingestion_asset"):
                return (asset[6],)
            if normalized.startswith("SELECT kind,source_url,media_type,page_count,content,metadata"):
                return ("original", url, "application/pdf", replay.JAN2019_CONTEXT_PAGES, body, metadata)
            if normalized.startswith("SELECT title,publisher,reference_period"):
                return ("DANE - " + filename, "DANE", replay.JAN2019_CONTEXT_REFERENCE_PERIOD)
            if normalized.startswith("SELECT records FROM ingestion_checkpoint"):
                return (replay.JAN2019_CONTEXT_TYPED_ROWS,)
            if normalized.startswith("SELECT count(*),count(*) FILTER"):
                return (replay.JAN2019_CONTEXT_RAW_ROWS, replay.JAN2019_CONTEXT_TYPED_ROWS,
                        replay.JAN2019_CONTEXT_UNRESOLVED_ROWS)
            if normalized.startswith("SELECT 1 FROM ingestion_checkpoint"):
                return None
            raise AssertionError("unexpected Jan lifecycle SQL: " + normalized)

        db = SpyDB(respond)
        old_witness = replay._generic_context_v14_witness
        old_hashlib = replay.hashlib
        replay._generic_context_v14_witness = lambda *_args: {
            "document_id": did, "vector_sha256": replay.JAN2019_CONTEXT_OLD_VECTOR_SHA256,
        }
        replay.hashlib = SimpleNamespace(sha256=lambda _body: SimpleNamespace(hexdigest=lambda: did))
        try:
            self.assertIsNone(replay.assert_retained_v14_binding_locked(
                db, url, "inputs-pdf", day, did, replay.JAN2019_CONTEXT_RAW_ROWS))
        finally:
            replay._generic_context_v14_witness = old_witness
            replay.hashlib = old_hashlib
        self.assertFalse(any(sql.startswith("UPDATE ") or sql.startswith("INSERT ")
                             or sql.startswith("DELETE ") for sql, _ in db.sql))

    def test_unknown_context_page_count_error_is_rejected(self):
        url = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_abr_2014.pdf"
        did = "b" * 64
        day = date(2014, 4, 30)
        asset = ("inputs-pdf", day, did, "failed", replay.VERSION, 10,
                 "ValueError: Retained input PDF page count mismatch")
        metadata = {"retention": "permanent", "ingestion_kind": "context-pdf",
                    "original_filename": url.rsplit("/", 1)[-1]}

        def respond(sql, params):
            normalized = " ".join(sql.split())
            if normalized.startswith("SELECT kind,observed_on,document_id,status,processor_version,records,error"):
                return asset
            if "metadata->>'ingestion_kind'='context-pdf'" in normalized:
                return [(did,)]
            if normalized.startswith("SELECT kind,metadata FROM source_document"):
                return ("original", metadata)
            if normalized.startswith("SELECT error FROM ingestion_asset"):
                return (asset[6],)
            raise AssertionError("unexpected unknown-context SQL: " + normalized)

        with self.assertRaises(ValueError):
            replay.assert_retained_v14_binding_locked(
                SpyDB(respond), url, "inputs-pdf", day, did, 10)

    def test_february_pending_v14_is_valid_locked_publication_state(self):
        url = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Bol_Insumos_feb_2019.pdf"
        spec = replay.LONG_INPUT_PDF_REPAIRS[url]
        did = spec["document_id"]
        day = date.fromisoformat(spec["day"])
        metadata = {"retention": "permanent", "ingestion_kind": "inputs-pdf",
                    "original_filename": "Bol_Insumos_feb_2019.pdf"}
        body = b"test-only source bytes"
        asset = ("inputs-pdf", day, did, "pending", replay.OLD_VERSION,
                 spec["raw_rows"], None)

        def respond(sql, params):
            normalized = " ".join(sql.split())
            if normalized.startswith("SELECT kind,observed_on,document_id,status,processor_version,records,error"):
                return asset
            if "metadata->>'ingestion_kind'='context-pdf'" in normalized:
                return []
            if normalized.startswith("SELECT kind,metadata FROM source_document"):
                return ("original", metadata)
            if normalized.startswith("SELECT kind,source_url,media_type,page_count,content,metadata"):
                return ("original", url, "application/pdf", spec["pages"], body, metadata)
            if normalized.startswith("SELECT title,publisher,reference_period"):
                return ("DANE - Bol_Insumos_feb_2019.pdf", "DANE", spec["day"])
            if normalized.startswith("SELECT records FROM ingestion_checkpoint"):
                return (spec["typed_rows"],)
            if normalized.startswith("SELECT count(*),count(*) FILTER"):
                return (spec["raw_rows"], spec["typed_rows"], spec["unresolved_rows"])
            raise AssertionError("unexpected SQL in pure lifecycle spy: " + normalized)

        db = SpyDB(respond)
        original_hashlib = replay.hashlib
        replay.hashlib = SimpleNamespace(sha256=lambda _body: SimpleNamespace(hexdigest=lambda: did))
        try:
            result = replay.assert_retained_v14_binding_locked(
                db, url, "inputs-pdf", day, did, spec["raw_rows"])
        finally:
            replay.hashlib = original_hashlib
        self.assertIsNone(result)
        self.assertTrue(any("FOR UPDATE" in sql for sql, _ in db.sql))
        self.assertFalse(any(sql.startswith("UPDATE ") or sql.startswith("INSERT ")
                             or sql.startswith("DELETE ") for sql, _ in db.sql))


    def test_registered_long_pdf_bounds_are_256_pages_and_32_mib(self):
        import hashlib
        import io
        from pypdf import PdfWriter

        self.assertEqual(replay.MAX_PDF_PAGES, 256)
        self.assertEqual(replay.MAX_PDF_BYTES, 32 * 1024 * 1024)
        writer = PdfWriter()
        for _ in range(256):
            writer.add_blank_page(width=72, height=72)
        buf = io.BytesIO(); writer.write(buf); body = buf.getvalue()
        did = hashlib.sha256(body).hexdigest()
        replay.assert_native_zero_input_context(body, did)
        writer.add_blank_page(width=72, height=72)
        buf = io.BytesIO(); writer.write(buf); too_many_pages = buf.getvalue()
        with self.assertRaisesRegex(ValueError, "page count unsupported"):
            replay.assert_native_zero_input_context(too_many_pages, hashlib.sha256(too_many_pages).hexdigest())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import unittest
from unittest import mock

from pipelines.ingestion import ocr

FIXTURES = Path(__file__).resolve().parent / "testdata"
# Publisher-truncated Bucaramanga/Centroabastos original from the official
# DANE 2022-09-06 city ZIP; original evidence is retained byte for byte.
BAD = FIXTURES / "f96bbed4f594872dd7f812f84c15b8f6686340f42c937c7fc70b9984f5138aa9.pdf"
GOOD = FIXTURES / "2146ca465e6df79936c0bafc73fb9a7e76628ef262daad4ead595fe554e58f0d.pdf"


class FakeResult:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class FakeDB:
    def __init__(self, docs=(), fail_on=None):
        self.docs = list(docs)
        self.scans = set()
        self.reviews = {}
        self.tasks = []
        self.statements = []
        self.fail_on = fail_on

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("database-write-failure")
        if sql.startswith("SELECT 1 FROM source_ocr_scan"):
            return FakeResult([(1,)] if any((params[0], version) in self.scans for version in params[1:]) else [])
        if sql.startswith("SELECT id,content,metadata->>'ingestion_kind'"):
            return FakeResult(self.docs)
        if "INSERT INTO official_source_review" in sql:
            key = (params[0], params[1], params[2])
            self.reviews.setdefault(key, params)
        elif "INSERT INTO source_ocr_scan" in sql:
            self.scans.add((params[0], params[1]))
        elif "INSERT INTO source_ocr_task" in sql:
            self.tasks.append(params)
        return FakeResult()


def did(blob):
    return hashlib.sha256(blob).hexdigest()


class OCRRenderRecoveryTests(unittest.TestCase):
    def test_exact_corrupt_archive_becomes_idempotent_review_not_price_or_task(self):
        blob = BAD.read_bytes()
        self.assertEqual(did(blob), "f96bbed4f594872dd7f812f84c15b8f6686340f42c937c7fc70b9984f5138aa9")
        db = FakeDB()
        with mock.patch.object(ocr, "enqueue_image", side_effect=AssertionError("must not create OCR image")), \
             mock.patch.object(ocr.requests, "post", side_effect=AssertionError("provider forbidden")):
            ocr.scan_document(db, blob, did(blob), "city-pdf")
            first = (dict(db.reviews), set(db.scans), list(db.tasks))
            ocr.scan_document(db, blob, did(blob), "city-pdf")
        self.assertEqual(len(db.reviews), 1)
        review = next(iter(db.reviews.values()))
        record = review[3].obj
        self.assertEqual(review[1], "PDF document render")
        self.assertTrue(review[2].endswith(":pdf-render-failure-v1"))
        self.assertEqual(record["original_sha256"], did(blob))
        self.assertEqual(record["original_bytes"], 117581)
        self.assertFalse(record["typed_prices"])
        self.assertTrue(record["original_retained"])
        self.assertIn((did(blob), ocr.PDF_RENDER_FAILURE_VERSION), db.scans)
        self.assertNotIn((did(blob), ocr.VERSION), db.scans)
        self.assertEqual(db.tasks, [])
        self.assertEqual(first[0], db.reviews)
        self.assertEqual(first[1], db.scans)

    def test_readable_pdf_with_embedded_logos_stays_native_and_skips_ocr(self):
        blob = GOOD.read_bytes()
        with mock.patch.object(ocr, "enqueue_image", side_effect=AssertionError("image presence is not OCR need")), \
             mock.patch.object(ocr.requests, "post", side_effect=AssertionError("provider forbidden")):
            db = FakeDB()
            ocr.scan_document(db, blob, did(blob), "city-pdf")
        self.assertFalse(db.reviews)
        self.assertFalse(db.tasks)
        self.assertIn((did(blob), ocr.VERSION), db.scans)

    def test_corrupt_first_document_does_not_block_later_native_document(self):
        bad, good = BAD.read_bytes(), GOOD.read_bytes()
        db = FakeDB([
            (did(bad), bad, "city-pdf"),
            (did(good), good, "city-pdf"),
        ])
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "unit-test-only"}), \
             mock.patch.object(ocr, "retire_audited_decorative_pdf_pages", return_value=0), \
             mock.patch.object(ocr, "requeue_cached_typed_reviews", return_value={"checked": 0, "requeued_documents": 0, "requeued_tasks": 0}), \
             mock.patch.object(ocr, "retire_native_daily_tasks", return_value=0), \
             mock.patch.object(ocr, "_ocr_enough_time", return_value=True), \
             mock.patch.object(ocr, "_priority_snapshot", return_value=(0, 0, 0, 0, 0, [])), \
             mock.patch.object(ocr, "_finish_policy_available", return_value=True), \
             mock.patch.object(ocr, "enqueue_image", return_value=True), \
             mock.patch.object(ocr.requests, "post", side_effect=AssertionError("provider forbidden")):
            result = ocr.drain(db, scan_limit=2)
        self.assertEqual(result["processed"], 0)
        self.assertIn((did(bad), ocr.PDF_RENDER_FAILURE_VERSION), db.scans)
        self.assertIn((did(good), ocr.VERSION), db.scans)
        scan_query = next(sql for sql, _ in db.statements if sql.startswith("SELECT id,content,metadata->>'ingestion_kind'"))
        self.assertIn("s.version IN (%s,%s)", scan_query)

    def test_changed_body_hash_gets_a_separate_failure_identity(self):
        original = BAD.read_bytes()
        changed = original + b"\n"
        db = FakeDB()
        ocr.scan_document(db, original, did(original), "city-pdf")
        ocr.scan_document(db, changed, did(changed), "city-pdf")
        self.assertIn((did(original), ocr.PDF_RENDER_FAILURE_VERSION), db.scans)
        self.assertIn((did(changed), ocr.PDF_RENDER_FAILURE_VERSION), db.scans)
        self.assertEqual({key[0] for key in db.reviews}, {did(original), did(changed)})

    def test_new_failure_policy_version_can_retry_a_prior_policy_marker(self):
        blob = BAD.read_bytes()
        db = FakeDB()
        prior_policy = ocr.VERSION + ":pdf-render-failure-v0"
        db.scans.add((did(blob), prior_policy))
        ocr.scan_document(db, blob, did(blob), "city-pdf")
        self.assertIn((did(blob), prior_policy), db.scans)
        self.assertIn((did(blob), ocr.PDF_RENDER_FAILURE_VERSION), db.scans)
        self.assertEqual(len(db.reviews), 1)

    def test_terminal_failure_marker_is_not_bypassed_by_normal_extraction_flag(self):
        blob = BAD.read_bytes()
        db = FakeDB()
        db.scans.add((did(blob), ocr.PDF_RENDER_FAILURE_VERSION))
        with mock.patch("pdfplumber.open", side_effect=AssertionError("terminal policy marker must suppress scan")):
            ocr.scan_document(db, blob, did(blob), "city-pdf", normal_extraction_failed=True)
        self.assertFalse(db.reviews)
        self.assertEqual(len(db.scans), 1)

    def test_budget_deferral_is_not_quarantined(self):
        blob = GOOD.read_bytes()
        from pipelines.ingestion.resumable_inputs import WorkDeferred
        db = FakeDB()
        with mock.patch("pipelines.ingestion.pdf_sources.check_run_budget", side_effect=WorkDeferred("resume")):
            with self.assertRaises(WorkDeferred):
                ocr.scan_document(db, blob, did(blob), "city-pdf")
        self.assertFalse(db.reviews)
        self.assertFalse(db.scans)

    def test_review_database_error_propagates(self):
        blob = BAD.read_bytes()
        db = FakeDB(fail_on="INSERT INTO official_source_review")
        with self.assertRaisesRegex(RuntimeError, "database-write-failure"):
            ocr.scan_document(db, blob, did(blob), "city-pdf")

    def test_unrelated_pdfplumber_open_typeerror_propagates(self):
        blob = GOOD.read_bytes()
        db = FakeDB()
        with mock.patch("pdfplumber.open", side_effect=TypeError("programming error")):
            with self.assertRaisesRegex(TypeError, "programming error"):
                ocr.scan_document(db, blob, did(blob), "city-pdf")
        self.assertFalse(db.reviews)
        self.assertFalse(db.scans)

    def test_unrelated_native_page_runtimeerror_propagates(self):
        blob = GOOD.read_bytes()

        class BrokenPage:
            images = []
            def extract_text(self): raise RuntimeError("unrelated page error")
            def close(self): pass

        class OnePage:
            pages = [BrokenPage()]
            def __enter__(self): return self
            def __exit__(self, *_): return False

        db = FakeDB()
        with mock.patch("pdfplumber.open", return_value=OnePage()):
            with self.assertRaisesRegex(RuntimeError, "unrelated page error"):
                ocr.scan_document(db, blob, did(blob), "city-pdf")
        self.assertFalse(db.reviews)
        self.assertFalse(db.scans)

    def test_unrelated_pdfium_runtimeerror_propagates(self):
        blob = BAD.read_bytes()
        db = FakeDB()
        with mock.patch("pypdfium2.PdfDocument", side_effect=RuntimeError("pdfium programming error")):
            with self.assertRaisesRegex(RuntimeError, "pdfium programming error"):
                ocr.scan_document(db, blob, did(blob), "city-pdf")
        self.assertFalse(db.reviews)
        self.assertFalse(db.scans)

    def test_page_failure_is_terminal_policy_marker_not_normal_completion(self):
        blob = GOOD.read_bytes()
        from pdfplumber.utils.exceptions import PdfminerException
        import pypdfium2 as pdfium

        class BrokenPage:
            images = [{}]
            def extract_text(self): return ""
            def to_image(self, **_): raise PdfminerException("page render parse failure")
            def close(self): pass

        class OnePage:
            pages = [BrokenPage()]
            def __enter__(self): return self
            def __exit__(self, *_): return False

        db = FakeDB()
        with mock.patch("pdfplumber.open", return_value=OnePage()), \
             mock.patch.object(ocr, "_pdfium_render", side_effect=pdfium.PdfiumError("fallback page error")):
            ocr.scan_document(db, blob, did(blob), "city-pdf")
        self.assertIn((did(blob), ocr.PDF_RENDER_FAILURE_VERSION), db.scans)
        self.assertNotIn((did(blob), ocr.VERSION), db.scans)
        self.assertEqual(len(db.reviews), 1)
        self.assertEqual(next(iter(db.reviews))[1], "PDF page 1 render")

    def test_pdfplumber_pdfium_render_failure_isolated_from_healthy_sibling(self):
        blob = GOOD.read_bytes()
        import pypdfium2 as pdfium

        class FailedRenderPage:
            images = [{}]
            closed = False
            def extract_text(self): return ""
            def to_image(self, **_): raise pdfium.PdfiumError("rendering error")
            def close(self): self.closed = True

        class HealthyNativePage:
            images = []
            closed = False
            reads = 0
            def extract_text(self):
                self.reads += 1
                return "Readable native page with sufficient text."
            def close(self): self.closed = True

        failed, healthy = FailedRenderPage(), HealthyNativePage()

        class TwoPagePdf:
            pages = [failed, healthy]
            def __enter__(self): return self
            def __exit__(self, *_): return False

        db = FakeDB()
        with (
            mock.patch("pdfplumber.open", return_value=TwoPagePdf()),
            mock.patch.object(ocr, "_pdfium_render", side_effect=pdfium.PdfiumError("fallback render failed")),
            mock.patch.object(ocr, "enqueue_image", side_effect=AssertionError("no synthetic OCR image")),
            mock.patch.object(ocr.requests, "post", side_effect=AssertionError("provider forbidden")),
        ):
            ocr.scan_document(db, blob, did(blob), "city-pdf")

        self.assertTrue(failed.closed)
        self.assertTrue(healthy.closed)
        self.assertEqual(healthy.reads, 1)
        self.assertEqual(len(db.reviews), 1)
        review = next(iter(db.reviews.values()))
        self.assertEqual(review[1], "PDF page 1 render")
        self.assertEqual(review[2], ocr.PDF_PAGE_RENDER_REVIEW_VERSION)
        self.assertIn((did(blob), ocr.PDF_RENDER_FAILURE_VERSION), db.scans)
        self.assertNotIn((did(blob), ocr.VERSION), db.scans)
        self.assertEqual(db.tasks, [])

    def test_pdfium_fallback_queues_real_page_numbers_when_native_open_fails(self):
        blob = GOOD.read_bytes()
        queued = []
        from pdfminer.pdfparser import PDFSyntaxError
        db = FakeDB()
        with mock.patch("pdfplumber.open", side_effect=PDFSyntaxError("forced native-open failure")), \
             mock.patch.object(ocr, "enqueue_image", side_effect=lambda db, did, loc, image, kind, page=None: queued.append((loc, page)) or True), \
             mock.patch.object(ocr.requests, "post", side_effect=AssertionError("provider forbidden")):
            ocr.scan_document(db, blob, did(blob), "city-pdf")
        self.assertEqual(queued, [(f"PDF page {n}", n) for n in range(1, 9)])
        self.assertFalse(db.reviews)
        self.assertIn((did(blob), ocr.VERSION), db.scans)

    def test_lazy_pdf_pages_parse_error_uses_independent_renderer(self):
        blob = GOOD.read_bytes()
        queued = []
        from pdfplumber.utils.exceptions import PdfminerException

        class LazyBrokenPdf:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            @property
            def pages(self): raise PdfminerException("lazy page construction failed")

        db = FakeDB()
        with mock.patch("pdfplumber.open", return_value=LazyBrokenPdf()), \
             mock.patch.object(ocr, "enqueue_image", side_effect=lambda db, did, loc, image, kind, page=None: queued.append((loc, page)) or True):
            ocr.scan_document(db, blob, did(blob), "city-pdf")
        self.assertEqual(queued, [(f"PDF page {n}", n) for n in range(1, 9)])
        self.assertIn((did(blob), ocr.VERSION), db.scans)


if __name__ == "__main__":
    unittest.main(verbosity=2)

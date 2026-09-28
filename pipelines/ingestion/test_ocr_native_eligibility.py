"""Queued DANE PDF OCR must still be necessary under the current native parser."""

import hashlib
import io
import os
import unittest
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from . import ocr, pdf_sources, worker

FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "artifacts/automation-audit-2026-09-26/ocr-native-eligibility"
)
COVER = FIXTURES / "4b6186b79e3e.pdf"
COVER_SHA = "4b6186b79e3e8778e1944195b137b7bff154239d13e0631ec2bc0501dca9fc8d"
DIVIDERS = (
    Path(__file__).resolve().parents[2]
    / "artifacts/app-data-audit-2026-09-27/planning/ocr-timer-0005/aug2015-original.pdf"
)
DIVIDERS_SHA = "ae095b5adef81b5847e72812f7b44585c5b11e3ed57ed2a8ce005b73c6e32e3a"
READINGS = [
    {"text": "independent first reading", "tables": [], "review_notes": []},
    {"text": "different second reading", "tables": [], "review_notes": []},
]


class Result:
    def __init__(self, one=None, many=()):
        self.one, self.many = one, many

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class Database:
    def __init__(self, body, kind="monthly-pdf", page=1, day=date(2015, 4, 30)):
        self.body, self.kind, self.page, self.day = body, kind, page, day
        self.sql = []
        self.updates = []
        stream = io.BytesIO()
        Image.new("RGB", (600, 800), "white").save(stream, format="PNG")
        self.image = stream.getvalue()

    def execute(self, sql, params=()):
        self.sql.append(sql)
        if sql.startswith("SELECT id,content"):
            return Result()
        if sql.startswith("SELECT count(*) FROM source_ocr_attempt"):
            return Result(one=(0,))
        if sql.startswith("SELECT document_id,source_locator,image_id"):
            return Result(many=[("doc", "PDF page 1", "image", self.kind, self.page)])
        if sql.startswith("SELECT d.content,d.reference_period"):
            return Result(one=(self.body, "2015-04-30", self.day))
        if sql.startswith("SELECT result FROM source_ocr_result"):
            return Result()
        if sql.startswith("SELECT content FROM source_document"):
            return Result(one=(self.image,))
        if sql.startswith("UPDATE source_ocr_task"):
            self.updates.append((sql, params))
        return Result()


class Page:
    width, height = 600, 800

    def __init__(self, text):
        self.text = text
        self.images = [{"x0": 0, "x1": 600, "top": 150, "bottom": 600}]

    def extract_text(self):
        return self.text


class Book:
    def __init__(self, pages):
        self.pages = pages


class NativeEligibilityTests(unittest.TestCase):
    def drain(self, db):
        with (
            patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "test-only", "GEMINI_OCR_DAILY_REQUESTS": "40"},
            ),
            patch.object(ocr, "transcribe", side_effect=READINGS) as provider,
        ):
            result = ocr.drain(db, limit=1, scan_limit=0)
        return result, provider.call_count

    @unittest.skipUnless(DIVIDERS.exists(), "Real August2015 DANE PDF is required")
    def test_actual_short_dividers_do_not_read_cache_or_consume_provider_quota(self):
        body = DIVIDERS.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), DIVIDERS_SHA)
        for number in (11, 43):
            with self.subTest(page=number):
                db = Database(body, page=number, day=date(2015, 8, 31))
                result, calls = self.drain(db)
                self.assertEqual(
                    (calls, result["processed"], result["review"]), (0, 0, 1)
                )
                self.assertIn("no OCR needed", db.updates[0][1][0])
                self.assertFalse(
                    any("SELECT result FROM source_ocr_result" in sql for sql in db.sql)
                )
                self.assertFalse(
                    any("INSERT INTO source_ocr_attempt" in sql for sql in db.sql)
                )

    def test_short_heading_with_substantial_price_image_still_needs_ocr(self):
        for title in ("Frutas frescas", "Abastecimiento"):
            page = Page(title)
            self.assertTrue(pdf_sources.native_price_page_failure(page, title, []))

    def test_small_body_image_is_not_mistaken_for_decorative_footer(self):
        page = Page("Frutas frescas")
        page.images = [{"x0": 100, "x1": 350, "top": 200, "bottom": 275}]
        self.assertFalse(pdf_sources.has_table_sized_image(page))
        self.assertTrue(pdf_sources.native_price_page_failure(page, page.text, []))

    def test_full_page_scan_and_corrupt_font_without_images_still_need_ocr(self):
        scan = Page("")
        scan.images = [{"x0": 0, "x1": 600, "top": 0, "bottom": 800}]
        self.assertTrue(pdf_sources.native_price_page_failure(scan, "", []))
        corrupt = Page("(cid:34)" * 100)
        corrupt.images = []
        self.assertTrue(
            pdf_sources.native_price_page_failure(corrupt, corrupt.text, [])
        )

    def test_corrupt_font_still_needs_ocr_when_some_prices_were_parsed(self):
        # Extracting numbers does not prove corrupt product/location text works.
        text = "(cid:34)" * 100
        self.assertTrue(
            pdf_sources.native_price_page_failure(Page(text), text, [("native",)])
        )

    @unittest.skipUnless(
        COVER.exists(), "Real April2015 DANE cover fixture is required"
    )
    def test_actual_old_cover_is_reviewed_without_reading_cache_or_calling_provider(
        self,
    ):
        body = COVER.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), COVER_SHA)
        db = Database(body)
        result, calls = self.drain(db)
        self.assertEqual((calls, result["processed"], result["review"]), (0, 0, 1))
        self.assertIn("no OCR needed", db.updates[0][1][0])
        self.assertFalse(
            any("SELECT result FROM source_ocr_result" in sql for sql in db.sql)
        )
        self.assertFalse(any("INSERT INTO source_ocr_attempt" in sql for sql in db.sql))
        self.assertFalse(any(sql.startswith(("DELETE", "TRUNCATE")) for sql in db.sql))
        self.assertFalse(any("UPDATE source_ocr_result" in sql for sql in db.sql))

    def test_native_headings_with_image_price_grid_still_use_ocr(self):
        text = "Abril de 2015\nPrecio $/Kg\nBogotá Medellín Cali"
        page = Page(text)
        self.assertFalse(ocr.needs_ocr(page, text))
        db = Database(b"fixture")
        with (
            patch.object(
                pdf_sources.pdfplumber, "open", return_value=nullcontext(Book([page]))
            ),
            patch.object(worker, "parse_pdf_pages", return_value=iter(())),
        ):
            result, calls = self.drain(db)
        self.assertEqual((calls, result["processed"]), (2, 1))

    def test_corrupt_native_font_still_uses_ocr(self):
        page = Page("(cid:34)" * 100)
        db = Database(b"fixture", kind="daily-pdf")
        with (
            patch.object(
                pdf_sources.pdfplumber, "open", return_value=nullcontext(Book([page]))
            ),
            patch.object(worker, "parse_pdf_pages", return_value=iter(())),
        ):
            result, calls = self.drain(db)
        self.assertEqual((calls, result["processed"]), (2, 1))

    def test_percentage_chart_is_nonprice_even_with_money_text_elsewhere(self):
        page = Page("Cuadro 1 Variación porcentual\nPrecio $/Kg Bogotá Medellín Cali")
        db = Database(b"fixture")
        with (
            patch.object(
                pdf_sources.pdfplumber, "open", return_value=nullcontext(Book([page]))
            ),
            patch.object(worker, "parse_pdf_pages", return_value=iter(())),
        ):
            result, calls = self.drain(db)
        self.assertEqual((calls, result["review"]), (0, 1))

    def test_imaged_continuation_requires_preceding_native_price_grid(self):
        pages = [Page("native grid"), Page("Precios nacionales, continuación")]
        with (
            patch.object(
                pdf_sources.pdfplumber,
                "open",
                side_effect=lambda *a, **k: nullcontext(Book(pages)),
            ),
            patch.object(
                worker,
                "parse_pdf_pages",
                side_effect=[iter(()), iter([("native",)]), iter(()), iter(())],
            ),
        ):
            self.assertTrue(
                pdf_sources.queued_price_page_needs_ocr(
                    b"x", date(2015, 4, 30), "monthly-pdf", 2
                )
            )
            self.assertFalse(
                pdf_sources.queued_price_page_needs_ocr(
                    b"x", date(2015, 4, 30), "monthly-pdf", 2
                )
            )

    def test_existing_native_grid_is_successful_extraction(self):
        page = Page("Precio $/Kg Bogotá Medellín Cali")
        self.assertFalse(
            pdf_sources.native_price_page_failure(page, page.text, [("native",)])
        )

    def test_unrelated_pork_and_city_queues_keep_existing_behavior(self):
        for kind in ("colombia-pork-pdf", "city-pdf"):
            with self.subTest(kind=kind):
                db = Database(b"fixture", kind=kind)
                with patch.object(
                    pdf_sources,
                    "queued_price_page_needs_ocr",
                    side_effect=AssertionError("wrong scope"),
                ):
                    result, calls = self.drain(db)
                self.assertEqual((calls, result["processed"]), (2, 1))
                self.assertFalse(
                    any("SELECT d.content,d.reference_period" in sql for sql in db.sql)
                )

    def test_invalid_queued_page_fails_closed_without_provider_call(self):
        db = Database(b"fixture", page=20)
        with patch.object(
            pdf_sources.pdfplumber,
            "open",
            return_value=nullcontext(Book([Page("native")])),
        ):
            result, calls = self.drain(db)
        self.assertEqual((calls, result["review"]), (0, 1))
        self.assertIn("invalid source page", db.updates[0][1][0])

    def test_retained_original_date_allows_recheck_after_asset_pointer_moves(self):
        db = Database(b"fixture", day=None)
        with patch.object(
            pdf_sources, "queued_price_page_needs_ocr", return_value=False
        ) as decision:
            result, calls = self.drain(db)
        self.assertEqual((calls, result["review"]), (0, 1))
        decision.assert_called_once_with(
            b"fixture", date(2015, 4, 30), "monthly-pdf", 1
        )


if __name__ == "__main__":
    unittest.main()

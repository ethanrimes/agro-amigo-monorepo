"""Two real publisher aliases and a blank-page OCR boundary, with original proofs."""

import io
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import openpyxl
import pdfplumber
from reportlab.pdfgen import canvas

from . import dane_weekly, pdf_link_recovery, worker
from .pdf_sources import native_price_page_failure, queued_price_page_needs_ocr

FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "artifacts/source-verification-2026-09-28/dane-prices/originals"
)
DAILY = next(u for u, a in pdf_link_recovery.ALIASES.items() if a.kind == "daily-pdf")
WEEKLY = next(
    u for u, a in pdf_link_recovery.ALIASES.items() if a.kind == "dane-weekly-pdf"
)


def pdf_day(day="25 de julio de 2014"):
    output = io.BytesIO()
    c = canvas.Canvas(output)
    c.drawString(36, 780, day)
    c.drawString(36, 760, "SIPSA - PRECIOS MAYORISTAS")
    c.save()
    return output.getvalue()


class PDFAliasSafety(unittest.TestCase):
    def test_only_exact_missing_pdf_alias_can_fetch(self):
        fetcher = Mock(return_value=pdf_day())
        for status in (200, 304, 403, 429, 500, 503):
            self.assertIsNone(
                pdf_link_recovery.recover_link(
                    DAILY, status, date(2014, 7, 25), fetcher, kind="daily-pdf"
                )
            )
        for url in (
            DAILY + "?x=1",
            DAILY.replace("www.dane.gov.co", "evil.test"),
            DAILY.lower(),
        ):
            self.assertIsNone(
                pdf_link_recovery.recover_link(
                    url, 404, date(2014, 7, 25), fetcher, kind="daily-pdf"
                )
            )
        self.assertIsNone(
            pdf_link_recovery.recover_link(
                DAILY, 404, date(2014, 7, 25), fetcher, kind="monthly-pdf"
            )
        )
        fetcher.assert_not_called()

    def test_html_and_wrong_printed_date_never_replace_original(self):
        for body in (b"<html>not PDF</html>", pdf_day("24 de julio de 2014")):
            with self.assertRaises(ValueError):
                pdf_link_recovery.recover_link(
                    DAILY, 404, date(2014, 7, 25), lambda _, body=body: body, kind="daily-pdf"
                )
        fetcher = Mock()
        with self.assertRaises(ValueError):
            pdf_link_recovery.recover_link(
                DAILY, 404, date(2014, 7, 24), fetcher, kind="daily-pdf"
            )
        fetcher.assert_not_called()

    def test_resolution_keeps_alias_parent_and_validates_changed_bytes(self):
        result = pdf_link_recovery.recover_link(
            DAILY, 410, date(2014, 7, 25), lambda _: pdf_day(), kind="daily-pdf"
        )
        self.assertEqual(result.archive_day, date(2014, 7, 25))
        self.assertEqual(result.evidence["original_url"], DAILY)
        self.assertIn("julio-de-2014", result.evidence["archive_url"])
        self.assertEqual(result.evidence["validated_price_rows"], 0)
        self.assertFalse(result.evidence["matches_audited_bytes"])

    def test_module_is_in_deployment_fingerprint(self):
        self.assertIn("pipelines/ingestion/pdf_link_recovery.py", worker.RELEASE_FILES)

    @unittest.skipUnless(
        (FIXTURES / "mayoristas_julio_25_2014.pdf").exists(),
        "original fixture unavailable",
    )
    def test_actual_daily_original_preserves_printed_date_and_canonical_link(self):
        body = (FIXTURES / "mayoristas_julio_25_2014.pdf").read_bytes()
        result = pdf_link_recovery.recover_link(
            DAILY, 404, date(2014, 7, 25), lambda _, body=body: body, kind="daily-pdf"
        )
        self.assertTrue(result.evidence["matches_audited_bytes"])
        self.assertEqual(result.evidence["pages"], 3)
        self.assertIn("25 de julio de 2014", result.evidence["printed_heading"])

    @unittest.skipUnless(
        (FIXTURES / "bol_23jul_al_29jul_2022.pdf").exists(),
        "original fixture unavailable",
    )
    def test_actual_weekly_all_4343_literal_triples_match_independent_xlsx(self):
        rule = pdf_link_recovery.ALIASES[WEEKLY]
        body = (FIXTURES / "bol_23jul_al_29jul_2022.pdf").read_bytes()
        result = pdf_link_recovery.recover_link(
            WEEKLY, 404, None, lambda _: body, kind="dane-weekly-pdf"
        )
        self.assertEqual(result.archive_day, date(2022, 7, 29))
        self.assertTrue(result.evidence["matches_audited_bytes"])
        self.assertEqual(
            (result.evidence["validated_price_rows"], result.evidence["review_rows"]),
            (4207, 136),
        )
        rows = dane_weekly.parse_pdf(body, rule.canonical_url)
        book = openpyxl.load_workbook(
            FIXTURES / "anex_23jul_al_29jul_2022.xlsx", data_only=True, read_only=True
        )
        expected = {}
        for sheet in book:
            for cells in sheet.values:
                if (
                    len(cells) >= 5
                    and isinstance(cells[0], str)
                    and isinstance(cells[1], str)
                    and all(
                        isinstance(v, (int, float)) and not isinstance(v, bool)
                        for v in cells[2:5]
                    )
                ):
                    expected[(cells[0].casefold().strip(), cells[1].strip())] = tuple(
                        float(v) for v in cells[2:5]
                    )
        actual = {
            (r["product_name"].casefold(), r["market"]): (
                r["min"],
                r["max"],
                r["price"] if r["price"] is not None else r["details"]["literal_mean"],
            )
            for r in rows
        }
        self.assertEqual(len(expected), 4343)
        self.assertEqual(actual, expected)
        fixed = [r for r in rows if r["details"].get("native_heading_recovery")]
        self.assertEqual(
            {r["product_name"] for r in fixed},
            {"Guayaba pera", "Tomate de árbol", "Uva importada"},
        )
        self.assertTrue(
            all(
                "comntinuación" in r["details"]["literal_product_heading"]
                for r in fixed
            )
        )
        guava = next(
            r
            for r in fixed
            if r["product_name"] == "Guayaba pera"
            and r["market"] == "Bucaramanga, Centroabastos"
        )
        self.assertEqual(
            (guava["min"], guava["max"], guava["price"]), (1360, 1600, 1425)
        )
        self.assertEqual(guava["source_page"], 24)
        self.assertEqual({r["date"] for r in rows}, {"2022-07-29"})
        self.assertEqual({r["period_start"] for r in rows}, {"2022-07-23"})


def image(top, bottom, body=b"logo"):
    return {
        "x0": 0,
        "x1": 600,
        "top": top,
        "bottom": bottom,
        "stream": SimpleNamespace(get_data=lambda: body),
    }


class BlankStationerySafety(unittest.TestCase):
    def page(self, images=None):
        pictures = images or [image(0, 70), image(750, 790, b"footer")]
        previous = SimpleNamespace(
            images=[image(0, 70), image(750, 790, b"footer")],
            extract_text=lambda: "Readable dated narrative " * 10,
        )
        page = SimpleNamespace(
            images=pictures,
            width=600,
            height=800,
            page_number=2,
            pdf=SimpleNamespace(pages=[previous]),
        )
        return page

    def test_only_identical_repeated_margin_art_is_skipped(self):
        with patch("pipelines.ingestion.ocr.needs_ocr", return_value=True) as needs:
            self.assertFalse(native_price_page_failure(self.page(), " ", []))
            needs.assert_not_called()

    def test_body_raster_unique_margin_and_corrupt_text_still_need_ocr(self):
        for page, text in [
            (self.page([image(100, 170, b"price grid")]), ""),
            (self.page([image(0, 70, b"new price grid")]), ""),
            (self.page(), "(cid:123)"),
        ]:
            with (
                self.subTest(text=text),
                patch("pipelines.ingestion.ocr.needs_ocr", return_value=True) as needs,
            ):
                self.assertTrue(native_price_page_failure(page, text, []))
                needs.assert_called_once()

    @unittest.skipUnless(
        (FIXTURES / "mayoristas_oct_25_2012.pdf").exists(),
        "original fixture unavailable",
    )
    def test_actual_blank_october_page_keeps_every_readable_page_off_ocr(self):
        body = (FIXTURES / "mayoristas_oct_25_2012.pdf").read_bytes()
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            self.assertFalse((pdf.pages[3].extract_text() or "").strip())
            self.assertEqual(len(pdf.pages[3].images), 2)
        for page in range(1, 5):
            self.assertFalse(
                queued_price_page_needs_ocr(body, date(2012, 10, 25), "daily-pdf", page)
            )


if __name__ == "__main__":
    unittest.main()

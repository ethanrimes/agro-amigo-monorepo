"""The archived June 2019 Cuadro 6 prints two incompatible date ranges."""

import hashlib
import io
import unittest
from pathlib import Path

import pdfplumber

from . import dane_weekly as weekly


URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Sem_22jun_2019__28jun_2019.pdf"
)
FIXTURE = Path(__file__).parent / "testdata/dane_weekly_2019_06_22_pages42_45.pdf"


class June2019ConflictingPrintedPeriods(unittest.TestCase):
    def test_original_cuadro_six_keeps_conflicting_page_for_review(self):
        # Exact original PDF: SHA-256
        # 7910fe69f3798cb8811f6dbfd20b627b618ca323bb4f6b15f9e6e545dcd04e4b.
        # This fixture retains its pages 42-45, preceded by 41 blank pages so
        # source_page and the source locators remain the printed page numbers.
        body = FIXTURE.read_bytes()
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "5f6db22a125db40b46e173bf8287dd4e3ff1016c2d06ce388d5c81041a421cd5",
        )
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            for page in (42, 43, 45):
                self.assertIn(
                    "2019 (22 al 28 de junio)",
                    pdf.pages[page - 1].extract_text(),
                )
            self.assertIn(
                "2019 (1 al 28 de junio) 2019 (22 al 28 de junio)",
                pdf.pages[43].extract_text(),
            )
        rows = weekly.parse_pdf(body, URL)
        self.assertEqual(len(rows), 297)
        for page, count in ((42, 85), (43, 80), (45, 47)):
            with self.subTest(page=page):
                page_rows = [row for row in rows if row["source_page"] == page]
                self.assertEqual(len(page_rows), count)
                self.assertTrue(all(row["price"] is not None for row in page_rows))
                self.assertEqual(
                    {(row["period_start"], row["date"]) for row in page_rows},
                    {("2019-06-22", "2019-06-28")},
                )

        conflicting = [row for row in rows if row["source_page"] == 44]
        self.assertEqual(len(conflicting), 85)
        self.assertTrue(all(row["price"] is None for row in conflicting))
        self.assertEqual(
            {(row["period_start"], row["date"]) for row in conflicting},
            {("2019-06-22", "2019-06-28")},
        )
        for row in conflicting:
            self.assertEqual(
                row["details"]["literal_printed_period_headings"],
                ["2019 (1 al 28 de junio)", "2019 (22 al 28 de junio)"],
            )
            self.assertEqual(row["details"]["literal_min"], row["min"])
            self.assertEqual(row["details"]["literal_max"], row["max"])
            self.assertGreater(row["details"]["literal_mean"], 0)
            self.assertIn("periodos contradictorios", row["details"]["quality_issue"])
        sample = next(
            row for row in conflicting
            if row["source_locator"] == "PDF page 44,table 1,column 1,line 2"
        )
        self.assertEqual(
            (sample["product_name"], sample["market"], sample["min"],
             sample["max"], sample["details"]["literal_mean"]),
            ("Fríjol Uribe rosado", "Medellín, Central Mayorista de Antioquia",
             4400, 4700, 4575),
        )

    def test_conflicting_heading_requires_an_explicit_url_match(self):
        body = FIXTURE.read_bytes()
        with self.assertRaisesRegex(ValueError, "conflicting printed periods"):
            weekly.parse_pdf(body, "undated-weekly.pdf")


if __name__ == "__main__":
    unittest.main()

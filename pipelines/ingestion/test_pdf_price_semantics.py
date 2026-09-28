"""Monetary proof must belong to the matrix, for native and OCR extraction."""

import io
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pdfplumber

from .pdf_sources import (
    VerifiedPDFPage,
    legacy_pdf_price_needs_review,
    parse_archived_price_pdf,
)
from .worker import SourceDateMismatch, parse_pdf, parse_pdf_pages

FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "artifacts/automation-audit-2026-09-26/dane/originals"
)


def matrix(header="Precio $/Kg · Julio de 2012"):
    return [
        [header, None, None, None, None, None, None],
        ["Producto", "Bogotá", None, "Medellín", None, "Cali", None],
        [None, "Precio", "Var%", "Precio", "Var%", "Precio", "Var%"],
        ["Ahuyama", "1.000", "63,99", "2.000", "0,09", "3.000", "15"],
    ]


class PriceSemantics(unittest.TestCase):
    def parse(self, tables, text="", day=date(2012, 7, 31), monthly=True):
        page = VerifiedPDFPage({"text": text, "tables": tables})
        return list(parse_pdf_pages([page], day, monthly, allow_empty=True))

    def test_verified_ocr_only_price_columns_and_versioned_provenance(self):
        rows = self.parse([matrix()])
        self.assertEqual([r[6] for r in rows], [1000, 2000, 3000])
        self.assertEqual({r[1] for r in rows}, {"dane-monthly-summary"})
        self.assertTrue(all(r[0].endswith("; monthly-pdf-v4") for r in rows))
        self.assertTrue(all(r[-1]["parser_version"] == "monthly-pdf-v4" for r in rows))

    def test_price_words_elsewhere_never_authorize_percentage_grid(self):
        table = [
            ["Producto", "Bogotá", "Medellín", "Cali"],
            ["Arveja", "63,99", "0,09", "15"],
        ]
        self.assertEqual(
            self.parse(
                [table], "Precio $/Kg Julio de 2012. Cuadro: Variación porcentual"
            ),
            [],
        )

    def test_each_table_requires_its_own_monetary_evidence(self):
        rows = self.parse([matrix(), matrix("Variación porcentual Julio de 2012")])
        self.assertEqual(len(rows), 3)
        self.assertTrue(all("table 1," in row[0] for row in rows))

    def test_missing_and_mismatched_printed_periods_fail_closed(self):
        self.assertEqual(self.parse([matrix("Precio $/Kg")]), [])
        with self.assertRaises(SourceDateMismatch):
            self.parse([matrix("Precio $/Kg · Agosto de 2012")])
        with self.assertRaises(SourceDateMismatch):
            self.parse(
                [matrix("Precio $/Kg · 26 de junio de 2012")],
                day=date(2012, 6, 27),
                monthly=False,
            )

    def test_legacy_review_predicate_is_narrow_and_requires_verified_version(self):
        self.assertTrue(legacy_pdf_price_needs_review("dane-monthly-bulletin", {}))
        self.assertTrue(legacy_pdf_price_needs_review("dane-monthly-bulletin", None))
        self.assertFalse(legacy_pdf_price_needs_review("dane-monthly-summary", {}))
        self.assertFalse(
            legacy_pdf_price_needs_review(
                "dane-monthly-bulletin", {"parser_version": "monthly-pdf-v4"}
            )
        )

    @unittest.skipUnless(
        (FIXTURES / "bol-SIPSAMensual-jul2026.pdf").exists(),
        "official original is an audit fixture",
    )
    def test_actual_july2026_percentage_tables_never_become_prices_or_ocr(self):
        data = (FIXTURES / "bol-SIPSAMensual-jul2026.pdf").read_bytes()
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            self.assertIn("63,99", str(pdf.pages[12].extract_tables()))
            self.assertEqual(
                list(
                    parse_pdf_pages(
                        pdf.pages, date(2026, 7, 31), True, allow_empty=True
                    )
                ),
                [],
            )
        with (
            patch("pipelines.ingestion.pdf_sources.verified_page") as ocr,
            self.assertRaisesRegex(ValueError, "No supported price grids"),
        ):
            list(
                parse_archived_price_pdf(
                    MagicMock(), data, "original", date(2026, 7, 31), "monthly-pdf"
                )
            )
        ocr.assert_not_called()

    @unittest.skipUnless(
        (FIXTURES / "mensual_julio_2012.pdf").exists(),
        "official original is an audit fixture",
    )
    def test_actual_2012_monthly_and_daily_price_tables_remain_readable(self):
        monthly = list(
            parse_pdf(
                (FIXTURES / "mensual_julio_2012.pdf").read_bytes(),
                date(2012, 7, 31),
                True,
            )
        )
        daily = list(
            parse_pdf(
                (FIXTURES / "mayoristas_junio_27_2012.pdf").read_bytes(),
                date(2012, 6, 27),
            )
        )
        self.assertEqual(len(monthly), 353)
        self.assertEqual(monthly[0][3:7], ("Ahuyama", "Armenia", "kg", 545))
        self.assertEqual(len(daily), 120)
        self.assertEqual(daily[0][3:7], ("Ahuyama", "Bogotá", "kg", 775))


if __name__ == "__main__":
    unittest.main()

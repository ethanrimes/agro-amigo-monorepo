"""Only exact duplicate header glyphs may recover a native weekly price table."""

import hashlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

import pdfplumber
from reportlab.pdfgen import canvas

from . import dane_weekly as weekly

FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "artifacts/extraction-robustness-2026-09-27/weekly"
)
REAL_PDF = FIXTURES / "ocr-replay-bol-SIPSASemanal-29ago04sep-2026.pdf"
REAL_SHA = "2ec00126cdac099b37dab085bb7e7caa4b53fc9437c1c9115a09a20afa132b5d"
REAL_URL = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSASemanal-29ago04sep-2026.pdf"


def overprinted_pdf(
    *, duplicate=True, offset=0, body_duplicate=False, missing_mean=False
):
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(612, 792))
    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        36,
        700,
        "Cuadro 2. Mercados mayoristas. Precios de venta de verduras y hortalizas",
    )
    pdf.drawString(36, 684, "19 al 25 de septiembre de 2026")
    for side, origin in enumerate((36, 320)):
        pdf.drawString(origin, 665, "Pesos por kilogramo")
        for x, heading in ((115, "Mínimo"), (155, "Máximo"), (195, "Medio")):
            if missing_mean and side == 1 and heading == "Medio":
                continue
            pdf.drawString(origin + x, 647, heading)
            if duplicate and side == 1:
                pdf.drawString(origin + x + offset, 647, heading)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(origin, 628, "Acelga")
        pdf.setFont("Helvetica", 9)
        pdf.drawString(origin, 610, "Bogotá" if side == 0 else "Armenia")
        for x, value in ((115, "333"), (155, "533"), (195, "418")):
            pdf.drawString(origin + x, 610, value)
            if body_duplicate and side == 1:
                pdf.drawString(origin + x, 610, value)
    pdf.save()
    return stream.getvalue()


class WeeklyOverprint(unittest.TestCase):
    def test_normal_headers_do_not_run_fallback(self):
        with patch.object(weekly, "_overprint_column_headers") as fallback:
            rows = weekly.parse_pdf(overprinted_pdf(duplicate=False), "weekly.pdf")
        fallback.assert_not_called()
        self.assertEqual(len(rows), 2)

    def test_exact_overprint_recovers_only_headers_preserving_every_body_field(self):
        original = overprinted_pdf()
        with (
            patch.object(weekly, "_overprint_column_headers", return_value=None),
            self.assertRaises(weekly.NormalExtractionFailed) as failed,
        ):
            weekly.parse_pdf(original, "weekly.pdf")
        self.assertEqual(failed.exception.required_pages, (1,))
        recovered = weekly.parse_pdf(original, "weekly.pdf")
        normal = weekly.parse_pdf(overprinted_pdf(duplicate=False), "weekly.pdf")
        for row in recovered:
            self.assertEqual(
                row["details"].pop("native_header_recovery"),
                "exact_overprinted_glyphs",
            )
        self.assertEqual(recovered, normal)
        self.assertEqual(
            [(row["min"], row["max"], row["price"]) for row in recovered],
            [(333, 533, 418), (333, 533, 418)],
        )

    def test_noncoincident_glyphs_are_not_guessed(self):
        with self.assertRaises(weekly.NormalExtractionFailed) as failed:
            weekly.parse_pdf(overprinted_pdf(offset=0.1), "weekly.pdf")
        self.assertEqual(failed.exception.required_pages, (1,))

    def test_duplicate_price_body_is_not_repaired_or_published(self):
        with self.assertRaises(weekly.NormalExtractionFailed) as failed:
            weekly.parse_pdf(overprinted_pdf(body_duplicate=True), "weekly.pdf")
        self.assertEqual(failed.exception.required_pages, (1,))

    def test_missing_header_still_requires_ocr_after_deduplication(self):
        body = overprinted_pdf(missing_mean=True)
        with self.assertRaises(weekly.NormalExtractionFailed) as failed:
            weekly.parse_pdf(body, "weekly.pdf")
        self.assertEqual(failed.exception.required_pages, (1,))
        reading = {
            "text": "Cuadro 2. Mercados mayoristas. Precios de venta de verduras y hortalizas. 19 al 25 de septiembre de 2026. Pesos por kilogramo",
            "tables": [
                [
                    ["Productos y mercados", "Mínimo", "Máximo", "Medio", "Tendencia"],
                    ["Acelga", "", "", "", ""],
                    ["Bogotá", "333", "533", "418", "="],
                ]
            ],
            "review_notes": [],
        }
        rows = weekly.parse_with_ocr(
            body, "weekly.pdf", "dane-weekly-pdf", {1: reading}
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            (rows[0]["product_name"], rows[0]["market"], rows[0]["price"]),
            ("Acelga", "Bogotá", 418),
        )

    @unittest.skipUnless(REAL_PDF.exists(), "Retained September4 original is required")
    def test_actual_overprinted_headers_recover_full_native_source_and_literal_anchors(
        self,
    ):
        body = REAL_PDF.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), REAL_SHA)
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            page = pdf.pages[67]
            self.assertEqual(len(page.images), 0)
            self.assertIn("MMíínniimmoo", page.extract_text())
            cleaned = page.dedupe_chars(
                tolerance=0, extra_attrs=("fontname", "size", "x1", "bottom")
            )
            self.assertEqual(len(page.chars) - len(cleaned.chars), 73)
        with (
            patch.object(weekly, "_overprint_column_headers", return_value=None),
            self.assertRaises(weekly.NormalExtractionFailed) as failed,
        ):
            weekly.parse_pdf(body, REAL_URL)
        self.assertEqual(failed.exception.required_pages, (68, 69))
        rows = weekly.parse_pdf(body, REAL_URL)
        self.assertEqual(len(rows), 4567)
        self.assertEqual(sum(row["price"] is not None for row in rows), 4435)
        self.assertEqual(
            {
                row["source_page"]
                for row in rows
                if row["details"].get("native_header_recovery")
            },
            {68, 69},
        )
        for product, market, expected in (
            ("Sal yodada", "Santa Marta (Magdalena)", (2776, 2864, 2813)),
            ("Salsa de tomate doy pack", "Armenia, Mercar", (16667, 17407, 17037)),
        ):
            selected = [
                row
                for row in rows
                if row["product_name"] == product and row["market"] == market
            ]
            self.assertEqual(len(selected), 1)
            row = selected[0]
            self.assertEqual((row["min"], row["max"], row["price"]), expected)
            self.assertEqual(
                (
                    row["source_page"],
                    row["date"],
                    row["period_start"],
                    row["currency"],
                    row["unit"],
                ),
                (68, "2026-09-04", "2026-08-29", "COP", "kg"),
            )


if __name__ == "__main__":
    unittest.main()

"""Original-backed Corabastos native ID table and blank-source boundaries."""

import hashlib
import unittest
from pathlib import Path

from . import colombia_sources


FIXTURES = Path(__file__).parent / "testdata"
MARCH = FIXTURES / "961bf016177e-Boletin_diario_20260309-sn.pdf"
FEBRUARY = FIXTURES / "14fcf6c96f01-Boletin-18febrero2025-1.pdf"


class CorabastosIdCompactOriginalTests(unittest.TestCase):
    def test_march9_native_id_table_preserves_literal_quality_and_package(self):
        body = MARCH.read_bytes()
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "14dc13b124e8ffccc809834f75816f0415bcdcd4285f3142a9194c070a98ca5a",
        )
        rows = colombia_sources.parse(
            body,
            "https://corabastos.com.co/wp-content/uploads/2026/03/Boletin_diario_20260309-sn.pdf",
            "colombia-corabastos-pdf",
        )
        self.assertEqual(len(rows), 346)  # 173 printed rows, two quality columns.
        eligible = [r for r in rows if r["price"] is not None and not r["details"].get("quality_issue")]
        self.assertEqual(len(eligible), 232)
        self.assertEqual(len(rows) - len(eligible), 114)

        def literal(product, quality, price, quantity, presentation):
            matches = [
                r for r in eligible
                if r["product_name"] == product and r["series"] == "corabastos-quality-" + quality
            ]
            self.assertEqual(len(matches), 1)
            row = matches[0]
            self.assertEqual(row["date"], "2026-03-09")
            self.assertEqual(row["price"], price)
            self.assertEqual(row["details"]["quantity"], quantity)
            self.assertEqual(row["details"]["presentation"], presentation)
            self.assertEqual(row["unit"], f"{presentation} · cantidad {quantity}")
            self.assertEqual(row["details"]["source_page"], 1)
            self.assertIn("PDF page 1, ID table y", row["source_locator"])

        literal("Banano Criollo", "extra", 32000, 30, "CAJA DE MADERA")
        literal("Banano Criollo", "primera", 30000, 30, "CAJA DE MADERA")
        literal("Limon Comun", "extra", 120000, 70, "BULTO")
        literal("Mora De Castilla", "primera", 30000, 7, "CAJA")
        self.assertTrue(
            all(r["price"] is None and r["details"]["quality_issue"] for r in rows
                if r["source_locator"].startswith("PDF page 3, ID table"))
        )

    def test_february18_original_has_no_date_or_price_table_to_ocr(self):
        body = FEBRUARY.read_bytes()
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "c4f5b171fddb72e9f666cf337cb939942fe3c695c8b480fbd9e5544d059ca70d",
        )
        rows = colombia_sources.parse(
            body,
            "https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-18febrero2025-1.pdf",
            "colombia-corabastos-pdf",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_locator"], "PDF pages 1-7, empty publisher export")
        self.assertIsNone(rows[0]["price"])
        self.assertNotIn("date", rows[0])
        self.assertIn("no observation date or price table", rows[0]["details"]["quality_issue"])


if __name__ == "__main__":
    unittest.main()

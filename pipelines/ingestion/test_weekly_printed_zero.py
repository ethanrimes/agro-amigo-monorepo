"""One literal zero must not discard every independent weekly PDF quote."""

import unittest
from datetime import date
from pathlib import Path

from . import dane_weekly

URL = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSASemanal-15jun-21jun-2024.pdf"
ORIGINAL = Path(__file__).parent / "testdata/bol-SIPSASemanal-15jun-21jun-2024.pdf"


class PrintedZero(unittest.TestCase):
    def test_native_zero_is_reviewed_while_adjacent_quotes_survive(self):
        rows = dane_weekly.parse_pdf(ORIGINAL.read_bytes(), URL)
        self.assertEqual(len(rows), 4421)
        target = next(r for r in rows if r["product_name"] == "Remolacha"
                      and r["market"] == "Neiva, Surabastos")
        self.assertIsNone(target["price"])
        self.assertEqual((target["details"]["literal_min"], target["details"]["literal_max"],
                          target["details"]["literal_mean"]), (0, 1152, 989))
        self.assertEqual(target["source_page"], 18)
        self.assertEqual(target["date"], "2024-06-21")
        self.assertIn("cero", target["details"]["quality_issue"])
        neighbour = next(r for r in rows if r["product_name"] == "Remolacha"
                         and r["market"] == "Pereira, Mercasa")
        self.assertEqual((neighbour["min"], neighbour["max"], neighbour["price"]), (1000, 1500, 1200))

    def test_unvalidated_zero_remains_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            dane_weekly._row("Remolacha", "Neiva, Surabastos", 0, 1152, 989, "-",
                             "Verduras", (date(2024, 6, 15), date(2024, 6, 21)), "unbound")


if __name__ == "__main__":
    unittest.main()

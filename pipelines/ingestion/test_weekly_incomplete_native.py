"""Exact DANE originals with readable, incomplete weekly price cells."""

import hashlib
import unittest
from datetime import date
from pathlib import Path

from . import dane_weekly as weekly

FIXTURES = Path(__file__).parent / "testdata"


class IncompleteNativeWeekly(unittest.TestCase):
    def test_2026_august_missing_minimum_is_literal_review(self):
        name = "bol-SIPSASemanal-15ago21agos-2026.pdf"
        body = (FIXTURES / name).read_bytes()
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "319c126e46e464b177beb8d44d68cfd89c689715da0f90bf55813be9b970b947",
        )
        rows = weekly.parse_pdf(body, name)
        self.assertEqual((len(rows), sum(r["price"] is None for r in rows)), (4538, 134))
        review = next(
            r
            for r in rows
            if r["source_locator"] == "PDF page 49,table 1,column 1,line 8"
        )
        self.assertEqual(
            (review["product_name"], review["market"], review["price"]),
            ("Carne de cerdo, pernil sin hueso", "Pereira, La 41-Impala", None),
        )
        self.assertEqual((review["min"], review["max"]), (None, 23000))
        self.assertEqual(
            review["details"]["literal_missing_columns"], ["Mínimo"]
        )
        self.assertEqual(review["details"]["literal_mean"], 23000)
        self.assertEqual(
            next(
                r
                for r in rows
                if r["source_page"] == 49
                and r["product_name"] == "Carne de res, bola de brazo"
                and r["market"] == "Bogotá, D.C., Paloquemao"
            )["price"],
            33000,
        )

    def test_missing_minimum_requires_explicit_review_scope(self):
        with self.assertRaises(ValueError):
            weekly._row(
                "Carne de cerdo, pernil sin hueso",
                "Pereira, La 41-Impala",
                None,
                23000,
                23000,
                "=",
                "carnes",
                (date(2026, 8, 15), date(2026, 8, 21)),
                "PDF page 49",
            )

    def test_2022_page_start_continuations_remain_missing_product_reviews(self):
        name = "Sem_19feb_2022_25feb_2022.pdf"
        body = (FIXTURES / name).read_bytes()
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "861e13a0d9aa0e5367e5368a1f4d8cba39d61a261a7fdd1fc00b53bf55439eb5",
        )
        rows = weekly.parse_pdf(body, name)
        self.assertEqual((len(rows), sum(r["price"] is None for r in rows)), (4377, 134))
        unbound = [r for r in rows if r["source_page"] == 19 and not r["product_name"]]
        self.assertEqual(
            [(r["market"], r["details"]["literal_mean"]) for r in unbound],
            [
                ("Buenaventura (Valle del Cauca)", 920),
                ("Cali, Cavasa", 679),
                ("Yopal (Casanare)", 1333),
            ],
        )
        self.assertTrue(all(r["price"] is None for r in unbound))
        self.assertEqual(
            next(
                r
                for r in rows
                if r["source_page"] == 19
                and r["product_name"] == "Zanahoria bogotana"
                and r["market"] == "Barranquilla, Barranquillita"
            )["price"],
            1546,
        )


if __name__ == "__main__":
    unittest.main()

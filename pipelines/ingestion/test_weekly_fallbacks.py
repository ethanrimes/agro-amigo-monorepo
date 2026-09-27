"""Verified weekly native fallbacks; uncertain source rows never become prices."""

import unittest
from datetime import date
from pathlib import Path

from pipelines.ingestion import dane_weekly as weekly
from pipelines.ingestion.test_dane_weekly import workbook

FIXTURES = Path("artifacts/extraction-robustness-2026-09-27/weekly")


class WeeklyFallbacks(unittest.TestCase):
    def test_explicit_year_first_cross_month_and_repeated_url_year(self):
        self.assertEqual(
            weekly._period("2021 (27 de febrero al 5 de marzo)"),
            (date(2021, 2, 27), date(2021, 3, 5)),
        )
        self.assertEqual(
            weekly.source_date("Sem_27feb_2021_05mar_2021.pdf"), date(2021, 3, 5)
        )
        self.assertEqual(
            weekly.source_date("Sem_27mar_2021_31mar_2021.xls"), date(2021, 3, 31)
        )
        with self.assertRaises(ValueError):
            weekly._period("2021 (27 de diciembre al 5 de enero)")
        with self.assertRaises(ValueError):
            weekly._verify_url(
                (date(2021, 2, 20), date(2021, 2, 26)), "Sem_27feb_2021_05mar_2021.pdf"
            )

    def test_missing_named_cell_is_review_and_not_carried_from_previous_row(self):
        rows = weekly.parse_workbook(
            workbook(
                [
                    ["Yuca ICA", "Popayán", 833, 867, 858, "="],
                    ["", "Tuluá", 600, 640, 627, "="],
                    ["Yuca llanera", "Bogotá", 1000, 1167, 1033, "+"],
                ]
            ),
            "annex.xlsx",
        )
        self.assertEqual([r["price"] for r in rows], [858, None, 1033])
        self.assertEqual(rows[1]["product_name"], "")
        self.assertEqual(rows[1]["details"]["literal_market_name"], "Tuluá")
        self.assertEqual(rows[1]["details"]["literal_mean"], 627)
        self.assertIn("row 6", rows[1]["source_locator"])

    def test_only_conflicting_named_quote_rows_are_reviewed(self):
        rows = weekly.parse_workbook(
            workbook(
                [
                    ["Uva", "Pereira", 11700, 13000, 12283, "+"],
                    ["Uva", "Bogotá", 10000, 11000, 10500, "+"],
                    ["Uva", "Pereira", 9600, 10800, 10108, "+"],
                    ["Acelga", "Bogotá", 333, 533, 418, "-"],
                ]
            ),
            "annex.xlsx",
        )
        self.assertEqual([r["price"] for r in rows], [None, 10500, None, 418])
        self.assertEqual(rows[0]["details"]["literal_mean"], 12283)
        self.assertEqual(rows[2]["details"]["literal_mean"], 10108)
        self.assertEqual(
            rows[0]["details"]["conflicting_source_locators"],
            [rows[0]["source_locator"], rows[2]["source_locator"]],
        )
        unchanged = weekly.parse_workbook(
            workbook(
                [
                    ["Uva", "Pereira", 10, 20, 15, "+"],
                    ["Uva", "Pereira", 10, 20, 15, "+"],
                ]
            ),
            "annex.xlsx",
        )
        self.assertEqual([r["price"] for r in unchanged], [15, 15])

    def test_orphan_native_tail_preserves_literal_evidence_and_adjacent_quote_review(
        self,
    ):
        def word(text, x, top, bold=False):
            return {
                "text": text,
                "x0": x,
                "x1": x + len(text) * 3,
                "top": top,
                "bottom": top + 8,
                "fontname": "Arial-BoldMT" if bold else "ArialMT",
                "size": 8,
            }

        headers = [
            word(t, x, 80)
            for t, x in [("Mínimo", 160), ("Máximo", 200), ("Medio", 240)]
        ]
        lines = [
            [word("Panela en pastilla", 30, 90, True)],
            [
                word("Nocaima (Cundinamarca)", 30, 102),
                word("2604", 160, 102),
                word("2708", 200, 102),
                word("2656", 240, 102),
            ],
            [
                word("Villeta (Cundinamarca)", 30, 114),
                word("2813", 160, 114),
                word("2938", 200, 114),
                word("2875", 240, 114),
            ],
            [word("Panela redonda blanca", 30, 126)],
        ]
        rows = weekly._native_column(
            lines,
            headers,
            "Procesados",
            (date(2021, 2, 27), date(2021, 3, 5)),
            65,
            1,
            2,
            {},
        )
        self.assertEqual([r["price"] for r in rows], [2656, None])
        self.assertEqual(rows[1]["details"]["literal_mean"], 2875)
        self.assertEqual(
            rows[1]["details"]["literal_unbound_tail_labels"], ["Panela redonda blanca"]
        )

    @unittest.skipUnless(
        (FIXTURES / "originals.json").exists(), "retained official originals optional"
    )
    def test_real_failed_workbooks_retain_every_literal_row_and_localize_reviews(self):
        expected = {
            "Sem_27mar_2021_31mar_2021.xls": (4432, 84),
            "anex-SIPSASemanal-08ago14ago-2026.xlsx": (4465, 36),
            "anex-SIPSASemanal-01ago06ago-2026.xlsx": (4342, 92),
        }
        for filename, (count, reviews) in expected.items():
            rows = weekly.parse_workbook((FIXTURES / filename).read_bytes(), filename)
            self.assertEqual(
                (len(rows), sum(r["price"] is None for r in rows)), (count, reviews)
            )
            self.assertEqual(len({r["source_locator"] for r in rows}), count)
            if filename.endswith(".xls"):
                missing = next(
                    r for r in rows if r["source_locator"] == "1.3!row 360,cols C:E"
                )
                self.assertEqual(
                    (
                        missing["product_name"],
                        missing["market"],
                        missing["details"]["literal_mean"],
                    ),
                    ("", "Tuluá (Valle del Cauca)", 627),
                )

    @unittest.skipUnless(
        (FIXTURES / "Sem_27feb_2021_05mar_2021.pdf").exists(),
        "retained official PDF optional",
    )
    def test_real_cross_month_pdf_native_fallback_and_source_conflicts(self):
        filename = "Sem_27feb_2021_05mar_2021.pdf"
        rows = weekly.parse_pdf((FIXTURES / filename).read_bytes(), filename)
        self.assertEqual(
            (len(rows), sum(r["price"] is None for r in rows)), (4488, 213)
        )
        self.assertEqual(
            {(r["period_start"], r["date"]) for r in rows},
            {("2021-02-27", "2021-03-05")},
        )
        quotes = {(r["product_name"], r["market"]): r for r in rows}
        self.assertEqual(quotes[("Acelga", "Armenia, Mercar")]["price"], 1178)
        self.assertEqual(
            quotes[("Color (bolsita)", "Ibagué, Plaza La 21")]["price"], 25867
        )
        self.assertEqual(
            quotes[("Sopa de pollo (caja)", "Bogotá, D.C., Corabastos")]["price"], 42759
        )
        self.assertFalse(any("continuaci" in r["product_name"].lower() for r in rows))
        # Printed continuation headings disagree internally/with companion XLSX.
        # Their literals remain evidence; no corrected product name is guessed.
        for product, count in [
            ("Remolacha regional", 30),
            ("Naranja Sweet", 38),
            ("Panela en pastilla", 5),
        ]:
            group = [r for r in rows if r["product_name"] == product]
            self.assertEqual(len(group), count)
            self.assertTrue(
                all(
                    r["price"] is None and r["details"]["literal_mean"] > 0
                    for r in group
                )
            )


if __name__ == "__main__":
    unittest.main()

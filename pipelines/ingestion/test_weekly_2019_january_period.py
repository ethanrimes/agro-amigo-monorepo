"""The printed January 2019 range omits 'de' before its first month."""

import hashlib
import unittest
from datetime import date
from pathlib import Path

from . import dane_weekly as weekly


class January2019PrintedPeriod(unittest.TestCase):
    def test_conflicting_printed_dates_are_literal_reviews(self):
        body = (
            Path(__file__).parent
            / "testdata/dane_weekly_2019_01_26_conflicting_pages.pdf"
        ).read_bytes()
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "c4f058f959c83c61dc15d5a1b8c9b07ce988260f9a2b569b0d2f3e447b4e3266",
        )
        name = "Sem_26ene_2019__01feb_2019.pdf"
        self.assertEqual(
            weekly._url_period(name),
            (date(2019, 1, 26), date(2019, 2, 1)),
        )
        rows = weekly.parse_pdf(body, name)
        self.assertEqual(len(rows), 302)
        for page, count in ((9, 85), (10, 90), (20, 48)):
            with self.subTest(page=page):
                page_rows = [row for row in rows if row["source_page"] == page]
                self.assertEqual(len(page_rows), count)
                self.assertTrue(all(row["price"] is None for row in page_rows))
                for row in page_rows:
                    self.assertEqual((row["period_start"], row["date"]),
                                     ("2019-01-24", "2019-01-30"))
                    self.assertEqual(row["details"]["literal_min"], row["min"])
                    self.assertEqual(row["details"]["literal_max"], row["max"])
                    self.assertGreater(row["details"]["literal_mean"], 0)
                    self.assertEqual(
                        row["details"]["source_filename_period_end"], "2019-02-01"
                    )
                    self.assertIn(
                        "2019 (24 al 30 de enero)",
                        row["details"]["literal_printed_period_heading"],
                    )
        page_11 = [row for row in rows if row["source_page"] == 11]
        self.assertEqual(len(page_11), 79)
        self.assertTrue(all(row["price"] is not None for row in page_11))
        self.assertEqual(
            next(row for row in rows if row["source_locator"] ==
                 "PDF page 9,table 1,column 1,line 2")["details"]["literal_mean"],
            978,
        )
        self.assertEqual(
            next(row for row in rows if row["source_locator"] ==
                 "PDF page 20,table 1,column 1,line 3")["details"]["literal_mean"],
            1300,
        )

    def test_exact_retained_page_11_uses_printed_cross_month_range(self):
        body = (
            Path(__file__).parent / "testdata/dane_weekly_2019_01_26_page11.pdf"
        ).read_bytes()
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "239983d48775eaedbfb6090f057e9884d3dcd0fafa9ca1c2dd8e196b8aeaf9ea",
        )
        self.assertEqual(
            weekly._period("2019 (26 enero al 01 de febrero)"),
            (date(2019, 1, 26), date(2019, 2, 1)),
        )
        rows = weekly.parse_pdf(body, "Sem_26ene_2019__01feb_2019.pdf")
        self.assertEqual(len(rows), 79)
        self.assertTrue(all(row["price"] is not None for row in rows))
        self.assertTrue(all(row["period_start"] == "2019-01-26" for row in rows))
        quote = next(
            row for row in rows
            if row["product_name"] == "Arveja verde en vaina pastusa"
            and row["market"] == "Cali, Cavasa"
        )
        self.assertEqual((quote["min"], quote["max"], quote["price"]), (3800, 4400, 4104))
        self.assertEqual(quote["source_locator"], "PDF page 11,table 1,column 1,line 3")

    def test_exact_page_61_inherits_only_the_same_table_headers_and_unit(self):
        body = (
            Path(__file__).parent / "testdata/dane_weekly_2019_01_26_pages60_61.pdf"
        ).read_bytes()
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "f618d1962895fc252483c635c171c28a89c7824c5667426b8e93f9dc33b8f71f",
        )
        rows = weekly.parse_pdf(body, "Sem_26ene_2019__01feb_2019.pdf")
        self.assertEqual((len(rows), sum(row["source_page"] == 61 for row in rows)), (86, 10))
        page_rows = [row for row in rows if row["source_page"] == 61]
        self.assertTrue(all(row["price"] is not None for row in page_rows))
        self.assertTrue(all(
            row["details"]["native_header_recovery"] == "same_table_previous_page"
            and row["details"]["native_unit_evidence_page"] == 60
            for row in page_rows
        ))
        quotes = {
            (row["product_name"], row["market"]):
            (row["min"], row["max"], row["price"])
            for row in page_rows
        }
        self.assertEqual(
            quotes[("Pollo entero fresco sin vísceras", "Bucaramanga, Frigoríficos")],
            (6500, 6500, 6500),
        )
        self.assertEqual(
            quotes[("Rabadillas de pollo", "Manizales, Centro Galerías")],
            (1700, 2000, 1850),
        )


if __name__ == "__main__":
    unittest.main()

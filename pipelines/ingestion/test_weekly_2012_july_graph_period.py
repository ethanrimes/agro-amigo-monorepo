"""The July 2012 graph is not a price-table period; 2018 is a real conflict."""

import hashlib
import unittest
from pathlib import Path

from . import dane_weekly as weekly
from .worker import SourceDateMismatch

TESTDATA = Path(__file__).parent / "testdata"
JULY = TESTDATA / "dane_weekly_2012_07_13_original.pdf"
JULY_SHA = "c69ba82a733c82cf5cae7d5412b2a347ff08e60f02bfecfc820518a825a8f7ce"
JULY_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Semana07julio_13julio_2012.pdf"
)
JUNE_2018 = TESTDATA / "dane_weekly_2018_06_15_conflicting_original.pdf"
JUNE_2018_SHA = "c3192584b35f69b03e8ba93872f9807f04109631d87fa76fc4671d06c05f4a64"
JUNE_2018_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Sem_09jun__15jun_2018.pdf"
)


class July2012GraphAndJune2018Conflict(unittest.TestCase):
    def test_july_original_retains_valid_week_and_page23_monetary_cells(self):
        body = JULY.read_bytes()
        self.assertEqual(len(body), 1_220_992)
        self.assertEqual(hashlib.sha256(body).hexdigest(), JULY_SHA)
        rows = weekly.parse_pdf(body, JULY_URL)
        self.assertEqual(weekly.VERSION, "dane-weekly-v24")
        self.assertEqual(len(rows), 3013)
        self.assertEqual(sum(r["price"] is not None for r in rows), 2933)
        self.assertEqual({(r["period_start"], r["date"]) for r in rows},
                         {("2012-07-07", "2012-07-13")})
        page = [r for r in rows if r["source_page"] == 23]
        self.assertEqual(len(page), 51)
        self.assertTrue(all(r["price"] is not None for r in page))
        for product, market, amounts in (
            ("Plátano hartón verde", "Rionegro (Antioquia)", (873, 938, 902)),
            ("Yuca criolla", "Barranquilla, Barranquillita", (838, 869, 849)),
        ):
            matches = [r for r in page if r["product_name"] == product and r["market"] == market]
            self.assertEqual(len(matches), 1)
            self.assertEqual((matches[0]["min"], matches[0]["max"], matches[0]["price"]), amounts)
            self.assertEqual(matches[0]["unit"], "kg")

    def test_separate_four_week_chart_before_table_does_not_set_price_date(self):
        # The retained page interleaves the chart's year/range into a
        # narrative line before the later, anchored monetary Cuadro heading.
        graph = ("Gráfico 6. Comportamiento del precio mayorista\n"
                 "Se reduce el precio de la arveja seca 2012 (junio 16 a julio 13)\n")
        table = ("Cuadro 3. Mercados mayoristas. Precios de venta de tubérculos\n"
                 "2012 (julio 7 a 13)\nPesos por kilogramo\nProductos y mercados\n")
        self.assertEqual(weekly._printed_monetary_period_headings(graph + table),
                         ["2012 (julio 7 a 13)"])
        self.assertEqual(weekly._period("2012 (julio 7 a 13)"),
                         (weekly.date(2012, 7, 7), weekly.date(2012, 7, 13)))
        with self.assertRaisesRegex(ValueError, "not a supported weekly period"):
            weekly._period("2012 (junio 16 a julio 13)")
        self.assertEqual(weekly._printed_monetary_period_headings(
            "Gráfico 6\n2012 (junio 16 a julio 13)\n" + table),
            ["2012 (junio 16 a julio 13)", "2012 (julio 7 a 13)"],
        )

    def test_june2018_cover_cannot_relabel_62_conflicting_monetary_headers(self):
        body = JUNE_2018.read_bytes()
        self.assertEqual(len(body), 2_510_777)
        self.assertEqual(hashlib.sha256(body).hexdigest(), JUNE_2018_SHA)
        with self.assertRaisesRegex(SourceDateMismatch, "printed period conflicts"):
            weekly.parse_pdf(body, JUNE_2018_URL)


if __name__ == "__main__":
    unittest.main()

"""A monthly chart cannot change the adjoining weekly price table's period."""
import hashlib
import unittest
from pathlib import Path

from . import dane_weekly as weekly

URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana25_29junio_2012.pdf"
ORIGINAL = Path(__file__).parent / "testdata/dane_weekly_2012_06_29_original.pdf"
WEEK = "2012 (junio 23 a 29)"
MONTH = "2012 (junio)"


class June2012SeparateGraphPeriodTests(unittest.TestCase):
    def test_whole_original_preserves_weekly_quotes_and_unverified_units(self):
        body = ORIGINAL.read_bytes()
        self.assertEqual(len(body), 900142)
        self.assertEqual(hashlib.sha256(body).hexdigest(), "d7636f4897cca1d34c2854712053363c368c368d3e3f5ce113ff06adc636884a")
        rows = weekly.parse_pdf(body, URL)
        self.assertEqual(len(rows), 1420)
        self.assertEqual(sum(row["price"] is not None for row in rows), 1347)
        self.assertEqual({(row["period_start"], row["date"]) for row in rows}, {("2012-06-23", "2012-06-29")})
        self.assertTrue(all(row["price"] is None for row in rows if row["unit"] == "unverified"))
        page = [row for row in rows if row["source_page"] == 13]
        self.assertEqual(len(page), 12)
        self.assertTrue(all(row["price"] is not None for row in page))
        for product, market, amounts in (
            ("Uva red globe nacional", "Bucaramanga, Centroabastos", (2480, 2660, 2555)),
            ("Uva verde", "Bogotá, D.C., Corabastos", (2400, 2453, 2411)),
        ):
            matches = [row for row in page if row["product_name"] == product and row["market"] == market]
            self.assertEqual(len(matches), 1)
            row = matches[0]
            self.assertEqual((row["min"], row["max"], row["price"]), amounts)
            self.assertEqual(row["unit"], "kg")
            self.assertEqual(row["details"]["price_statistic"], "published_mean")
        self.assertTrue(all(row["product_name"] != "Papa parda pastusa" for row in page))

    def test_only_separate_month_graph_is_excluded_from_period_candidates(self):
        text = f"Cuadro 2. Mercados mayoristas. Precios de venta de frutas\n{WEEK}\nProductos y mercados\nMínimo Máximo Medio\nTendencias: (=)\nGráfico 6. Comportamiento del precio mayorista\nde la papa parda pastusa\n{MONTH}\nSemanas y ciudades"
        self.assertEqual(weekly._printed_monetary_period_headings(text), [WEEK])

    def test_actual_conflicting_monetary_headers_are_preserved(self):
        text = f"Cuadro 2. Mercados mayoristas. Precios de venta de frutas\n{WEEK}\n{MONTH}\nProductos y mercados\nMínimo Máximo Medio\nTendencias: (=)"
        self.assertEqual(weekly._printed_monetary_period_headings(text), [WEEK, MONTH])

    def test_unclassified_dates_weekly_graphs_and_another_grid_fail_closed(self):
        prefix = f"Cuadro 2. Mercados mayoristas. Precios de venta de frutas\n{WEEK}\nProductos y mercados\nMínimo Máximo Medio\nTendencias: (=)\n"
        for tail, expected in (
            (MONTH, MONTH),
            (f"Gráfico 6. Evolución\n2012 (junio 16 a 22)", "2012 (junio 16 a 22)"),
            (f"Gráfico 6. Evolución\n{MONTH}\nProductos y mercados\nPesos por kilogramo", MONTH),
            (f"Gráfico 6. Evolución\ncontexto\ncontexto\ncontexto\n{MONTH}", MONTH),
        ):
            with self.subTest(tail=tail):
                self.assertEqual(weekly._printed_monetary_period_headings(prefix + tail), [WEEK, expected])


if __name__ == "__main__":
    unittest.main()

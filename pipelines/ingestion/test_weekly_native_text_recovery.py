"""Original text-layer DANE pages must not be sent to image OCR."""

import unittest
from pathlib import Path

from . import dane_weekly as weekly

FIXTURES = Path(__file__).parent / "testdata"


class WeeklyNativeTextRecovery(unittest.TestCase):
    def test_queued_text_pages_recover_literal_price_cells(self):
        # Each PDF contains the exact retained page and blank predecessors, so
        # source_page and source_locator retain the printed PDF page number.
        cases = (
            ("dane_weekly_2020_09_05_page33.pdf", "Sem_05sep_2020__11sep_2020.pdf", 91,
             33, "Uva importada", "Arauca (Arauca)", (13125, 13750, 13458)),
            ("dane_weekly_2020_09_12_page33.pdf", "Sem_12sep_2020__18sep_2020.pdf", 91,
             33, "Uva importada", "Cali, Cavasa", (11176, 11765, 11360)),
            ("dane_weekly_2020_10_12_page33.pdf", "Sem_12oct_2020__16oct_2020.pdf", 90,
             33, "Uva importada", "Bogotá, D.C., Corabastos", (11875, 12500, 12357)),
            ("dane_weekly_2020_10_24_page33.pdf", "Sem_24oct_2020__30oct_2020.pdf", 89,
             33, "Uva importada", "Cali, Cavasa", (10588, 11176, 10919)),
            ("dane_weekly_2020_11_21_page34.pdf", "Sem_21nov_2020__27nov_2020.pdf", 83,
             34, "Uva importada", "Tunja, Complejo de Servicios del Sur", (11875, 12250, 12000)),
            ("dane_weekly_2020_06_13_page35.pdf", "Sem_13jun_2020__19jun_2020.pdf", 3,
             35, "Zapote", "Medellín, Central Mayorista de Antioquia", (3000, 3300, 3067)),
            ("dane_weekly_2020_12_26_page39.pdf", "Sem_26dic_2020__31dic_2020.pdf", 19,
             39, "Yuca llanera", "Sogamoso (Boyacá)", (833, 933, 846)),
            ("dane_weekly_2025_09_20_page61.pdf", "bol-SIPSASemanal-20sep26sep-2025.pdf", 90,
             61, "Café instantáneo", 'Medellín, Plaza Minorista "José María Villa"', (190523, 193137, 192157)),
            ("dane_weekly_2025_10_04_pages62_63.pdf", "bol-SIPSASemanal-04oct10oct-2025.pdf", 181,
             62, "Café instantáneo", "Barranquilla. Barranquillita", (196814, 198873, 197794)),
            ("dane_weekly_2026_01_10_page62.pdf", "bol-SIPSASemanal-10ene16ene-2026.pdf", 93,
             62, "Café instantáneo", "Barranquilla, Barranquillita", (200931, 202157, 201440)),
        )
        for filename, url, count, page, product, market, prices in cases:
            with self.subTest(filename=filename):
                rows = weekly.parse_pdf((FIXTURES / filename).read_bytes(), url)
                self.assertEqual(len(rows), count)
                self.assertTrue(all(row["price"] is not None for row in rows))
                matches = [
                    row for row in rows
                    if row["source_page"] == page
                    and row["product_name"] == product
                    and row["market"] == market
                ]
                self.assertEqual(len(matches), 1)
                self.assertEqual(
                    (matches[0]["min"], matches[0]["max"], matches[0]["price"]),
                    prices,
                )

    def test_wrapped_market_binds_on_2019_page(self):
        page = (FIXTURES / "dane_weekly_2019_02_09_page12.pdf").read_bytes()
        rows = weekly.parse_pdf(page, "Sem_09feb_2019__15feb_2019.pdf")
        self.assertTrue(any(
            row["product_name"] == "Cebolla cabezona blanca importada"
            and row["market"] == "Ipiales (Nariño), Ipiales somos todos"
            and row["price"] == 1606
            for row in rows
        ))

    def test_2019_meat_headings_bind_exact_printed_prices(self):
        # These retained official PDF pages include the original page numbers.
        # Page 58 also prints the lomo sin hueso block that continues on 59.
        rows = weekly.parse_pdf(
            (FIXTURES / "dane_weekly_2019_02_09_queued_pages.pdf").read_bytes(),
            "Sem_09feb_2019__15feb_2019.pdf",
        )
        cases = (
            (59, "Carne de cerdo, lomo sin hueso", "Manizales, Centro Galerías", (12000, 14000, 12833)),
            (59, "Carne de cerdo, pernil con hueso", "Barranquilla, Barranquillita", (10000, 11000, 10375)),
            (59, "Carne de cerdo, pernil sin hueso", "Bogotá, D.C., Frigorífico Ble Ltda.", (10500, 11800, 11267)),
            (59, "Carne de cerdo, pernil sin hueso", "Ibagué, Plaza La 21", (11900, 13000, 12200)),
            (59, "Carne de cerdo, tocineta plancha", "Manizales, Centro Galerías", (10000, 12000, 11333)),
            (59, "Carne de cerdo, tocino barriga", "Bogotá, D.C., Frigorífico Ble Ltda.", (10000, 10500, 10083)),
            (59, "Carne de cerdo, tocino papada", "Bogotá, D.C., Frigorífico Ble Ltda.", (6500, 7000, 6750)),
            (62, "Carne de res, chatas", "Popayán, Plaza de mercado del barrio Bolívar", (16000, 16200, 16067)),
            (62, "Carne de res, cogote", "Bogotá, D.C., Frigorífico Ble Ltda.", (10600, 11000, 10833)),
            (62, "Carne de res, costilla", "Barranquilla, Barranquillita", (8000, 8600, 8250)),
            (62, "Carne de res en canal", "Arauca (Arauca)", (10000, 12000, 11333)),
            (62, "Carne de res, falda", "Barranquilla, Barranquillita", (12000, 13000, 12450)),
            (62, "Carne de res, lomo de brazo", "Bogotá, D.C., Paloquemao", (14600, 15000, 14867)),
        )
        for page, product, market, prices in cases:
            with self.subTest(page=page, product=product, market=market):
                matches = [
                    row for row in rows
                    if row["source_page"] == page
                    and row["product_name"] == product
                    and row["market"] == market
                ]
                self.assertEqual(len(matches), 1)
                self.assertEqual(
                    (matches[0]["min"], matches[0]["max"], matches[0]["price"]),
                    prices,
                )
                self.assertIn(f"PDF page {page},", matches[0]["source_locator"])
                if (page, product, market) in {
                    (59, "Carne de cerdo, lomo sin hueso", "Manizales, Centro Galerías"),
                    (59, "Carne de cerdo, pernil sin hueso", "Ibagué, Plaza La 21"),
                    (62, "Carne de res, chatas", "Popayán, Plaza de mercado del barrio Bolívar"),
                }:
                    self.assertEqual(
                        matches[0]["details"]["literal_product_heading"],
                        f"{product} (continuación)",
                    )
        for page, expected_count in ((59, 63), (62, 68)):
            page_rows = [row for row in rows if row["source_page"] == page]
            self.assertEqual(len(page_rows), expected_count)
            self.assertTrue(all(row["price"] is not None for row in page_rows))

        guadalupe = [
            row for row in rows
            if row["market"] == "Bogotá, D.C., Frigorífico Guadalupe"
        ]
        self.assertEqual(len(guadalupe), 14)
        self.assertFalse(any("Gua- dalupe" in row["market"] for row in rows))
        for row in guadalupe:
            self.assertEqual(
                row["details"]["literal_market_lines"],
                ["Bogotá, D.C., Frigorífico Gua-", "dalupe"],
            )
            self.assertEqual(
                row["details"]["native_market_join"],
                "explicit_guadalupe_line_wrap",
            )
        lomo_guadalupe = [
            row for row in guadalupe
            if row["source_page"] == 58
            and row["product_name"] == "Carne de cerdo, lomo sin hueso"
        ]
        self.assertEqual(len(lomo_guadalupe), 1)
        self.assertEqual(
            (lomo_guadalupe[0]["min"], lomo_guadalupe[0]["max"], lomo_guadalupe[0]["price"]),
            (13500, 13500, 13500),
        )

    def test_2019_april_printed_range_conflicts_remain_literal_reviews(self):
        # Source: https://www.dane.gov.co/files/investigaciones/agropecuario/
        # sipsa/Sem_20abr_2019__26abr_2019.pdf, PDF page 10, Cuadro 3.
        rows = weekly.parse_pdf(
            (FIXTURES / "dane_weekly_2019_04_20_page10.pdf").read_bytes(),
            "Sem_20abr_2019__26abr_2019.pdf",
        )
        self.assertEqual(len(rows), 92)
        reviews = [row for row in rows if row["price"] is None]
        expected = {
            "Montería, Mercado del Sur": (5500, 5500, 5167),
            "Palmira (Valle del Cauca)": (5500, 5700, 5475),
            "Sincelejo, Nuevo Mercado": (5500, 5000, 4983),
            "Valledupar, Mercabastos": (5500, 5400, 5322),
        }
        self.assertEqual(len(reviews), len(expected))
        for row in reviews:
            self.assertEqual(row["product_name"], "Ajo importado")
            self.assertIn(row["market"], expected)
            self.assertEqual(
                (
                    row["details"]["literal_min"],
                    row["details"]["literal_max"],
                    row["details"]["literal_mean"],
                ),
                expected[row["market"]],
            )
            self.assertEqual(row["source_page"], 10)
            self.assertIn("PDF page 10,", row["source_locator"])
            self.assertIn("fuera del rango", row["details"]["quality_issue"])
        siblings = [
            row for row in rows
            if row["product_name"] == "Ajo importado"
            and row["market"] == "Cali, Cavasa"
        ]
        self.assertEqual(len(siblings), 1)
        self.assertEqual(
            (siblings[0]["min"], siblings[0]["max"], siblings[0]["price"]),
            (5300, 5700, 5431),
        )
        self.assertEqual(sum(row["price"] is not None for row in rows), 88)

    def test_valid_price_token_and_unaligned_glue_are_not_split(self):
        def word(text, start):
            chars = [
                {"text": char, "x0": start + i * 4, "x1": start + (i + 1) * 4}
                for i, char in enumerate(text)
            ]
            return {"text": text, "x0": chars[0]["x0"], "x1": chars[-1]["x1"], "chars": chars}

        headers = [[
            {"x0": 100, "x1": 125}, {"x0": 140, "x1": 165}, {"x0": 180, "x1": 205}
        ]]
        words = [word("14.190", 100), word("13.12513.750", 300)]
        self.assertEqual(
            [item["text"] for item in weekly._split_joined_price_words(words, headers)],
            ["14.190", "13.12513.750"],
        )


if __name__ == "__main__":
    unittest.main()

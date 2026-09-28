"""Mixed monthly monetary/percentage captions retain their actual reference month."""

import io
import os
import unittest
from datetime import date
from pathlib import Path

import pdfplumber

from .pdf_sources import VerifiedPDFPage
from .worker import SourceDateMismatch, parse_pdf_pages

FIXTURES = Path(
    os.getenv(
        "AGRO_DANE_PRICE_FIXTURES",
        str(
            Path(__file__).resolve().parents[2]
            / "artifacts/source-verification-2026-09-28/dane-prices/originals"
        ),
    )
)


def table(caption, monetary=True):
    return [
        [
            ("Precio $/Kg. " if monetary else "Variación porcentual. ") + caption,
            None,
            None,
            None,
            None,
            None,
            None,
        ],
        ["Producto", "Bogotá", None, "Medellín", None, "Cali", None],
        [None, "Precio", "Var %", "Precio", "Var %", "Precio", "Var %"],
        ["Ahuyama", "900", "-3.02", "525", "0,00", "587", "-2,00"],
    ]


def parse(caption, day=date(2015, 8, 31), monetary=True):
    page = VerifiedPDFPage({"text": "", "tables": [table(caption, monetary)]})
    return list(parse_pdf_pages([page], day, True, allow_empty=True))


class MonthlyComparisonCaptions(unittest.TestCase):
    def test_explicit_current_previous_pair_keeps_only_literal_prices(self):
        rows = parse("Variación mensual. Agosto/julio 2015")
        self.assertEqual([r[6] for r in rows], [900, 525, 587])
        self.assertTrue(all(r[2] == date(2015, 8, 31) for r in rows))
        self.assertTrue(all(r[-1]["comparison_period"] == "2015-07" for r in rows))
        self.assertTrue(
            all(r[-1]["period_evidence"] == "Agosto/julio 2015" for r in rows)
        )
        self.assertTrue(all(r[0].endswith("monthly-pdf-v4") for r in rows))

    def test_year_rollover_is_previous_month_not_future_december(self):
        rows = parse("Variación mensual. Enero 2015/diciembre 2014", date(2015, 1, 31))
        self.assertEqual(rows[0][-1]["comparison_period"], "2014-12")

    def test_wrong_current_date_reversed_and_nonconsecutive_pairs_fail_closed(self):
        for text in [
            "Julio/agosto 2015",
            "Agosto/junio 2015",
            "Septiembre/agosto 2015",
            "Agosto/julio 2014",
            "Enero/diciembre 2015",
            "Enero 2015/diciembre 2015",
        ]:
            with self.subTest(text=text), self.assertRaises(SourceDateMismatch):
                parse("Variación mensual. " + text)

    def test_unexplained_month_pair_does_not_accept_its_trailing_month(self):
        self.assertEqual(parse("Agosto/julio 2015", date(2015, 7, 31)), [])

    def test_other_conflicting_period_is_not_hidden_by_comparison(self):
        with self.assertRaises(SourceDateMismatch):
            parse("Variación mensual. Agosto/julio 2015. Septiembre de 2015")

    def test_percentage_grid_with_same_month_pair_never_becomes_money(self):
        self.assertEqual(
            parse("Variación mensual. Agosto/julio 2015", monetary=False), []
        )

    @unittest.skipUnless(
        (FIXTURES / "Bol_mensual_ago_2015.pdf").exists(),
        "real original fixture unavailable",
    )
    def test_actual_august_2015_all_393_native_price_cells_and_no_percentages(self):
        import re

        with pdfplumber.open(
            io.BytesIO((FIXTURES / "Bol_mensual_ago_2015.pdf").read_bytes())
        ) as pdf:
            rows = list(
                parse_pdf_pages(pdf.pages, date(2015, 8, 31), True, allow_empty=True)
            )
            # Independent column enumeration fixed from visually inspected pages24/25.
            expected = {}
            for page_no, columns in [(24, range(1, 17, 2)), (25, range(2, 18, 2))]:
                cells = pdf.pages[page_no - 1].extract_tables()[0]
                for row_no, cellrow in enumerate(cells[2:], 3):
                    name = " ".join(str(cellrow[0] or "").split())
                    if not name:
                        continue
                    for col in columns:
                        token = str(cellrow[col] or "")
                        if re.fullmatch(r"\d+(?:\.\d{3})*(?:,\d+)?", token):
                            value = float(token.replace(".", "").replace(",", "."))
                            if value > 0:
                                expected[
                                    (page_no, row_no, col + 1, name, cells[0][col])
                                ] = value
            actual = {}
            for r in rows:
                m = re.search(r"page (\d+),table 1,row (\d+),col (\d+)", r[0])
                actual[(*(int(v) for v in m.groups()), r[3], r[4])] = r[6]
            self.assertEqual(len(expected), 393)
            self.assertEqual(actual, expected)
            self.assertEqual(actual[(24, 4, 2, "Ahuyama", "Barranquilla")], 1197)
            self.assertEqual(actual[(24, 4, 4, "Ahuyama", "Bogotá")], 900)
            self.assertTrue(all(r[2] == date(2015, 8, 31) for r in rows))
            self.assertTrue(all(r[-1]["comparison_period"] == "2015-07" for r in rows))
            self.assertEqual(
                {int(re.search(r"page (\d+)", r[0])[1]) for r in rows}, {24, 25}
            )

    @unittest.skipUnless(
        (FIXTURES / "Bol_mensual_ene_2016.pdf").exists(),
        "real original fixture unavailable",
    )
    def test_actual_january_2016_rollover_all_399_literal_cells(self):
        import re

        with pdfplumber.open(FIXTURES / "Bol_mensual_ene_2016.pdf") as pdf:
            rows = list(
                parse_pdf_pages(pdf.pages, date(2016, 1, 31), True, allow_empty=True)
            )
            expected = {}
            for page_no in (22, 23):
                cells = pdf.pages[page_no - 1].extract_tables()[0]
                for row_no, cellrow in enumerate(cells[2:], 3):
                    name = " ".join(str(cellrow[0] or "").split())
                    if not name:
                        continue
                    for col in range(2, 18, 2):
                        token = str(cellrow[col] or "")
                        if re.fullmatch(r"\d+(?:\.\d{3})*(?:,\d+)?", token):
                            value = float(token.replace(".", "").replace(",", "."))
                            if value > 0:
                                expected[
                                    (page_no, row_no, col + 1, name, cells[0][col])
                                ] = value
            actual = {}
            for row in rows:
                match = re.search(r"page (\d+),table 1,row (\d+),col (\d+)", row[0])
                actual[(*(int(v) for v in match.groups()), row[3], row[4])] = row[6]
            self.assertEqual(len(expected), 399)
            self.assertEqual(actual, expected)
            self.assertEqual(actual[(22, 4, 9, "Ahuyama", "Cartagena")], 679)
            self.assertTrue(all(r[2] == date(2016, 1, 31) for r in rows))
            self.assertTrue(all(r[-1]["comparison_period"] == "2015-12" for r in rows))

    def test_daily_cartagena_column_and_variation_remain_bound(self):
        cells = table("27 de junio de 2012")
        cells[1][5] = "Cartagena"
        page = VerifiedPDFPage({"text": "", "tables": [cells]})
        rows = list(parse_pdf_pages([page], date(2012, 6, 27), False))
        self.assertEqual(
            [(r[4], r[6]) for r in rows],
            [("Bogotá", 900), ("Medellín", 525), ("Cartagena", 587)],
        )
        self.assertTrue(all(r[-1]["parser_version"] == "daily-pdf-v5" for r in rows))


if __name__ == "__main__":
    unittest.main()

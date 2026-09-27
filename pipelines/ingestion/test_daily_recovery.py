"""Exact daily source recoveries, independent price-cell coverage and review bounds."""

import hashlib
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from unittest.mock import patch

import xlrd

from . import daily_recovery as recovery
from . import worker

FIXTURES = Path("artifacts/source-ambiguity-2026-09-27/daily")
CASES = (
    ("mayoristas_febrero_11_2014.xls", "2014-02-11", "2014-02-11", 333),
    ("mayoristas_noviembre_13_2013.xls", "2013-11-13", "2013-11-13", 300),
    ("mayoristas_septiembre_26_2013.xls", "2013-09-26", "2013-09-26", 398),
    ("mayoristas_anexo_dic_5_2012.xls", "2012-12-05", "2012-12-06", 241),
    ("mayoristas_anexo_feb_11_2013.xls", "2013-02-11", "2013-02-11", 231),
    ("mayoristas_diciembre_6_2013.xls", "2013-12-06", "2013-12-06", 431),
    ("mayoristas_julio_12_2013.xls", "2013-07-12", "2013-07-15", 231),
    ("mayoristas_junio_11_2014.xls", "2014-06-11", "2014-06-10", 332),
    ("mayoristas_mayo_20_2013.xls", "2013-05-20", "2013-05-21", 243),
)


def original_price_cells(path):
    result = {}
    book = xlrd.open_workbook(path)
    for sheet in book.sheets():
        header = next(
            i
            for i in range(min(12, sheet.nrows))
            if sum(str(c).strip().lower() == "precio" for c in sheet.row_values(i)) >= 3
        )
        columns = [
            i
            for i, v in enumerate(sheet.row_values(header))
            if str(v).strip().lower() == "precio"
        ]
        for row in range(header + 1, sheet.nrows):
            for col in columns:
                cell = sheet.cell(row, col)
                if cell.ctype == xlrd.XL_CELL_NUMBER and cell.value > 0:
                    result[f"{sheet.name}!row {row + 1},col {col + 1}"] = cell.value
    return result


class MaterializedDailyRecovery(unittest.TestCase):
    def matrix(self, heading="29 de noviembre de 2012"):
        return [
            [heading],
            ["Precio $/Kg", "Armenia, Mercar", "", "", "", "Medellín, CMA"],
            ["Producto", "Precio", "Var %", "Precio", "Var %", "Precio", "Var %"],
            ["Ahuyama", 567, 0, 671, -0.04, 600, 0.1],
        ]

    def test_explicit_markets_publish_and_missing_market_stays_literal_review(self):
        with patch.object(
            worker, "workbooks", return_value=[("Original", iter(self.matrix()))]
        ):
            result = recovery.parse_daily(b"synthetic", date(2012, 11, 29))
        self.assertEqual(
            [(r[4], r[6]) for r in result["rows"]],
            [("Armenia, Mercar", 567), ("Medellín, CMA", 600)],
        )
        self.assertEqual(len(result["reviews"]), 1)
        review = result["reviews"][0]
        self.assertEqual(review["source_locator"], "Original!row 4,col 4")
        self.assertEqual(review["record"]["price"], 671)
        self.assertEqual(review["record"]["raw_change"], -0.04)
        self.assertIsNone(review["record"]["market_name"])
        self.assertNotIn("Bucaramanga", str(review))

    def test_invalid_later_sheet_fails_before_any_rows_are_returned(self):
        sources = [
            ("Valid", iter(self.matrix())),
            ("Invalid", iter(self.matrix("30 de noviembre de 2012"))),
        ]
        with (
            patch.object(worker, "workbooks", return_value=sources),
            self.assertRaises(worker.SourceDateMismatch),
        ):
            recovery.parse_daily(b"synthetic", date(2012, 11, 29))

    def test_unreviewed_missing_date_or_conflict_never_uses_expected_date(self):
        for heading, exception in [
            ("13 de noviembre", ValueError),
            ("15 de julio de 2013", worker.SourceDateMismatch),
        ]:
            with (
                self.subTest(heading=heading),
                patch.object(
                    worker,
                    "workbooks",
                    return_value=[("Original", iter(self.matrix(heading)))],
                ),
                self.assertRaises(exception),
            ):
                recovery.parse_daily(b"unreviewed", date(2013, 7, 12))

    @unittest.skipUnless(
        (FIXTURES / "mayoristas_anexo_nov_29_2012.xls").exists(),
        "Original fixture unavailable",
    )
    def test_actual_nov29_all238_cells_partition_into178_quotes_and60_reviews(self):
        path = FIXTURES / "mayoristas_anexo_nov_29_2012.xls"
        result = recovery.parse_daily(path.read_bytes(), date(2012, 11, 29))
        quotes = result["rows"]
        reviews = result["reviews"]
        self.assertEqual((len(quotes), len(reviews)), (178, 60))
        values = {r[0]: r[6] for r in quotes}
        values.update({r["source_locator"]: r["record"]["price"] for r in reviews})
        self.assertEqual(values, original_price_cells(path))
        self.assertEqual(
            Counter(r["record"]["column"] for r in reviews), {6: 31, 10: 29}
        )
        self.assertTrue(all(r["record"]["market_name"] is None for r in reviews))
        self.assertEqual(
            {r[4] for r in quotes},
            {
                "Armenia, Mercar",
                "Bogotá, Corabastos",
                "Cali, Cavasa",
                "Manizales (Caldas)",
                "Medellín, CMA",
                "Pereira, Mercasa",
            },
        )
        self.assertTrue(
            all(r[2] == date(2012, 11, 29) and r[5] == "kg" for r in quotes)
        )

    @unittest.skipUnless(
        all((FIXTURES / c[0]).exists() for c in CASES),
        "Original recovery fixtures unavailable",
    )
    def test_all_nine_corroborated_originals_preserve_every_price_and_date_evidence(
        self,
    ):
        for name, archive, observed, count in CASES:
            with self.subTest(name=name):
                path = FIXTURES / name
                body = path.read_bytes()
                result = recovery.parse_daily(body, date.fromisoformat(archive))
                rows = result["rows"]
                self.assertEqual(len(rows), count)
                self.assertEqual({r[0]: r[6] for r in rows}, original_price_cells(path))
                self.assertEqual({r[2].isoformat() for r in rows}, {observed})
                self.assertEqual(result["reviews"], [])
                evidence = recovery.VERIFIED_DATE_RECOVERIES[
                    hashlib.sha256(body).hexdigest()
                ]
                self.assertEqual(result["date_resolutions"], [evidence])
                self.assertTrue(all(r[-1]["date_resolution"] == evidence for r in rows))
                with self.assertRaises((ValueError, worker.SourceDateMismatch)):
                    recovery.parse_daily(
                        body + b"\0" * 512, date.fromisoformat(archive)
                    )

    @unittest.skipUnless(
        (FIXTURES / "mayoristas_julio_06_2012.xls").exists(),
        "Original unresolved fixtures unavailable",
    )
    def test_both_july2012_dates_remain_unresolved_even_with_similar_tables(self):
        for day in (6, 9):
            path = FIXTURES / f"mayoristas_julio_{day:02d}_2012.xls"
            with self.subTest(day=day), self.assertRaises(worker.SourceDateMismatch):
                recovery.parse_daily(path.read_bytes(), date(2012, 7, day))

    @unittest.skipUnless(
        (FIXTURES / "mayoristas_anexo_feb_11_2013.xls").exists(),
        "Original source fixture unavailable",
    )
    def test_corroboration_does_not_replace_a_disagreeing_literal_price(self):
        result = recovery.parse_daily(
            (FIXTURES / "mayoristas_anexo_feb_11_2013.xls").read_bytes(),
            date(2013, 2, 11),
        )
        row = next(
            r
            for r in result["rows"]
            if r[3] == "Zanahoria" and r[4] == "Cartagena, Bazurto"
        )
        self.assertEqual(
            row[6], 1292
        )  # Companion prose prints1229; never rewrite workbook.

    @unittest.skipUnless(
        (FIXTURES / "mayoristas_junio_10_2014.xls").exists(),
        "Counterpart fixtures unavailable",
    )
    def test_mislinked_originals_have_exact_correctly_dated_counterparts(self):
        pairs = (
            ("mayoristas_anexo_dic_5_2012.xls", "mayoristas_anexo_dic_6_2012.xls"),
            ("mayoristas_julio_12_2013.xls", "mayoristas_julio_15_2013.xls"),
            ("mayoristas_mayo_20_2013.xls", "mayoristas_mayo_21_2013.xls"),
        )
        for wrong, right in pairs:
            with self.subTest(wrong=wrong):
                self.assertEqual(
                    (FIXTURES / wrong).read_bytes(), (FIXTURES / right).read_bytes()
                )
        books = [
            xlrd.open_workbook(FIXTURES / f"mayoristas_junio_{day}_2014.xls")
            for day in (10, 11)
        ]

        def native(book):
            return [
                (s.name, [s.row_values(i) for i in range(s.nrows)])
                for s in book.sheets()
            ]

        self.assertEqual(native(books[0]), native(books[1]))

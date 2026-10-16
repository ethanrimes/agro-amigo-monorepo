"""Exact DANE 2018 current/comparison month checks against native workbooks."""

import hashlib
import io
import unittest
from datetime import date
from pathlib import Path

import openpyxl

from .worker import SourceDateMismatch, parse_monthly_summary

FIXTURES = Path(__file__).parent / "testdata"
SOURCES = (
    ("sep", date(2018, 9, 30), 410, "f445c889d4c807d1c980f8cb3f8459f517b2c292e0ae6ca4bb90de2738d92bc1", 932),
    ("oct", date(2018, 10, 31), 408, "54753729f97d1194178486d55af7ca4f4de2363e134e654143a8cf008c3b93ee", 707),
)


class MonthlyAnnex2018Dates(unittest.TestCase):
    def test_hyphenated_current_comparison_headings_and_every_positive_cell(self):
        for month, expected_day, count, digest, first_price in SOURCES:
            with self.subTest(month=month):
                data = (FIXTURES / f"anex_mensual_{month}_2018.xlsx").read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
                rows = list(parse_monthly_summary(data, expected_day))
                self.assertEqual(len(rows), count)
                self.assertEqual({row[2] for row in rows}, {expected_day})
                self.assertEqual(rows[0][3:7], ("Ahuyama", "Barranquilla", "kg", first_price))

                book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
                try:
                    sheet = book["Anexo 1"]
                    expected = {}
                    for row_no, cells in enumerate(sheet.iter_rows(min_row=12, values_only=True), 12):
                        for column in range(2, 18, 2):
                            value = cells[column - 1]
                            if isinstance(value, (int, float)) and value > 0:
                                expected[
                                    f"Anexo 1!row {row_no},col {column}; monthly-annex-v3"
                                ] = float(value)
                finally:
                    book.close()
                self.assertEqual({row[0]: row[6] for row in rows}, expected)

                wrong_month = date(2018, 8 if month == "sep" else 9, 31 if month == "sep" else 30)
                with self.assertRaises(SourceDateMismatch):
                    list(parse_monthly_summary(data, wrong_month))


if __name__ == "__main__":
    unittest.main()

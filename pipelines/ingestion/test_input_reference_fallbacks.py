"""Native XLS context and provider/stratum tariffs are never municipal prices."""

import io
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import openpyxl
import xlrd

from .input_references import context_rows, extract_reference_rows
from .worker import SourceDateMismatch

FIXTURES = Path("artifacts/extraction-robustness-2026-09-27/inputs-xls")


class ReferenceFallbacks(unittest.TestCase):
    def capture(self, body, day=None):
        rows = []
        db = MagicMock()
        db.cursor.return_value.__enter__.return_value.executemany.side_effect = (
            lambda sql, batch: rows.extend(list(batch))
        )
        count = extract_reference_rows(db, body, "source", day)
        self.assertEqual(count, len(rows))
        return rows

    def workbook(self, sheet="ENERGIA SEP15", provider="CHEC"):
        book = openpyxl.Workbook()
        book.active.title = sheet
        for row in [
            [
                "Proveedor de servicios y estrato",
                "Tarifa septiembre",
                "Tarifa Subsidio",
                "Tarifa Contribuciones",
            ],
            [provider],
            [1, 200.042, 93.5596434, None],
            [4, 427.7205, 0, 0],
        ]:
            book.active.append(row)
        output = io.BytesIO()
        book.save(output)
        return output.getvalue()

    def test_native_tariff_keeps_provider_stratum_zero_and_absence_distinct(self):
        rows = self.capture(self.workbook(), date(2015, 9, 30))
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            rows[0][2:6],
            ("electricity", date(2015, 9, 30), "CHEC", "Energía eléctrica"),
        )
        first, last = [r[-1].obj for r in rows]
        self.assertEqual(first["Tarifa septiembre"], 200.042)
        self.assertIsNone(first["Tarifa Contribuciones"])
        self.assertEqual(last["Tarifa Contribuciones"], 0)
        self.assertEqual(last["stratum"], 4)
        self.assertNotIn("municipality", first)
        self.assertNotIn("unit", first)

    def test_conflicting_period_and_missing_provider_are_not_guessed(self):
        with self.assertRaises(SourceDateMismatch):
            self.capture(self.workbook(), date(2015, 10, 31))
        with self.assertRaisesRegex(ValueError, "period"):
            self.capture(self.workbook(sheet="ENERGIA OCT15"))
        with self.assertRaisesRegex(ValueError, "provider/stratum"):
            self.capture(self.workbook(provider=None))

    def test_ooxml_context_keeps_hyperlinks_and_rejects_unknown_format(self):
        book = openpyxl.Workbook()
        book.active["A1"] = "Fuente"
        book.active["A1"].hyperlink = "https://www.dane.gov.co/files/source.pdf"
        out = io.BytesIO()
        book.save(out)
        self.assertEqual(
            next(context_rows(out.getvalue()))[2:],
            (["Fuente"], ["https://www.dane.gov.co/files/source.pdf"]),
        )
        with self.assertRaisesRegex(ValueError, "Unrecognized native workbook"):
            list(context_rows(b"<html>Publisher failure</html>"))

    @unittest.skipUnless(
        (FIXTURES / "Bol_Insumos_sep_2015.xls").exists(),
        "retained native XLS unavailable",
    )
    def test_actual_energy_all_literal_price_subsidy_and_contribution_cells(self):
        for month in ("jun", "sep", "dic"):
            path = FIXTURES / f"Bol_Insumos_{month}_2015.xls"
            with self.subTest(file=path.name):
                book = xlrd.open_workbook(path)
                sheet = next(
                    s for s in book.sheets() if s.name.upper().startswith("ENERGIA")
                )
                expected = {}
                provider = None
                for n in range(1, sheet.nrows):
                    row = sheet.row_values(n)
                    if (
                        isinstance(row[0], str)
                        and row[0]
                        and not isinstance(row[1], (int, float))
                    ):
                        provider = row[0]
                    if isinstance(row[1], (int, float)) and row[1] > 0:
                        expected[f"{sheet.name}!row {n + 1}"] = (provider, *row[:4])
                rows = self.capture(path.read_bytes())
                values = {}
                for row in rows:
                    details = row[-1].obj
                    values[row[1]] = (
                        row[4],
                        *[details[header] for header in sheet.row_values(0)],
                    )
                self.assertEqual(values, expected)
                self.assertEqual(len(rows), 114)
                # A real OLE workbook must use xlrd and preserve every literal row.
                native = list(context_rows(path.read_bytes()))
                self.assertEqual(len(native), sum(s.nrows for s in book.sheets()))
                book.release_resources()


if __name__ == "__main__":
    unittest.main()

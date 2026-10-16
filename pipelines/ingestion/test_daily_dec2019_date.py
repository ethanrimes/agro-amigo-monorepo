"""Exact-source regression for DANE's December 2, 2019 workbook month typo."""
import hashlib
import io
import re
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import openpyxl
import pdfplumber

from pipelines.ingestion import daily_recovery, ocr, worker
from pipelines.ingestion.queue_plan import PRIORITY_SOURCE_REPAIRS, expected_versions
from pipelines.ingestion.retained_date_repairs import retained_exact_date_repair

FIXTURES = Path(__file__).parent / "testdata/dane_date_repairs"
XLS_SHA = "10a85133075b7e2c334bf472bda70df5d99ccdaec6640594ee7ac494d283a316"
PDF_SHA = "96d6ff9a067d516b3a532572e1495511879ae248dafdfab171e28b39d0677185"
DAY = date(2019, 12, 2)
URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_diciembre_02_2019.xlsx"
PDF_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_diciembre_02_2019.pdf"
HEADING = "Lunes 02 de noviembre de 2019"


def normalize(value):
    return " ".join(str(value or "").split())


class ExactDec2019Date(unittest.TestCase):
    def setUp(self):
        self.body = (FIXTURES / f"{XLS_SHA}.xlsx").read_bytes()
        self.pdf = (FIXTURES / f"{PDF_SHA}.pdf").read_bytes()

    def test_exact_original_and_companion_pdf_print_the_december_date(self):
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), XLS_SHA)
        self.assertEqual(hashlib.sha256(self.pdf).hexdigest(), PDF_SHA)
        book = openpyxl.load_workbook(io.BytesIO(self.body), read_only=True, data_only=True)
        try:
            self.assertEqual(book.sheetnames, ["Boletín diario"])
            self.assertEqual(book["Boletín diario"]["A2"].value, HEADING)
            self.assertIsNone(book["Boletín diario"]["A1"].value)
            self.assertEqual((book["Boletín diario"].max_row,
                              book["Boletín diario"].max_column), (46, 39))
        finally:
            book.close()
        with pdfplumber.open(io.BytesIO(self.pdf)) as pdf:
            self.assertGreaterEqual(len(pdf.pages), 1)
            text = pdf.pages[0].extract_text() or ""
        self.assertIn("2 de diciembre de 2019", normalize(text).lower())
        normalized_pdf = normalize(text)
        pdf_passages = (
            "En el caso de la cebolla junca, la mayor cotización de esta jornada se dio en Pasto, al subir 69,23%. Este comportamiento se explicó porque ingresó un menor volumen de producto de primera calidad originario de Buesaquillo (Nariño), desde donde se registraron salidas a otros mercados del país. Allí el kilo se transó a $489.",
            "En Cali (Cavasa) el incremento fue del 38,89% y el kilo se vendió a $1.111",
            "En Montería se registró un alza del 25,61% ya que se redujo el volumen de carga que ingresa de El Santuario, Marinilla (Antioquia) y Ocaña (Norte del Santander). Allí el kilo se comercializó a $2.146.",
            "Caso similar se presentó en Pasto al subir la cotización de arveja verde en vaina un 53,75%, pues se redujo la oferta procedente de Funes (Nariño), por lo que el kilo se ofreció a $2.050.",
            "Del mismo modo, en Villavicencio el kilo se comercializó a $3.600",
            "En Pasto, también se redujo la oferta de zanahoria proveniente de Túquerres (Nariño) ante la salida del producto hacia otros mercados del país. El kilo se comercializó a $587",
        )
        for passage in pdf_passages:
            self.assertIn(normalize(passage), normalized_pdf)
        book = openpyxl.load_workbook(io.BytesIO(self.body), read_only=True, data_only=True)
        try:
            sheet = book["Boletín diario"]
            corroborating = (
                ("Cebolla junca", "Pasto, El Potrerillo", "R9", 489),
                ("Cebolla junca", "Cali, Cavasa", "H9", 1111),
                ("Cebolla junca", "Montería", "P9", 2146),
                ("Arveja verde en vaina", "Pasto, El Potrerillo", "R7", 2050),
                ("Arveja verde en vaina", "Villavicencio, CAV", "AB7", 3600),
                ("Zanahoria", "Pasto, El Potrerillo", "R18", 587),
            )
            evidence_cells = daily_recovery.VERIFIED_DATE_RECOVERIES[XLS_SHA]["corroborating_cells"]
            self.assertEqual(len(evidence_cells), len(corroborating))
            for index, (product, market, cell, price) in enumerate(corroborating):
                row = int("".join(char for char in cell if char.isdigit()))
                col = "".join(char for char in cell if char.isalpha())
                with self.subTest(cell=cell):
                    self.assertEqual(sheet[f"A{row}"].value, product)
                    self.assertEqual(normalize(sheet[f"{col}3"].value), market)
                    self.assertEqual(sheet[cell].value, price)
                    self.assertEqual(evidence_cells[index], {"product": product, "market": market,
                                                                "xls_cell": cell, "price_cop_per_kg": price})
        finally:
            book.close()
        self.assertTrue(URL.endswith("mayoristas_diciembre_02_2019.xlsx"))
        self.assertTrue(PDF_URL.endswith("mayoristas_diciembre_02_2019.pdf"))

    def test_all_394_positive_native_price_and_variation_cells_are_unchanged(self):
        book = openpyxl.load_workbook(io.BytesIO(self.body), read_only=True, data_only=True)
        try:
            sheet = book["Boletín diario"]
            native = list(sheet.iter_rows(values_only=True))
            price_columns = [col for col, value in enumerate(native[3])
                             if normalize(value).lower() == "precio"]
            self.assertEqual(price_columns, list(range(1, 28, 2)))
            expected = {}
            for row_index, row in enumerate(native[4:], 5):
                for col in price_columns:
                    price = row[col] if col < len(row) else None
                    if isinstance(price, (int, float)) and price > 0:
                        variation = row[col + 1] if col + 1 < len(row) else None
                        expected[f"Boletín diario!row {row_index},col {col + 1}"] = (
                            normalize(row[0]), normalize(native[2][col]), price,
                            variation if isinstance(variation, (int, float)) else None,
                            variation,
                        )
        finally:
            book.close()
        self.assertEqual(len(expected), 394)
        with patch.object(ocr, "transcribe", side_effect=AssertionError("Unexpected OCR")):
            result = daily_recovery.parse_daily(self.body, DAY)
        actual = {}
        for row in result["rows"]:
            self.assertEqual(row[2], DAY)
            locator = row[0]
            match = re.fullmatch(r"Boletín diario!row (\d+),col (\d+)", locator)
            self.assertIsNotNone(match, locator)
            expected_variation = row[-1]["raw_change"]
            actual[locator] = (normalize(row[3]), normalize(row[4]), row[6],
                               row[7], expected_variation)
            self.assertEqual(row[-1]["date_resolution"],
                             daily_recovery.VERIFIED_DATE_RECOVERIES[XLS_SHA])
        self.assertEqual(len(result["rows"]), 394)
        self.assertEqual(result["reviews"], [])
        self.assertEqual(result["date_resolutions"],
                         [daily_recovery.VERIFIED_DATE_RECOVERIES[XLS_SHA]])
        self.assertEqual(actual, expected)

    def test_review_is_fail_closed_for_body_heading_and_expected_day(self):
        with self.assertRaises((ValueError, worker.SourceDateMismatch)):
            daily_recovery.parse_daily(self.body + b"changed", DAY)
        with self.assertRaises(worker.SourceDateMismatch):
            daily_recovery.parse_daily(self.body, date(2019, 12, 3))
        book = openpyxl.load_workbook(io.BytesIO(self.body), read_only=True, data_only=True)
        try:
            headings = [list(row) for row in
                        book["Boletín diario"].iter_rows(max_row=4, values_only=True)]
        finally:
            book.close()
        headings[1][0] = "Lunes 02 de otro mes de 2019"
        with self.assertRaisesRegex(worker.SourceDateMismatch, "heading no longer agrees"):
            daily_recovery._publication_day(self.body, headings, DAY)

    def test_exact_retained_binding_version_and_repair_queue_are_scoped(self):
        expected_version = worker.asset_parser_version("daily", URL)
        self.assertTrue(expected_version.endswith(":dec2019-native-month-review-v1"))
        self.assertEqual(worker.asset_parser_version("daily", URL + "?other"),
                         worker.parser_version("daily"))
        self.assertIn((URL, "daily", XLS_SHA), PRIORITY_SOURCE_REPAIRS)
        versions = expected_versions().obj
        self.assertEqual(versions["url:" + URL], expected_version)

        class Result:
            def __init__(self, value):
                self.value = value
            def fetchone(self):
                return (self.value,) if self.value is not None else None

        class DB:
            def __init__(self, value, old_version="daily-units-v6:dane-daily-query-v1"):
                self.value = value
                self.old_version = old_version
                self.calls = 0
                self.args = None
            def execute(self, sql, args):
                self.calls += 1
                self.args = args
                # Model the query's stale-version predicate, rather than blindly
                # returning a row for an already-current asset.
                if self.old_version == args[3]:
                    return Result(None)
                return Result(self.value)

        stale = DB(self.body)
        self.assertEqual(retained_exact_date_repair(stale, URL, "daily", expected_version),
                         self.body)
        self.assertEqual(stale.calls, 1)
        self.assertIn(XLS_SHA, stale.args)
        current = DB(self.body, old_version=expected_version)
        self.assertIsNone(retained_exact_date_repair(current, URL, "daily", expected_version))
        wrong_url = DB(self.body)
        self.assertIsNone(retained_exact_date_repair(wrong_url, URL + "?other", "daily",
                                                     expected_version))
        self.assertEqual(wrong_url.calls, 0)
        wrong_kind = DB(self.body)
        self.assertIsNone(retained_exact_date_repair(wrong_kind, URL, "monthly",
                                                     expected_version))
        self.assertEqual(wrong_kind.calls, 0)
        corrupt = DB(self.body + b"changed")
        with self.assertRaisesRegex(ValueError, "SHA mismatch"):
            retained_exact_date_repair(corrupt, URL, "daily", expected_version)

    def test_date_recovery_does_not_enqueue_image_ocr(self):
        self.assertEqual(list(ocr.spreadsheet_images(self.body, failed_only=True,
                                                      normal_extraction_failed=False)), [])


if __name__ == "__main__":
    unittest.main()

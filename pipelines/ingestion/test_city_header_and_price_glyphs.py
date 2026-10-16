"""Two unchanged DANE city originals with subtitle-first market headers."""
from datetime import date
from decimal import Decimal
import hashlib
from pathlib import Path
import unittest
from copy import deepcopy
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pdfplumber

from . import city_reports as city

DATA = Path(__file__).parent / "testdata"


class NativeCityHeaderAndPrices(unittest.TestCase):
    def test_october_source_keeps_market_category_package_and_rounds(self):
        body = (DATA / "city_bogota_subtitle_first_2024_10_05.pdf").read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(),
                         "75d454bff398b58aa1dd40b6326222382c9ef1f1dec026a38c2ea7a010fd1265")
        rows = list(city.parse_city_pdf(body, date(2024, 10, 5)))
        self.assertEqual(len(rows), 198)
        samples = [r for r in rows if r[0] in (
            "PDF page 1,table 1,row 6,round 1", "PDF page 1,table 1,row 6,round 2")]
        self.assertEqual(len(samples), 2)
        for sample in samples:
            self.assertEqual(sample[1:9], (date(2024, 10, 5), "limon-tahiti", "Limón tahití",
                "Bogotá, D.C., Corabastos", "Frutas > Cítricos", "Bulto", Decimal(70), "Kilogramo"))
        self.assertEqual(samples[0][11:14], (Decimal(300000), Decimal(310000), "kg"))
        self.assertEqual(samples[1][11:14], (Decimal(300000), Decimal(320000), "kg"))

    def test_january_source_native_comma_grouping_and_overlapping_padding_spaces(self):
        body = (DATA / "city_bogota_subtitle_first_2024_01_02.pdf").read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(),
                         "1113847acd00d9cf7850f2fa2c0b2ad60307d7a5c4de593e21f407f442693f98")
        rows = list(city.parse_city_pdf(body, date(2024, 1, 2)))
        self.assertEqual(len(rows), 189)
        first = next(r for r in rows if r[0] == "PDF page 1,table 1,row 5,round 1")
        self.assertEqual(first[1:9], (date(2024, 1, 2), "limon-comun", "Limón común",
            "Bogotá, Corabastos", "Frutas", "Bulto", Decimal(70), "Kilogramo"))
        self.assertEqual(first[11:14], (Decimal(140000), Decimal(150000), "kg"))
        self.assertEqual(first[14], Decimal(2000))
        second = next(r for r in rows if r[0] == "PDF page 1,table 1,row 5,round 2")
        self.assertEqual(second[11:14], (Decimal(140000), Decimal(140000), "kg"))
        banana = next(r for r in rows if r[3] == "Banano criollo" and r[9] == 1)
        self.assertEqual(banana[11:14], (Decimal(2100), Decimal(2200), "kg"))

    def test_header_fallback_requires_adjacent_quality_market_and_date(self):
        self.assertEqual(city._market_heading(
            "PRECIOS DE VENTA MAYORISTA\nPRODUCTOS DE PRIMERA CALIDAD\nBogotá, Corabastos\n2 de enero de 2024"),
            "Bogotá, Corabastos")
        self.assertIsNone(city._market_heading(
            "PRECIOS DE VENTA MAYORISTA\nPRODUCTOS DE PRIMERA CALIDAD\nProducto\nBogotá, Corabastos\n2 de enero de 2024"))
        self.assertIsNone(city._market_heading(
            "PRECIOS DE VENTA MAYORISTA\nPRODUCTOS DE PRIMERA CALIDAD\nBogotá, Corabastos"))

    def test_number_syntax_preserves_digits_and_decimal_precision(self):
        for token, expected in (("140,000", "140000"), ("1,250,000", "1250000"),
                                ("140.000", "140000"), ("1,25", "1.25")):
            with self.subTest(token=token):
                self.assertEqual(city._city_number(token), Decimal(expected))

    def test_native_price_padding_does_not_merge_separate_or_duplicate_runs(self):
        table = [["Limón", "Bulto", "70 Kilogramo", "1 50,000", "150000", "0", "0"]]
        original = [{"text": text, "x0": i * 5, "x1": i * 5 + 5,
                     "top": 10, "bottom": 20} for i, text in enumerate("150,000")]
        separated = deepcopy(original)
        for char in separated[1:]:
            char["x0"] += 15
            char["x1"] += 15
        duplicate = deepcopy(original) + [deepcopy(original[0])]
        two_lines = deepcopy(original)
        two_lines[-1]["top"] += 3
        for name, chars, expected in (
            ("one contiguous printed amount", original, "150,000"),
            ("two separated amounts", separated, "1 50,000"),
            ("duplicated leading digit", duplicate, "1 50,000"),
            ("different text baselines", two_lines, "1 50,000"),
        ):
            page = Mock(spec=pdfplumber.page.Page)
            page.extract_tables.side_effect = [[deepcopy(table)], [deepcopy(table)]]
            page.find_tables.return_value = [SimpleNamespace(rows=[
                SimpleNamespace(cells=[None, None, None, (0, 0, 100, 30), None, None, None])])]
            page.chars = chars
            with self.subTest(name=name):
                self.assertEqual(city._city_tables(page)[0][0][3], expected)

    def test_older_bogota_heading_keeps_literal_name_and_verified_municipality(self):
        body = (DATA / "city_bogota_subtitle_first_2024_01_02.pdf").read_bytes()
        rows = list(city.parse_city_pdf(body, date(2024, 1, 2)))
        db = Mock()
        db.execute.side_effect = [Mock(fetchall=lambda: []), Mock(fetchall=lambda: [
            ("11001", "BOGOTÁ, D.C.", "BOGOTÁ, D.C.")])]
        db.transaction.return_value = nullcontext()
        with patch.object(city, "_bulk_insert") as insert:
            city.save_classifications(db, "original-id", rows)
        markets = next(call.args[2] for call in insert.call_args_list if call.args[1] == "market")
        self.assertEqual(markets, [("dane-city-bogota-corabastos", "Bogotá, Corabastos",
                                    "Bogotá", "Bogotá, D.C.", "11001")])

    def test_name_only_audit_does_not_treat_native_price_padding_as_name_change(self):
        from .city_product_corrections import REGIONAL_COLUMNS, verified_corrections

        body = (DATA / "city_bogota_subtitle_first_2024_01_02.pdf").read_bytes()
        originals = [dict(zip(REGIONAL_COLUMNS, row)) for row in city.parse_city_pdf(body)]
        self.assertEqual(verified_corrections(body, hashlib.sha256(body).hexdigest(),
                                             "https://www.dane.gov.co/original.zip", originals), [])


if __name__ == "__main__":
    unittest.main()

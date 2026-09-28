"""Actual Futura native tables: cell boundaries, wrapped places and strict dates."""

import hashlib
import re
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pdfplumber

from . import pdf_sources as inputs
from .test_input_pdf_recovery import parse
from .worker import SourceDateMismatch, parser_version

FIXTURES = Path("artifacts/source-verification-2026-09-28/inputs-milk")
DID = "8c5e95de023a6fafd71484dc476c40083aa886d05ca00f90ada498cac05043f7"


def word(text, x, y, right=None, font="FuturaStd-Book"):
    return {
        "text": text,
        "x0": x,
        "x1": right or x + 50,
        "top": y,
        "bottom": y + 8,
        "fontname": font,
    }


class NativeGeometry(unittest.TestCase):
    def test_known_heavy_heading_is_not_arbitrary_font_guess(self):
        self.assertTrue(
            inputs._input_heading_word(
                word("Carrier", 45, 0, font="ABC+FuturaStd-Heavy")
            )
        )
        for font in [
            "ABC+FuturaStd-Book",
            "ABC+Unrecognized-Medium",
            "ABC+HeavilySpaced",
        ]:
            self.assertFalse(
                inputs._input_heading_word(word("Carrier", 45, 0, font=font))
            )
        self.assertEqual(inputs.INPUT_PDF_VERSION, parser_version("inputs-pdf"))
        self.assertEqual(inputs.INPUT_PDF_VERSION, "inputs-pdf-v8")

    def test_centered_header_requires_exact_contiguous_column_rules(self):
        p = MagicMock(
            horizontal_edges=[
                {"x0": 41, "x1": 175, "top": 136},
                {"x0": 175, "x1": 237, "top": 136},
                {"x0": 237, "x1": 301, "top": 136},
                {"x0": 317, "x1": 576, "top": 136},
            ]
        )
        self.assertEqual(inputs._input_ruled_left(p, 134, 0, 306, 182), 41)
        p.horizontal_edges = [
            {"x0": 41, "x1": 175, "top": 136},
            {"x0": 185, "x1": 301, "top": 136},
        ]
        with self.assertRaises(ValueError):
            inputs._input_ruled_left(p, 134, 0, 306, 182)

    def test_explicit_department_wrap_and_hyphen_preserve_literal_lines(self):
        for first, last, full in [
            (
                "Villa de San Diego de Ubaté",
                "(Cundinamarca)",
                "Villa de San Diego de Ubaté (Cundinamarca)",
            ),
            (
                "Villa de San Diego de Ubaté",
                "Cundinamarca)",
                "Villa de San Diego de Ubaté (Cundinamarca)",
            ),
            (
                "Guadalajara de Buga (Valle del",
                "Cauca)",
                "Guadalajara de Buga (Valle del Cauca)",
            ),
            (
                "Villa de San Diego de Ubaté (Cun-",
                "dinamarca)",
                "Villa de San Diego de Ubaté (Cundinamarca)",
            ),
        ]:
            with self.subTest(first=first, last=last):
                lines = [
                    (
                        100,
                        [
                            word(first, 40, 100, right=170),
                            word("32.667", 205, 100),
                            word("n.d.", 280, 100),
                        ],
                    ),
                    (109.6, [word(last, 42.5, 109.6, right=150)]),
                ]
                numeric = re.fullmatch(
                    r"(.+?)\s+(\d[\d.,]*)\s+(n\.d\.)", first + " 32.667 n.d."
                )
                result = inputs._input_wrapped_department(lines, 0, 180, numeric, True)
                self.assertEqual(result, (full, "32.667", "n.d.", [first, last]))

    def test_department_never_guessed_across_distance_price_or_heading(self):
        first = "Villa de San Diego de Ubaté"
        numeric = re.fullmatch(r"(.+) (\d+) (\d+)", first + " 1000 0")
        for suffix in [
            word("(Departamento inventado)", 40, 109, right=170),
            word("(Cundinamarca)", 40, 130, right=150),
            word("(Cundinamarca)", 205, 109),
            word("(Cundinamarca)", 40, 109, font="FuturaStd-Heavy"),
        ]:
            lines = [
                (
                    100,
                    [
                        word(first, 40, 100, right=170),
                        word("1000", 205, 100),
                        word("0", 280, 100),
                    ],
                ),
                (suffix["top"], [suffix]),
            ]
            with self.subTest(suffix=suffix):
                self.assertIsNone(
                    inputs._input_wrapped_department(lines, 0, 180, numeric, True)
                )

    def test_explicit_department_below_full_municipality_is_bound_not_empty(self):
        previous = (100, [word("Cali", 40, 100, right=70)], ["Cali"])
        current = [
            word("(Valle del Cauca)", 40, 109, right=165),
            word("11.157", 205, 109),
        ]
        self.assertEqual(inputs._input_location_prefix(previous, current, 180), "Cali")
        current[0]["text"] = "(Lugar desconocido)"
        self.assertEqual(inputs._input_location_prefix(previous, current, 180), "")

    def test_missing_municipality_fails_instead_of_publishing_empty_identity(self):
        with self.assertRaisesRegex(ValueError, "lacks a municipality"):
            parse(
                [
                    (35, 680, "Producto, 1 litro", True),
                    (35, 655, "(Caldas)", False),
                    (210, 655, "10.000", False),
                ]
            )


@unittest.skipUnless(
    (FIXTURES / "originals" / f"{DID}.pdf").exists(),
    "Actual retained original required",
)
class ActualNativeTables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = (FIXTURES / "originals" / f"{DID}.pdf").read_bytes()
        assert hashlib.sha256(cls.data).hexdigest() == DID
        cls.rows = list(inputs.parse_input_pdf(cls.data, date(2019, 2, 28)))

    def test_independent_complete_positive_price_variation_cell_reconciliation(self):
        # Poppler -layout is independent of the pdfplumber parser. Exclude the
        # identified narrative/axis coincidence on p88, never a data-table row.
        source = (FIXTURES / "feb2019-full-poppler.txt").read_text().split("\f")
        pattern = re.compile(
            r"(?<!\S)(\d[\d.,]*)(?: {2,})(n\.?\s*d\.|[-+]?\d[\d.,]*)(?=\s{2,}|$)",
            re.IGNORECASE,
        )
        printed = Counter()
        for page, text in enumerate(source, 1):
            if "mercados" not in text or "Precio medio" not in text:
                continue
            for line in text.splitlines():
                if page == 88 and "La tendencia del precio de Lorsban" in line:
                    continue
                for match in pattern.finditer(line):
                    price = float(match[1].replace(".", "").replace(",", "."))
                    change = (
                        None
                        if match[2].lower().startswith("n")
                        else float(match[2].replace(".", "").replace(",", "."))
                    )
                    if price > 0:
                        printed[(page, price, change)] += 1
        actual = Counter((r[-1]["page"], r[6], r[7]) for r in self.rows)
        self.assertEqual(sum(printed.values()), 14366)
        self.assertEqual(actual, printed)
        self.assertTrue(
            all(r[3] and r[4] and r[5] and r[2] == date(2019, 2, 28) for r in self.rows)
        )
        self.assertFalse(any(r[-1].get("quality_issue") for r in self.rows))

    def test_actual_visually_verified_product_places_and_packages(self):
        anchors = [
            (11, "Carrier", "Socorro", "1 litro", 19750),
            (11, "Cosmo-Aguas", "Villa de San Diego de Ubaté", "1 kilogramo", 32667),
            (
                11,
                "Ethrel 48 Sl",
                "Guadalajara de Buga",
                "200 centímetros cúbicos",
                52767,
            ),
            (22, "Cal dolomita 57-35", "Guadalajara de Buga", "50 kilogramos", 11263),
        ]
        for page, product, town, unit, price in anchors:
            with self.subTest(anchor=(page, product, town)):
                rows = [
                    r
                    for r in self.rows
                    if r[-1]["page"] == page
                    and r[3:7] == (product, town, unit, float(price))
                ]
                self.assertEqual(len(rows), 1)
                self.assertTrue(rows[0][0].startswith(f"PDF page {page},col "))
                self.assertEqual(rows[0][-1]["parser_version"], "inputs-pdf-v8")
        wrapped = [
            r
            for r in self.rows
            if r[-1]["page"] == 200
            and r[4] == "Villa de San Diego de Ubaté"
            and r[6] == 209133
        ]
        self.assertEqual(len(wrapped), 1)
        self.assertEqual(
            wrapped[0][-1]["printed_location_lines"],
            ["Villa de San Diego de Ubaté (Cun-", "dinamarca)"],
        )

    def test_actual_feb2016_wrapped_full_names_prevent_empty_locations(self):
        p = Path(
            "artifacts/extraction-robustness-2026-09-27/inputs-pdf/Bol_Insumos_feb_2016.pdf"
        )
        if not p.exists():
            self.skipTest("Retained February 2016 original required")
        with pdfplumber.open(p) as pdf:
            wrapper = MagicMock()
            wrapper.__enter__.return_value.pages = [pdf.pages[78]]
            with patch.object(pdfplumber, "open", return_value=wrapper):
                rows = list(inputs.parse_input_pdf(b"", date(2016, 2, 29)))
        for town, price in [("Cali", 11157), ("Valledupar", 13867)]:
            found = [
                r
                for r in rows
                if r[3] == "Negasunt aerosol" and r[4] == town and r[6] == price
            ]
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0][5], "300 centímetros cúbicos")
        self.assertTrue(all(r[4] for r in rows))

    def test_actual_feb2016_caption_column_conflict_is_retained_for_review(self):
        p = Path(
            "artifacts/extraction-robustness-2026-09-27/inputs-pdf/Bol_Insumos_feb_2016.pdf"
        )
        if not p.exists():
            self.skipTest("Retained February 2016 original required")
        with pdfplumber.open(p) as pdf:
            wrapper = MagicMock()
            wrapper.__enter__.return_value.pages = [pdf.pages[83]]
            with patch.object(pdfplumber, "open", return_value=wrapper):
                rows = list(inputs.parse_input_pdf(b"", date(2016, 2, 29)))
        self.assertGreater(len(rows), 30)
        self.assertTrue(all(r[1] == "dane-inputs-pdf-unresolved" for r in rows))
        self.assertTrue(all("diciembre" in r[-1]["quality_issue"] for r in rows))
        self.assertTrue(
            all(r[-1]["printed_price_column_months"] == ["diciembre"] for r in rows)
        )
        found = [r for r in rows if r[4] == "Cúcuta" and r[6] == 900000]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][-1]["printed_table_caption"], "2016 (febrero)")

    def test_actual_feb2018_wrong_year_caption_remains_review(self):
        p = (
            FIXTURES
            / "originals/54cb32e0d9f7a5f02468fa5efb56acac8618897e4c8210d5d39d019dba897de5.pdf"
        )
        with pdfplumber.open(p) as pdf:
            wrapper = MagicMock()
            wrapper.__enter__.return_value.pages = [pdf.pages[140]]
            with (
                patch.object(pdfplumber, "open", return_value=wrapper),
                self.assertRaisesRegex(SourceDateMismatch, "2017"),
            ):
                list(inputs.parse_input_pdf(b"", date(2018, 2, 28)))


if __name__ == "__main__":
    unittest.main()

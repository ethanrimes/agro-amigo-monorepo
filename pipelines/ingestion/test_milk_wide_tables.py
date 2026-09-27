"""Independent native checks for the September 2021 wide milk price table."""

import re
import shutil
import subprocess
import unittest
from collections import Counter
from datetime import date
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from .special_prices import _milk_full_width_table, parse_milk_pdf
from .worker import SourceDateMismatch

FIXTURE = Path("artifacts/source-ambiguity-2026-09-27/city-milk/milk-sep2021.pdf")
DEPARTMENTS = {
    "Antioquia",
    "Arauca",
    "Atlántico",
    "Bolívar",
    "Boyacá",
    "Caldas",
    "Caquetá",
    "Casanare",
    "Cauca",
    "Cesar",
    "Córdoba",
    "Cundinamarca",
    "Huila",
    "La Guajira",
    "Magdalena",
    "Meta",
    "Nariño",
    "Norte de Santander",
    "Putumayo",
    "Quindío",
    "Risaralda",
    "Santander",
    "Sucre",
    "Tolima",
    "Valle del Cauca",
}


def wide_page(
    month="Septiembre de 2021", *, body="Antioquia\nAbejorral 1.100 1.320 1.209 ="
):
    text = (
        "Boletín Técnico N° 108\nLeche Cruda en Finca\n"
        f"{month}\nCuadro 1. Precios de leche cruda en finca.\n"
        "Departamentos y Precio Precio Precio\nTendencia\n"
        f"municipios Mínimo Máximo Promedio\n{body}"
    )
    words = [
        {"text": label, "x0": x, "top": top}
        for label, x, top in [
            ("Departamentos", 130, 150),
            ("Mínimo", 263, 167),
            ("Máximo", 320, 167),
            ("Promedio", 374, 167),
            ("Precio", 265, 150),
            ("Precio", 320, 150),
            ("Precio", 378, 150),
        ]
    ]
    return SimpleNamespace(
        width=612,
        height=792,
        extract_text=lambda: text,
        extract_words=lambda: words,
        close=lambda: None,
        crop=lambda box: SimpleNamespace(
            extract_text=lambda: text if box[2] == 612 else ""
        ),
    )


def parse_pages(pages, day=None):
    pdf = MagicMock()
    pdf.__enter__.return_value.pages = pages
    with patch("pdfplumber.open", return_value=pdf):
        return list(parse_milk_pdf(b"native fixture", day))


class MilkWideTables(unittest.TestCase):
    def test_wide_table_report_heading_not_publication_date(self):
        rows = parse_pages([wide_page()], date(2021, 9, 30))
        self.assertEqual(
            rows[0][2:7],
            (date(2021, 9, 30), "Leche cruda en finca", "Abejorral", "litre", 1209.0),
        )
        self.assertEqual(rows, parse_pages([wide_page()]))
        self.assertEqual(rows[0][-1]["min_price"], 1100)
        self.assertEqual(rows[0][-1]["max_price"], 1320)

    def test_archive_and_each_continuation_heading_must_agree(self):
        with self.assertRaises(SourceDateMismatch):
            parse_pages([wide_page()], date(2021, 11, 30))
        with self.assertRaises(SourceDateMismatch):
            parse_pages([wide_page(), wide_page("Octubre de 2021")])

    def test_missing_report_month_never_uses_publication_or_narrative_date(self):
        for heading in (
            "",
            "16 de noviembre de 2021",
            "Durante septiembre de 2021 hubo lluvia.",
        ):
            with (
                self.subTest(heading=heading),
                self.assertRaisesRegex(ValueError, "no verifiable report month"),
            ):
                parse_pages([wide_page(heading)], date(2021, 9, 30))

    def test_wide_header_requires_one_aligned_monetary_grid(self):
        page = wide_page()
        self.assertTrue(_milk_full_width_table(page))
        original = page.extract_words()
        for words in (
            original + [{"text": "Departamentos", "x0": 410, "top": 150}],
            [word for word in original if word["text"] != "Precio"],
            [
                {**word, "top": 250} if word["text"] == "Máximo" else word
                for word in original
            ],
        ):
            page.extract_words = lambda words=words: words
            self.assertFalse(_milk_full_width_table(page))

    def test_native_glyph_spacing_preserves_explicit_department_letters(self):
        rows = parse_pages(
            [
                wide_page(body="Norte de Santa nder\nChinácota 1.000 1.100 1.045 ="),
            ]
        )
        self.assertEqual(rows[0][4], "Chinácota")
        self.assertEqual(rows[0][-1]["department"], "Norte de Santander")
        with self.assertRaisesRegex(ValueError, "without a department"):
            parse_pages(
                [wide_page(body="Norte de Santader\nChinácota 1.000 1.100 1.045 =")]
            )

    def test_department_continues_to_next_page_but_never_appears_from_nowhere(self):
        rows = parse_pages(
            [
                wide_page(body="Bolívar\nArjona 1.000 1.200 1.106 ="),
                wide_page(body="Calamar 1.000 1.200 1.085 ᵒᵒ"),
            ]
        )
        self.assertEqual(
            [row[-1]["department"] for row in rows], ["Bolívar", "Bolívar"]
        )
        with self.assertRaisesRegex(ValueError, "without a department"):
            parse_pages([wide_page(body="Calamar 1.000 1.200 1.085 ᵒᵒ")])

    @unittest.skipUnless(
        FIXTURE.exists() and shutil.which("pdftotext"),
        "retained official PDF and Poppler required",
    )
    def test_all_actual_price_cells_match_independent_poppler_text(self):
        body = FIXTURE.read_bytes()
        self.assertEqual(
            sha256(body).hexdigest(),
            "f9787aa7e94848bd7dc0c69d12511919cc49c4751898f14acbdf4fab3416874e",
        )
        # Independent extraction engine and full-page text, no parser helpers.
        text = subprocess.check_output(
            ["pdftotext", "-f", "8", "-l", "13", "-layout", str(FIXTURE), "-"]
        ).decode()
        expected, department = [], None
        for page_number, page in enumerate(text.split("\f"), 8):
            for line in page.splitlines():
                line = " ".join(line.split())
                if line in DEPARTMENTS:
                    department = line
                match = re.fullmatch(
                    r"(.+?)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+[=ᵒx]+", line
                )
                if match:
                    town, low, high, mean = match.groups()
                    self.assertIsNotNone(department)
                    expected.append(
                        (
                            department,
                            town,
                            int(low.replace(".", "")),
                            int(high.replace(".", "")),
                            int(mean.replace(".", "")),
                            page_number,
                        )
                    )
        rows = list(parse_milk_pdf(body, date(2021, 9, 30)))
        actual = [
            (
                row[-1]["department"],
                row[4],
                row[-1]["min_price"],
                row[-1]["max_price"],
                row[6],
                row[-1]["page"],
            )
            for row in rows
        ]
        self.assertEqual(len(expected), 208)
        self.assertEqual(actual, expected)
        self.assertEqual(len({(row[0], row[1]) for row in actual}), 208)
        self.assertEqual(len({row[0] for row in actual}), 25)
        self.assertEqual(
            Counter(row[-1] for row in actual),
            {8: 35, 9: 36, 10: 36, 11: 36, 12: 34, 13: 31},
        )
        self.assertEqual(len({row[0] for row in rows}), 208)
        self.assertTrue(
            all(row[2] == date(2021, 9, 30) and row[5] == "litre" for row in rows)
        )
        self.assertEqual(rows, list(parse_milk_pdf(body, None)))


if __name__ == "__main__":
    unittest.main()

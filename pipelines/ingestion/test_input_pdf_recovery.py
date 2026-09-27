"""Native input PDF recovery: exact printed identity before OCR or review.

Real original fixtures are downloaded and SHA-recorded in the ignored audit
folder; AGRO_INPUT_PDF_FIXTURES may point to a copy. No network or DB calls.
"""

import io
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pdfplumber
from reportlab.pdfgen import canvas

from pipelines.ingestion.pdf_sources import (
    INPUT_PDF_VERSION,
    _input_presentation,
    parse_input_pdf,
)


def source(lines):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(612, 792))
    for x, y, text, bold in [
        (35, 740, "Cuadro 13. Precios de elementos pecuarios", True),
        (35, 728, "2014 (marzo)", True),
        (35, 705, "Productos y mercados", False),
        (200, 705, "Precio medio", False),
        *lines,
    ]:
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 8)
        pdf.drawString(x, y, text)
    pdf.save()
    return buffer.getvalue()


def parse(lines):
    return list(parse_input_pdf(source(lines), date(2014, 3, 31)))


class InputPDFRecovery(unittest.TestCase):
    def test_no_space_after_comma_keeps_capacity_with_product(self):
        rows = parse(
            [
                (35, 680, "Fumigadora plastica manual", True),
                (35, 672, "15 litros,unidad", True),
                (35, 655, "Manizales (Caldas)", False),
                (210, 655, "90.367", False),
            ]
        )
        self.assertEqual(
            rows[0][3:7],
            (
                "Fumigadora plastica manual 15 litros",
                "Manizales",
                "unidad",
                90367,
            ),
        )

    def test_plain_font_continuation_never_borrows_previous_bottle_size(self):
        rows = parse(
            [
                (35, 680, "Curacron 500 EC, 1 litro", True),
                (35, 668, "Andes (Antioquia)", False),
                (210, 668, "46.753", False),
                (35, 650, "Curacron 500 EC,", True),
                (35, 642, "250 centimetros cubicos", False),
                (35, 630, "Andes (Antioquia)", False),
                (210, 630, "14.990", False),
            ]
        )
        self.assertEqual(
            [(r[5], r[6]) for r in rows],
            [
                ("1 litro", 46753),
                ("250 centimetros cubicos", 14990),
            ],
        )

    def test_glyph_font_change_does_not_split_unit_or_lose_heading(self):
        prefix = "1 kilogra"
        from reportlab.pdfbase.pdfmetrics import stringWidth

        rows = parse(
            [
                (35, 680, "Pasto Brachiaria,", True),
                (35, 672, prefix, True),
                (35 + stringWidth(prefix, "Helvetica-Bold", 8), 672, "mo", False),
                (35, 655, "Cali (Valle del Cauca)", False),
                (210, 655, "22.080", False),
            ]
        )
        self.assertEqual(
            rows[0][3:7], ("Pasto Brachiaria", "Cali", "1 kilogramo", 22080)
        )
        self.assertEqual(
            rows[0][-1]["printed_heading_lines"], ["Pasto Brachiaria,", "1 kilogramo"]
        )

    def test_decimal_commas_are_not_presentation_delimiters(self):
        self.assertEqual(
            _input_presentation(
                "Alevino 2,5-3,5 centimetros, paquete por 100 unidades", []
            ),
            (
                "Alevino 2,5-3,5 centimetros",
                "paquete por 100 unidades",
            ),
        )
        self.assertEqual(
            _input_presentation("Producto, 2,5 litros", []), ("Producto", "2,5 litros")
        )
        self.assertIsNone(_input_presentation("Bebedero 6,5 litros", []))

    def test_literal_standalone_unit_line_is_preserved_not_inferred(self):
        rows = parse(
            [
                (35, 680, "Bebedero plastico aves 6,5 litros", True),
                (35, 672, "unidad 1 unidad", True),
                (35, 655, "Espinal (Tolima)", False),
                (210, 655, "12.233", False),
            ]
        )
        self.assertEqual(
            rows[0][3:7],
            ("Bebedero plastico aves 6,5 litros", "Espinal", "unidad 1 unidad", 12233),
        )

    def test_missing_presentation_is_review_and_valid_neighbor_survives(self):
        rows = parse(
            [
                (35, 680, "Bebedero plastico aves 6,5 litros", True),
                (35, 665, "Espinal (Tolima)", False),
                (210, 665, "12.233", False),
                (35, 640, "Producto valido, 1 litro", True),
                (35, 625, "Espinal (Tolima)", False),
                (210, 625, "10.000", False),
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1], "dane-inputs-pdf-unresolved")
        self.assertEqual(rows[0][5], "Sin presentación verificable")
        self.assertTrue(rows[0][-1]["quality_issue"])
        self.assertEqual(rows[1][1], "dane-inputs-pdf")
        self.assertEqual(rows[1][3:7], ("Producto valido", "Espinal", "1 litro", 10000))

    def test_distant_or_price_column_text_cannot_supply_missing_unit(self):
        for extra in [
            [(35, 655, "250 centimetros cubicos", False)],
            [(35, 672, "250 centimetros cubicos", False), (210, 672, "7.000", False)],
        ]:
            with self.subTest(extra=extra):
                rows = parse(
                    [
                        (35, 680, "Producto sin presentacion", True),
                        *extra,
                        (35, 630, "Espinal (Tolima)", False),
                        (210, 630, "10.000", False),
                    ]
                )
                self.assertEqual(rows[0][1], "dane-inputs-pdf-unresolved")


FIXTURES = Path(
    os.environ.get(
        "AGRO_INPUT_PDF_FIXTURES",
        Path(__file__).resolve().parents[2]
        / "artifacts/extraction-robustness-2026-09-27/inputs-pdf",
    )
)

# Independently transcribed from rendered original pages, not parser output.
REAL_CASES = [
    (
        "insumos_factores_de_produccion_jul_2014.pdf",
        57,
        date(2014, 7, 31),
        "Fumigadora plástica manual 15 litros",
        "Manizales",
        "unidad",
        90367,
    ),
    (
        "insumos_factores_de_produccion_febrero_2013.pdf",
        22,
        date(2013, 2, 28),
        "Penicilina benzatínica procaínica y potásica 6 M. U. I.",
        "Anserma",
        "20 centímetros cúbicos",
        11900,
    ),
    (
        "insumos_factores_de_produccion_junio_2013.pdf",
        57,
        date(2013, 6, 30),
        "Curacron 500 EC",
        "Andes",
        "250 centímetros cúbicos",
        14990,
    ),
    (
        "insumos_factores_de_produccion_dic_2013.pdf",
        56,
        date(2013, 12, 31),
        "Gallina/polla ponedora hembra Hy-Line Brown menos de 1 semana",
        "Andes",
        "unidad",
        2550,
    ),
    (
        "insumos_factores_de_produccion_mar_2014.pdf",
        51,
        date(2014, 3, 31),
        "Bebedero plástico aves 6,5 litros",
        "Espinal",
        "unidad 1 unidad",
        12233,
    ),
    (
        "Bol_Insumos_sep_2015.pdf",
        85,
        date(2015, 9, 30),
        "Alevino cachama híbrida macho 2,5-3,5 centímetros",
        "Cereté",
        "paquete por 100 unidades",
        6733,
    ),
    (
        "Bol_Insumos_oct_2015.pdf",
        79,
        date(2015, 10, 31),
        "Pasto Brachiaria Brizantha CV. MG-5 Xaraes-Toledo-Victoria",
        "Cali",
        "1 kilogramo",
        22080,
    ),
    (
        "Bol_Insumos_feb_2016.pdf",
        81,
        date(2016, 2, 29),
        "Pasto Brachiaria brizantha CV. MG-5 Xaraes-Toledo-Victoria",
        "Cali",
        "1 kilogramo",
        20833,
    ),
]


class ActualInputPDFPages(unittest.TestCase):
    @unittest.skipUnless(
        all((FIXTURES / c[0]).exists() for c in REAL_CASES),
        "real original audit fixtures unavailable",
    )
    def test_eight_printed_failures_recover_exact_identity_price_and_unit(self):
        for filename, page_number, day, *expected in REAL_CASES:
            with (
                self.subTest(filename=filename),
                pdfplumber.open(FIXTURES / filename, pages=[page_number]) as selected,
            ):
                # Only restrict the page list for test speed; font metrics and
                # words are still read from the unmodified original PDF bytes.
                with patch(
                    "pipelines.ingestion.pdf_sources.pdfplumber.open",
                    return_value=selected,
                ):
                    rows = list(
                        parse_input_pdf((FIXTURES / filename).read_bytes(), day)
                    )
                matches = [r for r in rows if r[3:7] == tuple(expected)]
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0][1], "dane-inputs-pdf")
                self.assertEqual(matches[0][-1]["parser_version"], INPUT_PDF_VERSION)
                self.assertEqual(
                    matches[0][-1]["extraction_method"], "native-pdf-word-geometry"
                )
                self.assertIsNone(matches[0][-1]["quality_issue"])
                if "sep_2015" in filename:
                    variants = {
                        (r[5], r[6])
                        for r in rows
                        if r[3] == expected[0] and r[4] == "Cereté"
                    }
                    self.assertEqual(
                        variants,
                        {
                            ("paquete por 100 unidades", 6733),
                            ("paquete por 50 unidades", 3033),
                        },
                    )
                if "junio_2013" in filename:
                    variants = {
                        (r[5], r[6])
                        for r in rows
                        if r[3] == "Curacron 500 EC" and r[4] == "Andes"
                    }
                    self.assertEqual(
                        variants,
                        {("1 litro", 46753), ("250 centímetros cúbicos", 14990)},
                    )


if __name__ == "__main__":
    unittest.main()

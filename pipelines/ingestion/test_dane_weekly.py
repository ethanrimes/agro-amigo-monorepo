"""Literal monetary semantics and native-first weekly source regressions."""

import io
import unittest
from datetime import date
from pathlib import Path

import openpyxl
from reportlab.pdfgen import canvas

from pipelines.ingestion import dane_weekly as weekly


def workbook(rows=None, note="", period="19 al 25 de septiembre de 2026"):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "1.1"
    sheet.append(["Boletín semanal precios mayoristas - " + period])
    sheet.append(["1.1. Verduras y hortalizas"])
    sheet.append(
        [
            "Producto",
            "Mercado mayorista",
            "Pesos por kilogramo",
            None,
            None,
            "Tendencia*",
        ]
    )
    sheet.append([None, None, "Precio mínimo", "Precio máximo", "Precio medio"])
    for row in rows or [["Acelga", "Bogotá, D.C., Corabastos", 333, 533, 418, "---"]]:
        sheet.append(row)
    sheet.append([note])
    supply = book.create_sheet("1.9")
    supply.append(["Abastecimiento (toneladas)", "Variación %"])
    supply.append([150236, 2.4])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def native_pdf(
    second_market="Armenia", second_mean="418", product_font="Helvetica-Bold"
):
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(612, 792))
    c.setFont("Helvetica", 9)
    for y, text in [
        (
            700,
            "Cuadro 2. Mercados mayoristas. Precios de venta de verduras y hortalizas",
        ),
        (684, "19 al 25 de septiembre de 2026"),
    ]:
        c.drawString(36, y, text)
    for origin in [36, 320]:
        c.drawString(origin, 665, "Pesos por kilogramo")
        for x, text in [
            (origin + 115, "Mínimo"),
            (origin + 155, "Máximo"),
            (origin + 195, "Medio"),
        ]:
            c.drawString(x, 647, text)
        c.setFont(product_font, 9)
        c.drawString(origin, 628, "Acelga")
        c.setFont("Helvetica", 9)
        c.drawString(origin, 610, "Bogotá" if origin == 36 else second_market)
        for x, value in [
            (origin + 115, "333"),
            (origin + 155, "533"),
            (origin + 195, "418" if origin == 36 else second_mean),
        ]:
            c.drawString(x, 610, value)
    c.save()
    return out.getvalue()


class WeeklySemantics(unittest.TestCase):
    def test_discovery_archives_old_sem_filenames_and_leaves_without_binary_decode(
        self,
    ):
        html = b"""<a href="mayoristas-boletin-semanal-2012-1">2012</a><a href="/files/Sem_30dic_5ene_2018.xls">Anexo</a><a href="/files/Semana4_junio_2012.pdf">PDF</a><a href="https://evil.test/files/Sem_30dic_5ene_2018.pdf">x</a>"""
        found = weekly.discover(html, weekly.WEEKLY, "dane-weekly-index")
        self.assertEqual(
            [kind for _, kind in found],
            ["dane-weekly-index", "dane-weekly-xlsx", "dane-weekly-pdf"],
        )
        self.assertEqual(weekly.discover(b"\xff\xfe", "x", "dane-weekly-pdf"), [])

    def test_explicit_week_formats_and_url_dates(self):
        for text, expected in [
            ("19 al 25 de septiembre de 2026", (date(2026, 9, 19), date(2026, 9, 25))),
            ("2012 (agosto 4 a 10)", (date(2012, 8, 4), date(2012, 8, 10))),
            ("2012 (16 a 22 de junio)", (date(2012, 6, 16), date(2012, 6, 22))),
            (
                "30 de diciembre al 5 de enero de 2018",
                (date(2017, 12, 30), date(2018, 1, 5)),
            ),
            (
                "27 de diciembre de 2025 al 2 de enero de 2026",
                (date(2025, 12, 27), date(2026, 1, 2)),
            ),
        ]:
            self.assertEqual(weekly._period(text), expected)
        self.assertEqual(
            weekly.source_date("bol-SIPSASemanal-27dic202502ene2026.pdf"),
            date(2026, 1, 2),
        )
        self.assertIsNone(weekly.source_date("Semana4_junio_2012.pdf"))
        self.assertIsNone(weekly._period("25 de septiembre de 2026"))
        with self.assertRaises(ValueError):
            weekly._period("1 al 25 de septiembre de 2026")

    def test_published_mean_is_not_midpoint_and_supply_is_not_price(self):
        rows = weekly.parse(workbook(), "annex.xlsx", "dane-weekly-xlsx")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["min"], r["max"], r["price"]), (333, 533, 418))
        self.assertEqual(r["details"]["price_statistic"], "published_mean")
        self.assertEqual(
            (r["date"], r["period_start"], r["unit"]),
            ("2026-09-25", "2026-09-19", "kg"),
        )
        self.assertEqual(r["details"]["period_type"], "weekly")

    def test_egg_and_liquid_units_require_explicit_notes_including_wrapping(self):
        rows = [
            ["Huevo rojo A", "Bogotá", 400, 500, 450, "="],
            ["Aceite vegetal mezcla", "Cali", 1000, 2000, 1500, "+"],
        ]
        notes = "(*) Los precios reportados para los huevos son pesos por\nunidad. ** Los precios reportados para aceite vegetal mezcla, jugo de frutas y vinagre son $ / litro."
        output = weekly.parse_workbook(workbook(rows, notes), "annex.xlsx")
        self.assertEqual([r["unit"] for r in output], ["unit", "litre"])
        uncertain = weekly.parse_workbook(workbook(rows), "annex.xlsx")
        self.assertTrue(
            all(r["price"] is None and r["details"]["quality_issue"] for r in uncertain)
        )
        self.assertEqual([r["details"]["literal_mean"] for r in uncertain], [450, 1500])

    def test_invalid_incomplete_and_nonfinite_cells_never_publish(self):
        for values in [
            (10, 20, 30),
            (0, 20, 10),
            (float("nan"), 20, 10),
            (float("inf"), float("inf"), float("inf")),
        ]:
            with self.assertRaises(ValueError):
                weekly._row(
                    "A",
                    "M",
                    *values,
                    "",
                    "Cat",
                    (date(2012, 6, 16), date(2012, 6, 22)),
                    "fixture",
                )
        with self.assertRaises(ValueError):
            weekly.parse_workbook(
                workbook([["A", "M", 10, None, 15, "="]]), "annex.xlsx"
            )
        with self.assertRaises(ValueError):
            weekly.parse_workbook(
                workbook(period="12 al 18 de septiembre de 2026"),
                "anex-SIPSASemanal-19sep25sep-2026.xlsx",
            )

    def test_native_two_column_pdf_and_literal_ocr_semantics(self):
        rows = weekly.parse_pdf(native_pdf(), "report.pdf")
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["price"] for r in rows], [418, 418])
        reading = {
            "text": "Cuadro 2. Mercados mayoristas. Precios de venta de verduras y hortalizas. 19 al 25 de septiembre de 2026. Pesos por kilogramo",
            "tables": [
                [
                    ["Productos y mercados", "Mínimo", "Máximo", "Medio", "Tendencia"],
                    ["Acelga", "", "", "", ""],
                    ["Bogotá", "333", "533", "418", "---"],
                ]
            ],
        }
        ocr = weekly._ocr_page(
            reading, "report.pdf", 1, {"eggs": False, "liquids": False}
        )
        self.assertEqual(
            (ocr[0]["product_name"], ocr[0]["market"], ocr[0]["price"]),
            ("Acelga", "Bogotá", 418),
        )
        reading["tables"][0][3:] = [["Bogotá", "333", "53%", "418", "---"]]
        with self.assertRaises(ValueError):
            weekly._ocr_page(
                reading, "report.pdf", 1, {"eggs": False, "liquids": False}
            )

    def test_scanned_price_page_requests_only_failed_page_and_preserves_native_rows(
        self,
    ):
        import pdfplumber
        from pypdf import PdfReader, PdfWriter
        from reportlab.lib.utils import ImageReader

        original = native_pdf()
        with pdfplumber.open(io.BytesIO(original)) as pdf:
            image = pdf.pages[0].to_image(resolution=80).original
        scanned = io.BytesIO()
        c = canvas.Canvas(scanned, pagesize=(612, 792))
        c.drawImage(ImageReader(image), 0, 0, width=612, height=792)
        c.setFont("Helvetica", 9)
        c.drawString(36, 770, "DANE SIPSA Boletín semanal de precios mayoristas")
        c.save()
        writer = PdfWriter()
        writer.add_page(PdfReader(io.BytesIO(original)).pages[0])
        writer.add_page(PdfReader(io.BytesIO(scanned.getvalue())).pages[0])
        merged = io.BytesIO()
        writer.write(merged)
        with self.assertRaises(weekly.NormalExtractionFailed) as caught:
            weekly.parse_pdf(merged.getvalue(), "report.pdf")
        self.assertEqual(caught.exception.required_pages, (2,))
        reading = {
            "text": "Cuadro 2. Mercados mayoristas. Precios de venta de verduras y hortalizas. 19 al 25 de septiembre de 2026. Pesos por kilogramo",
            "tables": [
                [
                    ["Producto", "Mercado", "Mínimo", "Máximo", "Medio"],
                    ["Acelga", "Bogotá", "333", "533", "418"],
                    ["Acelga", "Armenia", "333", "533", "418"],
                ]
            ],
        }
        rows = weekly.parse_with_ocr(
            merged.getvalue(), "report.pdf", "dane-weekly-pdf", {2: reading}
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual([r["source_page"] for r in rows], [1, 1, 2, 2])

    def test_legacy_grouped_workbook_preserves_unknown_units_for_review(self):
        book = openpyxl.Workbook()
        sheet = book.active
        for row in [
            ["2012 (10 a 16 de noviembre)"],
            ["Cuadro 1. Mercados mayoristas. Precios de venta de verduras"],
            ["Productos y mercados", "Precio mínimo", "Precio máximo", "Precio medio"],
            ["Acelga"],
            ["Bogotá", 333, 533, 418],
        ]:
            sheet.append(row)
        buffer = io.BytesIO()
        book.save(buffer)
        rows = weekly.parse_workbook(
            buffer.getvalue(), "Anexo_Bol_Semanal_SIPSA_Noviembre_16_2012.xls"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2012-11-16")
        self.assertIsNone(rows[0]["price"])
        self.assertEqual(rows[0]["details"]["literal_mean"], 418)
        self.assertIsNone(rows[0]["details"]["literal_unit_heading"])

    def test_directional_wrapped_market_labels_for_centered_and_bottom_aligned_prices(
        self,
    ):
        def word(text, x, top, bold=False):
            return {
                "text": text,
                "x0": x,
                "x1": x + 20,
                "top": top,
                "bottom": top + 8,
                "fontname": "Helvetica-Bold" if bold else "Helvetica",
                "size": 8,
            }

        headers = [
            word(text, x, 80)
            for text, x in [("Mínimo", 120), ("Máximo", 160), ("Medio", 200)]
        ]
        for upper, number, lower in [
            (110, 115.71, 121.40),
            (110, 113.874, 120.561),
            (110, 120, 120),
        ]:
            lines = [
                [word("Acelga", 30, 90, True)],
                [
                    word("Armenia", 30, 100),
                    word("100", 120, 100),
                    word("200", 160, 100),
                    word("150", 200, 100),
                ],
                [word("Medellín, Central Mayorista de", 30, upper)],
                [
                    word("300", 120, number),
                    word("500", 160, number),
                    word("418", 200, number),
                ],
                [word("Antioquia", 30, lower)],
            ]
            rows = weekly._native_column(
                lines,
                headers,
                "Verduras",
                (date(2012, 6, 16), date(2012, 6, 22)),
                1,
                1,
                1,
                {},
            )
            self.assertEqual(
                [(r["market"], r["price"]) for r in rows],
                [("Armenia", 150), ("Medellín, Central Mayorista de Antioquia", 418)],
            )

    def test_discovery_all_observed_legacy_prefixes_and_fragment_deduplication(self):
        html = """<a href="#contenido-importante">Skip</a><a href="#">Root</a><a href="/files/investigaciones/agropecuario/sipsa/Anexo_25_30abr_2015.xls">Anexo</a><a href="/files/investigaciones/agropecuario/sipsa/bol_31dic_al_06ene_2023.pdf#page=2">Boletín</a><a href="/files/investigaciones/agropecuario/sipsa/anex_31dic_al_06ene_2023.xlsx">Anexo</a>"""
        rows = weekly.discover(html, weekly.WEEKLY, "dane-weekly-index")
        self.assertEqual(len(rows), 3)
        self.assertFalse(any("#" in url for url, _ in rows))
        self.assertEqual(weekly.source_date(rows[1][0]), date(2023, 1, 6))
        self.assertEqual(
            weekly._period("2017-2018 (30 de diciembre al 5 de enero)"),
            (date(2017, 12, 30), date(2018, 1, 5)),
        )

    def test_conflicting_same_week_literal_quotes_remain_reviews(self):
        rows = weekly.parse_pdf(
            native_pdf(second_market="Bogotá", second_mean="419"), "report.pdf"
        )
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["price"] is None for row in rows))
        self.assertEqual([r["details"]["literal_mean"] for r in rows], [418, 419])

    def test_centered_category_and_unbolded_product_headings(self):
        def word(text, x, top, bold=False):
            return {
                "text": text,
                "x0": x,
                "x1": x + len(text) * 3,
                "top": top,
                "bottom": top + 8,
                "fontname": "Arial-BoldMT" if bold else "ArialMT",
                "size": 8,
            }

        headers = [
            word(text, x, 80)
            for text, x in [("Mínimo", 160), ("Máximo", 200), ("Medio", 240)]
        ]
        lines = [
            [word("Carne de cerdo", 130, 90, True)],
            [word("Pollo entero", 30, 106, True)],
            [
                word("Cúcuta, Cenabastos", 30, 114),
                word("5000", 160, 114),
                word("5200", 200, 114),
                word("5133", 240, 114),
            ],
            [word("Rabadillas de pollo", 30, 130)],
            [
                word("Cúcuta, Cenabastos", 30, 138),
                word("2000", 160, 138),
                word("2100", 200, 138),
                word("2033", 240, 138),
            ],
        ]
        rows = weekly._native_column(
            lines,
            headers,
            "Carnes",
            (date(2012, 11, 10), date(2012, 11, 16)),
            36,
            1,
            2,
            {},
        )
        self.assertEqual(
            [(r["product_name"], r["market"], r["price"]) for r in rows],
            [
                ("Pollo entero", "Cúcuta, Cenabastos", 5133),
                ("Rabadillas de pollo", "Cúcuta, Cenabastos", 2033),
            ],
        )

    def test_centered_wrapped_market_bottom_is_not_a_product_heading(self):
        def word(text, x, top, bold=False):
            return {
                "text": text,
                "x0": x,
                "x1": x + len(text) * 3,
                "top": top,
                "bottom": top + 8,
                "fontname": "Arial-BoldMT" if bold else "ArialMT",
                "size": 8,
            }

        headers = [
            word(text, x, 80)
            for text, x in [("Mínimo", 160), ("Máximo", 200), ("Medio", 240)]
        ]
        lines = [
            [word("Acelga", 30, 90, True)],
            [word("Medellín, Central Mayorista de", 30, 100)],
            [
                word("100", 160, 105.71),
                word("200", 200, 105.71),
                word("150", 240, 105.71),
            ],
            [word("Antioquia", 30, 111.40)],
            [
                word("Armenia, Mercar", 30, 123),
                word("200", 160, 123),
                word("300", 200, 123),
                word("250", 240, 123),
            ],
        ]
        rows = weekly._native_column(
            lines,
            headers,
            "Verduras",
            (date(2012, 6, 16), date(2012, 6, 22)),
            1,
            1,
            1,
            {},
        )
        self.assertEqual([r["product_name"] for r in rows], ["Acelga", "Acelga"])
        self.assertEqual(rows[0]["market"], "Medellín, Central Mayorista de Antioquia")

    @unittest.skipUnless(
        Path(
            "artifacts/automation-audit-2026-09-26/weekly-assessment/bol-SIPSASemanal-19sep25sep-2026.pdf"
        ).exists(),
        "retained real originals are optional local fixtures",
    )
    def test_real_current_pdf_all_keys_and_numbers_match_independent_literal_snapshot(
        self,
    ):
        import json

        root = Path("artifacts/automation-audit-2026-09-26/weekly-assessment")
        rows = weekly.parse_pdf(
            (root / "bol-SIPSASemanal-19sep25sep-2026.pdf").read_bytes(),
            "bol-SIPSASemanal-19sep25sep-2026.pdf",
        )
        snapshot = json.loads(
            (
                root
                / "independent-snapshot-anex-SIPSASemanal-19sep25sep-2026.xlsx.rows.json"
            ).read_text()
        )

        def projection(row):
            return (row["product_name"], row["market"]), (
                row["min"],
                row["max"],
                row["price"]
                if row["price"] is not None
                else row["details"]["literal_mean"],
            )

        self.assertEqual(len(rows), 4571)
        self.assertEqual(dict(map(projection, rows)), dict(map(projection, snapshot)))
        self.assertEqual(sum(r["price"] is None for r in rows), 131)

    @unittest.skipUnless(
        Path(
            "artifacts/automation-audit-2026-09-26/weekly-assessment/Semana10nov_16nov_2012.pdf"
        ).exists(),
        "retained real originals are optional local fixtures",
    )
    def test_real_historical_unbolded_headings_and_publisher_conflicts(self):
        root = Path("artifacts/automation-audit-2026-09-26/weekly-assessment")
        rows = weekly.parse_pdf(
            (root / "Semana10nov_16nov_2012.pdf").read_bytes(),
            "Semana10nov_16nov_2012.pdf",
        )
        quote = {(r["product_name"], r["market"]): r for r in rows}
        self.assertEqual(
            quote[("Rabadillas de pollo", "Cúcuta, Cenabastos")]["price"], 2033
        )
        self.assertEqual(
            quote[("Pollo entero fresco sin vísceras", "Cúcuta, Cenabastos")]["price"],
            5133,
        )
        self.assertTrue(
            any(r["product_name"] == "Carne de cerdo en canal" for r in rows)
        )
        self.assertFalse(
            any(r["product_name"].startswith("Carne de Carne") for r in rows)
        )
        rows = weekly.parse_pdf(
            (root / "Sem_30dic_5ene_2018.pdf").read_bytes(), "Sem_30dic_5ene_2018.pdf"
        )
        self.assertTrue(any(r["product_name"] == "Zanahoria bogotana" for r in rows))
        conflicts = [
            r
            for r in rows
            if r["product_name"] == "Trucha entera fresca"
            and r["market"] == "Pasto, El Potrerillo"
        ]
        self.assertEqual(len(conflicts), 2)
        self.assertTrue(all(r["price"] is None for r in conflicts))
        self.assertEqual(
            {r["details"]["literal_mean"] for r in conflicts}, {9500, 11500}
        )

    def test_unbound_native_monetary_rows_request_page_ocr_and_unknown_ocr_columns_review(
        self,
    ):
        with self.assertRaises(weekly.NormalExtractionFailed) as caught:
            weekly.parse_pdf(native_pdf(product_font="Helvetica"), "report.pdf")
        self.assertEqual(caught.exception.required_pages, (1,))
        reading = {
            "text": "Cuadro 1. Mercados mayoristas. Precios de venta de verduras 19 al 25 de septiembre de 2026 Pesos por kilogramo",
            "tables": [[["Producto", "% cambio"], ["Acelga", "20"]]],
        }
        with self.assertRaisesRegex(ValueError, "without explicit monetary columns"):
            weekly._ocr_page(
                reading, "report.pdf", 1, {"eggs": False, "liquids": False}
            )


if __name__ == "__main__":
    unittest.main()

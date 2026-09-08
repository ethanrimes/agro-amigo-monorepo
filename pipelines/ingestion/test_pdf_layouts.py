"""Regressions for old table geometry, wrapped identities and publisher defects."""

import io
import unittest
from datetime import date

from reportlab.pdfgen import canvas

from pipelines.ingestion.pdf_sources import parse_input_pdf


def source_pdf(lines):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    for x, y, text, bold in lines:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 8)
        c.drawString(x, y, text)
    c.save()
    return buf.getvalue()


class HistoricalPDF(unittest.TestCase):
    def test_price_only_table_preserves_wrapped_numeric_product_heading(self):
        data = source_pdf(
            [
                (35, 740, "Cuadro 13. Precios de elementos pecuarios", True),
                (35, 728, "2012 (julio)", True),
                (35, 705, "Productos y mercados", False),
                (200, 705, "Precio medio", False),
                (35, 680, "Alambre de puas num. 14,", True),
                (35, 670, "rollo por 350 metros", True),
                (35, 650, "Aguachica (Cesar)", False),
                (210, 650, "141.250", False),
            ]
        )
        rows = list(parse_input_pdf(data, date(2012, 7, 31)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0][3:7],
            ("Alambre de puas num. 14", "Aguachica", "rollo por 350 metros", 141250.0),
        )
        self.assertEqual(rows[0][-1]["category"], "Elementos agropecuarios")

    def test_local_table_date_ignores_an_unrelated_chart_date(self):
        data = source_pdf(
            [
                (35, 755, "Cuadro 12. Tarifa de energia", True),
                (35, 744, "2012 (agosto)", False),
                (35, 690, "Cuadro 13. Precios de fertilizantes", True),
                (35, 678, "2012 (septiembre)", False),
                (35, 660, "Productos y mercados", False),
                (200, 660, "Precio medio", False),
                (35, 640, "Urea, 50 kilogramos", True),
                (35, 620, "Aguachica (Cesar)", False),
                (210, 620, "141.250", False),
            ]
        )
        self.assertEqual(
            list(parse_input_pdf(data, date(2012, 9, 30)))[0][2], date(2012, 9, 30)
        )

    def test_overprinted_heading_never_borrows_the_previous_product(self):
        data = source_pdf(
            [
                (35, 740, "Cuadro 2. Precios de medicamentos", True),
                (35, 728, "2012 (agosto)", False),
                (35, 705, "Productos y mercados", False),
                (200, 705, "Precio medio", False),
                (35, 680, "Alervec, 10 centimetros cubicos", True),
                (35, 660, "Cartago (Valle del Cauca)", False),
                (210, 660, "7.500", False),
                (35, 640, "Cuadro 2. Insumos pecuarios.", True),
                (35, 630, "Precios de medicamentos", True),
                (35, 610, "Aguachica (Cesar)", False),
                (210, 610, "11.650", False),
                (35, 590, "Ankofen, 10 centimetros cubicos", True),
                (35, 570, "Cartago (Valle del Cauca)", False),
                (210, 570, "12.150", False),
            ]
        )
        rows = list(parse_input_pdf(data, date(2012, 8, 31)))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][1], "dane-inputs-pdf-unresolved")
        self.assertTrue(rows[1][-1]["quality_issue"])
        self.assertEqual(rows[2][3], "Ankofen")


if __name__ == "__main__":
    unittest.main()

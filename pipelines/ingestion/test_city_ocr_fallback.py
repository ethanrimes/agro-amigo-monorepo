"""Real PDF objects: native prices, readable headings/image prices, and logos."""

import io
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import pdfplumber
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .city_reports import parse_archived_city_pdf, parse_city_pdf, publish_ocr_page
from .ocr import needs_ocr
from .pdf_sources import PDFOCRPending, parse_archived_price_pdf

HEAD = "PRECIOS DE VENTA MAYORISTA\nBarranquilla, Barranquillita\nPRODUCTOS PRIMERA CALIDAD\n07 de Septiembre de 2026"
TABLE = [
    ["Producto", "Presentación", "Unidades", "Ronda 1", "", "Ronda 2", ""],
    ["", "", "", "Mínimo", "Máximo", "Mínimo", "Máximo"],
    ["Frutas", "", "", "", "", "", ""],
    ["Cítricos", "", "", "", "", "", ""],
    ["Limón tahití", "Bulto", "24 Kilogramo", "85.000", "87.000", "0", "0"],
]
READ = {
    "text": "PRECIOS DE VENTA MAYORISTA\nContinuación",
    "tables": [TABLE],
    "review_notes": [],
}


def draw_table(c, table=TABLE):
    xs = [36, 136, 216, 306, 371, 436, 501, 576]
    top, height = 590, 38
    c.setFont("Helvetica", 9)
    for x in xs:
        c.line(x, top, x, top - height * len(table))
    for row, cells in enumerate(table):
        c.line(xs[0], top - row * height, xs[-1], top - row * height)
        for column, value in enumerate(cells):
            c.drawString(xs[column] + 3, top - row * height - 22, value)
    c.line(xs[0], top - height * len(table), xs[-1], top - height * len(table))


def mixed_city_pdf(table=TABLE, first_identity_in_image=False):
    source = io.BytesIO()
    c = canvas.Canvas(source, pagesize=(612, 792))
    draw_table(c, table)
    c.save()
    with pdfplumber.open(io.BytesIO(source.getvalue())) as pdf:
        # Actual rendered grid pixels, with no table text layer in the target.
        grid = pdf.pages[0].crop((34, 200, 578, 394)).to_image(resolution=150).original
    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=(612, 792))
    c.setFont("Helvetica", 12)
    heading = "DANE - Sistema de información SIPSA" if first_identity_in_image else HEAD
    for n, line in enumerate(heading.splitlines()):
        c.drawString(36, 760 - 18 * n, line)
    if first_identity_in_image:
        c.drawImage(ImageReader(grid), 34, 398, width=544, height=194)
    else:
        draw_table(c, table)
    c.showPage()
    c.setFont("Helvetica", 12)
    c.drawString(36, 750, "PRECIOS DE VENTA MAYORISTA - Continuación")
    c.drawImage(ImageReader(grid), 34, 398, width=544, height=194)
    c.showPage()
    c.setFont("Helvetica", 12)
    c.drawString(36, 750, "Notas de lectura - documento de prueba")
    c.drawImage(ImageReader(grid), 36, 650, width=80, height=30)
    c.save()
    return output.getvalue()


class CityOCRFallback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = mixed_city_pdf()

    def test_native_heading_is_not_a_successfully_read_price_table(self):
        with pdfplumber.open(io.BytesIO(self.data)) as pdf:
            self.assertFalse(needs_ocr(pdf.pages[1], pdf.pages[1].extract_text()))
            self.assertEqual(pdf.pages[1].extract_tables(), [])
            self.assertGreater(len(pdf.pages[1].extract_text()), 20)
        self.assertEqual(len(list(parse_city_pdf(self.data, date(2026, 9, 7)))), 1)
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        with patch("pipelines.ingestion.ocr.enqueue_image") as enqueue:
            with self.assertRaisesRegex(ValueError, r"pages \[2\] await"):
                list(
                    parse_archived_city_pdf(db, self.data, "fixture", date(2026, 9, 7))
                )
        self.assertEqual(enqueue.call_count, 1)
        self.assertEqual(enqueue.call_args.args[2], "PDF page 2")
        self.assertEqual(enqueue.call_args.args[-1], 2)

    def test_cached_agreement_keeps_both_native_and_image_rows_with_page_identity(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [(READ,), (READ,)]
        with patch("pipelines.ingestion.ocr.enqueue_image") as enqueue:
            rows = list(
                parse_archived_city_pdf(db, self.data, "fixture", date(2026, 9, 7))
            )
        enqueue.assert_not_called()
        self.assertEqual(len(rows), 2)
        self.assertEqual([row[-1] for row in rows], [1, 2])
        self.assertEqual(rows[1][1], date(2026, 9, 7))
        self.assertEqual(rows[1][4], "Barranquilla, Barranquillita")
        self.assertEqual(rows[1][5], "Frutas > Cítricos")
        self.assertEqual(rows[1][11:13], (85000, 87000))
        self.assertEqual(len({row[0] for row in rows}), 2)

    def test_disagreeing_cells_cannot_be_published(self):
        other = dict(READ, tables=[[row[:] for row in TABLE]])
        other["tables"][0][-1][3] = "86.000"
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [(READ,), (other,)]
        with patch("pipelines.ingestion.ocr.enqueue_image"):
            with self.assertRaisesRegex(ValueError, "await agreeing"):
                list(
                    parse_archived_city_pdf(db, self.data, "fixture", date(2026, 9, 7))
                )

    def test_publisher_title_alone_cannot_hide_an_image_only_first_page(self):
        data = mixed_city_pdf(first_identity_in_image=True)
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        with (
            patch("pipelines.ingestion.ocr.enqueue_image") as enqueue,
            self.assertRaisesRegex(ValueError, r"pages \[1\] await"),
        ):
            list(parse_archived_city_pdf(db, data, "fixture", date(2026, 9, 7)))
        self.assertEqual(enqueue.call_args.args[-1], 1)

    def test_city_ocr_publisher_reconstructs_document_not_isolated_continuation(self):
        db = MagicMock()
        db.execute.return_value.fetchone.side_effect = [
            (date(2026, 9, 7),),
            (self.data,),
        ]
        db.execute.return_value.fetchall.return_value = [(READ,), (READ,)]
        with patch("pipelines.ingestion.city_reports.save_classifications"):
            count = publish_ocr_page(db, "fixture", 2, READ)
        self.assertEqual(count, 2)
        rows = db.cursor.return_value.__enter__.return_value.executemany.call_args.args[
            1
        ]
        self.assertEqual([row[-1] for row in rows], [1, 2])
        self.assertTrue(all("verified image OCR" not in row[1] for row in rows))


class MatrixOCRFallback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = [
            ["Producto", "Bogotá", "Medellín", "Cali", "", "", ""],
            ["Limón tahití", "3.500", "3.600", "3.700", "", "", ""],
            ["", "", "", "", "", "", ""],
            ["", "", "", "", "", "", ""],
            ["", "", "", "", "", "", ""],
        ]
        cls.data = mixed_city_pdf(cls.table)
        cls.reading = dict(READ, tables=[cls.table])

    def test_only_matrix_page_with_failed_native_prices_is_queued(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        with patch("pipelines.ingestion.ocr.enqueue_image") as enqueue:
            with self.assertRaisesRegex(PDFOCRPending, r"pages \[2\] await"):
                list(
                    parse_archived_price_pdf(
                        db, self.data, "fixture", date(2026, 9, 7), "daily-pdf"
                    )
                )
        self.assertEqual(enqueue.call_count, 1)
        self.assertEqual(enqueue.call_args.args[-1], 2)

    def test_verified_matrix_preserves_all_market_columns_and_pages(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [
            (self.reading,),
            (self.reading,),
        ]
        rows = list(
            parse_archived_price_pdf(
                db, self.data, "fixture", date(2026, 9, 7), "monthly-pdf"
            )
        )
        self.assertEqual(len(rows), 6)
        self.assertEqual({row[1] for row in rows}, {"dane-monthly-bulletin"})
        self.assertEqual([row[6] for row in rows], [3500, 3600, 3700] * 2)
        self.assertEqual(len({row[0] for row in rows}), 6)


if __name__ == "__main__":
    unittest.main()

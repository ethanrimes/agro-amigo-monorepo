"""Literal wrapped municipality recovery and immutable publication supersession."""

import hashlib
import io
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter

from . import pdf_sources, worker
from . import test_input_pdf_publication as publication_tests
from .test_input_pdf_recovery import parse


class NativeLocationWraps(unittest.TestCase):
    def test_adjacent_nonbold_location_prefix_keeps_full_name(self):
        rows = parse(
            [
                (35, 680, "10-20-20, 50 kilogramos", True),
                (35, 664, "El Carmen", False),
                (35, 656, "de Viboral (Antioquia)", False),
                (210, 656, "92.417", False),
                (35, 644, "El Santuario (Antioquia)", False),
                (210, 644, "87.667", False),
            ]
        )
        self.assertEqual(
            [(r[4], r[6]) for r in rows],
            [("El Carmen de Viboral", 92417), ("El Santuario", 87667)],
        )
        self.assertEqual(
            rows[0][-1]["printed_location_lines"],
            ["El Carmen", "de Viboral (Antioquia)"],
        )

    def test_connector_can_be_on_first_line(self):
        rows = parse(
            [
                (35, 680, "10-20-20, 50 kilogramos", True),
                (35, 664, "San Pedro de los", False),
                (35, 656, "Milagros (Antioquia)", False),
                (210, 656, "92.417", False),
            ]
        )
        self.assertEqual(rows[0][4], "San Pedro de los Milagros")

    def test_three_adjacent_lines_retain_first_and_middle_fragments(self):
        rows = parse(
            [
                (35, 680, "Gallina/Polla, unidad", True),
                (35, 664, "Villa", False),
                (35, 656, "de San Diego", False),
                (35, 648, "de Ubaté (Cundinamarca)", False),
                (210, 648, "16.667", False),
            ]
        )
        self.assertEqual(rows[0][4], "Villa de San Diego de Ubaté")
        self.assertEqual(
            rows[0][-1]["printed_location_lines"],
            ["Villa", "de San Diego", "de Ubaté (Cundinamarca)"],
        )

    def test_nonadjacent_or_bold_heading_cannot_become_location(self):
        for bold, y in [(True, 664), (False, 680)]:
            with self.subTest(bold=bold, y=y):
                rows = parse(
                    [
                        (35, 696, "10-20-20, 50 kilogramos", True),
                        (35, y, "El Carmen", bold),
                        (35, 648, "de Viboral (Antioquia)", False),
                        (210, 648, "92.417", False),
                    ]
                )
                self.assertNotEqual(rows[0][4], "El Carmen de Viboral")

    def test_product_row_and_complete_location_never_prefix_next_market(self):
        rows = parse(
            [
                (35, 680, "10-20-20, 50 kilogramos", True),
                (35, 664, "Corinto (Cauca)", False),
                (210, 664, "100.000", False),
                (35, 656, "El Santuario (Antioquia)", False),
                (210, 656, "87.667", False),
            ]
        )
        self.assertEqual([r[4] for r in rows], ["Corinto", "El Santuario"])

    def test_retained_december_2015_page_has_literal_name_price_change_and_unit(self):
        path = Path(
            "artifacts/app-data-audit-2026-09-27/three-source-followup/de-viboral/original.pdf"
        )
        if not path.exists():
            self.skipTest("Retained authoritative original is unavailable")
        body = path.read_bytes()
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "1a7e6c1e96c4c53b731a5da10bbbc02823915dae2229e8c3695091a7a78a059b",
        )
        writer = PdfWriter()
        writer.add_page(PdfReader(io.BytesIO(body)).pages[7])
        page = io.BytesIO()
        writer.write(page)
        rows = list(pdf_sources.parse_input_pdf(page.getvalue(), date(2015, 12, 31)))
        (row,) = [
            r for r in rows if r[3] == "10-20-20" and r[4] == "El Carmen de Viboral"
        ]
        self.assertEqual(
            row[2:8],
            (
                date(2015, 12, 31),
                "10-20-20",
                "El Carmen de Viboral",
                "50 kilogramos",
                92417,
                7.3,
            ),
        )
        self.assertEqual(row[-1]["department"], "Antioquia")
        self.assertEqual(
            row[-1]["printed_location_lines"], ["El Carmen", "de Viboral (Antioquia)"]
        )
        self.assertFalse(any(r[4] == "de Viboral" for r in rows))


@unittest.skipUnless(
    os.environ.get("AGRO_INPUT_PDF_PUBLICATION_POSTGRES_TEST") == "1",
    "Explicit TEMP-only PostgreSQL opt-in",
)
class WrappedMunicipalityPublication(unittest.TestCase):
    setUp = publication_tests.InputPDFPublication.setUp

    def publish_pdf(self, version, municipality):
        meta = {
            "parser_version": version,
            "category": "Fertilizantes y enmiendas",
            "presentation": "50 kilogramos",
            "department": "Antioquia",
            "municipality": municipality,
            "brand": "",
            "ica": "",
        }
        row = worker.record(
            "dane-inputs-pdf",
            date(2015, 12, 31),
            "10-20-20",
            municipality,
            "50 kilogramos",
            92417,
            f"PDF page 8,col 1,y 605.7; {version}",
            7.3,
            meta,
        )
        with (
            patch.object(pdf_sources, "INPUT_PDF_VERSION", version),
            self.db.transaction(),
        ):
            worker.save_rows(self.db, "old", [row])
            worker.project(
                self.db, "old", "https://www.dane.gov.co/original.pdf", "inputs-pdf"
            )

    def test_corrected_identity_hides_old_projection_but_keeps_raw(self):
        self.publish_pdf("inputs-pdf-v6", "de Viboral")
        self.publish_pdf(pdf_sources.INPUT_PDF_VERSION, "El Carmen de Viboral")
        self.assertEqual(
            self.db.execute(
                "SELECT municipality,price FROM published_input_municipal_price"
            ).fetchall(),
            [("El Carmen de Viboral", 92417)],
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM input_municipal_price").fetchone()[0],
            2,
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 2
        )

    def test_newer_xls_precision_survives_corrected_pdf_replay(self):
        self.publish_pdf("inputs-pdf-v6", "de Viboral")
        self.db.execute("""INSERT INTO input_municipal_price VALUES
          ('10-20-20-50-kilogramos','Antioquia','2015-12-31','10-20-20',
           'Fertilizantes y enmiendas','50 kilogramos',92416.66666666667,
           'new','1.2!row 25836','','','','El Carmen de Viboral')""")
        self.publish_pdf(pdf_sources.INPUT_PDF_VERSION, "El Carmen de Viboral")
        rows = self.db.execute(
            "SELECT municipality,price::text,document_id,source_locator FROM published_input_municipal_price"
        ).fetchall()
        self.assertEqual(
            rows,
            [("El Carmen de Viboral", "92416.66666666667", "new", "1.2!row 25836")],
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 2
        )


if __name__ == "__main__":
    unittest.main()

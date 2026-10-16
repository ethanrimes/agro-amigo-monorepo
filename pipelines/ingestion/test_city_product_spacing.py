"""Native DANE PDFs where default table extraction joins printed product words."""

import hashlib
import io
import unittest
import zipfile
from pathlib import Path

import pdfplumber

from .city_reports import _city_tables, parse_city_pdf
from .worker import clean

FIXTURE = Path(__file__).parent / "testdata/city_joined_product_labels.zip"
UNAFFECTED = Path(__file__).parent / "testdata/city_regionales_05nov2025.zip"

# Each fixture member was copied byte-for-byte from its DANE city ZIP. The
# exact parent URL, member basename and PDF hash are audited in the test.
CASES = (
    (
        "bagre_rayado_entero.pdf",
        "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-3jul2024.zip",
        "Bogotá, D.C., Corabastos-03-07-2024.pdf",
        "bbe4cfe5d5648de5e4ba34dc0122622278fe2b6dbe2819a5bee3fbc659d24df7",
        "Bagre rayado entero congelado",
        "Bagrerayadoentero congelado",
        "Kilogramo",
    ),
    (
        "basa_entero_congelado.pdf",
        "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-17jul2024.zip",
        "Bogotá, D.C., Corabastos-17-07-2024.pdf",
        "c946c256f3514ef95106728426315f0f9db8bdef03b0ad73368c06b3d3f02b25",
        "Basa, entero congelado importado",
        "Basa,enterocongelado importado",
        "Kilogramo",
    ),
    (
        "cafe_molido.pdf",
        "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-5jul2024.zip",
        "Ibagué, Plaza La 21-05-07-2024.pdf",
        "49d2c364cd807baaea1e8c41edc8f23e93c057a049265bcb677d2a25caae4f90",
        "Café molido",
        "Cafémolido",
        "Unidad50GR",
    ),
    (
        "papa_criolla_sucia.pdf",
        "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-29jul2024.zip",
        "Cali, Cavasa-29-07-2024.pdf",
        "cc71efadfbc26dab14a6ae3e0bc6edabe9dee8ad2403bbf5ddad53e56c1335c4",
        "Papa criolla sucia",
        "Papacriollasucia",
        "Kilogramo",
    ),
    (
        "papa_parda_pastusa.pdf",
        "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-24jun2024.zip",
        "Cali, Cavasa-24-06-2024.pdf",
        "25c8bc5411c418265b881450057a2e2b5acdbf7fb5df84329e4e48c96bebd7b6",
        "Papa parda pastusa",
        "Papapardapastusa",
        "Kilogramo",
    ),
    (
        "papa_unica.pdf",
        "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-8jul2024.zip",
        "Cali, Cavasa-08-07-2024.pdf",
        "5470605c794d19761e29cef3950fc51d9565ba13dd1142ac446224c6f04162be",
        "Papa única",
        "Papaúnica",
        "Kilogramo",
    ),
    (
        "rabano_rojo.pdf",
        "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-17oct2023.zip",
        "Bogotá, D.C., Corabastos-17-10-2023.pdf",
        "02f89ca74a374ab045c92c74678096fcfe9291409a594dd24bbf12d76526f0bc",
        "Rábano rojo",
        "Rábanorojo",
        "Kilogramo",
    ),
)


class CityProductSpacing(unittest.TestCase):
    def test_original_native_pdfs_keep_printed_word_boundaries(self):
        with zipfile.ZipFile(FIXTURE) as bundle:
            for fixture_name, parent_url, original_name, sha, wanted, joined, units in CASES:
                with self.subTest(parent_url=parent_url, member=original_name):
                    body = bundle.read(fixture_name)
                    self.assertEqual(hashlib.sha256(body).hexdigest(), sha)
                    with pdfplumber.open(io.BytesIO(body)) as pdf:
                        pairs = []
                        for page in pdf.pages:
                            default = page.extract_tables()
                            corrected = _city_tables(page)
                            self.assertEqual(len(default), len(corrected))
                            for old_table, new_table in zip(default, corrected):
                                self.assertEqual(len(old_table), len(new_table))
                                for old_row, new_row in zip(old_table, new_table):
                                    self.assertEqual(old_row[1:], new_row[1:])
                                    pairs.append((clean(old_row[0]), clean(new_row[0])))
                        self.assertIn((joined, wanted), pairs)
                    parsed = list(parse_city_pdf(body))
                    matching = [row for row in parsed if row[3] == wanted]
                    self.assertTrue(matching)
                    self.assertFalse(any(row[3] == joined for row in parsed))
                    self.assertTrue(all(row[8] == units for row in matching))

    def test_unaffected_native_layout_keeps_its_rows_and_package(self):
        with zipfile.ZipFile(UNAFFECTED) as bundle:
            body = bundle.read("Ancuya (Nariño)-05-11-2025.pdf")
        rows = list(parse_city_pdf(body))
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0][3], "Panela cuadrada morena")
        self.assertEqual(rows[0][8], "Kilogramo")


if __name__ == "__main__":
    unittest.main()

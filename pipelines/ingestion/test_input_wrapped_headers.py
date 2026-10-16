"""January 2019 literal monetary headers and captions survive native wrapping."""

import hashlib
import json
import os
import re
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pdfplumber

from . import inputs, worker
from . import pdf_sources as parser
from . import test_input_pdf_publication as publication_tests
from .worker import SourceDateMismatch, parser_version
from .input_pdf_v17_replay import VERSION as GENERIC_INPUT_VERSION

FIXTURES = Path(
    os.environ.get(
        "AGRO_INPUT_HEADER_FIXTURES",
        "artifacts/source-verification-2026-09-28/inputs-milk/residual-context",
    )
)
DID = "849ab2d0128c957fc74102367c9b4604600b027c50f419fb901d7d0cb87c08cb"


@unittest.skipUnless(
    (FIXTURES / "jan2019.pdf").exists(), "Retained January 2019 original required"
)
class ActualWrappedInputHeaders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = (FIXTURES / "jan2019.pdf").read_bytes()
        assert hashlib.sha256(cls.data).hexdigest() == DID
        cls.rows = list(parser.parse_input_pdf(cls.data, date(2019, 1, 31)))

    def page_rows(self, page_no, transform=None):
        with pdfplumber.open(FIXTURES / "jan2019.pdf") as pdf:
            page = pdf.pages[page_no - 1]
            words = page.extract_words(extra_attrs=["fontname"])
            wrapper = MagicMock()
            wrapper.__enter__.return_value.pages = [page]
            with (
                patch.object(pdfplumber, "open", return_value=wrapper),
                patch.object(
                    page,
                    "extract_words",
                    return_value=transform(words) if transform else words,
                ),
            ):
                return list(parser.parse_input_pdf(b"", date(2019, 1, 31)))

    def test_full_document_independent_literal_price_and_variation_cells(self):
        self.assertEqual(parser.INPUT_PDF_VERSION, "inputs-pdf-v14")
        self.assertEqual(parser_version("inputs-pdf"), GENERIC_INPUT_VERSION)
        self.assertEqual(inputs.input_pdf_version_for_document(DID), GENERIC_INPUT_VERSION)
        self.assertEqual(len(self.rows), 14458)
        printed = Counter()
        pattern = re.compile(
            r"(?<!\S)(\d[\d.,]*)(?: {2,})(n\.?\s*d\.|[-+]?\d[\d.,]*)(?=\s{2,}|$)",
            re.IGNORECASE,
        )
        for page, text in enumerate(
            (FIXTURES / "jan2019.txt").read_text().split("\f"), 1
        ):
            if not all(token in text for token in ("mercados", "Precio", "medio")):
                continue
            for line in text.splitlines():
                for match in pattern.finditer(line):
                    price = float(match[1].replace(".", "").replace(",", "."))
                    change = (
                        None
                        if match[2].lower().startswith("n")
                        else float(match[2].replace(".", "").replace(",", "."))
                    )
                    if price > 0:
                        printed[page, price, change] += 1
        self.assertEqual(
            Counter((r[-1]["page"], r[6], r[7]) for r in self.rows), printed
        )
        self.assertTrue(
            all(
                r[2] == date(2019, 1, 31)
                and r[3]
                and r[4]
                and r[5]
                for r in self.rows
            )
        )

    def test_ten_independently_viewed_identity_unit_and_price_anchors(self):
        anchors = json.loads((FIXTURES / "root-visual-oracles.json").read_text())[
            "rows"
        ]
        self.assertEqual(len(anchors), 10)
        for anchor in anchors:
            with self.subTest(anchor=anchor):
                got = [
                    r
                    for r in self.rows
                    if r[-1]["page"] == anchor["page"]
                    and r[3] == anchor["product_name"]
                    and r[4] == anchor["municipality"]
                    and r[5] == anchor["presentation"]
                ]
                self.assertEqual(len(got), 1)
                self.assertEqual(
                    (got[0][6], got[0][7], got[0][-1]["department"]),
                    (anchor["price"], anchor["change_percent"], anchor["department"]),
                )

    def test_explicit_month_before_year_caption_has_no_inferred_period(self):
        rows = self.page_rows(56)
        self.assertGreater(len(rows), 40)
        self.assertTrue(all(r[2] == date(2019, 1, 31) for r in rows))
        with self.assertRaises(SourceDateMismatch):
            self.page_rows(
                56,
                lambda ws: [
                    {**w, "text": w["text"].replace("2019)", "2018)")} for w in ws
                ],
            )

    def test_unrelated_mean_word_cannot_unlock_a_price_header(self):
        self.assertEqual(
            self.page_rows(
                8,
                lambda ws: [
                    {**w, "x0": 5, "x1": 20} if w["text"] == "medio" else w for w in ws
                ],
            ),
            [],
        )

    def test_recognized_monetary_table_never_silently_completes_empty(self):
        with self.assertRaisesRegex(ValueError, "no verified rows"):
            self.page_rows(8, lambda ws: [w for w in ws if w["top"] < 310])

    def test_original_rule_spacing_preserves_wrapped_municipal_identity(self):
        rows = self.page_rows(60)
        exact = [
            r
            for r in rows
            if r[3] == "Butazinol NF" and r[4] == "Villa de San Diego de Ubaté"
        ]
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0][5:8], ("50 centímetros cúbicos", 40250, -4.5))


@unittest.skipUnless(
    os.environ.get("AGRO_INPUT_PDF_PUBLICATION_POSTGRES_TEST") == "1"
    and (FIXTURES / "jan2019.pdf").exists(),
    "Actual original and isolated TEMP PostgreSQL opt-in required",
)
class WrappedInputPublication(unittest.TestCase):
    setUp = publication_tests.InputPDFPublication.setUp

    def test_two_actual_wrapped_tables_publish_exact_original_rows_idempotently(self):
        rows = []
        with pdfplumber.open(FIXTURES / "jan2019.pdf") as pdf:
            wrapper = MagicMock()
            wrapper.__enter__.return_value.pages = [pdf.pages[7], pdf.pages[55]]
            with patch.object(pdfplumber, "open", return_value=wrapper):
                parsed = list(parser.parse_input_pdf(b"", date(2019, 1, 31)))
        for product, town, price in [
            ("Cerdas gestación Naranja", "Neiva", 54300),
            ("Estro-Zoo", "Pasto", 25160),
        ]:
            exact = [r for r in parsed if r[3] == product and r[4] == town]
            self.assertEqual(len(exact), 1)
            self.assertEqual(exact[0][6], price)
            rows.extend(exact)
        for _ in range(2):
            with publication_tests.synthetic_pdf_publication_version(parser.INPUT_PDF_VERSION), self.db.transaction():
                worker.save_rows(self.db, "old", rows)
                inputs.project_pdf_inputs(self.db, "old")
        actual = self.db.execute(
            "SELECT name,municipality,presentation,price,observed_on,document_id,source_locator FROM published_input_municipal_price ORDER BY name"
        ).fetchall()
        self.assertEqual(len(actual), 2)
        for got, row in zip(actual, sorted(rows, key=lambda r: r[3])):
            self.assertEqual(
                got, (row[3], row[4], row[5], row[6], date(2019, 1, 31), "old", row[0])
            )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 2
        )
        self.assertEqual(
            self.db.execute(
                "SELECT processor_version,records FROM ingestion_checkpoint WHERE step='inputs-pdf:published'"
            ).fetchone(),
            (parser.INPUT_PDF_VERSION, 2),
        )

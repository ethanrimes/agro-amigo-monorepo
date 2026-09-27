"""Readable daily prose is retained as narrative, never mistaken for an OCR job.

These actual originals have unavailable Excel companions but no PDF matrix.
Their price mentions require a separately verified narrative parser; a zero-grid
result is not evidence that all prices were ingested.
"""

import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pdfplumber

from pipelines.ingestion.pdf_sources import (
    native_price_page_failure,
    parse_archived_price_pdf,
)

FIXTURES = Path(
    os.environ.get(
        "AGRO_DAILY_PDF_FIXTURES",
        Path(__file__).resolve().parents[2]
        / "artifacts/extraction-robustness-2026-09-27/daily",
    )
)
CASES = [
    ("mayoristas_abril_18_2013.pdf", date(2013, 4, 18), 4, "$1.417"),
    ("mayoristas_agosto_11_2014.pdf", date(2014, 8, 11), 3, "$1.367"),
    ("mayoristas_agosto_8_2014.pdf", date(2014, 8, 8), 3, "$1.040"),
    ("mayoristas_oct_23_2012.pdf", date(2012, 10, 23), 3, "$2.557"),
]


class NoDatabase:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("Readable native narrative must not access OCR storage")


class ActualDailyNarrative(unittest.TestCase):
    @unittest.skipUnless(
        all((FIXTURES / c[0]).exists() for c in CASES),
        "real daily PDF fixtures unavailable",
    )
    def test_readable_narrative_preserves_zero_grid_diagnostic_without_ocr(self):
        for filename, day, page_count, printed_price in CASES:
            with self.subTest(filename=filename):
                body = (FIXTURES / filename).read_bytes()
                with pdfplumber.open(FIXTURES / filename) as pdf:
                    self.assertEqual(len(pdf.pages), page_count)
                    self.assertIn(printed_price, pdf.pages[0].extract_text())
                    for page in pdf.pages:
                        text = page.extract_text() or ""
                        self.assertGreater(len(text), 500)
                        self.assertEqual(page.extract_tables(), [])
                        self.assertFalse(
                            native_price_page_failure(page, text, [], False)
                        )
                with patch(
                    "pipelines.ingestion.pdf_sources.verified_page",
                    side_effect=AssertionError("Native prose must not be sent for OCR"),
                ) as ocr:
                    with self.assertRaisesRegex(
                        ValueError, "No supported price grids found in PDF"
                    ):
                        list(
                            parse_archived_price_pdf(
                                NoDatabase(),
                                body,
                                "local-fixture-only",
                                day,
                                "daily-pdf",
                            )
                        )
                    ocr.assert_not_called()


if __name__ == "__main__":
    unittest.main()

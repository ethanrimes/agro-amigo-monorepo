"""Exact retained DANE monthly pages must retire only proven decorative OCR work."""

import hashlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import pdfplumber

from . import pdf_sources

FIXTURES = (
    Path(__file__).resolve().parent
    / "testdata/monthly_decorative"
)
ORIGINALS = {
    "cp_mensual_dic_2014.pdf": (
        "e54423fc627fbbbeede4000c0a501ffaa5b3d1dd202532f6b0821c9622588277",
        (4, 5),  # Press-release stationery, without price cells.
    ),
    "pres_mensual_mar_2016.pdf": (
        "c629fc0064261be74fa79e03cbd7e496fe27d50f147ed2530a823d2a0b979a75",
        (4,),  # Vegetables section title.
    ),
    "pres_mensual_ene_2016.pdf": (
        "287a2b0fdbec72932334bb000366c14768bb42d2e5f23e2bad4cd45cbb13128a",
        (39, 48),  # Twelve-month-change and IPC/IPP section titles.
    ),
    "pres_mensual_sep_2017.pdf": (
        "0ac6bc14a62054bb84a6afa8e0dce19810674583a46577008c790a041b2ff9cc",
        (24,),  # Institutional/social closing slide.
    ),
}


class _ChangedStream:
    def get_data(self):
        return b"unknown new body raster with numeric price grid"


class _PageWithChangedImage:
    def __init__(self, page):
        self.height = page.height
        self.width = page.width
        self.page_number = page.page_number
        self.pdf = page.pdf
        self.images = [dict(image) for image in page.images]
        # Keep size and placement; only the exact embedded-image bytes change.
        self.images[0]["stream"] = _ChangedStream()


class MonthlyPDFDecorationTests(unittest.TestCase):
    def test_guard_hashes_are_exactly_the_human_reviewed_image_streams(self):
        manifest = json.loads(
            (
                FIXTURES
                / "verified-source-pages-55.json"
            ).read_text()
        )
        self.assertEqual(len(manifest["pages"]), 55)
        daily_original = (
            Path(__file__).resolve().parent
            / "testdata/dane_daily_2019_02_18_decorative_covers_original.pdf"
        )
        self.assertEqual(
            hashlib.sha256(daily_original.read_bytes()).hexdigest(),
            "4e0ddac5f22c1c852be933d1056a66c45b67a63886aab9a2cbd7fba688a1b3ac",
        )
        with pdfplumber.open(daily_original) as pdf:
            daily_image_hashes = {
                hashlib.sha256(pdf.pages[number - 1].images[0]["stream"].get_data()).hexdigest()
                for number in (4, 5)
            }
        self.assertEqual(daily_image_hashes, {
            "5863f18041a7eed718cef551a819f2bf50ecdc08c69726681dea44ee896da3ce",
            "8b10815133e6a3c2e1f46cd25e327fc2ec5e99afaa61e7bc92a2c8a8e2d2ef56",
        })
        self.assertEqual(
            pdf_sources.VERIFIED_DECORATIVE_IMAGE_SHA256,
            frozenset(daily_image_hashes) | frozenset(
                digest for page in manifest["pages"]
                for digest in page["image_stream_sha256"]
            ),
        )

    def original(self, filename):
        expected, _ = ORIGINALS[filename]
        body = (FIXTURES / filename).read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), expected)
        return body

    def test_exact_originals_cover_all_five_verified_decorative_layouts(self):
        for filename, (_, pages) in ORIGINALS.items():
            body = self.original(filename)
            with pdfplumber.open(io.BytesIO(body)) as pdf:
                for number in pages:
                    with self.subTest(original=filename, page=number):
                        page = pdf.pages[number - 1]
                        text = page.extract_text() or ""
                        self.assertTrue(page.images)
                        self.assertTrue(
                            pdf_sources._verified_decorative_page(page, text)
                        )
                        with patch(
                            "pipelines.ingestion.ocr.needs_ocr", return_value=True
                        ) as provider_eligibility:
                            self.assertFalse(
                                pdf_sources.native_price_page_failure(page, text, [])
                            )
                            provider_eligibility.assert_not_called()

    def test_unknown_image_same_geometry_remains_ocr_eligible(self):
        body = self.original("pres_mensual_sep_2017.pdf")
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            original = pdf.pages[23]
            changed = _PageWithChangedImage(original)
            text = original.extract_text() or ""
            self.assertFalse(pdf_sources._verified_decorative_page(changed, text))
            with patch(
                "pipelines.ingestion.ocr.needs_ocr", return_value=True
            ) as provider_eligibility:
                self.assertTrue(
                    pdf_sources.native_price_page_failure(changed, text, [])
                )
                provider_eligibility.assert_called_once()

    def test_numeric_or_corrupt_text_on_same_original_stays_ocr_eligible(self):
        body = self.original("pres_mensual_mar_2016.pdf")
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            page = pdf.pages[3]
            for text in (
                "Verduras y hortalizas\nBogotá Corabastos $12.345/kg",
                "Verduras y hortalizas (cid:123)",
            ):
                with self.subTest(text=text):
                    self.assertFalse(
                        pdf_sources._verified_decorative_page(page, text)
                    )
                    with patch(
                        "pipelines.ingestion.ocr.needs_ocr", return_value=True
                    ) as provider_eligibility:
                        self.assertTrue(
                            pdf_sources.native_price_page_failure(page, text, [])
                        )
                        provider_eligibility.assert_called_once()


if __name__ == "__main__":
    unittest.main()

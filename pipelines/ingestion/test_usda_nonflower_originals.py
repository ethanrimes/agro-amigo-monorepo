"""Archived USDA TXT links that point to non-flower report families."""

import hashlib
import unittest
from pathlib import Path

from . import international_sources


ORIGINALS = Path(__file__).parent / "testdata"
CASES = (
    ("01bb3c3a91f8-MH_FV221.TXT", "Miami", "MH_FV121", "VEGETABLES"),
    ("2ceefc47f7ac-BH_FV201.TXT", "Boston", "BH_FV030", "ONIONS AND POTATOES"),
    ("5a304a4be2c4-MH_FV221.TXT", "Miami", "MH_FV156", "MISC TROPICAL FRUIT AND VEG"),
    ("b17d89f49a7e-MH_FV221.TXT", "Miami", "MH_FV185", "TRUCK, AIR, BOAT AND IMPORT SHIPMENTS"),
    ("c49f43ee8fd6d91b86bad3acb382814762f07410060d6e35e02073745c76baeb-MH_FV221.TXT", "Miami", "MH_FV111", "PINEAPPLES"),
    ("92e10731554bdff477913b2e961ca3237d1fda2f1e4b54f87117d93bd01e2727-MH_FV221.TXT", "Miami", "MH_FV280", "IMPORTS THROUGH MIAMI AIRPORT"),
)


class NonflowerArchivedOriginalTests(unittest.TestCase):
    def test_exact_nonflower_originals_stay_explicit_no_price_reviews(self):
        for filename, market, code, commodity in CASES:
            with self.subTest(filename=filename):
                body = (ORIGINALS / filename).read_bytes()
                self.assertIn(
                    hashlib.sha256(body).hexdigest(),
                    international_sources._NONFLOWER_TEXT_ORIGINALS,
                )
                rows = international_sources.parse_text_flowers(
                    body, "https://example.test/" + filename, market
                )
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertIsNone(row["price"])
                self.assertNotIn("date", row)
                self.assertEqual(row["details"]["native_report_code"], code)
                self.assertEqual(row["details"]["printed_commodity"], commodity)
                self.assertTrue(row["details"]["printed_unit_evidence"])
                self.assertIn("not flower prices", row["details"]["quality_issue"])
                if code == "MH_FV280":
                    self.assertEqual(hashlib.sha256(body).hexdigest(), filename.split("-")[0])
                    self.assertIn("DOMESTIC SHIPMENTS AND IMPORTS OF ORNAMENTAL CROPS", body.decode("cp1252"))
                    self.assertEqual(row["details"]["printed_header"],
                                     "REPORTING OFFICE:  MIAMI   AUG 23 2021")
                    self.assertEqual(row["details"]["printed_unit_evidence"],
                                     "STEM COUNT, UNLESS OTHERWISE DESIGNATED.")
                if code == "MH_FV111":
                    self.assertEqual(hashlib.sha256(body).hexdigest(), filename.split("-")[0])
                    self.assertEqual(row["details"]["printed_header"],
                                     "MIAMI Shipping Point Prices as of 06-JAN-2022")
                    self.assertIn("30-35 lb cartons Tainung 9s 23.00-25.00",
                                  row["details"]["printed_unit_evidence"])

    def test_changed_original_does_not_inherit_the_terminal_exception(self):
        body = (ORIGINALS / CASES[0][0]).read_bytes()
        changed = body.replace(b"MH_FV121", b"MH_FV221", 1)
        with self.assertRaisesRegex(ValueError, "Unexpected USDA native text report header"):
            international_sources.parse_text_flowers(
                changed, "https://example.test/MH_FV221.TXT", "Miami"
            )


if __name__ == "__main__":
    unittest.main()

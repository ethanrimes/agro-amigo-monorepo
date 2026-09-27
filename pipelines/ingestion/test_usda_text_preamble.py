"""Blank archive preambles must not change quote semantics or source lines."""

import hashlib
import unittest
from datetime import date
from pathlib import Path

from .international_sources import parse_text_flowers

REPORT = (
    b"BOSTON Ornamental Terminal Prices as of 28-MAR-2023\r\n"
    b"Provided by: Specialty Crops Market News, USDA.\r\n"
    b"BH FV 201\r\n"
    b"---ALSTROEMERIA: MARKET STEADY. bunched 10s CB Assorted Colors long "
    b"8.50-10.00 mostly 8.50\r\n"
)


class TextPreamble(unittest.TestCase):
    def test_blank_lines_recover_native_header_but_keep_original_line_numbers(self):
        for preamble, extra_lines in ((b"\r\n", 1), (b" \r\n\t\n\n", 3)):
            with self.subTest(preamble=preamble):
                row = parse_text_flowers(preamble + REPORT, "official.txt", "Boston")[0]
                self.assertEqual(row["date"], date(2023, 3, 28))
                self.assertEqual(
                    (row["min"], row["max"], row["price"]), (8.5, 10, 9.25)
                )
                self.assertEqual(row["unit"], "bunched 10s")
                self.assertEqual(row["details"]["line_start"], 4 + extra_lines)
                self.assertIn(f"Text lines {4 + extra_lines}-", row["source_locator"])

    def test_nonempty_unexpected_preamble_is_still_rejected(self):
        with self.assertRaisesRegex(
            ValueError, "Unexpected USDA native text report header"
        ):
            parse_text_flowers(b"Wrong report / unavailable\n" + REPORT, "x", "Boston")

    def test_blank_only_document_and_wrong_market_are_rejected(self):
        for data, market in ((b"\n \r\n", "Boston"), (b"\n" + REPORT, "Miami")):
            with self.subTest(market=market), self.assertRaises(ValueError):
                parse_text_flowers(data, "x", market)

    def test_actual_original_has_exact_anchor_and_retains_uncertain_identities(self):
        original = (
            Path(__file__).resolve().parents[2]
            / "artifacts/source-ambiguity-2026-09-27/usda/source.txt"
        )
        if not original.exists():
            self.skipTest("Official source audit fixture is local")
        body = original.read_bytes()
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "3aad53490b84d1a7c662b3b792bab5af77b20dc85baa73ebb70305b176b6b9f9",
        )
        rows = parse_text_flowers(body, "official.txt", "Boston")
        self.assertEqual(len(rows), 159)
        self.assertEqual(
            sum(
                r["price"] is not None and not r["details"].get("quality_issue")
                for r in rows
            ),
            124,
        )
        self.assertEqual(
            rows[0]["source_locator"],
            "Text lines 16-17, commodity ALSTROEMERIA, quote 1",
        )
        self.assertEqual(
            (rows[0]["min"], rows[0]["max"], rows[0]["price"]), (8.5, 10, 9.25)
        )
        self.assertEqual(rows[0]["details"]["mostly_min"], 8.5)

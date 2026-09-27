"""Native source defects must not discard valid neighboring USDA observations."""

import re
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from . import international_sources as src

FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "artifacts/automation-audit-2026-09-26/international"
)
CASES = [
    ("failed-02.pdf", "boston", 1, 0, 0),
    ("historical-4af6bea32800ca79.pdf", "boston", 82, 80, 126),
    ("historical-1160497e206032bd.pdf", "boston", 1, 0, 0),
    ("all-12aa1274f02fe1e8.pdf", "boston", 69, 68, 110),
    ("failed-08.pdf", "miami", 58, 57, 110),
    ("historical-cb7c8e95ebdb4bfe.pdf", "miami", 93, 83, 186),
    ("historical-e6de2b1bd1b386c0.pdf", "miami", 53, 52, 104),
    ("historical-6587fc95e8cfeddb.pdf", "miami", 59, 58, 114),
    ("historical-5b1ffe818dfbe6c7.pdf", "miami", 93, 87, 186),
    ("historical-d5b9f164da92c284.pdf", "miami", 96, 90, 192),
    ("historical-e0c8fb6996154026.pdf", "miami", 84, 74, 168),
    ("historical-10be8415535871d2.pdf", "miami", 100, 83, 200),
    ("historical-7f47641b910a1e83.pdf", "miami", 71, 70, 138),
    ("historical-9a5988ffce6e4d47.pdf", "miami", 60, 60, 68),
    ("all-656fd0476dc68e8c.pdf", "miami", 65, 65, 98),
    ("historical-e13ac42a170cc0f7.pdf", "miami", 70, 67, 135),
    ("historical-4b27197d14a19500.pdf", "miami", 70, 69, 140),
]


class NativeSourceIsolation(unittest.TestCase):
    def parse_lines(self, lines, market="miami"):
        with patch.object(
            src,
            "_pdf_parts",
            return_value=(date(2025, 9, 15), [(t, 1, 1) for t in lines]),
        ):
            parser = (
                src.parse_miami_flowers
                if market == "miami"
                else src.parse_boston_flowers
            )
            return parser(b"fixture")

    def test_malformed_decimal_is_not_repaired_and_neighbors_keep_their_prices(self):
        rows = self.parse_lines(
            [
                "---CARNATIONS:",
                "Assorted Colors",
                "Fancy",
                "per stem 0.25-0.29 Novelty Fancy 0.25-.0.29 mostly 0.25-0.27 Yellow 0.30-0.35",
            ]
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual([r["price"] is None for r in rows], [False, True, False])
        self.assertEqual((rows[1]["min"], rows[1]["max"]), (None, None))
        self.assertEqual(rows[1]["details"]["literal_price_range"], "0.25-.0.29")
        self.assertEqual(rows[1]["details"]["unbound_mostly_quotes"][0]["min"], 0.25)
        self.assertEqual((rows[0]["min"], rows[2]["max"]), (0.25, 0.35))
        self.assertEqual(
            rows[2]["details"]["variety"], "Assorted Colors / Fancy; Yellow"
        )

    def test_wrapped_exceptional_notice_preserves_malformed_original(self):
        rows = self.parse_lines(
            [
                "---CARNATIONS:",
                "Fancy",
                "per stem 0.25-.0.29 mostly 0.25-0.27 occasional",
                "higher",
                "---ASTER:",
                "Purple",
                "per bunch 2.00",
            ]
        )
        self.assertIsNone(rows[0]["price"])
        self.assertIn("occasional\nhigher", rows[0]["details"]["original_quote"])
        self.assertEqual(rows[1]["price"], 2)

    def test_explicit_nonprice_notices_do_not_consume_following_variety(self):
        for notice in ["Supplies sufficient to quote.", "pink, no offerings."]:
            with self.subTest(notice=notice):
                rows = self.parse_lines(
                    [
                        "---CHRYSANTHEMUM:",
                        "Yellow",
                        "bunched 10s 4.55 " + notice,
                        "White",
                        "bunched 10s 5.00",
                    ]
                )
                self.assertEqual([r["price"] for r in rows], [4.55, 5])
                self.assertEqual(rows[0]["details"]["variety"], "Yellow")
                self.assertIn(notice, rows[0]["details"]["original_quote"])
                self.assertEqual(rows[1]["details"]["variety"], "White")

    def test_missing_package_never_inherits_later_printed_unit(self):
        rows = self.parse_lines(
            [
                "---PAEONIA: MARKET STEADY. NETHERLANDS long 3.50-4.00 OREGON long 30.00 per stem TEXAS long 3.50",
            ],
            "boston",
        )
        self.assertEqual([r["price"] for r in rows], [None, None, 3.5])
        self.assertEqual(
            [r["unit"] for r in rows],
            ["unspecified package", "unspecified package", "per stem"],
        )
        self.assertEqual([(r["min"], r["max"]) for r in rows[:2]], [(3.5, 4), (30, 30)])

    def test_conflicting_miami_occurrences_all_review_but_identical_repeats_survive(
        self,
    ):
        rows = self.parse_lines(
            [
                "---ASTER:",
                "Purple",
                "per bunch 2.00",
                "per bunch 3.00",
                "per bunch 2.00",
                "---CARNATIONS:",
                "Red",
                "per stem 1.00",
                "per stem 1.00",
            ]
        )
        self.assertEqual([r["price"] for r in rows], [None, None, None, 1, 1])
        self.assertTrue(
            all(len(r["details"]["ambiguous_identity_quotes"]) == 3 for r in rows[:3])
        )
        self.assertEqual(len({r["source_locator"] for r in rows}), 5)

    def test_boilerplate_over_an_image_is_not_classified_as_no_price(self):
        text = "WHOLESALE MARKET PRICES: Prices quoted cover sales by primary receivers of overall supplies on wholesale lots and are on stock of generally good merchantable quality and condition unless otherwise stated"
        fake_pdf = MagicMock()
        fake_pdf.__enter__.return_value.pages = [
            SimpleNamespace(height=792, images=[{"top": 200, "bottom": 600}], curves=[])
        ]
        with (
            patch("pdfplumber.open", return_value=fake_pdf),
            self.assertRaisesRegex(ValueError, "No Boston flower prices"),
        ):
            self.parse_lines([text], "boston")


class SeventeenOriginals(unittest.TestCase):
    @unittest.skipUnless(
        (FIXTURES / "failed-02.pdf").exists(),
        "Cached source audit originals unavailable",
    )
    def test_exact_counts_and_every_literal_range_in_all_seventeen_originals(self):
        # Geometry is unchanged. Independently inventory literal tokens without
        # using either runtime matcher, counting malformed tokens as opaque text.
        token = re.compile(
            r"(?P<bad>\d*\.\d{1,2}-\s*\.\d+\.\d{1,2})|(?<![\d.])(?P<lo>\d*\.\d{1,2})(?:\s*-\s*(?P<hi>\d*\.\d{1,2}))?(?!\d|\.\d)"
        )
        for name, market, count, valid, literal_count in CASES:
            with self.subTest(source=name):
                body = (FIXTURES / name).read_bytes()
                rows = src.parse(body, name, f"international-usda-{market}-flowers")
                self.assertEqual(
                    (len(rows), sum(r["price"] is not None for r in rows)),
                    (count, valid),
                )
                self.assertEqual(len({r["source_locator"] for r in rows}), len(rows))
                _, lines = src._pdf_parts(
                    body,
                    "MH_FV221" if market == "miami" else "BH_FV201",
                    2 if market == "miami" else 1,
                )
                native = Counter(
                    ("literal", m["bad"])
                    if m["bad"]
                    else (float(m["lo"]), float(m["hi"] or m["lo"]))
                    for m in token.finditer(" ".join(x[0] for x in lines))
                )
                kept = Counter()
                for row in rows:
                    d = row["details"]
                    self.assertEqual(row["price"] is None, bool(d.get("quality_issue")))
                    if row["min"] is not None:
                        kept[(row["min"], row["max"])] += 1
                    if "literal_price_range" in d:
                        self.assertIsNone(row["price"])
                        self.assertIsNone(row["min"])
                        kept[("literal", d["literal_price_range"])] += 1
                    if "mostly_min" in d:
                        kept[(d["mostly_min"], d["mostly_max"])] += 1
                    for key in [
                        "exceptional_prices",
                        "out_of_range_mostly_quotes",
                        "conflicting_mostly_quotes",
                        "unbound_mostly_quotes",
                    ]:
                        for q in d.get(key, []):
                            kept[(q["min"], q["max"])] += 1
                            kept.update(
                                (m["min"], m["max"]) for m in q.get("mostly_quotes", [])
                            )
                self.assertEqual(sum(native.values()), literal_count)
                self.assertEqual(kept, native)
                if valid == 0:
                    self.assertEqual(
                        rows[0]["details"]["review_type"], "no-price-report"
                    )


if __name__ == "__main__":
    unittest.main()

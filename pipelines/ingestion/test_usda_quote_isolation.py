"""Keep auditable USDA contradictions local to their literal quote identity."""

import hashlib
import re
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pdfplumber

from . import international_sources as src

FIXTURES = (
    Path(__file__).resolve().parents[2] / "artifacts/source-ambiguity-2026-09-27/usda"
)
ORIGINALS = {
    "boston-header.txt": "1df030ec957e9c31ff7ed011b8dd6cd3cda9c56387dfa7943bce926ae86b9a53",
    "boston-duplicate.pdf": "6b0161a94051b147ba0362ba9010bc629b81e96ef44cd9f71768fd098da72020",
    "miami-mostly.pdf": "d493eb464e68742e1b84095f710dd5ee1ea2995088483b32b06c2b1313a3d4cb",
}


class IsolatedQuoteReview(unittest.TestCase):
    def parse_lines(self, lines, market):
        with patch.object(
            src,
            "_pdf_parts",
            return_value=(date(2025, 3, 18), [(line, 1, 1) for line in lines]),
        ):
            parser = (
                src.parse_miami_flowers
                if market == "Miami"
                else src.parse_boston_flowers
            )
            return parser(b"fixture")

    def test_boston_all_conflicting_occurrences_review_and_other_origin_survives(self):
        rows = self.parse_lines(
            [
                (
                    "---DELPHINIUM: bunched 10s ECUADOR BELLADONNA long 16.00-18.50 "
                    "mostly 18.50 ECUADOR BELLADONNA long 18.50-25.00 mostly 18.50 "
                    "ECUADOR BELLADONNA long 16.00-18.50 "
                    "per bunch PERU HYBRID long 18.50"
                ),
            ],
            "Boston",
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual([r["price"] for r in rows], [None, None, None, 18.5])
        self.assertEqual(len({r["source_locator"] for r in rows}), 4)
        for row in rows[:3]:
            self.assertEqual(len(row["details"]["ambiguous_identity_quotes"]), 3)
            self.assertIn("Ambiguous duplicate", row["details"]["quality_issue"])
        self.assertEqual(rows[-1]["details"]["origin"], "PERU")

    def test_boston_exceptional_mostly_attaches_only_to_exceptional_range(self):
        rows = self.parse_lines(
            [
                (
                    "---ASTER: per bunch ECUADOR long 10.00-20.00 mostly 15.00 "
                    "few higher 21.00-25.00 mostly 23.00 per bunch PERU long 14.00 mostly 14.00"
                ),
            ],
            "Boston",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["price"], 15)
        self.assertEqual(rows[0]["details"]["mostly_min"], 15)
        exceptional = rows[0]["details"]["exceptional_prices"][0]
        self.assertEqual((exceptional["min"], exceptional["max"]), (21, 25))
        self.assertEqual(exceptional["mostly_quotes"][0]["min"], 23)
        self.assertEqual(rows[1]["details"]["mostly_min"], 14)
        self.assertNotIn("exceptional_prices", rows[1]["details"])

    def test_invalid_exceptional_mostly_reviews_only_parent_and_preserves_literals(
        self,
    ):
        for qualifier in ["mostly 26.00", "mostly 23.00 mostly 24.00"]:
            rows = self.parse_lines(
                [
                    (
                        "---ASTER: per bunch ECUADOR long 10.00-20.00 mostly 15.00 "
                        f"few higher 21.00-25.00 {qualifier} per bunch PERU long 14.00"
                    ),
                ],
                "Boston",
            )
            self.assertEqual([r["price"] for r in rows], [None, 14])
            exceptional = rows[0]["details"]["exceptional_prices"][0]
            self.assertEqual(
                len(exceptional["mostly_quotes"]), qualifier.count("mostly")
            )
            self.assertEqual(rows[0]["details"]["mostly_min"], 15)

    def test_invalid_mostly_is_retained_for_both_pdf_layouts(self):
        for market in ["Boston", "Miami"]:
            prefix = "ECUADOR " if market == "Boston" else ""
            for invalid in ["0.27-0.29", "0.32-0.31", "0.28-0.35"]:
                with self.subTest(market=market, invalid=invalid):
                    rows = self.parse_lines(
                        [
                            "---CARNATIONS:",
                            f"per stem {prefix}Select 0.28-0.31 mostly {invalid}",
                            "---ASTER:",
                            f"per bunch {prefix}Purple 2.00-3.00 mostly 2.50",
                        ],
                        market,
                    )
                    self.assertIsNone(rows[0]["price"])
                    self.assertEqual((rows[0]["min"], rows[0]["max"]), (0.28, 0.31))
                    self.assertEqual(
                        (
                            rows[0]["details"]["out_of_range_mostly_quotes"][0]["min"],
                            rows[0]["details"]["out_of_range_mostly_quotes"][0]["max"],
                        ),
                        tuple(float(v) for v in invalid.split("-")),
                    )
                    self.assertEqual(rows[1]["price"], 2.5)
                    self.assertEqual(rows[1]["details"]["mostly_min"], 2.5)

    def test_later_valid_mostly_does_not_clear_previous_review(self):
        rows = self.parse_lines(
            [
                "---CARNATIONS:",
                "per stem Select 0.28-0.31 mostly 0.27-0.29 mostly 0.29-0.30",
            ],
            "Miami",
        )
        self.assertIsNone(rows[0]["price"])
        self.assertIn("quality_issue", rows[0]["details"])
        self.assertEqual(rows[0]["details"]["mostly_min"], 0.29)
        self.assertEqual(len(rows[0]["details"]["out_of_range_mostly_quotes"]), 1)


class ActualReportRegressions(unittest.TestCase):
    def original(self, name):
        path = FIXTURES / name
        if not path.exists():
            self.skipTest("Downloaded official USDA audit original unavailable")
        body = path.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), ORIGINALS[name])
        return body

    def test_march_2023_blank_preamble_keeps_native_line_provenance(self):
        rows = src.parse_text_flowers(
            self.original("boston-header.txt"), "official.txt", "Boston"
        )
        self.assertEqual(
            (len(rows), sum(r["price"] is not None for r in rows)), (163, 127)
        )
        self.assertEqual({r["date"] for r in rows}, {date(2023, 3, 21)})
        self.assertEqual(
            (rows[0]["min"], rows[0]["max"], rows[0]["unit"]), (25, 25, "per bunch")
        )
        self.assertEqual(
            rows[0]["source_locator"],
            "Text lines 16-17, commodity ACACIA (MIMOSA), quote 1",
        )
        self.assertEqual(
            (rows[1]["min"], rows[1]["max"], rows[1]["details"]["mostly_min"]),
            (14, 15, 15),
        )

    def test_boston_exact_exceptional_values_and_valid_neighbor(self):
        rows = src.parse_boston_flowers(self.original("boston-duplicate.pdf"))
        self.assertEqual(len(rows), 39)
        review = [r for r in rows if r["price"] is None]
        self.assertEqual(len(review), 0)
        self.assertEqual({r["date"] for r in rows}, {date(2025, 3, 18)})
        row = next(
            r
            for r in rows
            if r["product_id"]
            == "usda-flower-delphinium-belladonna-long-bunched-10s-ecuador"
        )
        self.assertEqual((row["min"], row["max"], row["price"]), (16, 18.5, 17.25))
        self.assertEqual(row["details"]["mostly_min"], 18.5)
        self.assertEqual(
            row["details"]["exceptional_prices"],
            [
                {
                    "qualifier": "few higher",
                    "min": 18.5,
                    "max": 25,
                    "source_locator": "PDF page 1, commodity DELPHINIUM, quote 3",
                    "mostly_quotes": [
                        {
                            "min": 18.5,
                            "max": 18.5,
                            "source_locator": "PDF page 1, commodity DELPHINIUM, quote 4",
                        }
                    ],
                }
            ],
        )
        self.assertEqual(
            row["source_locator"], "PDF page 1, commodity DELPHINIUM, quote 1"
        )
        self.assertIn(
            "few higher 18.50-25.00 mostly 18.50", row["details"]["original_quote"]
        )
        peru = next(r for r in rows if r["details"]["origin"] == "PERU")
        self.assertEqual((peru["price"], peru["unit"]), (18.5, "per bunch"))

    def test_miami_exact_wrapped_literal_contradiction_does_not_change_neighbor(self):
        rows = src.parse_miami_flowers(self.original("miami-mostly.pdf"))
        self.assertEqual(len(rows), 56)
        review = [r for r in rows if r["price"] is None]
        self.assertEqual(len(review), 1)
        row = review[0]
        self.assertEqual(
            (row["min"], row["max"], row["date"]), (0.28, 0.31, date(2025, 6, 30))
        )
        self.assertEqual(
            row["source_locator"], "PDF page 1, col 1, text row 31-32, quote 3"
        )
        self.assertEqual(
            row["details"]["out_of_range_mostly_quotes"],
            [
                {
                    "min": 0.27,
                    "max": 0.29,
                    "source_locator": "PDF page 1, col 1, text row 31-32, quote 4",
                }
            ],
        )
        neighbor = next(
            r
            for r in rows
            if r["source_locator"] == "PDF page 1, col 1, text row 31-32, quote 1"
        )
        self.assertAlmostEqual(neighbor["price"], 0.285)
        self.assertEqual((neighbor["min"], neighbor["max"]), (0.27, 0.30))

    def test_all_literal_ranges_are_preserved_in_prices_or_review(self):
        # Independent range inventory over native PDF text, including the
        # malformed qualifier. No parser price token matcher is reused here.
        number = re.compile(
            r"(?<![\d.])(\d*\.\d{1,2})(?:\s*-\s*(\d*\.\d{1,2}))?(?!\d|\.\d)"
        )
        for name, columns, parser, count in [
            ("boston-duplicate.pdf", 1, src.parse_boston_flowers, 67),
            ("miami-mostly.pdf", 2, src.parse_miami_flowers, 107),
        ]:
            with self.subTest(name=name):
                self.original(name)
                sections = []
                with pdfplumber.open(FIXTURES / name) as pdf:
                    for page in pdf.pages:
                        for col in range(columns):
                            sections.append(
                                page.crop(
                                    (
                                        col * page.width / columns,
                                        106,
                                        (col + 1) * page.width / columns,
                                        page.height - 95,
                                    )
                                ).extract_text()
                                or ""
                            )
                native = Counter(
                    (float(m[1]), float(m[2] or m[1]))
                    for m in number.finditer(" ".join(sections).replace("\n", " "))
                )
                rows = parser((FIXTURES / name).read_bytes())
                retained = Counter((r["min"], r["max"]) for r in rows)
                for row in rows:
                    details = row["details"]
                    if "mostly_min" in details:
                        retained[(details["mostly_min"], details["mostly_max"])] += 1
                    for key in [
                        "exceptional_prices",
                        "out_of_range_mostly_quotes",
                        "conflicting_mostly_quotes",
                    ]:
                        retained.update(
                            (q["min"], q["max"]) for q in details.get(key, [])
                        )
                    for exceptional in details.get("exceptional_prices", []):
                        retained.update(
                            (q["min"], q["max"])
                            for q in exceptional.get("mostly_quotes", [])
                        )
                self.assertEqual(sum(native.values()), count)
                self.assertEqual(retained, native)
                self.assertEqual(len({r["source_locator"] for r in rows}), len(rows))


if __name__ == "__main__":
    unittest.main()

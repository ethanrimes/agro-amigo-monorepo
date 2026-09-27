"""Identity, provenance, missing cells and layout regressions for official prices."""

import hashlib
import io
import json
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from unittest.mock import patch

import openpyxl

from . import international_sources as src

FIXTURES = Path(__file__).resolve().parents[2] / "artifacts" / "official-sources"
AUDIT_FIXTURES = FIXTURES.parent / "automation-audit-2026-09-26" / "international"


def workbook():
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Monthly Prices"
    sheet.append(["World Bank Commodity Price Data"])
    sheet.append(["monthly prices in nominal US dollars"])
    sheet.append([None, *src.WB_SERIES])
    sheet.append([None, *["($/mt)" if "oil" in k else "($/kg)" for k in src.WB_SERIES]])
    sheet.append(["1960M01", *[float(i + 1) for i in range(len(src.WB_SERIES))]])
    desc = book.create_sheet("Description")
    for _, _, prefix in src.WB_SERIES.values():
        desc.append(
            [
                None,
                prefix + " methodology and historical basis",
                "Official underlying source",
            ]
        )
    ignored = book.create_sheet("Mismatch Details")
    ignored.append(["1960M01", "Coffee, Arabica", 999999])
    return book


def encode(book):
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


class WorldBankTests(unittest.TestCase):
    def test_mutable_url_reparses_corrected_cells_and_new_months(self):
        before = workbook()
        initial = src.parse_world_bank(encode(before), src.WORLD_BANK_MONTHLY)
        before["Monthly Prices"]["C5"] = 2.75
        before["Monthly Prices"].append(["1960M02", *[3.0 for _ in src.WB_SERIES]])
        revised = src.parse_world_bank(encode(before), src.WORLD_BANK_MONTHLY)
        coffee = [r for r in revised if r["product_id"] == "wb-coffee-arabica"]
        self.assertEqual(len(revised), 90)
        self.assertEqual([r["price"] for r in coffee], [2.75, 3.0])
        self.assertEqual(coffee[0]["source_locator"], initial[1]["source_locator"])
        self.assertEqual(coffee[0]["details"]["source_url"], src.WORLD_BANK_MONTHLY)

    def test_original_units_dates_and_exact_locator(self):
        rows = src.parse(
            encode(workbook()),
            src.WORLD_BANK_MONTHLY,
            "international-worldbank-monthly",
        )
        self.assertEqual(len(rows), 45)
        coffee = next(r for r in rows if r["product_id"] == "wb-coffee-arabica")
        oil = next(r for r in rows if r["product_id"] == "wb-palm-oil")
        self.assertEqual(
            (coffee["currency"], coffee["unit"], coffee["date"]),
            ("USD", "kg", date(1960, 1, 31)),
        )
        self.assertEqual(coffee["price"], 2)
        self.assertEqual(coffee["source_locator"], "Monthly Prices!C5")
        self.assertEqual(oil["unit"], "tonne")
        self.assertEqual(oil["price"], 12)
        self.assertIn("historical basis", oil["details"]["source_description"])

    def test_missing_errors_and_zero_never_become_prices(self):
        book = workbook()
        for col, value in enumerate([None, "...", "…", "#VALUE!", 0], 2):
            book["Monthly Prices"].cell(5, col).value = value
        rows = src.parse_world_bank(encode(book), src.WORLD_BANK_MONTHLY)
        self.assertEqual(len(rows), 40)
        self.assertTrue(all(r["price"] > 0 for r in rows))

    def test_currency_unit_date_and_duplicate_changes_fail(self):
        for mutation in ("currency", "unit", "date", "duplicate", "bad_value"):
            with self.subTest(mutation=mutation):
                book = workbook()
                sheet = book["Monthly Prices"]
                if mutation == "currency":
                    sheet["A2"] = "monthly prices in euros"
                if mutation == "unit":
                    sheet["B4"] = "(2010=100)"
                if mutation == "date":
                    sheet["A5"] = "1960Q01"
                if mutation == "duplicate":
                    sheet.append([v.value for v in sheet[5]])
                if mutation == "bad_value":
                    sheet["B5"] = "about 100"
                with self.assertRaises(ValueError):
                    src.parse_world_bank(encode(book), src.WORLD_BANK_MONTHLY)

    def test_discovery_uses_only_real_trusted_links(self):
        body = b'<a href="https://evil.example/CMO-Historical-Data-Monthly.xlsx">bad</a><a href="https://thedocs.worldbank.org/new/CMO-Historical-Data-Monthly.xlsx">good</a>'
        rows = src.discover(body, src.WORLD_BANK_HOME, "international-worldbank-index")
        self.assertEqual(
            rows,
            [
                (
                    "https://thedocs.worldbank.org/new/CMO-Historical-Data-Monthly.xlsx",
                    "international-worldbank-monthly",
                )
            ],
        )
        self.assertEqual(src.discover(), src.ROOTS)


class FlowerIdentityTests(unittest.TestCase):
    def parse_lines(self, lines):
        parts = (
            date(2026, 8, 31),
            [(line, 1 if i < 6 else 2, 1) for i, line in enumerate(lines)],
        )
        with patch.object(src, "_pdf_parts", return_value=parts):
            return src.parse_miami_flowers(b"fixture")

    def test_grade_size_inline_colors_and_page_continuation(self):
        rows = self.parse_lines(
            [
                "---CARNATIONS: DEMAND MODERATE.",
                "Prices represent few spot market sales.",
                "Assorted Colors",
                "Select",
                "per stem 0.26-0.30 mostly 0.27-0.29; Novelty 0.25-0.31",
                "Fancy",
                "per stem 0.25-0.29",
                "---ROSE, HYBRID TEA: DEMAND MODERATE.",
                "Prices represent few spot market sales.",
                "Red Varieties Freedom",
                "per stem",
                "60 cm 0.52-0.60 mostly 0.55-0.60",
                "50 cm 0.43-0.54",
            ]
        )
        self.assertEqual(len(rows), 5)
        self.assertEqual(len({r["product_id"] for r in rows}), 5)
        self.assertEqual(rows[0]["details"]["mostly_min"], 0.27)
        self.assertEqual(rows[0]["price"], 0.28)
        self.assertEqual(rows[-1]["source_page"], 2)
        self.assertIn("50 cm", rows[-1]["details"]["variety"])
        self.assertTrue(
            all("country not specified" in r["details"]["origin"] for r in rows)
        )

    def test_wrapped_mostly_and_inline_color_keep_distinct_identities(self):
        rows = self.parse_lines(
            [
                "---CARNATIONS, MINIATURE:",
                "Assorted Colors",
                "per bunch 2.64-3.75 mostly 2.64-2.86; Purple 3.23-3.75 mostly",
                "3.23-3.29; Lavender",
                "2.34-2.70; Peach 2.34-2.70",
            ]
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({r["product_id"] for r in rows}), 4)
        self.assertEqual(rows[1]["details"]["variety"], "Assorted Colors; Purple")
        self.assertEqual(rows[1]["details"]["mostly_max"], 3.29)
        self.assertEqual(rows[2]["details"]["variety"], "Assorted Colors; Lavender")
        self.assertIn("text row 3-5", rows[2]["source_locator"])
        self.assertIn("Lavender\n2.34", rows[2]["details"]["original_quote"])

    def test_inline_no_market_notice_does_not_pollute_following_color(self):
        rows = self.parse_lines(
            [
                "---CARNATIONS, MINIATURE:",
                "Assorted Colors",
                "per bunch 2.64-3.75 mostly 2.64-2.86; Burgundy supplies in too few hands to",
                "establish a market; Lavender 2.91-3.75 mostly 2.91-3.44",
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["details"]["variety"], "Assorted Colors; Lavender")
        self.assertIn("Burgundy", rows[1]["details"]["original_quote"])
        self.assertTrue(all("Burgundy" not in r["product_name"] for r in rows))

    def test_explicit_unavailable_notices_and_first_report_are_not_prices(self):
        rows = self.parse_lines(
            [
                "---ROSE, SPRAY TYPE: DEMAND GOOD. FIRST REPORT on red rose spray type 50cm.",
                "Red Varieties",
                "per stem",
                "50 cm 0.78-0.80 FIRST REPORT.",
                "40 cm no offerings",
                "per stem Supplies insufficient to quote.",
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["details"]["variety"], "Red Varieties / 50 cm")

    def test_wrapped_color_cannot_cross_layout_boundary_or_lose_quote(self):
        with self.assertRaisesRegex(ValueError, "qualifier continuation"):
            self.parse_lines(
                [
                    "---ASTER:",
                    "per bunch 2.00; Purple",
                    "---CARNATIONS:",
                    "per stem 1.00",
                ]
            )

    def test_repeated_miami_block_preserves_locators_but_conflicts_fail(self):
        lines = ["---ASTER:", "Purple", "per bunch 2.00-3.00"]
        rows = self.parse_lines(lines + lines)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["product_id"], rows[1]["product_id"])
        self.assertNotEqual(rows[0]["source_locator"], rows[1]["source_locator"])
        with self.assertRaisesRegex(ValueError, "Ambiguous duplicate"):
            self.parse_lines(lines + ["---ASTER:", "Purple", "per bunch 2.00-4.00"])

    def test_standard_grade_and_exceptional_prices_keep_the_parent_quote(self):
        rows = self.parse_lines(
            [
                "---CARNATIONS:",
                "Red",
                "Standard",
                "per stem 0.25",
                "White",
                "Standard",
                "per stem 0.20-0.26",
                "---ROSE, HYBRID TEA:",
                "Red Varieties Freedom",
                "per stem",
                "60 cm 0.40-0.50 few 0.75",
                "50 cm 0.38-0.55 few 0.35",
            ]
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["details"]["variety"], "Red / Standard")
        self.assertEqual(rows[1]["details"]["variety"], "White / Standard")
        self.assertEqual(rows[2]["details"]["variety"], "Red Varieties Freedom / 60 cm")
        self.assertEqual(rows[2]["price"], 0.45)
        self.assertEqual(rows[2]["details"]["exceptional_prices"][0]["min"], 0.75)
        self.assertEqual(rows[3]["details"]["exceptional_prices"][0]["max"], 0.35)
        sparse = self.parse_lines(["---ASTER:", "Purple", "per bunch few 2.62"])
        self.assertEqual(sparse[0]["details"]["variety"], "Purple")
        self.assertEqual(sparse[0]["details"]["quote_qualifier"], "few")
        self.assertEqual(sparse[0]["price"], 2.62)

    def test_boston_verified_origins_and_repeated_producer_origin(self):
        parts = (
            date(2024, 6, 18),
            [
                (
                    "---SWEET WILLIAM: MARKET STEADY. per bunch NEW ENGLAND NEW ENGLAND PRODUCE 8.50",
                    1,
                    1,
                ),
                (
                    "---ASTER: MARKET STEADY. per bunch ITALY long 10.00 FRANCE open field long 12.00 TEXAS long 11.00",
                    1,
                    1,
                ),
            ],
        )
        with patch.object(src, "_pdf_parts", return_value=parts):
            rows = src.parse_boston_flowers(b"fixture")
        self.assertEqual(
            [r["details"]["origin"] for r in rows],
            ["NEW ENGLAND", "ITALY", "FRANCE", "TEXAS"],
        )
        self.assertEqual(rows[0]["details"]["variety"], "NEW ENGLAND PRODUCE")
        with patch.object(
            src,
            "_pdf_parts",
            return_value=(
                date(2024, 6, 18),
                [("---ASTER: per bunch COLOMBIA ECUADOR long 10.00", 1, 1)],
            ),
        ):
            with self.assertRaisesRegex(ValueError, "Ambiguous Boston flower origin"):
                src.parse_boston_flowers(b"fixture")

    def test_boston_composite_origin_and_carton_preserve_literal_basis(self):
        parts = (
            date(2024, 6, 18),
            [
                (
                    "---DAFFODIL: MARKET STEADY. per carton 50 bunches of 10 stems WASHINGTON field grown medium 3.50",
                    1,
                    1,
                ),
                (
                    "---LISIANTHUS: MARKET STEADY. per bunch NEW ENGLAND MASSACHUSETTS AND NEARBY PRODUCING AREAS open field long 15.00",
                    1,
                    1,
                ),
            ],
        )
        with patch.object(src, "_pdf_parts", return_value=parts):
            rows = src.parse_boston_flowers(b"fixture")
        self.assertEqual(rows[0]["unit"], "per carton 50 bunches of 10 stems")
        self.assertEqual(rows[0]["price"], 3.50)
        self.assertEqual(
            rows[1]["details"]["origin"],
            "NEW ENGLAND MASSACHUSETTS AND NEARBY PRODUCING AREAS",
        )
        with patch.object(
            src,
            "_pdf_parts",
            return_value=(
                date(2024, 6, 18),
                [
                    (
                        "---PAEONIA: NETHERLANDS long 3.50-4.00 per stem TEXAS long 3.50",
                        1,
                        1,
                    )
                ],
            ),
        ):
            with self.assertRaisesRegex(ValueError, "before its package"):
                src.parse_boston_flowers(b"fixture")

    def test_unquoted_product_does_not_inherit_neighbor_price(self):
        rows = self.parse_lines(
            [
                "---HYDRANGEA: DEMAND MODERATE.",
                "Prices represent few spot market sales.",
                "VARIOUS VARIETIES Blue",
                "per stem supplies in too few hands to establish a market",
                "VARIOUS VARIETIES White",
                "per stem 0.74-1.15 mostly 0.90-1.00",
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertIn("White", rows[0]["product_name"])

    def test_invalid_ranges_fail(self):
        for quote in ["per stem 2.00-1.00", "per stem 1.00-2.00 mostly 3.00"]:
            with self.subTest(quote=quote), self.assertRaises(ValueError):
                self.parse_lines(
                    [
                        "---CARNATIONS: MARKET STEADY.",
                        "Prices represent few spot market sales.",
                        "Select",
                        quote,
                    ]
                )

    def test_older_market_boundary_and_wrapped_no_quote_preserve_grade(self):
        rows = self.parse_lines(
            [
                "---ALSTROEMERIA: DEMAND MODERATE. MARKET ABOUT",
                "STEADY.",
                "ASSORTED COLORS",
                "Super Select",
                "bunched 10s Supplies in too few hands to establish a",
                "market.",
                "Select",
                "bunched 10s 2.63-3.45 mostly 2.63-3.07",
                "---ROSE, SPRAY TYPE: DEMAND MODERATE. MARKET PINK 50 CM",
                "LOWER, OTHERS ABOUT STEADY.",
                "PINK VARIETIES",
                "per stem",
                "50 cm 0.34-0.50 mostly 0.38-0.42",
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["details"]["variety"], "ASSORTED COLORS / Select")
        self.assertEqual(rows[0]["details"]["mostly_max"], 3.07)
        self.assertEqual(rows[1]["details"]["variety"], "PINK VARIETIES / 50 cm")
        self.assertEqual(rows[1]["unit"], "per stem")

    def test_wrapped_price_qualifier_does_not_become_flower_variant(self):
        rows = self.parse_lines(
            [
                "---CARNATIONS: DEMAND MODERATE. MARKET ABOUT STEADY.",
                "Assorted Colors",
                "Fancy",
                "per stem 0.25-0.30 mostly 0.26-0.27 occasional higher and",
                "lower Novelty Fancy 0.25-0.29 mostly 0.26-0.27",
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            rows[1]["details"]["variety"], "Assorted Colors / Fancy; Novelty Fancy"
        )
        self.assertEqual(
            rows[1]["details"]["original_quote"],
            "lower Novelty Fancy 0.25-0.29 mostly 0.26-0.27",
        )

    def test_header_without_narrative_preserves_explicit_package_rules(self):
        rows = self.parse_lines(
            [
                "---ANTIRRHINUM (SNAPDRAGON):",
                "bunched 10s",
                "70 cm supplies in too few hands to establish a market.",
                "---ASTER:",
                "Purple",
                "per bunch 2.00-3.00",
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["details"]["source_product"], "ASTER")
        with self.assertRaises(ValueError):
            self.parse_lines(["---ASTER:", "Purple 2.00-3.00"])

    def test_wrapped_literal_price_range_preserves_both_lines(self):
        rows = self.parse_lines(
            [
                "---CARNATIONS: DEMAND MODERATE. MARKET ABOUT STEADY.",
                "Assorted Colors",
                "Fancy",
                "per stem 0.25-0.30 mostly 0.26-0.27 Novelty Fancy 0.25-",
                "0.30 mostly 0.26-0.27",
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual((rows[1]["min"], rows[1]["max"]), (0.25, 0.30))
        self.assertEqual(rows[1]["details"]["mostly_min"], 0.26)
        self.assertIn("Fancy; Novelty Fancy", rows[1]["product_name"])
        self.assertIn("text row 4-5", rows[1]["source_locator"])
        self.assertIn("0.25-\n0.30", rows[1]["details"]["original_quote"])

    def test_unfinished_or_nonadjacent_price_range_fails(self):
        for tail in [[], ["Select"], ["0.20 mostly 0.26-0.27"]]:
            with self.subTest(tail=tail), self.assertRaises(ValueError):
                self.parse_lines(["---CARNATIONS:", "per stem 0.25-", *tail])
        with (
            patch.object(
                src,
                "_pdf_parts",
                return_value=(
                    date(2025, 8, 11),
                    [
                        ("---CARNATIONS:", 1, 1),
                        ("per stem 0.25-", 1, 1),
                        ("0.30", 2, 1),
                    ],
                ),
            ),
            self.assertRaisesRegex(ValueError, "range continuation"),
        ):
            src.parse_miami_flowers(b"fixture")

    def test_literal_single_decimal_quote_is_a_price_not_variety(self):
        rows = self.parse_lines(
            [
                "---CHRYSANTHEMUM: DEMAND MODERATE. MARKET ABOUT STEADY.",
                "FUJI/SPIDER Disbud, White",
                "bunched 10s 3.50-4.46 mostly 3.50-4.00 Green 3.5-4.46",
                "mostly 3.50-4.00",
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            rows[1]["details"]["variety"], "FUJI/SPIDER Disbud, White; Green"
        )
        self.assertEqual((rows[1]["min"], rows[1]["max"]), (3.5, 4.46))
        self.assertEqual(rows[1]["details"]["mostly_max"], 4.00)
        for quote in ["per stem 3.500-4.46", "per stem 3.50-4.46 Green 3.500"]:
            with self.subTest(quote=quote), self.assertRaises(ValueError):
                self.parse_lines(["---CARNATIONS:", quote])

    def test_unrecognized_old_narrative_or_notice_never_drops_numeric_quotes(self):
        for lines in [
            ["---ASTER: DEMAND MODERATE. MARKET", "per bunch 2.00-3.00"],
            ["---ASTER: Approximate prices 2.00-3.00.", "per bunch 2.00-3.00"],
            [
                "---ASTER: DEMAND MODERATE.",
                "per bunch Supplies in too few hands to establish a",
                "2.00-3.00",
            ],
        ]:
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                self.parse_lines(lines)


@unittest.skipUnless(
    (FIXTURES / "CMO-Historical-Data-Monthly.xlsx").exists(),
    "Downloaded source fixture not installed",
)
class DownloadedSourceTests(unittest.TestCase):
    def test_world_bank_complete_numeric_coverage(self):
        rows = src.parse_world_bank(
            (FIXTURES / "CMO-Historical-Data-Monthly.xlsx").read_bytes(),
            src.WORLD_BANK_MONTHLY,
        )
        self.assertEqual((len(rows), len({r["product_id"] for r in rows})), (31381, 45))
        self.assertEqual(min(r["date"] for r in rows), date(1960, 1, 31))
        self.assertEqual(max(r["date"] for r in rows), date(2026, 8, 31))
        self.assertEqual(len({(r["product_id"], r["date"]) for r in rows}), len(rows))
        latest = {r["product_id"]: r for r in rows if r["date"] == date(2026, 8, 31)}
        self.assertEqual(latest["wb-coffee-arabica"]["price"], 7.97)
        self.assertEqual(latest["wb-coffee-robusta"]["price"], 3.98)

    def test_real_miami_three_pages_preserve_all_66_variants(self):
        rows = src.parse_miami_flowers((FIXTURES / "miami-flower.pdf").read_bytes())
        self.assertEqual(len(rows), 66)
        rose = [r for r in rows if r["details"]["source_product"] == "ROSE, HYBRID TEA"]
        self.assertEqual(len(rose), 6)
        self.assertEqual({r["source_page"] for r in rows}, {1, 2, 3})
        self.assertTrue(all(r["min"] <= r["price"] <= r["max"] for r in rows))
        canonical = json.dumps(
            rows, sort_keys=True, default=str, separators=(",", ":"), ensure_ascii=False
        )
        self.assertEqual(
            hashlib.sha256(canonical.encode()).hexdigest(),
            "7504562bf1168bede73a4ad0fe007b00962411694e0f0f1ff13fd42e80465530",
        )

    def test_real_older_miami_complete_native_price_coverage(self):
        rows = src.parse_miami_flowers(
            (FIXTURES / "usda-miami-historical-failure.pdf").read_bytes()
        )
        self.assertEqual(len(rows), 61)
        self.assertEqual({r["date"] for r in rows}, {date(2025, 7, 28)})
        self.assertEqual({r["source_page"] for r in rows}, {1, 2})
        self.assertEqual(
            Counter(r["unit"] for r in rows),
            {"per stem": 30, "per bunch": 25, "bunched 10s": 6},
        )
        self.assertEqual(
            Counter(r["details"]["source_product"] for r in rows),
            {
                "ALSTROEMERIA": 1,
                "ANTIRRHINUM (SNAPDRAGON)": 1,
                "ASTER": 2,
                "CARNATIONS": 13,
                "CARNATIONS, MINIATURE": 5,
                "CHRYSANTHEMUM": 15,
                "GYPSOPHILA": 2,
                "HYDRANGEA": 4,
                "LIMONIUM": 4,
                "ROSE, HYBRID TEA": 6,
                "ROSE, SPRAY TYPE": 7,
                "SOLIDAGO": 1,
            },
        )
        self.assertEqual(len({r["source_locator"] for r in rows}), 61)
        self.assertEqual(len({r["product_id"] for r in rows}), 61)
        self.assertEqual(rows[0]["details"]["variety"], "ASSORTED COLORS / Select")
        self.assertEqual((rows[0]["min"], rows[0]["max"]), (2.63, 3.45))
        self.assertEqual((rows[-1]["min"], rows[-1]["max"]), (2.69, 3.55))
        self.assertTrue(all(r["min"] <= r["price"] <= r["max"] for r in rows))

    def test_real_neighbor_reports_reconcile_every_printed_range(self):
        for name, count, day, ranges in [
            ("usda-miami-historical-failure.pdf", 61, date(2025, 7, 28), 116),
            ("usda-miami-neighbor-1.pdf", 63, date(2025, 8, 4), 122),
            ("usda-miami-neighbor-2.pdf", 62, date(2025, 8, 11), 120),
            ("miami-flower.pdf", 66, date(2026, 8, 31), 97),
        ]:
            with self.subTest(source=name):
                body = (FIXTURES / name).read_bytes()
                rows = src.parse_miami_flowers(body)
                report_day, lines = src._pdf_parts(body, "MH_FV221", 2)
                self.assertEqual((len(rows), report_day), (count, day))
                # Independently read the complete native text across line wraps
                # and reconcile all printed ranges, including mostly ranges.
                printed = Counter(
                    (float(m["low"]), float(m["high"] or m["low"]))
                    for m in src.PRICE.finditer(" ".join(line for line, _, _ in lines))
                )
                extracted = Counter((r["min"], r["max"]) for r in rows)
                extracted.update(
                    (r["details"]["mostly_min"], r["details"]["mostly_max"])
                    for r in rows
                    if "mostly_min" in r["details"]
                )
                self.assertEqual(sum(printed.values()), ranges)
                self.assertEqual(printed, extracted)
                self.assertEqual(len({r["product_id"] for r in rows}), count)

    def test_real_boston_exact_colombian_prices(self):
        rows = src.parse_boston_flowers((FIXTURES / "boston-flower.pdf").read_bytes())
        self.assertEqual(len(rows), 35)
        colombia = [r for r in rows if r["details"]["origin"] == "COLOMBIA"]
        self.assertEqual(len(colombia), 7)
        clavel = next(
            r for r in colombia if r["details"]["source_product"] == "CARNATIONS"
        )
        self.assertEqual(
            (clavel["min"], clavel["max"], clavel["unit"]), (0.60, 0.70, "per stem")
        )
        callas = [
            r
            for r in colombia
            if r["details"]["source_product"] == "ZANTEDESCHIA (CALLA)"
        ]
        self.assertEqual(len(callas), 2)

    def test_historical_boston_pdf_layouts(self):
        for file, count in [
            ("boston-2025-06-17.pdf", 34),
            ("boston-2025-07-01.pdf", 32),
            ("boston-2025-08-12.pdf", 35),
        ]:
            with self.subTest(file=file):
                self.assertEqual(
                    len(src.parse_boston_flowers((FIXTURES / file).read_bytes())), count
                )

    def test_publisher_malformed_miami_range_is_rejected(self):
        # September 29, 2025 literally prints "0.25-.0.29" in the source.
        with self.assertRaises(ValueError):
            src.parse_miami_flowers((FIXTURES / "miami-2025-09-29.pdf").read_bytes())


@unittest.skipUnless(
    (AUDIT_FIXTURES / "miami-current.pdf").exists(),
    "September 26 audit fixture not installed",
)
class September2026LiveSourceRegressions(unittest.TestCase):
    def test_current_and_recovered_reports_reconcile_every_printed_range(self):
        for filename, market, count, day in [
            ("miami-current.pdf", "miami", 76, date(2026, 9, 21)),
            ("boston-current.pdf", "boston", 35, date(2026, 9, 22)),
            ("failed-00.pdf", "boston", 130, date(2024, 1, 23)),
            ("failed-01.pdf", "boston", 79, date(2024, 6, 18)),
            ("failed-03.pdf", "boston", 112, date(2024, 4, 2)),
            ("failed-04.pdf", "boston", 116, date(2024, 2, 20)),
            ("failed-07.pdf", "miami", 76, date(2024, 8, 22)),
            ("failed-09.pdf", "miami", 71, date(2025, 4, 22)),
            ("failed-10.pdf", "miami", 62, date(2025, 1, 21)),
            ("failed-11.pdf", "miami", 68, date(2025, 3, 18)),
            ("failed-13.pdf", "miami", 63, date(2025, 1, 23)),
        ]:
            with self.subTest(filename=filename):
                body = (AUDIT_FIXTURES / filename).read_bytes()
                rows = src.parse(body, filename, f"international-usda-{market}-flowers")
                report_day, lines = src._pdf_parts(
                    body,
                    "MH_FV221" if market == "miami" else "BH_FV201",
                    2 if market == "miami" else 1,
                )
                self.assertEqual((len(rows), report_day), (count, day))
                printed = Counter(
                    (float(m["low"]), float(m["high"] or m["low"]))
                    for m in src.PRICE.finditer(" ".join(line for line, _, _ in lines))
                )
                extracted = Counter((r["min"], r["max"]) for r in rows)
                extracted.update(
                    (r["details"]["mostly_min"], r["details"]["mostly_max"])
                    for r in rows
                    if "mostly_min" in r["details"]
                )
                extracted.update(
                    (quote["min"], quote["max"])
                    for row in rows
                    for quote in row["details"].get("exceptional_prices", [])
                )
                self.assertEqual(printed, extracted)
                self.assertEqual(len({r["source_locator"] for r in rows}), len(rows))

    def test_latest_wrapped_colors_and_colombian_boston_quote(self):
        rows = src.parse_miami_flowers(
            (AUDIT_FIXTURES / "miami-current.pdf").read_bytes()
        )
        purple = next(
            r
            for r in rows
            if r["details"]["source_product"] == "CARNATIONS, MINIATURE"
            and r["details"]["variety"] == "Assorted Colors; Purple"
        )
        self.assertEqual(
            (purple["min"], purple["max"], purple["details"]["mostly_max"]),
            (3.23, 3.75, 3.29),
        )
        self.assertEqual(
            purple["source_locator"], "PDF page 1, col 2, text row 74-75, quote 3"
        )
        self.assertTrue(all("Burgundy" not in r["product_name"] for r in rows))
        boston = src.parse_boston_flowers(
            (AUDIT_FIXTURES / "boston-current.pdf").read_bytes()
        )
        clavel = next(
            r for r in boston if r["details"]["source_product"] == "CARNATIONS"
        )
        self.assertEqual(
            (clavel["details"]["origin"], clavel["min"], clavel["max"], clavel["unit"]),
            ("COLOMBIA", 0.60, 0.70, "per stem"),
        )

    def test_genuinely_contradictory_publications_remain_rejected(self):
        for filename, market, reason in [
            ("failed-06.pdf", "boston", "Ambiguous duplicate"),
            ("failed-08.pdf", "miami", "Malformed USDA printed price range"),
            ("failed-12.pdf", "miami", "mostly range is outside"),
            ("historical-4af6bea32800ca79.pdf", "boston", "before its package"),
        ]:
            with (
                self.subTest(filename=filename),
                self.assertRaisesRegex(ValueError, reason),
            ):
                src.parse(
                    (AUDIT_FIXTURES / filename).read_bytes(),
                    filename,
                    f"international-usda-{market}-flowers",
                )

    def test_repeated_conflicting_mostly_qualifier_reviews_only_affected_quote(self):
        fixture = AUDIT_FIXTURES / "all-10bc0303cd855711.pdf"
        if not fixture.exists():
            self.skipTest("Real USDA Boston August 5 2025 fixture")
        rows = src.parse_boston_flowers(fixture.read_bytes())
        self.assertEqual(len(rows), 35)
        review = [r for r in rows if r["price"] is None]
        self.assertEqual(len(review), 1)
        row = review[0]
        self.assertEqual(row["details"]["source_product"], "SOLIDAGO")
        self.assertEqual(
            row["source_locator"], "PDF page 1, commodity SOLIDAGO, quote 1"
        )
        self.assertEqual(
            (row["min"], row["max"], row["date"]), (10, 14, date(2025, 8, 5))
        )
        self.assertIn("quality_issue", row["details"])
        self.assertEqual(
            [(q["min"], q["max"]) for q in row["details"]["conflicting_mostly_quotes"]],
            [(13, 13), (10, 10)],
        )
        self.assertTrue(all(r["price"] > 0 for r in rows if r not in review))


class NativeTextFlowerTests(unittest.TestCase):
    def parse_text(self, text, market="Boston"):
        heading = "Terminal" if market == "Boston" else "Shipping Point"
        body = (
            f"{market.upper()} Ornamental {heading} Prices as of 27-NOV-2018\n"
            "Provided by: Specialty Crops Market News\nUSDA.\n" + text
        ).encode()
        return src.parse(
            body,
            "https://esmis.nal.usda.gov/report.TXT",
            f"international-usda-{market.lower()}-flowers",
        )

    def test_discovery_includes_txt_and_canonicalizes_archive_fragments(self):
        for market in ("miami", "boston"):
            fixture = AUDIT_FIXTURES / f"international-usda-{market}-index-last.html"
            if not fixture.exists():
                self.skipTest("Native TXT archive index fixtures")
            url = (
                src.USDA_MIAMI_ARCHIVE if market == "miami" else src.USDA_BOSTON_ARCHIVE
            )
            found = src.discover(
                fixture.read_bytes(), url, f"international-usda-{market}-index"
            )
            self.assertTrue(any(u.upper().endswith(".TXT") for u, _ in found))
            self.assertTrue(all("#" not in u for u, _ in found))
            self.assertEqual(len(found), len(set(found)))
        found = src.discover(
            b'<a href="?page=1#main-content">One</a><a href="?page=1">Same</a>',
            src.USDA_MIAMI_ARCHIVE,
            "international-usda-miami-index",
        )
        self.assertEqual(
            found,
            [(src.USDA_MIAMI_ARCHIVE + "?page=1", "international-usda-miami-index")],
        )

    def test_explicit_packages_origins_and_sizes_are_preserved(self):
        rows = self.parse_text(
            "---ROSE, HYBRID TEA: MARKET STEADY. per stem EC Red Varieties 70cm .95-1.25 mostly .95 60cm .85-1.25 mostly .85\n"
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            [r["details"]["variety"] for r in rows],
            ["Red Varieties 70cm", "Red Varieties 60cm"],
        )
        self.assertTrue(
            all(r["details"]["origin"] == "USDA origin code EC" for r in rows)
        )
        self.assertTrue(
            all(
                r["source_page"] is None
                and r["source_locator"].startswith("Text lines")
                for r in rows
            )
        )
        self.assertEqual(
            (rows[0]["min"], rows[0]["max"], rows[0]["unit"]), (0.95, 1.25, "per stem")
        )

    def test_ambiguous_variant_review_preserves_valid_siblings_and_all_ranges(self):
        rows = self.parse_text(
            "---ASTER: per bunch CB Monte Casino long 7.50 red 8.00 NL long 12.00 mostly 13.00\n---ACACIA: per bunch CB long 7.50\n"
        )
        self.assertEqual(len(rows), 4)
        self.assertIsNone(rows[1]["price"])
        self.assertIsNone(rows[2]["price"])
        self.assertEqual(rows[2]["details"]["out_of_range_mostly_quotes"][0]["min"], 13)
        self.assertEqual(rows[0]["price"], 7.5)
        self.assertEqual(rows[3]["price"], 7.5)

    def test_bad_header_is_rejected_without_trying_ocr_or_pdf(self):
        with self.assertRaisesRegex(ValueError, "header"):
            src.parse(
                b"<html>price 9.50</html>",
                "https://esmis.nal.usda.gov/report.TXT",
                "international-usda-boston-flowers",
            )

    def test_all_ranges_in_both_real_2018_reports_are_retained(self):
        for market, count, publishable, day in [
            ("miami", 85, 52, date(2018, 12, 17)),
            ("boston", 190, 135, date(2018, 11, 27)),
        ]:
            fixture = AUDIT_FIXTURES / f"{market}-2018.TXT"
            if not fixture.exists():
                self.skipTest("Actual 2018 native text originals")
            body = fixture.read_bytes()
            rows = src.parse(
                body,
                f"https://esmis.nal.usda.gov/{market}.TXT",
                f"international-usda-{market}-flowers",
            )
            self.assertEqual(len(rows), count)
            self.assertEqual(sum(r["price"] is not None for r in rows), publishable)
            self.assertTrue(all(r["date"] == day for r in rows))
            self.assertEqual(len({r["source_locator"] for r in rows}), len(rows))
            printed = Counter(
                (float(m["low"]), float(m["high"] or m["low"]))
                for m in src.PRICE.finditer(" ".join(body.decode().split()))
            )
            retained = Counter((r["min"], r["max"]) for r in rows)
            retained.update(
                (r["details"]["mostly_min"], r["details"]["mostly_max"])
                for r in rows
                if "mostly_min" in r["details"]
            )
            for key in (
                "exceptional_prices",
                "conflicting_mostly_quotes",
                "out_of_range_mostly_quotes",
            ):
                retained.update(
                    (q["min"], q["max"])
                    for r in rows
                    for q in r["details"].get(key, [])
                )
            self.assertEqual(printed, retained)
            if market == "miami":
                self.assertEqual(
                    rows[0]["details"]["variety"], "Sup Sel Assorted Colors"
                )
                self.assertEqual(
                    (rows[0]["min"], rows[0]["max"], rows[0]["unit"]),
                    (2.45, 2.65, "bunched 10s"),
                )
                self.assertIn(
                    "Mostly Colombia.", rows[0]["details"]["commodity_origin_note"]
                )
            else:
                self.assertEqual((rows[0]["price"], rows[1]["price"]), (7.5, 12))
                self.assertEqual(rows[0]["details"]["origin"], "USDA origin code CB")


if __name__ == "__main__":
    unittest.main()

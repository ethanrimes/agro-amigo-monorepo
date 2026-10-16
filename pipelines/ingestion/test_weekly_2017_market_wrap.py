"""Exact archived January 2017 two-column Medellín market-line oracle."""

import unittest
from datetime import date
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from pipelines.ingestion import dane_weekly as weekly


SOURCE = Path(__file__).parent / "testdata/dane_weekly_2017_01_21_original.pdf"


def word(text, x, top, bold=False):
    return {
        "text": text,
        "x0": x,
        "x1": x + len(text) * 3,
        "top": top,
        "fontname": "FuturaStd-Bold" if bold else "FuturaStd-Book",
    }


def monetary_line(label, top, minimum, maximum, mean):
    return [
        word(label, 36, top), word(minimum, 180, top),
        word(maximum, 215, top), word(mean, 250, top),
    ]


HEADERS = [{"x0": x, "x1": x + 25} for x in (170, 205, 240)]
PERIOD = (date(2017, 1, 21), date(2017, 1, 27))


class January2017NativeMarketWrap(unittest.TestCase):
    def test_full_original_changes_only_315_followers_and_194_predecessors(self):
        body = SOURCE.read_bytes()
        self.assertEqual(sha256(body).hexdigest(), weekly.JANUARY_2017_MARKET_WRAP_SHA)
        original_column = weekly._native_column

        def old_assignment(*args, **kwargs):
            return original_column(*args, **{**kwargs, "january_2017_market_wrap": False})

        with patch.object(weekly, "_native_column", side_effect=old_assignment):
            prior = weekly.parse_pdf(body, weekly.JANUARY_2017_MARKET_WRAP_URL)
        revised = weekly.parse_pdf(body, weekly.JANUARY_2017_MARKET_WRAP_URL)
        self.assertEqual((len(prior), len(revised)), (4716, 4716))
        self.assertEqual(
            (sum(row["price"] is not None for row in prior),
             sum(row["price"] is not None for row in revised)),
            (4560, 4560),
        )
        changed_market = 0
        newly_bound = 0
        for old, new in zip(prior, revised):
            for key in set(old) | set(new):
                if key not in {"market", "details"}:
                    self.assertEqual(old.get(key), new.get(key),
                                     (new["source_locator"], key))
            if old["market"] != new["market"]:
                changed_market += 1
            if new["details"].get("native_market_join") == (
                "january_2017_same_column_leading_market_line"
            ):
                newly_bound += 1
                self.assertEqual(len(new["details"]["literal_market_lines"]), 2)
        self.assertEqual((changed_market, newly_bound), (494, 315))

        by_locator = {row["source_locator"]: row for row in revised}
        # Independent visual readings of physical pages 6, 16, and 31.
        controls = [
            (6, 1, 10, "Acelga", "Ipiales (Nariño), Ipiales somos todos", 1000, 1000, 1000),
            (6, 1, 12, "Acelga", "Medellín, Central Mayorista de Antioquia", 1000, 1200, 1050),
            (16, 2, 58, "Limón Tahití", "Manizales (Caldas)", 700, 1000, 838),
            (16, 2, 60, "Limón Tahití", "Medellín, Central Mayorista de Antioquia", 800, 1000, 902),
            (16, 2, 62, "Limón Tahití", "Medellín, Plaza Minorista “José María Villa”", 800, 1200, 1063),
            (31, 1, 47, "Carne de cerdo, costilla", "Manizales (Caldas)", 12000, 14000, 12667),
            (31, 1, 49, "Carne de cerdo, costilla", "Medellín, Central Mayorista de Antioquia", 10800, 15700, 12500),
            (31, 1, 51, "Carne de cerdo, costilla", "Medellín, Plaza Minorista “José María Villa”", 12800, 13500, 13075),
        ]
        for page, column, line, product, market, minimum, maximum, mean in controls:
            locator = f"PDF page {page},table 1,column {column},line {line}"
            with self.subTest(locator=locator):
                row = by_locator[locator]
                self.assertEqual(
                    (row["product_name"], row["market"], row["min"], row["max"], row["price"], row["unit"], row["date"]),
                    (product, market, minimum, maximum, mean, "kg", "2017-01-27"),
                )

    def test_lead_requires_immediate_priced_follower_in_same_product_column(self):
        lines = [
            [word("Acelga", 36, 10, bold=True)],
            monetary_line("Manizales (Caldas)", 20, "700", "1.000", "838"),
            [word("Medellín, Central", 36, 26.8)],
            monetary_line("Mayorista de Antioquia", 33.6, "800", "1.000", "902"),
            [word("Medellín, Plaza", 36, 40.4)],
            monetary_line("Minorista “José María Villa”", 47.2, "800", "1.200", "1.063"),
        ]
        args = (lines, HEADERS, "verduras y hortalizas", PERIOD, 6, 1, 1, {})
        rows = weekly._native_column(*args, january_2017_market_wrap=True)
        self.assertEqual(
            [(r["market"], r["price"]) for r in rows],
            [("Manizales (Caldas)", 838),
             ("Medellín, Central Mayorista de Antioquia", 902),
             ("Medellín, Plaza Minorista “José María Villa”", 1063)],
        )
        old = weekly._native_column(*args)
        self.assertEqual(old[0]["market"], "Manizales (Caldas) Medellín, Central")

        cases = (
            # A follower printed only in the other physical column is not
            # present in this column's input and cannot be borrowed.
            lines[:3],
            # A different monetary market follows the lead.
            lines[:3] + [monetary_line("Otro mercado", 33.6, "800", "1.000", "902")],
            # The purported follower is too far away.
            lines[:3] + [monetary_line("Mayorista de Antioquia", 38, "800", "1.000", "902")],
            # A product boundary cannot supply a follower in the next block.
            lines[:3] + [[word("Limón Tahití", 36, 33.6, bold=True)]]
            + [monetary_line("Mayorista de Antioquia", 40.4, "800", "1.000", "902")],
        )
        for malformed in cases:
            with self.subTest(malformed=malformed[-1][0]["text"]), self.assertRaises(ValueError):
                weekly._native_column(
                    malformed, HEADERS, "verduras y hortalizas", PERIOD,
                    6, 1, 1, {}, january_2017_market_wrap=True,
                )


if __name__ == "__main__":
    unittest.main()

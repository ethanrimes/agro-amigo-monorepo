"""Exact printed July 2022 continuation typo, with whole-original parity."""

import csv
import re
import unittest
from hashlib import sha256
from pathlib import Path

from . import dane_weekly as weekly


HERE = Path(__file__).parent / "testdata"
ORIGINAL = HERE / "dane_weekly_2022_07_02_original.pdf"
CONTROLS = HERE / "weekly_20220708_manual_six_prices.psv"
URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_02jul_al_08jul_2022.pdf"
SHA = "9f428bddcef7ede04ba7d91b7e39d2a89413a70f4b132d1f516f4577330c271c"
LITERAL = "Aguacate papelillo (comtinuación)"
LOCATOR_PREFIX = "PDF page 21,table 1,column 2,line "


class WeeklyJuly2022PrintedContinuation(unittest.TestCase):
    def test_only_exact_native_terminal_annotation_is_stripped(self):
        self.assertEqual(weekly.VERSION, "dane-weekly-v24")
        self.assertEqual(weekly._product_heading(LITERAL), ("Aguacate papelillo", True))
        for unrelated in (
            "Aguacate papelillo (comtinuacion)",
            "Aguacate papelillo (comtinuación) extra",
            "Aguacate papelillo variedad comtinuación",
            "Aguacate papelillo (cultivo tardío)",
        ):
            with self.subTest(unrelated=unrelated):
                self.assertEqual(weekly._product_heading(unrelated), (unrelated, False))

    def test_complete_native_pdf_only_six_identity_rows_change(self):
        body = ORIGINAL.read_bytes()
        self.assertEqual(len(body), 4_149_203)
        self.assertEqual(sha256(body).hexdigest(), SHA)
        self.assertEqual(sha256(CONTROLS.read_bytes()).hexdigest(),
                         "c51f40cb2a430f65b6a4a0ea311e96dfdb6dff5ab50b43f3eb9748443f451085")
        with CONTROLS.open() as stream:
            controls = list(csv.DictReader(stream, delimiter="|"))
        self.assertEqual(len(controls), 6)

        current = weekly.parse_pdf(body, URL)
        self.assertEqual(len(current), 4378)
        affected = {row["source_locator"]: row for row in current
                    if row["details"].get("literal_product_heading") == LITERAL}
        self.assertEqual(set(affected), {row["source_locator"] for row in controls})
        for control in controls:
            with self.subTest(market=control["market"]):
                row = affected[control["source_locator"]]
                self.assertTrue(row["source_locator"].startswith(LOCATOR_PREFIX))
                self.assertEqual(row["product_name"], "Aguacate papelillo")
                self.assertEqual(row["market"], control["market"])
                self.assertEqual((row["min"], row["max"], row["price"]),
                                 tuple(int(control[key]) for key in ("minimum", "maximum", "mean")))
                self.assertEqual(row["details"]["trend"], control["trend"])
                self.assertEqual((row["date"], row["period_start"], row["unit"]),
                                 ("2022-07-08", "2022-07-02", "kg"))
                self.assertEqual(row["details"]["literal_product_heading"], LITERAL)

        # Reproduce the archived v22 classification by removing only the newly
        # approved literal marker. The whole 4,378-row original must otherwise
        # stay identical: no amount, date, unit, locator or unrelated identity
        # can drift behind this finite correction.
        prior = weekly.PRODUCT_CONTINUATION
        old_markers = tuple(marker for marker in weekly.PRODUCT_CONTINUATION_MARKERS
                            if marker != "(comtinuación)")
        try:
            weekly.PRODUCT_CONTINUATION = re.compile(
                r"\s*(?:" + "|".join(re.escape(marker) for marker in
                                      sorted(old_markers, key=len, reverse=True)) + r")\s*$",
                re.IGNORECASE,
            )
            old = weekly.parse_pdf(body, URL)
        finally:
            weekly.PRODUCT_CONTINUATION = prior
        self.assertEqual(len(old), len(current))
        changed = []
        for before, after in zip(old, current, strict=True):
            self.assertEqual(before["source_locator"], after["source_locator"])
            different = {key for key in before if before[key] != after[key]}
            if different:
                self.assertEqual(different,
                                 {"product_id", "product_name", "identity_dimensions", "details"})
                self.assertEqual(before["product_name"], LITERAL)
                self.assertEqual(after["product_name"], "Aguacate papelillo")
                self.assertEqual(before["details"] | {"literal_product_heading": LITERAL},
                                 after["details"])
                changed.append(after["source_locator"])
        self.assertEqual(set(changed), set(affected))
        self.assertEqual(len(changed), 6)
        self.assertTrue(any(row["source_locator"].startswith("PDF page 21,table 1,column 1,")
                            and row["product_name"] == "Aguacate papelillo" for row in current))


if __name__ == "__main__":
    unittest.main()

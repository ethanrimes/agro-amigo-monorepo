"""Audited 2012 headings and market ligatures join without changing money."""

import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from . import dane_weekly as weekly
from . import worker


ORIGINAL = Path(__file__).parent / "testdata/dane_weekly_2012_06_16_original.pdf"
SHA = "dd059a09eecb1fa01cadb24a4f21a7768d97d9e31684dee6a57222c536faf6a8"
CONTROLS = {
    "PDF page 19,table 1,column 1,line 49": ("Barranquilla. Barranquillita", 8000, 8000, 8000),
    "PDF page 19,table 1,column 1,line 50": ("Bogotá, D. C. Frigorífico Guadalupe", 7575, 7675, 7625),
    "PDF page 19,table 1,column 1,line 51": ("Bogotá, D. C. Frigorífico San Martín", 8267, 8267, 8267),
    "PDF page 19,table 1,column 1,line 52": ("Pereira. La 41", 9500, 9500, 9500),
    "PDF page 22,table 1,column 1,line 24": ("Bogotá, D. C. Paloquemao", 18000, 18000, 18000),
}


class Weekly2012FontRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = ORIGINAL.read_bytes()
        assert hashlib.sha256(cls.body).hexdigest() == SHA

    def test_full_original_five_headings_and_71_market_runs_only(self):
        # Parse the exact bytes under the pre-repair native path. This disables
        # all three source-bound changes without changing the dated source URL.
        with patch.object(weekly, "JUNE_2012_FONT_RUN_SHA", "0" * 64):
            old = weekly.parse_pdf(self.body, weekly.JUNE_2012_FONT_RUN_URL)
        new = weekly.parse_pdf(self.body, weekly.JUNE_2012_FONT_RUN_URL)
        self.assertEqual((len(old), len(new)), (1428, 1428))
        self.assertEqual((sum(r["price"] is not None for r in new),
                          sum(r["price"] is None for r in new)), (1340, 88))
        canonical = lambda rows: json.dumps(rows, sort_keys=True, ensure_ascii=False,
                                            separators=(",", ":"), allow_nan=False).encode()
        self.assertEqual(hashlib.sha256(canonical(old)).hexdigest(),
                         "078cee539d0634651400d43916bed1444a77b296a620d9e61e28ba16434ebdb8")
        self.assertEqual(hashlib.sha256(canonical(new)).hexdigest(),
                         "1e6dbd51e7e388f446521e73af589e62996a292cadfeed295200aea824580d22")
        old_by = {r["source_locator"]: r for r in old}
        new_by = {r["source_locator"]: r for r in new}
        self.assertEqual(set(old_by), set(new_by))
        changed = {k for k in old_by if old_by[k] != new_by[k]}
        heading_changed = {k for k in old_by if old_by[k]["product_name"] != new_by[k]["product_name"]}
        market_changed = {k for k in old_by if old_by[k]["market"] != new_by[k]["market"]}
        self.assertEqual(heading_changed, set(CONTROLS))
        self.assertEqual((len(market_changed), len(changed), len(heading_changed & market_changed)),
                         (71, 74, 2))
        self.assertEqual(changed, heading_changed | market_changed)
        self.assertEqual({new_by[k]["market"] for k in market_changed},
                         {"Bogotá, D. C. Frigorífico Guadalupe",
                          "Bogotá, D. C. Frigorífico San Martín"})
        self.assertEqual((sum(new_by[k]["market"].endswith("Guadalupe") for k in market_changed),
                          sum(new_by[k]["market"].endswith("San Martín") for k in market_changed)),
                         (37, 34))
        for locator in changed:
            before, after = old_by[locator], new_by[locator]
            changed_fields = {key for key in before if before[key] != after[key]}
            expected_fields = {"details"}
            if locator in heading_changed:
                expected_fields |= {"product_id", "product_name", "identity_dimensions"}
            if locator in market_changed:
                expected_fields.add("market")
                self.assertEqual(after["details"]["literal_market_font_runs"], ["Frigoríﬁ", "co"])
                self.assertEqual(after["details"]["native_market_recovery"],
                                 "exact_2012_adjacent_ligature_run")
            self.assertEqual(changed_fields, expected_fields)
        for locator, (market, low, high, mean) in CONTROLS.items():
            before, after = old_by[locator], new_by[locator]
            expected_product = ("Calamar anillos" if locator.startswith("PDF page 22")
                                else "Carne de cerdo, pernil con hueso")
            self.assertEqual(after["product_name"], expected_product)
            self.assertEqual((after["market"], after["min"], after["max"], after["price"]),
                             (market, low, high, mean))
            self.assertEqual(after["date"], "2012-06-22")
            self.assertEqual(after["unit"], "kg")
            self.assertEqual(after["details"]["literal_product_heading"], expected_product)
            self.assertEqual(after["details"]["native_heading_recovery"],
                             "exact_2012_adjacent_font_run")
            for key in ("date", "unit", "min", "max", "price", "source_page", "source_locator"):
                self.assertEqual(before[key], after[key])

    def test_other_url_and_changed_bytes_cannot_inherit_identity(self):
        self.assertEqual(worker.parser_version("dane-weekly-pdf"), "official-v2:dane-weekly-v24")
        self.assertEqual(worker.asset_parser_version("dane-weekly-pdf", weekly.JUNE_2012_FONT_RUN_URL),
                         "official-v2:jun2012-native-font-run-v2:dane-weekly-v24")
        self.assertEqual(worker.asset_parser_version("dane-weekly-pdf", weekly.JUNE_2012_FONT_RUN_URL + "?other"),
                         "official-v2:dane-weekly-v24")
        words = [
            {"text": "anillo", "x0": 70.11, "x1": 89.20, "top": 458.87,
             "fontname": "Arial-BoldMT", "chars": [{}]},
            {"text": "s", "x0": 89.05, "x1": 92.85, "top": 458.87,
             "fontname": "ArialMT", "chars": [{}]},
        ]
        transform = weekly._audited_june_2012_font_runs
        self.assertEqual([w["text"] for w in transform(words, weekly.JUNE_2012_FONT_RUN_URL, SHA, 22, 600)],
                         ["anillos"])
        for url, sha in ((weekly.JUNE_2012_FONT_RUN_URL + "?other", SHA),
                         (weekly.JUNE_2012_FONT_RUN_URL, "0" * 64)):
            self.assertEqual(transform(words, url, sha, 22, 600), words)
        for field, value in (("top", 459.5), ("x0", 90.0), ("fontname", "Arial-BoldMT"),
                             ("text", "other")):
            changed = [dict(w) for w in words]
            changed[1][field] = value
            with self.assertRaisesRegex(ValueError, "font runs changed|glyph geometry changed"):
                transform(changed, weekly.JUNE_2012_FONT_RUN_URL, SHA, 22, 600)

    def test_market_ligature_requires_exact_original_page_column_and_glyphs(self):
        import pdfplumber

        with pdfplumber.open(ORIGINAL) as pdf:
            page = pdf.pages[18]
            words = page.extract_words(extra_attrs=["fontname", "size"], return_chars=True)
            repaired = weekly._audited_june_2012_font_runs(
                words, weekly.JUNE_2012_FONT_RUN_URL, SHA, 19, page.width
            )
            self.assertEqual(sum(w["text"] == "Frigorífico" for w in repaired), 29)
            self.assertEqual(sum(w["text"] == "Frigorífi" for w in repaired), 0)
            self.assertIs(weekly._audited_june_2012_font_runs(
                words, weekly.JUNE_2012_FONT_RUN_URL + "?alias", SHA, 19, page.width
            ), words)
            first = next(i for i, w in enumerate(words) if w["text"] == "Frigorífi")
            for side, field, value in (
                (0, "x0", 200), (0, "fontname", "OtherFont"),
                (1, "x0", words[first + 1]["x0"] + 1),
                (1, "text", "cos"),
            ):
                changed = [dict(w) for w in words]
                changed[first + side][field] = value
                with self.assertRaisesRegex(ValueError, "market glyph geometry changed"):
                    weekly._audited_june_2012_font_runs(
                        changed, weekly.JUNE_2012_FONT_RUN_URL, SHA, 19, page.width
                    )
            changed = [dict(w) for w in words]
            changed[first]["chars"] = [*words[first]["chars"][:-1],
                                         {**words[first]["chars"][-1], "text": "i"}]
            with self.assertRaisesRegex(ValueError, "market glyph geometry changed"):
                weekly._audited_june_2012_font_runs(
                    changed, weekly.JUNE_2012_FONT_RUN_URL, SHA, 19, page.width
                )


if __name__ == "__main__":
    unittest.main()

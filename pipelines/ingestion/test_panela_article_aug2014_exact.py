"""Durable source-bound tests for the Aug 2014 panela article tables."""
from __future__ import annotations

import hashlib
import json
import gzip
import unittest
from pathlib import Path

from . import panela_article_aug2014_exact as MODULE
from . import dane_weekly as WEEKLY
from .panela_article_aug2014_official import official_rows

DATA = Path(__file__).resolve().parent / "testdata" / "weekly_aug2014_panela_article"
ORIGINAL = DATA / (MODULE.ORIGINAL_SHA + ".pdf")
ORACLE = DATA / "visual-oracle.json"
ORACLE_SHA = "0e9ca0cddf5daaa67b13afaf6043ceb2e800c12056cb239ea396c9395739174a"
REGRESSION = Path(__file__).resolve().parent / "testdata" / "weekly_aug2014_regression"
REGRESSION_MANIFEST_SHA = "558e3f39d1e58516ff5f82865bfaf252931a4c80cb652fdd210dbe40cf5d8e08"


class August2014PanelaArticle(unittest.TestCase):
    def test_native_cells_match_independent_visual_oracle(self):
        body = ORIGINAL.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), MODULE.ORIGINAL_SHA)
        oracle_bytes = ORACLE.read_bytes()
        self.assertEqual(hashlib.sha256(oracle_bytes).hexdigest(), ORACLE_SHA)
        oracle = json.loads(oracle_bytes)
        cells = MODULE.extract(body, MODULE.SOURCE_URL)
        expected = []
        for table in oracle["tables"]:
            for row_no, (market, values) in enumerate(table["rows"], 1):
                for col_no, value in enumerate(values, 1):
                    start, end = oracle["weeks"][col_no - 1]
                    expected.append((table["page"], table["table"], row_no, col_no,
                        table["product"], market, start, end,
                        f"{value:,}".replace(",", "."), value))
        actual = [(cell["source_page"], cell["source_table"], cell["source_row"],
            cell["source_column"], cell["product_literal"], cell["market_literal"],
            cell["period_start"], cell["period_end"], cell["price_literal"],
            cell["price_cop_per_kg"]) for cell in cells]
        self.assertEqual(actual, expected)
        self.assertEqual([sum(c["source_table"] == n for c in cells) for n in (2, 3, 4)],
                         [30, 25, 5])

    def test_official_projection_keeps_article_basis_and_single_price(self):
        body = ORIGINAL.read_bytes()
        rows = official_rows(body, MODULE.SOURCE_URL)
        self.assertEqual(len(rows), 60)
        self.assertEqual({row["series"] for row in rows}, {"dane-panela-article"})
        self.assertEqual({row["basis"] for row in rows},
                         {"Precio por kilo publicado en artículo"})
        self.assertEqual({row["identity_dimensions"]["published_statistic"]
                          for row in rows}, {"published_single_price"})
        self.assertTrue(all(row["currency"] == "COP" and row["unit"] == "kg"
                            and row["min"] is None and row["max"] is None
                            for row in rows))

    def test_first_four_weekly_full_vectors_remain_unchanged(self):
        manifest_path = REGRESSION / "manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        self.assertEqual(hashlib.sha256(manifest_bytes).hexdigest(), REGRESSION_MANIFEST_SHA)
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest["parser_version"], "dane-weekly-v24")
        self.assertEqual(len(manifest["cases"]), 4)
        for case in manifest["cases"]:
            with self.subTest(source=case["source_sha256"]):
                source = REGRESSION / f"{case['source_sha256']}.pdf"
                body = source.read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), case["source_sha256"])
                vector_path = REGRESSION / case["fixture"]
                vector_bytes = vector_path.read_bytes()
                self.assertEqual(hashlib.sha256(vector_bytes).hexdigest(), case["fixture_sha256"])
                with gzip.open(vector_path, "rt", encoding="utf-8") as stream:
                    expected = [json.loads(line) for line in stream]
                actual = WEEKLY.parse_pdf(body, case["url"])
                self.assertEqual(len(actual), case["row_count"])
                self.assertEqual(sum(row["price"] is not None for row in actual), case["priced_rows"])
                self.assertEqual(sum(row["price"] is None for row in actual), case["review_rows"])
                self.assertEqual(actual, expected)

    def test_wrong_url_and_changed_original_fail_closed(self):
        body = ORIGINAL.read_bytes()
        with self.assertRaisesRegex(ValueError, "Exact Aug 2014 panela article original changed"):
            MODULE.extract(body, MODULE.SOURCE_URL + "?alias=1")
        changed = body[:-1] + bytes([body[-1] ^ 1])
        with self.assertRaisesRegex(ValueError, "Exact Aug 2014 panela article original changed"):
            MODULE.extract(changed, MODULE.SOURCE_URL)


if __name__ == "__main__":
    unittest.main(verbosity=2)

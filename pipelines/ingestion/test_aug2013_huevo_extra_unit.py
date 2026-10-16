"""Exact two-row unit correction witnessed by the archived Aug-2013 PDF."""

from copy import deepcopy
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from . import dane_weekly as weekly
from . import aug2013_huevo_extra_unit as unit_review
from .panela_article_aug2013_official import official_rows as panela_article_rows


SOURCE = Path(__file__).parent / "testdata/weekly_aug2013_page43/5a8af3b10894d3241907e149a39451d09488bf827d79b52d3789e5a8cfa60f4d.pdf"


class Aug2013HuevoExtraUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = SOURCE.read_bytes()
        cls.url = weekly.AUG2013_PAGE43_URL
        cls.document_id = hashlib.sha256(cls.body).hexdigest()
        if cls.document_id != unit_review.SOURCE_SHA:
            raise AssertionError("Aug-2013 original PDF bytes changed")
        cls.native_rows = weekly.parse_pdf(cls.body, cls.url)

    def test_only_the_two_narrative_witnessed_rows_gain_unit_prices(self):
        native = self.native_rows
        self.assertEqual((len(native), sum(row["price"] is not None for row in native)),
                         (4297, 4163))
        self.assertEqual(sum(row["price"] is None for row in native), 134)
        original_targets = {
            row["source_locator"]: deepcopy(row)
            for row in native if row["source_locator"] in {
                target["source_locator"] for target in unit_review.TARGETS
            }
        }
        self.assertEqual(set(original_targets), {
            target["source_locator"] for target in unit_review.TARGETS
        })

        weekly_rows = unit_review.apply(self.body, self.url, native)
        changed = [
            (before, after) for before, after in zip(native, weekly_rows)
            if before != after
        ]
        self.assertEqual(len(weekly_rows), len(native))
        self.assertEqual(
            {after["source_locator"] for _, after in changed},
            {target["source_locator"] for target in unit_review.TARGETS},
        )
        self.assertEqual(len(changed), 2)

        targets = {target["source_locator"]: target for target in unit_review.TARGETS}
        for before, after in changed:
            target = targets[after["source_locator"]]
            with self.subTest(locator=after["source_locator"]):
                self.assertEqual(before, original_targets[after["source_locator"]])
                self.assertEqual((after["product_id"], after["product_name"], after["market"]),
                                 ("huevo-rojo-extra", "Huevo rojo extra", target["market"]))
                self.assertEqual((after["date"], after["period_start"], after["source_page"]),
                                 ("2013-08-23", "2013-08-17", 30))
                self.assertEqual((after["unit"], after["price"], after["min"], after["max"]),
                                 ("unit", target["literal"], target["literal"], target["literal"]))
                details = after["details"]
                self.assertEqual(details["literal_unit_heading"], "Pesos por kilogramo")
                evidence = details["unit_exception_evidence"]
                self.assertEqual((evidence["source_url"], evidence["document_id"]),
                                 (self.url, self.document_id))
                self.assertEqual(evidence["table_unit_heading_literal"], "Pesos por kilogramo")

        self.assertEqual(sum(row["price"] is not None for row in weekly_rows), 4165)
        self.assertEqual(sum(row["price"] is None for row in weekly_rows), 132)
        # The source's printed table heading stays literal on the repaired rows.
        self.assertTrue(all(
            row["details"]["literal_unit_heading"] == "Pesos por kilogramo"
            for row in weekly_rows if row["source_locator"] in targets
        ))

    def test_normal_weekly_dispatch_keeps_the_60_row_article_separate(self):
        weekly_rows = unit_review.apply(self.body, self.url, self.native_rows)
        article_rows = panela_article_rows(self.body, self.url)
        self.assertEqual(len(article_rows), 60)
        with patch.object(weekly, "parse_pdf", return_value=self.native_rows), patch(
            "pipelines.ingestion.panela_article_aug2013_official.official_rows",
            return_value=article_rows,
        ):
            parsed = weekly.parse(self.body, self.url, "dane-weekly-pdf")

        self.assertEqual(parsed, weekly_rows + article_rows)
        self.assertEqual((len(parsed), sum(row["price"] is not None for row in parsed),
                          sum(row["price"] is None for row in parsed)),
                         (4357, 4225, 132))
        self.assertEqual(sum(row["series"] == "dane-weekly" and row["price"] is not None
                             for row in parsed), 4165)
        self.assertEqual(sum(row["series"] == "dane-panela-article" and row["price"] is not None
                             for row in parsed), 60)

    def test_wrong_source_locator_day_or_numeric_tuple_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "source changed"):
            unit_review.apply(self.body, self.url + "?alias", self.native_rows)
        with self.assertRaisesRegex(ValueError, "source changed"):
            unit_review.apply(self.body + b"changed", self.url, self.native_rows)

        mutations = {
            "source locator": ("source_locator", "PDF page 30,table 1,column 2,line 999"),
            "printed day": ("date", "2013-08-22"),
            "market identity": ("market", "Cali, Cavasa"),
            "numeric minimum": ("min", 222.0),
            "numeric maximum": ("max", 222.0),
            "numeric source mean": ("details.literal_mean", 222.0),
            "numeric existing price": ("price", 222.0),
        }
        for label, (field, value) in mutations.items():
            target_locator = unit_review.TARGETS[0]["source_locator"]
            mutated = deepcopy(self.native_rows)
            row = next(row for row in mutated if row["source_locator"] == target_locator)
            if field.startswith("details."):
                row["details"][field.split(".", 1)[1]] = value
            else:
                row[field] = value
            with self.subTest(control=label):
                with self.assertRaisesRegex(ValueError, "tuple changed or is ambiguous"):
                    unit_review.apply(self.body, self.url, mutated)


if __name__ == "__main__":
    unittest.main(verbosity=2)

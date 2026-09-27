"""Seasonal comparisons must keep compatible units and actual monthly evidence."""

import unittest
from datetime import date

from .seasonality import derive


class SeasonalEvidence(unittest.TestCase):
    def test_unit_prices_cannot_replace_kg_prices_and_each_month_retains_its_document(
        self,
    ):
        rows = [
            ("p", "m", 2025, month, 1000 + month, str(month), "Sheet!row 8", "kg")
            for month in range(1, 13)
        ]
        rows += [
            ("p", "m", 2025, month, 90, "egg", "Sheet!row 9", "unit")
            for month in range(1, 13)
        ]
        result, review = derive(rows, [])
        self.assertFalse(review)
        self.assertEqual(result[0][3], list(range(1001, 1013)))
        self.assertEqual(result[0][6], [[str(month)] for month in range(1, 13)])

    def test_conflicting_or_incomplete_years_are_reviewed_without_inventing_months(
        self,
    ):
        rows = [
            ("p", "m", 2025, month, 1000, "a", "row 1", "kg") for month in range(1, 13)
        ]
        rows.append(("p", "m", 2025, 1, 1500, "b", "row 2", "kg"))
        rows += [
            ("q", "m", 2025, month, 500, "c", "row 3", "kg") for month in range(1, 12)
        ]
        valid, review = derive(rows, [])
        self.assertEqual(valid, [])
        self.assertEqual(len(review), 2)

    def test_fnc_mean_uses_reported_days_only_and_preserves_multiple_originals(self):
        rows = [(date(2025, month, 1), 125000, "a") for month in range(1, 13)]
        rows.append((date(2025, 1, 2), 250000, "b"))
        valid, review = derive([], rows)
        self.assertFalse(review)
        self.assertEqual(valid[0][3], [1500] + [1000] * 11)
        self.assertEqual(valid[0][6][0], ["a", "b"])
        self.assertIn("2 published daily references", valid[0][5][0])


if __name__ == "__main__":
    unittest.main()

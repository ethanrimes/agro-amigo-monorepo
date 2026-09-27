"""Seasonal comparisons must keep compatible units and actual monthly evidence."""

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from . import seasonality, worker
from .resumable_inputs import WorkDeferred
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


class SeasonalBudget(unittest.TestCase):
    def test_shorter_remaining_run_deadline_wins_over_explicit_caller_deadline(self):
        token = worker.RUN_DEADLINE.set(5)
        self.addCleanup(worker.RUN_DEADLINE.reset, token)
        db = MagicMock()
        with (
            patch.object(seasonality, "time", SimpleNamespace(monotonic=Mock(side_effect=[0, 5]))),
            self.assertRaises(WorkDeferred),
        ):
            seasonality.refresh(db, 2026, deadline=1000)
        db.execute.assert_not_called()

    def test_seasonal_deferral_is_reported_and_fresh_source_still_runs(self):
        db = MagicMock()

        def execute(sql, *args):
            result = MagicMock()
            result.fetchone.return_value = None if "summary ? 'auxiliary_finished_at'" in sql else (True,)
            return result

        db.execute.side_effect = execute
        source = ("https://example.invalid/fresh-price.xlsx", "daily", None)
        with (
            patch.object(worker, "connect") as connect,
            patch.object(worker, "refresh_catalog", return_value=0),
            patch.object(worker, "refresh_trm", return_value=1),
            patch.object(worker, "refresh_seasons", side_effect=WorkDeferred("Seasonal complete-year batches deferred")),
            patch("pipelines.ingestion.queue_plan.daily_candidates", return_value=[source]),
            patch("pipelines.ingestion.queue_plan.backfill_candidates", return_value=[]),
            patch.object(worker, "process_asset", return_value=12) as process,
            patch("pipelines.ingestion.retained_replays.drain", return_value={}),
            patch("pipelines.ingestion.ocr.drain", return_value={}),
        ):
            connect.return_value.__enter__.return_value = db
            result = worker.run("backfill", limit=4, time_budget=2100)
        process.assert_called_once_with(db, *source)
        self.assertEqual(result["assets"], 1)
        self.assertEqual(result["rows"], 12)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["deferred"], [{"source": "seasonality", "reason": "Seasonal complete-year batches deferred"}])
        self.assertNotIn("auxiliary_finished_at", result)
        statuses = [c.args[1][0] for c in db.execute.call_args_list if c.args[0].startswith("UPDATE ingestion_run SET status=%s")]
        self.assertEqual(statuses, ["partial"])


if __name__ == "__main__":
    unittest.main()

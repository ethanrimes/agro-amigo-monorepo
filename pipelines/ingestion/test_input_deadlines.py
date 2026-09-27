"""Budget checks must stop native input parsing without publishing partial work."""

import unittest
from unittest.mock import MagicMock, patch

from . import inputs, resumable_inputs, worker


class InputDeadlineTests(unittest.TestCase):
    def test_expired_budget_does_not_start_validation(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        with (
            patch.object(resumable_inputs.time, "monotonic", return_value=10),
            patch.object(inputs, "parse_inputs") as parse,
            self.assertRaisesRegex(resumable_inputs.WorkDeferred, "before starting"),
        ):
            resumable_inputs.publish(db, b"fixture", "doc", "inputs", None, deadline=10)
        parse.assert_not_called()
        db.transaction.assert_not_called()
        self.assertEqual(db.execute.call_count, 1)  # Read checkpoints only.

    def test_full_validation_budget_closes_generator_without_checkpointing(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        state = {"consumed": 0, "closed": False, "now": 0}

        def rows(_):
            try:
                for number in range(5000):
                    state["consumed"] += 1
                    if number == 999:
                        state["now"] = 10
                    yield (number,)
            finally:
                state["closed"] = True

        with (
            patch.object(inputs, "parse_inputs", side_effect=rows) as parse,
            patch.object(
                resumable_inputs.time, "monotonic", side_effect=lambda: state["now"]
            ),
            patch.object(worker, "save_rows") as save,
            patch.object(inputs, "project_inputs") as project,
            self.assertRaisesRegex(
                resumable_inputs.WorkDeferred, "validation exceeded"
            ),
        ):
            resumable_inputs.publish(db, b"fixture", "doc", "inputs", None, deadline=10)
        self.assertEqual(state["consumed"], 1000)
        self.assertTrue(state["closed"])
        parse.assert_called_once_with(b"fixture")
        save.assert_not_called()
        project.assert_not_called()
        db.transaction.assert_not_called()
        self.assertEqual(db.execute.call_count, 1)

    def test_completed_native_batches_still_check_budget_before_skipping(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [
            ("validated", 2),
            ("native-batch:000001", 1),
            ("native-batch:000002", 1),
        ]
        state = {"consumed": 0, "closed": False}

        def rows(_):
            try:
                for number in range(2):
                    state["consumed"] += 1
                    yield (number,)
            finally:
                state["closed"] = True

        with (
            patch.object(inputs, "parse_inputs", side_effect=rows) as parse,
            patch.object(resumable_inputs, "BATCH_SIZE", 1),
            patch.object(resumable_inputs.time, "monotonic", return_value=10),
            patch.object(worker, "save_rows") as save,
            patch.object(inputs, "project_inputs") as project,
            self.assertRaisesRegex(
                resumable_inputs.WorkDeferred, "source rows will resume"
            ),
        ):
            resumable_inputs.publish(db, b"fixture", "doc", "inputs", None, deadline=10)
        self.assertEqual(state["consumed"], 1)
        self.assertTrue(state["closed"])
        parse.assert_called_once_with(b"fixture")
        save.assert_not_called()
        project.assert_not_called()
        db.transaction.assert_not_called()
        self.assertEqual(db.execute.call_count, 1)


if __name__ == "__main__":
    unittest.main()

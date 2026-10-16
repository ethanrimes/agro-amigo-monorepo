"""Keep the exact retained-source repair inside its capped queue lane."""

import unittest

from pipelines.ingestion import queue_plan


AUG = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Semana_20ago_23ago_2013.pdf",
    "dane-weekly-pdf",
    queue_plan.date(2013, 8, 23),
)
MAY = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Semana_18may_24may_2013.pdf",
    "dane-weekly-pdf",
    queue_plan.date(2013, 5, 24),
)


class Aug2013RepairSlotTests(unittest.TestCase):
    def test_exact_article_uses_existing_cap_and_keeps_nonweekly_rotation(self):
        rows = [(f"https://example.test/{i}", kind, queue_plan.date(2020, 1, i))
                for i, kind in enumerate(("inputs-pdf", "daily", "city-zip", "milk-pdf", "coffee-pdf"), 1)]
        selected = queue_plan._with_aug2013_repair_slot(rows, AUG, 5)
        self.assertEqual(selected, [AUG, *rows[:4]])
        self.assertEqual(len(selected), 5)

    def test_existing_weekly_repair_keeps_priority_and_cap(self):
        rows = [MAY, ("https://example.test/city", "city-zip", queue_plan.date(2020, 1, 1))]
        selected = queue_plan._with_aug2013_repair_slot(rows, AUG, 5)
        self.assertEqual(selected[:2], [MAY, AUG])

    def test_full_lane_preserves_may_and_exact_aug_then_drops_only_tail(self):
        tail = ("https://example.test/tail", "coffee-pdf", queue_plan.date(2020, 1, 5))
        rows = [MAY] + [
            (f"https://example.test/{i}", kind, queue_plan.date(2020, 1, i))
            for i, kind in enumerate(("inputs-pdf", "city-zip", "milk-pdf", "daily", "coffee-pdf"), 1)
        ]
        self.assertEqual(len(rows), 6)
        selected = queue_plan._with_aug2013_repair_slot(rows + [tail], AUG, 7)
        self.assertEqual(selected[:2], [MAY, AUG])
        self.assertEqual(len(selected), 7)
        self.assertNotIn(tail, selected)

    def test_weekly_at_last_full_lane_slot_is_promoted_with_aug(self):
        rows = [
            (f"https://example.test/{i}", kind, queue_plan.date(2020, 1, i))
            for i, kind in enumerate(("inputs-pdf", "city-zip", "milk-pdf", "daily"), 1)
        ] + [MAY]
        selected = queue_plan._with_aug2013_repair_slot(rows, AUG, 5)
        self.assertEqual(selected, [MAY, AUG, *rows[:3]])
        self.assertEqual(len(selected), 5)

    def test_single_slot_preserves_existing_weekly_repair(self):
        self.assertEqual(queue_plan._with_aug2013_repair_slot([MAY], AUG, 1), [MAY])

    def test_unqualified_or_already_selected_article_does_not_change_lane(self):
        rows = [("https://example.test/city", "city-zip", queue_plan.date(2020, 1, 1))]
        self.assertEqual(queue_plan._with_aug2013_repair_slot(rows, None, 5), rows)
        self.assertEqual(queue_plan._with_aug2013_repair_slot([AUG], AUG, 5), [AUG])


if __name__ == "__main__":
    unittest.main()

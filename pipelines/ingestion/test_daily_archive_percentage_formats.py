"""Daily ZIP decoration must preserve the common native percentage semantics."""

import copy
import unittest
from datetime import date

from . import daily_archives, daily_recovery
from .test_daily_percentage_formats import matrix_bytes


class ArchivePercentageFormats(unittest.TestCase):
    def decorate(self, values):
        data = matrix_bytes(values)
        parsed = daily_recovery.parse_daily(data, date(2021, 12, 17))
        parsed["rows"][0][-1]["parent_evidence"] = "immutable ZIP member"
        original = copy.deepcopy(parsed)
        decorated = daily_archives._daily_changes(data, parsed)
        self.assertEqual(parsed, original, "Decoration cannot mutate parsed evidence")
        for before, after in zip(original["rows"], decorated["rows"]):
            self.assertEqual(before[:8], after[:8])
            for key, value in before[-1].items():
                self.assertEqual(after[-1][key], value)
            self.assertEqual(
                after[-1]["container_parser_version"], daily_archives.VERSION
            )
            self.assertEqual(after[-1]["literal_change"], before[-1]["raw_change"])
            self.assertEqual(after[-1]["extraction_method"], "native-workbook-cells")
        self.assertEqual(decorated["reviews"], original["reviews"])
        self.assertEqual(decorated["date_resolutions"], original["date_resolutions"])
        return decorated["rows"]

    def test_negative_and_zero_use_their_native_sections(self):
        rows = self.decorate(
            [(-0.81, "0.00%;0.00"), (0, "0%;0%;0.00"), (0.1, "0.00%;0.00")]
        )
        self.assertEqual([row[7] for row in rows], [-0.81, 0, 10])
        self.assertEqual([row[-1]["change_scale"] for row in rows], [1, 1, 100])

    def test_quoted_and_escaped_percent_in_selected_sections_are_literal(self):
        rows = self.decorate(
            [(-0.81, '0.00%;0.00"%"'), (-0.81, r"0.00%;0.00\%"), (0, '0%;0%;0"%"')]
        )
        self.assertEqual([row[7] for row in rows], [-0.81, -0.81, 0])
        self.assertEqual([row[-1]["change_scale"] for row in rows], [1, 1, 1])

    def test_unknown_conditional_format_remains_review_in_archive_adapter(self):
        good = matrix_bytes([(0.1, "0%"), (0.1, "0%"), (0.1, "0%")])
        parsed = daily_recovery.parse_daily(good, date(2021, 12, 17))
        conditional = matrix_bytes([(0.1, "[<1]0%;0"), (0.1, "0%"), (0.1, "0%")])
        with self.assertRaisesRegex(ValueError, "Conditional"):
            daily_archives._daily_changes(conditional, parsed)

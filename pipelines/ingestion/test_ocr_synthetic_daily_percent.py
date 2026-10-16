"""Actual two-reading Gemini fixture exercises OCR-only printed percent typing."""

import copy
import json
import unittest
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from unittest.mock import patch

from . import ocr, worker

FIXTURE = Path(__file__).parent / "testdata/ocr_synthetic_daily_20260904.json"
URL = "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSADiario-04sep2026.xlsx"
LOCATOR = "Boletín diario!image 1,anchor row 1,col 1"


class SourceOnlyStub:
    def execute(self, *_args, **_kwargs):
        return self

    def fetchone(self):
        return URL, "2026-09-04"

    def transaction(self):
        return nullcontext()


class SyntheticDailyProviderReadings(unittest.TestCase):
    def test_real_two_readings_preserve_agreement_review_gate(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(fixture["fixture_source_sha256"],
                         "4abcd3aa9402a3572e0d7899ce93fdef9e885cbe8fb02a512fdcb38195238e55")
        self.assertEqual(fixture["provider_model"], "gemini-3.5-flash")
        first, second = fixture["provider_readings"]
        self.assertEqual(first["tables"], second["tables"])
        self.assertEqual([len(first["review_notes"]), len(second["review_notes"])], [2, 0])
        self.assertFalse(ocr.compare_readings(first, second))

    def test_both_literal_readings_type_all_six_source_changes_without_db_writes(self):
        readings = json.loads(FIXTURE.read_text())["provider_readings"]
        expected = {
            ("Cebolla junca", "Bogotá, Corabastos"): (3125, 22),
            ("Cebolla junca", "Bucaramanga, Centroabastos"): (1719, -4),
            ("Cebolla junca", "Medellín, CMA"): (2175, 4),
            ("Limón Tahití", "Bogotá, Corabastos"): (2500, 7),
            ("Limón Tahití", "Bucaramanga, Centroabastos"): (2250, 2),
            ("Limón Tahití", "Medellín, CMA"): (2900, 17),
        }
        for index, reading in enumerate(readings):
            with self.subTest(reading=index):
                captured = []
                with (
                    patch.object(worker, "save_rows", side_effect=lambda _db, _did, rows, captured=captured: captured.extend(rows)),
                    patch.object(worker, "project", return_value=None) as project,
                ):
                    self.assertTrue(ocr.publish_workbook_reading(
                        SourceOnlyStub(), "synthetic-only", LOCATOR, "daily", reading
                    ))
                project.assert_called_once()
                self.assertEqual(len(captured), len(expected))
                for row in captured:
                    key = (row[3], row[4])
                    self.assertIn(key, expected)
                    self.assertEqual(row[2], date(2026, 9, 4))
                    self.assertEqual(row[5], "kg")
                    self.assertEqual((row[6], row[7]), expected[key])
                    self.assertTrue(row[0].startswith(LOCATOR + "; verified OCR; "))
                    self.assertEqual(row[-1]["change_percent_encoding"], "printed_ocr_percent")
                    self.assertEqual(row[-1]["extraction"], "verified-image-ocr")

    def test_missing_percent_mark_is_not_inferred_from_ocr_digits(self):
        reading = copy.deepcopy(json.loads(FIXTURE.read_text())["provider_readings"][1])
        for row in reading["tables"][0]:
            if row[0] == "Cebolla junca":
                row[2] = "22"
                break
        captured = []
        with (
            patch.object(worker, "save_rows", side_effect=lambda _db, _did, rows: captured.extend(rows)),
            patch.object(worker, "project", return_value=None),
        ):
            self.assertTrue(ocr.publish_workbook_reading(
                SourceOnlyStub(), "synthetic-only", LOCATOR, "daily", reading
            ))
        cebolla = next(row for row in captured if row[3:5] == ["Cebolla junca", "Bogotá, Corabastos"])
        self.assertEqual(cebolla[6], 3125)
        self.assertIsNone(cebolla[7])
        self.assertEqual(cebolla[-1]["change_percent_encoding"], "unverified_ocr_percent")


if __name__ == "__main__":
    unittest.main()

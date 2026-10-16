"""Exact Jan 25 source and paired OCR projection regressions (no database/provider)."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from . import city_exact_source_dispatch_v44_b as dispatch
from . import city_jan25_ocr_whole as whole
from . import worker

DATA = Path(__file__).parent / "testdata" / "city_armenia_20240125_ocr"
ZIP = DATA / f"{whole.PARENT}.zip"
READINGS_SNAPSHOT = DATA / "cached_paired_readings.json"


def _readings():
    readings = {}
    for image_id, version, reading, result, *_ in json.loads(READINGS_SNAPSHOT.read_text()):
        readings.setdefault(image_id, {})[reading] = result
    return readings


class Jan25PairedProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = whole._manifest_bytes()
        cls.readings = _readings()
        cls.output = whole.project_source(ZIP.read_bytes(), cls.readings, cls.manifest)

    def test_exact_source_pins_full_cohort_and_all_seventeen_fields(self):
        self.assertEqual(whole.URL, "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-25ene2024.zip")
        self.assertEqual(len(self.manifest["zip_members"]), 30)
        self.assertEqual(len(self.manifest["pages"]), 33)
        self.assertEqual(sum(map(len, self.readings.values())), 66)
        self.assertEqual(len(self.output), 15)
        for did, rows in self.output.items():
            self.assertTrue(rows)
            self.assertTrue(all(len(row) == 17 for row in rows))
            spec = self.manifest["children"][did]
            self.assertEqual(len(rows), spec["expected_row_count"])
            self.assertEqual(whole._row_sha(rows), spec["expected_rows_sha256"])
        self.assertEqual(sum(len(self.output[did]) for did in self.manifest["publish_member_ids"]), 740)

    def test_measurement_date_and_two_round_compound_packaging_are_preserved(self):
        penol = self.output[self.manifest["date_mismatch_member"]]
        self.assertEqual(len(penol), 10)
        self.assertTrue(all(row[1].isoformat() == "2024-01-23" for row in penol))
        self.assertEqual(self.manifest["parent_publication_date"], "2024-01-25")
        cali_did = next(did for did, spec in self.manifest["children"].items()
                        if spec["entry"] == "Cali, Cavasa 25-1-2024.pdf")
        cali = self.output[cali_did]
        kiwi = [row for row in cali if row[2] == "kiwi"]
        self.assertEqual([(row[9], row[11], row[12]) for row in kiwi],
                         [(1, 140000, 150000), (2, 150000, 150000)])
        self.assertTrue(any(row[6] == "Caja de cartón" for row in cali))

    def test_numeric_and_unreviewed_printed_date_changes_reject(self):
        altered = copy.deepcopy(self.readings)
        image_id = next(image for image, spec in self.manifest["pages"].items()
                        if spec["normalized_differences"].get("presentation"))
        altered[image_id][0]["tables"][0][10][3] = "999.999"
        with self.assertRaisesRegex(ValueError, "OCR pair hash differs"):
            whole.project_source(ZIP.read_bytes(), altered, self.manifest)

        altered = copy.deepcopy(self.readings)
        image_id = next(image for image, spec in self.manifest["pages"].items()
                        if spec["normalized_differences"].get("presentation"))
        altered[image_id][0]["text"] = altered[image_id][0]["text"].replace(
            "25 de Enero de 2024", "24 de Enero de 2024", 1)
        with self.assertRaisesRegex(ValueError, "OCR pair hash differs"):
            whole.project_source(ZIP.read_bytes(), altered, self.manifest)

    def test_worker_priority_and_dispatch_are_exact_source_only(self):
        self.assertEqual(worker.URL_SOURCE_REPAIR_VERSIONS[whole.URL],
                         ("city-zip", ":armenia-jan2024-ocr-whole-v1:jan25-paired-review-v1"))
        self.assertEqual(worker.asset_parser_version("city-zip", whole.URL), whole.VERSION)
        self.assertIn("pipelines/ingestion/city_jan25_ocr_whole.py", worker.RELEASE_FILES)
        self.assertIn("pipelines/ingestion/jan25_paired_projection_manifest.json", worker.RELEASE_FILES)
        unrelated = whole.URL + "?different-source"
        self.assertNotIn(unrelated, worker.URL_SOURCE_REPAIR_VERSIONS)
        self.assertIsNone(dispatch.maybe_publish_exact_city_zip(None, unrelated, b"", "0" * 64))


if __name__ == "__main__":
    unittest.main()

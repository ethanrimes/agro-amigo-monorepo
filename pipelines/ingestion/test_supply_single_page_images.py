"""Portable original-backed image Cuadro 1 parity and private SQL publication."""
import copy
import csv
import hashlib
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from . import supply_single_page_images as adapter


FIXTURES = Path(__file__).with_name("testdata")
CASES = (
    ("sep2021", "05abc2c0ccfce9a42f11805c1500fc81c8b8e10bdf025b4469569b06d98a5121", 4, (527152, 565000, 7.18)),
    ("dec2020", "a978f0dcc210e831c2e3676b214448c121b846fd9152fdd88da5d1db5bd4a006", 3, (530047, 550051, 3.77)),
    ("jan2021-first", "2c298078437323885a5104ae6c902ea84e597bf4c65449b00da3e2961cea530d", 3, (278749, 239811, -13.97)),
)


def source(case):
    key = case[0]
    original = (FIXTURES / f"supply-image-only-{key}.pdf").read_bytes()
    assert hashlib.sha256(original).hexdigest() == case[1]
    with (FIXTURES / f"supply-image-only-{key}-visual.tsv").open() as stream:
        literal = list(csv.reader(stream, delimiter="\t"))[1:]
    assert len(literal) == 30 and literal[-1][:2] == ["TOTAL", ""]
    spec = adapter.SOURCES[case[1]]
    reading = {"text": "Cuadro 1", "tables": [[
        ["Ciudad", "Central", spec.prior_header, spec.current_header, "Variación (%)"],
        *literal,
    ]], "review_notes": []}
    return original, reading


class ExactImageSources(unittest.TestCase):
    def test_all_270_independent_literal_cells_and_original_frames(self):
        for case in CASES:
            with self.subTest(source=case[0]):
                original, reading = source(case)
                rows = adapter.paired(original, case[1], case[2],
                                      [reading, copy.deepcopy(reading)])
                self.assertEqual(len(rows), 90)
                self.assertEqual(len({r["name"] for r in rows}), 30)
                with (FIXTURES / f"supply-image-only-{case[0]}-visual.tsv").open() as stream:
                    printed = list(csv.reader(stream, delimiter="\t"))[1:]
                for row_index, cells in enumerate(printed):
                    expected_name = "TOTAL" if cells[0] == "TOTAL" else cells[0] + ", " + cells[1]
                    for column in range(3):
                        emitted = rows[row_index * 3 + column]
                        self.assertEqual(emitted["name"], expected_name)
                        self.assertEqual(emitted["details"]["literal_value"], cells[column + 2])
                        self.assertEqual(emitted["details"]["value"],
                                         float(cells[column + 2].rstrip("%").replace(".", "").replace(",", ".")))
                self.assertEqual([r["details"]["value"] for r in rows[-3:]], list(case[3]))
                self.assertEqual({r["details"]["frequency"] for r in rows},
                                 {"first_fortnight" if case[0] == "jan2021-first" else "monthly"})
                self.assertEqual(rows[0]["details"]["literal_value"], reading["tables"][0][1][2])
                self.assertTrue(all("printed-row-v2" in r["source_locator"] for r in rows))
                self.assertTrue(all(r["details"]["non_additive"] for r in rows))
                self.assertEqual(rows[-3]["details"]["aggregation_level"], "reported_markets_total")
                if case[0] == "jan2021-first":
                    self.assertEqual({r["observed_on"] for r in rows},
                                     {date(2020, 12, 15), date(2021, 1, 15)})
                if case[0] == "sep2021":
                    self.assertIn("imputar", rows[22 * 3]["details"]["source_note"])

    def test_retained_real_sep2021_pair_accepts_only_noncell_footnote_crop(self):
        import json
        original, _ = source(CASES[0])
        retained = json.loads((FIXTURES / "supply-image-only-sep2021-retained-ocr-pair.json").read_text())
        self.assertEqual(retained["document_id"], CASES[0][1])
        readings = retained["readings"]
        self.assertEqual(len(readings), 2)
        with (FIXTURES / "supply-image-only-sep2021-visual.tsv").open() as stream:
            literal = list(csv.reader(stream, delimiter="\t"))[1:]
        for item in readings:
            self.assertEqual(item["tables"][0][1:], literal)
            self.assertEqual(len(item["review_notes"]), 1)
        rows = adapter.paired(original, CASES[0][1], 4, readings)
        self.assertEqual(len(rows), 90)
        self.assertEqual([r["details"]["value"] for r in rows[-3:]], [527152, 565000, 7.18])
        self.assertEqual(rows[22 * 3]["details"]["source_note"], adapter.SEPTEMBER_POPAYAN_IMPUTATION)
        # Raw provider uncertainty evidence is retained, not rewritten or dropped.
        self.assertEqual(readings, retained["readings"])
        for label in ("unknown note", "altered footnote", "missing cell", "numeric uncertainty"):
            changed = copy.deepcopy(readings[1])
            if label == "unknown note": changed["review_notes"] = ["The last tonnes cell is unreadable."]
            elif label == "altered footnote": changed["review_notes"] = ["The footnote at the bottom of the page is cropped; price unclear."]
            elif label == "missing cell": changed["tables"][0].pop(4)
            else: changed["tables"][0][1][3] = "?"
            with self.subTest(label=label), self.assertRaises(ValueError):
                adapter.paired(original, CASES[0][1], 4, [readings[0], changed])
        with self.assertRaises(ValueError):
            adapter.paired(original, CASES[0][1], 3, readings)
        with self.assertRaises(ValueError):
            adapter.paired(original + b"modified", CASES[0][1], 4, readings)

    def test_wrong_source_period_header_market_incomplete_and_uncertain_reject(self):
        for case in CASES:
            original, reading = source(case)
            variants = []
            wrong = copy.deepcopy(reading); wrong["tables"][0][0][3] = "Octubre 2021 (t)"; variants.append(wrong)
            wrong = copy.deepcopy(reading); wrong["tables"][0][1][1] = "Other market"; variants.append(wrong)
            wrong = copy.deepcopy(reading); wrong["tables"][0].pop(5); variants.append(wrong)
            wrong = copy.deepcopy(reading); wrong["tables"][0][1][2] = "?"; variants.append(wrong)
            wrong = copy.deepcopy(reading); wrong["tables"][0][-1][3] = "999.999"; variants.append(wrong)
            wrong = copy.deepcopy(reading); wrong["review_notes"] = ["uncertain"]; variants.append(wrong)
            wrong = copy.deepcopy(reading); wrong["tables"][0][1][4] = "99,99%"; variants.append(wrong)
            for index, variant in enumerate(variants):
                with self.subTest(source=case[0], mutation=index), self.assertRaises(ValueError):
                    adapter.paired(original, case[1], case[2], [reading, variant])
            with self.subTest(source=case[0]), self.assertRaises(ValueError):
                adapter.page_rows(original + b"changed", case[1], case[2], reading)
            with self.subTest(source=case[0]), self.assertRaises(ValueError):
                adapter.page_rows(original, case[1], case[2] + 1, reading)

    def test_two_readings_must_agree_on_printed_literal_not_just_number(self):
        original, reading = source(CASES[0])
        second = copy.deepcopy(reading)
        second["tables"][0][1][2] = "9317"
        with self.assertRaises(ValueError):
            adapter.paired(original, CASES[0][1], CASES[0][2], [reading, second])


@unittest.skipUnless(os.environ.get("AGRO_DAILY_ZIP_POSTGRES_TEST") == "1", "Private PostgreSQL opt-in")
class ExactImagePublication(unittest.TestCase):
    from .test_daily_archives import ArchivePublicationPostgres as _Fixture
    setUp = _Fixture.setUp

    def test_each_exact_original_atomic_90_rows_and_cached_no_provider(self):
        from psycopg.types.json import Jsonb
        from . import ocr, worker
        for table in ("source_ocr_task", "source_ocr_result"):
            self.db.execute(f"CREATE TEMP TABLE {table}(LIKE public.{table} INCLUDING ALL)")
        for case in CASES:
            with self.subTest(source=case[0]):
                original, reading = source(case)
                did = worker.archive(self.db, adapter.SOURCES[case[1]].url,
                                     original, "supply-reference-pdf", None)
                self.db.execute("INSERT INTO ingestion_asset(url,kind,document_id,status,records) "
                    "VALUES(%s,'supply-reference-pdf',%s,'review',0)",
                    (adapter.SOURCES[case[1]].url, did))
                from . import supply_period_summaries as supply
                self.assertEqual(supply.queue_image_only_market_pages(self.db, original, did), [case[2]])
                image_id = self.db.execute("SELECT image_id FROM source_ocr_task WHERE document_id=%s "
                    "AND source_locator=%s", (did, adapter.task_locator(did))).fetchone()[0]
                for number in (0, 1):
                    self.db.execute("INSERT INTO source_ocr_result(image_id,version,reading,result) "
                        "VALUES(%s,%s,%s,%s)", (image_id, ocr.VERSION, number, Jsonb(reading)))
                self.assertEqual(supply.publish_verified_ocr(self.db, original, did, case[2],
                    [reading, copy.deepcopy(reading)]), 90)
                self.assertEqual(adapter.publish_verified(self.db, original, did, case[2],
                    [reading, copy.deepcopy(reading)]), 90)
                self.assertEqual(self.db.execute("SELECT count(*) FROM input_reference_row WHERE document_id=%s",
                    (did,)).fetchone()[0], 90)
                self.assertEqual(self.db.execute("SELECT status,records FROM ingestion_asset WHERE document_id=%s",
                    (did,)).fetchone(), ("complete", 90))
                self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id=%s",
                    (did,)).fetchone(), ("published",))
                self.assertEqual(bytes(self.db.execute("SELECT content FROM source_document WHERE id=%s",
                    (did,)).fetchone()[0]), original)
                with patch.object(ocr, "transcribe", side_effect=AssertionError("No provider on cached replay")):
                    self.assertEqual(len(adapter.cached_rows(self.db, original, did,
                        adapter.SOURCES[did].expected_day)), 90)
                    self.assertEqual(supply.publish(self.db, original, did,
                        "supply-reference-pdf", adapter.SOURCES[did].expected_day), (90, []))
                with self.assertRaises(ValueError):
                    adapter.cached_rows(self.db, original, did, date(2026, 1, 1))
        for table in ("historical_price", "daily_price", "regional_price", "official_price_quote"):
            self.assertEqual(self.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)

    def test_retained_real_sep2021_pair_publishes_only_full_source_table(self):
        import json
        from psycopg.types.json import Jsonb
        from . import ocr, worker, supply_period_summaries as supply
        original, _ = source(CASES[0])
        did = worker.archive(self.db, adapter.SOURCES[CASES[0][1]].url,
                             original, "supply-reference-pdf", None)
        self.db.execute("INSERT INTO ingestion_asset(url,kind,document_id,status,records) "
            "VALUES(%s,'supply-reference-pdf',%s,'review',0)",
            (adapter.SOURCES[did].url, did))
        for table in ("source_ocr_task", "source_ocr_result"):
            self.db.execute(f"CREATE TEMP TABLE {table}(LIKE public.{table} INCLUDING ALL)")
        self.assertEqual(supply.queue_image_only_market_pages(self.db, original, did), [4])
        image_id = self.db.execute("SELECT image_id FROM source_ocr_task WHERE document_id=%s",
                                   (did,)).fetchone()[0]
        retained = json.loads((FIXTURES / "supply-image-only-sep2021-retained-ocr-pair.json").read_text())
        for number, reading in enumerate(retained["readings"]):
            self.db.execute("INSERT INTO source_ocr_result(image_id,version,reading,result) VALUES(%s,%s,%s,%s)",
                            (image_id, ocr.VERSION, number, Jsonb(reading)))
        self.assertEqual(supply.publish_verified_ocr(self.db, original, did, 4, retained["readings"]), 90)
        self.assertEqual(self.db.execute("SELECT count(*) FROM input_reference_row WHERE document_id=%s",
                         (did,)).fetchone()[0], 90)
        self.assertEqual(self.db.execute("SELECT status,records FROM ingestion_asset WHERE document_id=%s",
                         (did,)).fetchone(), ("complete", 90))
        self.assertEqual(self.db.execute("SELECT result->'review_notes' FROM source_ocr_result "
                         "WHERE image_id=%s AND reading=0", (image_id,)).fetchone()[0],
                         retained["readings"][0]["review_notes"])
        self.assertEqual(len(adapter.cached_rows(self.db, original, did, date(2021, 9, 30))), 90)
        with patch.object(ocr, "transcribe", side_effect=AssertionError("No provider on cached replay")):
            self.assertEqual(supply.publish(self.db, original, did,
                             "supply-reference-pdf", date(2021, 9, 30)), (90, []))

"""Source-bound paired image halves, withheld partials and retained SQL rows."""
import copy
import hashlib
import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from . import supply_fortnight_images as adapter

FIXTURES = Path(__file__).with_name("testdata")
ORIGINAL = FIXTURES / "supply_june2020_fortnight_original.pdf"
VISUAL = FIXTURES / "supply_june2020_fortnight_visual.tsv"


def readings():
    result = {2: {"text": "Cuadro 1", "tables": [[[
        "Ciudad", "Central", "Primera quincena de mayo (t)",
        "Primera quincena de junio (t)", "Variación (%)",
    ]]], "review_notes": []}, 3: {"text": "Fuente: DANE-Sipsa", "tables": [[]], "review_notes": []}}
    for line in VISUAL.read_text().splitlines():
        page, *cells = line.split("\t")
        result[int(page)]["tables"][0].append(cells)
    return result


class ImageHalves(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = ORIGINAL.read_bytes()
        if hashlib.sha256(cls.original).hexdigest() != adapter.DOCUMENT_ID:
            raise AssertionError("Portable source original changed")

    def test_complete_independent_literal_page_oracles(self):
        samples = readings()
        rows = []
        for page in adapter.PAGES:
            part = adapter.paired_page(self.original, adapter.DOCUMENT_ID, page,
                                       [samples[page], copy.deepcopy(samples[page])])
            self.assertEqual(len(part), 45)
            rows += part
        self.assertEqual(len({r["name"] for r in rows}), 30)
        self.assertEqual((rows[0]["details"]["value"], rows[1]["details"]["value"]), (5620, 5606))
        self.assertEqual([r["details"]["value"] for r in rows[-3:]], [238744, 241047, .96])
        self.assertEqual({r["details"]["frequency"] for r in rows}, {"first_fortnight"})
        self.assertEqual({r["observed_on"] for r in rows}, {date(2020, 5, 15), date(2020, 6, 15)})
        self.assertTrue(all(r["details"]["non_additive"] for r in rows))
        self.assertEqual(rows[45]["source_locator"].split(";")[0], "PDF page 3, OCR table 1, row 1, column 2")

    def test_disagreement_uncertainty_omission_and_identity_never_publish(self):
        samples = readings()
        for label in ("price", "review", "omit", "identity", "unit", "negative"):
            second = copy.deepcopy(samples[2])
            if label == "price": second["tables"][0][1][2] = "5.621"
            elif label == "review": second["review_notes"] = ["uncertain"]
            elif label == "omit": second["tables"][0].pop()
            elif label == "identity": second["tables"][0][1][1] = "Other market"
            elif label == "unit": second["tables"][0][0][2] = "Primera quincena de mayo (kg)"
            else: second["tables"][0][1][2] = "-5.620"
            with self.subTest(label=label), self.assertRaises(ValueError):
                adapter.paired_page(self.original, adapter.DOCUMENT_ID, 2, [samples[2], second])

    def test_unknown_source_page_or_invented_continuation_header_rejects(self):
        samples = readings()
        for body, did, page in ((self.original+b"changed", adapter.DOCUMENT_ID, 2),
                                (self.original, "0"*64, 2), (self.original, adapter.DOCUMENT_ID, 4)):
            with self.subTest(page=page), self.assertRaises(ValueError):
                adapter.page_rows(body, did, page, samples[2])
        continuation = copy.deepcopy(samples[3])
        continuation["tables"][0].insert(0, samples[2]["tables"][0][0])
        with self.assertRaises(ValueError):
            adapter.page_rows(self.original, adapter.DOCUMENT_ID, 3, continuation)

    def test_real_retained_pairs_preserve_printed_typo_and_all_ninety_cells(self):
        retained = json.loads((FIXTURES / "supply_june2020_real_ocr_v2.json").read_text())
        expected = readings()
        for page in adapter.PAGES:
            actual = [item[2] for item in retained if item[0] == page]
            rows = adapter.paired_page(self.original, adapter.DOCUMENT_ID, page, actual)
            visual = adapter.paired_page(self.original, adapter.DOCUMENT_ID, page,
                [expected[page], copy.deepcopy(expected[page])])
            identity = lambda xs: [(adapter.normalized(r["name"]), r["details"]["literal_value"],
                                   r["observed_on"], r["details"]["unit"]) for r in xs]
            self.assertEqual(identity(rows), identity(visual))
            if page == 2:
                spelling = [r for r in rows if "Saper Mendoza" in r["name"]]
                self.assertEqual(len(spelling), 3)
                self.assertTrue(all("nombre literal" in r["details"]["source_note"] for r in spelling))

    def test_only_exact_source_page_and_verified_non_uncertainty_comments_pass(self):
        sample = readings()
        for note in ("uncertain", "888 may be 889", "", None):
            reading = copy.deepcopy(sample[2])
            reading["review_notes"] = [note]
            with self.subTest(note=note), self.assertRaises(ValueError):
                adapter.page_rows(self.original, adapter.DOCUMENT_ID, 2, reading)
        for note in adapter.VERIFIED_PRINTED_SPELLING_COMMENTS:
            reading = copy.deepcopy(sample[3])
            reading["review_notes"] = [note]
            with self.assertRaises(ValueError):
                adapter.page_rows(self.original, adapter.DOCUMENT_ID, 3, reading)


@unittest.skipUnless(os.environ.get("AGRO_DAILY_ZIP_POSTGRES_TEST") == "1", "Private PostgreSQL opt-in")
class ImagePublication(unittest.TestCase):
    from .test_daily_archives import ArchivePublicationPostgres as _Fixture
    setUp = _Fixture.setUp

    def test_two_halves_are_atomic_idempotent_and_cached_without_provider(self):
        from psycopg.types.json import Jsonb
        from . import ocr, worker
        samples = readings()
        original = ORIGINAL.read_bytes()
        did = worker.archive(self.db, adapter.SOURCE_URL, original, "supply-reference-pdf", None)
        self.db.execute("INSERT INTO ingestion_asset(url,kind,document_id,status,records) "
            "VALUES(%s,'supply-reference-pdf',%s,'review',0)", (adapter.SOURCE_URL, did))
        for table in ("source_ocr_task", "source_ocr_result"):
            self.db.execute(f"CREATE TEMP TABLE {table}(LIKE public.{table} INCLUDING ALL)")
        self.assertEqual(adapter.queue(self.db, original, did), [2, 3])
        for page in adapter.PAGES:
            image_id = self.db.execute("SELECT image_id FROM source_ocr_task WHERE document_id=%s "
                "AND source_page=%s", (did, page)).fetchone()[0]
            for reading in (0, 1):
                self.db.execute("INSERT INTO source_ocr_result(image_id,version,reading,result) VALUES(%s,%s,%s,%s)",
                    (image_id, ocr.VERSION, reading, Jsonb(samples[page])))
            count = adapter.publish_verified(self.db, original, did, page, [samples[page], copy.deepcopy(samples[page])])
            self.assertEqual(count, 0 if page == 2 else 90)
            self.assertEqual(self.db.execute("SELECT count(*) FROM input_reference_row WHERE document_id=%s", (did,)).fetchone()[0], count)
        self.assertEqual(self.db.execute("SELECT status,records FROM ingestion_asset WHERE document_id=%s", (did,)).fetchone(), ("complete", 90))
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_task WHERE document_id=%s AND status='published'", (did,)).fetchone()[0], 2)
        self.assertEqual(adapter.publish_verified(self.db, original, did, 3, [samples[3], copy.deepcopy(samples[3])]), 90)
        self.assertEqual(len(adapter.cached_rows(self.db, original, did, date(2020, 6, 15))), 90)
        with self.assertRaises(ValueError):
            adapter.cached_rows(self.db, original, did, date(2020, 6, 30))
        with patch.object(ocr, "transcribe", side_effect=AssertionError("No provider on cached replay")):
            from .supply_period_summaries import publish
            self.assertEqual(publish(self.db, original, did, "supply-reference-pdf"), (90, []))
        for table in ("historical_price", "daily_price", "regional_price", "official_price_quote"):
            self.assertEqual(self.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)
        self.assertEqual(bytes(self.db.execute("SELECT content FROM source_document WHERE id=%s", (did,)).fetchone()[0]), original)


if __name__ == "__main__":
    unittest.main()

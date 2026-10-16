"""A bounded native check retires stale daily OCR without provider requests."""

import hashlib
import os
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from . import ocr, worker

FIXTURES = Path(__file__).with_name("testdata")
ORIGINALS = (
    ("dane_daily_2014_06_09_blank_page4.pdf", date(2014, 6, 9), 4),
    ("dane_daily_2017_04_19_blank_page4.pdf", date(2017, 4, 19), 4),
)


class Result:
    def __init__(self, one=None, many=()):
        self.one, self.many = one, many

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class Database:
    def __init__(self):
        self.sources = {}
        self.tasks = {}
        self.retired = []
        self.scanned = []
        self.requeued = []
        self.task_states = {}
        self.asset_version = "daily-pdf-v5"

    def add(self, filename, day, page, *, did=None, count=1):
        body = (FIXTURES / filename).read_bytes()
        did = did or hashlib.sha256(body).hexdigest()
        self.sources[did] = (body, str(day), day)
        self.tasks[did] = [(f"PDF page {page}-{i}", f"image-{i}", page)
                           for i in range(count)]
        self.task_states[did] = [("pending", None) for _ in range(count)]
        return did

    def execute(self, query, params=()):
        if query.startswith("SELECT d.content FROM source_document d"):
            # This fixture has no exact visually audited decorative-page
            # original; the separate native daily sweep owns its page tasks.
            return Result()
        if query.startswith("SELECT id,content"):
            return Result()
        if query.startswith("SELECT count(*) FROM source_ocr_attempt"):
            return Result(one=(0,))
        if query.startswith("SELECT document_id,source_locator,image_id,source_kind"):
            return Result()
        if query.startswith("SELECT t.document_id FROM source_ocr_task"):
            return Result(many=[(did,) for did in list(self.tasks)[:params[1]]
                                if did not in self.scanned])
        if query.startswith("SELECT d.content,d.reference_period,a.observed_on"):
            return Result(one=self.sources.get(params[0]))
        if query.startswith("SELECT source_locator,image_id,source_page"):
            return Result(many=self.tasks[params[0]][:params[1]])
        if query.startswith("SELECT status,error FROM source_ocr_task"):
            return Result(many=self.task_states[params[0]])
        if query.startswith("UPDATE source_ocr_task SET status='review'"):
            self.retired.append(params)
            index = self.tasks[params[1]].index((params[2], params[3], params[4]))
            self.task_states[params[1]][index] = ("review", params[0])
            return Result()
        if query.startswith("UPDATE ingestion_asset a SET status='pending'"):
            assert self.asset_version == "daily-pdf-v5"
            assert "a.status='awaiting-ocr'" in query
            assert "t.error IS DISTINCT FROM %s" in query
            self.requeued.append(params)
            return Result(one=("https://dane.example/retained.pdf",))
        if query.startswith("INSERT INTO source_ocr_scan"):
            self.scanned.append(params[0])
            return Result()
        if query.startswith("SELECT d.content FROM ingestion_asset a"):
            assert params[1] == ocr.NATIVE_DAILY_REQUEUE_REASON
            assert "a.status='pending'" in query
            assert "d.kind='original'" in query
            return Result(one=(self.sources[next(iter(self.sources))][0],))
        raise AssertionError(query)


class NativeDailySweep(unittest.TestCase):
    def test_current_v5_asset_requeues_after_exact_original_pages_clear_without_provider(self):
        db = Database()
        did = db.add(*ORIGINALS[0])
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}), patch.object(
            ocr, "transcribe", side_effect=AssertionError("provider called")
        ) as provider:
            result = ocr.drain(db, limit=0, scan_limit=0)
        self.assertFalse(result["configured"])
        self.assertEqual(result["daily_native_sweep"]["retired"], 1)
        self.assertEqual(result["daily_native_sweep"]["eligible"], 0)
        self.assertEqual(result["daily_native_sweep"]["requeued_assets"], 1)
        self.assertEqual(len(db.retired), 1)
        self.assertEqual(db.retired[0][1:], (did, "PDF page 4-0", "image-0", 4))
        self.assertIn("Native extraction rechecked", db.retired[0][0])
        self.assertEqual(db.scanned, [did])
        self.assertEqual(db.requeued[0][1], did)
        provider.assert_not_called()

    def test_another_page_needing_ocr_blocks_asset_requeue(self):
        db = Database()
        did = db.add(*ORIGINALS[0])
        db.task_states[did] = [("review", ocr.NATIVE_DAILY_REVIEW_REASON)]
        with patch("pipelines.ingestion.pdf_sources.queued_price_page_needs_ocr",
                   side_effect=[False, True]) as gate:
            self.assertFalse(ocr.requeue_native_daily_asset(
                db, did, db.sources[did][0], ORIGINALS[0][1]
            ))
        self.assertEqual(gate.call_count, 2)
        self.assertEqual(db.requeued, [])

    def test_eligible_page_is_untouched_and_scan_marker_advances(self):
        db = Database()
        did = db.add(*ORIGINALS[0])
        with patch("pipelines.ingestion.pdf_sources.queued_price_page_needs_ocr",
                   return_value=True):
            result = ocr.retire_native_daily_tasks(db)
        self.assertEqual(result["eligible"], 1)
        self.assertEqual(db.retired, [])
        self.assertEqual(db.scanned, [did])
        self.assertEqual(db.requeued, [])

    def test_document_limit_deadline_and_original_hash_are_enforced(self):
        db = Database()
        first = db.add(*ORIGINALS[0])
        second = db.add(*ORIGINALS[1])
        self.assertEqual(ocr.retire_native_daily_tasks(db, document_limit=1)["documents"], 1)
        self.assertEqual(db.scanned, [first])
        self.assertEqual(len(db.retired), 1)
        self.assertEqual(ocr.retire_native_daily_tasks(db, deadline=time.monotonic() + 1)["documents"], 0)
        self.assertEqual(db.scanned, [first])
        db.sources[second] = (b"%PDF-tampered", str(ORIGINALS[1][1]), ORIGINALS[1][1])
        self.assertEqual(ocr.retire_native_daily_tasks(db)["errors"], 1)
        self.assertEqual(db.scanned, [first])
        self.assertEqual(len(db.retired), 1)

    def test_failed_page_recheck_does_not_mark_document_scanned(self):
        db = Database()
        db.add(*ORIGINALS[0])
        with patch("pipelines.ingestion.pdf_sources.queued_price_page_needs_ocr",
                   side_effect=ValueError("uncertain page")):
            result = ocr.retire_native_daily_tasks(db)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(db.scanned, [])
        self.assertEqual(db.retired, [])
        self.assertEqual(db.requeued, [])

    def test_unresolved_review_blocks_asset_requeue(self):
        db = Database()
        did = db.add(*ORIGINALS[0])
        db.task_states[did] = [("review", "Independent readings disagree")]
        self.assertFalse(ocr.requeue_native_daily_asset(
            db, did, db.sources[did][0], ORIGINALS[0][1]
        ))
        self.assertEqual(db.requeued, [])

    def test_pending_replay_uses_retained_original(self):
        db = Database()
        db.add(*ORIGINALS[0])
        with patch.object(worker, "fetch_asset", side_effect=AssertionError("network fetch")):
            retained = worker.retained_daily_ocr_resume(db, "https://dane.example/retained.pdf")
        self.assertEqual(retained[0], next(iter(db.sources.values()))[0])

    def test_more_than_eight_pages_remains_untouched(self):
        db = Database()
        db.add(*ORIGINALS[0], count=9)
        result = ocr.retire_native_daily_tasks(db)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(db.retired, [])
        self.assertEqual(db.scanned, [])


if __name__ == "__main__":
    unittest.main()

"""Provider quota/time accounting uses only uncached readings; no real I/O."""

import io
import os
import unittest
from unittest.mock import patch

from PIL import Image

from . import ocr

READING = {"text": "Readable literal fixture note", "tables": [], "review_notes": []}


class Result:
    def __init__(self, one=None, many=()):
        self.one, self.many = one, many

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class Database:
    def __init__(self, used, cache, tasks=("image",)):
        self.used, self.cache, self.tasks = used, cache, tasks
        self.scan_limit = None
        stream = io.BytesIO()
        Image.new("RGB", (400, 300), "white").save(stream, format="PNG")
        self.png = stream.getvalue()

    def execute(self, sql, params=()):
        if sql.startswith("SELECT id,content"):
            self.scan_limit = params[1]
            return Result()
        if sql.startswith("SELECT count(*) FROM source_ocr_attempt"):
            return Result(one=(self.used,))
        if sql.startswith("SELECT document_id,source_locator,image_id"):
            return Result(
                many=[("doc", image, image, "fixture", None) for image in self.tasks]
            )
        if sql.startswith("SELECT content FROM source_document"):
            return Result(one=(self.png,))
        if sql.startswith("SELECT result FROM source_ocr_result"):
            return Result(
                one=(READING,) if (params[0], params[2]) in self.cache else None
            )
        if sql.startswith("INSERT INTO source_ocr_attempt"):
            self.used += 1
        return Result()


class OCRBudgetTests(unittest.TestCase):
    def run_case(self, *, start=0, used=0, cache=(), tasks=("image",), duration=0):
        clock = [start]
        db = Database(used, cache, tasks)

        def transcribe(*args, **kwargs):
            clock[0] += duration
            return dict(READING)

        with (
            patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "mock-only", "GEMINI_OCR_DAILY_REQUESTS": "40"},
            ),
            patch("time.monotonic", side_effect=lambda: clock[0]),
            patch.object(ocr, "transcribe", side_effect=transcribe) as provider,
            patch.object(ocr, "publish_workbook_reading", return_value=False),
        ):
            result = ocr.drain(db, limit=len(tasks), scan_limit=1, deadline=600)
        return result, provider.call_count, clock[0], db

    def test_full_cached_pair_publishes_at_quota_with_short_remaining_budget(self):
        result, calls, end, db = self.run_case(
            start=550, used=40, cache=(("image", 0), ("image", 1))
        )
        self.assertEqual((result["processed"], calls, end, db.used), (1, 0, 550, 40))
        self.assertEqual(db.scan_limit, 0)

    def test_one_cached_reading_uses_final_request_and_only_reserves_one_call(self):
        result, calls, end, db = self.run_case(
            start=350, used=39, cache=(("image", 0),), duration=200
        )
        self.assertEqual((result["processed"], calls, end, db.used), (1, 1, 550, 40))

    def test_two_uncached_readings_fit_fresh_600_second_slot(self):
        result, calls, end, db = self.run_case(duration=200)
        self.assertEqual((result["processed"], calls, end, db.used), (1, 2, 400, 2))
        self.assertEqual(sum(ocr.PROVIDER_TIMEOUT), 200)

    def test_pair_is_deferred_when_connect_plus_read_would_overrun(self):
        result, calls, end, db = self.run_case(start=220, duration=200)
        self.assertEqual((result["deferred"], calls, end, db.used), (1, 0, 220, 0))

    def test_uncached_quota_block_does_not_starve_cached_task_in_same_selection(self):
        result, calls, _end, db = self.run_case(
            used=40, tasks=("new", "cached"), cache=(("cached", 0), ("cached", 1))
        )
        self.assertEqual(
            (result["processed"], result["deferred"], calls, db.used), (1, 1, 0, 40)
        )

    def test_no_publication_starts_after_final_sql_reserve_is_spent(self):
        result, calls, _, _ = self.run_case(
            start=580, cache=(("image", 0), ("image", 1))
        )
        self.assertIn("Insufficient", result["deferred"])
        self.assertEqual(calls, 0)


if __name__ == "__main__":
    unittest.main()

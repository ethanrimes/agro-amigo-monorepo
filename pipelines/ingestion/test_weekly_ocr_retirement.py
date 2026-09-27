"""Weekly native completion retires obsolete OCR without hiding unresolved pages."""

import os
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from . import dane_weekly, ocr, official_sources, worker
from .resumable_inputs import WorkDeferred
from .test_ocr_budget import READING, Database, Result

KIND = "dane-weekly-pdf"
URL = "https://www.dane.gov.co/files/weekly.pdf"


class WeeklyDatabase(Database):
    def __init__(self, checkpoints=(), *, kind=KIND, cache=()):
        super().__init__(used=0, cache=cache)
        self.checkpoints = set(checkpoints)
        self.kind = kind
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if sql.startswith("SELECT 1 FROM ingestion_checkpoint"):
            return Result(one=(1,) if params in self.checkpoints else None)
        if sql.startswith("SELECT document_id,source_locator,image_id"):
            return Result(many=[("doc", "PDF page 2", "image", self.kind, 2)])
        if sql.startswith("SELECT content,source_url"):
            return Result(one=(b"%PDF-original", URL))
        return super().execute(sql, params)


class WeeklyOCRRetirement(unittest.TestCase):
    def test_native_success_retires_only_pending_weekly_tasks_after_publication(self):
        db = MagicMock()
        events = []
        db.execute.side_effect = lambda sql, params: events.append((sql, params))
        with (
            patch.object(dane_weekly, "discover", return_value=[]),
            patch.object(dane_weekly, "parse", return_value=["native row"]),
            patch.object(
                official_sources,
                "publish_rows",
                side_effect=lambda *args: events.append("published") or 1,
            ),
        ):
            self.assertEqual(official_sources.process(db, b"PDF", "doc", URL, KIND), 1)
        self.assertEqual(events[0], "published")
        sql, params = events[1]
        self.assertIn("status='review'", sql)
        self.assertIn("source_kind='dane-weekly-pdf'", sql)
        self.assertIn("status IN ('pending','deferred')", sql)
        self.assertIn("Native extraction succeeded; no OCR needed", params[0])
        self.assertIn("prior readings retained", params[0])
        self.assertEqual(params[1], "doc")

    def test_failed_or_partial_native_publication_does_not_retire_tasks(self):
        for failure in (ValueError("invalid quote"), WorkDeferred("resume batches")):
            with self.subTest(failure=type(failure).__name__):
                db = MagicMock()
                with (
                    patch.object(dane_weekly, "discover", return_value=[]),
                    patch.object(dane_weekly, "parse", return_value=["native row"]),
                    patch.object(official_sources, "publish_rows", side_effect=failure),
                    self.assertRaises(type(failure)),
                ):
                    official_sources.process(db, b"PDF", "doc", URL, KIND)
                db.execute.assert_not_called()

    def test_successful_workbook_publication_does_not_retire_image_tasks(self):
        db = MagicMock()
        with (
            patch.object(dane_weekly, "discover", return_value=[]),
            patch.object(dane_weekly, "parse", return_value=["native row"]),
            patch.object(official_sources, "publish_rows", return_value=1),
        ):
            official_sources.process(db, b"XLS", "doc", URL, "dane-weekly-xlsx")
        db.execute.assert_not_called()

    def test_cached_required_pages_remain_ocr_published_not_native_retired(self):
        import pdfplumber

        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [(READING,), (READING,)]
        page = SimpleNamespace(
            to_image=lambda **kwargs: SimpleNamespace(original="retained image")
        )
        with (
            patch.object(dane_weekly, "discover", return_value=[]),
            patch.object(
                dane_weekly,
                "parse",
                side_effect=dane_weekly.NormalExtractionFailed([2]),
            ),
            patch.object(
                pdfplumber,
                "open",
                return_value=nullcontext(SimpleNamespace(pages=[page, page])),
            ),
            patch.object(ocr, "enqueue_image") as enqueue,
            patch.object(
                dane_weekly, "parse_with_ocr", return_value=["OCR row"]
            ) as parse,
            patch.object(official_sources, "publish_rows", return_value=1),
        ):
            self.assertEqual(official_sources.process(db, b"PDF", "doc", URL, KIND), 1)
        enqueue.assert_called_once_with(
            db, "doc", "PDF page 2", "retained image", KIND, 2
        )
        parse.assert_called_once_with(b"PDF", URL, KIND, {2: READING})
        updates = [
            c.args for c in db.execute.call_args_list if c.args[0].startswith("UPDATE")
        ]
        self.assertEqual(len(updates), 1)
        self.assertIn("status='published'", updates[0][0])
        self.assertEqual(updates[0][1], ("doc", [2]))

    def test_unresolved_required_page_keeps_tasks_and_never_completes(self):
        import pdfplumber

        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        page = SimpleNamespace(
            to_image=lambda **kwargs: SimpleNamespace(original="image")
        )
        with (
            patch.object(dane_weekly, "discover", return_value=[]),
            patch.object(
                dane_weekly,
                "parse",
                side_effect=dane_weekly.NormalExtractionFailed([1]),
            ),
            patch.object(
                pdfplumber,
                "open",
                return_value=nullcontext(SimpleNamespace(pages=[page])),
            ),
            patch.object(ocr, "enqueue_image"),
            patch.object(official_sources, "publish_rows") as publish,
        ):
            self.assertIsNone(official_sources.process(db, b"PDF", "doc", URL, KIND))
        publish.assert_not_called()
        self.assertFalse(
            any(c.args[0].startswith("UPDATE") for c in db.execute.call_args_list)
        )

    def drain(self, db):
        with (
            patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "test-only", "GEMINI_OCR_DAILY_REQUESTS": "40"},
            ),
            patch.object(ocr, "transcribe", return_value=READING) as provider,
            patch.object(ocr, "publish_workbook_reading", return_value=False),
            patch.object(official_sources, "process", return_value=1) as publish,
        ):
            result = ocr.drain(db, limit=1, scan_limit=0)
        return result, provider, publish

    def test_current_document_completion_skips_cache_images_and_provider(self):
        db = WeeklyDatabase(checkpoints=[("doc", worker.parser_version(KIND))])
        result, provider, publish = self.drain(db)
        self.assertEqual(result, {"processed": 0, "review": 1, "deferred": 0})
        provider.assert_not_called()
        publish.assert_not_called()
        self.assertFalse(any("source_ocr_result" in sql for sql, _ in db.calls))
        self.assertFalse(any("SELECT content" in sql for sql, _ in db.calls))
        self.assertFalse(
            any("INSERT INTO source_ocr_attempt" in sql for sql, _ in db.calls)
        )
        checkpoint_sql = next(
            sql for sql, _ in db.calls if "SELECT 1 FROM ingestion_checkpoint" in sql
        )
        self.assertIn("step='official:complete'", checkpoint_sql)
        update = next(
            (sql, p) for sql, p in db.calls if sql.startswith("UPDATE source_ocr_task")
        )
        self.assertIn("status='review'", update[0])
        self.assertIn("no OCR needed", update[1][0])

    def test_old_version_or_other_document_completion_does_not_skip_required_ocr(self):
        for checkpoint in (
            ("doc", "official-v2:dane-weekly-v1"),
            ("another-doc", worker.parser_version(KIND)),
        ):
            with self.subTest(checkpoint=checkpoint):
                db = WeeklyDatabase(checkpoints=[checkpoint])
                result, provider, publish = self.drain(db)
                self.assertEqual((result["processed"], provider.call_count), (1, 2))
                publish.assert_called_once()

    def test_uncompleted_weekly_cached_ocr_still_publishes_without_provider(self):
        db = WeeklyDatabase(cache=(("image", 0), ("image", 1)))
        result, provider, publish = self.drain(db)
        self.assertEqual(result["processed"], 1)
        provider.assert_not_called()
        publish.assert_called_once_with(db, b"%PDF-original", "doc", URL, KIND)
        self.assertTrue(any("status='published'" in sql for sql, _ in db.calls))

    def test_inputs_with_native_rows_do_not_use_weekly_completion_gate(self):
        db = WeeklyDatabase(
            checkpoints=[("doc", worker.parser_version(KIND))], kind="inputs-pdf"
        )
        result, provider, _ = self.drain(db)
        self.assertEqual((result["processed"], provider.call_count), (1, 2))
        self.assertFalse(any("ingestion_checkpoint" in sql for sql, _ in db.calls))


if __name__ == "__main__":
    unittest.main()

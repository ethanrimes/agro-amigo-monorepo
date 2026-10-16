"""Pending OCR originals still receive native-first revision checks.

The real scheduling SQL runs against a private PostgreSQL TEMP table. HTTP is
stubbed only at the publisher boundary; the 304 database update is real.
"""

import os
import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from . import queue_plan, worker


@unittest.skipUnless(
    os.environ.get("AGRO_QUEUE_POSTGRES_TEST") == "1",
    "Isolated local PostgreSQL opt-in",
)
class OcrRevalidationQueue(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.info.host.startswith("/tmp/agro-"))
        self.db.execute("SET search_path=pg_temp")
        self.db.execute(
            "CREATE TEMP TABLE ingestion_asset "
            "(LIKE public.ingestion_asset INCLUDING ALL)"
        )
        self.db.execute(
            "CREATE TEMP TABLE official_source_review "
            "(LIKE public.official_source_review INCLUDING ALL)"
        )
        self.today = date.today()

    def add(self, label, age, *, historical=False, outdated=False, status="awaiting-ocr"):
        url = "https://example.invalid/" + label + ".pdf"
        day = self.today - timedelta(days=365 if historical else 2)
        self.db.execute(
            """INSERT INTO ingestion_asset
            (url,kind,observed_on,status,processor_version,checked_at,
             document_id,records,http_etag)
            VALUES(%s,'daily-pdf',%s,%s,%s,now()-(%s * interval '1 hour'),
                   'retained-original',7,'"original"')""",
            (url, day, status, "old-parser" if outdated else worker.parser_version("daily-pdf"), age),
        )
        return url

    def selected(self, daily=True):
        rows = (
            queue_plan.daily_candidates(self.db, self.today)
            if daily
            else queue_plan.backfill_candidates(self.db, 100)
        )
        return {row[0] for row in rows}

    def test_current_pending_ocr_checks_daily_without_retrying_too_soon(self):
        due = self.add("due-current", 25)
        recent = self.add("recent-current", 23)
        self.assertEqual(self.selected(), {due})
        self.assertNotIn(recent, self.selected())

    def test_historical_pending_ocr_checks_monthly_and_parser_replay_is_immediate(self):
        due = self.add("due-history", 31 * 24, historical=True)
        recent = self.add("recent-history", 29 * 24, historical=True)
        replay = self.add("replay-history", 1, historical=True, outdated=True)
        self.assertEqual(self.selected(daily=False), {due, replay})
        self.assertNotIn(recent, self.selected(daily=False))
        self.assertEqual(self.selected(), set())

    def test_current_parser_change_bypasses_ocr_and_failure_cooldowns(self):
        replay = self.add("replay-current", 1, outdated=True)
        failed = self.add("failed-current", 1, outdated=True, status="failed")
        ordinary_failure = self.add("ordinary-failure", 1, status="failed")
        self.assertEqual(self.selected(), {replay, failed})
        self.assertNotIn(ordinary_failure, self.selected())

    def test_conditional_304_keeps_pending_ocr_original_and_rows_then_cools_down(self):
        url = self.add("unchanged", 25)
        response = SimpleNamespace(status_code=304)
        with patch.object(worker.SESSION, "get", return_value=response) as get:
            self.assertIsNone(worker.fetch_asset(self.db, url))
        self.assertEqual(get.call_args.kwargs["headers"], {"If-None-Match": '"original"'})
        self.assertEqual(
            self.db.execute(
                "SELECT status,document_id,records FROM ingestion_asset WHERE url=%s", (url,)
            ).fetchone(),
            ("awaiting-ocr", "retained-original", 7),
        )
        self.assertEqual(self.selected(), set())

    def test_changed_200_returns_new_bytes_without_overwriting_retained_pointer(self):
        url = self.add("changed", 25)
        response = SimpleNamespace(
            status_code=200, headers={"ETag": '"revision"'},
            content=b"new native-readable original", raise_for_status=lambda: None,
        )
        with patch.object(worker.SESSION, "get", return_value=response):
            self.assertEqual(worker.fetch_asset(self.db, url), response.content)
        self.assertEqual(
            self.db.execute(
                "SELECT status,document_id,records,http_etag FROM ingestion_asset WHERE url=%s", (url,)
            ).fetchone(),
            ("awaiting-ocr", "retained-original", 7, '"revision"'),
        )

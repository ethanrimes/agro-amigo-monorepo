"""Proposed private-PG tests for the exact July 2022 pending continuation.

This staged copy is intentionally unexecuted while V35 owns the private cluster.
The larger source-wide publication/crash cases are specified in
TRADEOFFS_AND_TESTS.md and should be added before release.
"""

import hashlib
import os
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg
from psycopg.types.json import Jsonb

from . import dane_weekly, official_sources, queue_plan, worker
from .resumable_inputs import WorkDeferred
from .test_official_catalog import install_cache
from .retained_pdf_upgrade import (
    JUL2022_PENDING_URL, JUL2022_NEW_ASSET_VERSION,
    JUL2022_OLD_ASSET_VERSION, JUL2022_QUOTE_VERSION,
    JUL2022_PENDING_ERRORS,
    retained_pdf_upgrade,
)

SHA = "2ab314d876e586aafd8017a50d26762a1a96cbb489a57cc45a51007d63158304"
BODY = Path(__file__).parent / "testdata/dane_weekly_2022_07_09_native_layout.pdf"
REASON = "Official source validated; committed quote batches will resume"


class ExactPendingWeeklyResumePostgres(unittest.TestCase):
    def setUp(self):
        dsn = os.environ.get("AGRO_REFERENCE_TEST_DSN")
        if not dsn:
            raise RuntimeError("Explicit private PostgreSQL DSN required")
        self.db = psycopg.connect(dsn, autocommit=True)
        self.addCleanup(self.db.close)
        if not str(self.db.info.host).startswith("/tmp/agro-"):
            raise RuntimeError("Private socket required")
        self.db.execute("SET search_path=pg_temp; SET statement_timeout='15s'")
        for table in ("source_document", "ingestion_asset", "ingestion_checkpoint", "historical_price"):
            self.db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")
        self.body = BODY.read_bytes()
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), SHA)
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
            "reference_period,content,metadata) VALUES(%s,'DANE weekly','DANE',%s,"
            "'application/pdf','original','2022-07-15',%s,%s)",
            (SHA, JUL2022_PENDING_URL, self.body, Jsonb({"ingestion_kind": "dane-weekly-pdf"})),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,"
            "observed_on,checked_at,records,error) VALUES(%s,'dane-weekly-pdf',"
            "'pending',%s,%s,'2022-07-15',now()-interval '7 hours',0,%s)",
            (JUL2022_PENDING_URL, JUL2022_OLD_ASSET_VERSION, SHA, REASON),
        )

    def local(self):
        return retained_pdf_upgrade(
            self.db, JUL2022_PENDING_URL, "dane-weekly-pdf",
            JUL2022_NEW_ASSET_VERSION, JUL2022_QUOTE_VERSION,
        )

    def test_pending_continuation_is_one_weekly_repair_and_local_during_host_cooldown(self):
        self.assertEqual(self.local(), self.body)
        self.assertEqual(worker.asset_parser_version("dane-weekly-pdf", JUL2022_PENDING_URL),
                         JUL2022_NEW_ASSET_VERSION)
        self.assertEqual(worker.parser_version("dane-weekly-pdf", JUL2022_PENDING_URL),
                         JUL2022_QUOTE_VERSION)
        self.assertIn(JUL2022_PENDING_URL,
                      [row[0] for row in queue_plan.repair_candidates(self.db, 5)])
        with patch.object(worker, "fetch_asset", side_effect=AssertionError("source HTTP forbidden")):
            self.assertTrue(worker.retained_reparse_during_host_cooldown(
                self.db, JUL2022_PENDING_URL, "dane-weekly-pdf"))
        self.db.execute("UPDATE ingestion_asset SET checked_at=now() WHERE url=%s",
                        (JUL2022_PENDING_URL,))
        self.assertNotIn(JUL2022_PENDING_URL,
                         [row[0] for row in queue_plan.repair_candidates(self.db, 5)])

    def test_exact_pending_leads_weekly_kind_without_increasing_total_slots(self):
        other = "https://www.dane.gov.co/files/other-old-weekly.pdf"
        did = "b" * 64
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
            "reference_period,content,metadata) VALUES(%s,'Other weekly','DANE',%s,"
            "'application/pdf','original','2012-01-01',%s,%s)",
            (did, other, b"%PDF-other", Jsonb({"ingestion_kind": "dane-weekly-pdf"})),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,"
            "observed_on,checked_at,records) VALUES(%s,'dane-weekly-pdf','complete',"
            "'official-v2:dane-weekly-v23',%s,'2012-01-01',now()-interval '30 days',1)",
            (other, did),
        )
        selected = [r[0] for r in queue_plan.repair_candidates(self.db, 5)]
        self.assertEqual(selected, [JUL2022_PENDING_URL])
        self.db.execute("UPDATE ingestion_asset SET checked_at=now() WHERE url=%s",
                        (JUL2022_PENDING_URL,))
        self.assertEqual([r[0] for r in queue_plan.repair_candidates(self.db, 5)], [other])

    def test_pending_worker_reuses_original_without_publisher_http(self):
        with (
            patch.object(worker, "fetch_asset", side_effect=AssertionError("publisher HTTP forbidden")) as fetch,
            patch.object(worker, "archive", return_value=SHA) as archive,
            patch("pipelines.ingestion.official_sources.process", return_value=4225) as publish,
        ):
            self.assertEqual(worker.process_asset(
                self.db, JUL2022_PENDING_URL, "dane-weekly-pdf", date(2022, 7, 15)), 4225)
        fetch.assert_not_called()
        archive.assert_called_once_with(
            self.db, JUL2022_PENDING_URL, self.body, "dane-weekly-pdf", date(2022, 7, 15))
        publish.assert_called_once_with(
            self.db, self.body, SHA, JUL2022_PENDING_URL, "dane-weekly-pdf")
        self.assertEqual(self.db.execute(
            "SELECT status,records,processor_version FROM ingestion_asset WHERE url=%s",
            (JUL2022_PENDING_URL,),
        ).fetchone(), ("complete", 4225, JUL2022_NEW_ASSET_VERSION))

    def test_wrong_state_version_reason_and_checkpoint_fail_closed(self):
        for column, wrong, original in (
            ("status", "review", "pending"),
            ("records", 1, 0),
            ("processor_version", JUL2022_NEW_ASSET_VERSION, JUL2022_OLD_ASSET_VERSION),
            ("error", "unrelated pending work", REASON),
            ("document_id", "0" * 64, SHA),
            ("kind", "daily-pdf", "dane-weekly-pdf"),
        ):
            with self.subTest(column=column):
                self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s",
                                (wrong, JUL2022_PENDING_URL))
                try:
                    self.assertIsNone(self.local())
                    # A review asset may still enter the ordinary stale repair
                    # lane; it must never inherit this pending-only local route.
                    if column != "status":
                        self.assertNotIn(JUL2022_PENDING_URL,
                                         [r[0] for r in queue_plan.repair_candidates(self.db, 5)])
                finally:
                    self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s",
                                    (original, JUL2022_PENDING_URL))
        self.assertIsNone(retained_pdf_upgrade(
            self.db, JUL2022_PENDING_URL, "dane-weekly-pdf",
            "future-asset-version", JUL2022_QUOTE_VERSION))
        self.assertIsNone(retained_pdf_upgrade(
            self.db, JUL2022_PENDING_URL, "dane-weekly-pdf",
            JUL2022_NEW_ASSET_VERSION, "future-quote-version"))
        self.db.execute(
            "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
            "VALUES(%s,%s,'official:complete',4225)", (SHA, JUL2022_QUOTE_VERSION),
        )
        self.assertIsNone(self.local())
        self.assertNotIn(JUL2022_PENDING_URL,
                         [r[0] for r in queue_plan.repair_candidates(self.db, 5)])

    def test_only_exact_work_deferred_reasons_or_numeric_catalog_progress_resume(self):
        valid = (*JUL2022_PENDING_ERRORS,
                 "Official catalog refresh deferred after 64 of 4200 identities")
        for reason in valid:
            with self.subTest(reason=reason):
                self.db.execute("UPDATE ingestion_asset SET error=%s WHERE url=%s",
                                (reason, JUL2022_PENDING_URL))
                self.assertEqual(self.local(), self.body)
                self.assertIn(JUL2022_PENDING_URL,
                              [r[0] for r in queue_plan.repair_candidates(self.db, 5)])
        for reason in ("Official catalog refresh deferred after arbitrary identities",
                       "Official catalog refresh deferred after 64 of 4200 identities; altered",
                       "HostRateLimited: publisher returned 429", ""):
            with self.subTest(reason=reason):
                self.db.execute("UPDATE ingestion_asset SET error=%s WHERE url=%s",
                                (reason, JUL2022_PENDING_URL))
                self.assertIsNone(self.local())
                self.assertNotIn(JUL2022_PENDING_URL,
                                 [r[0] for r in queue_plan.repair_candidates(self.db, 5)])

    def test_content_sha_rechecked_and_wrong_original_metadata_rejected(self):
        self.db.execute("UPDATE source_document SET content=%s WHERE id=%s",
                        (self.body + b"changed", SHA))
        with self.assertRaisesRegex(ValueError, "invalid original SHA"):
            self.local()
        self.db.execute("UPDATE source_document SET content=%s WHERE id=%s", (self.body, SHA))
        for column, bad, original in (
            ("source_url", JUL2022_PENDING_URL + "?other", JUL2022_PENDING_URL),
            ("media_type", "application/octet-stream", "application/pdf"),
        ):
            self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s", (bad, SHA))
            self.assertIsNone(self.local())
            self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s", (original, SHA))
        self.db.execute("UPDATE source_document SET metadata=%s WHERE id=%s",
                        (Jsonb({"ingestion_kind": "monthly-pdf"}), SHA))
        self.assertIsNone(self.local())


class ExactPendingWeeklyPublicationPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = BODY.read_bytes()
        if hashlib.sha256(cls.body).hexdigest() != SHA:
            raise RuntimeError("Native July 2022 original SHA mismatch")
        cls.rows = dane_weekly.parse_pdf(cls.body, JUL2022_PENDING_URL)
        if (len(cls.rows), sum(r["price"] is not None for r in cls.rows)) != (4828, 4225):
            raise RuntimeError("Native source row and money counts changed")

    def setUp(self):
        dsn = os.environ.get("AGRO_REFERENCE_TEST_DSN")
        if not dsn:
            raise RuntimeError("Explicit private PostgreSQL DSN required")
        self.db = psycopg.connect(dsn, autocommit=True)
        self.addCleanup(self.db.close)
        if not str(self.db.info.host).startswith("/tmp/agro-"):
            raise RuntimeError("Private socket required")
        self.db.execute("SET search_path=pg_temp; SET statement_timeout='90s'")
        for name in ("source_document", "ingestion_asset", "official_price_quote",
                     "official_source_review", "ingestion_checkpoint", "historical_price"):
            self.db.execute(f"CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING ALL)")
        install_cache(self.db)
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
            "reference_period,content,metadata) VALUES(%s,'DANE weekly','DANE',%s,"
            "'application/pdf','original','2022-07-15',%s,%s)",
            (SHA, JUL2022_PENDING_URL, self.body, Jsonb({"ingestion_kind": "dane-weekly-pdf"})),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,"
            "observed_on,checked_at,records) VALUES(%s,'dane-weekly-pdf',"
            "'awaiting-ocr',%s,%s,'2022-07-15',now()-interval '7 hours',0)",
            (JUL2022_PENDING_URL, JUL2022_OLD_ASSET_VERSION, SHA),
        )
        self.deadline_token = worker.RUN_DEADLINE.set(None)
        self.addCleanup(worker.RUN_DEADLINE.reset, self.deadline_token)

    def counts(self):
        return self.db.execute(
            "SELECT (SELECT count(*) FROM official_price_quote WHERE document_id=%s "
            "AND parser_version=%s),"
            "(SELECT count(*) FROM official_source_review WHERE document_id=%s "
            "AND parser_version=%s),"
            "(SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='official:complete')",
            (SHA, JUL2022_QUOTE_VERSION, SHA, JUL2022_QUOTE_VERSION,
             SHA, JUL2022_QUOTE_VERSION),
        ).fetchone()

    def test_first_and_partial_batch_deferrals_resume_all_native_rows_without_duplication(self):
        # First deadline expires after validated reviews, before any quote batch.
        worker.RUN_DEADLINE.set(time.monotonic() - 1)
        with self.assertRaisesRegex(WorkDeferred, "Official source validated"):
            official_sources.publish_rows(
                self.db, self.rows, SHA, "dane-weekly-pdf", source_url=JUL2022_PENDING_URL)
        self.assertEqual(self.counts(), (0, 603, 0))
        self.db.execute(
            "UPDATE ingestion_asset SET status='pending',error=%s,"
            "checked_at=now()-interval '6 hours' WHERE url=%s",
            (REASON, JUL2022_PENDING_URL),
        )
        self.assertIn(JUL2022_PENDING_URL,
                      [r[0] for r in queue_plan.repair_candidates(self.db, 5)])
        self.assertEqual(retained_pdf_upgrade(
            self.db, JUL2022_PENDING_URL, "dane-weekly-pdf",
            JUL2022_NEW_ASSET_VERSION, JUL2022_QUOTE_VERSION), self.body)

        # A later worker can crash after exactly one durable 256-quote batch.
        worker.RUN_DEADLINE.set(None)
        with patch("pipelines.ingestion.write_pacing.pause_between_batches",
                   side_effect=WorkDeferred("Committed official quote batches retained; next batch deferred")):
            with self.assertRaises(WorkDeferred):
                official_sources.publish_rows(
                    self.db, self.rows, SHA, "dane-weekly-pdf", source_url=JUL2022_PENDING_URL)
        self.assertEqual(self.counts(), (256, 603, 0))
        self.db.execute("UPDATE ingestion_asset SET error=%s WHERE url=%s",
                        ("Committed official quote batches retained; next batch deferred",
                         JUL2022_PENDING_URL))
        self.assertEqual(retained_pdf_upgrade(
            self.db, JUL2022_PENDING_URL, "dane-weekly-pdf",
            JUL2022_NEW_ASSET_VERSION, JUL2022_QUOTE_VERSION), self.body)

        with patch("pipelines.ingestion.write_pacing.pause_between_batches"):
            self.assertEqual(official_sources.publish_rows(
                self.db, self.rows, SHA, "dane-weekly-pdf", source_url=JUL2022_PENDING_URL), 4225)
            self.assertEqual(official_sources.publish_rows(
                self.db, self.rows, SHA, "dane-weekly-pdf", source_url=JUL2022_PENDING_URL), 4225)
        self.assertEqual(self.counts(), (4225, 603, 1))
        self.assertIsNone(retained_pdf_upgrade(
            self.db, JUL2022_PENDING_URL, "dane-weekly-pdf",
            JUL2022_NEW_ASSET_VERSION, JUL2022_QUOTE_VERSION))


class ExactPendingWorkerBudget(unittest.TestCase):
    def observe(self, budget):
        clock = [0.0]
        seen = []
        db = MagicMock()

        def execute(sql, *args):
            result = MagicMock()
            result.fetchone.return_value = (True,)
            result.fetchall.return_value = []
            return result

        def process(_db, url, kind, day):
            seen.append((url, worker.RUN_DEADLINE.get()))
            if url == JUL2022_PENDING_URL:
                clock[0] = worker.RUN_DEADLINE.get()
                raise WorkDeferred(REASON)
            return 1

        db.execute.side_effect = execute
        with (
            patch.object(worker, "connect") as connect,
            patch.object(worker, "discover", return_value=[]),
            patch("pipelines.ingestion.official_sources.discover_roots"),
            patch.object(worker, "refresh_catalog", return_value={}),
            patch.object(worker.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(worker, "process_asset", side_effect=process),
            patch.object(queue_plan, "supply_validation_retry", return_value=[]),
            patch.object(queue_plan, "city_catchup_candidates", return_value=[]),
            patch.object(queue_plan, "repair_candidates", return_value=[
                (JUL2022_PENDING_URL, "dane-weekly-pdf", date(2022, 7, 15)),
                ("other-kind", "milk-pdf", None),
            ]),
            patch.object(queue_plan, "historical_candidates", return_value=[]),
            patch.object(queue_plan, "recent_pending_daily_pdf_candidates", return_value=[]),
            patch.object(queue_plan, "daily_candidates", return_value=[]),
            patch.object(queue_plan, "current_dane_candidates", return_value=[]),
            patch.object(queue_plan, "backfill_candidates", return_value=[]),
            patch("pipelines.ingestion.retained_replays.drain", return_value={}),
            patch("pipelines.ingestion.ocr.drain", return_value={}),
        ):
            connect.return_value.__enter__.return_value = db
            summary = worker.run("backfill", limit=10, time_budget=budget)
        self.assertIsNone(worker.RUN_DEADLINE.get())
        return seen, summary

    def test_selected_retry_gets_ninety_seconds_and_next_source_keeps_parent_budget(self):
        seen, summary = self.observe(200)
        self.assertEqual(seen, [(JUL2022_PENDING_URL, 90), ("other-kind", 200)])
        self.assertEqual(summary["assets"], 1)
        self.assertEqual([r["url"] for r in summary["deferred"]], [JUL2022_PENDING_URL])

    def test_global_deadline_ceils_exact_retry_and_stops_next_source(self):
        seen, summary = self.observe(60)
        self.assertEqual(seen, [(JUL2022_PENDING_URL, 60)])
        self.assertTrue(summary["time_budget_reached"])


if __name__ == "__main__":
    unittest.main()

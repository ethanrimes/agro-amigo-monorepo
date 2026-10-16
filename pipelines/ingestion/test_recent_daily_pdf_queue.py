"""Bounded daily-PDF gap/retry scheduling against real private PostgreSQL."""

import getpass
import random
import shutil
import subprocess
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg

from . import queue_plan, worker
from .resumable_inputs import WorkDeferred


TODAY = date(2026, 10, 4)


class RecentDailyPdfSelectionPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-recent-daily-pdf-pg-", dir="/tmp"))
        cls.cluster = cls.directory / "data"
        cls.port = random.randrange(41000, 49000)
        try:
            subprocess.run(
                ["initdb", "-D", str(cls.cluster), "--auth=trust", "--no-locale"],
                check=True, stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                ["pg_ctl", "-D", str(cls.cluster), "-l", str(cls.directory / "postgres.log"),
                 "-o", f'-k {cls.directory} -p {cls.port} -h ""', "-w", "start"],
                check=True, stdout=subprocess.DEVNULL,
            )
            cls.db = psycopg.connect(
                f"host={cls.directory} port={cls.port} dbname=postgres user={getpass.getuser()}",
                autocommit=True,
            )
            assert str(cls.db.info.host).startswith("/tmp/agro-recent-daily-pdf-pg-")
            cls.db.execute("SET search_path=pg_temp")
            cls.db.execute(
                """CREATE TEMP TABLE ingestion_asset(
                  url text PRIMARY KEY,kind text,status text,observed_on date,
                  checked_at timestamptz,discovered_at timestamptz)"""
            )
            with cls.db.cursor() as cur:
                with cur.copy(
                    "COPY ingestion_asset(url,kind,status,observed_on,checked_at) FROM STDIN"
                ) as copy:
                    for i in range(1622):
                        copy.write_row((
                            f"older-daily-{i:04}", "daily-pdf", "pending",
                            date(2012, 1, 1) + timedelta(days=i), None,
                        ))
            cls.db.execute(
                """INSERT INTO ingestion_asset(url,kind,status,observed_on,checked_at) VALUES
                  ('aug21','daily-pdf','pending','2026-08-21',NULL),
                  ('aug20','daily-pdf','pending','2026-08-20',NULL),
                  ('due-retry','daily-pdf','pending','2026-08-19',now()-interval '7 hours'),
                  ('cooldown-retry','daily-pdf','pending','2026-08-18',now()-interval '1 hour'),
                  ('old-boundary','daily-pdf','pending','2026-07-06',NULL),
                  ('outside-90-days','daily-pdf','pending','2026-07-05',NULL),
                  ('fresh','daily-pdf','pending','2026-09-21',NULL),
                  ('exact-14-days','daily-pdf','pending','2026-09-20',NULL),
                  ('future','daily-pdf','pending','2026-10-05',NULL),
                  ('review','daily-pdf','review','2026-08-22',NULL),
                  ('failed','daily-pdf','failed','2026-08-23',NULL),
                  ('other-kind','daily','pending','2026-08-24',NULL)"""
            )
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        db = getattr(cls, "db", None)
        if db is not None:
            db.close()
        cluster = getattr(cls, "cluster", None)
        if cluster is not None and cluster.exists():
            subprocess.run(
                ["pg_ctl", "-D", str(cluster), "-m", "fast", "-w", "stop"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        directory = getattr(cls, "directory", None)
        if directory is not None:
            shutil.rmtree(directory, ignore_errors=True)

    def setUp(self):
        self.db.execute("BEGIN")

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def urls(self, limit=2):
        return [r[0].decode() if isinstance(r[0], bytes) else r[0]
                for r in queue_plan.recent_pending_daily_pdf_candidates(self.db, TODAY, limit)]

    def test_1622_older_assets_cannot_starve_newest_gap_and_due_retry(self):
        # The exact 14-day boundary is a separate, even fresher candidate.
        self.db.execute("UPDATE ingestion_asset SET status='complete' WHERE url='exact-14-days'")
        self.assertEqual(self.urls(), ["aug21", "due-retry"])
        self.assertEqual(self.urls(1), ["aug21"])
        self.assertEqual(self.urls(0), [])
        self.assertEqual(self.urls(100), ["aug21", "due-retry"])
        self.db.execute("UPDATE ingestion_asset SET status='complete' WHERE url='aug21'")
        self.assertEqual(self.urls(), ["aug20", "due-retry"])
        self.db.execute(
            "UPDATE ingestion_asset SET checked_at=now()-interval '1 hour' WHERE url='due-retry'"
        )
        self.assertEqual(self.urls(), ["aug20"])

    def test_boundaries_and_unrelated_review_failed_stay_out(self):
        self.db.execute(
            "UPDATE ingestion_asset SET status='complete' WHERE url IN ('aug21','aug20')"
        )
        self.assertEqual(self.urls(), ["exact-14-days", "due-retry"])
        self.db.execute("UPDATE ingestion_asset SET status='complete' WHERE url='exact-14-days'")
        self.assertEqual(self.urls(), ["old-boundary", "due-retry"])
        self.db.execute("UPDATE ingestion_asset SET status='complete' WHERE url='old-boundary'")
        self.assertEqual(self.urls(), ["due-retry"])


class RecentDailyPdfWorkerRuntime(unittest.TestCase):
    def run_case(self, *, mode="backfill", recent=(), repair=(), historical=(),
                 fresh=(), backlog=(), limit=8, blocked_host=False, defer=None,
                 exhaust_fresh=None):
        db = MagicMock()
        clock = [0.0]
        observed = []

        def execute(sql, *args):
            result = MagicMock()
            result.fetchone.return_value = (
                None if sql in (queue_plan.CITY_DUE_SQL, queue_plan.CITY_RECENT_SQL) else (True,)
            )
            result.fetchall.return_value = (
                [("www.dane.gov.co", datetime.now(timezone.utc) + timedelta(hours=1))]
                if blocked_host and "SELECT host,retry_at FROM source_host_cooldown" in sql
                else []
            )
            return result

        db.execute.side_effect = execute

        def process(_db, url, kind, day):
            observed.append((url, worker.RUN_DEADLINE.get()))
            if url == defer:
                clock[0] = worker.RUN_DEADLINE.get()
                raise WorkDeferred("A source retained its partial checkpoint")
            if url == exhaust_fresh:
                clock[0] = worker.RUN_DEADLINE.get()
            return 1

        with (
            patch.object(worker, "connect") as connect,
            patch.object(worker, "discover", return_value=[]),
            patch("pipelines.ingestion.official_sources.discover_roots"),
            patch.object(worker, "refresh_catalog", return_value={}),
            patch.object(worker.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(worker, "process_asset", side_effect=process),
            patch.object(worker, "HostCooldowns") as cooldown_type,
            patch.object(worker, "retained_reparse_during_host_cooldown", return_value=False),
            patch.object(queue_plan, "supply_validation_retry", return_value=[]),
            patch.object(queue_plan, "repair_candidates", return_value=list(repair)),
            patch.object(queue_plan, "historical_candidates", return_value=list(historical)),
            patch.object(queue_plan, "daily_candidates", return_value=list(fresh)),
            patch.object(queue_plan, "current_dane_candidates", return_value=[]),
            patch.object(queue_plan, "recent_pending_daily_pdf_candidates", return_value=list(recent)) as selector,
            patch.object(queue_plan, "backfill_candidates", return_value=list(backlog)),
            patch("pipelines.ingestion.retained_replays.drain", return_value={}),
            patch("pipelines.ingestion.ocr.drain", return_value={}),
        ):
            connect.return_value.__enter__.return_value = db
            cooldown_type.return_value.blocked.side_effect = (
                lambda url: datetime.now(timezone.utc) + timedelta(hours=1)
                if blocked_host and url.startswith("https://www.dane.gov.co/") else None
            )
            result = worker.run(mode, limit=limit, time_budget=200)
        self.assertIsNone(worker.RUN_DEADLINE.get())
        return result, observed, selector

    def test_reserved_order_deadline_deferral_and_dedup(self):
        result, observed, selector = self.run_case(
            repair=[("repair", "milk-pdf", None)],
            historical=[("old", "dane-weekly-pdf", date(2012, 6, 29))],
            fresh=[("gap", "daily-pdf", date(2026, 8, 21)),
                   ("fresh", "daily", date(2026, 10, 3))],
            recent=[("gap", "daily-pdf", date(2026, 8, 21)),
                    ("retry", "daily-pdf", date(2026, 8, 19))],
            backlog=[("gap", "daily-pdf", date(2026, 8, 21)),
                     ("back", "daily", None)], defer="gap",
        )
        self.assertEqual(selector.call_count, 1)
        self.assertEqual([x[0] for x in observed],
                         ["repair", "old", "gap", "retry", "fresh", "back"])
        self.assertEqual([x[1] for x in observed], [200, 90, 90, 180, 200, 200])
        self.assertEqual(result["assets"], 5)
        self.assertEqual([x["url"] for x in result["deferred"]], ["gap"])
        self.assertEqual(len(result["recent_daily_pdf_lane"]["selected"]), 2)

    def test_old_history_and_gap_run_before_long_fresh_consumes_budget(self):
        result, observed, _ = self.run_case(
            historical=[("old-2012", "dane-weekly-pdf", date(2012, 6, 29))],
            recent=[("aug21-gap", "daily-pdf", date(2026, 8, 21))],
            fresh=[("large-fresh", "inputs", date(2026, 10, 3))],
            backlog=[("ordinary-backlog", "daily", None)],
            exhaust_fresh="large-fresh",
        )
        self.assertEqual([x[0] for x in observed],
                         ["old-2012", "aug21-gap", "large-fresh"])
        self.assertEqual([x[1] for x in observed], [90, 90, 200])
        self.assertEqual(result["assets"], 3)
        self.assertTrue(result["time_budget_reached"])

    def test_due_retry_advances_without_never_attempted_gap(self):
        result, observed, _ = self.run_case(
            recent=[("due-retry", "daily-pdf", date(2026, 8, 19))],
            fresh=[("large-fresh", "inputs", date(2026, 10, 3))],
            exhaust_fresh="large-fresh",
        )
        self.assertEqual([x[0] for x in observed], ["due-retry", "large-fresh"])
        self.assertEqual([x[1] for x in observed], [90, 200])
        self.assertEqual(result["assets"], 2)

    def test_host_cooldown_blocks_only_affected_recent_url(self):
        blocked = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-21ago2026.pdf"
        result, observed, _ = self.run_case(
            recent=[(blocked, "daily-pdf", date(2026, 8, 21))],
            fresh=[("fresh", "daily", date(2026, 10, 3))],
            blocked_host=True,
        )
        self.assertEqual([x[0] for x in observed], ["fresh"])
        self.assertEqual(result["deferred_hosts"]["www.dane.gov.co"]["count"], 1)

    def test_daily_mode_and_small_cap_preserve_existing_behavior(self):
        daily, observed, selected = self.run_case(
            mode="daily", fresh=[("fresh", "daily", date(2026, 10, 3))]
        )
        selected.assert_not_called()
        self.assertEqual([x[0] for x in observed], ["fresh"])
        self.assertNotIn("recent_daily_pdf_lane", daily)

        capped, observed, _ = self.run_case(
            limit=3,
            repair=[("repair", "milk-pdf", None)],
            historical=[("old", "dane-weekly-pdf", date(2012, 6, 29))],
            fresh=[("fresh", "daily", date(2026, 10, 3))],
            recent=[("gap", "daily-pdf", date(2026, 8, 21))],
        )
        self.assertEqual([x[0] for x in observed], ["repair", "old", "gap"])
        self.assertEqual(capped["assets"], 3)
        self.assertTrue(capped["asset_limit_reached"])


if __name__ == "__main__":
    unittest.main()

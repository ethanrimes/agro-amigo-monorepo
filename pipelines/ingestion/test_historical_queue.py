"""A bounded old-source lane survives newer backlogs without relaxing reviews."""

import getpass
import random
import shutil
import subprocess
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg

from . import queue_plan, worker
from .resumable_inputs import WorkDeferred


class _ClockedDb:
    """Pin only the proposed hourly rotation in a private PostgreSQL test."""

    def __init__(self, db, rotation):
        self.db = db
        self.rotation = rotation

    def execute(self, sql, params=()):
        needle = "floor(extract(epoch FROM now())/3600)::bigint"
        if "clock AS" in sql:
            assert needle in sql
            sql = sql.replace(needle, str(self.rotation))
        return self.db.execute(sql, params)


def _urls(rows):
    return [row[0].decode() if isinstance(row[0], bytes) else row[0] for row in rows]


class HistoricalQueuePostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-historical-queue-pg-", dir="/tmp"))
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
            assert str(cls.db.info.host).startswith("/tmp/agro-historical-queue-pg-")
            cls.db.execute("SET search_path=pg_temp")
            cls.db.execute(
                """CREATE TEMP TABLE ingestion_asset(
                  url text PRIMARY KEY,kind text,status text,error text,
                  checked_at timestamptz,observed_on date,processor_version text,
                  document_id text,discovered_at timestamptz)"""
            )
            cls.db.execute(
                """CREATE TEMP TABLE official_source_review(
                  document_id text,parser_version text,source_locator text,record jsonb)"""
            )
            with cls.db.cursor() as cur:
                with cur.copy(
                    """COPY ingestion_asset(url,kind,status,error,checked_at,
                       observed_on,processor_version,document_id,discovered_at) FROM STDIN"""
                ) as copy:
                    for i in range(2000):
                        copy.write_row((
                            f"new-weekly-{i:04}", "dane-weekly-pdf", "pending",
                            None, None, date(2020, 1, 1) + timedelta(days=i), "", None, None,
                        ))
                    for i in range(26):
                        copy.write_row((
                            f"old-weekly-{i:02}", "dane-weekly-pdf", "pending",
                            None, None, date(2012, 6, 29) + timedelta(days=7*i), "", None, None,
                        ))
                    for kind, day in (
                        ("inputs-pdf", date(2013, 7, 31)),
                        ("dane-weekly-xlsx", date(2015, 1, 9)),
                        ("daily", date(2016, 8, 17)),
                        ("monthly-pdf", date(2017, 7, 31)),
                        ("daily-pdf", date(2019, 12, 24)),
                        ("city-pdf", date(2024, 5, 18)),
                        ("city-zip", date(2021, 6, 14)),
                    ):
                        copy.write_row(("old-" + kind, kind, "pending", None,
                                        None, day, "", None, None))
                    for url, kind, status, day in (
                        ("terminal-review", "dane-weekly-pdf", "review", date(2011, 1, 1)),
                        ("finished", "dane-weekly-pdf", "complete", date(2010, 1, 1)),
                        ("press-review", "monthly-pdf", "review", date(2011, 1, 1)),
                    ):
                        copy.write_row((url, kind, status, None, None, day, "old", None, None))
            cls.db.execute(
                """INSERT INTO ingestion_asset VALUES
                  ('recent-failure','dane-weekly-pdf','failed','HTTP 404',
                   now()-interval '1 hour','2009-01-01','old',NULL,now()),
                  ('deferred-older','dane-weekly-pdf','pending','WorkDeferred',
                   now()-interval '7 hours','2012-01-01','old',NULL,now())"""
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

    def test_two_thousand_newer_weeklies_do_not_hide_earliest_2012(self):
        self.assertNotIn("old-weekly-00", _urls(queue_plan.backfill_candidates(self.db, 1000)))
        self.assertEqual(
            _urls(queue_plan.historical_candidates(_ClockedDb(self.db, 0), 5))[0],
            "old-weekly-00",
        )

    def test_five_slots_rotate_seven_other_families_without_starvation(self):
        selections = []
        for rotation in range(7):
            rows = queue_plan.historical_candidates(_ClockedDb(self.db, rotation), 5)
            selected = _urls(rows)
            self.assertEqual(len(selected), len(set(selected)))
            self.assertEqual(len(selected), 5)
            self.assertEqual(selected[0], "old-weekly-00")
            self.assertFalse({"terminal-review", "finished", "press-review", "recent-failure"} & set(selected))
            selections.append(selected)
        for kind in ("inputs-pdf", "dane-weekly-xlsx", "daily", "monthly-pdf", "daily-pdf", "city-pdf", "city-zip"):
            self.assertEqual(sum("old-" + kind in selected for selected in selections), 4)

    def test_never_attempted_rotates_before_deferral_then_cooldown_controls_retry(self):
        self.db.execute("UPDATE ingestion_asset SET status='complete' WHERE url='old-weekly-00'")
        self.assertEqual(_urls(queue_plan.historical_candidates(_ClockedDb(self.db, 0), 5))[0], "old-weekly-01")
        self.db.execute(
            "UPDATE ingestion_asset SET checked_at=now()-interval '7 hours' WHERE url='old-weekly-01'"
        )
        self.assertEqual(_urls(queue_plan.historical_candidates(_ClockedDb(self.db, 0), 5))[0], "old-weekly-02")
        self.db.execute("UPDATE ingestion_asset SET status='complete' WHERE url LIKE 'old-weekly-%' OR url LIKE 'new-weekly-%'")
        self.assertEqual(_urls(queue_plan.historical_candidates(_ClockedDb(self.db, 0), 5))[0], "deferred-older")
        self.db.execute("UPDATE ingestion_asset SET status='complete' WHERE url='deferred-older'")
        self.assertNotIn("recent-failure", _urls(queue_plan.historical_candidates(_ClockedDb(self.db, 0), 5)))
        self.db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '7 hours' WHERE url='recent-failure'")
        self.assertEqual(_urls(queue_plan.historical_candidates(_ClockedDb(self.db, 0), 5))[0], "recent-failure")

    def test_zero_and_oversized_limits_are_bounded(self):
        self.assertEqual(queue_plan.historical_candidates(self.db, 0), [])
        self.assertEqual(len(queue_plan.historical_candidates(_ClockedDb(self.db, 0), 1000)), 5)

    def test_merged_run_keeps_fifty_fresh_slots_and_total_cap(self):
        repair = [(f"repair-{i}", "milk-pdf", None) for i in range(5)]
        fresh = [(f"fresh-{i}", "daily", None) for i in range(50)]
        historic = queue_plan.historical_candidates(_ClockedDb(self.db, 0), 5)
        backlog = queue_plan.backfill_candidates(self.db, 100)
        seen = set()
        merged = []
        for row in repair + historic + fresh + backlog:
            if row[0] not in seen:
                seen.add(row[0])
                merged.append(row)
            if len(merged) == 100:
                break
        self.assertEqual(len(merged), 100)
        self.assertEqual(_urls(merged)[5], "old-weekly-00")
        self.assertTrue({row[0] for row in fresh} <= set(_urls(merged)))
        self.assertEqual(len({row[0] for row in merged}), 100)


class HistoricalWorkerRun(unittest.TestCase):
    """Exercise actual worker.run ordering and deadlines with isolated callbacks."""

    def run_case(self, *, mode="backfill", limit=6, budget=200,
                 historical=(), fresh=(), repairs=(), backlog=(),
                 asset_url=None, process=None):
        clock = [0.0]
        observed = []
        db = MagicMock()

        def execute(sql, *args):
            result = MagicMock()
            result.fetchone.return_value = (True,)
            if "SELECT url,kind,observed_on FROM ingestion_asset WHERE url=" in sql:
                result.fetchall.return_value = [(asset_url, "daily", None)]
            return result

        db.execute.side_effect = execute

        def process_asset(_db, url, kind, day):
            observed.append((url, worker.RUN_DEADLINE.get(), clock[0]))
            if process:
                return process(url, kind, clock)
            return 1

        with (
            patch.object(worker, "connect") as connect,
            patch.object(worker, "discover", return_value=[]),
            patch("pipelines.ingestion.official_sources.discover_roots"),
            patch.object(worker, "refresh_catalog", return_value={}),
            patch.object(worker.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(worker, "process_asset", side_effect=process_asset),
            patch.object(queue_plan, "supply_validation_retry", return_value=[]),
            patch.object(queue_plan, "repair_candidates", return_value=list(repairs)),
            patch.object(queue_plan, "historical_candidates", return_value=list(historical)) as selected,
            patch.object(queue_plan, "city_catchup_candidates", return_value=[]),
            patch.object(queue_plan, "recent_pending_daily_pdf_candidates", return_value=[]),
            patch.object(queue_plan, "daily_candidates", return_value=list(fresh)),
            patch.object(queue_plan, "current_dane_candidates", return_value=[]),
            patch.object(queue_plan, "backfill_candidates", return_value=list(backlog)),
            patch("pipelines.ingestion.retained_replays.drain", return_value={}),
            patch("pipelines.ingestion.ocr.drain", return_value={}),
        ):
            connect.return_value.__enter__.return_value = db
            result = worker.run(
                mode, limit=limit, time_budget=budget, asset_url=asset_url,
            )
        self.assertIsNone(worker.RUN_DEADLINE.get())
        return result, observed, selected

    def test_deferred_historical_file_leaves_fresh_window_and_restores_deadline(self):
        def process(url, kind, clock):
            if url == "old":
                self.assertEqual(worker.RUN_DEADLINE.get(), 90)
                clock[0] = 90
                raise WorkDeferred("old native page checkpoint needs more time")
            return 1

        result, observed, _ = self.run_case(
            historical=[("old", "dane-weekly-pdf", date(2012, 6, 29))],
            fresh=[("fresh", "daily", date(2026, 10, 3))],
            process=process,
        )
        self.assertEqual([url for url, _, _ in observed], ["old", "fresh"])
        self.assertEqual([deadline for _, deadline, _ in observed], [90, 200])
        self.assertEqual(result["assets"], 1)
        self.assertEqual([row["url"] for row in result["deferred"]], ["old"])
        self.assertEqual(len(result["historical_lane"]["selected"]), 1)

    def test_historical_deadline_obeys_parent_ceiling_and_resets(self):
        result, observed, _ = self.run_case(
            budget=60,
            historical=[("old", "dane-weekly-pdf", date(2012, 6, 29))],
            fresh=[("fresh", "daily", date(2026, 10, 3))],
        )
        self.assertEqual([deadline for _, deadline, _ in observed], [60, 60])
        self.assertEqual(result["assets"], 2)

    def test_repair_keeps_own_budget_and_fresh_duplicate_uses_prior_historical_slot(self):
        result, observed, _ = self.run_case(
            repairs=[("repair", "milk-pdf", date(2024, 11, 30))],
            historical=[
                ("repair", "milk-pdf", date(2024, 11, 30)),
                ("also-fresh", "daily", date(2026, 10, 3)),
                ("old-only", "dane-weekly-pdf", date(2012, 6, 29)),
            ],
            fresh=[("also-fresh", "daily", date(2026, 10, 3)),
                   ("fresh", "daily", date(2026, 10, 3))],
        )
        self.assertEqual([url for url, _, _ in observed],
                         ["repair", "also-fresh", "old-only", "fresh"])
        self.assertEqual([deadline for _, deadline, _ in observed],
                         [200, 90, 90, 200])
        self.assertEqual(result["assets"], 4)

    def test_daily_and_targeted_runs_do_not_select_historical_lane(self):
        daily, observed, selector = self.run_case(
            mode="daily", fresh=[("fresh", "daily", date(2026, 10, 3))],
        )
        selector.assert_not_called()
        self.assertEqual([url for url, _, _ in observed], ["fresh"])
        self.assertNotIn("historical_lane", daily)
        targeted, observed, selector = self.run_case(
            mode="backfill", asset_url="target",
            fresh=[("fresh", "daily", date(2026, 10, 3))],
        )
        selector.assert_not_called()
        self.assertEqual([url for url, _, _ in observed], ["target"])
        self.assertNotIn("historical_lane", targeted)

    def test_historical_lane_does_not_raise_total_asset_cap(self):
        result, observed, _ = self.run_case(
            limit=3,
            repairs=[("repair", "milk-pdf", None)],
            historical=[("old-a", "dane-weekly-pdf", date(2012, 6, 29)),
                        ("old-b", "dane-weekly-xlsx", date(2015, 1, 9))],
            fresh=[("fresh", "daily", date(2026, 10, 3))],
        )
        self.assertEqual([url for url, _, _ in observed], ["repair", "old-a", "old-b"])
        self.assertEqual(result["assets"], 3)
        self.assertTrue(result["asset_limit_reached"])


if __name__ == "__main__":
    unittest.main()

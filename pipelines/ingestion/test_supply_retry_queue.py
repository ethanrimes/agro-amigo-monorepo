"""A deferred whole-source supply validation gets time before large fresh inputs."""

import os
import unittest
from unittest.mock import MagicMock, patch

from . import queue_plan, worker
from .resumable_inputs import WorkDeferred


class SupplyRetryRuntimeTests(unittest.TestCase):
    def execute_run(self, mode, retry, fresh, backlog, durations):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (True,)
        clock = [0]
        seen = []

        def process(_db, url, kind, day):
            seen.append(url)
            clock[0] += durations[url]
            if clock[0] > worker.RUN_DEADLINE.get():
                raise WorkDeferred("Supply native validation exceeded the run budget")
            return 1

        with (
            patch.object(worker, "connect") as connect,
            patch.object(worker, "refresh_catalog", return_value=0),
            patch.object(worker, "discover", return_value=[]),
            patch("pipelines.ingestion.official_sources.discover_roots"),
            patch.object(worker.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(
                queue_plan, "supply_validation_retry", return_value=retry
            ) as retries,
            patch.object(queue_plan, "daily_candidates", return_value=fresh),
            patch.object(queue_plan, "backfill_candidates", return_value=backlog),
            patch.object(worker, "process_asset", side_effect=process),
            patch("pipelines.ingestion.retained_replays.drain", return_value={}),
            patch("pipelines.ingestion.ocr.drain", return_value={}),
        ):
            connect.return_value.__enter__.return_value = db
            result = worker.run(mode, limit=6, time_budget=100)
        return result, seen, retries.call_count

    def test_supply_validation_finishes_before_fresh_work_can_consume_its_window(self):
        supply = ("supply", "supply", None)
        fresh = ("fresh", "inputs", None)
        other = ("other", "daily", None)
        result, seen, calls = self.execute_run(
            "backfill",
            [supply],
            [fresh],
            [supply, other],
            {"supply": 60, "fresh": 60, "other": 1},
        )
        self.assertEqual(seen, ["supply", "fresh"])
        self.assertEqual(result["assets"], 1)
        self.assertEqual([r["url"] for r in result["deferred"]], ["fresh"])
        self.assertEqual(calls, 1)

    def test_retry_is_not_processed_twice_when_present_in_all_lanes(self):
        supply = ("supply", "supply", None)
        result, seen, _ = self.execute_run(
            "backfill",
            [supply],
            [supply],
            [supply],
            {"supply": 101},
        )
        self.assertEqual(seen, ["supply"])
        self.assertEqual(result["assets"], 0)
        self.assertEqual(len(result["deferred"]), 1)

    def test_daily_refresh_keeps_its_current_source_order(self):
        result, seen, calls = self.execute_run(
            "daily",
            [("supply", "supply", None)],
            [("fresh", "daily", None)],
            [],
            {"fresh": 1},
        )
        self.assertEqual(seen, ["fresh"])
        self.assertEqual(calls, 0)
        self.assertEqual(result["assets"], 1)


@unittest.skipUnless(
    os.environ.get("AGRO_SUPPLY_POSTGRES_TEST") == "1",
    "Isolated local PostgreSQL opt-in",
)
class SupplyRetrySelectionTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.info.host.startswith("/tmp/agro-"))
        self.db.execute("SET search_path=pg_temp")
        self.db.execute(
            "CREATE TEMP TABLE ingestion_asset(url text,kind text,status text,error text,checked_at timestamptz,observed_on date)"
        )

    def add(
        self,
        url,
        kind="supply",
        status="pending",
        error="Supply native validation exceeded the run budget",
        hours=7,
    ):
        self.db.execute(
            "INSERT INTO ingestion_asset VALUES(%s,%s,%s,%s,now()-make_interval(hours=>%s),'2023-01-01')",
            (url, kind, status, error, hours),
        )

    def test_only_eligible_time_budget_deferrals_get_one_slot(self):
        self.add("newly discovered", error=None)
        self.add("wrong source kind", kind="inputs")
        self.add("review", status="review")
        self.add("failed", status="failed")
        self.add("finished", status="complete")
        self.add("invalid date", error="Invalid supply date 2023:47")
        self.add("not due", hours=1)
        self.add("older interrupted", hours=10)
        self.add("newer interrupted", hours=8)
        rows = queue_plan.supply_validation_retry(self.db)
        self.assertEqual([r[0] for r in rows], ["older interrupted"])

    def test_completed_retry_cannot_block_the_next_source(self):
        self.add("a", hours=10)
        self.add(
            "b", error="Supply native validation deferred before starting", hours=8
        )
        self.assertEqual(queue_plan.supply_validation_retry(self.db)[0][0], "a")
        self.db.execute(
            "UPDATE ingestion_asset SET status='complete',error=NULL WHERE url='a'"
        )
        self.assertEqual(queue_plan.supply_validation_retry(self.db)[0][0], "b")

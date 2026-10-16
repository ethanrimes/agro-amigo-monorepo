"""Queue selection cancellation, recovery and exact-source version drift."""

import getpass
import random
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg

from .queue_plan import bounded_selection


PG16_BIN = Path("/opt/homebrew/opt/postgresql@16/bin")


def postgres_binary(name):
    found = shutil.which(name)
    if found:
        return found
    candidate = PG16_BIN / name
    return str(candidate) if candidate.is_file() else None


class BoundedSelectionPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initdb = postgres_binary("initdb")
        cls.pg_ctl = postgres_binary("pg_ctl")
        if not cls.initdb or not cls.pg_ctl:
            raise unittest.SkipTest("Disposable PostgreSQL binaries unavailable")

        cls.directory = Path(tempfile.mkdtemp(prefix="agro-queue-selection-pg-", dir="/tmp"))
        cls.socket_dir = cls.directory / "socket"
        cls.socket_dir.mkdir()
        cls.cluster = cls.directory / "cluster"
        with socket.socket() as free_port:
            free_port.bind(("127.0.0.1", 0))
            cls.port = free_port.getsockname()[1]

        subprocess.run(
            [cls.initdb, "-D", str(cls.cluster), "--auth=trust", "--no-locale", "--encoding=UTF8"],
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            [cls.pg_ctl, "-D", str(cls.cluster), "-l", str(cls.directory / "postgres.log"),
             "-o", f'-h "" -k "{cls.socket_dir}" -p {cls.port}', "-w", "start"],
            check=True, capture_output=True, text=True,
        )
        pid_file = cls.cluster / "postmaster.pid"
        pid_lines = pid_file.read_text().splitlines()
        if len(pid_lines) < 2 or Path(pid_lines[1]) != cls.cluster:
            raise RuntimeError("Disposable PostgreSQL identity did not match its owned cluster")
        cls.postmaster_pid = int(pid_lines[0])
        cls.dsn = (
            f"host={cls.socket_dir} port={cls.port} dbname=postgres "
            f"user={getpass.getuser()}"
        )
        with psycopg.connect(cls.dsn, autocommit=True) as probe:
            if probe.info.host != str(cls.socket_dir):
                raise RuntimeError("Test connection escaped its owned Unix socket")
            if probe.execute("SELECT inet_server_addr()").fetchone()[0] is not None:
                raise RuntimeError("Disposable PostgreSQL unexpectedly accepts TCP connections")

    @classmethod
    def tearDownClass(cls):
        cluster = getattr(cls, "cluster", None)
        directory = getattr(cls, "directory", None)
        if cluster is None or directory is None or not (cluster / "postmaster.pid").exists():
            if directory is not None:
                shutil.rmtree(directory, ignore_errors=True)
            return

        pid_lines = (cluster / "postmaster.pid").read_text().splitlines()
        if (len(pid_lines) < 2 or int(pid_lines[0]) != cls.postmaster_pid
                or Path(pid_lines[1]) != cluster):
            raise RuntimeError("Refusing to stop a PostgreSQL process with changed identity")
        subprocess.run(
            [cls.pg_ctl, "-D", str(cluster), "-m", "fast", "-w", "stop"],
            check=True, capture_output=True, text=True,
        )
        if (cluster / "postmaster.pid").exists():
            raise RuntimeError("Owned PostgreSQL still has a postmaster.pid after stop")
        shutil.rmtree(directory)

    def setUp(self):
        self.db = psycopg.connect(self.dsn, autocommit=True)
        self.addCleanup(self.db.close)
        self.db.execute("SET statement_timeout='2s'")
        self.db.execute("CREATE TEMP TABLE queue_fixture(id integer primary key, value text not null)")
        self.db.execute("INSERT INTO queue_fixture VALUES (1, 'kept')")

    def test_timeout_discards_partial_rows_and_following_lane_succeeds(self):
        before = self.db.execute(
            "SELECT value,xmin::text FROM queue_fixture WHERE id=1"
        ).fetchone()

        def canceled_lane():
            yield from self.db.execute("SELECT value FROM queue_fixture ORDER BY id").fetchall()
            self.db.execute("SELECT pg_sleep(0.25)").fetchone()
            yield ("must not escape",)

        timed_out = bounded_selection(
            self.db, "slow-fixture", canceled_lane, max_ms=40,
        )
        self.assertEqual(timed_out.rows, ())
        self.assertEqual(timed_out.diagnostic, {
            "lane": "slow-fixture", "status": "deferred",
            "reason": "statement_timeout", "error": "QueryCanceled", "sqlstate": "57014",
        })
        self.assertEqual(self.db.execute("SHOW statement_timeout").fetchone()[0], "2s")

        next_lane = bounded_selection(
            self.db, "following-fixture",
            lambda: self.db.execute("SELECT value FROM queue_fixture ORDER BY id").fetchall(),
            max_ms=500,
        )
        self.assertEqual(next_lane.rows, (("kept",),))
        self.assertIsNone(next_lane.diagnostic)
        self.assertEqual(
            self.db.execute("SELECT value,xmin::text FROM queue_fixture WHERE id=1").fetchone(),
            before,
        )
        self.assertEqual(self.db.execute("SHOW statement_timeout").fetchone()[0], "2s")

    def test_expired_deadline_defers_without_invoking_callback(self):
        invoked = []
        result = bounded_selection(
            self.db, "expired-fixture", lambda: invoked.append(True),
            deadline=time.monotonic() - 0.001,
        )
        self.assertEqual(invoked, [])
        self.assertEqual(result.rows, ())
        self.assertEqual(result.diagnostic, {
            "lane": "expired-fixture", "status": "deferred",
            "reason": "deadline_exhausted",
        })
        self.assertEqual(self.db.execute("SHOW statement_timeout").fetchone()[0], "2s")

    def test_success_materializes_rows_and_restores_timeout(self):
        result = bounded_selection(
            self.db, "success-fixture",
            lambda: self.db.execute("SELECT value FROM queue_fixture ORDER BY id").fetchall(),
            max_ms=500,
        )
        self.assertEqual(result.rows, (("kept",),))
        self.assertIsNone(result.diagnostic)
        self.assertEqual(self.db.execute("SHOW statement_timeout").fetchone()[0], "2s")

    def test_non_timeout_database_errors_propagate(self):
        with self.assertRaises(psycopg.errors.DivisionByZero):
            bounded_selection(
                self.db, "invalid-fixture",
                lambda: self.db.execute("SELECT 1/0").fetchall(), max_ms=500,
            )
        self.assertEqual(self.db.execute("SELECT 1").fetchone(), (1,))
        self.assertEqual(self.db.execute("SHOW statement_timeout").fetchone()[0], "2s")

    def test_closed_connection_failure_propagates(self):
        self.db.close()
        with self.assertRaises(psycopg.Error):
            bounded_selection(
                self.db, "closed-fixture", lambda: ((1,),), max_ms=500,
            )

    def test_weekly_source_versions_match_every_registered_override(self):
        from . import dane_weekly, queue_plan, worker
        from .reviewed_weekly_feb2014 import PAIRS
        from .reviewed_weekly_native_context import URLS

        pdf_urls = (
            dane_weekly.JANUARY_2017_JAN13_URL, dane_weekly.JUNE_2012_FONT_RUN_URL,
            dane_weekly.AUGUST_2015_WRAP_URL, dane_weekly.AUG2014_PAGE43_URL,
            dane_weekly.NOV2019_COTINUACION_URL,
            dane_weekly.NOVEMBER_2016_MEDELLIN_WRAP_URL,
            dane_weekly.MAY2013_WHITE_CORN_URL, dane_weekly.JULY2012_CONFLICT_URL,
            "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_16jun_20jun_2014.pdf",
        )
        xls_urls = set(dane_weekly.RICE_MONTHLY_CONFLICT_URLS) | set(PAIRS) | set(URLS)
        versions = queue_plan.expected_versions().obj
        for kind, urls in (("dane-weekly-pdf", pdf_urls), ("dane-weekly-xlsx", xls_urls)):
            for url in urls:
                with self.subTest(kind=kind, url=url):
                    self.assertEqual(versions.get("url:" + url),
                                     worker.asset_parser_version(kind, url))
            neighbour = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/unreviewed-neighbour.pdf"
            self.assertNotIn("url:" + neighbour, versions)
            self.assertEqual(versions[kind], worker.parser_version(kind))

    def test_actual_backfill_selects_five_omitted_versions_and_leaves_current_neighbours(self):
        from . import dane_weekly, queue_plan, worker
        from .reviewed_weekly_feb2014 import PAIRS

        # This proves queue eligibility only. Original SHA, metadata and
        # publication guards are independently enforced by the publishers.
        self.db.execute("""CREATE TEMP TABLE ingestion_asset(
          url text PRIMARY KEY, kind text, observed_on date,
          checked_at timestamptz, discovered_at timestamptz DEFAULT now(),
          status text, processor_version text, document_id text, error text);
          CREATE TEMP TABLE official_source_review(
            document_id text, parser_version text, source_locator text, record jsonb);
        """)
        cases = [("dane-weekly-pdf", dane_weekly.AUG2014_PAGE43_URL),
                 ("dane-weekly-pdf", dane_weekly.JULY2012_CONFLICT_URL)]
        cases.extend(("dane-weekly-xlsx", url) for url in PAIRS)
        before = []
        for kind, url in cases:
            self.db.execute("""INSERT INTO ingestion_asset(
              url,kind,observed_on,checked_at,status,processor_version,document_id)
              VALUES(%s,%s,'2014-02-08',now()-interval '1 hour','review',%s,%s)""",
              (url, kind, worker.parser_version(kind), "a" * 64))
            before.append((url, self.db.execute(
                "SELECT xmin::text FROM ingestion_asset WHERE url=%s", (url,)).fetchone()[0]))
        for kind in ("dane-weekly-pdf", "dane-weekly-xlsx"):
            self.db.execute("""INSERT INTO ingestion_asset(
              url,kind,observed_on,checked_at,status,processor_version,document_id)
              VALUES(%s,%s,'2014-02-08',now()-interval '1 hour','complete',%s,%s)""",
              ("https://www.dane.gov.co/unchanged-" + kind, kind,
               worker.parser_version(kind), "b" * 64))

        self.assertEqual({r[0] for r in queue_plan.backfill_candidates(self.db, 100)},
                         {url for _, url in cases})
        self.assertEqual(before, self.db.execute(
            "SELECT url,xmin::text FROM ingestion_asset WHERE document_id=%s ORDER BY array_position(%s::text[],url)",
            ("a" * 64, [url for url, _ in before])).fetchall())
        for kind, url in cases:
            self.db.execute("UPDATE ingestion_asset SET processor_version=%s WHERE url=%s",
                            (worker.asset_parser_version(kind, url), url))
        self.assertEqual(queue_plan.backfill_candidates(self.db, 100), [])

    def test_worker_continues_other_lanes_and_records_partial_after_real_timeout(self):
        from . import queue_plan, worker

        self.db.execute("""
          CREATE TEMP TABLE ingestion_run(
            id uuid PRIMARY KEY, mode text, started_at timestamptz DEFAULT now(),
            status text DEFAULT 'running', finished_at timestamptz, summary jsonb DEFAULT '{}');
          CREATE TEMP TABLE ingestion_asset(url text PRIMARY KEY, kind text, checked_at timestamptz);
          INSERT INTO ingestion_asset VALUES ('https://example.org/fresh.xlsx','daily',NULL);
          INSERT INTO ingestion_run(id,mode,status,finished_at,summary) VALUES
            ('00000000-0000-0000-0000-000000000001','daily','succeeded',now(),
             '{"discovery_finished_at":"done","auxiliary_finished_at":"done"}');
        """)
        before = self.db.execute("SELECT value,xmin::text FROM queue_fixture").fetchall()
        attempted = []

        def slow_repair(*_args):
            self.db.execute("SELECT pg_sleep(0.25)").fetchall()
            return [("must-not-escape", "daily", date(2020, 1, 1))]

        def short_selection(db, lane, callback, **kwargs):
            return bounded_selection(db, lane, callback, max_ms=40, **kwargs)

        with (
            patch.object(worker, "connect", side_effect=lambda: nullcontext(self.db)),
            patch.object(worker, "HostCooldowns") as cooldowns,
            patch.object(worker, "refresh_catalog", return_value={}),
            patch.object(worker, "process_asset", side_effect=lambda _db, url, *_args: attempted.append(url) or 1),
            patch("pipelines.ingestion.label_normalization.drain", return_value={"available": True, "deferred": False}),
            patch("pipelines.ingestion.city_product_backfill.drain", return_value={"completed": 1, "errors": []}),
            patch("pipelines.ingestion.retained_replays.drain", return_value={}),
            patch("pipelines.ingestion.ocr.drain", return_value={}),
            patch.object(queue_plan, "bounded_selection", side_effect=short_selection),
            patch.object(queue_plan, "current_dane_candidates", return_value=[]),
            patch.object(queue_plan, "daily_candidates", return_value=[("https://example.org/fresh.xlsx", "daily", date(2020, 1, 1))]),
            patch.object(queue_plan, "supply_validation_retry", return_value=[]),
            patch.object(queue_plan, "repair_candidates", side_effect=slow_repair),
            patch.object(queue_plan, "historical_candidates", return_value=[]),
            patch.object(queue_plan, "recent_pending_daily_pdf_candidates", return_value=[]),
            patch.object(queue_plan, "city_catchup_candidates", return_value=[]),
            patch.object(queue_plan, "backfill_candidates", return_value=[]),
        ):
            cooldowns.return_value.blocked.return_value = None
            result = worker.run("backfill", limit=2, time_budget=600)

        self.assertEqual(attempted, ["https://example.org/fresh.xlsx"])
        self.assertEqual(result["assets"], 1)
        self.assertEqual(result["city_product_scan"]["completed"], 1)
        self.assertEqual(result["deferred"], [{"source": "queue_selection", "lane": "historical_repairs",
            "status": "deferred", "reason": "statement_timeout", "error": "QueryCanceled", "sqlstate": "57014"}])
        status, saved = self.db.execute("SELECT status,summary FROM ingestion_run WHERE mode='backfill'").fetchone()
        self.assertEqual(status, "partial")
        self.assertNotIn("fatal", saved)
        self.assertEqual(saved["deferred"], result["deferred"])
        self.assertEqual(self.db.execute("SELECT value,xmin::text FROM queue_fixture").fetchall(), before)
        self.assertEqual(self.db.execute("SHOW statement_timeout").fetchone()[0], "2s")


if __name__ == "__main__":
    unittest.main()

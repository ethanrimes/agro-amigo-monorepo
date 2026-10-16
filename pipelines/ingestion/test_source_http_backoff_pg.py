"""Private local-HTTP/disposable-PostgreSQL checks; no publisher or cloud writes."""

import getpass
import hashlib
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg
import requests

from . import worker
from .source_http_backoff import (
    FALLBACK_SECONDS, HostCooldowns, HostRateLimited, NoThrottleRetry,
    retry_deadline,
)


class Handler(BaseHTTPRequestHandler):
    hits = []
    retry_after = "120"
    unavailable = 0

    def do_GET(self):
        cls = type(self)
        cls.hits.append(self.path)
        if self.path.startswith("/throttle"):
            self.send_response(429)
            if cls.retry_after is not None:
                self.send_header("Retry-After", cls.retry_after)
            self.end_headers()
            self.wfile.write(b"not a source original")
        elif self.path == "/unavailable" and cls.unavailable:
            cls.unavailable -= 1
            self.send_response(503)
            self.send_header("Retry-After", "0")
            self.end_headers()
        elif self.path == "/missing":
            self.send_response(404)
            self.end_headers()
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"independent source")

    def do_POST(self):
        # Drain the test request before closing this HTTP/1.0 connection.
        # Otherwise the unread form body can reset the client mid-response.
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.do_GET()

    def log_message(self, *_args):
        pass


class HostBackoffPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("initdb") or not shutil.which("pg_ctl"):
            raise unittest.SkipTest("Disposable PostgreSQL binaries unavailable")
        cls.tmp = tempfile.TemporaryDirectory(prefix="agro-http-backoff-")
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        cls.socket_dir = base / "socket"
        cls.socket_dir.mkdir()
        cls.cluster = base / "cluster"
        subprocess.run(["initdb", "-D", str(cls.cluster), "--auth=trust", "--no-locale", "--encoding=UTF8"],
                       check=True, capture_output=True, text=True)
        with socket.socket() as free:
            free.bind(("127.0.0.1", 0))
            cls.port = free.getsockname()[1]
        subprocess.run(["pg_ctl", "-D", str(cls.cluster), "-l", str(base / "postgres.log"),
                        "-o", f"-h '' -k {cls.socket_dir} -p {cls.port}", "-w", "start"],
                       check=True, capture_output=True, text=True)
        cls.addClassCleanup(lambda: subprocess.run(
            ["pg_ctl", "-D", str(cls.cluster), "-m", "fast", "-w", "stop"],
            check=True, capture_output=True, text=True))
        cls.dsn = f"host={cls.socket_dir} port={cls.port} dbname=postgres user={getpass.getuser()}"
        with psycopg.connect(cls.dsn, autocommit=True) as db:
            db.execute("CREATE ROLE agro_ingestor")
            db.execute("CREATE ROLE agro_reader")
            migration = (Path(__file__).parent / "migrations" /
                         "20261003_052_source_http_backoff.sql").read_text()
            db.execute(migration)
            db.execute("""CREATE TABLE ingestion_run(
                id uuid PRIMARY KEY, mode text, status text DEFAULT 'running',
                started_at timestamptz DEFAULT now(), finished_at timestamptz,
                summary jsonb DEFAULT '{}'::jsonb)""")
            db.execute("""CREATE TABLE ingestion_asset(
                url text PRIMARY KEY,kind text,observed_on date,document_id text,
                status text DEFAULT 'pending',checked_at timestamptz,
                attempts integer DEFAULT 0,error text,processor_version text DEFAULT '',
                records integer DEFAULT 0,http_etag text,http_last_modified text)""")
            db.execute("CREATE TABLE ingestion_checkpoint(document_id text,step text,records integer)")
            db.execute("""CREATE TABLE source_document(
                id text PRIMARY KEY,content bytea,kind text,source_url text,
                media_type text,metadata jsonb)""")
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.http.server_close)
        cls.addClassCleanup(cls.http.shutdown)

    def setUp(self):
        self.db = psycopg.connect(self.dsn, autocommit=True)
        self.addCleanup(self.db.close)
        for table in ("source_host_cooldown", "ingestion_run", "ingestion_checkpoint",
                      "ingestion_asset", "source_document"):
            self.db.execute(f"TRUNCATE {table}")
        Handler.hits = []
        Handler.retry_after = "120"
        Handler.unavailable = 0
        self.url = f"http://127.0.0.1:{self.http.server_port}/throttle"
        self.other = f"http://localhost:{self.http.server_port}/ok"
        session = requests.Session()
        session.mount("http://", worker.SESSION.get_adapter("https://"))
        self.enterContext(patch.object(worker, "SESSION", session))
        self.enterContext(patch(
            "pipelines.ingestion.queue_plan.current_dane_candidates", return_value=[]
        ))
        self.addCleanup(session.close)
        self.token = worker.HOST_COOLDOWNS.set(HostCooldowns(self.db))
        self.addCleanup(lambda: worker.HOST_COOLDOWNS.reset(self.token))

    def test_retry_after_seconds_date_and_bounded_fallback(self):
        now = datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc)
        self.assertEqual(retry_deadline("120", now), now + timedelta(seconds=120))
        future = now + timedelta(hours=31)
        self.assertEqual(retry_deadline(format_datetime(future), now), future)
        for literal in (None, "nonsense", "0", format_datetime(now - timedelta(days=1))):
            self.assertEqual(retry_deadline(literal, now),
                             now + timedelta(seconds=FALLBACK_SECONDS))

    def test_first_429_is_one_request_persists_and_blocks_same_host_only(self):
        self.db.execute("INSERT INTO ingestion_asset(url,kind) VALUES(%s,'daily-pdf')", (self.url,))
        with self.assertRaises(HostRateLimited) as caught:
            worker.fetch_asset(self.db, self.url)
        self.assertEqual(Handler.hits, ["/throttle"])
        self.assertEqual(caught.exception.literal_header, "120")
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_document").fetchone()[0], 0)
        row = self.db.execute("SELECT host,response_status,retry_after_literal,retry_at FROM source_host_cooldown").fetchone()
        self.assertEqual(row[:3], ("127.0.0.1", 429, "120"))
        self.assertGreater(row[3], datetime.now(timezone.utc) + timedelta(seconds=100))
        with self.assertRaises(HostRateLimited):
            worker.fetch(self.url + "-sibling")
        self.assertEqual(Handler.hits, ["/throttle"])
        self.assertEqual(worker.fetch(self.other), b"independent source")
        self.assertEqual(Handler.hits, ["/throttle", "/ok"])
        restarted = HostCooldowns(self.db)
        self.assertIsNotNone(restarted.blocked(self.url))
        self.db.execute("UPDATE source_host_cooldown SET retry_at=now()-interval '1 second'")
        restarted = HostCooldowns(self.db)
        self.assertIsNone(restarted.blocked(self.url))
        worker.HOST_COOLDOWNS.set(restarted)
        with self.assertRaises(HostRateLimited):
            worker.fetch(self.url)
        self.assertEqual(Handler.hits.count("/throttle"), 2)

    def test_503_retries_and_404_does_not_create_host_cooldown(self):
        Handler.unavailable = 1
        self.assertEqual(worker.fetch(self.url.replace("/throttle", "/unavailable")),
                         b"independent source")
        self.assertEqual(Handler.hits, ["/unavailable", "/unavailable"])
        with self.assertRaises(requests.HTTPError):
            worker.fetch(self.url.replace("/throttle", "/missing"))
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_host_cooldown").fetchone()[0], 0)
        self.assertFalse(NoThrottleRetry(total=3, status_forcelist=[500, 503]).is_retry("GET", 429, True))
        self.assertTrue(NoThrottleRetry(total=3, status_forcelist=[500, 503]).is_retry("GET", 503, True))

    def test_429_cooldown_commits_even_when_source_transaction_rolls_back(self):
        durable = HostCooldowns(
            self.db, writer=lambda: psycopg.connect(self.dsn, autocommit=True)
        )
        worker.HOST_COOLDOWNS.set(durable)
        with self.assertRaises(HostRateLimited):
            with self.db.transaction():
                worker.fetch(self.url)
        self.assertEqual(Handler.hits, ["/throttle"])
        self.assertIsNotNone(HostCooldowns(self.db).blocked(self.url))

    def test_post_query_429_uses_same_cooldown_and_never_archives_body(self):
        with self.assertRaises(HostRateLimited):
            worker._request("POST", self.url, data={"dataAccessId": "qryTabla"},
                            timeout=(10, 60))
        self.assertEqual(Handler.hits, ["/throttle"])
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_document").fetchone()[0], 0)
        with self.assertRaises(HostRateLimited):
            worker._request("GET", self.url + "-next")
        self.assertEqual(Handler.hits, ["/throttle"])

    def test_discovery_throttle_is_deferred_while_other_families_continue(self):
        operations = {name: MagicMock() for name in (
            "discover_special", "discover_monthly", "discover_price_daily",
            "discover_coffee", "discover_inputs", "discover_supply",
        )}
        operations["discover_special"].side_effect = HostRateLimited(
            "dane.gov.co", datetime.now(timezone.utc) + timedelta(minutes=5), "300"
        )
        with patch.multiple(worker, **operations):
            outcomes = worker.discover(self.db)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["deferred_host"], "dane.gov.co")
        self.assertNotIn("error", outcomes[0])
        for operation in operations.values():
            operation.assert_called_once()

    def test_run_defers_siblings_without_changing_checkpoints_or_budget(self):
        siblings = [self.url, self.url + "-failed", self.url + "-complete"]
        for i, url in enumerate(siblings):
            self.db.execute(
                "INSERT INTO ingestion_asset(url,kind,document_id,status,processor_version,checked_at) "
                "VALUES(%s,'daily-pdf',%s,%s,'old-v1',now()-interval '1 day')",
                (url, f"retained-{i}", ("archived", "failed", "complete")[i]),
            )
            self.db.execute("INSERT INTO ingestion_checkpoint VALUES(%s,'saved',%s)",
                            (f"retained-{i}", i + 1))
        self.db.execute("INSERT INTO ingestion_asset(url,kind) VALUES(%s,'coffee')", (self.other,))
        before = self.db.execute(
            "SELECT url,document_id,status,processor_version,checked_at,attempts FROM ingestion_asset ORDER BY url"
        ).fetchall()

        def processor(db, url, _kind, _day):
            worker.fetch(url)
            db.execute("UPDATE ingestion_asset SET status='complete' WHERE url=%s", (url,))
            return 1

        with (
            patch.object(worker, "connect", side_effect=lambda: psycopg.connect(self.dsn, autocommit=True)),
            patch.object(worker, "discover", return_value=[]),
            patch("pipelines.ingestion.official_sources.discover_roots", return_value=0),
            patch.object(worker, "refresh_catalog", return_value={"inputs": {"deferred": []}}),
            patch.object(worker, "process_asset", side_effect=processor),
            patch("pipelines.ingestion.queue_plan.daily_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.supply_validation_retry", return_value=[]),
            patch("pipelines.ingestion.queue_plan.repair_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.historical_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.recent_pending_daily_pdf_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.backfill_candidates",
                  return_value=[(u, "daily-pdf" if u != self.other else "coffee", None)
                                for u in siblings + [self.other]]),
            patch("pipelines.ingestion.retained_replays.drain", return_value={}),
            patch("pipelines.ingestion.ocr.drain", return_value={}),
            patch("pipelines.ingestion.retained_pdf_upgrade.retained_pdf_upgrade", return_value=None),
        ):
            summary = worker.run(mode="backfill", limit=2, time_budget=210)
        self.assertEqual(Handler.hits, ["/throttle", "/ok"])
        self.assertEqual(summary["assets"], 1)
        self.assertEqual(summary["deferred_hosts"]["127.0.0.1"]["count"], 3)
        after = self.db.execute(
            "SELECT url,document_id,status,processor_version,checked_at,attempts FROM ingestion_asset ORDER BY url"
        ).fetchall()
        old = {row[0]: row for row in before}
        new = {row[0]: row for row in after}
        self.assertEqual(new[siblings[0]][1:4], ("retained-0", "pending", "old-v1"))
        self.assertEqual(new[siblings[0]][5], 1)
        for url in siblings[1:]:
            self.assertEqual(new[url], old[url])
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint").fetchone()[0], 3)

    def test_blocked_host_allows_only_verified_local_pdf_upgrade(self):
        self.db.execute(
            "INSERT INTO source_host_cooldown(host,retry_at) VALUES('127.0.0.1',now()+interval '1 hour')"
        )
        local = self.url.replace("/throttle", "/local-upgrade")
        corrupt = self.url.replace("/throttle", "/corrupt")
        sibling = self.url.replace("/throttle", "/sibling")
        no_original = self.url.replace("/throttle", "/no-original")
        for url, body, did in ((local, b"%PDF-valid-local", None),
                               (corrupt, b"%PDF-corrupt", "wrong-sha")):
            did = did or hashlib.sha256(body).hexdigest()
            self.db.execute(
                "INSERT INTO source_document VALUES(%s,%s,'original',%s,'application/pdf',%s)",
                (did, body, url, psycopg.types.json.Jsonb({"ingestion_kind": "daily-pdf"})),
            )
            self.db.execute(
                "INSERT INTO ingestion_asset(url,kind,document_id,status,processor_version) "
                "VALUES(%s,'daily-pdf',%s,'complete','older-parser')", (url, did),
            )
        self.db.execute("INSERT INTO ingestion_asset(url,kind,status,checked_at) VALUES(%s,'daily-pdf','failed',now()-interval '1 day')", (sibling,))
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,document_id,status,processor_version,checked_at) "
            "VALUES(%s,'daily-pdf','missing-original','complete','older-parser',now()-interval '1 day')",
            (no_original,),
        )
        self.db.execute("INSERT INTO ingestion_asset(url,kind) VALUES(%s,'coffee')", (self.other,))
        old_skipped = {
            url: self.db.execute(
                "SELECT status,checked_at,attempts FROM ingestion_asset WHERE url=%s", (url,)
            ).fetchone()
            for url in (sibling, no_original)
        }

        def processor(db, url, kind, _day):
            if kind == "daily-pdf":
                from .retained_pdf_upgrade import retained_pdf_upgrade
                retained_pdf_upgrade(db, url, kind, worker.asset_parser_version(kind, url))
            else:
                worker.fetch(url)
            db.execute("UPDATE ingestion_asset SET status='complete' WHERE url=%s", (url,))
            return 1

        with (
            patch.object(worker, "connect", side_effect=lambda: psycopg.connect(self.dsn, autocommit=True)),
            patch.object(worker, "discover", return_value=[]),
            patch("pipelines.ingestion.official_sources.discover_roots", return_value=0),
            patch.object(worker, "refresh_catalog", return_value={"inputs": {"deferred": []}}),
            patch.object(worker, "process_asset", side_effect=processor),
            patch("pipelines.ingestion.queue_plan.daily_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.supply_validation_retry", return_value=[]),
            patch("pipelines.ingestion.queue_plan.repair_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.historical_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.recent_pending_daily_pdf_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.backfill_candidates",
                  return_value=[(u, "coffee" if u == self.other else "daily-pdf", None)
                                for u in (local, sibling, no_original, corrupt, self.other)]),
            patch("pipelines.ingestion.retained_replays.drain", return_value={}),
            patch("pipelines.ingestion.ocr.drain", return_value={}),
        ):
            summary = worker.run(mode="backfill", limit=3, time_budget=210)
        self.assertEqual(Handler.hits, ["/ok"])
        self.assertEqual(summary["assets"], 2)
        self.assertEqual(summary["deferred_hosts"]["127.0.0.1"]["count"], 2)
        self.assertTrue(any("invalid original SHA" in item["error"] for item in summary["errors"]))
        for url in (sibling, no_original):
            self.assertEqual(self.db.execute(
                "SELECT status,checked_at,attempts FROM ingestion_asset WHERE url=%s", (url,)
            ).fetchone(), old_skipped[url])
        self.assertEqual(self.db.execute(
            "SELECT status FROM ingestion_asset WHERE url=%s", (local,)
        ).fetchone()[0], "complete")
        self.assertEqual(self.db.execute(
            "SELECT status,document_id FROM ingestion_asset WHERE url=%s", (corrupt,)
        ).fetchone(), ("failed", "wrong-sha"))

    def test_expired_work_deadline_precedes_retained_pdf_hash(self):
        self.db.execute(
            "INSERT INTO source_host_cooldown(host,retry_at) VALUES('127.0.0.1',now()+interval '1 hour')"
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,processor_version) "
            "VALUES(%s,'daily-pdf','complete','older-parser')", (self.url,)
        )
        with (
            patch.object(worker, "connect", side_effect=lambda: psycopg.connect(self.dsn, autocommit=True)),
            patch.object(worker, "discover", return_value=[]),
            patch("pipelines.ingestion.official_sources.discover_roots", return_value=0),
            patch.object(worker, "refresh_catalog", return_value={"inputs": {"deferred": []}}),
            patch("pipelines.ingestion.queue_plan.daily_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.supply_validation_retry", return_value=[]),
            patch("pipelines.ingestion.queue_plan.repair_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.historical_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.recent_pending_daily_pdf_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.backfill_candidates",
                  return_value=[(self.url, "daily-pdf", None)]),
            patch("pipelines.ingestion.retained_pdf_upgrade.retained_pdf_upgrade") as local_reparse,
            patch("pipelines.ingestion.ocr.drain", return_value={}),
        ):
            summary = worker.run(mode="backfill", limit=1, time_budget=0)
        self.assertTrue(summary["time_budget_reached"])
        local_reparse.assert_not_called()
        self.assertEqual(Handler.hits, [])


if __name__ == "__main__":
    unittest.main()

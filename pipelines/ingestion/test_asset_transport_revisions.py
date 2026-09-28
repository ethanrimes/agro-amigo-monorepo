"""Local HTTP and disposable PostgreSQL proof for mutable original retention.

The bodies are controlled revisions, not publisher originals. No cloud DB or
publisher host is contacted, and the temporary database is destroyed afterward.
"""

import hashlib
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import psycopg
import requests

from . import worker
from .resumable_inputs import WorkDeferred


class RevisionHandler(BaseHTTPRequestHandler):
    body = b"revision-one"
    etag = '"one"'
    last_modified = "Mon, 01 Sep 2025 00:00:00 GMT"
    failures = 0
    drops = 0
    unconditional_304 = False
    seen = []

    def do_GET(self):
        cls = type(self)
        cls.seen.append(dict(self.headers))
        if cls.drops:
            cls.drops -= 1
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if cls.failures:
            cls.failures -= 1
            self.send_response(503)
            self.send_header("Retry-After", "0")
            self.end_headers()
            return
        if cls.unconditional_304 or self.headers.get("If-None-Match") == cls.etag or (
            not self.headers.get("If-None-Match")
            and self.headers.get("If-Modified-Since") == cls.last_modified
        ):
            self.send_response(304)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("ETag", cls.etag)
        self.send_header("Last-Modified", cls.last_modified)
        self.send_header("Content-Length", str(len(cls.body)))
        self.end_headers()
        self.wfile.write(cls.body)

    def log_message(self, *_args):
        pass


class AssetTransportRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("initdb") or not shutil.which("pg_ctl"):
            raise unittest.SkipTest("Disposable local PostgreSQL tools unavailable")
        cls.tmp = tempfile.TemporaryDirectory(prefix="agro-asset-revisions-")
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        cls.socket_dir = base / "socket"
        cls.socket_dir.mkdir()
        cluster = base / "cluster"
        subprocess.run(
            ["initdb", "-D", str(cluster), "-A", "trust", "-U", "agro_test", "--no-instructions"],
            check=True, capture_output=True, text=True,
        )
        with socket.socket() as free:
            free.bind(("127.0.0.1", 0))
            cls.port = free.getsockname()[1]
        subprocess.run(
            ["pg_ctl", "-D", str(cluster), "-o", f"-h '' -k {cls.socket_dir} -p {cls.port}", "-w", "start"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
        )
        cls.addClassCleanup(lambda: subprocess.run(
            ["pg_ctl", "-D", str(cluster), "-m", "immediate", "-w", "stop"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
        ))
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), RevisionHandler)
        thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        thread.start()
        cls.addClassCleanup(cls.http.server_close)
        cls.addClassCleanup(cls.http.shutdown)

    def setUp(self):
        RevisionHandler.body = b"revision-one"
        RevisionHandler.etag = '"one"'
        RevisionHandler.last_modified = "Mon, 01 Sep 2025 00:00:00 GMT"
        RevisionHandler.failures = 0
        RevisionHandler.drops = 0
        RevisionHandler.unconditional_304 = False
        RevisionHandler.seen = []
        self.url = f"http://127.0.0.1:{self.http.server_port}/supply.xlsx"
        self.db = psycopg.connect(
            host=str(self.socket_dir), port=self.port, user="agro_test",
            dbname="postgres", autocommit=True,
        )
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp")
        self.db.execute("""CREATE TEMP TABLE source_document(
            id text PRIMARY KEY,title text NOT NULL,publisher text NOT NULL,
            source_url text NOT NULL,media_type text NOT NULL,kind text NOT NULL,
            reference_period text NOT NULL,retrieved_at timestamptz DEFAULT now(),
            page_count integer,content bytea NOT NULL,metadata jsonb NOT NULL)""")
        self.db.execute("CREATE TEMP TABLE document_alias(alias text PRIMARY KEY,document_id text)")
        self.db.execute("""CREATE TEMP TABLE ingestion_asset(
            url text PRIMARY KEY,kind text,document_id text,status text DEFAULT 'pending',
            observed_on date,discovered_at timestamptz DEFAULT now(),
            records integer DEFAULT 0,checked_at timestamptz,attempts integer DEFAULT 0,
            error text,processor_version text DEFAULT '',http_etag text,http_last_modified text)""")
        self.db.execute("""CREATE TEMP TABLE ingestion_checkpoint(
            document_id text,processor_version text,step text,records bigint,
            PRIMARY KEY(document_id,processor_version,step))""")
        self.db.execute("INSERT INTO ingestion_asset(url,kind) VALUES(%s,'supply')", (self.url,))
        session = requests.Session()
        session.mount("http://", worker.SESSION.get_adapter("https://"))
        self.enterContext(patch.object(worker, "SESSION", session))
        self.addCleanup(session.close)
        self.enterContext(patch("pipelines.ingestion.ocr.scan_document"))

    def state(self):
        return self.db.execute(
            "SELECT document_id,status,http_etag,http_last_modified FROM ingestion_asset WHERE url=%s",
            (self.url,),
        ).fetchone()

    def originals(self):
        return self.db.execute("SELECT id,content FROM source_document ORDER BY id").fetchall()

    def test_changed_bytes_unchanged_replies_and_validators_keep_both_originals(self):
        with patch("pipelines.ingestion.supply.publish_supply", return_value=1) as publish:
            self.assertEqual(worker.process_asset(self.db, self.url, "supply", None), 1)
            first = hashlib.sha256(b"revision-one").hexdigest()
            self.assertEqual(self.state()[:3], (first, "complete", '"one"'))
            self.assertEqual(worker.process_asset(self.db, self.url, "supply", None), 0)
            self.assertEqual(publish.call_count, 1)
            self.assertEqual(RevisionHandler.seen[-1].get("If-None-Match"), '"one"')

            RevisionHandler.body = b"revision-two"
            RevisionHandler.etag = '"two"'
            RevisionHandler.last_modified = "Tue, 02 Sep 2025 00:00:00 GMT"
            self.assertEqual(worker.process_asset(self.db, self.url, "supply", None), 1)
            second = hashlib.sha256(b"revision-two").hexdigest()
            self.assertEqual(self.state()[:3], (second, "complete", '"two"'))
            self.assertEqual({row[0]: bytes(row[1]) for row in self.originals()},
                             {first: b"revision-one", second: b"revision-two"})
            self.assertEqual(worker.process_asset(self.db, self.url, "supply", None), 0)
            self.assertEqual(publish.call_count, 2)

            # A validator rotation with identical bytes updates HTTP state but
            # does not create a duplicate original or run publication again.
            RevisionHandler.etag = '"two-rotated"'
            self.assertEqual(worker.process_asset(self.db, self.url, "supply", None), 0)
            self.assertEqual(self.state()[2], '"two-rotated"')
            self.assertEqual(len(self.originals()), 2)
            self.assertEqual(publish.call_count, 2)

    def test_forced_parser_refresh_detects_changed_bytes_even_with_stale_etag(self):
        with patch("pipelines.ingestion.supply.publish_supply", return_value=1):
            worker.process_asset(self.db, self.url, "supply", None)
            self.db.execute("UPDATE ingestion_asset SET processor_version='older-parser' WHERE url=%s", (self.url,))
            RevisionHandler.body = b"revision-two"
            # Misconfigured publisher reuses an ETag; force must avoid sending it.
            self.assertEqual(worker.process_asset(self.db, self.url, "supply", None), 1)
        self.assertNotIn("If-None-Match", RevisionHandler.seen[-1])
        self.assertEqual({bytes(row[1]) for row in self.originals()},
                         {b"revision-one", b"revision-two"})

    def test_last_modified_only_and_transient_status_retry(self):
        self.db.execute("UPDATE ingestion_asset SET http_etag=NULL,document_id=%s,status='complete',processor_version=%s WHERE url=%s",
                        (worker.archive(self.db, self.url, b"old", "supply"), worker.parser_version("supply"), self.url))
        self.db.execute("UPDATE ingestion_asset SET http_last_modified=%s WHERE url=%s",
                        ("Mon, 01 Sep 2025 00:00:00 GMT", self.url))
        RevisionHandler.body = b"new-after-retry"
        RevisionHandler.etag = '"new"'
        RevisionHandler.last_modified = "Tue, 02 Sep 2025 00:00:00 GMT"
        RevisionHandler.failures = 1
        with patch("pipelines.ingestion.supply.publish_supply", return_value=1):
            self.assertEqual(worker.process_asset(self.db, self.url, "supply", None), 1)
        self.assertGreaterEqual(len(RevisionHandler.seen), 2)
        self.assertEqual(RevisionHandler.seen[0].get("If-Modified-Since"),
                         "Mon, 01 Sep 2025 00:00:00 GMT")
        self.assertEqual(self.state()[0], hashlib.sha256(b"new-after-retry").hexdigest())
        self.assertEqual(len(self.originals()), 2)

    def test_unconditional_304_never_marks_pending_asset_processed(self):
        RevisionHandler.unconditional_304 = True
        with patch("pipelines.ingestion.supply.publish_supply") as publish:
            with self.assertRaisesRegex(ValueError, "304 without a conditional"):
                worker.process_asset(self.db, self.url, "supply", None)
        publish.assert_not_called()
        self.assertEqual(self.state()[0:2], (None, "pending"))
        self.assertEqual(len(RevisionHandler.seen), 2)
        self.assertEqual(RevisionHandler.seen[1].get("Cache-Control"), "no-cache")

    def test_unconditional_304_reprocesses_completed_retained_bytes_on_parser_upgrade(self):
        with patch("pipelines.ingestion.supply.publish_supply", return_value=1) as publish:
            worker.process_asset(self.db, self.url, "supply", None)
            self.db.execute("UPDATE ingestion_asset SET processor_version='older-parser' WHERE url=%s", (self.url,))
            RevisionHandler.unconditional_304 = True
            self.assertEqual(worker.process_asset(self.db, self.url, "supply", None), 1)
        self.assertEqual(publish.call_count, 2)
        self.assertEqual(len(self.originals()), 1)
        self.assertEqual(self.state()[1], "complete")
        self.assertEqual(RevisionHandler.seen[-1].get("Cache-Control"), "no-cache")

    def test_dropped_connection_retries_without_archiving_partial_original(self):
        RevisionHandler.drops = 1
        with patch("pipelines.ingestion.supply.publish_supply", return_value=1):
            self.assertEqual(worker.process_asset(self.db, self.url, "supply", None), 1)
        self.assertEqual(len(RevisionHandler.seen), 2)
        self.assertEqual(self.originals()[0][0], hashlib.sha256(b"revision-one").hexdigest())
        self.assertEqual(len(self.originals()), 1)

    def test_checkpoint_resume_uses_retained_revision_before_new_url_bytes(self):
        first = hashlib.sha256(b"revision-one").hexdigest()
        calls = []

        def deferred_publish(db, data, did):
            calls.append((bytes(data), did))
            if len(calls) == 1:
                db.execute("INSERT INTO ingestion_checkpoint VALUES(%s,%s,'supply:validated',1)",
                           (did, worker.parser_version("supply")))
                raise WorkDeferred("controlled interruption after validation")
            return 1

        with patch("pipelines.ingestion.supply.publish_supply", side_effect=deferred_publish):
            with self.assertRaises(WorkDeferred):
                worker.process_asset(self.db, self.url, "supply", None)
            self.assertEqual(self.state()[:2], (first, "pending"))
            RevisionHandler.body = b"revision-two"
            RevisionHandler.etag = '"two"'
            self.assertEqual(worker.process_asset(self.db, self.url, "supply", None), 1)
            self.assertEqual(calls[1], (b"revision-one", first))
            self.assertEqual(len(RevisionHandler.seen), 1)
            self.assertEqual(worker.process_asset(self.db, self.url, "supply", None), 1)
            self.assertEqual(len(self.originals()), 2)

    def test_old_failed_input_versions_reenter_hourly_backfill_without_cooldown(self):
        from .queue_plan import backfill_candidates

        for name, version in (("old-v4", "inputs-reference-v4"), ("empty", "")):
            self.db.execute(
                """INSERT INTO ingestion_asset(url,kind,status,processor_version,
                   observed_on,checked_at) VALUES(%s,'inputs-reference','failed',%s,
                   '2017-04-30',now())""",
                (self.url + name, version),
            )
        self.db.execute(
            """INSERT INTO ingestion_asset(url,kind,status,processor_version,
               observed_on,checked_at) VALUES(%s,'inputs-reference','failed',%s,
               '2017-04-30',now())""",
            (self.url + "current", worker.parser_version("inputs-reference")),
        )
        selected = {url for url, _, _ in backfill_candidates(self.db, 100)}
        self.assertIn(self.url + "old-v4", selected)
        self.assertIn(self.url + "empty", selected)
        self.assertNotIn(self.url + "current", selected)

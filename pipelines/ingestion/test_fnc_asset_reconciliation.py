"""Strict FNC monthly-upload identity and owned-PostgreSQL lifecycle checks.

The PostgreSQL class runs only when AGRO_FNC_ASSET_RECONCILIATION_PG=1. It
creates its own temporary Unix-socket-only cluster and never accepts a DSN.
"""
from __future__ import annotations

import getpass
import hashlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest

from .fnc_asset_reconciliation import (
    RETIREMENT_PREFIX,
    reconcile_fnc_workbook_assets,
    upload_equivalence_key,
)


BASE = "https://www.federaciondecafeteros.org/wp-content/uploads/2026/09/Precios-area-y-produccion-de-cafe-Septiembre-2026.xlsx"
REV1 = BASE[:-5] + "-1.xlsx"
REV2 = BASE[:-5] + "-2.xlsx"
SHA_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class UploadIdentityTests(unittest.TestCase):
    def test_only_exact_monthly_upload_revision_names_share_a_key(self):
        key = upload_equivalence_key(BASE)
        self.assertEqual(key, ("www.federaciondecafeteros.org", "/wp-content/uploads/2026/09", 2026, 9))
        self.assertEqual(upload_equivalence_key(REV1), key)
        self.assertEqual(upload_equivalence_key(REV2), key)

    def test_upload_key_keeps_host_directory_report_year_month_and_case(self):
        key = upload_equivalence_key(BASE)
        mismatches = (
            BASE.replace("2026.xlsx", "2025.xlsx"),
            BASE.replace("Septiembre-2026", "Octubre-2026"),
            BASE.replace("/2026/09/", "/2026/08/"),
            BASE.replace("www.federaciondecafeteros.org", "federaciondecafeteros.org"),
            BASE.replace("Septiembre", "septiembre"),
            BASE.replace("Septiembre-2026.xlsx", "Septiembre-2026-final.xlsx"),
            BASE.replace("Precios-area-y-produccion-de-cafe", "Precios-area-y-produccion-de-cafe-extra"),
            BASE + "?download=1",
            BASE.replace("https://", "http://"),
            "https://evil.example/wp-content/uploads/2026/09/Precios-area-y-produccion-de-cafe-Septiembre-2026.xlsx",
        )
        for url in mismatches:
            with self.subTest(url=url):
                self.assertNotEqual(upload_equivalence_key(url), key)


@unittest.skipUnless(
    os.environ.get("AGRO_FNC_ASSET_RECONCILIATION_PG") == "1",
    "set AGRO_FNC_ASSET_RECONCILIATION_PG=1 to run the owned disposable PostgreSQL qualification",
)
class FncAssetReconciliationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        binary_dir = Path("/opt/homebrew/opt/postgresql@17/bin")
        initdb = str(binary_dir / "initdb") if (binary_dir / "initdb").exists() else shutil.which("initdb")
        pg_ctl = str(binary_dir / "pg_ctl") if (binary_dir / "pg_ctl").exists() else shutil.which("pg_ctl")
        if not initdb or not pg_ctl:
            raise unittest.SkipTest("PostgreSQL initdb/pg_ctl unavailable")
        import psycopg

        cls._psycopg = psycopg
        # macOS limits Unix socket paths to 103 bytes; keep this owned cluster
        # root short while still placing it under a unique temporary directory.
        cls.tmp = tempfile.TemporaryDirectory(prefix="afn", dir="/tmp")
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        cls.socket_dir = base / "socket"
        cls.socket_dir.mkdir()
        cls.cluster = base / "cluster"
        subprocess.run(
            [initdb, "-D", str(cls.cluster), "--auth=trust", "--no-locale", "--encoding=UTF8"],
            check=True, capture_output=True, text=True,
        )
        with socket.socket() as free:
            free.bind(("127.0.0.1", 0))
            cls.port = free.getsockname()[1]
        cls.log = base / "postgres.log"
        start = subprocess.run(
            [pg_ctl, "-D", str(cls.cluster), "-l", str(cls.log), "-o",
             f"-h '' -k {cls.socket_dir} -p {cls.port}", "-w", "start"],
            capture_output=True, text=True,
        )
        if start.returncode:
            raise RuntimeError(f"owned PostgreSQL startup failed: {start.stdout}\n{start.stderr}\n{cls.log.read_text() if cls.log.exists() else ''}")
        cls.pg_ctl = pg_ctl
        cls.dsn = f"host={cls.socket_dir} port={cls.port} dbname=postgres user={getpass.getuser()}"
        cls.addClassCleanup(lambda: subprocess.run(
            [pg_ctl, "-D", str(cls.cluster), "-m", "fast", "-w", "stop"],
            check=True, capture_output=True, text=True,
        ))
        with psycopg.connect(cls.dsn, autocommit=True) as db:
            db.execute("""CREATE TABLE source_document(
                id text PRIMARY KEY, title text NOT NULL, publisher text NOT NULL,
                source_url text NOT NULL, media_type text NOT NULL, kind text NOT NULL,
                reference_period text NOT NULL, retrieved_at timestamptz NOT NULL DEFAULT now(),
                page_count integer, content bytea NOT NULL, metadata jsonb NOT NULL DEFAULT '{}')""")
            db.execute("""CREATE TABLE ingestion_asset(
                url text PRIMARY KEY, kind text NOT NULL, observed_on date,
                discovered_at timestamptz NOT NULL DEFAULT now(), checked_at timestamptz,
                status text NOT NULL DEFAULT 'pending', attempts integer NOT NULL DEFAULT 0,
                document_id text REFERENCES source_document(id), records integer NOT NULL DEFAULT 0,
                error text, processor_version text NOT NULL DEFAULT '')""")
            db.execute("""CREATE TABLE official_price_quote(
                document_id text NOT NULL REFERENCES source_document(id), source_locator text NOT NULL,
                product_name text NOT NULL, observed_on date NOT NULL, price numeric NOT NULL,
                PRIMARY KEY(document_id,source_locator))""")

    def setUp(self):
        self.db = self._psycopg.connect(self.dsn, autocommit=True)
        self.addCleanup(self.db.close)
        self.db.execute("TRUNCATE official_price_quote, ingestion_asset, source_document")

    @staticmethod
    def _source_bytes(label: str) -> bytes:
        return ("retained original bytes for " + label).encode()

    def _source(self, url: str, title: str, source_bytes: bytes):
        did = hashlib.sha256(source_bytes).hexdigest()
        self.db.execute(
            """INSERT INTO source_document
               (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
               VALUES (%s,%s,'FNC',%s,%s,'original','2026-09',%s,%s::jsonb)""",
            (did, title, url, SHA_MEDIA, source_bytes, '{"ingestion_kind":"coffee"}'),
        )
        return did

    def _asset(self, url, *, status, error=None, did=None, records=0, attempts=0):
        self.db.execute(
            """INSERT INTO ingestion_asset
               (url,kind,status,error,document_id,records,attempts,checked_at,processor_version)
               VALUES (%s,'coffee',%s,%s,%s,%s,%s,'2026-10-03 12:34:56+00','fnc-parser-test')""",
            (url, status, error, did, records, attempts),
        )

    def _snapshot(self, url):
        return self.db.execute(
            """SELECT status,error,document_id,records,attempts,checked_at,processor_version,
                      xmin::text FROM ingestion_asset WHERE url=%s""", (url,),
        ).fetchone()

    def _old_with_original(self, url=REV1, error="HTTPError: 404 Client Error: Not Found"):
        body = self._source_bytes("old")
        did = self._source(url, "Retained failed FNC workbook", body)
        self._asset(url, status="failed", error=error, did=did, records=20241, attempts=8)
        self.db.execute(
            "INSERT INTO official_price_quote VALUES(%s,'sheet:Prices!A1','Café pergamino','2026-09-30',1200000)",
            (did,),
        )
        return did, hashlib.sha256(body).hexdigest()

    def _complete_replacement(self, url=BASE):
        body = self._source_bytes("current:" + url)
        did = self._source(url, "Current linked FNC workbook", body)
        self._asset(url, status="complete", did=did, records=20249, attempts=2)
        return did

    def test_numbered_to_base_retirement_preserves_all_old_evidence(self):
        old_did, old_hash = self._old_with_original(REV1)
        self._complete_replacement(BASE)
        before = self._snapshot(REV1)
        src_before = self.db.execute(
            "SELECT content,metadata,xmin::text FROM source_document WHERE id=%s", (old_did,)
        ).fetchone()
        quote_before = self.db.execute(
            "SELECT *,xmin::text FROM official_price_quote WHERE document_id=%s", (old_did,)
        ).fetchall()

        self.assertEqual(reconcile_fnc_workbook_assets(self.db, [BASE]),
                         {"revived": 0, "retired": 1, "ambiguous": 0})
        after = self._snapshot(REV1)
        self.assertEqual(after[:1], ("archived",))
        self.assertTrue(after[1].startswith(RETIREMENT_PREFIX))
        self.assertIn("HTTPError: 404", after[1])
        self.assertEqual(after[2:7], before[2:7])
        self.assertNotEqual(after[7], before[7])  # only the state/error row changed
        src_after = self.db.execute(
            "SELECT content,metadata,xmin::text FROM source_document WHERE id=%s", (old_did,)
        ).fetchone()
        quote_after = self.db.execute(
            "SELECT *,xmin::text FROM official_price_quote WHERE document_id=%s", (old_did,)
        ).fetchall()
        self.assertEqual(src_after, src_before)
        self.assertEqual(quote_after, quote_before)
        self.assertEqual(hashlib.sha256(src_after[0]).hexdigest(), old_hash)

        retired = self._snapshot(REV1)
        self.assertEqual(reconcile_fnc_workbook_assets(self.db, [BASE, REV1]),
                         {"revived": 1, "retired": 0, "ambiguous": 0})
        revived = self._snapshot(REV1)
        self.assertEqual(revived[:1], ("pending",))
        self.assertFalse(revived[1].startswith(RETIREMENT_PREFIX))
        self.assertIn(retired[1], revived[1])
        self.assertEqual(revived[2:7], retired[2:7])
        self.assertNotEqual(revived[7], retired[7])
        self.assertEqual(self.db.execute(
            "SELECT content,metadata,xmin::text FROM source_document WHERE id=%s", (old_did,)
        ).fetchone(), src_before)
        self.assertEqual(self.db.execute(
            "SELECT *,xmin::text FROM official_price_quote WHERE document_id=%s", (old_did,)
        ).fetchall(), quote_before)

    def test_base_to_numbered_and_numbered_to_numbered_are_equivalent(self):
        cases = ((BASE, REV1), (REV1, REV2))
        for old_url, current_url in cases:
            with self.subTest(old=old_url, current=current_url):
                self.db.execute("TRUNCATE official_price_quote, ingestion_asset, source_document")
                self._old_with_original(old_url)
                self._complete_replacement(current_url)
                stats = reconcile_fnc_workbook_assets(self.db, [current_url])
                self.assertEqual(stats, {"revived": 0, "retired": 1, "ambiguous": 0})
                self.assertEqual(self._snapshot(old_url)[0], "archived")

    def test_multiple_linked_replacements_are_ambiguous_and_left_failed(self):
        self._old_with_original(REV1)
        self._complete_replacement(BASE)
        second = BASE[:-5] + "-2.xlsx"
        self._complete_replacement(second)
        before = self._snapshot(REV1)
        stats = reconcile_fnc_workbook_assets(self.db, [BASE, second])
        self.assertEqual(stats, {"revived": 0, "retired": 0, "ambiguous": 1})
        self.assertEqual(self._snapshot(REV1), before)

    def test_year_month_directory_host_or_case_difference_never_retires(self):
        current_urls = (
            BASE.replace("Septiembre-2026", "Septiembre-2025"),
            BASE.replace("Septiembre-2026", "Octubre-2026"),
            BASE.replace("/2026/09/", "/2026/08/"),
            BASE.replace("www.federaciondecafeteros.org", "federaciondecafeteros.org"),
            BASE.replace("Septiembre-2026", "septiembre-2026"),
        )
        for current in current_urls:
            with self.subTest(current=current):
                self.db.execute("TRUNCATE official_price_quote, ingestion_asset, source_document")
                self._old_with_original(REV1)
                did = self._source(current, "Current but non-equivalent workbook", self._source_bytes(current))
                self._asset(current, status="complete", did=did, records=20249)
                before = self._snapshot(REV1)
                self.assertEqual(reconcile_fnc_workbook_assets(self.db, [current]),
                                 {"revived": 0, "retired": 0, "ambiguous": 0})
                self.assertEqual(self._snapshot(REV1), before)

    def test_only_unique_complete_retained_original_authorizes_retirement(self):
        for mode in ("pending", "missing-did", "zero-records", "wrong-source-url", "wrong-metadata"):
            with self.subTest(mode=mode):
                self.db.execute("TRUNCATE official_price_quote, ingestion_asset, source_document")
                self._old_with_original(REV1)
                if mode == "pending":
                    did = self._source(BASE, "Not complete", self._source_bytes(mode))
                    self._asset(BASE, status="pending", did=did)
                elif mode == "missing-did":
                    self._asset(BASE, status="complete")
                elif mode == "zero-records":
                    did = self._source(BASE, "Completed with zero records", self._source_bytes(mode))
                    self._asset(BASE, status="complete", did=did, records=0)
                elif mode == "wrong-source-url":
                    did = self._source(BASE + ".other", "Wrong retained source URL", self._source_bytes(mode))
                    self._asset(BASE, status="complete", did=did)
                else:
                    did = self._source(BASE, "Wrong retained kind", self._source_bytes(mode))
                    self.db.execute("UPDATE source_document SET metadata='{}'::jsonb WHERE id=%s", (did,))
                    self._asset(BASE, status="complete", did=did)
                before = self._snapshot(REV1)
                self.assertEqual(reconcile_fnc_workbook_assets(self.db, [BASE]),
                                 {"revived": 0, "retired": 0, "ambiguous": 0})
                self.assertEqual(self._snapshot(REV1), before)

    def test_raw_404_marker_anchor_and_non_target_status_guards(self):
        for error, status in (
            ("timeout after seeing 404 in a URL", "failed"),
            (RETIREMENT_PREFIX + " some replacement; prior error: 404", "failed"),
            ("HTTPError: 404 Client Error", "complete"),
        ):
            with self.subTest(error=error, status=status):
                self.db.execute("TRUNCATE official_price_quote, ingestion_asset, source_document")
                did = self._source(REV1, "Old source", self._source_bytes(error))
                self._asset(REV1, status=status, error=error, did=did)
                self._complete_replacement(BASE)
                before = self._snapshot(REV1)
                self.assertEqual(reconcile_fnc_workbook_assets(self.db, [BASE]),
                                 {"revived": 0, "retired": 0, "ambiguous": 0})
                self.assertEqual(self._snapshot(REV1), before)

    def test_non_target_marker_rows_are_not_revived_and_non_monthly_urls_do_not_retire(self):
        marker = RETIREMENT_PREFIX + " " + BASE + "; prior error: HTTPError: 404"
        self._asset(BASE, status="complete", error=marker)
        nonmonthly = BASE.replace("Precios-area-y-produccion-de-cafe-Septiembre-2026", "Precios-area-y-produccion-de-cafe-2026")
        self._asset(nonmonthly, status="failed", error="404 Not Found")
        before_complete = self._snapshot(BASE)
        before_old = self._snapshot(nonmonthly)
        self.assertEqual(reconcile_fnc_workbook_assets(self.db, [BASE]),
                         {"revived": 0, "retired": 0, "ambiguous": 0})
        self.assertEqual(self._snapshot(BASE), before_complete)
        self.assertEqual(self._snapshot(nonmonthly), before_old)


if __name__ == "__main__":
    unittest.main()

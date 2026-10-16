"""Private PostgreSQL regression for the source-bound May 2013 replay gate."""
import hashlib
import json
import os
import re
import unittest
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb

from pipelines.ingestion import dane_weekly, official_sources
from pipelines.ingestion.retained_pdf_upgrade import retained_may2013_white_corn_original

FIX = Path(__file__).resolve().parent / "testdata/may2013_white_corn_heading"
URL = dane_weekly.MAY2013_WHITE_CORN_URL
DID = dane_weekly.MAY2013_WHITE_CORN_SHA
KIND = "dane-weekly-pdf"
OLD = "official-v2:dane-weekly-v24"
NEW = "official-v2:may2013-white-corn-heading-v1:dane-weekly-v24"
OWN_ERROR = "ValueError: May 2013 asset is outside the pinned pending/completed lifecycle"
FIELDS = (
    "document_id", "source_locator", "parser_version", "quote_key", "product_id",
    "product_name", "category", "publisher", "series", "basis", "currency",
    "unit", "market", "observed_on", "period_start", "price", "min_price",
    "max_price", "source_page", "details",
)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _validate_owned_dsn(dsn):
    try:
        values = conninfo_to_dict(dsn)
    except Exception as exc:
        raise RuntimeError("Invalid May 2013 private-test DSN") from exc
    if any(key in values for key in ("service", "servicefile", "hostaddr")):
        raise RuntimeError("Service and TCP host-address DSNs are forbidden for this test")
    host = values.get("host", "")
    if (not _is_owned_test_socket(host)
            or "," in host or ".." in Path(host).parts):
        raise RuntimeError("Only one canonical task-owned May 2013 Unix socket is allowed")
    if values.get("user") != "postgres" or values.get("dbname") != "postgres":
        raise RuntimeError("May 2013 test requires the owned postgres role/database")
    port = values.get("port", "")
    if not port.isdigit() or not 1024 <= int(port) <= 65535:
        raise RuntimeError("May 2013 test requires an explicit valid local port")
    return values


def _is_owned_test_socket(host):
    return bool(
        re.fullmatch(r"/tmp/agro-may2013-socket-[A-Za-z0-9_-]+", host)
        or re.fullmatch(r"/tmp/agro-may2013-worker-[A-Za-z0-9_-]+/socket", host)
    )


def _connect_owned_dsn(dsn):
    _validate_owned_dsn(dsn)
    return psycopg.connect(dsn, autocommit=True)


class May2013OwnedDSNGuard(unittest.TestCase):
    def test_untrusted_dsns_are_rejected_before_connect(self):
        invalid = (
            "postgresql://postgres:secret@db.example.com/postgres",
            "host=/tmp/agro-may2013-socket-safe port=5432 user=postgres dbname=postgres service=prod",
            "host=/tmp/agro-may2013-socket-safe port=5432 user=postgres dbname=postgres hostaddr=127.0.0.1",
            "host=/tmp/agro-may2013-socket-safe port=5432 user=app dbname=postgres",
            "host=/tmp/agro-may2013-socket-../other port=5432 user=postgres dbname=postgres",
            "host=/tmp/agro-may2013-socket-safe user=postgres dbname=postgres",
        )
        with patch("pipelines.ingestion.test_may2013_lifecycle_guard_pg.psycopg.connect") as connect:
            for value in invalid:
                with self.subTest(dsn=value):
                    with self.assertRaises(RuntimeError):
                        _connect_owned_dsn(value)
            connect.assert_not_called()

    def test_explicit_owned_unix_dsn_is_accepted_before_connect(self):
        safe = "postgresql://postgres@/postgres?host=/tmp/agro-may2013-socket-safe&port=55432"
        marker = object()
        with patch("pipelines.ingestion.test_may2013_lifecycle_guard_pg.psycopg.connect", return_value=marker) as connect:
            self.assertIs(_connect_owned_dsn(safe), marker)
        connect.assert_called_once_with(safe, autocommit=True)


@unittest.skipUnless(os.environ.get("AGRO_MAY2013_TEST_DSN"), "Explicit owned May 2013 PostgreSQL DSN required")
class May2013LifecycleGuardPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ.get("AGRO_MAY2013_TEST_DSN")
        if not dsn:
            raise unittest.SkipTest("Explicit owned May 2013 PostgreSQL DSN required")
        _validate_owned_dsn(dsn)
        cls.db = _connect_owned_dsn(dsn)
        if (cls.db.info.user != "postgres" or cls.db.info.dbname != "postgres"
                or not _is_owned_test_socket(str(cls.db.info.host))):
            cls.db.close()
            raise RuntimeError("Only the explicit task-owned May 2013 Unix PostgreSQL socket is allowed")
        cls.schema = "qa_may2013_guard_" + uuid.uuid4().hex[:12]
        cls.db.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.db.execute(f'SET search_path="{cls.schema}",public')
        cls.db.execute("SET statement_timeout='30s'; SET lock_timeout='2s'")
        for table in ("source_document", "official_price_quote", "official_source_review",
                      "ingestion_asset", "ingestion_checkpoint"):
            cls.db.execute(f'CREATE TABLE "{table}" (LIKE public."{table}" INCLUDING ALL)')
        cls.body = (FIX / "may2013_original.pdf").read_bytes()
        cls.old = json.loads((FIX / "may2013_v24_quotes_4201_prior.json").read_text())
        cls.expected = json.loads((FIX / "may2013_heading_quotes_4201_expected.json").read_text())
        if sha_bytes(cls.body) != DID or len(cls.body) != dane_weekly.MAY2013_WHITE_CORN_SIZE:
            raise AssertionError("Pinned original PDF bytes changed")
        if len(cls.old) != 4201 or len(cls.expected) != 4201:
            raise AssertionError("Pinned old/new full quote fixtures changed")
        cls.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
            "reference_period,page_count,content,metadata) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (DID, "DANE · SIPSA - Semana_18may_24may_2013.pdf", "DANE · SIPSA", URL,
             "application/pdf", "original", "2013-05-24", 44, cls.body,
             Jsonb({"retention": "permanent", "ingestion_kind": KIND,
                    "original_filename": "Semana_18may_24may_2013.pdf"})),
        )
        cls.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,observed_on,records,error) "
            "VALUES(%s,%s,'failed',%s,%s,%s,4201,%s)",
            (URL, KIND, NEW, DID, date(2013, 5, 24), OWN_ERROR),
        )
        cls.canonical_checkpoints = (
            (OLD, "official:catalog-start:official-catalog-v1:2026-10-05", 4201),
            (OLD, "official:catalog-start:official-catalog-v1:2026-10-08", 4201),
            (OLD, "official:complete", 4201),
        )
        cls._insert_quote_fixture(cls.old)
        cls._insert_quote_fixture(cls.expected)
        for locator in official_sources.MAY2013_WHITE_CORN_TARGETS:
            cls.db.execute(
                "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) "
                "VALUES(%s,%s,%s,%s,%s)",
                (DID, locator, NEW, Jsonb({"retired_by": locator + official_sources.MAY2013_WHITE_CORN_SUFFIX}),
                 official_sources.MAY2013_WHITE_CORN_REASON),
            )
        cls._replace_checkpoints(cls.canonical_checkpoints)
        cls.before = cls._old_quote_snapshot()

    @classmethod
    def _insert_quote_fixture(cls, fixture):
        columns = ",".join(FIELDS)
        with cls.db.cursor().copy(f"COPY official_price_quote ({columns}) FROM STDIN") as copy:
            for row in fixture:
                copy.write_row((
                    row["document_id"], row["source_locator"], row["parser_version"],
                    row["quote_key"], row["product_id"], row["product_name"], row["category"],
                    row["publisher"], row["series"], row["basis"], row["currency"], row["unit"],
                    row["market"], date.fromisoformat(row["observed_on"]),
                    date.fromisoformat(row["period_start"]) if row.get("period_start") else None,
                    Decimal(str(row["price"])) if row.get("price") is not None else None,
                    Decimal(str(row["min_price"])) if row.get("min_price") is not None else None,
                    Decimal(str(row["max_price"])) if row.get("max_price") is not None else None,
                    row["source_page"], Jsonb(row.get("details") or {}),
                ))

    @classmethod
    def _replace_checkpoints(cls, checkpoints):
        cls.db.execute("DELETE FROM ingestion_checkpoint WHERE document_id=%s", (DID,))
        if checkpoints:
            with cls.db.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) VALUES(%s,%s,%s,%s)",
                    [(DID, *checkpoint) for checkpoint in checkpoints],
                )

    @classmethod
    def _old_quote_snapshot(cls):
        return cls.db.execute(
            "SELECT " + ",".join(FIELDS) + ",xmin::text FROM official_price_quote "
            "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
            (DID, OLD),
        ).fetchall()

    def setUp(self):
        self.db.execute(
            "UPDATE ingestion_asset SET status='failed',processor_version=%s,document_id=%s,"
            "observed_on=%s,records=4201,error=%s WHERE url=%s",
            (NEW, DID, date(2013, 5, 24), OWN_ERROR, URL),
        )
        self._replace_checkpoints(self.canonical_checkpoints)

    def assert_old_vector_unchanged(self):
        after = self._old_quote_snapshot()
        self.assertEqual(after, self.before)
        self.assertEqual(len(after), 4201)
        self.assertEqual(
            official_sources._may2013_digest([dict(zip(FIELDS, row[:-1])) for row in after]),
            official_sources.MAY2013_WHITE_CORN_PRIOR_SHA256,
        )

    def test_captured_failed_revision_with_exact_completed_old_history_is_retryable(self):
        body = official_sources._validate_may2013_heading_source(self.db, URL, DID, KIND)
        self.assertEqual(body, self.body)
        self.assertEqual(
            retained_may2013_white_corn_original(self.db, URL, KIND, NEW, NEW),
            self.body,
        )
        self.assert_old_vector_unchanged()

    def test_worker_failed_to_pending_transition_keeps_exact_source_replay_eligible(self):
        # process_asset marks a failed asset pending before calling the source
        # adapter. The prior version accepted the failed tuple but rejected
        # this exact in-flight tuple, so every scheduled retry failed again.
        self.db.execute(
            "UPDATE ingestion_asset SET status='pending' WHERE url=%s", (URL,)
        )
        self.assertEqual(
            official_sources._validate_may2013_heading_source(
                self.db, URL, DID, KIND
            ),
            self.body,
        )
        self.assertEqual(
            retained_may2013_white_corn_original(self.db, URL, KIND, NEW, NEW),
            self.body,
        )
        self.assertIsNone(
            retained_may2013_white_corn_original(
                self.db, URL + "?alias", KIND, NEW, NEW
            )
        )
        self.assertIsNone(
            retained_may2013_white_corn_original(
                self.db, URL, KIND, OLD, NEW
            )
        )
        self.assert_old_vector_unchanged()

    def test_retained_bytes_helper_rejects_forged_error_version_and_source_metadata(self):
        self.assertIsNone(
            retained_may2013_white_corn_original(self.db, URL, KIND, OLD, OLD)
        )
        self.db.execute(
            "UPDATE ingestion_asset SET error='ValueError: unrelated error' WHERE url=%s",
            (URL,),
        )
        self.assertIsNone(
            retained_may2013_white_corn_original(self.db, URL, KIND, NEW, NEW)
        )
        self.db.execute("UPDATE ingestion_asset SET error=%s WHERE url=%s", (OWN_ERROR, URL))

        class OneRow:
            def __init__(self, row): self.row = tuple(row)
            def fetchone(self): return self.row

        class ChangedMetadataReadback:
            def execute(self, sql, params=None):
                result = self_db.execute(sql, params)
                if "SELECT id,title,publisher,source_url" in sql:
                    row = list(result.fetchone())
                    row[9] = {"retention": "temporary", "ingestion_kind": KIND,
                              "original_filename": "Semana_18may_24may_2013.pdf"}
                    return OneRow(row)
                return result

        self_db = self.db
        with self.assertRaisesRegex(ValueError, "Exact May 2013 original metadata"):
            retained_may2013_white_corn_original(
                ChangedMetadataReadback(), URL, KIND, NEW, NEW
            )
        self.assert_old_vector_unchanged()

    def test_completed_v24_asset_accepts_exact_bounded_old_catalog_history(self):
        self.db.execute(
            "UPDATE ingestion_asset SET status='complete',processor_version=%s,error=NULL WHERE url=%s",
            (OLD, URL),
        )
        self.assertEqual(official_sources._validate_may2013_heading_source(self.db, URL, DID, KIND), self.body)
        self.assert_old_vector_unchanged()

    def test_new_revision_catalog_start_resumes_after_full_old_history(self):
        from pipelines.ingestion.official_catalog import VERSION as catalog_version
        new_start = (NEW, f"official:catalog-start:{catalog_version}:2026-10-10", 4203)
        self._replace_checkpoints(self.canonical_checkpoints + (new_start,))
        self.db.execute(
            "UPDATE ingestion_asset SET status='pending',records=4201,error=%s WHERE url=%s",
            ("Official catalog refresh deferred after 256 of 4203 identities", URL),
        )
        self.assertEqual(official_sources._validate_may2013_heading_source(self.db, URL, DID, KIND), self.body)
        self.assert_old_vector_unchanged()

    def test_new_revision_complete_and_replay_pending_states_validate_full_cohort(self):
        from pipelines.ingestion.official_catalog import VERSION as catalog_version
        new_start = (NEW, f"official:catalog-start:{catalog_version}:2026-10-10", 4203)
        new_complete = (NEW, "official:complete", 4201)
        checkpoints = self.canonical_checkpoints + (new_start, new_complete)
        for status in ("complete", "pending"):
            with self.subTest(status=status):
                self._replace_checkpoints(checkpoints)
                self.db.execute(
                    "UPDATE ingestion_asset SET status=%s,processor_version=%s,records=4201,error=NULL WHERE url=%s",
                    (status, NEW, URL),
                )
                self.assertEqual(official_sources._validate_may2013_heading_source(self.db, URL, DID, KIND), self.body)
                self.assert_old_vector_unchanged()

    def test_wrong_error_or_unrecognized_checkpoint_history_fails_closed(self):
        invalid = {
            "altered-own-error": (self.canonical_checkpoints, "ValueError: different lifecycle error"),
            "missing-required-oct5-anchor": (self.canonical_checkpoints[1:], OWN_ERROR),
            "unknown-canonical-day": ((self.canonical_checkpoints[0],
                (OLD, "official:catalog-start:official-catalog-v1:2026-10-09", 4201),
                self.canonical_checkpoints[2]), OWN_ERROR),
            "wrong-old-version": ((self.canonical_checkpoints[0],
                ("official-v2:dane-weekly-v25", self.canonical_checkpoints[1][1], 4201),
                self.canonical_checkpoints[2]), OWN_ERROR),
            "wrong-checkpoint-count": ((self.canonical_checkpoints[0],
                (OLD, self.canonical_checkpoints[1][1], 4200), self.canonical_checkpoints[2]), OWN_ERROR),
            "extra-unknown-step": ((self.canonical_checkpoints[0],
                (OLD, "official:partial", 4201), self.canonical_checkpoints[1],
                self.canonical_checkpoints[2]), OWN_ERROR),
            "noncanonical-day": ((self.canonical_checkpoints[0],
                (OLD, "official:catalog-start:official-catalog-v1:2026-10-08T00:00:00", 4201),
                self.canonical_checkpoints[2]), OWN_ERROR),
        }
        for label, (checkpoints, error) in invalid.items():
            with self.subTest(case=label):
                self.db.execute("UPDATE ingestion_asset SET error=%s WHERE url=%s", (error, URL))
                self._replace_checkpoints(checkpoints)
                with self.assertRaisesRegex(ValueError, "May 2013 asset is outside"):
                    official_sources._validate_may2013_heading_source(self.db, URL, DID, KIND)
                self.assert_old_vector_unchanged()
                self.db.execute("UPDATE ingestion_asset SET error=%s WHERE url=%s", (OWN_ERROR, URL))
                self._replace_checkpoints(self.canonical_checkpoints)
        with self.subTest(case="duplicate-start-is-rejected-by-checkpoint-key"):
            duplicate = (self.canonical_checkpoints[0], *self.canonical_checkpoints)
            with self.assertRaises(psycopg.errors.UniqueViolation):
                with self.db.transaction():
                    self._replace_checkpoints(duplicate)
            self.assert_old_vector_unchanged()

    @classmethod
    def tearDownClass(cls):
        cls.db.execute(f'DROP SCHEMA IF EXISTS "{cls.schema}" CASCADE')
        cls.db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

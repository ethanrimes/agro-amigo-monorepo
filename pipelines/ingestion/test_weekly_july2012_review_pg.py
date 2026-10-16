"""Exact July 2012 review publication against an owned PostgreSQL fixture.

Requires a fresh disposable local database on a /tmp/agro-july2012-* socket,
with database name agro_july2012_private_*. It creates TEMP shadow tables only.
"""
from __future__ import annotations

import hashlib
import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import dane_weekly as DANE, official_sources as OFFICIAL, official_catalog, worker

SOURCE_PATH = Path(__file__).parent / "testdata/dane_weekly_2012_07_19_original.pdf"
SOURCE_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana14_19julio_2012.pdf"
SOURCE_ID = "fd66a34201085c864a2953e2e8ae56e593f2c12d897fdcb95e14bb1589c70856"
KIND = "dane-weekly-pdf"
REVIEW_SUFFIX = ":july2012-period-conflict-review-v1"
BASE_VERSION = "official-v2:dane-weekly-v24"
REVISION = BASE_VERSION + REVIEW_SUFFIX
EXPECTED_REVIEWS = 2983


class July2012RevisionWiring(unittest.TestCase):
    def test_only_exact_weekly_asset_receives_review_revision(self):
        self.assertEqual(worker.parser_version(KIND), BASE_VERSION)
        self.assertEqual(worker.parser_version(KIND, SOURCE_URL), REVISION)
        self.assertEqual(worker.asset_parser_version(KIND, SOURCE_URL), REVISION)
        self.assertEqual(worker.parser_version(KIND, SOURCE_URL + "?copy=1"), BASE_VERSION)
        self.assertEqual(worker.asset_parser_version(KIND, SOURCE_URL + "?copy=1"), BASE_VERSION)


@unittest.skipUnless(os.environ.get("AGRO_JULY2012_PRIVATE_PG_DSN"),
                     "Explicit owned July 2012 private PostgreSQL DSN required")
class July2012ReviewPublicationPG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ["AGRO_JULY2012_PRIVATE_PG_DSN"]
        cls.db = psycopg.connect(cls.dsn, autocommit=True)
        if (not str(cls.db.info.host).startswith("/tmp/agro-july2012-")
                or not cls.db.info.dbname.startswith("agro_july2012_private_")
                or cls.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None):
            cls.db.close()
            raise RuntimeError("Only the owned local July 2012 private PostgreSQL fixture is allowed")
        cls.db.execute("SET statement_timeout='90s'")
        cls._create_temp_schema()

    @classmethod
    def _create_temp_schema(cls):
        db = cls.db
        db.execute("""
            CREATE TEMP TABLE source_document(
              id text PRIMARY KEY, title text, publisher text, source_url text,
              media_type text, kind text, reference_period text, page_count integer,
              content bytea, metadata jsonb
            );
            CREATE TEMP TABLE ingestion_asset(
              url text PRIMARY KEY, kind text, document_id text, observed_on date,
              status text, processor_version text, records integer, error text
            );
            CREATE TEMP TABLE official_price_quote(
              document_id text NOT NULL, source_locator text NOT NULL,
              parser_version text NOT NULL, parsed_at timestamptz NOT NULL DEFAULT now(),
              PRIMARY KEY(document_id,source_locator,parser_version)
            );
            CREATE TEMP TABLE official_source_review(
              document_id text NOT NULL, source_locator text NOT NULL,
              parser_version text NOT NULL, record jsonb NOT NULL,
              reason text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
              PRIMARY KEY(document_id,source_locator,parser_version)
            );
            CREATE TEMP TABLE ingestion_checkpoint(
              document_id text NOT NULL, processor_version text NOT NULL,
              step text NOT NULL, records bigint NOT NULL DEFAULT 0,
              completed_at timestamptz NOT NULL DEFAULT now(),
              PRIMARY KEY(document_id,processor_version,step)
            );
        """)

    def setUp(self):
        db = self.db
        for table in ("official_source_review", "official_price_quote",
                      "ingestion_checkpoint", "ingestion_asset", "source_document"):
            db.execute(f"TRUNCATE pg_temp.{table}")
        body = SOURCE_PATH.read_bytes()
        self.assertEqual(len(body), 1_165_022)
        self.assertEqual(hashlib.sha256(body).hexdigest(), SOURCE_ID)
        db.execute(
            "INSERT INTO pg_temp.source_document "
            "(id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata) "
            "VALUES(%s,%s,%s,%s,'application/pdf','original','2012-07-19',34,%s,%s)",
            (SOURCE_ID, "DANE · SIPSA - Semana14_19julio_2012.pdf", "DANE · SIPSA",
             SOURCE_URL, body, Jsonb({"retention": "permanent", "ingestion_kind": KIND,
                                      "original_filename": "Semana14_19julio_2012.pdf"})),
        )
        db.execute(
            "INSERT INTO pg_temp.ingestion_asset "
            "(url,kind,document_id,observed_on,status,processor_version,records,error) "
            "VALUES(%s,%s,%s,'2012-07-19','failed',%s,0,%s)",
            (SOURCE_URL, KIND, SOURCE_ID, REVISION,
             "ValueError: Weekly PDF page 23 has conflicting printed periods"),
        )
        self.rows = DANE.parse_pdf(body, SOURCE_URL)
        self.assertEqual(len(self.rows), EXPECTED_REVIEWS)
        self.source_before = self.source_snapshot()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def source_snapshot(self):
        return self.db.execute(
            "SELECT id,title,publisher,source_url,media_type,kind,reference_period,"
            "page_count,content,metadata,xmin::text FROM pg_temp.source_document WHERE id=%s",
            (SOURCE_ID,),
        ).fetchone()

    def counts(self):
        return tuple(self.db.execute(
            f"SELECT count(*) FROM pg_temp.{table}"
        ).fetchone()[0] for table in (
            "official_price_quote", "official_source_review", "ingestion_checkpoint"))

    def patched_publish(self, rows=None, *, document_id=SOURCE_ID,
                        source_url=SOURCE_URL, kind=KIND):
        with patch.object(official_catalog, "mark_document_dirty"), \
                patch.object(official_catalog, "refresh_document"):
            return OFFICIAL.publish_rows(
                self.db, self.rows if rows is None else rows,
                document_id, kind, source_url=source_url,
            )

    def assert_rejected_before_writes(self, **kwargs):
        before = self.counts()
        with self.assertRaises(ValueError):
            self.patched_publish(**kwargs)
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.source_snapshot(), self.source_before)

    def test_publishes_all_reviews_without_quotes_and_replays_idempotently(self):
        before = self.counts()
        self.assertEqual(self.patched_publish(), 0)
        self.assertEqual(self.counts(), (0, EXPECTED_REVIEWS, 1))
        reviews = self.db.execute(
            "SELECT source_locator,record,reason,xmin::text FROM pg_temp.official_source_review "
            "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
            (SOURCE_ID, REVISION),
        ).fetchall()
        self.assertEqual(len(reviews), EXPECTED_REVIEWS)
        self.assertEqual(len({row[0] for row in reviews}), EXPECTED_REVIEWS)
        self.assertTrue(all(row[1]["price"] is None and row[1]["date"] is None
                            and row[1]["details"]["quality_issue"] for row in reviews))
        review_xmins = {row[0]: row[3] for row in reviews}
        checkpoint_before = self.db.execute(
            "SELECT processor_version,step,records,xmin::text FROM pg_temp.ingestion_checkpoint "
            "WHERE document_id=%s ORDER BY processor_version,step", (SOURCE_ID,)
        ).fetchall()
        self.assertEqual(checkpoint_before[0][:3], (REVISION, "official:complete", 0))
        self.assertEqual(self.source_snapshot(), self.source_before)

        self.assertEqual(self.patched_publish(), 0)
        self.assertEqual(self.counts(), (0, EXPECTED_REVIEWS, 1))
        reviews_after = self.db.execute(
            "SELECT source_locator,xmin::text FROM pg_temp.official_source_review "
            "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
            (SOURCE_ID, REVISION),
        ).fetchall()
        self.assertEqual(dict(reviews_after), review_xmins)
        self.assertEqual(self.db.execute(
            "SELECT processor_version,step,records,xmin::text FROM pg_temp.ingestion_checkpoint "
            "WHERE document_id=%s ORDER BY processor_version,step", (SOURCE_ID,)
        ).fetchall(), checkpoint_before)
        self.assertEqual(self.source_snapshot(), self.source_before)
        self.assertEqual(before, (0, 0, 0))

    def test_wrong_source_identity_and_kind_fail_before_writes(self):
        self.assert_rejected_before_writes(source_url=SOURCE_URL + "?copy=1")
        self.assert_rejected_before_writes(document_id="0" * 64)
        self.assert_rejected_before_writes(kind="dane-weekly-xlsx")

    def test_wrong_reference_day_fails_before_writes(self):
        before = self.counts()
        class Rollback(Exception):
            pass
        with self.assertRaises(Rollback):
            with self.db.transaction():
                self.db.execute("UPDATE pg_temp.source_document SET reference_period='2012-07-20' WHERE id=%s", (SOURCE_ID,))
                with self.assertRaisesRegex(ValueError, "reference day"):
                    self.patched_publish()
                self.assertEqual(self.counts(), before)
                raise Rollback()
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.source_snapshot(), self.source_before)

    def test_malformed_rows_partial_duplicates_and_any_typed_quote_fail_before_writes(self):
        for name, change in (
            ("partial", lambda rows: rows[:-1]),
            ("duplicate locator", lambda rows: [*rows[:-1], rows[0]]),
            ("price", lambda rows: [{**rows[0], "price": 1}, *rows[1:]]),
            ("date", lambda rows: [{**rows[0], "date": "2012-07-19"}, *rows[1:]]),
            ("quality issue", lambda rows: [{**rows[0], "details": {**rows[0]["details"], "quality_issue": None}}, *rows[1:]]),
            ("missing details", lambda rows: [{**rows[0], "details": None}, *rows[1:]]),
            ("caption", lambda rows: [{**rows[0], "details": {**rows[0]["details"], "literal_printed_period_heading": "2012 (julio 14 a 19)"}}, *rows[1:]]),
            ("filename range", lambda rows: [{**rows[0], "details": {**rows[0]["details"], "literal_filename_period_end": "2012-07-20"}}, *rows[1:]]),
        ):
            with self.subTest(name=name):
                self.assert_rejected_before_writes(rows=change(self.rows))

        self.db.execute(
            "INSERT INTO pg_temp.official_price_quote(document_id,source_locator,parser_version) "
            "VALUES(%s,'old typed row','official-v2:dane-weekly-v24')", (SOURCE_ID,)
        )
        before = self.counts()
        with self.assertRaisesRegex(ValueError, "already has typed price quotes"):
            self.patched_publish()
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.source_snapshot(), self.source_before)

    def test_incomplete_existing_review_revision_fails_before_writes(self):
        self.patched_publish()
        self.db.execute(
            "DELETE FROM pg_temp.official_source_review WHERE document_id=%s AND parser_version=%s "
            "AND source_locator=(SELECT min(source_locator) FROM pg_temp.official_source_review "
            "WHERE document_id=%s AND parser_version=%s)",
            (SOURCE_ID, REVISION, SOURCE_ID, REVISION),
        )
        before = self.counts()
        with self.assertRaisesRegex(ValueError, "review revision is incomplete"):
            self.patched_publish()
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.source_snapshot(), self.source_before)


@unittest.skipUnless(os.environ.get("AGRO_JULY2012_WORKER_PG_DSN"),
                     "Explicit owned full-schema July worker PostgreSQL DSN required")
class July2012WorkerLifecyclePG(unittest.TestCase):
    """Exercise the complete worker path against an owned full-schema database."""

    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ["AGRO_JULY2012_WORKER_PG_DSN"]
        cls.db = psycopg.connect(cls.dsn, autocommit=True)
        if (not str(cls.db.info.host).startswith("/tmp/agro-july2012-worker-")
                or not cls.db.info.dbname.startswith("agro_july2012_worker_")
                or cls.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None):
            cls.db.close()
            raise RuntimeError("Only the owned full-schema July worker PostgreSQL fixture is allowed")
        cls.db.execute("SET statement_timeout='180s'")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_real_worker_replays_full_review_and_keeps_source_immutable(self):
        db = self.db
        body = SOURCE_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), SOURCE_ID)
        self.assertEqual(len(body), 1_165_022)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM source_document WHERE id=%s", (SOURCE_ID,)
        ).fetchone()[0], 0)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM ingestion_asset WHERE url=%s", (SOURCE_URL,)
        ).fetchone()[0], 0)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (SOURCE_ID,)
        ).fetchone()[0], 0)

        metadata = {
            "retention": "permanent", "ingestion_kind": KIND,
            "original_filename": "Semana14_19julio_2012.pdf",
        }
        db.execute(
            "INSERT INTO source_document "
            "(id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata) "
            "VALUES(%s,%s,%s,%s,'application/pdf','original','2012-07-19',34,%s,%s)",
            (SOURCE_ID, "DANE · SIPSA - Semana14_19julio_2012.pdf", "DANE · SIPSA",
             SOURCE_URL, body, Jsonb(metadata)),
        )
        db.execute(
            "INSERT INTO ingestion_asset "
            "(url,kind,document_id,observed_on,status,processor_version,records,error) "
            "VALUES(%s,%s,%s,%s,'failed',%s,0,%s)",
            (SOURCE_URL, KIND, SOURCE_ID, date(2012, 7, 19), BASE_VERSION,
             "ValueError: Weekly PDF page 23 has conflicting printed periods"),
        )

        def source_snapshot():
            return db.execute(
                "SELECT id,title,publisher,source_url,media_type,kind,reference_period,"
                "page_count,content,metadata,xmin::text FROM source_document WHERE id=%s",
                (SOURCE_ID,),
            ).fetchone()

        source_before = source_snapshot()
        fetch_calls = []

        def exact_fetch(_db, url, force=False, *, require_bytes=False):
            self.assertEqual(url, SOURCE_URL)
            fetch_calls.append((url, bool(force), bool(require_bytes)))
            return body

        from . import blob_archive

        def exact_blob(digest, data, suffix, media_type):
            self.assertEqual(digest, SOURCE_ID)
            self.assertEqual(data, body)
            self.assertEqual(suffix, ".pdf")
            self.assertEqual(media_type, "application/pdf")

        review_state = None
        checkpoint_state = None
        with patch.object(worker, "fetch_asset", side_effect=exact_fetch), \
                patch.object(blob_archive, "retain_original_blob", side_effect=exact_blob):
            for pass_number in (1, 2):
                self.assertEqual(worker.process_asset(db, SOURCE_URL, KIND, date(2012, 7, 19)), 0)
                self.assertEqual(source_snapshot(), source_before)
                asset = db.execute(
                    "SELECT status,records,error,processor_version,document_id,observed_on "
                    "FROM ingestion_asset WHERE url=%s", (SOURCE_URL,),
                ).fetchone()
                self.assertEqual(asset, (
                    "review", 0, OFFICIAL.JULY2012_REVIEW_REASON, REVISION,
                    SOURCE_ID, date(2012, 7, 19),
                ))
                self.assertEqual(db.execute(
                    "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (SOURCE_ID,)
                ).fetchone()[0], 0)
                reviews = db.execute(
                    "SELECT source_locator,record,reason,xmin::text FROM official_source_review "
                    "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
                    (SOURCE_ID, REVISION),
                ).fetchall()
                self.assertEqual(len(reviews), EXPECTED_REVIEWS)
                self.assertEqual(len({row[0] for row in reviews}), EXPECTED_REVIEWS)
                self.assertTrue(all(
                    row[1]["price"] is None and row[1]["date"] is None
                    and row[1]["period_start"] is None
                    and row[1]["details"]["quality_issue"] == OFFICIAL.JULY2012_REVIEW_REASON
                    and row[2] == OFFICIAL.JULY2012_REVIEW_REASON
                    for row in reviews
                ))
                checkpoints = db.execute(
                    "SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint "
                    "WHERE document_id=%s AND step='official:complete' ORDER BY processor_version",
                    (SOURCE_ID,),
                ).fetchall()
                self.assertEqual(len(checkpoints), 1)
                self.assertEqual(checkpoints[0][:3], (REVISION, "official:complete", 0))
                self.assertEqual(db.execute(
                    "SELECT count(*) FROM official_source_review WHERE document_id=%s",
                    (SOURCE_ID,),
                ).fetchone()[0], EXPECTED_REVIEWS)
                if pass_number == 1:
                    review_state = {row[0]: row[3] for row in reviews}
                    checkpoint_state = checkpoints
                else:
                    self.assertEqual({row[0]: row[3] for row in reviews}, review_state)
                    self.assertEqual(checkpoints, checkpoint_state)

        self.assertEqual(len(fetch_calls), 2)
        self.assertEqual(source_snapshot(), source_before)


if __name__ == "__main__":
    unittest.main(verbosity=2)

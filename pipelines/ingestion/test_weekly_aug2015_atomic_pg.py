"""Exact Aug 2015 full-original, atomic replay, and concurrent reader controls.

Requires a fresh owned full-schema PG database. The caller provisions/stops PG;
the test never contacts a source site or production database.
"""

import contextlib
import hashlib
import io
import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import dane_weekly, official_sources, queue_plan, worker, write_pacing
from .resumable_inputs import WorkDeferred


DID = dane_weekly.AUGUST_2015_WRAP_SHA
URL = dane_weekly.AUGUST_2015_WRAP_URL
KIND = "dane-weekly-pdf"
OLD = "official-v2:dane-weekly-v24"
NEW = "official-v2:aug2015-medellin-market-wrap-v1:dane-weekly-v24"
PDF = Path(__file__).parent / "testdata" / "weekly_aug2015" / f"{DID}.pdf"


@unittest.skipUnless(os.environ.get("AGRO_WEEKLY_AUG2015_TEST_DSN"),
                     "Explicit fresh owned full-schema PostgreSQL DSN required")
class August2015AtomicPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ["AGRO_WEEKLY_AUG2015_TEST_DSN"]
        cls.db = psycopg.connect(cls.dsn, autocommit=True)
        if (not str(cls.db.info.host).startswith("/tmp/agro-weekly-")
                or not cls.db.info.dbname.startswith("agro_weekly_")
                or cls.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None):
            cls.db.close()
            raise RuntimeError("Only an owned Unix-socket weekly database is allowed")
        cls.db.execute("SET statement_timeout='90s'")
        for table in ("source_document", "ingestion_asset", "official_price_quote",
                      "official_source_review", "ingestion_checkpoint"):
            if cls.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                cls.db.close()
                raise RuntimeError("Exact weekly database must be empty")
        cls.body = PDF.read_bytes()
        if hashlib.sha256(cls.body).hexdigest() != DID:
            raise RuntimeError("Exact full-original fixture bytes changed")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_full_original_atomic_worker_queue_and_reader(self):
        db = self.db
        self.assertEqual(worker.parser_version(KIND, URL), NEW)
        self.assertEqual(worker.asset_parser_version(KIND, URL), NEW)
        native = dane_weekly.parse_pdf(self.body, URL)
        with patch.object(dane_weekly, "AUGUST_2015_WRAP_URL", "_old_parser_"):
            old = dane_weekly.parse_pdf(self.body, URL)
        self.assertEqual((len(native), len(old)), (4472, 4472))
        self.assertEqual(sum(r["price"] is not None for r in native), 4335)
        self.assertEqual(sum(r["price"] is None for r in native), 137)
        self.assertEqual(
            hashlib.sha256(json.dumps(native, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest(),
            dane_weekly.AUGUST_2015_WRAP_ROWS_SHA,
        )
        by_new = {r["source_locator"]: r for r in native}
        by_old = {r["source_locator"]: r for r in old}
        self.assertEqual(set(by_new), set(by_old))
        changed = {k for k in by_new if by_new[k]["market"] != by_old[k]["market"]}
        self.assertEqual(len(changed), 392)
        self.assertEqual(sum(by_new[k]["price"] is not None for k in changed), 374)
        for locator in set(by_new) - changed:
            self.assertEqual(by_new[locator], by_old[locator])

        db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
            "reference_period,page_count,content,metadata) VALUES(%s,'DANE weekly','DANE',"
            "%s,'application/pdf','original','2015-08-14',44,%s,%s)",
            (DID, URL, self.body, Jsonb({"ingestion_kind": KIND})),
        )
        db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,"
            "observed_on,checked_at,records) VALUES(%s,%s,'complete',%s,%s,"
            "'2015-08-14',now()-interval '7 hours',4335)",
            (URL, KIND, OLD, DID),
        )
        real_version = worker.parser_version

        def previous_version(kind, url=None):
            return OLD if kind == KIND and url == URL else real_version(kind, url)

        with patch.object(worker, "parser_version", side_effect=previous_version), \
                patch.object(write_pacing.time, "sleep"):
            self.assertEqual(official_sources.publish_rows(db, old, DID, KIND,
                                                           source_url=URL), 4335)
        prior_public = dict(db.execute(
            "SELECT source_locator,to_jsonb(p) FROM published_official_price p "
            "WHERE document_id=%s", (DID,),
        ).fetchall())
        self.assertEqual(len(prior_public), 4335)
        old_quotes = {r[0]: (r[1], r[2]) for r in db.execute(
            "SELECT source_locator,to_jsonb(q),xmin::text FROM official_price_quote q "
            "WHERE document_id=%s AND parser_version=%s", (DID, OLD),
        ).fetchall()}
        old_reviews = dict(db.execute(
            "SELECT source_locator,xmin::text FROM official_source_review "
            "WHERE document_id=%s AND parser_version=%s", (DID, OLD),
        ).fetchall())
        self.assertEqual((len(old_quotes), len(old_reviews)), (4335, 137))

        # The owned schema has bare roles. Give the local ingestion role only
        # mutable worker DML; immutable original/archive UPDATE remains denied.
        db.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO agro_ingestor")
        db.execute("GRANT INSERT,UPDATE ON ingestion_run,ingestion_asset,"
                   "official_catalog_current TO agro_ingestor")
        db.execute("GRANT UPDATE ON source_ocr_task TO agro_ingestor")
        db.execute("GRANT INSERT ON source_document,official_price_quote,"
                   "official_source_review,ingestion_checkpoint TO agro_ingestor")
        self.assertFalse(db.execute(
            "SELECT has_table_privilege('agro_ingestor','source_document','UPDATE')"
        ).fetchone()[0])
        self.assertFalse(db.execute(
            "SELECT has_table_privilege('agro_ingestor','source_archive_member','UPDATE')"
        ).fetchone()[0])

        def first_batch_reader(*_args, **_kwargs):
            with psycopg.connect(self.dsn, autocommit=True,
                                 options="-c statement_timeout=8000 -c lock_timeout=2000") as reader:
                reader.execute("SET ROLE agro_reader")
                with reader.transaction():
                    reader.execute("SET TRANSACTION READ ONLY")
                    visible = dict(reader.execute(
                        "SELECT source_locator,to_jsonb(p) FROM published_official_price p "
                        "WHERE document_id=%s", (DID,),
                    ).fetchall())
                self.assertEqual(visible, prior_public)
            raise WorkDeferred("Official source validated; committed quote batches will resume")

        db.execute("SET ROLE agro_ingestor")
        try:
            with patch.object(worker, "connect", return_value=contextlib.nullcontext(db)), \
                    patch.object(worker, "fetch_asset", side_effect=AssertionError("HTTP forbidden")), \
                    patch("pipelines.ingestion.blob_archive.retain_original_blob"), \
                    patch("pipelines.ingestion.ocr.drain", return_value={"processed": 0}), \
                    patch.object(write_pacing, "pause_between_batches",
                                 side_effect=first_batch_reader), \
                    contextlib.redirect_stdout(io.StringIO()):
                summary = worker.run(mode="discover", limit=1, time_budget=120,
                                     ocr_limit=0, ocr_scan_limit=0, asset_url=URL)
            self.assertTrue(any(row.get("url") == URL for row in summary["deferred"]))
        finally:
            db.execute("RESET ROLE")
        self.assertEqual(db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s "
            "AND parser_version=%s", (DID, NEW),
        ).fetchone()[0], 0)
        self.assertEqual(dict(db.execute(
            "SELECT source_locator,to_jsonb(p) FROM published_official_price p "
            "WHERE document_id=%s", (DID,),
        ).fetchall()), prior_public)
        self.assertEqual(db.execute(
            "SELECT status,processor_version,records FROM ingestion_asset WHERE url=%s",
            (URL,),
        ).fetchone(), ("pending", OLD, 4335))
        self.assertIsNone(db.execute(
            "SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s AND "
            "processor_version=%s AND step='official:complete'", (DID, NEW),
        ).fetchone())
        self.assertTrue(any(row[0] == URL and row[1] == KIND
                            for row in queue_plan.repair_candidates(db, limit=8)))

        db.execute("SET ROLE agro_ingestor")
        try:
            with patch.object(worker, "fetch_asset", side_effect=AssertionError("HTTP forbidden")), \
                    patch("pipelines.ingestion.blob_archive.retain_original_blob"), \
                    patch.object(write_pacing.time, "sleep"):
                self.assertEqual(worker.process_asset(db, URL, KIND, date(2015, 8, 14)), 4335)
                new_xmins = dict(db.execute(
                    "SELECT source_locator,xmin::text FROM official_price_quote WHERE "
                    "document_id=%s AND parser_version=%s", (DID, NEW),
                ).fetchall())
                self.assertEqual(len(new_xmins), 4335)
                self.assertEqual(worker.process_asset(db, URL, KIND, date(2015, 8, 14)), 0)
                self.assertEqual(dict(db.execute(
                    "SELECT source_locator,xmin::text FROM official_price_quote WHERE "
                    "document_id=%s AND parser_version=%s", (DID, NEW),
                ).fetchall()), new_xmins)
        finally:
            db.execute("RESET ROLE")
        self.assertEqual(db.execute(
            "SELECT status,processor_version,records FROM ingestion_asset WHERE url=%s",
            (URL,),
        ).fetchone(), ("complete", NEW, 4335))
        self.assertEqual(db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND "
            "processor_version=%s AND step='official:complete'", (DID, NEW),
        ).fetchone(), (4335,))
        self.assertEqual(db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s "
            "AND parser_version=%s", (DID, NEW),
        ).fetchone()[0], 137)
        self.assertEqual({r[0]: (r[1], r[2]) for r in db.execute(
            "SELECT source_locator,to_jsonb(q),xmin::text FROM official_price_quote q "
            "WHERE document_id=%s AND parser_version=%s", (DID, OLD),
        ).fetchall()}, old_quotes)
        self.assertEqual(dict(db.execute(
            "SELECT source_locator,xmin::text FROM official_source_review "
            "WHERE document_id=%s AND parser_version=%s", (DID, OLD),
        ).fetchall()), old_reviews)
        current = {r[0]: r[1:] for r in db.execute(
            "SELECT source_locator,market,quote_key,price,min_price,max_price "
            "FROM published_official_price WHERE document_id=%s", (DID,),
        ).fetchall()}
        self.assertEqual(len(current), 4335)
        for locator in changed:
            expected = by_new[locator]
            if expected["price"] is None:
                self.assertNotIn(locator, current)
                continue
            self.assertEqual(current[locator][0], expected["market"])
            self.assertEqual(tuple(float(x) for x in current[locator][2:]),
                             tuple(expected[k] for k in ("price", "min", "max")))
            old_key = db.execute(
                "SELECT quote_key FROM official_price_quote WHERE document_id=%s "
                "AND source_locator=%s AND parser_version=%s", (DID, locator, OLD),
            ).fetchone()[0]
            self.assertIsNone(db.execute(
                "SELECT 1 FROM published_official_price WHERE document_id=%s "
                "AND source_locator=%s AND quote_key=%s", (DID, locator, old_key),
            ).fetchone())

        # Completion cannot make a wrong or missing requested day acceptable.
        # These guards run after all records exist, so a false positive would
        # otherwise be hidden by a no-op checkpoint shortcut.
        current_full = dict(db.execute(
            "SELECT source_locator,to_jsonb(p) FROM published_official_price p "
            "WHERE document_id=%s", (DID,),
        ).fetchall())
        new_full = {r[0]: (r[1], r[2]) for r in db.execute(
            "SELECT source_locator,to_jsonb(q),xmin::text FROM official_price_quote q "
            "WHERE document_id=%s AND parser_version=%s", (DID, NEW),
        ).fetchall()}
        complete_cp = db.execute(
            "SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='official:complete'", (DID, NEW),
        ).fetchone()
        for wrong_day in (date(2015, 8, 13), None):
            with patch.object(worker, "fetch_asset", side_effect=AssertionError("HTTP forbidden")):
                with self.assertRaisesRegex(ValueError, "identity or date changed"):
                    worker.process_asset(db, URL, KIND, wrong_day)
            self.assertEqual(dict(db.execute(
                "SELECT source_locator,to_jsonb(p) FROM published_official_price p "
                "WHERE document_id=%s", (DID,),
            ).fetchall()), current_full)
            self.assertEqual({r[0]: (r[1], r[2]) for r in db.execute(
                "SELECT source_locator,to_jsonb(q),xmin::text FROM official_price_quote q "
                "WHERE document_id=%s AND parser_version=%s", (DID, NEW),
            ).fetchall()}, new_full)
            self.assertEqual(db.execute(
                "SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s "
                "AND processor_version=%s AND step='official:complete'", (DID, NEW),
            ).fetchone(), complete_cp)

    def test_exact_body_url_and_date_refusal(self):
        body = self.body
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            dane_weekly.parse_pdf(body + b"x", URL)
        other_url = URL.replace("14ago", "15ago")
        self.assertNotEqual(worker.parser_version(KIND, other_url), NEW)
        self.assertNotEqual(worker.asset_parser_version(KIND, other_url), NEW)
        self.assertEqual(hashlib.sha256(body).hexdigest(), DID)

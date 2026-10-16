"""Actual retained May 2013 worker replay on an owned full-schema database."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb

from pipelines.ingestion import dane_weekly, queue_plan, worker
from pipelines.ingestion.retained_pdf_upgrade import MAY2013_PENDING_URL


HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "testdata" / "may2013_white_corn_heading"
URL = dane_weekly.MAY2013_WHITE_CORN_URL
DID = dane_weekly.MAY2013_WHITE_CORN_SHA
KIND = "dane-weekly-pdf"
OLD = "official-v2:dane-weekly-v24"
NEW = "official-v2:may2013-white-corn-heading-v1:dane-weekly-v24"
OWN_ERROR = "ValueError: May 2013 asset is outside the pinned pending/completed lifecycle"
OLD_FIELDS = (
    "document_id", "source_locator", "parser_version", "quote_key", "product_id",
    "product_name", "category", "publisher", "series", "basis", "currency",
    "unit", "market", "observed_on", "period_start", "price", "min_price",
    "max_price", "source_page", "details",
)


def _owned_local_dsn(dsn: str) -> None:
    values = conninfo_to_dict(dsn)
    host = values.get("host", "")
    if (values.get("user") != "postgres" or values.get("dbname") != "postgres"
            or not re.fullmatch(r"/tmp/agro-may2013-worker-[A-Za-z0-9_-]+/socket", host)
            or values.get("hostaddr") or values.get("service") or values.get("servicefile")
            or not values.get("port", "").isdigit()
            or not 1024 <= int(values["port"]) <= 65535):
        raise RuntimeError("Only the explicitly owned May 2013 Unix-socket PG is allowed")


@unittest.skipUnless(os.environ.get("AGRO_MAY2013_WORKER_TEST_DSN"),
                     "Explicit owned May 2013 full-schema PostgreSQL DSN required")
class May2013ActualWorkerReplayPG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ["AGRO_MAY2013_WORKER_TEST_DSN"]
        _owned_local_dsn(dsn)
        cls.db = psycopg.connect(dsn, autocommit=True)
        if (cls.db.info.user != "postgres" or cls.db.info.dbname != "postgres"
                or not re.fullmatch(r"/tmp/agro-may2013-worker-[A-Za-z0-9_-]+/socket", str(cls.db.info.host))
                or cls.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None):
            cls.db.close()
            raise RuntimeError("May worker qualification is restricted to its owned local socket")
        cls.db.execute("SET statement_timeout='180s'; SET lock_timeout='2s'")
        for table in ("source_document", "ingestion_asset", "official_price_quote",
                      "official_source_review", "ingestion_checkpoint"):
            if cls.db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]:
                cls.db.close()
                raise RuntimeError("Fresh disposable May worker database must be empty")
        cls.body = (FIXTURE / "may2013_original.pdf").read_bytes()
        cls.old = json.loads((FIXTURE / "may2013_v24_quotes_4201_prior.json").read_text())
        if hashlib.sha256(cls.body).hexdigest() != DID or len(cls.body) != dane_weekly.MAY2013_WHITE_CORN_SIZE:
            raise AssertionError("Exact retained May source body changed")
        if len(cls.old) != 4201:
            raise AssertionError("Pinned v24 quote vector must contain 4,201 rows")
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
        cls.checkpoints = (
            (OLD, "official:catalog-start:official-catalog-v1:2026-10-05", 4201),
            (OLD, "official:catalog-start:official-catalog-v1:2026-10-08", 4201),
            (OLD, "official:complete", 4201),
        )
        with cls.db.cursor() as cur:
            cur.executemany(
                "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
                "VALUES(%s,%s,%s,%s)", [(DID, *row) for row in cls.checkpoints],
            )
        with cls.db.cursor().copy(f"COPY official_price_quote ({','.join(OLD_FIELDS)}) FROM STDIN") as copy:
            for row in cls.old:
                copy.write_row(tuple(
                    Jsonb(row.get(field) or {}) if field == "details"
                    else date.fromisoformat(row[field]) if field in ("observed_on", "period_start") and row.get(field)
                    else None if field == "period_start" and not row.get(field)
                    else row.get(field)
                    for field in OLD_FIELDS
                ))

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_failed_asset_replays_from_retained_original_and_is_immutable_on_refresh(self):
        db = self.db
        before_source = db.execute(
            "SELECT id,title,publisher,source_url,media_type,kind,reference_period,page_count,"
            "content,metadata,xmin::text FROM source_document WHERE id=%s", (DID,),
        ).fetchone()
        before_old = db.execute(
            "SELECT " + ",".join(OLD_FIELDS) + ",xmin::text FROM official_price_quote "
            "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
            (DID, OLD),
        ).fetchall()
        before_checkpoints = db.execute(
            "SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint "
            "WHERE document_id=%s ORDER BY processor_version,step", (DID,),
        ).fetchall()
        self.assertEqual([row[:3] for row in before_checkpoints], list(self.checkpoints))

        # The exact retained failure must be offered for repair and be allowed
        # through a DANE host cooldown with no publisher request.
        repair = [row[0] for row in queue_plan.repair_candidates(db, 8)]
        backfill = [row[0] for row in queue_plan.backfill_candidates(db, 1000)]
        self.assertIn(URL, repair + backfill)
        self.assertTrue(worker.retained_reparse_during_host_cooldown(db, URL, KIND))
        fetches = []

        def forbidden_first_fetch(*_args, **_kwargs):
            raise AssertionError("Exact May failure must replay from the retained PDF")

        with patch.object(worker, "fetch_asset", side_effect=forbidden_first_fetch) as fetch_asset, \
             patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=None), \
             patch("pipelines.ingestion.ocr.scan_document", return_value=[]), \
             patch("pipelines.ingestion.write_pacing.pause_between_batches", return_value=None):
            count = worker.process_asset(db, URL, KIND, date(2013, 5, 24))
            fetch_asset.assert_not_called()
            self.assertEqual(count, 4201)

        current_asset = db.execute(
            "SELECT status,document_id,processor_version,observed_on,records,error "
            "FROM ingestion_asset WHERE url=%s", (URL,),
        ).fetchone()
        self.assertEqual(current_asset[:2], ("complete", DID))
        self.assertEqual(current_asset[2], NEW)
        self.assertEqual(current_asset[3:5], (date(2013, 5, 24), 4201))
        self.assertIsNone(current_asset[5])
        new_quotes = db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s AND parser_version=%s",
            (DID, NEW),
        ).fetchone()[0]
        new_reviews = db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s AND parser_version=%s",
            (DID, NEW),
        ).fetchone()[0]
        self.assertEqual((new_quotes, new_reviews), (4201, 205))
        self.assertEqual(db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='official:complete'", (DID, NEW),
        ).fetchone(), (4201,))

        # The ordinary completed refresh is allowed to revalidate HTTP and
        # receives the unchanged exact publisher body. The completion shortcut
        # must avoid all quote/review/checkpoint/source writes.
        durable_before = (
            db.execute("SELECT to_jsonb(d),xmin::text FROM source_document d WHERE id=%s", (DID,)).fetchone(),
            db.execute("SELECT to_jsonb(q),xmin::text FROM official_price_quote q WHERE document_id=%s ORDER BY source_locator,parser_version", (DID,)).fetchall(),
            db.execute("SELECT to_jsonb(r),xmin::text FROM official_source_review r WHERE document_id=%s ORDER BY source_locator,parser_version", (DID,)).fetchall(),
            db.execute("SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s ORDER BY processor_version,step", (DID,)).fetchall(),
        )

        def same_publisher_body(_db, request_url, **_kwargs):
            fetches.append(request_url)
            self.assertEqual(request_url, URL)
            return self.body

        with patch.object(worker, "fetch_asset", side_effect=same_publisher_body) as fetch_asset, \
             patch("pipelines.ingestion.blob_archive.retain_original_blob", return_value=None):
            replay_count = worker.process_asset(db, URL, KIND, date(2013, 5, 24))
            fetch_asset.assert_called_once()
        self.assertEqual(replay_count, 4201)
        self.assertEqual(fetches, [URL])
        durable_after = (
            db.execute("SELECT to_jsonb(d),xmin::text FROM source_document d WHERE id=%s", (DID,)).fetchone(),
            db.execute("SELECT to_jsonb(q),xmin::text FROM official_price_quote q WHERE document_id=%s ORDER BY source_locator,parser_version", (DID,)).fetchall(),
            db.execute("SELECT to_jsonb(r),xmin::text FROM official_source_review r WHERE document_id=%s ORDER BY source_locator,parser_version", (DID,)).fetchall(),
            db.execute("SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s ORDER BY processor_version,step", (DID,)).fetchall(),
        )
        self.assertEqual(durable_after, durable_before)
        self.assertEqual(db.execute(
            "SELECT " + ",".join(OLD_FIELDS) + ",xmin::text FROM official_price_quote "
            "WHERE document_id=%s AND parser_version=%s ORDER BY source_locator",
            (DID, OLD),
        ).fetchall(), before_old)
        self.assertEqual(db.execute(
            "SELECT id,title,publisher,source_url,media_type,kind,reference_period,page_count,"
            "content,metadata,xmin::text FROM source_document WHERE id=%s", (DID,),
        ).fetchone(), before_source)
        self.assertEqual(db.execute(
            "SELECT processor_version,step,records,xmin::text FROM ingestion_checkpoint "
            "WHERE document_id=%s ORDER BY processor_version,step", (DID,),
        ).fetchall()[:3], before_checkpoints)


if __name__ == "__main__":
    unittest.main(verbosity=2)

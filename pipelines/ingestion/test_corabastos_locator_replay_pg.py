"""Six exact historical Corabastos originals through the actual worker path.

Requires a fresh owned full-schema database via AGRO_COR_LOCATOR_TEST_DSN.
Uses the disposable local publisher only; Blob, production, and providers are forbidden.
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

from . import (blob_archive, colombia_sources, corabastos_locator_replay as replay,
               corabastos_source_relocation as relocation, ocr,
               official_sources, queue_plan, worker, write_pacing)
from .resumable_inputs import WorkDeferred

FIXTURES = Path(__file__).parent / "testdata/corabastos_locator"
COLUMNS = ("document_id", "source_locator", "parser_version", "quote_key",
           "product_id", "product_name", "category", "publisher", "series",
           "basis", "currency", "unit", "market", "observed_on",
           "period_start", "price", "min_price", "max_price", "source_page",
           "details")
EXPECTED_MOVES = {
    "8748df4db724": 12, "5b16541ebf21": 18, "855beb303e4b": 14,
    "bb77b9ac465f": 14, "1cf46b5a7fc9": 12, "a6bd81f04321": 18,
}


def _source_cases():
    cases = []
    for path in sorted(FIXTURES.glob("prior-*.json")):
        case = json.loads(path.read_text())
        did = case["document_id"]
        source = FIXTURES / case["url"].rsplit("/", 1)[-1]
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != did:
            raise ValueError("Pinned Corabastos PDF fixture changed")
        if len(case["prior_quotes"]) != 350 or case["asset"]["document_id"] != did:
            raise ValueError("Historical 350-quote fixture changed")
        cases.append((case, source))
    if len(cases) != 6:
        raise ValueError("Six exact source fixtures required")
    return cases


def _public_business(db, did):
    rows = db.execute(
        "SELECT " + ",".join(COLUMNS) + " FROM published_official_price "
        "WHERE document_id=%s", (did,),
    ).fetchall()
    return {
        tuple(relocation._stored_full20(row)[field]
              for field in relocation.FIELDS)
        for row in rows
    }


def _forbid_http(*_args, **_kwargs):
    raise AssertionError("Exact retained replay attempted source HTTP")


class _NoCooldown:
    def __init__(self, *_args, **_kwargs):
        pass

    def blocked(self, _url):
        return None


@unittest.skipUnless(os.environ.get("AGRO_COR_LOCATOR_TEST_DSN"),
                     "Fresh owned full-schema Corabastos database required")
class CorabastosLocatorReplayPG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ["AGRO_COR_LOCATOR_TEST_DSN"]
        cls.db = psycopg.connect(cls.dsn, autocommit=True)
        db = cls.db
        if (not str(db.info.host).startswith("/tmp/agro-cor-reloc-")
                or not str(db.info.dbname).startswith("agro_cor_reloc_")
                or db.execute("SELECT inet_server_addr()").fetchone()[0] is not None):
            db.close()
            raise RuntimeError("Corabastos test requires an owned Unix-only DB")
        for table in ("source_document", "ingestion_asset", "official_price_quote",
                      "official_source_review", "ingestion_checkpoint"):
            if db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                db.close()
                raise RuntimeError("Corabastos full-schema database must begin empty")
        cls.cases = _source_cases()
        db.execute("SET statement_timeout='30s'")
        db.execute("SET lock_timeout='2s'")
        for case, source in cls.cases:
            did, url, asset = case["document_id"], case["url"], case["asset"]
            db.execute(
                "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
                "reference_period,content,metadata) VALUES(%s,%s,'Corabastos S.A.',%s,"
                "'application/pdf','original',%s,%s,%s)",
                (did, source.name, url, str(asset["observed_on"])[:7],
                 source.read_bytes(), Jsonb({"ingestion_kind": relocation.KIND,
                     "retention": "permanent", "original_filename": source.name})),
            )
            db.execute(
                "INSERT INTO ingestion_asset(url,kind,observed_on,status,document_id,"
                "processor_version) VALUES(%s,%s,%s,'failed',%s,%s)",
                (url, relocation.KIND, asset["observed_on"], did,
                 asset["processor_version"]),
            )
            with db.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO official_price_quote(" + ",".join(COLUMNS) + ") "
                    "VALUES (" + ",".join(["%s"] * len(COLUMNS)) + ")",
                    [tuple(did if name == "document_id" else
                           Jsonb(row[name]) if name == "details" else row[name]
                           for name in COLUMNS) for row in case["prior_quotes"]],
                )
        cls.prior_xmins = {
            did: dict(db.execute(
                "SELECT source_locator,xmin::text FROM official_price_quote "
                "WHERE document_id=%s AND parser_version='official-v2:colombia-prices-v2'",
                (did,),
            ).fetchall()) for did in (case["document_id"] for case, _ in cls.cases)
        }
        cls.source_xmins = dict(db.execute(
            "SELECT id,xmin::text FROM source_document WHERE id=ANY(%s)",
            ([case["document_id"] for case, _ in cls.cases],),
        ).fetchall())
        cls.prior_public = {
            case["document_id"]: _public_business(db, case["document_id"])
            for case, _ in cls.cases
        }
        if any(len(rows) != 350 for rows in cls.prior_public.values()):
            raise ValueError("Historical public 350-row business vector changed")
        # The disposable schema creates bare roles. Model only worker DML;
        # immutable original and archive-member UPDATE remains denied.
        db.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO agro_ingestor")
        db.execute("GRANT INSERT,UPDATE ON ingestion_run,ingestion_asset,"
                   "official_catalog_current TO agro_ingestor")
        db.execute("GRANT UPDATE ON source_ocr_task TO agro_ingestor")
        db.execute("GRANT INSERT ON source_document,official_price_quote,"
                   "official_source_review,ingestion_checkpoint TO agro_ingestor")
        for immutable in ("source_document", "source_archive_member"):
            if db.execute("SELECT has_table_privilege('agro_ingestor',%s,'UPDATE')",
                          (immutable,)).fetchone()[0]:
                raise ValueError("Local ingestor may rewrite immutable source")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_actual_worker_defer_reader_resume_all_six_and_queue(self):
        db = self.db
        version = worker.parser_version(relocation.KIND) + relocation.NEW_SUFFIX
        self.assertEqual(len(relocation.REVIEWED_ORIGINALS), 11)
        for case, _ in self.cases:
            self.assertEqual(worker.asset_parser_version(relocation.KIND, case["url"]), version)
        mapped = queue_plan.expected_versions().obj
        self.assertTrue(all(mapped["url:" + c["url"]] == version for c, _ in self.cases))
        due = {row[0] for row in queue_plan.backfill_candidates(db, 1000)}
        self.assertTrue({c["url"] for c, _ in self.cases} <= due)
        self.assertEqual(worker.asset_parser_version(
            relocation.KIND, "https://corabastos.com.co/unreviewed.pdf"),
            worker.parser_version(relocation.KIND))
        target = self.cases[0][0]

        def local_connect():
            conn = psycopg.connect(self.dsn, autocommit=True)
            conn.execute("SET ROLE agro_ingestor")
            return conn

        with patch.object(worker, "connect", side_effect=local_connect), \
             patch.object(worker, "HostCooldowns", _NoCooldown), \
             patch.object(worker, "fetch_asset", side_effect=_forbid_http), \
             patch.object(blob_archive, "retain_original_blob", return_value=None), \
             patch.object(ocr, "drain", return_value={"queued": 0}), \
             patch.object(write_pacing, "pause_between_batches",
                          side_effect=WorkDeferred("source batch pause")):
            deferred = worker.run(
                mode="backfill", limit=1, time_budget=120, ocr_limit=0,
                ocr_scan_limit=0, asset_url=target["url"],
            )
        self.assertEqual(len(deferred["deferred"]), 1)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s "
            "AND parser_version=%s", (target["document_id"], version),
        ).fetchone()[0], 256)
        self.assertEqual(db.execute(
            "SELECT status FROM ingestion_asset WHERE url=%s", (target["url"],)
        ).fetchone()[0], "failed")
        self.assertEqual(_public_business(db, target["document_id"]),
                         self.prior_public[target["document_id"]])
        with psycopg.connect(self.dsn, autocommit=True) as reader:
            reader.execute("SET ROLE agro_reader")
            self.assertEqual(_public_business(reader, target["document_id"]),
                             self.prior_public[target["document_id"]])

        with patch.object(worker, "connect", side_effect=local_connect), \
             patch.object(worker, "HostCooldowns", _NoCooldown), \
             patch.object(worker, "fetch_asset", side_effect=_forbid_http), \
             patch.object(blob_archive, "retain_original_blob", return_value=None), \
             patch.object(ocr, "drain", return_value={"queued": 0}), \
             patch.object(write_pacing, "pause_between_batches", return_value=None):
            resumed = worker.run(
                mode="backfill", limit=1, time_budget=120, ocr_limit=0,
                ocr_scan_limit=0, asset_url=target["url"],
            )
        self.assertEqual(resumed["assets"], 1)
        self.assertEqual(resumed["rows"], 350)
        db.execute("SET ROLE agro_ingestor")
        try:
            with patch.object(worker, "fetch_asset", side_effect=_forbid_http), \
                 patch.object(blob_archive, "retain_original_blob", return_value=None), \
                 patch.object(write_pacing, "pause_between_batches", return_value=None):
                for case, _ in self.cases[1:]:
                    self.assertEqual(worker.process_asset(
                        db, case["url"], relocation.KIND,
                        date.fromisoformat(case["asset"]["observed_on"])), 350)
        finally:
            db.execute("RESET ROLE")
        for case, _ in self.cases:
            did, url = case["document_id"], case["url"]
            prefix = did[:12]
            self.assertEqual(db.execute(
                "SELECT status,processor_version,records FROM ingestion_asset WHERE url=%s",
                (url,),
            ).fetchone(), ("complete", version, 350))
            self.assertEqual(db.execute(
                "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
                "AND processor_version=%s AND step='official:complete'", (did, version),
            ).fetchall(), [(350,)])
            self.assertEqual(db.execute(
                "SELECT count(*) FROM official_price_quote WHERE document_id=%s "
                "AND parser_version=%s", (did, version),
            ).fetchone()[0], 350)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM official_source_review WHERE document_id=%s "
                "AND parser_version=%s", (did, version),
            ).fetchone()[0], EXPECTED_MOVES[prefix])
            self.assertEqual(_public_business(db, did), self.prior_public[did])
            self.assertEqual(dict(db.execute(
                "SELECT source_locator,xmin::text FROM official_price_quote "
                "WHERE document_id=%s AND parser_version='official-v2:colombia-prices-v2'",
                (did,),
            ).fetchall()), self.prior_xmins[did])
        due_after = {row[0] for row in queue_plan.backfill_candidates(db, 1000)}
        self.assertFalse(due_after & {c["url"] for c, _ in self.cases})
        self.assertEqual(dict(db.execute(
            "SELECT id,xmin::text FROM source_document WHERE id=ANY(%s)",
            ([case["document_id"] for case, _ in self.cases],),
        ).fetchall()), self.source_xmins)
        before = {
            case["document_id"]: (
                db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s",
                           (case["document_id"],)).fetchone()[0],
                db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s",
                           (case["document_id"],)).fetchone()[0],
            ) for case, _ in self.cases
        }
        first, first_pdf = self.cases[0]
        other_pdf = self.cases[1][1]
        db.execute("SET ROLE agro_ingestor")
        try:
            with patch.object(worker, "fetch_asset", return_value=first_pdf.read_bytes()), \
                 patch.object(blob_archive, "retain_original_blob", return_value=None):
                worker.process_asset(
                    db, first["url"], relocation.KIND,
                    date.fromisoformat(first["asset"]["observed_on"]),
                )
            with self.assertRaises(ValueError):
                with db.transaction():
                    with patch.object(worker, "fetch_asset", return_value=other_pdf.read_bytes()), \
                         patch.object(blob_archive, "retain_original_blob", return_value=None):
                        worker.process_asset(
                            db, first["url"], relocation.KIND,
                            date.fromisoformat(first["asset"]["observed_on"]),
                        )
        finally:
            db.execute("RESET ROLE")
        for case, _ in self.cases:
            did = case["document_id"]
            self.assertEqual((
                db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s",
                           (did,)).fetchone()[0],
                db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s",
                           (did,)).fetchone()[0],
            ), before[did])
            self.assertEqual(_public_business(db, did), self.prior_public[did])


    def test_seventh_equivalent_source_cannot_retire_prior_locators(self):
        # The geometry/20-field resemblance of an unrelated PDF is not a
        # source adjudication. The ordinary publisher must still hold a
        # missing old locator; the six-source retirement path is inaccessible.
        db = self.db
        case, source = self.cases[0]
        url = case["url"].replace(".pdf", "-unreviewed.pdf")
        body = source.read_bytes() + b"\n% unrelated, unreviewed copy\n"
        did = hashlib.sha256(body).hexdigest()
        native = list(colombia_sources.parse(source.read_bytes(), case["url"],
                                              relocation.KIND))
        self.assertEqual(len(native), 350)
        base_version = worker.parser_version(relocation.KIND)
        self.assertNotIn(url, relocation.REVIEWED_ORIGINALS.values())
        self.assertNotIn(did, relocation.REVIEWED_ORIGINALS)
        with self.assertRaisesRegex(ValueError,
                                    "omitted previously published source locators"):
            with db.transaction():
                db.execute(
                    "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
                    "reference_period,content,metadata) VALUES(%s,%s,'Corabastos S.A.',%s,"
                    "'application/pdf','original',%s,%s,%s)",
                    (did, source.name, url, str(case["asset"]["observed_on"])[:7],
                     body, Jsonb({"ingestion_kind": relocation.KIND,
                                  "retention": "permanent"})),
                )
                db.execute(
                    "INSERT INTO ingestion_asset(url,kind,observed_on,status,document_id,"
                    "processor_version) VALUES(%s,%s,%s,'failed',%s,%s)",
                    (url, relocation.KIND, case["asset"]["observed_on"],
                     did, base_version),
                )
                with db.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO official_price_quote(" + ",".join(COLUMNS) + ") "
                        "VALUES (" + ",".join(["%s"] * len(COLUMNS)) + ")",
                        [tuple(did if name == "document_id" else
                               Jsonb(row[name]) if name == "details" else row[name]
                               for name in COLUMNS) for row in case["prior_quotes"]],
                    )
                self.assertIsNone(relocation.select_prior_for_relocation(
                    db, did, url, base_version, native))
                with self.assertRaisesRegex(ValueError, "Unreviewed Corabastos"):
                    relocation.prepare(db, did, url, base_version,
                                       base_version + relocation.NEW_SUFFIX,
                                       native, [], set())
                official_sources.publish_rows(
                    db, native, did, relocation.KIND, source_url=url)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM source_document WHERE id=%s", (did,),
        ).fetchone()[0], 0)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s", (did,),
        ).fetchone()[0], 0)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,),
        ).fetchone()[0], 0)
        for prior_case, _ in self.cases:
            old_did = prior_case["document_id"]
            self.assertEqual(dict(db.execute(
                "SELECT source_locator,xmin::text FROM official_price_quote "
                "WHERE document_id=%s AND parser_version='official-v2:colombia-prices-v2'",
                (old_did,),
            ).fetchall()), self.prior_xmins[old_did])

    def test_registered_url_changed_bytes_refused_before_retirement(self):
        case, _ = self.cases[0]
        changed_did = hashlib.sha256(b"different registered bytes").hexdigest()
        with self.assertRaisesRegex(ValueError, "Reviewed Corabastos original or URL changed"):
            relocation.select_prior_for_relocation(
                self.db, changed_did, case["url"],
                worker.parser_version(relocation.KIND), ())
        with self.assertRaisesRegex(ValueError, "Reviewed Corabastos original or URL changed"):
            relocation.select_prior_for_relocation(
                self.db, case["document_id"],
                case["url"].replace(".pdf", "-changed.pdf"),
                worker.parser_version(relocation.KIND), ())


if __name__ == "__main__":
    unittest.main()

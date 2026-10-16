"""Maintained regressions for the exact retained Sep 2013 DANE weekly PDF.

The PG case is opt-in and requires a dedicated root-reviewed owned fixture."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import unittest
from pathlib import Path
from datetime import date
from decimal import Decimal

import pdfplumber
import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb
from unittest.mock import patch

from pipelines.ingestion import dane_weekly as weekly
from pipelines.ingestion import official_sources, queue_plan, retained_pdf_upgrade, worker
from pipelines.ingestion.weekly_boundary_review import reviewed_article_bottom

REPO = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = Path(__file__).resolve().parent / "testdata/weekly_sep2013_page43"
PDF = FIXTURE_ROOT / "Semana23_sep_27sep_2013.pdf"
ORACLE = FIXTURE_ROOT / "page43_physical_oracle.json"
SOURCE_SHA = "ca2205284936795f03167c310ca401bb2beda72732c9db4d15a878134b378603"
ORACLE_SHA = "4fb15aa599e475bb44d53a700b0adf83816d436607114c7f09f8799fee3c4462"


class September2013MaintainedParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = PDF.read_bytes()
        cls.sha = hashlib.sha256(cls.body).hexdigest()
        if cls.sha != SOURCE_SHA or cls.sha != weekly.SEP2013_PAGE43_SHA:
            raise AssertionError("retained source bytes changed")
        if hashlib.sha256(ORACLE.read_bytes()).hexdigest() != ORACLE_SHA:
            raise AssertionError("independent physical page-43 oracle changed")
        with pdfplumber.open(io.BytesIO(cls.body)) as pdf:
            if len(pdf.pages) != 44:
                raise AssertionError(f"retained source page count changed: {len(pdf.pages)}")
            cls.page = pdf.pages[42]
            cls.words = cls.page.extract_words(extra_attrs=["fontname", "size"], return_chars=True)
            starts = sorted({w["top"] for w in cls.words
                             if w["text"] == "Cuadro" and w["x0"] < cls.page.width * .20})
            cls.top = starts[0]
            cls.table_text = cls.page.crop((0, cls.top - 1, cls.page.width, cls.page.height)).extract_text() or ""
            cls.columns = weekly._column_headers(cls.words, cls.page.width)

    def test_whole_source_and_full_page43_match_independent_physical_oracle(self):
        rows = weekly.parse(self.body, weekly.SEP2013_PAGE43_URL, "dane-weekly-pdf")
        self.assertEqual(len(rows), 4468)
        self.assertEqual((sum(r["price"] is not None for r in rows),
                          sum(r["price"] is None for r in rows)), (4336, 132))
        self.assertEqual({(r["period_start"], r["date"]) for r in rows},
                         {("2013-09-21", "2013-09-27")})
        page_rows = [r for r in rows if r["source_page"] == 43]
        oracle = json.loads(ORACLE.read_text())
        self.assertEqual((len(page_rows), oracle["price_rows"], oracle["money_cells"]), (56, 56, 168))
        for row, expected in zip(page_rows, oracle["rows"]):
            with self.subTest(locator=row["source_locator"]):
                self.assertEqual(row["market"], expected["market_literal"])
                self.assertEqual(row["product_name"], expected["product_literal"])
                self.assertEqual((row["min"], row["price"], row["max"]),
                                 (expected["minimum"], expected["mean"], expected["maximum"]))
        target = [r for r in page_rows if r["market"] == "Medellín, Central Mayorista de Antioquia"
                  and r["product_name"] == "Sardinas en lata"]
        self.assertEqual(len(target), 1)
        self.assertEqual((target[0]["min"], target[0]["price"], target[0]["max"]), (4527, 4527, 4527))
        vinegar = [r for r in page_rows if r["product_name"] == "Vinagre"]
        self.assertEqual(len(vinegar), 10)
        self.assertEqual({(r["unit"], r["price"] is not None) for r in vinegar}, {("kg", True)})

    def test_table_article_boundary_preserves_week_and_rejects_alias(self):
        cutoff = reviewed_article_bottom(weekly.SEP2013_PAGE43_URL, self.sha, 43,
                                         self.words, self.top - 1, self.page.height)
        body_text = self.page.crop((0, self.top - 1, self.page.width, cutoff)).extract_text() or ""
        self.assertIn("Tendencias:", body_text)
        self.assertNotIn("Precios de la panela", body_text)
        self.assertEqual(reviewed_article_bottom(weekly.SEP2013_PAGE43_URL + "?alias", self.sha,
                         43, self.words, self.top - 1, self.page.height), self.page.height)
        self.assertIsNone(weekly._sep2013_page43_table_period_override(
            weekly.SEP2013_PAGE43_URL, self.sha, 42, 1, self.table_text, self.words))
        self.assertIsNone(weekly._sep2013_page43_table_period_override(
            weekly.SEP2013_PAGE43_URL, self.sha, 43, 2, self.table_text, self.words))

    def test_period_override_fails_closed_on_source_caption_date_unit_or_article_change(self):
        fn = weekly._sep2013_page43_table_period_override
        with self.assertRaisesRegex(ValueError, "source bytes changed"):
            fn(weekly.SEP2013_PAGE43_URL, "0" * 64, 43, 1, self.table_text, self.words)
        self.assertIsNone(fn(weekly.SEP2013_PAGE43_URL + "?alias", self.sha, 43, 1,
                             self.table_text, self.words))
        cases = [
            (self.table_text.replace("Cuadro 8.", "Cuadro 9.", 1), self.words, "caption changed"),
            (self.table_text, [{**w, "text": "octubre)"} if w["text"] == "septiembre)" else w
                               for w in self.words], "table date header changed"),
            (self.table_text, [{**w, "text": "libra"} if w["text"] == "kilogramo" else w
                               for w in self.words], "kilogram headings changed"),
        ]
        for text, words, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ValueError, reason):
                    fn(weekly.SEP2013_PAGE43_URL, self.sha, 43, 1, text, words)
        words = [dict(w) for w in self.words if w["text"] != "Tendencias:"]
        with self.assertRaisesRegex(ValueError, "anchors changed"):
            fn(weekly.SEP2013_PAGE43_URL, self.sha, 43, 1, self.table_text, words)

    def _glyph_words(self):
        for i in range(len(self.words) - 1):
            if self.words[i]["text"] == "Antioquia4" and self.words[i + 1]["text"] == ".527":
                return [dict(w) for w in self.words[i - 4:i + 2]]
        self.fail("audited glyph sequence missing")

    def test_exact_native_glyph_partition_and_six_negative_partitions(self):
        glyphs = self._glyph_words()
        good = weekly._split_joined_price_words(glyphs, self.columns, sep2013_page43=True)
        self.assertEqual([w["text"] for w in good[-2:]], ["Antioquia", "4.527"])
        self.assertEqual(glyphs[-2]["text"], "Antioquia4")  # no input mutation
        negatives = []
        bad = [dict(w) for w in glyphs]; bad[-1] = {**bad[-1], "text": ".52x"}; negatives.append(("malformed numeric suffix", bad, self.columns))
        bad = [dict(w) for w in glyphs]; bad[-5] = {**bad[-5], "text": "Caldas"}; negatives.append(("wrong market prefix", bad, self.columns))
        bad = [dict(w) for w in glyphs]; bad[-1] = {**bad[-1], "top": bad[-1]["top"] + 1}; negatives.append(("different baseline", bad, self.columns))
        bad = [dict(w) for w in glyphs]; bad[-1] = {**bad[-1], "x0": bad[-1]["x0"] + 1}; negatives.append(("noncontiguous glyphs", bad, self.columns))
        shifted = [[dict(h) for h in col] for col in self.columns]; shifted[1][0] = {**shifted[1][0], "x0": 700, "x1": 720}; negatives.append(("wrong minimum header", glyphs, shifted))
        duplicated = glyphs + [dict(w) for w in glyphs[-6:]]; negatives.append(("ambiguous duplicate", duplicated, self.columns))
        for reason, words, columns in negatives:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ValueError, "ambiguous"):
                    weekly._split_joined_price_words(words, columns, sep2013_page43=True)
        unscoped = weekly._split_joined_price_words(glyphs, self.columns)
        self.assertNotIn("4.527", [w["text"] for w in unscoped])
        self.assertIn(".527", [w["text"] for w in unscoped])

    def test_worker_revision_and_priority_queue_pin_are_exact_source_only(self):
        url = weekly.SEP2013_PAGE43_URL
        expected = ("official-v2" + weekly.SEP2013_PAGE43_SUFFIX + ":dane-weekly-v24")
        for module in (weekly, official_sources, queue_plan, retained_pdf_upgrade, worker):
            module_path = Path(module.__file__).resolve()
            self.assertTrue(module_path.is_relative_to(REPO / "pipelines/ingestion"),
                            f"expected maintained ingestion module, got {module.__file__}")
        self.assertEqual(worker.parser_version("dane-weekly-pdf", url), expected)
        self.assertEqual(worker.asset_parser_version("dane-weekly-pdf", url), expected)
        self.assertNotEqual(worker.asset_parser_version("dane-weekly-pdf", url + "?alias"), expected)
        pinned = [row for row in queue_plan.PRIORITY_SOURCE_REPAIRS if row[0] == url]
        self.assertEqual(pinned, [(url, "dane-weekly-pdf", weekly.SEP2013_PAGE43_SHA)])
        self.assertEqual(queue_plan.expected_versions().obj["url:" + url], expected)

    def test_retained_original_source_binding_mismatch_fails_before_http_fallback(self):
        from .retained_pdf_upgrade import retained_sep2013_page43_original
        from datetime import date
        expected = worker.asset_parser_version("dane-weekly-pdf", weekly.SEP2013_PAGE43_URL)
        metadata = {"retention": "permanent", "ingestion_kind": "dane-weekly-pdf",
                    "original_filename": "Semana23_sep_27sep_2013.pdf"}
        asset = ("failed", weekly.SEP2013_PAGE43_SHA, None, "official-v2:dane-weekly-v24", 0,
                 "ValueError: Weekly PDF page 43 has conflicting printed periods")
        doc = (weekly.SEP2013_PAGE43_SHA, "DANE · SIPSA - Semana23_sep_27sep_2013.pdf",
               "DANE · SIPSA", weekly.SEP2013_PAGE43_URL, "application/pdf", "original",
               "Serie histórica completa", 44, self.body, metadata)
        class FakeDB:
            def __init__(self, document): self.document = document
            def execute(self, query, params):
                class Result:
                    def __init__(self, row): self.row = row
                    def fetchone(self): return self.row
                if "FROM ingestion_asset a JOIN source_document" in query:
                    return Result(asset + self.document)
                if "FROM ingestion_checkpoint" in query:
                    return Result(None)
                raise AssertionError("unexpected retained-source query")
        self.assertEqual(retained_sep2013_page43_original(
            FakeDB(doc), weekly.SEP2013_PAGE43_URL, "dane-weekly-pdf", expected, expected), self.body)
        for label, mutation in (
            ("title", {"title": "wrong title"}),
            ("source URL", {"source_url": weekly.SEP2013_PAGE43_URL + "?alias"}),
            ("media type", {"media_type": "application/octet-stream"}),
            ("page count", {"page_count": 43}),
            ("source bytes", {"content": self.body + b"x"}),
            ("metadata kind", {"metadata": {**metadata, "ingestion_kind": "other"}}),
        ):
            bad = list(doc)
            for key, value in mutation.items():
                bad[{"title": 1, "source_url": 3, "media_type": 4, "page_count": 7,
                     "content": 8, "metadata": 9}[key]] = value
            with self.subTest(binding=label), self.assertRaisesRegex(ValueError, "source binding changed"):
                retained_sep2013_page43_original(FakeDB(tuple(bad)), weekly.SEP2013_PAGE43_URL,
                                                  "dane-weekly-pdf", expected, expected)
        self.assertIsNone(retained_sep2013_page43_original(
            FakeDB(doc), weekly.SEP2013_PAGE43_URL + "?alias", "dane-weekly-pdf", expected, expected))
        for label, asset_change in (("wrong source DID", {"document_id": "0" * 64}),
                                    ("wrong parent date", {"observed_on": date(2013, 9, 26)})):
            bad_asset = list(asset)
            for key, value in asset_change.items():
                bad_asset[{"document_id": 1, "observed_on": 2}[key]] = value
            class BadAssetDB(FakeDB):
                def execute(self, query, params):
                    class Result:
                        def __init__(self, row): self.row = row
                        def fetchone(self): return self.row
                    if "FROM ingestion_asset a JOIN source_document" in query:
                        return Result(tuple(bad_asset) + doc)
                    if "FROM ingestion_checkpoint" in query:
                        return Result(None)
                    raise AssertionError("unexpected retained-source query")
            with self.subTest(binding=label), self.assertRaisesRegex(ValueError, "source binding changed"):
                retained_sep2013_page43_original(BadAssetDB(doc), weekly.SEP2013_PAGE43_URL,
                                                  "dane-weekly-pdf", expected, expected)

    def test_verified_complete_checkpoint_returns_retained_body_and_rejects_wrong_count(self):
        from .retained_pdf_upgrade import retained_sep2013_page43_original
        exact = worker.asset_parser_version("dane-weekly-pdf", weekly.SEP2013_PAGE43_URL)
        metadata = {"retention": "permanent", "ingestion_kind": "dane-weekly-pdf",
                    "original_filename": "Semana23_sep_27sep_2013.pdf"}
        asset = ("failed", weekly.SEP2013_PAGE43_SHA, None, "official-v2:dane-weekly-v24", 0,
                 "ValueError: Weekly PDF page 43 has conflicting printed periods")
        doc = (weekly.SEP2013_PAGE43_SHA, "DANE · SIPSA - Semana23_sep_27sep_2013.pdf",
               "DANE · SIPSA", weekly.SEP2013_PAGE43_URL, "application/pdf", "original",
               "Serie histórica completa", 44, self.body, metadata)
        class CheckpointDB:
            def __init__(self, records): self.records = records
            def execute(self, query, params):
                class Result:
                    def __init__(self, row): self.row = row
                    def fetchone(self): return self.row
                if "FROM ingestion_asset a JOIN source_document" in query:
                    return Result(asset + doc)
                if "FROM ingestion_checkpoint" in query:
                    self.query_params = params
                    return Result(None if self.records is None else (self.records,))
                raise AssertionError("unexpected retained-source query")
        good = CheckpointDB(4336)
        self.assertEqual(retained_sep2013_page43_original(good, weekly.SEP2013_PAGE43_URL,
                         "dane-weekly-pdf", exact, exact), self.body)
        self.assertEqual(good.query_params, (weekly.SEP2013_PAGE43_SHA, exact))
        bad = CheckpointDB(4335)
        with self.assertRaisesRegex(ValueError, "complete checkpoint has an unexpected record count"):
            retained_sep2013_page43_original(bad, weekly.SEP2013_PAGE43_URL,
                                             "dane-weekly-pdf", exact, exact)

    def test_unit_exception_is_only_enabled_by_exact_scoped_callsite(self):
        text = self.table_text
        self.assertEqual(text.count("Pesos por kilogramo"), 2)
        self.assertIsNone(weekly._unit("vinagre", weekly._exceptions("Vinagre")))
        parsed = weekly.parse(self.body, weekly.SEP2013_PAGE43_URL, "dane-weekly-pdf")
        vinegar = [r for r in parsed if r.get("source_page") == 43 and r["product_name"] == "Vinagre"]
        self.assertTrue(all(r["unit"] == "kg" and r["price"] is not None for r in vinegar))
        self.assertIsNone(weekly._unit("vinagre", weekly._exceptions("Vinagre; pesos por litro")))


def _owned_sep2013_dsn_values(dsn):
    """Validate a task-owned Unix socket DSN before opening any connection."""
    try:
        values = conninfo_to_dict(dsn)
    except Exception as exc:
        raise RuntimeError("Invalid Sep 2013 maintained-test DSN") from exc
    if any(key in values for key in ("service", "servicefile", "hostaddr")):
        raise RuntimeError("Service and TCP address DSNs are forbidden")
    host = values.get("host", "")
    if not re.fullmatch(r"/tmp/agro-sep2013-worker-[A-Za-z0-9_-]+/socket", host):
        raise RuntimeError("Only one canonical task-owned Sep 2013 Unix socket is allowed")
    if values.get("user") != "postgres" or values.get("dbname") != "postgres":
        raise RuntimeError("Sep 2013 test requires the owned postgres role/database")
    port = values.get("port", "")
    if not port.isdigit() or not 1024 <= int(port) <= 65535:
        raise RuntimeError("Sep 2013 test requires an explicit valid local port")
    return values


class September2013OwnedDSNGuard(unittest.TestCase):
    def test_unowned_dsns_are_rejected_before_connect(self):
        invalid = (
            "postgresql://postgres@db.example.com/postgres",
            "host=/tmp/agro-sep2013-worker-safe/socket port=5432 user=postgres dbname=postgres service=prod",
            "host=/tmp/agro-sep2013-worker-safe/socket port=5432 user=postgres dbname=postgres hostaddr=127.0.0.1",
            "host=/tmp/agro-sep2013-worker-safe/socket port=5432 user=app dbname=postgres",
            "host=/tmp/agro-sep2013-worker-safe/socket user=postgres dbname=postgres",
        )
        with patch.object(psycopg, "connect") as connect:
            for dsn in invalid:
                with self.subTest(dsn=dsn), self.assertRaises(RuntimeError):
                    _owned_sep2013_dsn_values(dsn)
            connect.assert_not_called()


@unittest.skipUnless(os.environ.get("AGRO_SEP2013_PRIVATE_WORKER_PG_DSN"),
                     "Explicit root GO and owned Sep 2013 full-schema PostgreSQL DSN required")
class September2013MaintainedWorkerPGTests(unittest.TestCase):
    """Calls the real process_asset/publisher against a disposable owned PG only."""
    @classmethod
    def setUpClass(cls):
        cls.url = weekly.SEP2013_PAGE43_URL
        cls.kind = "dane-weekly-pdf"
        cls.did = weekly.SEP2013_PAGE43_SHA
        cls.day = None  # Exact queue identity keeps asset observed_on unset.
        cls.body = PDF.read_bytes()
        dsn = os.environ["AGRO_SEP2013_PRIVATE_WORKER_PG_DSN"]
        expected_dsn = _owned_sep2013_dsn_values(dsn)  # Must precede connect.
        cls.db = psycopg.connect(dsn, autocommit=True)
        if (str(cls.db.info.host) != expected_dsn["host"]
                or cls.db.info.dbname != "postgres"
                or cls.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None
                or not str(cls.db.execute("SHOW server_version").fetchone()[0]).startswith("16.")):
            cls.db.close()
            raise RuntimeError("Only a specifically owned local Sep 2013 fixture is allowed")
        cls.db.execute("SET statement_timeout='180s'")
        from pipelines.ingestion.test_input_pdf_v17_role import install
        install(cls.db)
        # Test-only grants reproduce the exact reader surface needed for this
        # qualification. They exist only in the owned disposable PostgreSQL.
        cls.db.execute("REVOKE ALL ON source_document,official_price_quote,official_source_review,ingestion_checkpoint FROM agro_reader")
        cls.db.execute("GRANT SELECT ON source_document,official_price_quote,official_source_review,ingestion_checkpoint TO agro_reader")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_real_queue_null_date_worker_publication_replay_and_append_only_baseline(self):
        db, url, kind, did, day, body = self.db, self.url, self.kind, self.did, self.day, self.body
        rows = weekly.parse(body, url, kind)
        self.assertEqual(hashlib.sha256(body).hexdigest(), did)
        self.assertEqual(db.execute("SELECT count(*) FROM source_document WHERE id=%s", (did,)).fetchone()[0], 0)
        metadata = {"retention": "permanent", "ingestion_kind": kind,
                    "original_filename": "Semana23_sep_27sep_2013.pdf"}
        db.execute(
            "INSERT INTO source_document (id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata) "
            "VALUES(%s,%s,%s,%s,'application/pdf','original','Serie histórica completa',44,%s,%s)",
            (did, "DANE · SIPSA - Semana23_sep_27sep_2013.pdf", "DANE · SIPSA", url, body, Jsonb(metadata)))
        base = worker.parser_version(kind)
        revision = worker.asset_parser_version(kind, url)
        self.assertEqual(revision, "official-v2" + weekly.SEP2013_PAGE43_SUFFIX + ":dane-weekly-v24")
        self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)).fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s", (did,)).fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s", (did,)).fetchone()[0], 0)
        for table in ("official_price_quote", "official_source_review", "source_document"):
            for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
                self.assertFalse(db.execute("SELECT has_table_privilege('agro_ingestor',%s,%s)",
                                            ("public." + table, privilege)).fetchone()[0],
                                 f"agro_ingestor unexpectedly has {privilege} on {table}")
        self.assertTrue(db.execute("SELECT has_table_privilege('agro_ingestor','public.official_price_quote','INSERT')").fetchone()[0])
        reader_tables = ("source_document", "official_price_quote", "official_source_review", "ingestion_checkpoint")
        for table in reader_tables:
            self.assertTrue(db.execute("SELECT has_table_privilege('agro_reader',%s,'SELECT')", ("public." + table,)).fetchone()[0])
            for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                self.assertFalse(db.execute("SELECT has_table_privilege('agro_reader',%s,%s)",
                                            ("public." + table, privilege)).fetchone()[0],
                                 f"agro_reader unexpectedly has {privilege} on {table}")
        db.execute("SET ROLE agro_reader")
        try:
            self.assertEqual(db.execute("SELECT count(*) FROM source_document WHERE id=%s", (did,)).fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s", (did,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s", (did,)).fetchone()[0], 0)
        finally:
            db.execute("RESET ROLE")
        poisoned_on = date(2013, 9, 28)
        failed_error = "ValueError: Weekly PDF page 43 has conflicting printed periods"
        db.execute(
            "INSERT INTO ingestion_asset (url,kind,document_id,observed_on,status,processor_version,records,error,checked_at) "
            "VALUES(%s,%s,%s,%s,'failed',%s,0,%s,now()-interval '7 hours')",
            (url, kind, did, poisoned_on, base, failed_error))
        def source_snapshot():
            return db.execute("SELECT id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata,xmin::text FROM source_document WHERE id=%s", (did,)).fetchone()
        source_original = source_snapshot()
        asset_poisoned = db.execute("SELECT status,document_id,observed_on,processor_version,records,error,xmin::text FROM ingestion_asset WHERE url=%s AND kind=%s", (url, kind)).fetchone()
        def publisher_with_bad_url():
            db.execute("SET ROLE agro_ingestor")
            try:
                return official_sources.publish_rows(db, rows, did, kind, source_url=url + "?alias")
            finally:
                db.execute("RESET ROLE")
        with self.assertRaisesRegex(ValueError, "Exact September 2013 page-43 source original changed"):
            publisher_with_bad_url()
        self.assertEqual(source_snapshot(), source_original)
        self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)).fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s", (did,)).fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s", (did,)).fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT status,document_id,observed_on,processor_version,records,error,xmin::text FROM ingestion_asset WHERE url=%s AND kind=%s", (url, kind)).fetchone(), asset_poisoned)
        fetch_calls = []
        def no_fetch(_db, fetch_url, force=False, *, require_bytes=False):
            fetch_calls.append(fetch_url)
            raise AssertionError("Pinned retained source must not make an HTTP request")
        from . import blob_archive
        def no_cloud_blob(digest, data, suffix, media_type):
            self.assertEqual((digest, data, suffix, media_type), (did, body, ".pdf", "application/pdf"))
        def as_ingestor():
            self.assertIsNone(day, "worker dispatch must preserve queued NULL observed_on")
            db.execute("SET ROLE agro_ingestor")
            try:
                return worker.process_asset(db, url, kind, day)
            finally:
                db.execute("RESET ROLE")
        with patch.object(worker, "fetch_asset", side_effect=no_fetch), \
                patch.object(blob_archive, "retain_original_blob", side_effect=no_cloud_blob):
            with self.assertRaisesRegex(ValueError, "source binding changed"):
                as_ingestor()
        self.assertEqual(fetch_calls, [])
        self.assertEqual(source_snapshot(), source_original)
        self.assertEqual(db.execute("SELECT status,document_id,observed_on,processor_version,records,error,xmin::text FROM ingestion_asset WHERE url=%s AND kind=%s", (url, kind)).fetchone(), asset_poisoned)
        self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s", (did,)).fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s", (did,)).fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s", (did,)).fetchone()[0], 0)
        db.execute("UPDATE ingestion_asset SET observed_on=NULL WHERE url=%s AND kind=%s", (url, kind))
        self.assertTrue(worker.retained_reparse_during_host_cooldown(db, url, kind))
        self.assertIn((url, kind, None), queue_plan.backfill_candidates(db, 1000))
        source_original = source_snapshot()
        quote_columns = ("document_id,source_locator,parser_version,quote_key,product_id,product_name,category,publisher,"
                         "series,basis,currency,unit,market,observed_on,period_start,price,min_price,max_price,source_page,details")
        def quote_projection(row):
            identity = {key: row[key] for key in ("product_id", "series", "market", "currency", "unit", "basis")}
            identity["dimensions"] = row.get("identity_dimensions", {})
            quote_key = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            details = {**row.get("details", {}), "identity_dimensions": identity["dimensions"]}
            as_day = lambda value: date.fromisoformat(value) if isinstance(value, str) else value
            return (did, row["source_locator"], revision, quote_key, row["product_id"], row["product_name"],
                    row["category"], row["publisher"], row["series"], row["basis"], row["currency"],
                    row["unit"], row["market"], as_day(row["date"]), as_day(row.get("period_start")),
                    Decimal(str(float(row["price"]))),
                    None if row.get("min") is None else Decimal(str(float(row["min"]))),
                    None if row.get("max") is None else Decimal(str(float(row["max"]))),
                    row.get("source_page") or row.get("details", {}).get("source_page"), details)
        expected_quotes = sorted((quote_projection(r) for r in rows if not r.get("details", {}).get("quality_issue") and r.get("price") is not None), key=lambda x: x[1])
        expected_reviews = sorted(((did, r["source_locator"], revision,
                                    json.loads(json.dumps(r, ensure_ascii=False, default=str)),
                                    r.get("details", {}).get("quality_issue") or "No unambiguous positive price")
                                   for r in rows if r.get("details", {}).get("quality_issue") or r.get("price") is None), key=lambda x: x[1])
        def quote_state():
            return db.execute(f"SELECT {quote_columns},xmin::text FROM official_price_quote WHERE document_id=%s AND parser_version=%s ORDER BY source_locator", (did, revision)).fetchall()
        def review_state():
            return db.execute("SELECT document_id,source_locator,parser_version,record,reason,xmin::text FROM official_source_review WHERE document_id=%s AND parser_version=%s ORDER BY source_locator", (did, revision)).fetchall()
        def checkpoint_state():
            return db.execute("SELECT document_id,processor_version,step,records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='official:complete'", (did, revision)).fetchall()
        first_state = None
        with patch.object(worker, "fetch_asset", side_effect=no_fetch), \
                patch.object(blob_archive, "retain_original_blob", side_effect=no_cloud_blob):
            for replay in (False, True):
                if replay:
                    db.execute("UPDATE ingestion_asset SET status='failed',observed_on=NULL,processor_version=%s,records=0,error=%s,checked_at=now()-interval '7 hours' WHERE url=%s",
                                (base, failed_error, url))
                    self.assertIn((url, kind, None), queue_plan.backfill_candidates(db, 1000))
                self.assertEqual(as_ingestor(), 4336)
                asset_after = db.execute("SELECT observed_on FROM ingestion_asset WHERE url=%s AND kind=%s", (url, kind)).fetchone()[0]
                self.assertEqual(asset_after, date(2013, 9, 27))
                self.assertEqual(source_snapshot(), source_original)
                qrows = quote_state()
                self.assertEqual([row[:-1] for row in qrows], expected_quotes)
                self.assertEqual(len(qrows), 4336)
                rrows = review_state()
                self.assertEqual([row[:-1] for row in rrows], expected_reviews)
                self.assertEqual(len(rrows), 132)
                checkpoints = checkpoint_state()
                self.assertEqual(len(checkpoints), 1)
                self.assertEqual(checkpoints[0][1:4], (revision, "official:complete", 4336))
                state = (qrows, rrows, checkpoints)
                if first_state is None:
                    first_state = state
                else:
                    self.assertEqual(state, first_state)
        self.assertEqual(fetch_calls, [])



if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Actual disposable PostgreSQL checks for OCR attempt/outcome persistence.

All runtime rows live in TEMP tables on a local Unix socket. Provider calls
are mocked, and the exact migration is parsed in a rolled-back scratch schema.
"""

from datetime import datetime
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
import psycopg

from . import ocr
from .ocr_finish_policy import OUTCOME_CODES


DSN = os.environ.get("AGRO_REFERENCE_TEST_DSN", "")
SOCKET_PREFIXES = ("/tmp/agro-", "/private/tmp/agro-")
MIGRATION = Path(__file__).resolve().parent / "migrations/20261007_069_ocr_finish_outcomes.sql"


def private_connection():
    if not any(f"host={prefix}" in DSN for prefix in SOCKET_PREFIXES):
        raise RuntimeError("OCR finish tests require an explicit private Unix PostgreSQL socket")
    db = psycopg.connect(DSN, connect_timeout=3, autocommit=True,
                         options="-c statement_timeout=3000 -c timezone=UTC")
    if db.execute("SELECT inet_server_addr() IS NULL").fetchone() != (True,):
        db.close()
        raise RuntimeError("OCR finish test socket resolved to a network server")
    return db


def image():
    stream = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(stream, format="PNG")
    return stream.getvalue()


class OCRFinishPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = private_connection()
        cls.db.execute("""CREATE TEMP TABLE source_ocr_task(
          document_id text,source_locator text,image_id text,source_kind text,
          source_page integer,status text DEFAULT 'pending',created_at timestamptz DEFAULT now(),
          checked_at timestamptz,error text,PRIMARY KEY(document_id,source_locator))""")
        cls.db.execute("""CREATE TEMP TABLE source_ocr_attempt(
          id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,image_id text,
          started_at timestamptz DEFAULT now(),version text,reading smallint)""")
        cls.db.execute("""CREATE TEMP TABLE source_ocr_attempt_outcome(
          attempt_id bigint PRIMARY KEY REFERENCES source_ocr_attempt(id),outcome_code text,
          recorded_at timestamptz DEFAULT now())""")
        cls.db.execute("""CREATE TEMP TABLE source_ocr_result(
          image_id text,version text,reading integer,result jsonb,
          PRIMARY KEY(image_id,version,reading))""")
        cls.db.execute("CREATE TEMP TABLE source_document(id text PRIMARY KEY,content bytea,media_type text,metadata jsonb,retrieved_at timestamptz DEFAULT now())")
        cls.db.execute("CREATE TEMP TABLE source_ocr_scan(document_id text,version text)")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.db.execute("TRUNCATE source_ocr_attempt_outcome,source_ocr_task,source_ocr_attempt,source_ocr_result,source_document,source_ocr_scan")
        self.db.execute("INSERT INTO source_document(id,content,media_type,metadata) VALUES('image',%s,'image/png','{}'::jsonb)", (image(),))
        self.db.execute("INSERT INTO source_ocr_task(document_id,source_locator,image_id,source_kind,source_page) VALUES('doc','PDF page 1','image','city-pdf',1)")

    def seed_attempt(self, code, *, reading=1, days_ago=0):
        aid = self.db.execute(
            """INSERT INTO source_ocr_attempt(image_id,version,reading,started_at)
            VALUES('image',%s,%s,now()-(%s*interval '1 day')) RETURNING id""",
            (ocr.VERSION, reading, days_ago),
        ).fetchone()[0]
        if code is not None:
            self.db.execute("INSERT INTO source_ocr_attempt_outcome(attempt_id,outcome_code) VALUES(%s,%s)", (aid, code))
        return aid

    def cache_first(self):
        self.db.execute("INSERT INTO source_ocr_result(image_id,version,reading,result) VALUES('image',%s,0,'{\"text\":\"retained\",\"tables\":[],\"review_notes\":[]}'::jsonb)", (ocr.VERSION,))

    def run_drain(self, provider, *, daily_cap="40", db=None, comparator=False, limit=1):
        from . import monthly_pdf_recovery
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "mock-only", "GEMINI_OCR_DAILY_REQUESTS": daily_cap}),
            patch.object(ocr, "retire_audited_decorative_pdf_pages", return_value=0),
            patch.object(ocr, "requeue_cached_typed_reviews", return_value={"checked": 0}),
            patch.object(ocr, "retire_native_daily_tasks", return_value={"checked": 0}),
            patch.object(monthly_pdf_recovery, "retire_tasks", return_value={"checked": 0}),
            patch.object(ocr, "compare_typed_task_readings", return_value=comparator),
            patch.object(ocr, "_finalize_milk_task", return_value=None),
            patch.object(ocr, "transcribe", side_effect=provider),
        ):
            return ocr.drain(db or self.db, limit=limit, scan_limit=0)

    def test_first_max_tokens_preserves_cached_first_and_defers_without_partial_output(self):
        self.cache_first()
        calls = []
        def provider(*_args, **_kwargs):
            calls.append(1)
            raise ocr.OCRProviderOutcome("MAX_TOKENS")
        result = self.run_drain(provider)
        self.assertEqual((result["deferred"], len(calls)), (1, 1))
        self.assertEqual(self.db.execute("SELECT status,error FROM source_ocr_task").fetchone(),
                         ("deferred", "provider_finish=MAX_TOKENS:retry_after_24h"))
        self.assertEqual(self.db.execute("SELECT reading,outcome_code FROM source_ocr_attempt a JOIN source_ocr_attempt_outcome o ON o.attempt_id=a.id").fetchall(), [(1, "MAX_TOKENS")])
        self.assertEqual(self.db.execute("SELECT reading FROM source_ocr_result").fetchall(), [(0,)])

    def test_first_output_limit_defers_only_that_page_and_processes_cached_neighbor(self):
        self.cache_first()
        self.db.execute("INSERT INTO source_document(id,content,media_type,metadata) VALUES('image2',%s,'image/png','{}'::jsonb)", (image(),))
        self.db.execute("INSERT INTO source_ocr_task(document_id,source_locator,image_id,source_kind,source_page) VALUES('doc2','PDF page 1','image2','city-pdf',1)")
        for reading in (0, 1):
            self.db.execute("INSERT INTO source_ocr_result(image_id,version,reading,result) VALUES('image2',%s,%s,'{\"text\":\"cached\",\"tables\":[],\"review_notes\":[]}'::jsonb)", (ocr.VERSION, reading))
        calls = []
        def provider(*_args, **_kwargs):
            calls.append(1)
            raise ocr.OCRProviderOutcome("MAX_TOKENS")
        result = self.run_drain(provider, limit=2)
        self.assertEqual((result["deferred"], result["processed"], result["review"], len(calls)), (1, 1, 1, 1))
        self.assertEqual(self.db.execute("SELECT document_id,status FROM source_ocr_task ORDER BY document_id").fetchall(),
                         [("doc", "deferred"), ("doc2", "review")])
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_attempt").fetchone(), (1,))
        self.assertEqual(self.db.execute("SELECT outcome_code FROM source_ocr_attempt_outcome").fetchone(), ("MAX_TOKENS",))

    def test_cooldown_then_one_retry_across_day_reset(self):
        self.cache_first()
        self.seed_attempt("MAX_TOKENS", days_ago=2)
        self.db.execute("UPDATE source_ocr_task SET status='deferred',checked_at=now()-interval '25 hours',error='provider_finish=MAX_TOKENS:retry_after_24h'")
        calls = []
        def provider(*_args, **_kwargs):
            calls.append(1)
            raise ocr.OCRProviderOutcome("MAX_TOKENS")
        result = self.run_drain(provider)
        self.assertEqual((result["review"], len(calls)), (1, 1))
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_attempt_outcome WHERE outcome_code='MAX_TOKENS'").fetchone(), (2,))
        self.db.execute("UPDATE source_ocr_task SET status='pending',checked_at=NULL")
        result = self.run_drain(provider)
        self.assertEqual((result["review"], len(calls)), (1, 1))
        self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task").fetchone(), ("review",))

    def test_cooldown_does_not_spend_quota_and_zero_quota_never_calls_provider(self):
        self.cache_first()
        self.seed_attempt("MAX_TOKENS")
        calls = []
        self.run_drain(lambda *_a, **_k: calls.append(1))
        self.assertEqual(calls, [])
        self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task").fetchone(), ("deferred",))
        self.db.execute("UPDATE source_ocr_task SET checked_at=now()-interval '25 hours'")
        self.run_drain(lambda *_a, **_k: calls.append(1), daily_cap="0")
        self.assertEqual(calls, [])

    def test_cooling_task_does_not_occupy_bounded_city_selection(self):
        self.cache_first()
        self.seed_attempt("MAX_TOKENS")
        self.db.execute("UPDATE source_ocr_task SET status='deferred',checked_at=now()-interval '7 hours',error='provider_finish=MAX_TOKENS:retry_after_24h'")
        self.db.execute("INSERT INTO source_document(id,content,media_type,metadata) VALUES('image2',%s,'image/png','{}'::jsonb)", (image(),))
        self.db.execute("INSERT INTO source_ocr_task(document_id,source_locator,image_id,source_kind,source_page) VALUES('doc2','PDF page 1','image2','city-pdf',1)")
        scheduled = ocr._priority_snapshot(self.db, 40, None, 2)[-1]
        self.assertEqual([row[0] for row in scheduled], ["doc2"])

    def test_max_retry_spent_by_http_429(self):
        self.cache_first()
        self.seed_attempt("MAX_TOKENS", days_ago=2)
        self.db.execute("UPDATE source_ocr_task SET status='deferred',checked_at=now()-interval '25 hours'")
        def provider(*_args, **_kwargs):
            raise ocr.OCRDeferred("Gemini OCR HTTP 429", outcome_code="HTTP_429")
        result = self.run_drain(provider)
        self.assertEqual(result["review"], 1)
        self.assertEqual(self.db.execute("SELECT outcome_code FROM source_ocr_attempt_outcome ORDER BY attempt_id").fetchall(), [("MAX_TOKENS",), ("HTTP_429",)])
        self.db.execute("UPDATE source_ocr_task SET status='pending',checked_at=NULL")
        result = self.run_drain(lambda *_a, **_k: self.fail("retry must not call provider"))
        self.assertEqual(result["review"], 1)

    def test_fresh_http_429_defers_and_retains_sanitized_attempt(self):
        self.cache_first()
        def provider(*_args, **_kwargs):
            raise ocr.OCRDeferred("Gemini OCR HTTP 429", outcome_code="HTTP_429")
        result = self.run_drain(provider)
        self.assertEqual(result["deferred"], 1)
        self.assertEqual(self.db.execute("SELECT outcome_code FROM source_ocr_attempt_outcome").fetchone(), ("HTTP_429",))
        self.assertEqual(self.db.execute("SELECT reading FROM source_ocr_result").fetchall(), [(0,)])

    def test_safety_recitation_and_unknown_finish_are_terminal_review(self):
        for code in ("SAFETY", "RECITATION", "OTHER_FINISH"):
            with self.subTest(code=code):
                self.db.execute("TRUNCATE source_ocr_attempt_outcome,source_ocr_attempt,source_ocr_result")
                self.cache_first()
                self.db.execute("UPDATE source_ocr_task SET status='pending',checked_at=NULL,error=NULL")
                def provider(*_args, **_kwargs):
                    raise ocr.OCRProviderOutcome(code)
                result = self.run_drain(provider)
                self.assertEqual(result["review"], 1)
                self.assertEqual(self.db.execute("SELECT outcome_code FROM source_ocr_attempt_outcome").fetchone(), (code,))
                self.assertEqual(self.db.execute("SELECT reading FROM source_ocr_result").fetchall(), [(0,)])

    def test_outcome_storage_failure_leaves_unclassified_attempt_and_blocks_retry(self):
        self.cache_first()
        original_record = ocr._record_finish
        def broken(*_args, **_kwargs):
            raise RuntimeError("private fixture outcome storage failure")
        with patch.object(ocr, "_record_finish", side_effect=broken):
            with self.assertRaises(RuntimeError):
                self.run_drain(lambda *_a, **_k: (_ for _ in ()).throw(ocr.OCRProviderOutcome("MAX_TOKENS")))
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_attempt").fetchone(), (1,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_attempt_outcome").fetchone(), (0,))
        result = self.run_drain(lambda *_a, **_k: self.fail("unclassified retry must not call provider"))
        self.assertEqual(result["review"], 1)

    def test_stop_without_cached_result_never_retries(self):
        self.cache_first()
        self.seed_attempt("STOP_VALID")
        result = self.run_drain(lambda *_a, **_k: self.fail("STOP result loss must not call provider"))
        self.assertEqual(result["review"], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_result").fetchone(), (1,))

    def test_terminal_outcome_persisted_before_status_update_blocks_crash_replay(self):
        for code, task_status in (("SAFETY", "pending"), ("STOP_BAD_SCHEMA", "deferred")):
            with self.subTest(code=code):
                self.db.execute("TRUNCATE source_ocr_attempt_outcome,source_ocr_attempt,source_ocr_result")
                self.cache_first()
                self.seed_attempt(code)
                self.db.execute(
                    "UPDATE source_ocr_task SET status=%s,checked_at=NULL,error=NULL",
                    (task_status,),
                )
                result = self.run_drain(lambda *_a, **_k: self.fail("terminal finish must not make another provider request"))
                self.assertEqual(result["review"], 1)
                self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task").fetchone(), ("review",))
                self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_attempt").fetchone(), (1,))

    def test_stop_result_storage_failure_is_fail_closed_on_next_run(self):
        self.cache_first()
        class FailResultInsert:
            def __init__(self, db):
                self.db = db
            def execute(self, sql, params=()):
                if sql.startswith("INSERT INTO source_ocr_result"):
                    raise RuntimeError("private fixture result storage failure")
                return self.db.execute(sql, params)
        result = {"text": "complete", "tables": [], "review_notes": []}
        with self.assertRaises(RuntimeError):
            self.run_drain(lambda *_a, **_k: result, db=FailResultInsert(self.db))
        self.assertEqual(self.db.execute("SELECT outcome_code FROM source_ocr_attempt_outcome").fetchone(), ("STOP_VALID",))
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_result").fetchone(), (1,))
        replay = self.run_drain(lambda *_a, **_k: self.fail("lost STOP result must not be reread"))
        self.assertEqual(replay["review"], 1)

    def test_invalid_stop_schema_never_records_valid_stop_or_second_result(self):
        self.cache_first()
        result = self.run_drain(lambda *_a, **_k: {"text": "x", "tables": [[[42]]], "review_notes": []})
        self.assertEqual(result["review"], 1)
        self.assertEqual(self.db.execute("SELECT outcome_code FROM source_ocr_attempt_outcome").fetchone(), ("STOP_BAD_SCHEMA",))
        self.assertEqual(self.db.execute("SELECT reading FROM source_ocr_result").fetchall(), [(0,)])

    def test_completed_second_reading_still_needs_typed_agreement(self):
        self.cache_first()
        valid = {"text": "complete", "tables": [], "review_notes": []}
        result = self.run_drain(lambda *_a, **_k: valid, comparator=False)
        self.assertEqual(result["review"], 1)
        self.assertEqual(self.db.execute("SELECT reading FROM source_ocr_result ORDER BY reading").fetchall(), [(0,), (1,)])
        self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task").fetchone(), ("review",))

    def test_old_schema_capability_keeps_terminal_max_tokens_behavior(self):
        self.cache_first()
        with patch.object(ocr, "_finish_policy_available", return_value=False):
            result = self.run_drain(lambda *_a, **_k: (_ for _ in ()).throw(ocr.OCRProviderOutcome("MAX_TOKENS")))
        self.assertEqual(result["review"], 1)
        self.assertEqual(self.db.execute("SELECT version,reading FROM source_ocr_attempt").fetchone(), (None, None))
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_attempt_outcome").fetchone(), (0,))


class OCRFinishMigrationPostgres(unittest.TestCase):
    def test_exact_migration_is_append_only_and_rejects_unsanitized_outcomes(self):
        db = private_connection()
        try:
            db.autocommit = False
            db.execute("CREATE SCHEMA ocr_finish_migration_fixture")
            db.execute("SET LOCAL search_path TO ocr_finish_migration_fixture,public")
            db.execute("CREATE TABLE source_document(id text PRIMARY KEY)")
            db.execute("CREATE TABLE source_ocr_attempt(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,image_id text REFERENCES source_document(id),started_at timestamptz DEFAULT now())")
            db.execute("CREATE FUNCTION prevent_history_removal() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable'; END $$")
            db.execute("INSERT INTO source_document(id) VALUES('image')")
            db.execute("INSERT INTO source_ocr_attempt(image_id) VALUES('image')")
            db.execute(MIGRATION.read_text())
            self.assertEqual(db.execute("SELECT version,reading FROM source_ocr_attempt WHERE image_id='image'").fetchone(), (None, None))
            db.execute("INSERT INTO source_ocr_attempt(image_id,version,reading) VALUES('image','v2',1)")
            db.execute("INSERT INTO source_ocr_attempt_outcome(attempt_id,outcome_code) VALUES(2,'MAX_TOKENS')")
            db.execute("INSERT INTO source_ocr_attempt(image_id,version,reading) VALUES('image','v2',0)")
            with self.assertRaises(psycopg.errors.CheckViolation):
                with db.transaction():
                    db.execute("INSERT INTO source_ocr_attempt_outcome(attempt_id,outcome_code) VALUES(3,'secret-response')")
            with self.assertRaises(psycopg.errors.RaiseException):
                with db.transaction():
                    db.execute("INSERT INTO source_ocr_attempt_outcome(attempt_id,outcome_code) VALUES(1,'MAX_TOKENS')")
            for code in sorted(OUTCOME_CODES - {"MAX_TOKENS"}):
                aid = db.execute("INSERT INTO source_ocr_attempt(image_id,version,reading) VALUES('image','v2',0) RETURNING id").fetchone()[0]
                db.execute("INSERT INTO source_ocr_attempt_outcome(attempt_id,outcome_code) VALUES(%s,%s)", (aid, code))
            self.assertEqual(
                {row[0] for row in db.execute("SELECT outcome_code FROM source_ocr_attempt_outcome")},
                OUTCOME_CODES,
            )
            with self.assertRaises(psycopg.errors.RaiseException):
                with db.transaction():
                    db.execute("UPDATE source_ocr_attempt_outcome SET outcome_code='OTHER_FINISH' WHERE attempt_id=2")
        finally:
            # Leave no schema/table/row behind in the shared local fixture.
            db.rollback()
            db.close()


if __name__ == "__main__":
    unittest.main()

"""Bounded retained-version replay tests; optional PostgreSQL uses TEMP only."""

import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from psycopg.types.json import Jsonb

from . import official_sources, worker
from . import retained_replays as replay

KIND = "international-usda-boston-flowers"
URL = "https://www.ams.usda.gov/mnreports/bh_fv201.pdf"
FIXTURES = Path(__file__).resolve().parents[2] / "artifacts" / "official-sources"


def fake_db(candidates):
    db = MagicMock()

    def execute(sql, params=()):
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        if "WITH versions" in sql:
            result.fetchall.return_value = candidates
        elif "pg_try_advisory" in sql:
            result.fetchone.return_value = (True,)
        elif sql.startswith("SELECT content"):
            result.fetchone.return_value = (b"retained source bytes",)
        return result

    db.execute.side_effect = execute
    return db


class RetainedReplayTests(unittest.TestCase):
    def test_registered_leaf_kinds_exclude_indexes_evidence_and_media(self):
        kinds = dict(replay.leaf_versions())
        self.assertIn(KIND, kinds)
        self.assertIn("international-worldbank-monthly", kinds)
        self.assertIn("colombia-pork-pdf", kinds)
        self.assertNotIn("colombia-pork-posts", kinds)
        self.assertNotIn("colombia-corabastos-media", kinds)
        self.assertNotIn("colombia-evidence", kinds)
        self.assertTrue(all(not k.endswith("-index") for k in kinds))

    def test_selection_uses_metadata_and_limit_before_loading_bytes(self):
        sql, params = replay.candidate_query([(KIND, "v3")], 2, 3600)
        self.assertNotIn("content", sql)
        self.assertNotIn("historical_price", sql)
        self.assertIn("d.source_url=a.url", sql)
        self.assertIn("d.retrieved_at<current.retrieved_at", sql)
        self.assertIn("c.processor_version=v.processor_version", sql)
        self.assertIn("'official:complete'", sql)
        self.assertNotIn("FROM official_price_quote", sql)
        self.assertIn("LIMIT %s", sql)
        self.assertEqual(params[-1], 2)

    def test_zero_budget_or_disabled_drain_does_no_database_work(self):
        db = MagicMock()
        with patch.object(replay.time, "monotonic", return_value=10):
            self.assertEqual(replay.drain(db, deadline=9)["selected"], 0)
            self.assertEqual(replay.drain(db, limit=0)["selected"], 0)
        db.execute.assert_not_called()

    def test_original_url_content_and_hard_cap_are_preserved(self):
        db = fake_db([("a" * 64, URL, KIND, "v3")])
        with patch.object(official_sources, "process", return_value=35) as process:
            result = replay.drain(db, limit=999)
        self.assertEqual(result["rows"], 35)
        process.assert_called_once_with(
            db, b"retained source bytes", "a" * 64, URL, KIND
        )
        query = next(
            c for c in db.execute.call_args_list if "WITH versions" in c.args[0]
        )
        self.assertEqual(query.args[1][-1], 2)
        steps = [
            c.args[1][2]
            for c in db.execute.call_args_list
            if c.args[0].startswith("INSERT INTO ingestion_checkpoint")
        ]
        self.assertEqual(steps, [replay.COMPLETE])

    def test_failed_document_does_not_block_other_document_and_step_is_bounded(self):
        db = fake_db([("a" * 64, URL, KIND, "v3"), ("b" * 64, URL, KIND, "v3")])
        with patch.object(
            official_sources, "process", side_effect=[ValueError("Á" * 10000), 4]
        ):
            result = replay.drain(db)
        self.assertEqual(
            (result["review"], result["completed"], result["rows"]), (1, 1, 4)
        )
        steps = [
            c.args[1][2]
            for c in db.execute.call_args_list
            if c.args[0].startswith("INSERT INTO ingestion_checkpoint")
        ]
        self.assertEqual(steps, [replay.REVIEW, replay.COMPLETE])
        self.assertTrue(all(len(step.encode()) < 100 for step in steps))

    def test_ocr_and_transient_failure_never_get_completion_markers(self):
        for outcome in [None, RuntimeError("temporary source read failure")]:
            with self.subTest(outcome=outcome):
                db = fake_db([("a" * 64, URL, KIND, "v3")])
                with patch.object(official_sources, "process", side_effect=[outcome]):
                    result = replay.drain(db)
                self.assertEqual(result["completed"], 0)
                steps = [
                    c.args[1][2]
                    for c in db.execute.call_args_list
                    if c.args[0].startswith("INSERT INTO ingestion_checkpoint")
                ]
                self.assertEqual(len(steps), 1)
                self.assertTrue(steps[0].startswith(replay.ATTEMPT_PREFIX))

    def test_deadline_between_documents_stops_before_next_content_read(self):
        db = fake_db([("a" * 64, URL, KIND, "v3"), ("b" * 64, URL, KIND, "v3")])
        clock = [0]

        def process(*args):
            clock[0] = 11
            return 7

        with (
            patch.object(replay.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(official_sources, "process", side_effect=process),
        ):
            result = replay.drain(db, deadline=10)
        self.assertEqual((result["completed"], result["deferred"]), (1, 1))
        self.assertEqual(
            sum(
                c.args[0].startswith("SELECT content")
                for c in db.execute.call_args_list
            ),
            1,
        )


@unittest.skipUnless(
    os.environ.get("AGRO_REPLAY_POSTGRES_TEST") == "1",
    "Explicit opt-in for real PostgreSQL TEMP-table tests",
)
class RetainedReplayPostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        # Every application table referenced by replay/process is shadowed.
        # LIKE copies structure/indexes, never public rows, triggers or FKs.
        for table in (
            "source_document",
            "ingestion_asset",
            "official_price_quote",
            "official_source_review",
        ):
            self.db.execute(
                f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"
            )
        self.db.execute(
            "CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text,records bigint NOT NULL DEFAULT 0,completed_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(document_id,processor_version,step))"
        )
        self.db.execute("CREATE TEMP TABLE replay_probe(value text)")
        self.db.execute("CREATE INDEX ON source_document(source_url,retrieved_at DESC)")
        self.db.execute("SET search_path=pg_temp")
        self.version = worker.parser_version(KIND)
        self.latest = self.add_document(b"new current bytes", "2026-09-26", KIND)
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,document_id,status) VALUES(%s,%s,%s,'complete')",
            (URL, KIND, self.latest),
        )

    def tearDown(self):
        self.db.close()  # TEMP data disappears; public tables were never written.

    def add_document(self, body, at, kind=KIND, url=URL):
        did = hashlib.sha256(body).hexdigest()
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,retrieved_at,content,metadata) VALUES(%s,'Fixture','USDA AMS',%s,'application/pdf','original','fixture',%s,%s,%s)",
            (did, url, at, body, Jsonb({"ingestion_kind": kind})),
        )
        return did

    def steps(self):
        return self.db.execute(
            "SELECT document_id,processor_version,step,records FROM ingestion_checkpoint ORDER BY document_id,step"
        ).fetchall()

    def test_two_retained_real_pdfs_publish_once_without_moving_current_pointer(self):
        first = self.add_document(
            (FIXTURES / "boston-flower.pdf").read_bytes(), "2026-09-08"
        )
        second = self.add_document(
            (FIXTURES / "boston-2025-06-17.pdf").read_bytes(), "2026-09-07"
        )
        # Wrong-kind and newer-than-current originals must not be replayed.
        self.add_document(
            b"index bytes", "2026-09-09", "international-usda-boston-index"
        )
        self.add_document(b"later archived bytes", "2026-09-27")
        result = replay.drain(self.db)
        self.assertEqual((result["completed"], result["rows"]), (2, 69))
        self.assertEqual({row[0] for row in self.steps()}, {first, second})
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0],
            69,
        )
        self.assertEqual(
            self.db.execute(
                "SELECT document_id,status FROM ingestion_asset WHERE url=%s", (URL,)
            ).fetchone(),
            (self.latest, "complete"),
        )
        self.assertEqual(replay.drain(self.db)["selected"], 0)
        # The official completion marker alone avoids unnecessary replay, but
        # a partial footprint without either marker must remain recoverable.
        self.db.execute(
            "DELETE FROM pg_temp.ingestion_checkpoint WHERE step=%s", (replay.COMPLETE,)
        )
        self.assertEqual(replay.drain(self.db)["selected"], 0)
        before = self.db.execute(
            "SELECT document_id,source_locator,parser_version,parsed_at FROM official_price_quote ORDER BY 1,2,3"
        ).fetchall()
        self.db.execute("DELETE FROM pg_temp.ingestion_checkpoint")
        # Model an interrupted publication: a retained source has a footprint
        # but is missing one literal quote. The deletion is TEMP fixture only.
        missing = before[0][:3]
        self.db.execute(
            "DELETE FROM pg_temp.official_price_quote WHERE document_id=%s AND source_locator=%s AND parser_version=%s",
            missing,
        )
        result = replay.drain(self.db)
        self.assertEqual((result["selected"], result["completed"]), (2, 2))
        self.assertEqual(result["errors"], [])
        after = self.db.execute(
            "SELECT document_id,source_locator,parser_version,parsed_at FROM official_price_quote ORDER BY 1,2,3"
        ).fetchall()
        self.assertEqual(len(after), len(before))
        self.assertEqual(after[0][:3], missing)
        self.assertEqual(after[1:], before[1:])

    def test_failure_rolls_back_partial_work_and_version_upgrade_retries_review(self):
        bad = self.add_document(b"malformed source", "2026-09-09")
        self.add_document((FIXTURES / "boston-flower.pdf").read_bytes(), "2026-09-08")
        original = official_sources.process

        def process(db, body, did, url, kind):
            if did == bad:
                db.execute("INSERT INTO replay_probe VALUES('must roll back')")
                raise ValueError("Malformed source range")
            return original(db, body, did, url, kind)

        with patch.object(official_sources, "process", side_effect=process):
            result = replay.drain(self.db)
        self.assertEqual((result["review"], result["completed"]), (1, 1))
        self.assertEqual(self.db.execute("SELECT * FROM replay_probe").fetchall(), [])
        self.assertEqual(
            self.db.execute(
                "SELECT reason FROM official_source_review WHERE document_id=%s", (bad,)
            ).fetchone(),
            ("Malformed source range",),
        )
        self.assertEqual(replay.drain(self.db)["selected"], 0)
        with (
            patch.object(worker, "parser_version", return_value="upgraded"),
            patch.object(official_sources, "process", return_value=0),
        ):
            result = replay.drain(self.db)
        self.assertEqual(result["completed"], 2)
        self.assertTrue(
            any(row[:3] == (bad, "upgraded", replay.COMPLETE) for row in self.steps())
        )

    def test_ocr_tasks_commit_without_completion_and_retry_after_cooldown(self):
        did = self.add_document(
            (FIXTURES / "boston-flower.pdf").read_bytes(), "2026-09-08"
        )

        def pending(db, *args):
            db.execute("INSERT INTO replay_probe VALUES('durable OCR task')")

        with patch.object(official_sources, "process", side_effect=pending):
            self.assertEqual(replay.drain(self.db)["awaiting_ocr"], 1)
        self.assertEqual(
            self.db.execute("SELECT * FROM replay_probe").fetchall(),
            [("durable OCR task",)],
        )
        self.assertTrue(
            all(row[2].startswith(replay.ATTEMPT_PREFIX) for row in self.steps())
        )
        self.assertEqual(replay.drain(self.db)["selected"], 0)
        self.db.execute(
            "UPDATE pg_temp.ingestion_checkpoint SET completed_at=now()-interval '2 hours'"
        )
        self.assertEqual(replay.drain(self.db)["completed"], 1)
        self.assertTrue(
            any(row[:3] == (did, self.version, replay.COMPLETE) for row in self.steps())
        )


if __name__ == "__main__":
    unittest.main()

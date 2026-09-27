"""Exact-identity input publication survives interruption; all writes use TEMP."""

import os
import re
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import psycopg
from psycopg.pq import TransactionStatus

from . import inputs, resumable_inputs, worker
from .resumable_inputs import WorkDeferred

PERIOD = date(2026, 8, 31)


def source_rows():
    rows = []
    for number in [5, 2, 0, 4, 1, 3, 5]:
        rows.append(
            worker.record(
                "dane-inputs-municipal",
                PERIOD,
                f"Producto {number:03d}",
                "Municipio",
                "kg",
                100 + number + (20 if number == 5 and rows else 0),
                f"sheet!row {len(rows) + 1}",
                details={
                    "department": "Antioquia",
                    "municipality": "Municipio",
                    "presentation": "kg",
                    "category": "Fertilizantes",
                },
            )
        )
    return rows


@unittest.skipUnless(
    os.environ.get("AGRO_INPUT_BATCH_POSTGRES_TEST") == "1",
    "Explicit PostgreSQL TEMP opt-in",
)
class InputPublicationBatchTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.autocommit)
        self.db.execute("SET search_path=pg_temp")
        for table in (
            "historical_price",
            "input_price",
            "input_municipal_price",
            "ingestion_checkpoint",
            "source_ocr_task",
        ):
            self.db.execute(
                f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"
            )
        self.db.execute("""CREATE TEMP TABLE source_document(id text PRIMARY KEY,retrieved_at timestamptz NOT NULL);
          CREATE TEMP TABLE input_revision(id text,department text,municipality text,observed_on date,retrieved_at timestamptz NOT NULL,PRIMARY KEY(id,department,municipality,observed_on));
          CREATE TEMP TABLE retained_record(table_name text,fingerprint text,captured_at timestamptz DEFAULT now(),record jsonb,PRIMARY KEY(table_name,fingerprint));
          CREATE TEMP TABLE input_attempt(table_name text,id text,operation text);
          CREATE FUNCTION pg_temp.input_attempt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            INSERT INTO input_attempt VALUES(TG_TABLE_NAME,NEW.id,TG_OP);RETURN NEW;END $$;""")
        schema = (Path(__file__).parent / "schema.sql").read_text()
        retain = re.search(
            r"CREATE OR REPLACE FUNCTION preserve_record_version\(\)[\s\S]*?END \$\$;",
            schema,
        ).group(0)
        self.db.execute(
            retain.replace(
                "preserve_record_version()", "pg_temp.preserve_record_version()"
            )
        )
        for table in ("input_price", "input_municipal_price"):
            self.db.execute(f"""CREATE TRIGGER attempt BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION pg_temp.input_attempt();
              CREATE TRIGGER preserve AFTER INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION pg_temp.preserve_record_version()""")
        for letter, day in [("a", 1), ("b", 3), ("c", 2)]:
            self.db.execute(
                "INSERT INTO source_document VALUES(%s,%s)",
                (letter * 64, f"2026-09-0{day}T00:00:00Z"),
            )
        self.did = "a" * 64
        self.kind = "inputs-annex"
        self.db.execute(
            "INSERT INTO source_ocr_task(document_id,source_locator,image_id,source_kind,status) VALUES(%s,'pending','image',%s,'pending')",
            (self.did, self.kind),
        )
        self.rows = source_rows()
        self.enterContext(
            patch.object(inputs, "parse_inputs", side_effect=lambda _: iter(self.rows))
        )
        self.references = self.enterContext(
            patch(
                "pipelines.ingestion.input_references.extract_reference_rows",
                return_value=0,
            )
        )
        self.enterContext(patch.object(resumable_inputs, "PUBLICATION_BATCH_SIZE", 2))

    def publish(self, did=None, **kwargs):
        return resumable_inputs.publish(
            self.db, b"fixture", did or self.did, self.kind, PERIOD, **kwargs
        )

    def count(self, table):
        return self.db.execute(f"SELECT count(*) FROM pg_temp.{table}").fetchone()[0]

    def steps(self):
        return dict(
            self.db.execute(
                "SELECT step,records FROM ingestion_checkpoint WHERE document_id=%s",
                (self.did,),
            ).fetchall()
        )

    def test_failed_second_group_is_atomic_and_resume_preserves_conflicts_and_progress(
        self,
    ):
        self.db.execute("""CREATE FUNCTION pg_temp.fail_input() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF NEW.id='producto-002-kg' THEN RAISE EXCEPTION 'forced second input group';END IF;RETURN NEW;END $$;
          CREATE TRIGGER fail_input BEFORE INSERT ON input_municipal_price FOR EACH ROW EXECUTE FUNCTION pg_temp.fail_input()""")
        with self.assertRaisesRegex(psycopg.Error, "forced second input group"):
            self.publish()
        self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
        self.assertEqual(self.count("historical_price"), 7)
        self.assertEqual(self.count("input_municipal_price"), 2)
        self.assertEqual(self.count("input_revision"), 2)
        self.assertEqual(self.count("input_attempt"), 2)
        self.assertEqual(self.count("retained_record"), 2)
        steps = self.steps()
        self.assertEqual(steps["native"], 7)
        groups = {k: v for k, v in steps.items() if k.startswith("published-group-v1:")}
        self.assertEqual(len(groups), 1)
        self.assertNotIn("published:2026-08-31", steps)
        self.assertNotIn("references", steps)
        self.references.assert_not_called()
        self.assertEqual(
            self.db.execute("SELECT status FROM source_ocr_task").fetchone(),
            ("pending",),
        )
        self.assertIsNone(
            self.db.execute("SELECT to_regclass('pg_temp.input_stage')").fetchone()[0]
        )
        self.db.rollback()
        self.db.execute("DROP TRIGGER fail_input ON input_municipal_price")
        with (
            patch.object(
                inputs,
                "parse_inputs",
                side_effect=AssertionError("native parse repeated"),
            ),
            patch.object(
                inputs, "project_inputs", wraps=inputs.project_inputs
            ) as project,
        ):
            self.assertEqual(self.publish(), (7, 1))
            self.assertEqual(project.call_count, 2)
        self.assertEqual(self.count("input_municipal_price"), 5)
        self.assertEqual(self.count("input_revision"), 5)
        self.assertEqual(self.count("input_attempt"), 5)
        self.assertEqual(self.count("retained_record"), 5)
        self.assertFalse(
            self.db.execute(
                "SELECT 1 FROM input_municipal_price WHERE id='producto-005-kg'"
            ).fetchone()
        )
        self.assertEqual(
            len([s for s in self.steps() if s.startswith("published-group-v1:")]), 3
        )
        self.assertEqual(self.steps()["published:2026-08-31"], 1)
        self.assertEqual(
            self.db.execute("SELECT status FROM source_ocr_task").fetchone(),
            ("native-complete",),
        )
        with patch.object(
            inputs,
            "prepare_input_stage",
            side_effect=AssertionError("completed month restaged"),
        ):
            self.assertEqual(self.publish(), (7, 1))
        self.assertEqual(self.count("input_attempt"), 5)

    def test_unchanged_newer_revision_advances_watermark_without_insert_attempts(self):
        self.assertEqual(self.publish(), (7, 1))
        first = self.db.execute(
            "SELECT id,price,document_id,source_locator FROM input_municipal_price ORDER BY id"
        ).fetchall()
        self.assertEqual(self.publish("b" * 64), (7, 1))
        self.assertEqual(self.count("input_attempt"), 5)
        self.assertEqual(self.count("retained_record"), 5)
        self.assertEqual(
            self.db.execute(
                "SELECT id,price,document_id,source_locator FROM input_municipal_price ORDER BY id"
            ).fetchall(),
            first,
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM input_revision WHERE retrieved_at='2026-09-03'::timestamptz"
            ).fetchone(),
            (5,),
        )
        # Intermediate older changed prices cannot replace the later equal-price revision.
        changed = [(*r[:6], r[6] + 100, *r[7:]) for r in self.rows]
        self.rows = changed
        self.assertEqual(self.publish("c" * 64), (7, 1))
        self.assertEqual(self.count("input_attempt"), 5)
        self.assertEqual(
            self.db.execute(
                "SELECT id,price,document_id,source_locator FROM input_municipal_price ORDER BY id"
            ).fetchall(),
            first,
        )

    def test_deadline_after_first_group_leaves_no_month_or_source_completion(self):
        project = inputs.project_inputs
        clock = Mock(return_value=0)

        def publish_one(*args, **kwargs):
            result = project(*args, **kwargs)
            clock.return_value = 101
            return result

        with (
            patch.object(resumable_inputs, "time", SimpleNamespace(monotonic=clock)),
            patch.object(inputs, "project_inputs", side_effect=publish_one),
            self.assertRaises(WorkDeferred),
        ):
            self.publish(deadline=100)
        self.assertEqual(self.count("input_municipal_price"), 2)
        self.assertEqual(
            len([s for s in self.steps() if s.startswith("published-group-v1:")]), 1
        )
        self.assertNotIn("published:2026-08-31", self.steps())
        self.assertEqual(self.publish(), (7, 1))
        self.assertEqual(self.count("input_attempt"), 5)

    def test_validation_failure_and_outer_rollback_publish_nothing(self):
        def invalid(_):
            yield from self.rows
            raise ValueError("invalid final native source row")

        with (
            patch.object(inputs, "parse_inputs", side_effect=invalid),
            self.assertRaisesRegex(ValueError, "invalid final"),
        ):
            self.publish()
        self.assertEqual(self.count("historical_price"), 0)
        self.assertEqual(self.count("input_municipal_price"), 0)
        self.assertEqual(self.steps(), {})
        with (
            self.assertRaisesRegex(RuntimeError, "caller rollback"),
            self.db.transaction(),
        ):
            self.assertEqual(self.publish(), (7, 1))
            raise RuntimeError("caller rollback")
        for table in (
            "historical_price",
            "input_municipal_price",
            "input_revision",
            "retained_record",
            "input_attempt",
            "ingestion_checkpoint",
        ):
            self.assertEqual(self.count(table), 0, table)
        self.assertEqual(
            self.db.execute("SELECT status FROM source_ocr_task").fetchone(),
            ("pending",),
        )


if __name__ == "__main__":
    unittest.main()

"""Input replay ordering; optional integration checks write TEMP tables only."""

import os
import unittest
from datetime import date
from unittest.mock import MagicMock

from . import inputs, worker


class InputRevisionSQLTests(unittest.TestCase):
    def test_both_projections_guard_changed_values_by_original_revision(self):
        db = MagicMock()
        cur = db.cursor.return_value.__enter__.return_value
        cur.fetchmany.return_value = []
        cur.execute.return_value.fetchone.return_value = (0,)
        self.assertEqual(inputs.project_inputs(db, "incoming", date(2026, 1, 31)), 0)
        updates = [
            call
            for call in cur.execute.call_args_list
            if call.args[0].startswith(
                ("INSERT INTO input_price(", "INSERT INTO input_municipal_price(")
            )
        ]
        self.assertEqual(len(updates), 2)
        for update in updates:
            self.assertIn("IS DISTINCT FROM", update.args[0])
            self.assertIn(
                "AND (SELECT retrieved_at FROM source_document WHERE id=%s)",
                update.args[0],
            )
            self.assertIn(
                ">= (SELECT retrieved_at FROM source_document WHERE id=input_",
                update.args[0],
            )
            self.assertIn("FROM input_revision r", update.args[0])
            self.assertEqual(update.args[1], ("incoming", "incoming"))
        watermark = next(
            call
            for call in cur.execute.call_args_list
            if call.args[0].startswith("INSERT INTO input_revision(")
        )
        self.assertIn("HAVING min(price)=max(price)", watermark.args[0])
        self.assertIn(
            "WHERE input_revision.retrieved_at<excluded.retrieved_at", watermark.args[0]
        )


@unittest.skipUnless(
    os.environ.get("AGRO_INPUT_REVISION_POSTGRES_TEST") == "1",
    "Explicit opt-in for PostgreSQL TEMP-table checks",
)
class InputRevisionPostgresTests(unittest.TestCase):
    def test_old_replay_new_revision_and_equal_value_provenance(self):
        with worker.connect() as db:
            for table in ("historical_price", "input_price", "input_municipal_price"):
                db.execute(
                    f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"
                )
            db.execute(
                "CREATE TEMP TABLE source_document(id text PRIMARY KEY,retrieved_at timestamptz NOT NULL)"
            )
            db.execute(
                "CREATE TEMP TABLE input_revision(id text,department text,municipality text,observed_on date,retrieved_at timestamptz NOT NULL,PRIMARY KEY(id,department,municipality,observed_on))"
            )
            db.execute("SET search_path=pg_temp")
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM pg_class WHERE oid IN ('historical_price'::regclass,'input_price'::regclass,'input_municipal_price'::regclass,'source_document'::regclass,'input_revision'::regclass) AND relpersistence='t'"
                ).fetchone()[0],
                5,
            )
            for key, day in (
                ("a", 8),
                ("b", 20),
                ("c", 25),
                ("d", 26),
                ("e", 25),
                ("f", 27),
                ("g", 28),
            ):
                db.execute(
                    "INSERT INTO source_document VALUES(%s,%s)",
                    (key * 64, f"2026-09-{day:02d}T00:00:00Z"),
                )

            def publish(key, price, *, conflicts=0, rollback=False):
                did = key * 64
                rows = []
                for series, municipality in (
                    ("dane-inputs", ""),
                    ("dane-inputs-municipal", "El Carmen de Viboral"),
                ):
                    for value in price if isinstance(price, list) else [price]:
                        rows.append(
                            worker.record(
                                series,
                                date(2026, 1, 31),
                                "Arada de prueba",
                                municipality or "Antioquia",
                                "hora/máquina",
                                value,
                                f"3.7!row {len(rows) + 1}",
                                details={
                                    "category": "Servicios agrícolas",
                                    "department": "Antioquia",
                                    "municipality": municipality,
                                    "presentation": "hora/máquina",
                                },
                            )
                        )
                with db.transaction():
                    worker.save_rows(db, did, rows)
                    self.assertEqual(
                        inputs.project_inputs(db, did, date(2026, 1, 31)), conflicts
                    )
                    if rollback:
                        raise RuntimeError("simulated month transaction failure")

            def assert_published(key, price):
                for table in ("input_price", "input_municipal_price"):
                    self.assertEqual(
                        db.execute(f"SELECT price,document_id FROM {table}").fetchall(),
                        [(price, key * 64)],
                    )

            publish("b", 110)
            assert_published("b", 110)
            # Simulate published rows that existed before this additive migration.
            # Only this session's TEMP metadata is removed, never application data.
            db.execute("TRUNCATE input_revision")
            publish("a", 100)  # Older original must not roll back a correction.
            assert_published("b", 110)
            publish("c", 120)  # A genuinely newer changed original is accepted.
            assert_published("c", 120)
            publish("d", 120)  # Equal values keep the existing source locator.
            assert_published("c", 120)
            self.assertEqual(
                db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 8
            )
            publish("e", 115)  # Between c and unchanged d: published c is not enough.
            assert_published("c", 120)
            watermark = db.execute(
                "SELECT retrieved_at FROM input_revision ORDER BY municipality"
            ).fetchall()
            self.assertEqual(
                [str(row[0].date()) for row in watermark], ["2026-09-26"] * 2
            )
            publish("f", [130, 140], conflicts=2)
            assert_published("c", 120)
            self.assertEqual(
                db.execute(
                    "SELECT retrieved_at FROM input_revision ORDER BY municipality"
                ).fetchall(),
                watermark,
            )
            with self.assertRaisesRegex(RuntimeError, "simulated month"):
                publish("g", 150, rollback=True)
            assert_published("c", 120)
            self.assertEqual(
                db.execute(
                    "SELECT retrieved_at FROM input_revision ORDER BY municipality"
                ).fetchall(),
                watermark,
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 14
            )


if __name__ == "__main__":
    unittest.main()

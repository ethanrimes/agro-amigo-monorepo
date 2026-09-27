"""Supply publication semantics and retained evidence; isolated local PG only."""

import gzip
import json
import os
import time
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from . import supply, worker

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "artifacts/automation-audit-2026-09-26/international"
CURRENT_CACHE = EVIDENCE / "supply-2026-current-groups.jsonl.gz"


def groups(
    kg=100,
    *,
    month=1,
    days=(2, 20),
    category="Verduras",
    food="Tomate chonto",
    rows=None,
):
    return {
        ("Armenia, Mercar", food, date(2020, month, 1)): {
            "kg": kg,
            "days": {date(2020, month, d) for d in days},
            "category": category,
            "rows": rows or {"1.1": [[10, 12]]},
        }
    }


@unittest.skipUnless(
    os.environ.get("AGRO_SUPPLY_POSTGRES_TEST") == "1",
    "Explicit opt-in for isolated local PostgreSQL; cloud connections prohibited",
)
class SupplyRevisionPostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(
            self.db.info.host.startswith("/tmp/agro-"),
            "Supply integration tests require a private local PostgreSQL Unix socket",
        )
        self.db.execute("SET search_path=pg_temp")
        self.db.execute("SET statement_timeout='30s'")
        self.db.execute(
            "CREATE TEMP TABLE source_document(id text PRIMARY KEY,retrieved_at timestamptz)"
        )
        self.db.execute(
            "CREATE TEMP TABLE ingestion_checkpoint(document_id text REFERENCES source_document(id),processor_version text,step text,records bigint,completed_at timestamptz DEFAULT now(),PRIMARY KEY(document_id,processor_version,step))"
        )
        self.db.execute("CREATE TEMP TABLE product(id text PRIMARY KEY,name text)")
        self.db.execute(
            "CREATE TEMP TABLE municipality(id text PRIMARY KEY,name text,department text)"
        )
        self.db.execute(
            "CREATE TEMP TABLE market(id text PRIMARY KEY,name text,city text,region text,municipality_id text)"
        )
        market_schema = (ROOT / "pipelines/market/schema.sql").read_text()
        declaration = market_schema[
            market_schema.index("CREATE TABLE IF NOT EXISTS supply_observation") :
        ].split(";", 1)[0]
        self.db.execute(
            declaration.replace("CREATE TABLE IF NOT EXISTS", "CREATE TEMP TABLE")
        )
        schema = (ROOT / "pipelines/ingestion/schema.sql").read_text()
        declaration = schema[
            schema.index("CREATE TABLE IF NOT EXISTS retained_record") :
        ].split(";", 1)[0]
        self.db.execute(
            declaration.replace("CREATE TABLE IF NOT EXISTS", "CREATE TEMP TABLE")
        )
        for name in (
            "preserve_record_version",
            "prevent_history_removal",
            "enforce_demo_window",
        ):
            start = schema.index(f"CREATE OR REPLACE FUNCTION {name}()")
            definition = schema[start : schema.index("END $$;", start) + len("END $$;")]
            self.db.execute(
                definition.replace(f"FUNCTION {name}()", f"FUNCTION pg_temp.{name}()")
            )
        self.db.execute(
            "CREATE TRIGGER preserve_versions AFTER INSERT OR UPDATE ON supply_observation FOR EACH ROW EXECUTE FUNCTION pg_temp.preserve_record_version()"
        )
        self.db.execute(
            "CREATE TRIGGER demo_window BEFORE INSERT OR UPDATE ON supply_observation FOR EACH ROW EXECUTE FUNCTION pg_temp.enforce_demo_window()"
        )
        for table in ("supply_observation", "retained_record"):
            self.db.execute(
                f"CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION pg_temp.prevent_history_removal()"
            )
        for table in (
            "source_document",
            "ingestion_checkpoint",
            "product",
            "municipality",
            "market",
            "supply_observation",
            "retained_record",
        ):
            self.assertEqual(
                self.db.execute(
                    "SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)",
                    (table,),
                ).fetchone(),
                ("t",),
            )
        for key, day in (
            ("a", 8),
            ("b", 15),
            ("c", 20),
            ("d", 25),
            ("e", 26),
            ("f", 27),
            ("g", 27),
        ):
            self.db.execute(
                "INSERT INTO source_document VALUES(%s,%s)",
                (key * 64, f"2026-09-{day:02d}T00:00:00Z"),
            )
        self.db.execute("INSERT INTO municipality VALUES('63001','Armenia','Quindío')")

    def publish(self, key, values, db=None):
        with patch.object(supply, "parse_supply", return_value=values):
            return supply.publish_supply(
                db or self.db, b"native parser independently tested", key * 64
            )

    def test_newer_corrections_equal_value_evidence_and_stale_replay(self):
        for key, kg, winner, amount in (
            ("a", 100, "a", 100),
            ("c", 120, "c", 120),
            ("b", 105, "c", 120),
            ("e", 120, "e", 120),
            ("d", 115, "e", 120),
            ("f", 125, "f", 125),
            ("g", 130, "g", 130),
        ):
            self.assertEqual(self.publish(key, groups(kg)), 1)
            self.assertEqual(
                self.db.execute(
                    "SELECT quantity_kg,document_id FROM supply_observation"
                ).fetchone(),
                (amount, winner * 64),
            )
        before = self.db.execute("SELECT count(*) FROM retained_record").fetchone()[0]
        self.publish("g", groups(130))
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM retained_record").fetchone()[0],
            before,
        )
        evidence = self.db.execute(
            "SELECT record->>'document_id',record->>'quantity_kg' FROM retained_record WHERE table_name='supply_observation'"
        ).fetchall()
        self.assertEqual(
            set(evidence),
            {
                (k * 64, str(v))
                for k, v in (("a", 100), ("c", 120), ("e", 120), ("f", 125), ("g", 130))
            },
        )

    def test_metadata_only_correction_updates_every_source_field_same_original(self):
        self.publish("c", groups())
        self.db.execute(
            "INSERT INTO product VALUES('tomato-catalog-id','Tomate chonto')"
        )
        revised = groups(
            days=(1, 8, 25),
            category="Verduras y hortalizas",
            food="Tomate CHONTO",
            rows={"2.1": [[15, 16], [19, 20]]},
        )
        # A new parser version can correct metadata from an immutable original.
        with patch.object(worker, "parser_version", return_value="supply-metadata-fix"):
            self.publish("c", revised)
        self.assertEqual(
            self.db.execute(
                "SELECT food_name,product_id,category,observed_on,first_reported_on,reporting_days,quantity_kg,source_rows FROM supply_observation"
            ).fetchone(),
            (
                "Tomate CHONTO",
                "tomato-catalog-id",
                "Verduras y hortalizas",
                date(2020, 1, 25),
                date(2020, 1, 1),
                3,
                100,
                {"2.1": [[15, 16], [19, 20]]},
            ),
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM retained_record").fetchone()[0], 2
        )
        self.assertEqual(
            self.db.execute("SELECT municipality_id FROM market").fetchone(), ("63001",)
        )

    def test_source_timestamp_is_required_before_parsing_or_publication(self):
        self.db.execute("INSERT INTO source_document VALUES('null-timestamp',NULL)")
        for did in ("missing", "null-timestamp"):
            with (
                patch.object(supply, "parse_supply") as parse,
                self.assertRaisesRegex(ValueError, "retained source timestamp"),
            ):
                supply.publish_supply(self.db, b"source", did)
            parse.assert_not_called()
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM supply_observation").fetchone()[0], 0
        )

    def test_outer_transaction_rolls_back_every_month_and_retained_version(self):
        initial = {**groups(month=1), **groups(month=2)}
        self.publish("a", initial)
        before = self.db.execute(
            "SELECT * FROM supply_observation ORDER BY period_start"
        ).fetchall()
        originals = self.db.execute(
            "SELECT fingerprint FROM retained_record ORDER BY fingerprint"
        ).fetchall()
        real_cursor = self.db.cursor
        statements = []

        class Cursor:
            def __enter__(inner):
                inner.cur = real_cursor().__enter__()
                return inner

            def __exit__(inner, *args):
                return inner.cur.__exit__(*args)

            def __getattr__(inner, name):
                return getattr(inner.cur, name)

            def execute(inner, sql, params=()):
                if sql.startswith("INSERT INTO supply_observation"):
                    inner.cur.execute("SELECT DISTINCT period_start FROM supply_stage")
                    statements.append(inner.cur.fetchone()[0])
                    if len(statements) == 2:
                        raise RuntimeError("Simulated second-month interruption")
                return inner.cur.execute(sql, params)

        class Database:
            def __getattr__(inner, name):
                return getattr(self.db, name)

            def cursor(inner):
                return Cursor()

        with (
            self.assertRaisesRegex(RuntimeError, "second-month"),
            self.db.transaction(),
        ):
            self.publish(
                "c", {**groups(200, month=1), **groups(300, month=2)}, Database()
            )
        self.assertEqual(statements, [date(2020, 2, 1), date(2020, 1, 1)])
        self.assertEqual(
            self.db.execute(
                "SELECT * FROM supply_observation ORDER BY period_start"
            ).fetchall(),
            before,
        )
        self.assertEqual(
            self.db.execute(
                "SELECT fingerprint FROM retained_record ORDER BY fingerprint"
            ).fetchall(),
            originals,
        )

    def test_historical_deletion_and_truncation_remain_blocked(self):
        self.publish("a", groups())
        for statement in (
            "DELETE FROM supply_observation",
            "TRUNCATE supply_observation",
            "DELETE FROM retained_record",
        ):
            with self.assertRaisesRegex(Exception, "Permanent historical data"):
                self.db.execute(statement)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM supply_observation").fetchone()[0], 1
        )

    @unittest.skipUnless(
        CURRENT_CACHE.exists() or (EVIDENCE / "supply-2026-groups.jsonl.gz").exists(),
        "Optional real-source aggregate cache",
    )
    def test_real_year_publication_updates_preserve_all_source_rows_and_days(self):
        values = {}
        cache = (
            CURRENT_CACHE
            if CURRENT_CACHE.exists()
            else EVIDENCE / "supply-2026-groups.jsonl.gz"
        )
        with gzip.open(cache, "rt") as stream:
            for line in stream:
                r = json.loads(line)
                values[(r["market"], r["food"], date.fromisoformat(r["period"]))] = {
                    "kg": r["kg"],
                    "days": {date.fromisoformat(d) for d in r["days"]},
                    "category": r["category"],
                    "rows": r["rows"],
                }
        self.assertGreater(len(values), 20000)
        timings = {}
        for key, operation in (
            ("a", "initial_insert"),
            ("c", "equal_quantity_newer_original"),
            ("b", "older_original_replay"),
            ("c", "identical_repeat"),
        ):
            began = time.monotonic()
            self.assertEqual(self.publish(key, values), len(values))
            timings[operation] = round(time.monotonic() - began, 3)
        actual = self.db.execute(
            "SELECT market_id,food_id,period_start,food_name,category,quantity_kg,first_reported_on,observed_on,reporting_days,document_id,source_rows FROM supply_observation"
        ).fetchall()
        self.assertEqual(len(actual), len(values))
        expected = {
            (f"sipsa-{worker.slug(m)}", worker.slug(f), p): (f, g)
            for (m, f, p), g in values.items()
        }
        for row in actual:
            food, g = expected[row[:3]]
            self.assertEqual(
                row[3:],
                (
                    food,
                    g["category"],
                    Decimal(str(g["kg"])),
                    min(g["days"]),
                    max(g["days"]),
                    len(g["days"]),
                    "c" * 64,
                    g["rows"],
                ),
            )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM retained_record").fetchone()[0],
            len(values) * 2,
        )
        (EVIDENCE / "supply-v5-publication-performance.json").write_text(
            json.dumps(
                {
                    "environment": "isolated local PostgreSQL with real retention trigger",
                    "groups": len(values),
                    "months": len({k[2] for k in values}),
                    "timings_seconds": timings,
                    "azure_300_second_capacity_verified": False,
                },
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    unittest.main()

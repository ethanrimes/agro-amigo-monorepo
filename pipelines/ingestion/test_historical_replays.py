"""Historical COPY replays: production table constraints, TEMP-only SQL writes."""

import os
import unittest
from datetime import date

from psycopg.errors import CheckViolation
from psycopg.pq import TransactionStatus

from . import worker

TABLES = ("historical_price",)


def source_rows(count, *, offset=0, price=3500):
    for number in range(offset, offset + count):
        yield worker.record(
            "dane-daily",
            date(2026, 9, 25),
            "Tomate",
            "Bogotá, Corabastos",
            "kg",
            price + number,
            f"sheet 1!row {number + 1}",
            details={"category": "Verduras", "source_row": number + 1},
        )


@unittest.skipUnless(
    os.environ.get("AGRO_HISTORICAL_REPLAY_POSTGRES_TEST") == "1",
    "Explicit opt-in for isolated PostgreSQL TEMP-table replay checks",
)
class HistoricalReplayPostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.autocommit)
        self.db.execute("SET search_path=pg_temp")
        self.db.execute("SET statement_timeout='30s'")
        self.db.execute(
            "CREATE TEMP TABLE historical_price (LIKE public.historical_price INCLUDING ALL)"
        )
        self.assertEqual(
            self.db.execute(
                "SELECT relpersistence FROM pg_class WHERE oid='historical_price'::regclass"
            ).fetchone(),
            ("t",),
        )
        # BEFORE INSERT runs even on rows rejected later by ON CONFLICT. This
        # counter distinguishes truly skipped identities from conflict no-ops.
        self.db.execute("""CREATE TEMP TABLE historical_insert_attempt(document_id text,source_locator text);
            CREATE FUNCTION pg_temp.track_historical_insert() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
              INSERT INTO pg_temp.historical_insert_attempt VALUES(NEW.document_id,NEW.source_locator); RETURN NEW;
            END $$;
            CREATE TRIGGER track_insert BEFORE INSERT ON historical_price FOR EACH ROW EXECUTE FUNCTION pg_temp.track_historical_insert();
            CREATE FUNCTION pg_temp.reject_historical_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
              RAISE EXCEPTION 'Immutable fixture must never be updated, deleted or truncated';
            END $$;
            CREATE TRIGGER protect_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON historical_price
              FOR EACH STATEMENT EXECUTE FUNCTION pg_temp.reject_historical_mutation();""")

    def save(self, rows, did="a" * 64):
        with self.db.transaction():
            return worker.save_rows(self.db, did, rows)

    def counts(self):
        return self.db.execute(
            "SELECT (SELECT count(*) FROM historical_price),(SELECT count(*) FROM historical_insert_attempt)"
        ).fetchone()

    def test_full_replay_never_attempts_existing_inserts(self):
        self.assertEqual(self.save(source_rows(20000)), 20000)
        self.assertEqual(self.counts(), (20000, 20000))
        before = self.db.execute(
            "SELECT count(DISTINCT xmin::text),min(xmin::text),sum(price) FROM historical_price"
        ).fetchone()
        self.assertEqual(self.save(source_rows(20000)), 20000)
        self.assertEqual(self.counts(), (20000, 20000))
        self.assertEqual(
            before,
            self.db.execute(
                "SELECT count(DISTINCT xmin::text),min(xmin::text),sum(price) FROM historical_price"
            ).fetchone(),
        )
        self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
        self.assertIsNone(
            self.db.execute("SELECT to_regclass('pg_temp.ingestion_stage')").fetchone()[
                0
            ]
        )

    def test_partial_existing_file_only_inserts_missing_identities(self):
        self.assertEqual(self.save(source_rows(3, offset=2)), 3)
        self.assertEqual(self.save(source_rows(7)), 7)
        self.assertEqual(self.counts(), (7, 7))
        actual = self.db.execute(
            "SELECT source_locator,price,details FROM historical_price ORDER BY source_locator"
        ).fetchall()
        self.assertEqual(actual, [(row[0], row[6], row[-1]) for row in source_rows(7)])

    def test_same_locator_in_new_original_is_preserved_separately(self):
        self.assertEqual(self.save(source_rows(2)), 2)
        self.assertEqual(self.save(source_rows(2, price=5000), "b" * 64), 2)
        self.assertEqual(self.counts(), (4, 4))
        self.assertEqual(
            self.db.execute(
                "SELECT document_id,min(price) FROM historical_price GROUP BY document_id ORDER BY 1"
            ).fetchall(),
            [("a" * 64, 3500), ("b" * 64, 5000)],
        )

    def test_reparsed_identity_does_not_replace_immutable_source_values(self):
        self.assertEqual(self.save(source_rows(2)), 2)
        original = self.db.execute(
            "SELECT * FROM historical_price ORDER BY source_locator"
        ).fetchall()
        self.assertEqual(self.save(source_rows(2, price=9000)), 2)
        self.assertEqual(self.counts(), (2, 2))
        self.assertEqual(
            original,
            self.db.execute(
                "SELECT * FROM historical_price ORDER BY source_locator"
            ).fetchall(),
        )

    def test_invalid_new_row_rolls_back_only_current_transaction(self):
        self.assertEqual(self.save(source_rows(1)), 1)
        incoming = list(source_rows(3))
        invalid = list(incoming[-1])
        invalid[6] = -10
        incoming[-1] = tuple(invalid)
        with self.assertRaises(CheckViolation):
            self.save(incoming)
        self.assertEqual(self.counts(), (1, 1))
        self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
        self.assertEqual(self.save(source_rows(3)), 3)
        self.assertEqual(self.counts(), (3, 3))

    def test_empty_stream_publishes_nothing(self):
        self.assertEqual(self.save(iter(())), 0)
        self.assertEqual(self.counts(), (0, 0))


if __name__ == "__main__":
    unittest.main()

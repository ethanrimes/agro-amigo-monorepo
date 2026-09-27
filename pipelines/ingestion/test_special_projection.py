"""Farm/mill publication chronology and bulk writes in isolated TEMP tables."""

import os
import unittest
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from psycopg.errors import CheckViolation
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from . import special_prices, worker

TABLES = (
    "source_document",
    "historical_price",
    "price_observation",
    "product",
    "market",
    "municipality",
    "ingestion_asset",
)
DAY = date(2026, 7, 31)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def milk(
    price=2100,
    *,
    town="Rionegro",
    low=2000,
    high=2200,
    locator="sheet 1!row 2",
    day=DAY,
):
    return worker.record(
        "dane-milk-farm",
        day,
        "Leche cruda en finca",
        town,
        "litre",
        price,
        locator,
        details={
            "department": "Antioquia",
            "municipality": town,
            "price_basis": "farmgate",
            "min_price": low,
            "max_price": high,
        },
    )


def rice(price=2750000, *, low=2500000, high=2800000):
    return worker.record(
        "dane-rice-mill",
        DAY,
        "Arroz blanco",
        "Espinal",
        "tonne",
        price,
        "rice!row 2",
        details={
            "department": "Tolima",
            "municipality": "Espinal",
            "price_basis": "mill",
            "min_price": low,
            "max_price": high,
        },
    )


@unittest.skipUnless(
    os.environ.get("AGRO_SPECIAL_PROJECTION_POSTGRES_TEST") == "1",
    "Explicit opt-in for isolated PostgreSQL TEMP-table projection checks",
)
class SpecialProjectionPostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.autocommit)
        self.db.execute("SET search_path=pg_temp")
        self.db.execute("SET statement_timeout='30s'")
        for table in TABLES:
            self.db.execute(
                f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"
            )
            self.assertEqual(
                self.db.execute(
                    "SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)",
                    (table,),
                ).fetchone(),
                ("t",),
            )
        self.db.execute("""CREATE TEMP TABLE retained_record(table_name text,fingerprint text,record jsonb,PRIMARY KEY(table_name,fingerprint));
            CREATE TEMP TABLE price_insert_statements(operation text);
            CREATE FUNCTION pg_temp.count_price_statements() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
              INSERT INTO pg_temp.price_insert_statements VALUES(TG_OP); RETURN NULL;
            END $$;
            CREATE TRIGGER price_statements AFTER INSERT ON price_observation
              FOR EACH STATEMENT EXECUTE FUNCTION pg_temp.count_price_statements();
            CREATE TRIGGER demo_window BEFORE INSERT OR UPDATE ON price_observation
              FOR EACH ROW EXECUTE FUNCTION public.enforce_demo_window();""")
        # Exercise the actual append-only revision function against TEMP records.
        schema = (Path(__file__).parent / "schema.sql").read_text()
        function = schema.split(
            "CREATE OR REPLACE FUNCTION preserve_record_version()", 1
        )[1].split("END $$;", 1)[0]
        self.db.execute(
            "CREATE FUNCTION pg_temp.preserve_record_version()" + function + "END $$;"
        )
        self.db.execute(
            "CREATE TRIGGER preserve_versions AFTER INSERT OR UPDATE ON price_observation FOR EACH ROW EXECUTE FUNCTION pg_temp.preserve_record_version()"
        )

    def original(self, label, rows, *, retrieved="2026-09-20T12:00:00Z", media=XLSX):
        did = sha256(label.encode()).hexdigest()
        url = "https://example.invalid/" + label
        self.db.execute(
            """INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,retrieved_at,metadata)
            VALUES(%s,%s,'DANE',%s,%s,'original','',%s,%s,%s)""",
            (
                did,
                label,
                url,
                media,
                label.encode(),
                retrieved,
                Jsonb(
                    {
                        "ingestion_kind": "milk-pdf"
                        if media == "application/pdf"
                        else "milk"
                    }
                ),
            ),
        )
        with self.db.transaction():
            worker.save_rows(self.db, did, rows)
        return did, url

    def publish(self, original):
        return special_prices.project_special(self.db, *original)

    def prices(self):
        return self.db.execute(
            "SELECT price,min_price,max_price,unit,document_id,source_locator FROM price_observation ORDER BY product_id,market_id,observed_on"
        ).fetchall()

    def count(self, table):
        return self.db.execute(f"SELECT count(*) FROM pg_temp.{table}").fetchone()[0]

    def test_old_workbook_replay_is_rejected_and_equal_newer_value_advances_provenance(
        self,
    ):
        original = self.original("current", [milk()])
        older = self.original(
            "older", [milk(1900, low=1800, high=2000)], retrieved="2026-09-10T12:00:00Z"
        )
        newer = self.original(
            "newer-same-price", [milk()], retrieved="2026-09-25T12:00:00Z"
        )
        self.assertEqual(self.publish(original), 0)
        self.assertEqual(self.publish(older), 0)
        self.assertEqual(
            self.prices()[0][0:5], (2100, 2000, 2200, "litre", original[0])
        )
        self.assertEqual(self.publish(newer), 0)
        self.assertEqual(self.prices()[0][4], newer[0])
        self.assertEqual(
            self.db.execute("SELECT source_url FROM price_observation").fetchone()[0],
            newer[1],
        )
        self.assertEqual(self.count("historical_price"), 3)
        self.assertEqual(self.count("source_document"), 3)
        retained = [
            r[0]
            for r in self.db.execute("SELECT record FROM retained_record").fetchall()
        ]
        self.assertEqual({r["document_id"] for r in retained}, {original[0], newer[0]})

    def test_pdf_workbook_precedence_review_escape_and_chronology_all_hold(self):
        pdf = self.original(
            "early-pdf",
            [milk(1900, low=1800, high=2000)],
            retrieved="2026-09-10T12:00:00Z",
            media="application/pdf",
        )
        workbook = self.original("middle-workbook", [milk()])
        later_pdf = self.original(
            "later-pdf",
            [milk(2300, low=2200, high=2400)],
            retrieved="2026-09-25T12:00:00Z",
            media="application/pdf",
        )
        newest_workbook = self.original(
            "newest-workbook",
            [milk(2400, low=2300, high=2500)],
            retrieved="2026-09-26T12:00:00Z",
        )
        for doc, expected in [(pdf, pdf), (workbook, workbook), (later_pdf, workbook)]:
            self.publish(doc)
            self.assertEqual(self.prices()[0][4], expected[0])
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,document_id,status) VALUES(%s,'milk',%s,'review')",
            (workbook[1], workbook[0]),
        )
        self.publish(later_pdf)
        self.assertEqual(self.prices()[0][4], later_pdf[0])
        self.publish(workbook)  # Workbook priority cannot bypass retrieval chronology.
        self.assertEqual(self.prices()[0][4], later_pdf[0])
        self.publish(pdf)
        self.assertEqual(self.prices()[0][4], later_pdf[0])
        self.publish(newest_workbook)
        self.assertEqual(self.prices()[0][4], newest_workbook[0])

    def test_milk_keeps_litres_and_rice_converts_mean_and_both_bounds_to_kg(self):
        original = self.original("milk-and-rice", [milk(), rice()])
        self.assertEqual(self.publish(original), 0)
        rows = {r[3]: r for r in self.prices()}
        self.assertEqual(rows["litre"][:3], (2100, 2000, 2200))
        self.assertEqual(rows["kg"][:3], (2750, 2500, 2800))
        self.assertIn("COP/tonelada dividido entre 1000 = COP/kg", rows["kg"][5])
        self.assertIn("precio en finca, COP/litro", rows["litre"][5])
        raw = self.db.execute(
            "SELECT unit,price,details FROM historical_price WHERE series='dane-rice-mill'"
        ).fetchone()
        self.assertEqual(raw[:2], ("tonne", 2750000))
        self.assertEqual((raw[2]["min_price"], raw[2]["max_price"]), (2500000, 2800000))
        self.assertEqual(self.count("price_insert_statements"), 1)

    def test_null_rice_bounds_remain_null(self):
        original = self.original("rice-no-bounds", [rice(low=None, high=None)])
        self.publish(original)
        self.assertEqual(self.prices()[0][:4], (2750, None, None, "kg"))

    def test_conflicting_means_or_ranges_are_excluded_while_exact_duplicates_collapse(
        self,
    ):
        rows = [
            milk(locator="r1"),
            milk(2150, locator="r2"),
            milk(town="Yarumal", locator="r3"),
            milk(town="Yarumal", low=1900, locator="r4"),
            milk(town="Entrerríos", locator="r5"),
            milk(town="Entrerríos", locator="r6"),
        ]
        missing = list(milk(town="Unknown", locator="r7"))
        missing[-1] = {}
        rows.append(tuple(missing))
        original = self.original("conflicts", rows)
        self.assertEqual(self.publish(original), 3)
        self.assertEqual(self.count("price_observation"), 1)
        self.assertEqual(self.count("historical_price"), 7)
        self.assertEqual(
            self.db.execute(
                "SELECT city FROM market WHERE id=(SELECT market_id FROM price_observation)"
            ).fetchone()[0],
            "Entrerríos",
        )

    def test_bound_repair_same_document_updates_but_identical_replay_does_not(self):
        original = self.original("bounds", [milk()])
        self.publish(original)
        self.db.execute("UPDATE price_observation SET min_price=NULL,max_price=NULL")
        self.publish(original)
        self.assertEqual(self.prices()[0][:3], (2100, 2000, 2200))
        before = self.db.execute("SELECT xmin::text FROM price_observation").fetchone()
        versions = self.count("retained_record")
        self.publish(original)
        self.assertEqual(
            self.db.execute("SELECT xmin::text FROM price_observation").fetchone(),
            before,
        )
        self.assertEqual(self.count("retained_record"), versions)

    def test_failed_price_batch_rolls_back_catalog_rows_but_retains_archived_history(
        self,
    ):
        original = self.original("invalid-range", [milk(low=3000)])
        with self.assertRaises(CheckViolation):
            self.publish(original)
        for table in (
            "price_observation",
            "product",
            "market",
            "retained_record",
            "price_insert_statements",
        ):
            self.assertEqual(self.count(table), 0, table)
        self.assertEqual(self.count("historical_price"), 1)
        self.assertEqual(self.count("source_document"), 1)
        self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
        self.assertIsNone(
            self.db.execute(
                "SELECT to_regclass('pg_temp.special_price_stage')"
            ).fetchone()[0]
        )

    def test_six_thousand_prices_publish_in_one_statement_and_replay_preserves_versions(
        self,
    ):
        rows = [
            milk(
                town=f"Municipio {town}",
                day=date(2000 + month // 12, month % 12 + 1, 1),
                locator=f"sheet!{town}:{month}",
            )
            for town in range(50)
            for month in range(120)
        ]
        original = self.original("bulk-6000", rows)
        self.assertEqual(self.publish(original), 0)
        self.assertEqual(self.count("price_observation"), 6000)
        self.assertEqual(self.count("price_insert_statements"), 1)
        self.assertEqual(self.count("retained_record"), 6000)
        self.assertEqual(
            self.db.execute("SELECT sum(price) FROM price_observation").fetchone()[0],
            Decimal(2100 * 6000),
        )
        self.publish(original)
        self.assertEqual(self.count("price_insert_statements"), 2)
        self.assertEqual(self.count("retained_record"), 6000)
        self.assertEqual(self.count("historical_price"), 6000)


if __name__ == "__main__":
    unittest.main()

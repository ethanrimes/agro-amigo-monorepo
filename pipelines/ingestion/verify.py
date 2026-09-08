"""Live integrity, retention, source-value and least-privilege checks."""

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import psycopg

from pipelines.ingestion.worker import connect, today


def verify():
    with connect() as db:
        coverage = db.execute(
            "SELECT series,count(*),min(observed_on),max(observed_on) FROM historical_price GROUP BY series ORDER BY series"
        ).fetchall()
        assert coverage, "No historical observations"
        for table in [
            "price_observation",
            "coffee_reference",
            "coffee_factor",
            "exchange_rate",
            "daily_price",
            "input_price",
            "input_municipal_price",
            "regional_price",
        ]:
            rows, missing, future = db.execute(
                f"SELECT count(*),count(*) FILTER(WHERE document_id IS NULL),count(*) FILTER(WHERE observed_on>%s) FROM {table}",
                (today(),),
            ).fetchone()
            assert missing == future == 0, (table, missing, future)
            print(table, rows, "traceable records; no future dates")
        for table in [
            "historical_price",
            "retained_record",
            "source_document",
            "daily_price",
            "price_observation",
            "seasonal_year",
            "supply_observation",
            "input_municipal_price",
            "regional_price",
            "source_pdf_page",
            "source_archive_member",
            "regional_classification",
            "source_ocr_result",
        ]:
            try:
                with db.transaction():
                    db.execute(f"DELETE FROM {table} WHERE false")
            except (
                psycopg.errors.RaiseException,
                psycopg.errors.InsufficientPrivilege,
            ):
                pass
            else:
                raise AssertionError("Deletion not blocked: " + table)
        try:
            with db.transaction():
                db.execute(
                    "INSERT INTO coffee_reference(observed_on,price,source_url) VALUES(%s,1,%s)",
                    (
                        today() + timedelta(days=1),
                        "https://example.invalid/retention-test",
                    ),
                )
        except psycopg.errors.RaiseException:
            pass
        else:
            raise AssertionError("Future date accepted")
        with db.transaction():
            db.execute(
                "INSERT INTO coffee_reference(observed_on,price,source_url) VALUES(%s,1,%s)",
                (date(1900, 1, 1), "https://example.invalid/retention-test"),
            )
            raise psycopg.Rollback()
        assert not db.execute(
            "SELECT 1 FROM coffee_reference WHERE observed_on=%s", (date(1900, 1, 1),)
        ).fetchone()
        checks = [
            (
                "dane-monthly",
                date(2013, 1, 31),
                "Alas de pollo con costillar",
                "Barranquilla, Barranquillita",
                3073,
            ),
            ("dane-monthly-bulletin", date(2012, 7, 31), "Ahuyama", "Armenia", 545),
            (
                "fnc-daily",
                date(2003, 1, 2),
                "Café pergamino seco",
                "FNC nacional",
                277000,
            ),
            ("dane-daily", date(2012, 6, 12), "Ahuyama", "Bogotá", 800),
        ]
        for series, day, product, market, expected in checks:
            values = db.execute(
                "SELECT DISTINCT price FROM historical_price WHERE series=%s AND observed_on=%s AND product_name=%s AND market_name=%s",
                (series, day, product, market),
            ).fetchall()
            assert values and all(float(v[0]) == expected for v in values), (
                series,
                day,
                values,
            )
        documents = 0
        # Hash the actual original bytes for every ingested asset, one at a time.
        ids = [
            r[0]
            for r in db.execute(
                "SELECT DISTINCT document_id FROM ingestion_asset WHERE document_id IS NOT NULL"
            ).fetchall()
        ]
        for did in ids:
            content = db.execute(
                "SELECT content FROM source_document WHERE id=%s", (did,)
            ).fetchone()[0]
            assert hashlib.sha256(content).hexdigest() == did, did
            documents += 1
        report = {
            "coverage": coverage,
            "source_hashes_verified": documents,
            "queue": db.execute(
                "SELECT kind,status,count(*) FROM ingestion_asset GROUP BY kind,status ORDER BY kind,status"
            ).fetchall(),
            "database_size": db.execute(
                "SELECT pg_size_pretty(pg_database_size(current_database()))"
            ).fetchone()[0],
        }
        Path("artifacts").mkdir(exist_ok=True)
        Path("artifacts/ingestion-validation.json").write_text(
            json.dumps(report, default=str, indent=2) + "\n"
        )
        print(json.dumps(report, default=str, indent=2))
    print("Permanent retention, source values, date guards and archived hashes passed.")


if __name__ == "__main__":
    verify()

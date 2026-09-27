"""Real FNC publication/routing proof; explicitly opted-in PostgreSQL TEMP only.

Network/archive and OCR scanning are replaced at their edges. Native parsers,
legacy daily/factor/branch projection, official publisher, retained selection,
checkpoints, production column constraints and the production date trigger run.
"""

import hashlib
import json
import os
import unittest
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from psycopg.types.json import Jsonb

from . import coffee_sources, official_sources, retained_replays, worker

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts/automation-audit-2026-09-26"
AS_OF = date(2026, 9, 26)
TABLES = (
    "source_document",
    "ingestion_asset",
    "official_price_quote",
    "official_source_review",
    "historical_price",
    "coffee_reference",
    "coffee_factor",
    "market",
    "price_observation",
    "document_alias",
    "source_pdf_page",
)


def fixtures():
    return [
        r
        for r in json.loads((ARTIFACTS / "colombia-current-coverage.json").read_text())
        if r["kind"] == "coffee-pdf"
        or (r["kind"] == "coffee" and "b13fef2a71" in r["file"])
    ]


def identity(row):
    parts = {
        key: row[key]
        for key in ("product_id", "series", "market", "currency", "unit", "basis")
    }
    parts["dimensions"] = row.get("identity_dimensions", {})
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


@unittest.skipUnless(
    os.environ.get("AGRO_COFFEE_POSTGRES_TEST") == "1",
    "Explicit opt-in for real PostgreSQL TEMP-table FNC integration",
)
class CoffeeIntegrationPostgresTests(unittest.TestCase):
    def setUp(self):
        # This suite isolates raw batching/routing; dedicated catalog tests cover
        # the derived refresh hook against the actual migration and SQL.
        self.enterContext(
            patch(
                "pipelines.ingestion.official_catalog.refresh_document", return_value=0
            )
        )
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        # Fail closed before touching application relations. LIKE copies column
        # constraints/indexes/defaults, never rows, triggers, or external FKs.
        self.db.execute("SET search_path=pg_temp")
        self.db.execute("SET statement_timeout='60s'")
        for table in TABLES:
            self.db.execute(
                f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"
            )
        self.db.execute(
            "CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text,records bigint NOT NULL DEFAULT 0,completed_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(document_id,processor_version,step))"
        )
        for table in (*TABLES, "ingestion_checkpoint"):
            self.assertEqual(
                self.db.execute(
                    "SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)",
                    (table,),
                ).fetchone(),
                ("t",),
            )
        # Apply the actual deployed function to TEMP rows, including the 1913
        # observation. No public relation or function is created/altered.
        for table in (
            "official_price_quote",
            "coffee_reference",
            "coffee_factor",
            "price_observation",
        ):
            self.db.execute(
                f"CREATE TRIGGER demo_window BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION public.enforce_demo_window()"
            )
        self.items = fixtures()
        self.bodies = {}
        self.expected = {}
        for item in self.items:
            body = (ROOT / item["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(body).hexdigest(), item["sha256"])
            self.bodies[item["url"]] = body
            self.expected[item["sha256"]] = coffee_sources.publication_rows(
                coffee_sources.parse(body, item["url"], item["kind"], as_of=AS_OF)
            )
            self.add_document(item, body, "2026-09-26T00:00:00Z")
        self.clock = patch.object(worker, "today", return_value=AS_OF)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def add_document(self, item, body, retrieved_at):
        did = hashlib.sha256(body).hexdigest()
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,retrieved_at,content,metadata) VALUES(%s,'Real FNC integration fixture','FNC',%s,%s,'original','2026-09',%s,%s,%s)",
            (
                did,
                item["url"],
                "application/pdf"
                if item["kind"] == "coffee-pdf"
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                retrieved_at,
                body,
                Jsonb({"ingestion_kind": item["kind"]}),
            ),
        )
        return did

    def assert_exact_publication(self):
        actual = self.db.execute(
            "SELECT document_id,source_locator,parser_version,quote_key,product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,period_start,price,source_page,details FROM official_price_quote"
        ).fetchall()
        self.assertEqual(len(actual), 11553)
        by_source = {(r[0], r[1]): r for r in actual}
        for item in self.items:
            did = item["sha256"]
            for row in self.expected[did]:
                self.assertEqual(
                    by_source[(did, row["source_locator"])],
                    (
                        did,
                        row["source_locator"],
                        worker.parser_version(item["kind"]),
                        identity(row),
                        row["product_id"],
                        row["product_name"],
                        row["category"],
                        row["publisher"],
                        row["series"],
                        row["basis"],
                        row["currency"],
                        row["unit"],
                        row["market"],
                        row["date"],
                        row.get("period_start"),
                        Decimal(str(row["price"])),
                        row.get("source_page"),
                        {**row["details"], "identity_dimensions": {}},
                    ),
                )
        self.assertEqual(min(r[13] for r in actual), date(1913, 1, 31))
        self.assertNotIn("fnc-internal-daily", Counter(r[8] for r in actual))
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_source_review").fetchone(),
            (0,),
        )

    def test_worker_real_workbook_pdf_and_repeat_preserve_exact_extra_quotes(self):
        for item in self.items:
            self.db.execute(
                "INSERT INTO ingestion_asset(url,kind,status) VALUES(%s,%s,'pending')",
                (item["url"], item["kind"]),
            )

        def local_archive(db, url, data, kind, day):
            self.assertIs(db, self.db)
            self.assertEqual(data, self.bodies[url])
            return hashlib.sha256(data).hexdigest()

        from . import ocr

        with (
            patch.object(
                worker,
                "fetch_asset",
                side_effect=lambda db, url, **kw: self.bodies[url],
            ),
            patch.object(worker, "archive", side_effect=local_archive),
            patch.object(ocr, "scan_document"),
        ):
            for item in sorted(self.items, key=lambda r: r["kind"]):
                count = worker.process_asset(self.db, item["url"], item["kind"], None)
                self.assertEqual(count, 20218 if item["kind"] == "coffee" else 2)
            self.assert_exact_publication()
            before = self.db.execute(
                "SELECT document_id,source_locator,parser_version,parsed_at FROM official_price_quote ORDER BY 1,2,3"
            ).fetchall()
            for item in self.items:
                count = worker.process_asset(self.db, item["url"], item["kind"], None)
                self.assertEqual(count, 0)
            self.assertEqual(
                self.db.execute(
                    "SELECT document_id,source_locator,parser_version,parsed_at FROM official_price_quote ORDER BY 1,2,3"
                ).fetchall(),
                before,
            )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM coffee_reference").fetchone(),
            (8666,),
        )
        # FNC prints 2018-11-11 twice with the same COP805,000 price. Retain
        # both literal source rows, while the dated national view is unique.
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone(),
            (8667,),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*),min(price),max(price) FROM historical_price WHERE observed_on='2018-11-11'"
            ).fetchone(),
            (2, Decimal(805000), Decimal(805000)),
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM coffee_factor").fetchone(), (13,)
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM price_observation").fetchone(),
            (16,),
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM source_pdf_page").fetchone(), (2,)
        )
        self.assertEqual(
            self.db.execute(
                "SELECT DISTINCT processor_version,status FROM ingestion_asset"
            ).fetchall(),
            [(worker.parser_version("coffee"), "complete")],
        )
        self.assertEqual(
            worker.parser_version("coffee"),
            official_sources.VERSION + ":" + coffee_sources.VERSION,
        )

    def test_retained_real_coffee_versions_route_once_without_current_pointer_change(
        self,
    ):
        kinds = dict(retained_replays.leaf_versions())
        pointers = {}
        for item in self.items:
            self.assertEqual(kinds[item["kind"]], worker.parser_version(item["kind"]))
            # This is a pointer-only sentinel for a newer mutable revision. The
            # replayed document retains its actual bytes, SHA and official URL.
            current = self.add_document(
                item,
                ("Test pointer sentinel " + item["kind"]).encode(),
                "2026-09-27T00:00:00Z",
            )
            pointers[item["url"]] = current
            self.db.execute(
                "INSERT INTO ingestion_asset(url,kind,document_id,status) VALUES(%s,%s,%s,'complete')",
                (item["url"], item["kind"], current),
            )
        with patch.object(worker, "fetch", side_effect=AssertionError("No refetch")):
            result = retained_replays.drain(self.db)
        self.assertEqual(result["errors"], [])
        self.assertEqual((result["completed"], result["rows"]), (2, 11553))
        self.assert_exact_publication()
        self.assertEqual(
            dict(self.db.execute("SELECT url,document_id FROM ingestion_asset")),
            pointers,
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*),sum(records) FROM ingestion_checkpoint WHERE step=%s AND processor_version=%s",
                (retained_replays.COMPLETE, worker.parser_version("coffee")),
            ).fetchone(),
            (2, 11553),
        )
        self.assertEqual(retained_replays.drain(self.db)["selected"], 0)
        # Retained official routing intentionally adds supplementary references;
        # the regular worker owns the separate national/factor/branch tables.
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM coffee_reference").fetchone(),
            (0,),
        )


if __name__ == "__main__":
    unittest.main()

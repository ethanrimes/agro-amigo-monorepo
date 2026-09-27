"""Daily eligibility changes despite an unchanged FNC original and HTTP ETag.

Opt-in PostgreSQL TEMP-only integration. Native workbook parsers, HTTP validator
logic, archive hashes, projections and success checkpoints execute unchanged.
"""

import hashlib
import os
import unittest
from datetime import date
from unittest.mock import Mock, patch

from psycopg.types.json import Jsonb

from . import official_sources, worker
from .test_coffee_integration import TABLES
from .test_coffee_sources import workbook

DAY1 = date(2026, 9, 26)
DAY2 = date(2026, 9, 27)
URL = "https://federaciondecafeteros.org/rollover-fixture.xlsx"


def original(price=999999, *, future_only=False):
    def edit(book):
        daily = book["1. Precio Interno Diario "]
        daily["B7"] = DAY2 if future_only else DAY1
        daily["B8"] = DAY2
        daily["C8"] = price

    return workbook(edit)


@unittest.skipUnless(
    os.environ.get("AGRO_COFFEE_ROLLOVER_POSTGRES_TEST") == "1",
    "Explicit PostgreSQL TEMP-table opt-in",
)
class CoffeeRolloverPostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.autocommit)
        self.db.execute("SET search_path=pg_temp")
        for table in TABLES:
            self.db.execute(
                f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"
            )
        self.db.execute(
            "CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text,records bigint,completed_at timestamptz DEFAULT now(),PRIMARY KEY(document_id,processor_version,step))"
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status) VALUES(%s,'coffee','pending')",
            (URL,),
        )
        token = worker.RUN_DEADLINE.set(None)
        self.addCleanup(worker.RUN_DEADLINE.reset, token)
        self.day = DAY1
        self.body = original()
        self.responses = []
        self.unconditional_304 = False
        self.enterContext(patch.object(worker, "today", side_effect=lambda: self.day))
        self.enterContext(patch.object(worker.SESSION, "get", side_effect=self.http))
        self.enterContext(patch.object(worker, "archive", side_effect=self.archive))
        self.enterContext(patch("pipelines.ingestion.ocr.scan_document"))
        self.enterContext(
            patch(
                "pipelines.ingestion.official_catalog.refresh_document", return_value=0
            )
        )
        self.native = self.enterContext(
            patch.object(worker, "parse_coffee", wraps=worker.parse_coffee)
        )

    def http(self, url, *, headers, timeout):
        self.assertEqual(url, URL)
        self.responses.append(dict(headers))
        etag = '"' + hashlib.sha256(self.body).hexdigest() + '"'
        unchanged = headers.get("If-None-Match") == etag
        return Mock(
            status_code=304 if unchanged or self.unconditional_304 else 200,
            content=self.body,
            headers={"ETag": etag},
        )

    def archive(self, db, url, data, kind, day):
        did = hashlib.sha256(data).hexdigest()
        db.execute(
            """INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
            VALUES(%s,'Rollover fixture','FNC',%s,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','original','2026-09',%s,%s)
            ON CONFLICT DO NOTHING""",
            (did, url, data, Jsonb({"ingestion_kind": kind})),
        )
        return did

    def publish(self):
        return worker.process_asset(self.db, URL, "coffee", None)

    def markers(self):
        return self.db.execute(
            "SELECT document_id,processor_version,step FROM ingestion_checkpoint WHERE step LIKE 'as-of:%%' ORDER BY step,document_id"
        ).fetchall()

    def test_same_sha_replays_next_colombia_day_and_same_day_304_is_cheap(self):
        self.assertGreater(self.publish(), 0)
        did = hashlib.sha256(self.body).hexdigest()
        self.assertEqual(self.responses[-1], {})
        self.assertEqual(self.native.call_count, 1)
        self.assertEqual(
            self.db.execute("SELECT observed_on FROM coffee_reference").fetchall(),
            [(DAY1,)],
        )
        self.assertEqual(
            self.markers(), [(did, worker.parser_version("coffee"), "as-of:2026-09-26")]
        )
        self.assertEqual(self.publish(), 0)
        self.assertIn("If-None-Match", self.responses[-1])
        self.assertEqual(self.native.call_count, 1)
        self.day = DAY2
        self.assertGreater(self.publish(), 0)
        self.assertEqual(self.responses[-1], {})
        self.assertEqual(self.native.call_count, 2)
        self.assertEqual(
            self.db.execute(
                "SELECT observed_on FROM coffee_reference ORDER BY observed_on"
            ).fetchall(),
            [(DAY1,), (DAY2,)],
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone(), (2,)
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM source_document").fetchone(), (1,)
        )
        self.assertEqual(
            [m[2] for m in self.markers()], ["as-of:2026-09-26", "as-of:2026-09-27"]
        )
        self.assertEqual(self.publish(), 0)
        self.assertEqual(self.native.call_count, 2)

    def test_changed_bytes_same_day_revalidate_and_publish_new_document(self):
        self.publish()
        old = hashlib.sha256(self.body).hexdigest()
        self.body = original(price=888888)
        self.assertGreater(self.publish(), 0)
        new = hashlib.sha256(self.body).hexdigest()
        self.assertNotEqual(old, new)
        self.assertIn("If-None-Match", self.responses[-1])
        self.assertEqual(self.native.call_count, 2)
        self.assertEqual({m[0] for m in self.markers()}, {old, new})
        self.assertEqual(
            self.db.execute(
                "SELECT document_id FROM ingestion_asset WHERE url=%s", (URL,)
            ).fetchone(),
            (new,),
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM source_document").fetchone(), (2,)
        )

    def test_unconditional_304_uses_retained_bytes_for_new_days_native_parse(self):
        self.publish()
        self.day = DAY2
        self.unconditional_304 = True
        self.assertGreater(self.publish(), 0)
        self.assertEqual(self.responses[-1], {})
        self.assertEqual(self.native.call_count, 2)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM coffee_reference").fetchone(), (2,)
        )
        self.assertEqual(len(self.markers()), 2)

    def test_failed_native_parse_cannot_mark_day_even_if_other_series_are_valid(self):
        self.body = original(future_only=True)
        with (
            patch.object(worker, "enqueue_failed_workbook", return_value=False),
            self.assertRaisesRegex(ValueError, "No FNC daily history"),
        ):
            self.publish()
        self.assertEqual(self.markers(), [])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM source_document").fetchone(), (1,)
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM coffee_reference").fetchone(), (0,)
        )

    def test_ocr_pending_and_publication_failure_never_mark_success(self):
        self.body = original(future_only=True)

        def await_ocr(db, url, kind, exc):
            db.execute(
                "UPDATE ingestion_asset SET status='awaiting-ocr' WHERE url=%s", (url,)
            )
            return True

        with patch.object(worker, "enqueue_failed_workbook", side_effect=await_ocr):
            self.assertEqual(self.publish(), 0)
        self.assertEqual(self.markers(), [])
        self.body = original()
        with (
            patch.object(
                official_sources,
                "publish_rows",
                side_effect=RuntimeError("publication failed"),
            ),
            self.assertRaisesRegex(RuntimeError, "publication failed"),
        ):
            self.publish()
        self.assertEqual(self.markers(), [])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM coffee_reference").fetchone(), (0,)
        )

    def test_old_marker_never_substitutes_for_current_parser(self):
        self.publish()
        self.db.execute(
            "UPDATE ingestion_checkpoint SET processor_version='earlier-parser' WHERE step LIKE 'as-of:%%'"
        )
        self.assertGreater(self.publish(), 0)
        self.assertEqual(self.responses[-1], {})
        self.assertEqual(self.native.call_count, 2)
        self.assertEqual(len(self.markers()), 2)


if __name__ == "__main__":
    unittest.main()

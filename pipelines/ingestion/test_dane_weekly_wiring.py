"""Weekly sources use official publication, revision checks and bounded queues."""

import hashlib
import os
import unittest
from contextlib import nullcontext
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from . import (
    dane_weekly,
    function_app,
    ocr,
    official_sources,
    queue_plan,
    retained_replays,
    worker,
)
from .test_ocr_budget import Database as OCRDatabase
from .test_ocr_budget import Result as OCRResult

KIND = "dane-weekly-xlsx"
URL = "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSASemanal-19sep25sep-2026.xlsx"
DAY = date(2026, 9, 25)


def quote():
    return {
        "product_id": "tomate-chonto",
        "product_name": "Tomate chonto",
        "category": "Verduras y hortalizas",
        "publisher": "DANE · SIPSA",
        "series": "dane-weekly",
        "basis": "Precio mayorista semanal",
        "currency": "COP",
        "unit": "kg",
        "market": "Bogotá, D.C., Corabastos",
        "date": DAY,
        "period_start": date(2026, 9, 19),
        "price": 2500,
        "min": 2000,
        "max": 3000,
        "source_locator": "Hoja 1!B8:D8",
        "details": {"period_start": "2026-09-19", "period_end": "2026-09-25"},
    }


class WeeklyWiring(unittest.TestCase):
    def test_explicit_weekly_filename_supplies_date_but_ambiguous_history_does_not(
        self,
    ):
        self.assertEqual(dane_weekly.source_date(URL), DAY)
        self.assertIsNone(
            dane_weekly.source_date(
                "https://www.dane.gov.co/files/Semana4_junio_2012.pdf"
            )
        )

    def test_only_registered_weekly_kinds_get_adapter_versions_and_retained_replay(
        self,
    ):
        for kind in dane_weekly.PUBLISHERS:
            self.assertIs(official_sources.adapter(kind), dane_weekly)
            self.assertTrue(official_sources.is_reference_kind(kind))
            self.assertEqual(
                worker.parser_version(kind),
                official_sources.VERSION + ":" + dane_weekly.VERSION,
            )
        self.assertFalse(official_sources.is_reference_kind("dane-weekly-unsupported"))
        with self.assertRaisesRegex(ValueError, "Unregistered"):
            official_sources.adapter("dane-weekly-unsupported")
        versions = queue_plan.expected_versions().obj
        self.assertTrue(set(dane_weekly.PUBLISHERS) <= versions.keys())
        leaves = dict(retained_replays.leaf_versions())
        self.assertIn("dane-weekly-xlsx", leaves)
        self.assertIn("dane-weekly-pdf", leaves)
        self.assertNotIn("dane-weekly-index", leaves)
        self.assertIn("pipelines/ingestion/dane_weekly.py", worker.RELEASE_FILES)

    def test_root_and_child_discovery_queue_explicit_weekly_date(self):
        from . import colombia_sources, international_sources

        db = MagicMock()
        root = dane_weekly.ROOTS[0]
        with (
            patch.object(colombia_sources, "discover", return_value=[]),
            patch.object(international_sources, "discover", return_value=[]),
            patch.object(dane_weekly, "discover", return_value=[root, (URL, KIND)]),
            patch.object(dane_weekly, "source_date", return_value=DAY),
            patch.object(worker, "queue") as queue,
        ):
            official_sources.discover_roots(db)
        self.assertEqual(queue.call_args_list[0].args, (db, *root))
        self.assertEqual(queue.call_args_list[1].args, (db, URL, KIND, DAY))
        with (
            patch.object(dane_weekly, "discover", return_value=[(URL, KIND)]),
            patch.object(dane_weekly, "source_date", return_value=DAY),
            patch.object(dane_weekly, "parse", return_value=[]),
            patch.object(official_sources, "publish_rows", return_value=0),
            patch.object(worker, "queue") as queue,
        ):
            self.assertEqual(
                official_sources.process(db, b"<html>", "index-doc", *root), 0
            )
        queue.assert_called_once_with(db, URL, KIND, DAY)

    def test_archive_keeps_publisher_original_bytes_and_real_xls_mime(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None
        url = URL.replace(".xlsx", ".xls")
        data = b"original xls bytes"
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}):
            did = worker.archive(db, url, data, KIND, DAY)
        self.assertEqual(did, hashlib.sha256(data).hexdigest())
        stored = next(
            c.args[1]
            for c in db.execute.call_args_list
            if c.args[0].startswith("INSERT INTO source_document")
        )
        self.assertEqual(
            stored[2:7],
            ("DANE · SIPSA", url, "application/vnd.ms-excel", "original", str(DAY)),
        )
        self.assertEqual(stored[8], data)
        self.assertEqual(stored[9].obj["ingestion_kind"], KIND)

    def test_current_original_uses_conditional_fetch_but_changed_hash_republishes(self):
        old = b"old weekly original"
        changed = b"corrected weekly original"
        old_did = hashlib.sha256(old).hexdigest()
        version = worker.parser_version(KIND)
        for data, count in ((None, 0), (old, 0), (changed, 1)):
            with self.subTest(body=data):
                db = MagicMock()
                db.execute.return_value.fetchone.side_effect = [(version,)] + (
                    [(old_did, "complete", 1)] if data else []
                )
                with (
                    patch.object(worker, "fetch_asset", return_value=data) as fetch,
                    patch.object(
                        worker,
                        "archive",
                        side_effect=lambda _db, _url, body, *_: hashlib.sha256(
                            body
                        ).hexdigest(),
                    ) as archive,
                    patch.object(
                        official_sources, "process", return_value=1
                    ) as publish,
                    patch.object(worker, "project") as legacy,
                    patch.object(ocr, "scan_document") as scan,
                ):
                    self.assertEqual(worker._process_asset(db, URL, KIND, DAY), count)
                fetch.assert_called_once_with(db, URL, force=False)
                self.assertEqual(publish.call_count, count)
                self.assertEqual(archive.call_count, int(data is not None))
                legacy.assert_not_called()
                scan.assert_not_called()  # Native adapter owns any necessary OCR.

    def test_parser_upgrade_forces_revalidation_and_missing_ocr_never_completes(self):
        db = MagicMock()
        db.execute.return_value.fetchone.side_effect = [
            ("old-version",),
            ("doc", "complete", 1),
        ]
        with (
            patch.object(worker, "fetch_asset", return_value=b"original") as fetch,
            patch.object(worker, "archive", return_value="doc"),
            patch.object(official_sources, "process", return_value=None),
        ):
            self.assertEqual(worker._process_asset(db, URL, KIND, DAY), 0)
        fetch.assert_called_once_with(db, URL, force=True)
        updated = [
            c.args[1]
            for c in db.execute.call_args_list
            if "status=%s,records=%s" in c.args[0]
        ]
        self.assertEqual(updated[-1], ("doc", "awaiting-ocr", 0, URL))

    def test_http_304_and_updated_validator_keep_source_revalidation(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (
            "old-etag",
            None,
            "complete",
            "old-doc",
        )
        response = MagicMock(status_code=304)
        with patch.object(worker.SESSION, "get", return_value=response) as fetch:
            self.assertIsNone(worker.fetch_asset(db, URL))
        self.assertEqual(
            fetch.call_args.kwargs["headers"], {"If-None-Match": "old-etag"}
        )
        response.status_code = 200
        response.content = b"corrected weekly bytes"
        response.headers = {"ETag": "new-etag"}
        with patch.object(worker.SESSION, "get", return_value=response):
            self.assertEqual(worker.fetch_asset(db, URL), b"corrected weekly bytes")
        self.assertIn(
            ("new-etag", None, URL),
            [c.args[1] for c in db.execute.call_args_list if len(c.args) > 1],
        )

    def test_cached_weekly_pdf_ocr_routes_back_to_official_adapter_without_provider_calls(
        self,
    ):
        class WeeklyOCR(OCRDatabase):
            def execute(self, sql, params=()):
                if sql.startswith("SELECT document_id,source_locator,image_id"):
                    return OCRResult(
                        many=[("doc", "PDF page 1", "image", "dane-weekly-pdf", 1)]
                    )
                if sql.startswith("SELECT content,source_url"):
                    return OCRResult(
                        one=(b"%PDF-original", URL.replace(".xlsx", ".pdf"))
                    )
                return super().execute(sql, params)

        db = WeeklyOCR(used=40, cache=(("image", 0), ("image", 1)))
        with (
            patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "mock-only", "GEMINI_OCR_DAILY_REQUESTS": "40"},
            ),
            patch.object(ocr, "transcribe") as provider,
            patch.object(ocr, "publish_workbook_reading") as legacy,
            patch.object(official_sources, "process", return_value=3) as publish,
        ):
            result = ocr.drain(db, limit=1, scan_limit=0)
        self.assertEqual(result["processed"], 1)
        publish.assert_called_once_with(
            db, b"%PDF-original", "doc", URL.replace(".xlsx", ".pdf"), "dane-weekly-pdf"
        )
        provider.assert_not_called()
        legacy.assert_not_called()


@unittest.skipUnless(
    os.environ.get("AGRO_WEEKLY_WIRING_POSTGRES_TEST") == "1",
    "Explicit local/TEMP PostgreSQL opt-in",
)
class WeeklyPostgresWiring(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        # Derived catalog materialization has its own PostgreSQL suite. Keep
        # this fixture focused on the literal weekly publication contract.
        catalog = patch(
            "pipelines.ingestion.official_catalog.refresh_document", return_value=1
        )
        self.catalog = catalog.start()
        self.addCleanup(catalog.stop)
        self.db.execute(
            "CREATE TEMP TABLE ingestion_asset (LIKE public.ingestion_asset INCLUDING ALL)"
        )
        self.db.execute(
            "CREATE TEMP TABLE official_price_quote (LIKE public.official_price_quote INCLUDING ALL)"
        )
        self.db.execute(
            "CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text,records bigint,PRIMARY KEY(document_id,processor_version,step))"
        )
        self.db.execute("SET search_path=pg_temp,public")

    def seed(
        self,
        url,
        kind,
        *,
        day=None,
        status="complete",
        checked="now()-interval '1 day'",
        version=None,
    ):
        self.db.execute(
            f"INSERT INTO ingestion_asset(url,kind,observed_on,status,checked_at,processor_version) VALUES(%s,%s,%s,%s,{checked},%s)",
            (url, kind, day, status, version or worker.parser_version(kind)),
        )

    def test_weekly_current_roots_recent_revisions_fresh_and_historical_lanes(self):
        root, root_kind = dane_weekly.ROOTS[0]
        self.seed(root, root_kind)
        current_index = "https://www.dane.gov.co/weekly-2026"
        old_index = "https://www.dane.gov.co/weekly-2012"
        self.seed(current_index, "dane-weekly-index")
        self.seed(old_index, "dane-weekly-index")
        self.seed(URL, KIND, day=DAY)
        self.seed(URL + "?cooldown", KIND, day=DAY, checked="now()")
        self.seed(URL + "?ocr", KIND, day=DAY, status="awaiting-ocr")
        self.seed(URL + "?old", KIND, day=date(2012, 6, 22))
        self.seed(
            URL + "?upgrade",
            KIND,
            day=date(2012, 6, 22),
            checked="now()",
            version="old-weekly",
        )
        self.seed(URL + "?pending-2012", KIND, day=date(2012, 6, 22), status="pending")
        self.seed(URL + "?pending-2026", KIND, day=DAY, status="pending")
        self.seed(URL + "?undated", "dane-weekly-pdf", status="pending")
        daily = {r[0] for r in queue_plan.daily_candidates(self.db, date(2026, 9, 27))}
        self.assertTrue(
            {root, current_index, URL, URL + "?pending-2026", URL + "?undated"} <= daily
        )
        self.assertFalse(
            {
                old_index,
                URL + "?old",
                URL + "?cooldown",
                URL + "?ocr",
                URL + "?upgrade",
                URL + "?pending-2012",
            }
            & daily
        )
        backfill = [r[0] for r in queue_plan.backfill_candidates(self.db, 100)]
        self.assertIn(URL + "?upgrade", backfill)
        self.assertIn(URL + "?pending-2012", backfill)
        self.assertLess(
            backfill.index(URL + "?pending-2026"), backfill.index(URL + "?pending-2012")
        )
        self.assertNotIn(URL + "?cooldown", backfill)

    def test_new_native_parser_retries_stale_ocr_before_pending_backlog(self):
        kind = "inputs-annex"
        for status in ("awaiting-ocr", "failed", "review"):
            self.seed(
                "https://example.invalid/stale-" + status,
                kind,
                day=DAY,
                status=status,
                checked="now()",
                version="old-native-parser",
            )
            self.seed(
                "https://example.invalid/current-" + status,
                kind,
                day=DAY,
                status=status,
                checked="now()",
            )
        self.seed(
            "https://example.invalid/old-pending",
            kind,
            day=date(2012, 1, 31),
            status="pending",
        )
        self.seed(
            "https://example.invalid/interrupted-pending",
            kind,
            day=DAY,
            status="pending",
            checked="now()",
            version="old-native-parser",
        )
        fresh = {r[0] for r in queue_plan.daily_candidates(self.db, date(2026, 9, 27))}
        backfill = [r[0] for r in queue_plan.backfill_candidates(self.db, 100)]
        self.assertNotIn("https://example.invalid/interrupted-pending", fresh)
        self.assertNotIn("https://example.invalid/interrupted-pending", backfill)
        for status in ("awaiting-ocr", "failed", "review"):
            stale = "https://example.invalid/stale-" + status
            current = "https://example.invalid/current-" + status
            self.assertIn(stale, fresh)
            self.assertIn(stale, backfill)
            self.assertNotIn(current, fresh)
            self.assertNotIn(current, backfill)
            self.assertLess(
                backfill.index(stale),
                backfill.index("https://example.invalid/old-pending"),
            )

    def test_weekly_publication_keeps_period_range_and_official_only_identity(self):
        self.seed(URL, KIND)
        self.db.execute(
            "UPDATE ingestion_asset SET document_id='weekly-original' WHERE url=%s",
            (URL,),
        )
        with patch.object(worker, "today", return_value=date(2026, 9, 27)):
            self.assertEqual(
                official_sources.publish_rows(
                    self.db, [quote()], "weekly-original", KIND
                ),
                1,
            )
            self.assertEqual(
                official_sources.publish_rows(
                    self.db, [quote()], "weekly-original", KIND
                ),
                1,
            )
        row = self.db.execute(
            "SELECT series,basis,currency,unit,observed_on,period_start,price,min_price,max_price,document_id FROM official_price_quote"
        ).fetchone()
        self.assertEqual(
            row,
            (
                "dane-weekly",
                "Precio mayorista semanal",
                "COP",
                "kg",
                DAY,
                date(2026, 9, 19),
                2500,
                2000,
                3000,
                "weekly-original",
            ),
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0],
            1,
        )
        self.assertEqual(
            self.db.execute(
                "SELECT records FROM ingestion_checkpoint WHERE step='official:complete'"
            ).fetchone(),
            (1,),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT observed_on FROM ingestion_asset WHERE url=%s", (URL,)
            ).fetchone(),
            (DAY,),
        )
        self.assertEqual(self.catalog.call_count, 2)

    def test_workbook_viewer_allows_weekly_xls_but_rejects_unregistered_kind_and_pdf(
        self,
    ):
        self.db.execute(
            "CREATE TEMP TABLE source_document(id text PRIMARY KEY,content bytea,publisher text,media_type text,metadata jsonb)"
        )
        cases = [
            ("a", "DANE · SIPSA", "dane-weekly-xlsx", "application/vnd.ms-excel", 200),
            (
                "b",
                "Unregistered publisher",
                "dane-weekly-unsupported",
                "application/vnd.ms-excel",
                404,
            ),
            ("c", "DANE · SIPSA", "dane-weekly-pdf", "application/vnd.ms-excel", 404),
            ("d", "DANE · SIPSA", "dane-weekly-xlsx", "application/pdf", 404),
            ("e", "DANE", "inputs", "application/vnd.ms-excel", 200),
            (
                "f",
                "FNC",
                "coffee",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                200,
            ),
        ]
        for key, publisher, kind, media, expected in cases:
            did = key * 64
            self.db.execute(
                "INSERT INTO source_document VALUES(%s,%s,%s,%s,jsonb_build_object('ingestion_kind',%s::text))",
                (did, b"archived workbook", publisher, media, kind),
            )
            request = SimpleNamespace(
                route_params={"id": did},
                params={"sheet": "Precios", "start": "5", "limit": "50"},
            )
            with (
                patch.object(
                    function_app, "connect", return_value=nullcontext(self.db)
                ),
                patch(
                    "pipelines.ingestion.workbook_preview.preview",
                    return_value={"sheet": "Precios", "rows": []},
                ) as preview,
            ):
                response = function_app.source_workbook.build().get_user_function()(
                    request
                )
            self.assertEqual(response.status_code, expected, kind)
            if expected == 200:
                preview.assert_called_once_with(b"archived workbook", "Precios", 5, 50)
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            else:
                preview.assert_not_called()


if __name__ == "__main__":
    unittest.main()

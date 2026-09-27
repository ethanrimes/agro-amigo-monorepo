"""Regression tests for ingestion dispatch, revisions, health and OCR fallback."""

import io
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from PIL import Image

from . import colombia_sources, function_app, official_sources, worker
from .ocr import enqueue_image, png_bytes, spreadsheet_images


def image_workbook():
    book = Workbook()
    book.active.append(["DANE", "Precios", "Municipio", "Fecha"])
    book.active.add_image(
        ExcelImage(io.BytesIO(png_bytes(Image.new("RGB", (800, 500), "white")))), "A4"
    )
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


class Runtime(unittest.TestCase):
    def setUp(self):
        # Catalog SQL has its own PostgreSQL integration suite. These fixtures
        # exercise orchestration and intentionally provide no cache tables.
        self.catalog = patch.object(worker, "refresh_catalog", return_value=0)
        self.catalog.start()
        self.addCleanup(self.catalog.stop)

    def test_failed_input_publication_resumes_retained_bytes_before_mutable_url(self):
        db = MagicMock()
        did = "a" * 64
        url = "https://www.dane.gov.co/series-inputs.xlsx"
        db.execute.return_value.fetchone.side_effect = [
            (worker.parser_version("inputs-municipal"),),
            (b"validated retained original",),
            (did, "failed", 0),
        ]
        with (
            patch.object(worker, "fetch_asset") as fetch,
            patch.object(worker, "archive", return_value=did),
            patch("pipelines.ingestion.ocr.scan_document"),
            patch(
                "pipelines.ingestion.resumable_inputs.publish", return_value=(42, 0)
            ) as publish,
        ):
            self.assertEqual(
                worker.process_asset(db, url, "inputs-municipal", None), 42
            )
        fetch.assert_not_called()
        self.assertEqual(publish.call_args.args[1], b"validated retained original")
        self.assertIn(
            "a.status IN ('pending','failed')", db.execute.call_args_list[1].args[0]
        )

    def test_catalog_failure_is_visible_and_ocr_still_runs_then_refreshes(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (True,)
        events = []

        def refresh(_db):
            events.append("catalog")
            if len(events) == 1:
                raise ValueError("Temporary catalog failure")
            return 7

        with (
            patch.object(worker, "connect") as connect,
            patch.object(worker, "refresh_catalog", side_effect=refresh),
            patch(
                "pipelines.ingestion.ocr.drain",
                side_effect=lambda *args, **kwargs: events.append("ocr") or {},
            ),
        ):
            connect.return_value.__enter__.return_value = db
            result = worker.run("ocr", limit=0, time_budget=600)
        self.assertEqual(events, ["catalog", "ocr", "catalog"])
        self.assertEqual(result["errors"][0]["source"], "official_catalog")
        self.assertEqual(result["catalog_after_publication"], 7)

    def test_targeted_operational_check_only_processes_registered_sources(self):
        url = "https://www.dane.gov.co/retained-source.xlsx"
        for registered in (False, True):
            with self.subTest(registered=registered):
                db = MagicMock()
                db.execute.return_value.fetchone.return_value = (True,)
                db.execute.return_value.fetchall.return_value = (
                    [(url, "supply", None)] if registered else []
                )
                with (
                    patch.object(worker, "connect") as connect,
                    patch.object(worker, "process_asset", return_value=5) as process,
                    patch("pipelines.ingestion.ocr.drain", return_value={}),
                    patch(
                        "pipelines.ingestion.queue_plan.backfill_candidates"
                    ) as queue,
                ):
                    connect.return_value.__enter__.return_value = db
                    summary = worker.run(
                        "backfill", asset_url=url, ocr_limit=0, ocr_scan_limit=0
                    )
                self.assertEqual(summary["assets"], int(registered))
                self.assertEqual(process.call_count, int(registered))
                queue.assert_not_called()
                self.assertTrue(
                    any(
                        c.args
                        == (
                            "SELECT url,kind,observed_on FROM ingestion_asset WHERE url=%s",
                            (url,),
                        )
                        for c in db.execute.call_args_list
                    )
                )

    def test_operational_http_check_preserves_ocr_and_time_bounds(self):
        req = MagicMock(
            params={"asset_url": "https://www.dane.gov.co/retained-source.xlsx"}
        )
        with patch.object(function_app, "run", return_value={}) as run:
            response = function_app.run_check.build().get_user_function()(req)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            run.call_args.kwargs,
            {
                "limit": 4,
                "time_budget": 120,
                "ocr_limit": 0,
                "ocr_scan_limit": 0,
                "asset_url": req.params["asset_url"],
            },
        )

    def test_health_poll_never_aggregates_historical_prices(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        req = MagicMock(params={})
        with (
            patch.object(function_app, "connect") as connect,
            patch.object(
                function_app, "automation_health", return_value={"status": "ok"}
            ),
        ):
            connect.return_value.__enter__.return_value = db
            response = function_app.status.build().get_user_function()(req)
        self.assertEqual(response.status_code, 200)
        sql = " ".join(call.args[0] for call in db.execute.call_args_list)
        self.assertIn("SELECT 1", sql)
        self.assertNotIn("FROM historical_price", sql)

    def test_automation_health_reports_stall_and_stale_discovery(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (None, None, 1)
        db.execute.return_value.fetchall.return_value = []
        result = function_app.automation_health(db)
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(len(result["issues"]), 3)

    def test_current_run_does_not_hide_overdue_recent_sources(self):
        from datetime import datetime, timezone

        db = MagicMock()
        now = datetime.now(timezone.utc)
        db.execute.return_value.fetchone.return_value = (now, now, 0)
        db.execute.return_value.fetchall.return_value = [
            ("city-zip", now, now.date(), 0, 7, 4)
        ]
        result = function_app.automation_health(db)
        self.assertEqual(result["status"], "degraded")
        self.assertIn("city-zip", result["issues"][0])

    def test_retained_replay_errors_are_visible_in_run_summary(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (True,)
        with (
            patch.object(worker, "connect") as connect,
            patch("pipelines.ingestion.queue_plan.daily_candidates", return_value=[]),
            patch(
                "pipelines.ingestion.queue_plan.backfill_candidates", return_value=[]
            ),
            patch("pipelines.ingestion.ocr.drain", return_value={}),
            patch(
                "pipelines.ingestion.retained_replays.drain",
                return_value={
                    "errors": [{"phase": "selection", "error": "statement timeout"}]
                },
            ) as replay,
        ):
            connect.return_value.__enter__.return_value = db
            result = worker.run("backfill", limit=4, time_budget=120)
        replay.assert_called_once()
        self.assertEqual(result["errors"][0]["source"], "retained_replay")
        final = [
            call
            for call in db.execute.call_args_list
            if call.args[0].startswith("UPDATE ingestion_run SET status=%s")
        ][-1]
        self.assertEqual(final.args[1][0], "partial")

    def test_daily_source_failure_keeps_progress_and_does_not_repeat_entire_run(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (True,)
        sources = [
            ("https://example.invalid/bad", "daily", None),
            ("https://example.invalid/good", "daily", None),
        ]
        with (
            patch.object(worker, "connect") as connect,
            patch.object(worker, "discover", return_value=[]),
            patch("pipelines.ingestion.official_sources.discover_roots"),
            patch(
                "pipelines.ingestion.queue_plan.daily_candidates", return_value=sources
            ),
            patch.object(
                worker,
                "process_asset",
                side_effect=[ValueError("Unsupported source layout"), 12],
            ),
            patch("pipelines.ingestion.ocr.drain", return_value={}),
            patch("pipelines.ingestion.retained_replays.drain", return_value={}),
        ):
            connect.return_value.__enter__.return_value = db
            summary = worker.run("daily", limit=2)
        self.assertEqual(summary["assets"], 1)
        self.assertEqual(summary["rows"], 12)
        self.assertEqual(len(summary["errors"]), 1)
        self.assertEqual(summary["phase"], "finished")
        self.assertNotIn("active_asset", summary)

    def test_checkpoint_deferral_is_ready_next_run_but_not_retried_in_same_run(self):
        from .resumable_inputs import WorkDeferred

        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (True,)
        source = ("https://example.invalid/resumable-input", "inputs-annex", None)
        failed = ("https://example.invalid/failed-input", "inputs-annex", None)
        with (
            patch.object(worker, "connect") as connect,
            patch.object(worker, "discover", return_value=[]),
            patch("pipelines.ingestion.official_sources.discover_roots"),
            patch(
                "pipelines.ingestion.queue_plan.daily_candidates",
                return_value=[source, source, failed],
            ) as candidates,
            patch.object(
                worker, "process_asset",
                side_effect=[WorkDeferred("Committed batches will resume"), ValueError("Invalid source")],
            ) as process,
            patch("pipelines.ingestion.ocr.drain", return_value={}),
            patch("pipelines.ingestion.retained_replays.drain", return_value={}),
        ):
            connect.return_value.__enter__.return_value = db
            summary = worker.run("daily", limit=4)
        # Both the duplicate initial candidate and the refreshed queue contain
        # this still-eligible URL. Neither may repeat its work in this run.
        self.assertEqual(candidates.call_count, 2)
        self.assertEqual([c.args[1] for c in process.call_args_list], [source[0], failed[0]])
        self.assertEqual(summary["assets"], 0)
        self.assertEqual(summary["rows"], 0)
        self.assertEqual(summary["deferred"], [{"url": source[0], "reason": "Committed batches will resume"}])
        self.assertEqual(len(summary["errors"]), 1)
        deferred = [c for c in db.execute.call_args_list if "SET status='pending',checked_at=now()-interval" in c.args[0]]
        self.assertEqual(len(deferred), 1)
        self.assertIn("interval '6 hours'", deferred[0].args[0])
        self.assertEqual(deferred[0].args[1], ("Committed batches will resume", source[0]))
        failures = [c for c in db.execute.call_args_list if "SET status=%s,attempts=attempts+1,checked_at=now()" in c.args[0]]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].args[1][0], "failed")
        self.assertEqual(failures[0].args[1][-1], failed[0])

    def test_overlap_is_durable_instead_of_silent(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (False,)
        with patch.object(worker, "connect") as connect:
            connect.return_value.__enter__.return_value = db
            self.assertEqual(worker.run("daily"), {"status": "skipped_overlap"})
        self.assertIn(
            "skipped_overlap", " ".join(c.args[0] for c in db.execute.call_args_list)
        )

    def test_discovery_failure_does_not_skip_other_sources(self):
        names = [
            "discover_special",
            "discover_monthly",
            "discover_price_daily",
            "discover_coffee",
            "discover_inputs",
            "discover_supply",
        ]
        mocks = {name: MagicMock() for name in names}
        mocks[names[0]].side_effect = ValueError("Publisher layout changed")
        with patch.multiple(worker, **mocks):
            errors = worker.discover(MagicMock())
        self.assertEqual(len(errors), 1)
        for operation in mocks.values():
            operation.assert_called_once()

    def test_official_revision_and_pdf_page_are_preserved(self):
        row = {
            "product_id": "cerdo",
            "product_name": "Cerdo",
            "category": "Porcinos",
            "publisher": "Porkcolombia / FNP",
            "series": "weekly",
            "basis": "Producer survey",
            "currency": "COP",
            "unit": "kg en pie",
            "market": "Colombia",
            "date": "2020-03-27",
            "price": 5298,
            "source_locator": "PDF page 3, row 1",
            "details": {"source_page": 3},
        }
        versions = []
        for adapter_version in ("fixture-v1", "fixture-v2"):
            db = MagicMock()
            with patch.object(colombia_sources, "VERSION", adapter_version):
                official_sources.publish_rows(db, [row], "a" * 64, "colombia-pork-pdf")
            value = db.cursor.return_value.copy.return_value.__enter__.return_value.write_row.call_args.args[
                0
            ]
            versions.append(value[2])
            self.assertEqual(value[18], 3)
        self.assertNotEqual(*versions)
        self.assertTrue(versions[0].endswith(":fixture-v1"))

    def test_review_revision_also_includes_adapter_version(self):
        db = MagicMock()
        row = {
            "source_locator": "row 7",
            "price": None,
            "details": {"quality_issue": "ambiguous source"},
        }
        official_sources.publish_rows(db, [row], "a" * 64, "colombia-agronet-cacao")
        value = (
            db.cursor.return_value.__enter__.return_value.executemany.call_args.args[1][
                0
            ]
        )
        self.assertEqual(value[2], worker.parser_version("colombia-agronet-cacao"))

    def test_shared_source_locator_cannot_silently_drop_market_cells(self):
        rows = [
            {
                "source_locator": "PDF page 2, row 7",
                "price": None,
                "market": market,
                "details": {"quality_issue": "ambiguous source"},
            }
            for market in ("Bogotá", "Antioquia")
        ]
        with self.assertRaisesRegex(ValueError, "Source locator maps"):
            official_sources.publish_rows(
                MagicMock(), rows, "a" * 64, "colombia-pork-pdf"
            )

    def test_native_titles_do_not_hide_failed_image_price_table(self):
        data = image_workbook()
        self.assertEqual(list(spreadsheet_images(data, failed_only=True)), [])
        self.assertEqual(
            len(
                list(
                    spreadsheet_images(
                        data, failed_only=True, normal_extraction_failed=True
                    )
                )
            ),
            1,
        )
        db = MagicMock()
        db.execute.return_value.fetchone.side_effect = [("a" * 64, data), (1,)]
        with patch("pipelines.ingestion.ocr.scan_document") as scan:
            self.assertTrue(
                worker.enqueue_failed_workbook(
                    db,
                    "https://example.invalid/prices.xlsx",
                    "inputs",
                    ValueError("No input price rows parsed"),
                )
            )
        self.assertTrue(scan.call_args.kwargs["normal_extraction_failed"])

    def test_image_scan_never_materializes_entire_worksheet_xml(self):
        data = image_workbook()
        original_read = zipfile.ZipFile.read

        def bounded_read(bundle, name, *args, **kwargs):
            if str(name).startswith("xl/worksheets/sheet") and str(name).endswith(
                ".xml"
            ):
                self.fail("OCR scanner loaded an entire worksheet XML")
            return original_read(bundle, name, *args, **kwargs)

        with patch.object(zipfile.ZipFile, "read", bounded_read):
            self.assertEqual(list(spreadsheet_images(data, failed_only=True)), [])
            self.assertEqual(
                len(
                    list(
                        spreadsheet_images(
                            data, failed_only=True, normal_extraction_failed=True
                        )
                    )
                ),
                1,
            )

    def test_semantic_date_failure_never_forces_ocr(self):
        db = MagicMock()
        self.assertFalse(
            worker.enqueue_failed_workbook(
                db,
                "https://example.invalid/prices.xlsx",
                "inputs",
                worker.SourceDateMismatch("No input price rows parsed"),
            )
        )
        db.execute.assert_not_called()

    def test_ocr_image_inherits_original_publisher(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (
            "https://porkcolombia.co/report.pdf",
            "Porkcolombia / FNP",
        )
        with patch.object(worker, "archive", return_value="b" * 64) as archive:
            self.assertTrue(
                enqueue_image(
                    db,
                    "a" * 64,
                    "PDF page 2",
                    Image.new("RGB", (800, 500)),
                    "colombia-pork-pdf",
                    2,
                )
            )
        self.assertEqual(
            archive.call_args.kwargs["publisher_override"], "Porkcolombia / FNP"
        )

    def test_release_identity_includes_http_status_and_host_code(self):
        self.assertIn("pipelines/ingestion/function_app.py", worker.RELEASE_FILES)
        self.assertIn("pipelines/ingestion/host.json", worker.RELEASE_FILES)
        self.assertEqual(len(worker.release_fingerprint()), 64)


if __name__ == "__main__":
    unittest.main()

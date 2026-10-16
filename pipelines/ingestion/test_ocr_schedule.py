"""OCR recovery must run even while ordinary historical assets fill each run."""

import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from . import function_app, worker


class OcrSchedule(unittest.TestCase):
    def test_awaiting_ocr_revalidation_uses_etag_and_keeps_unchanged_asset(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (
            '"first"', "Mon, 28 Sep 2026 00:00:00 GMT", "awaiting-ocr", "first-sha"
        )
        response = SimpleNamespace(status_code=304, close=Mock())
        with patch.object(worker.SESSION, "get", return_value=response) as get:
            self.assertIsNone(worker.fetch_asset(db, "https://example.invalid/price.pdf"))
        response.close.assert_called_once_with()
        self.assertEqual(get.call_args.kwargs["headers"], {"If-None-Match": '"first"'})
        self.assertIn("checked_at=now()", db.execute.call_args.args[0])

    def test_awaiting_ocr_changed_bytes_are_returned_for_native_reparse(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (
            '"first"', None, "awaiting-ocr", "first-sha"
        )
        response = SimpleNamespace(
            status_code=200, headers={"ETag": '"second"'}, content=b"revised original",
            raise_for_status=lambda: None, close=Mock(),
        )
        with patch.object(worker.SESSION, "get", return_value=response):
            self.assertEqual(
                worker.fetch_asset(db, "https://example.invalid/price.pdf"),
                b"revised original",
            )
        response.close.assert_called_once_with()
        self.assertEqual(db.execute.call_args.args[1][0], '"second"')

    def test_ocr_timer_has_independent_bounded_budget(self):
        with patch.object(function_app, "run", return_value={}) as run:
            function_app.ocr_recovery.build().get_user_function()(MagicMock())
        run.assert_called_once_with(
            "ocr", limit=0, time_budget=600, ocr_limit=2, ocr_scan_limit=1
        )

    def test_ocr_run_never_discovers_or_starts_large_native_assets(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (True,)
        with (
            patch.object(worker, "connect") as connect,
            patch.object(worker, "discover") as discover,
            patch.object(worker, "process_asset") as process,
            patch.object(worker, "refresh_trm") as trm,
            patch("pipelines.ingestion.queue_plan.daily_candidates") as fresh,
            patch("pipelines.ingestion.queue_plan.backfill_candidates") as backfill,
            patch("pipelines.ingestion.retained_replays.drain") as replay,
            patch(
                "pipelines.ingestion.ocr.drain", return_value={"completed": 1}
            ) as ocr,
        ):
            connect.return_value.__enter__.return_value = db
            result = worker.run(
                "ocr", limit=0, time_budget=600, ocr_limit=2, ocr_scan_limit=1
            )
        for method in (discover, process, trm, fresh, backfill, replay):
            method.assert_not_called()
        self.assertEqual(result["ocr"], {"completed": 1})
        self.assertEqual(ocr.call_args.kwargs["limit"], 2)
        self.assertIsNotNone(ocr.call_args.kwargs["deadline"])


class AuxiliaryScheduling(unittest.TestCase):
    def test_due_exchange_rates_and_seasonality_precede_historical_assets(self):
        db = MagicMock()

        def execute(sql, *args):
            result = MagicMock()
            result.fetchone.return_value = (
                None if "auxiliary_finished_at" in sql else (True,)
            )
            return result

        db.execute.side_effect = execute
        events = []
        with (
            patch.object(worker, "connect") as connect,
            patch.object(
                worker, "refresh_trm", side_effect=lambda db: events.append("trm") or 1
            ),
            patch.object(
                worker,
                "refresh_seasons",
                side_effect=lambda db: events.append("seasons"),
            ),
            patch.object(
                worker,
                "process_asset",
                side_effect=lambda *args: events.append("asset") or 1,
            ),
            patch(
                "pipelines.ingestion.queue_plan.daily_candidates",
                return_value=[("source", "daily", None)],
            ),
            patch("pipelines.ingestion.queue_plan.current_dane_candidates", return_value=[]),
            patch(
                "pipelines.ingestion.queue_plan.backfill_candidates", return_value=[]
            ),
            patch("pipelines.ingestion.queue_plan.supply_validation_retry", return_value=[]),
            patch("pipelines.ingestion.queue_plan.repair_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.historical_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.city_catchup_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.recent_pending_daily_pdf_candidates", return_value=[]),
            patch("pipelines.ingestion.city_product_backfill.drain", return_value={}),
            patch("pipelines.ingestion.retained_replays.drain", return_value={}),
            patch("pipelines.ingestion.ocr.drain", return_value={}),
        ):
            connect.return_value.__enter__.return_value = db
            result = worker.run("backfill", limit=1)
        self.assertEqual(events, ["trm", "seasons", "asset"])
        self.assertIn("auxiliary_finished_at", result)

    def test_hourly_city_scan_is_bounded_before_asset_backlog(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (True,)
        events = []
        with (
            patch.object(worker, "connect") as connect,
            patch.object(worker, "refresh_catalog", return_value={}),
            patch.object(worker, "process_asset", side_effect=lambda *args: events.append("asset") or 0),
            patch("pipelines.ingestion.queue_plan.daily_candidates", return_value=[("source", "daily", None)]),
            patch("pipelines.ingestion.queue_plan.current_dane_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.backfill_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.supply_validation_retry", return_value=[]),
            patch("pipelines.ingestion.queue_plan.repair_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.historical_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.city_catchup_candidates", return_value=[]),
            patch("pipelines.ingestion.queue_plan.recent_pending_daily_pdf_candidates", return_value=[]),
            patch("pipelines.ingestion.city_product_backfill.drain", side_effect=lambda *args, **kw: events.append("scan") or {"completed": 0}) as scan,
            patch("pipelines.ingestion.retained_replays.drain", return_value={}),
            patch("pipelines.ingestion.ocr.drain", return_value={}),
        ):
            connect.return_value.__enter__.return_value = db
            worker.run("backfill", limit=1)
            worker.run("ocr", limit=0, time_budget=600)
            worker.run("backfill", limit=1, time_budget=120)
        self.assertEqual(events, ["scan", "asset", "asset"])
        self.assertEqual(scan.call_count, 1)
        self.assertLessEqual(scan.call_args.kwargs["deadline"], time.monotonic() + 90)

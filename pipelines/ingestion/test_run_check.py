"""Authenticated source checks share the normal bounded checkpoint path."""

import unittest
from unittest.mock import patch

import azure.functions as func

from . import function_app


class RunCheckBudget(unittest.TestCase):
    def invoke(self, params):
        request = func.HttpRequest(
            method="POST", url="https://example.invalid/api/run-check",
            params=params, body=b"",
        )
        with patch.object(function_app, "run", return_value={}) as run:
            response = function_app.run_check.build().get_user_function()(request)
        return response, run

    def test_default_stays_bounded_and_has_no_provider_requests(self):
        response, run = self.invoke({})
        self.assertEqual(response.status_code, 200)
        run.assert_called_once_with(
            "backfill", limit=4, time_budget=120,
            ocr_limit=0, ocr_scan_limit=0, asset_url=None,
        )

    def test_large_original_uses_explicit_bounded_source_budget(self):
        url = "https://www.dane.gov.co/files/annual.xlsx"
        response, run = self.invoke({"asset_url": url, "time_budget": "1800"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(run.call_args.kwargs["time_budget"], 1800)
        self.assertEqual(run.call_args.kwargs["asset_url"], url)

    def test_invalid_or_unscoped_extended_budget_never_starts_work(self):
        for budget in ("0", "29", "2101", "-1", "1.5", "abc"):
            with self.subTest(budget=budget):
                response, run = self.invoke({"asset_url": "source", "time_budget": budget})
                self.assertEqual(response.status_code, 400)
                run.assert_not_called()
        response, run = self.invoke({"time_budget": "1800"})
        self.assertEqual(response.status_code, 400)
        run.assert_not_called()

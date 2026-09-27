"""Literal macroregion labels, paired OCR gates, and native chart parity."""

import json
import os
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pdfplumber

from . import milk_macroregions as milk
from . import ocr
from .test_ocr_budget import Database, Result

OLD = Path("artifacts/app-data-audit-2026-09-27/planning/milk-failed37")
CURRENT = Path(
    "artifacts/automation-audit-2026-09-26/dane/originals/bol-SIPSALeche-jul2026.pdf"
)
DECEMBER = OLD / "e38876f9f130dcb7fb0cc6562e8843d542eb8eff652ee3ac513fb1a4fd940727.pdf"
MAY = OLD / "5f69a7c090e47c649c35d99c1972a3a5ad32d87503e5bb612d91979e69c82179.pdf"


def reading():
    return {
        "text": "Gráfico 1. Comportamiento del precio promedio de la leche cruda en finca\n5 macrorregiones lecheras\nNoviembre y diciembre de 2025\nPrecio por litro\nNoviembre 2025 Diciembre 2025",
        "tables": [
            [
                ["Macrorregión", "Noviembre 2025", "Diciembre 2025"],
                ["Costa Caribe", "1.893", "1.930"],
                ["Antioquia y Eje Cafetero", "2.094", "2.113"],
                ["Boyacá y Cundinamarca", "2.102", "2.108"],
                ["Cauca, Nariño y Valle del Cauca", "1.971", "1.998"],
                ["Resto del país", "1.911", "1.922"],
            ]
        ],
        "review_notes": [],
    }


CHART = milk.Chart(
    1,
    date(2025, 12, 31),
    (date(2025, 11, 30), date(2025, 12, 31)),
    "noviembre y diciembre de 2025",
    "precio promedio de la leche cruda en finca",
    (0, 240, 612, 520),
)


class MilkMacroregionValidation(unittest.TestCase):
    def test_dequeue_rechecks_source_asset_date_and_document_review(self):
        cases = [
            ([], "no current validated"),
            ([(date(2025, 11, 30), "awaiting-ocr", None)], "archive date"),
            ([(date(2025, 12, 31), "review", "SourceDateMismatch")], "document review"),
            (
                [(date(2025, 12, 31), "failed", "No supported layout")],
                "document review",
            ),
        ]
        for assets, message in cases:
            db = MagicMock()
            db.execute.side_effect = [Result(one=(b"original",)), Result(many=assets)]
            with (
                self.subTest(assets=assets),
                patch.object(milk, "inspect", return_value=CHART),
                self.assertRaisesRegex(ValueError, message),
            ):
                milk.eligible_task(db, "doc", CHART.locator)
        db = MagicMock()
        db.execute.side_effect = [
            Result(one=(b"original",)),
            Result(many=[(CHART.report_month, "awaiting-ocr", None)]),
            Result(one=(1,)),
        ]
        with patch.object(milk, "inspect", return_value=CHART):
            self.assertEqual(milk.eligible_task(db, "doc", CHART.locator), CHART)
        db.execute.side_effect = [
            Result(one=(b"original",)),
            Result(many=[(CHART.report_month, "awaiting-ocr", None)]),
            Result(one=None),
        ]
        with (
            patch.object(milk, "inspect", return_value=CHART),
            self.assertRaisesRegex(ValueError, "validation checkpoint"),
        ):
            milk.eligible_task(db, "doc", CHART.locator)

    def test_all_ten_literals_have_region_month_litre_and_mean_identity(self):
        rows = milk.paired_rows(CHART, [reading(), reading()])
        self.assertEqual(len(rows), 10)
        self.assertEqual(
            [r["price"] for r in rows],
            [1893, 1930, 2094, 2113, 2102, 2108, 1971, 1998, 1911, 1922],
        )
        for row in rows:
            self.assertEqual(
                (row["currency"], row["unit"], row["series"]),
                ("COP", "litro", milk.SERIES),
            )
            self.assertEqual(row["category"], "Leche cruda en finca")
            self.assertEqual(row["details"]["statistic"], "published_mean")
            self.assertEqual(row["details"]["price_statistic"], "published_mean")
            self.assertEqual(row["details"]["period_type"], "monthly")
            self.assertEqual(row["details"]["period_end"], row["date"].isoformat())
            self.assertTrue(row["details"]["not_municipal"])
            self.assertEqual(row["source_page"], 1)
            self.assertEqual(row["period_start"].day, 1)

    def test_region_rows_are_bound_by_printed_name_not_position(self):
        second = reading()
        second["tables"][0][1:] = reversed(second["tables"][0][1:])
        self.assertEqual(
            milk.paired_rows(CHART, [reading(), second]),
            milk.parse_reading(CHART, reading()),
        )

    def test_two_identical_wrong_months_cannot_override_native_caption(self):
        wrong = reading()
        wrong["tables"][0][0][1:] = ["Diciembre 2025", "Noviembre 2025"]
        with self.assertRaisesRegex(ValueError, "legend columns"):
            milk.paired_rows(CHART, [wrong, wrong])
        wrong = reading()
        wrong["text"] = wrong["text"].replace("diciembre de 2025", "diciembre de 2024")
        with self.assertRaises(ValueError):
            milk.paired_rows(CHART, [wrong, wrong])

    def test_missing_unit_basis_month_region_value_or_uncertainty_fails(self):
        mutations = [
            lambda r: r.update(review_notes=["one label unclear"]),
            lambda r: r.update(text=r["text"].replace("Precio por litro", "")),
            lambda r: r["tables"][0][0].__setitem__(1, "Noviembre"),
            lambda r: r["tables"][0].pop(),
            lambda r: r["tables"][0][1].__setitem__(0, "Bolívar"),
            lambda r: r["tables"][0][2].__setitem__(0, "Costa Caribe"),
            lambda r: r["tables"][0][1].__setitem__(1, ""),
            lambda r: r["tables"][0][1].__setitem__(1, "1.?93"),
            lambda r: r["tables"][0][1].__setitem__(1, "1.89.3"),
            lambda r: r["tables"][0][1].__setitem__(1, "-1893"),
            lambda r: r["tables"].append([["extra unexplained chart"]]),
        ]
        for mutate in mutations:
            r = reading()
            mutate(r)
            with self.subTest(reading=r), self.assertRaises(ValueError):
                milk.paired_rows(CHART, [r, deepcopy(r)])
        with self.assertRaisesRegex(ValueError, "basis"):
            milk.parse_reading(replace(CHART, basis_evidence=""), reading())

    def test_independent_price_disagreement_is_never_published(self):
        second = reading()
        second["tables"][0][1][2] = "1.980"
        with self.assertRaisesRegex(ValueError, "disagree"):
            milk.paired_rows(CHART, [reading(), second])

    def test_colombian_thousands_and_literal_decimals(self):
        r = reading()
        r["tables"][0][1][1] = "1.893,25"
        row = milk.parse_reading(CHART, r)[0]
        self.assertEqual(row["price"], 1893.25)
        self.assertEqual(row["details"]["literal_price"], "1.893,25")
        for bad in ["1,893", "1.89", "1 893", "1893 pesos"]:
            r["tables"][0][1][1] = bad
            with self.assertRaises(ValueError):
                milk.parse_reading(CHART, r)

    def test_rollover_requires_explicit_first_year_and_consecutive_months(self):
        months, _ = milk._caption_months("Diciembre de 2024 y enero de 2025")
        self.assertEqual(months, (date(2024, 12, 31), date(2025, 1, 31)))
        for bad in ["Diciembre y enero de 2025", "Octubre y diciembre de 2025"]:
            with self.assertRaises(ValueError):
                milk._caption_months(bad)

    def test_specialized_prompt_requests_literal_labels_without_bar_estimates(self):
        response = MagicMock(ok=True, status_code=200)
        response.json.return_value = {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": json.dumps(reading())}]},
                }
            ]
        }
        with patch.object(ocr.requests, "post", return_value=response) as post:
            ocr.transcribe(b"fixture", key="test-only", source_kind=milk.KIND)
        prompt = post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
        self.assertIn("all FIVE named regions", prompt)
        self.assertIn("Do not estimate bar heights", prompt)
        self.assertNotIn("test-only", post.call_args.args[0])


class ChartDatabase(Database):
    def __init__(self, readings):
        super().__init__(40, ())
        self.readings, self.updates = readings, []

    def execute(self, sql, params=()):
        if sql.startswith("SELECT document_id,source_locator,image_id"):
            return Result(many=[("doc", CHART.locator, "image", milk.KIND, 1)])
        if sql.startswith("SELECT result FROM source_ocr_result"):
            return Result(one=(self.readings[params[2]],))
        if sql.startswith("UPDATE source_ocr_task"):
            self.updates.append(params)
        return super().execute(sql, params)


class MilkMacroregionDrain(unittest.TestCase):
    def run_chart(self, readings, eligible=True):
        db = ChartDatabase(readings)
        with (
            patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "test-only", "GEMINI_OCR_DAILY_REQUESTS": "40"},
            ),
            patch.object(
                milk,
                "eligible_task",
                return_value=CHART if eligible else None,
                side_effect=None
                if eligible
                else ValueError("Native equivalent is now available"),
            ),
            patch.object(milk, "publish_readings", return_value=10) as publish,
            patch.object(ocr, "transcribe") as provider,
            patch.object(ocr, "_finalize_milk_task") as finalize,
        ):
            result = ocr.drain(db, limit=1, scan_limit=0)
        finalize.assert_called_once_with(db, "doc", milk.KIND)
        return result, db, publish, provider

    def test_cached_pair_publishes_at_request_cap_without_provider(self):
        result, db, publish, provider = self.run_chart([reading(), reading()])
        self.assertEqual((result["processed"], result["review"]), (1, 0))
        publish.assert_called_once()
        provider.assert_not_called()
        self.assertEqual(db.updates[-1][0], "published")

    def test_disagreement_retains_review_and_never_publishes(self):
        second = reading()
        second["tables"][0][1][1] = "1.983"
        result, db, publish, provider = self.run_chart([reading(), second])
        self.assertEqual(result["review"], 1)
        self.assertIn("disagree", db.updates[-1][0])
        publish.assert_not_called()
        provider.assert_not_called()

    def test_native_equivalent_recheck_prevents_any_provider_or_publication(self):
        result, _db, publish, provider = self.run_chart(
            [reading(), reading()], eligible=False
        )
        self.assertEqual(result["review"], 1)
        publish.assert_not_called()
        provider.assert_not_called()


@unittest.skipUnless(
    CURRENT.exists() and DECEMBER.exists() and MAY.exists(),
    "Retained official PDF fixtures required",
)
class RealMilkMacroregionOriginals(unittest.TestCase):
    def test_native_color_legend_not_bar_position_assigns_month(self):
        chart = milk.inspect(MAY.read_bytes())
        with pdfplumber.open(MAY) as pdf:
            page = pdf.pages[0]
            rectangles = deepcopy(page.rects)
            legends = [
                r
                for r in rectangles
                if 490 < r["top"] < 493 and 3 < r["x1"] - r["x0"] < 12
            ]
            self.assertEqual(len(legends), 2)
            legends[0]["non_stroking_color"], legends[1]["non_stroking_color"] = (
                legends[1]["non_stroking_color"],
                legends[0]["non_stroking_color"],
            )
            vector = MagicMock(rects=rectangles, chars=page.chars)
            vector.search.side_effect = page.search
            vector.extract_words.return_value = page.extract_words()
            vector.extract_text.return_value = page.extract_text()
            swapped = milk.parse_reading(
                chart,
                milk._native_chart_reading(vector, chart),
                method="native-pdf-chart-label-geometry",
            )
        self.assertEqual([r["price"] for r in swapped][:2], [2057, 2038])

    def test_missing_native_numeric_label_is_review_not_image_fallback(self):
        chart = milk.inspect(MAY.read_bytes())
        with pdfplumber.open(MAY) as pdf:
            page = pdf.pages[0]
            vector = MagicMock(rects=page.rects, chars=page.chars)
            vector.search.side_effect = page.search
            vector.extract_words.return_value = [
                w for w in page.extract_words() if w["text"] != "2.132"
            ]
            vector.extract_text.return_value = page.extract_text()
            with self.assertRaisesRegex(ValueError, "unique printed numeric label"):
                milk._native_chart_reading(vector, chart)

    def test_existing_municipal_prices_remain_exactly_unchanged(self):
        from .special_prices import parse_milk_pdf

        count = 0
        targets = json.loads((OLD / "replay-ready.json").read_text())
        for target in targets:
            if target["expected_outcome"] != "native-prices":
                continue
            path = OLD / (target["document_id"] + ".pdf")
            old = json.loads(path.with_name(path.stem + "-parsed.json").read_text())
            current = list(
                parse_milk_pdf(path.read_bytes(), date.fromisoformat(target["date"]))
            )
            self.assertEqual(
                json.loads(json.dumps(current, default=str)), old, target["url"]
            )
            count += len(current)
        self.assertEqual(count, 3952)

    def test_july_and_december_raster_charts_have_verified_native_failure(self):
        for path, months in [
            (CURRENT, (date(2026, 6, 30), date(2026, 7, 31))),
            (DECEMBER, CHART.months),
        ]:
            with self.subTest(path=path):
                chart = milk.inspect(path.read_bytes())
                self.assertEqual(chart.months, months)
                self.assertIsNotNone(chart.bbox)
                self.assertFalse(chart.native_rows)
        with self.assertRaisesRegex(ValueError, "archive date"):
            milk.inspect(CURRENT.read_bytes(), date(2026, 6, 30))

    def test_may_native_chart_all_ten_values_match_independent_visual_oracle(self):
        expected = [2038, 2057, 2132, 2136, 2134, 2145, 2004, 1983, 1908, 1909]
        with patch.object(ocr, "enqueue_image") as queue:
            chart = milk.enqueue(None, MAY.read_bytes(), "fixture")
        queue.assert_not_called()
        self.assertIsNone(chart.bbox)
        self.assertEqual([r["price"] for r in chart.native_rows], expected)
        self.assertEqual(
            [r["market"] for r in chart.native_rows][::2], list(milk.REGIONS)
        )
        self.assertTrue(
            all(r["details"]["native_label_binding"] for r in chart.native_rows)
        )
        self.assertTrue(
            all(
                r["details"]["extraction_method"] == "native-pdf-chart-label-geometry"
                for r in chart.native_rows
            )
        )

    def test_eighteen_prior_originals_keep_dates_and_native_equivalence(self):
        targets = [
            r
            for r in json.loads((OLD / "results.json").read_text())
            if "2025" in r["url"] or "2026" in r["url"]
        ]
        self.assertEqual(len(targets), 18)
        charts = [
            milk.inspect((OLD / (r["document_id"] + ".pdf")).read_bytes())
            for r in targets
        ]
        self.assertEqual(sum(bool(c.native_rows) for c in charts), 1)
        self.assertEqual(sum(c.bbox is not None for c in charts), 17)
        self.assertEqual(charts[0].months, (date(2024, 12, 31), date(2025, 1, 31)))


if __name__ == "__main__":
    unittest.main()

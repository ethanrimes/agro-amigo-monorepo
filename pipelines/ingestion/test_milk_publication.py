"""Composite milk publication: native parity, bounded OCR and durable totals."""

import os
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from . import milk_macroregions as macro, milk_publication as publication, worker
from . import official_catalog
from .special_prices import MilkNarrativeOnly
from .test_milk_macroregions import CHART, reading, DECEMBER, MAY, CURRENT
from . import test_special_projection as projection_tests

milk = projection_tests.milk


class MilkPublicationVersion(unittest.TestCase):
    def test_composite_version_and_release_include_both_independent_parsers(self):
        self.assertEqual(
            worker.parser_version("milk-pdf"), "milk-pdf-v7:" + macro.VERSION
        )
        self.assertEqual(worker.parser_version(macro.KIND), macro.VERSION)
        for filename in ("milk_macroregions.py", "milk_publication.py"):
            self.assertIn("pipelines/ingestion/" + filename, worker.RELEASE_FILES)


@unittest.skipUnless(
    os.environ.get("AGRO_MILK_PUBLICATION_POSTGRES_TEST") == "1",
    "Explicit isolated PostgreSQL opt-in",
)
class MilkPublicationPostgres(unittest.TestCase):
    original = projection_tests.SpecialProjectionPostgresTests.original
    prices = projection_tests.SpecialProjectionPostgresTests.prices
    count = projection_tests.SpecialProjectionPostgresTests.count

    def setUp(self):
        projection_tests.SpecialProjectionPostgresTests.setUp(self)
        self.db.execute("""
          CREATE TEMP TABLE official_price_quote(LIKE public.official_price_quote INCLUDING ALL);
          CREATE TEMP TABLE official_source_review(LIKE public.official_source_review INCLUDING ALL);
          CREATE TEMP TABLE official_catalog_current(quote_key text PRIMARY KEY,payload jsonb,
            dirty boolean NOT NULL DEFAULT true,version text NOT NULL DEFAULT '',refreshed_at timestamptz);
          CREATE TEMP TABLE ingestion_checkpoint(document_id text,processor_version text,step text,records bigint,
            completed_at timestamptz DEFAULT now(),PRIMARY KEY(document_id,processor_version,step));
          CREATE TEMP TABLE source_ocr_task(document_id text,source_locator text,source_kind text,
            status text DEFAULT 'pending',error text,checked_at timestamptz,
            PRIMARY KEY(document_id,source_locator));
          CREATE TEMP TABLE price_observation_review(
            document_id text,source_locator text,product_id text,market_id text,source_id text,
            observed_on date,period text,unit text,reason text,evidence jsonb,
            PRIMARY KEY(document_id,source_locator,product_id,market_id,source_id,observed_on,period,unit));
        """)
        self.did, self.url = self.original(
            "milk-composite", [], media="application/pdf"
        )
        self.day = CHART.report_month
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,document_id,observed_on,status,processor_version) "
            "VALUES(%s,'milk-pdf',%s,%s,'pending','milk-pdf-v7')",
            (self.url, self.did, self.day),
        )
        self.rows = [
            milk(day=self.day, locator="PDF page 3,col 1,line 3; parser milk-pdf-v7"),
            milk(
                2050,
                town="Sonsón",
                day=self.day,
                locator="PDF page 3,col 1,line 4; parser milk-pdf-v7",
            ),
        ]
        self.chart_rows = tuple(
            macro.parse_reading(CHART, reading(), method="native-pdf-table")
        )
        self.native_chart = replace(CHART, native_rows=self.chart_rows, bbox=None)
        self.refresh_states = []
        actual_refresh = official_catalog.refresh_document

        def refresh(db, did):
            state = db.execute(
                "SELECT status FROM ingestion_asset WHERE document_id=%s", (did,)
            ).fetchone()[0]
            self.refresh_states.append(state)
            return actual_refresh(db, did)

        self.enterContext(
            patch(
                "pipelines.ingestion.official_catalog.refresh_document",
                side_effect=refresh,
            )
        )
        token = worker.RUN_DEADLINE.set(None)
        self.addCleanup(worker.RUN_DEADLINE.reset, token)

    def state(self):
        return self.db.execute(
            "SELECT status,records,error FROM ingestion_asset WHERE url=%s", (self.url,)
        ).fetchone()

    def run_publication(self, chart, rows=None):
        with (
            patch(
                "pipelines.ingestion.special_prices.parse_milk_pdf",
                return_value=iter(self.rows if rows is None else rows),
            ),
            patch.object(macro, "inspect", return_value=chart),
        ):
            return publication.publish(self.db, b"native", self.did, self.url, self.day)

    def task(self, status="pending"):
        self.db.execute(
            "INSERT INTO source_ocr_task(document_id,source_locator,source_kind,status) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (self.did, CHART.locator, macro.KIND, status),
        )
        return CHART

    def test_native_rows_preserve_municipal_bytes_and_independent_ten_chart_rows(self):
        with (
            patch.object(macro, "enqueue") as enqueue,
            patch("pipelines.ingestion.ocr.scan_document") as generic,
        ):
            self.assertEqual(self.run_publication(self.native_chart), 12)
            self.assertEqual(self.run_publication(self.native_chart), 12)
        enqueue.assert_not_called()
        generic.assert_not_called()
        retained = self.db.execute(
            "SELECT source_locator,series,observed_on,product_name,market_name,unit,price,change_percent,details FROM historical_price ORDER BY source_locator"
        ).fetchall()
        self.assertEqual(retained, self.rows)
        self.assertEqual(self.count("price_observation"), 2)
        self.assertEqual(self.count("official_price_quote"), 10)
        self.assertEqual(self.state(), ("complete", 12, None))
        self.assertEqual(
            self.db.execute(
                "SELECT DISTINCT series,unit,market FROM official_price_quote ORDER BY market"
            ).fetchall(),
            [(macro.SERIES, "litro", r) for r in sorted(macro.REGIONS)],
        )
        self.assertTrue(self.refresh_states)
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM official_catalog_current WHERE payload IS NOT NULL"
            ).fetchone()[0],
            5,
        )

    def test_narrative_can_publish_native_chart_without_municipal_rows(self):
        with (
            patch(
                "pipelines.ingestion.special_prices.parse_milk_pdf",
                side_effect=MilkNarrativeOnly("native"),
            ),
            patch.object(macro, "inspect", return_value=self.native_chart),
            patch.object(macro, "enqueue") as enqueue,
        ):
            self.assertEqual(
                publication.publish(self.db, b"native", self.did, self.url, self.day),
                10,
            )
        enqueue.assert_not_called()
        self.assertEqual(self.count("historical_price"), 0)
        self.assertEqual(self.state(), ("complete", 10, None))

    def test_no_chart_narrative_remains_processed_and_never_ocr(self):
        with patch.object(macro, "enqueue") as enqueue:
            self.assertEqual(self.run_publication(None, []), 0)
        enqueue.assert_not_called()
        self.assertEqual(self.state()[0:2], ("processed", 0))
        self.assertIn("Native narrative", self.state()[2])

    def test_pending_then_success_counts_both_sets_once(self):
        with patch.object(macro, "enqueue", side_effect=lambda *a: self.task()):
            self.assertEqual(self.run_publication(CHART), 2)
        self.assertEqual(self.state()[0:2], ("awaiting-ocr", 2))
        # Real paired-reader validation and publisher; no provider or archive call.
        with patch.object(macro, "inspect", return_value=CHART):
            self.assertEqual(
                macro.publish_readings(
                    self.db,
                    self.did,
                    CHART.locator,
                    "retained-image",
                    [reading(), reading()],
                ),
                10,
            )
        self.db.execute("UPDATE source_ocr_task SET status='published'")
        for _ in range(2):
            self.assertEqual(
                publication.finalize_macroregion_publication(self.db, self.did, 999), 12
            )
        self.assertEqual(self.state(), ("complete", 12, None))
        self.assertEqual(self.count("official_price_quote"), 10)
        self.assertEqual(self.count("price_observation"), 2)

    def test_chart_review_does_not_withdraw_valid_municipal_prices(self):
        with patch.object(macro, "enqueue", side_effect=lambda *a: self.task()):
            self.run_publication(CHART)
        self.db.execute(
            "UPDATE source_ocr_task SET status='review',error='readings disagree'"
        )
        self.assertEqual(
            publication.finalize_macroregion_publication(self.db, self.did), 2
        )
        self.assertEqual(self.state()[0:2], ("complete", 2))
        self.assertIn("retained for review", self.state()[2])
        self.assertEqual(self.count("price_observation"), 2)
        self.assertEqual(self.count("official_price_quote"), 0)

    def test_unsupported_native_binding_is_chart_review_not_generic_ocr(self):
        with (
            patch(
                "pipelines.ingestion.special_prices.parse_milk_pdf",
                return_value=iter(self.rows),
            ),
            patch.object(
                macro,
                "inspect",
                side_effect=ValueError("Native chart legend uncertain"),
            ),
            patch.object(macro, "enqueue") as enqueue,
        ):
            self.assertEqual(
                publication.publish(self.db, b"native", self.did, self.url, self.day), 2
            )
        enqueue.assert_not_called()
        self.assertEqual(self.count("official_source_review"), 1)
        self.assertEqual(self.state()[0:2], ("complete", 2))
        self.assertIn("review", self.state()[2])

    def test_date_conflict_cannot_publish_either_chart_month_from_cached_readings(self):
        self.db.execute(
            "UPDATE ingestion_asset SET status='review',observed_on=%s",
            (date(2025, 10, 31),),
        )
        publication._checkpoint(self.db, self.did, publication.MUNICIPAL_STEP, 0)
        self.task()
        with (
            patch.object(macro, "inspect", return_value=CHART),
            self.assertRaisesRegex(ValueError, "document review"),
        ):
            macro.publish_readings(
                self.db, self.did, CHART.locator, "image", [reading(), reading()]
            )
        self.assertIsNone(
            publication.finalize_macroregion_publication(self.db, self.did, 10)
        )
        self.assertEqual(self.state()[0], "review")
        self.assertEqual(self.count("official_price_quote"), 0)
        self.assertEqual(self.refresh_states, ["review"])

    def test_previous_chart_review_hides_exact_old_rows_and_next_version_recovers(self):
        self.run_publication(self.native_chart)
        with (
            patch.object(macro, "VERSION", "milk-macroregions-v2"),
            patch(
                "pipelines.ingestion.special_prices.parse_milk_pdf",
                return_value=iter(self.rows),
            ),
            patch.object(
                macro, "inspect", side_effect=ValueError("Native legend ambiguity")
            ),
        ):
            self.assertEqual(
                publication.publish(self.db, b"native", self.did, self.url, self.day), 2
            )
        self.assertEqual(self.count("official_price_quote"), 10)
        self.assertEqual(self.count("price_observation"), 2)
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM official_catalog_current WHERE payload IS NOT NULL"
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM official_source_review WHERE source_locator LIKE 'PDF page 1, chart 1, region %%'"
            ).fetchone()[0],
            10,
        )
        with patch.object(macro, "VERSION", "milk-macroregions-v3"):
            self.assertEqual(self.run_publication(self.native_chart), 12)
        self.assertEqual(self.count("official_price_quote"), 20)
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM official_catalog_current WHERE payload IS NOT NULL"
            ).fetchone()[0],
            5,
        )

    def test_ocr_disagreement_withdraws_prior_chart_not_municipal_siblings(self):
        self.run_publication(self.native_chart)
        with patch.object(macro, "VERSION", "milk-macroregions-v2"):
            publication._checkpoint(self.db, self.did, publication.MUNICIPAL_STEP, 2)
            self.db.execute(
                "INSERT INTO source_ocr_task(document_id,source_locator,source_kind,status,error) VALUES(%s,%s,%s,'review','Independent readings disagree')",
                (self.did, CHART.locator, macro.KIND),
            )
            self.assertEqual(
                publication.finalize_macroregion_publication(self.db, self.did), 2
            )
        self.assertEqual(self.state()[0:2], ("complete", 2))
        self.assertEqual(self.count("price_observation"), 2)
        self.assertEqual(self.count("official_price_quote"), 10)
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM official_catalog_current WHERE payload IS NOT NULL"
            ).fetchone()[0],
            0,
        )

    def test_date_failure_before_publication_and_outer_rollback_preserve_original(self):
        with (
            patch(
                "pipelines.ingestion.special_prices.parse_milk_pdf",
                return_value=iter(self.rows),
            ),
            patch.object(
                macro, "inspect", side_effect=worker.SourceDateMismatch("wrong month")
            ),
            self.assertRaises(worker.SourceDateMismatch),
        ):
            publication.publish(self.db, b"native", self.did, self.url, self.day)
        self.assertEqual(self.count("historical_price"), 0)
        with self.assertRaisesRegex(RuntimeError, "caller rollback"):
            with self.db.transaction():
                self.run_publication(self.native_chart)
                raise RuntimeError("caller rollback")
        for table in (
            "historical_price",
            "official_price_quote",
            "price_observation",
            "ingestion_checkpoint",
        ):
            self.assertEqual(self.count(table), 0)
        self.assertEqual(self.count("source_document"), 1)

    def test_later_document_date_review_withdraws_both_old_chart_months(self):
        self.run_publication(self.native_chart)
        self.db.execute(
            "UPDATE ingestion_asset SET status='review',observed_on=%s",
            (date(2025, 12, 31),),
        )
        self.assertIsNone(
            publication.finalize_macroregion_publication(self.db, self.did)
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM official_catalog_current WHERE payload IS NOT NULL"
            ).fetchone()[0],
            0,
        )
        self.assertEqual(self.count("official_price_quote"), 10)
        self.assertEqual(self.count("official_source_review"), 10)
        self.assertEqual(self.state()[0], "review")

    def test_processing_date_conflict_quarantines_prior_month_before_raising(self):
        self.run_publication(self.native_chart)
        with (
            patch(
                "pipelines.ingestion.special_prices.parse_milk_pdf",
                return_value=iter(self.rows),
            ),
            patch.object(
                macro,
                "inspect",
                side_effect=worker.SourceDateMismatch("Archive date differs"),
            ),
            self.assertRaises(worker.SourceDateMismatch),
        ):
            publication.publish(self.db, b"native", self.did, self.url, self.day)
        self.assertEqual(self.state()[0], "review")
        self.assertEqual(self.count("official_price_quote"), 10)
        self.assertEqual(self.count("official_source_review"), 10)
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM official_catalog_current WHERE payload IS NOT NULL"
            ).fetchone()[0],
            0,
        )

    def test_unknown_municipal_grid_is_separate_review_while_native_chart_publishes(
        self,
    ):
        with (
            patch(
                "pipelines.ingestion.special_prices.parse_milk_pdf",
                side_effect=ValueError("No milk PDF price rows parsed"),
            ),
            patch.object(macro, "inspect", return_value=self.native_chart),
            patch.object(
                publication,
                "_municipal_coverage",
                return_value=(False, [{"page": 3, "municipal_grid_heading": True}]),
            ),
        ):
            self.assertEqual(
                publication.publish(self.db, b"native", self.did, self.url, self.day),
                10,
            )
        self.assertEqual(self.count("historical_price"), 0)
        self.assertEqual(self.count("official_source_review"), 1)
        self.assertEqual(self.state()[0:2], ("complete", 10))
        self.assertIn(
            "Municipal extraction remains under separate review", self.state()[2]
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM official_catalog_current WHERE payload IS NOT NULL"
            ).fetchone()[0],
            5,
        )

    def test_worker_upgrade_reprocesses_each_old_terminal_or_ocr_state(self):
        for status in ("complete", "processed", "review", "awaiting-ocr"):
            self.db.execute(
                "UPDATE ingestion_asset SET status=%s,processor_version='milk-pdf-v7'",
                (status,),
            )
            with (
                patch.object(worker, "fetch_asset", return_value=b"native") as fetch,
                patch.object(worker, "archive", return_value=self.did),
                patch("pipelines.ingestion.pdf_sources.extract_pages"),
                patch(
                    "pipelines.ingestion.special_prices.parse_milk_pdf",
                    return_value=iter(self.rows),
                ),
                patch.object(macro, "inspect", return_value=self.native_chart),
            ):
                self.assertEqual(
                    worker.process_asset(self.db, self.url, "milk-pdf", self.day), 12
                )
            self.assertTrue(fetch.call_args.kwargs["force"])
            self.assertEqual(self.state(), ("complete", 12, None))
            self.assertEqual(
                self.db.execute(
                    "SELECT processor_version FROM ingestion_asset"
                ).fetchone()[0],
                worker.parser_version("milk-pdf"),
            )
        self.assertEqual(self.count("official_price_quote"), 10)
        self.assertEqual(self.count("historical_price"), 2)

    def actual_report(self, path, day, expected, pending):
        body = path.read_bytes()
        self.db.execute(
            "UPDATE source_document SET content=%s WHERE id=%s", (body, self.did)
        )
        self.db.execute("UPDATE ingestion_asset SET observed_on=%s", (day,))
        images = []

        def retained_crop(db, did, locator, image, kind, page):
            images.append((locator, image.size, kind, page))
            db.execute(
                "INSERT INTO source_ocr_task(document_id,source_locator,source_kind) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                (did, locator, kind),
            )
            return True

        with (
            patch.object(worker, "fetch_asset", return_value=body),
            patch.object(worker, "archive", return_value=self.did),
            patch("pipelines.ingestion.pdf_sources.extract_pages"),
            patch("pipelines.ingestion.ocr.enqueue_image", side_effect=retained_crop),
            patch("pipelines.ingestion.ocr.scan_document") as generic,
        ):
            self.assertEqual(
                worker.process_asset(self.db, self.url, "milk-pdf", day), expected
            )
        generic.assert_not_called()
        self.assertEqual(
            self.db.execute(
                "SELECT content FROM source_document WHERE id=%s", (self.did,)
            ).fetchone()[0],
            body,
        )
        self.assertEqual(self.state()[0], "awaiting-ocr" if pending else "complete")
        self.assertEqual(len(images), 1 if pending else 0)
        if pending:
            self.assertEqual(images[0][2:], (macro.KIND, 1))
            self.assertGreater(images[0][1][0], 240)
            self.assertIn("isolated macroregion chart", self.state()[2])
        return body

    @unittest.skipUnless(DECEMBER.exists(), "Retained December2025 original required")
    def test_actual_december2025_chart_only_queues_one_crop(self):
        body = self.actual_report(DECEMBER, date(2025, 12, 31), 0, True)
        self.assertTrue(publication._municipal_coverage(body)[0])
        self.assertEqual(self.count("historical_price"), 0)
        self.assertEqual(self.count("official_source_review"), 0)

    @unittest.skipUnless(CURRENT.exists(), "Retained July2026 original required")
    def test_actual_july2026_native_narrative_queues_only_chart(self):
        self.actual_report(CURRENT, date(2026, 7, 31), 0, True)
        self.assertEqual(self.count("historical_price"), 0)

    @unittest.skipUnless(MAY.exists(), "Retained May2026 original required")
    def test_actual_may2026_native_labels_publish_ten_without_ocr(self):
        self.actual_report(MAY, date(2026, 5, 31), 10, False)
        self.assertEqual(self.count("official_price_quote"), 10)
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM official_catalog_current WHERE payload IS NOT NULL"
            ).fetchone()[0],
            5,
        )

    @unittest.skipUnless(
        Path("artifacts/official-sources/milk-2014-aug-bulletin.pdf").exists(),
        "Retained August2014 original required",
    )
    def test_actual_2014_municipal_rows_keep_every_native_field_and_locator(self):
        from .special_prices import parse_milk_pdf

        body = Path(
            "artifacts/official-sources/milk-2014-aug-bulletin.pdf"
        ).read_bytes()
        expected = list(parse_milk_pdf(body, date(2014, 8, 31)))
        self.assertEqual(len(expected), 183)
        self.db.execute(
            "UPDATE ingestion_asset SET observed_on=%s", (date(2014, 8, 31),)
        )
        with patch.object(macro, "enqueue") as enqueue:
            self.assertEqual(
                publication.publish(
                    self.db, body, self.did, self.url, date(2014, 8, 31)
                ),
                183,
            )
        enqueue.assert_not_called()
        actual = self.db.execute(
            "SELECT source_locator,series,observed_on,product_name,market_name,unit,price,change_percent,details FROM historical_price ORDER BY source_locator"
        ).fetchall()
        self.assertEqual(actual, sorted(expected, key=lambda r: r[0]))
        self.assertEqual(self.count("price_observation"), 183)
        self.assertEqual(self.count("official_price_quote"), 0)
        self.assertEqual(self.state(), ("complete", 183, None))


if __name__ == "__main__":
    unittest.main()

"""Exact source presentation follows its guarded revision, not an older spelling."""

import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from . import inputs, pdf_sources, worker
from .test_input_pdf_publication import InputPDFPublication, synthetic_pdf_publication_version


@unittest.skipUnless(
    os.environ.get("AGRO_INPUT_PDF_PUBLICATION_POSTGRES_TEST") == "1",
    "Explicit TEMP-only PostgreSQL opt-in",
)
class InputPresentationRevision(unittest.TestCase):
    def setUp(self):
        InputPDFPublication.setUp(self)
        self.db.execute("INSERT INTO source_document VALUES('mid','2026-09-02')")

    def publish(self, did, presentation, price="11167", *, pdf=False, version=None):
        version = version or pdf_sources.INPUT_PDF_VERSION
        rows = []
        for municipal in (False, True):
            meta = {
                "sheet": "pdf" if pdf else "1.2",
                "category": "Antibióticos, antimicóticos y antiparasitarios",
                "presentation": presentation,
                "department": "Quindío",
                "municipality": "Armenia" if municipal else "",
                "brand": "",
                "ica": "",
                "parser_version": version if pdf else "inputs-v4",
            }
            rows.append(
                worker.record(
                    "dane-inputs-pdf"
                    if pdf
                    else "dane-inputs-municipal"
                    if municipal
                    else "dane-inputs",
                    date(2016, 2, 29),
                    "Benzetacil LA",
                    meta["municipality"] or "Quindío",
                    presentation,
                    Decimal(price),
                    f"PDF page {62 if municipal else 61},col 1,y 603.3; {version}"
                    if pdf
                    else f"1.2!row {2 if municipal else 1}",
                    details=meta,
                )
            )
        with (
            synthetic_pdf_publication_version(version),
            self.db.transaction(),
        ):
            worker.save_rows(self.db, did, rows)
            if pdf:
                inputs.project_pdf_inputs(self.db, did)
            else:
                inputs.project_inputs(self.db, did)

    def assert_current(self, did, presentation, price="11167", locator_suffix=None):
        for table in ("input_price", "input_municipal_price"):
            rows = self.db.execute(
                f"SELECT id,price,presentation,document_id,source_locator FROM published_{table}"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            key, actual_price, actual_presentation, actual_did, locator = rows[0]
            self.assertEqual(key, "benzetacil-la-3-m-u-i")
            self.assertEqual(
                (actual_price, actual_presentation, actual_did),
                (Decimal(price), presentation, did),
            )
            if locator_suffix:
                self.assertTrue(locator.endswith(locator_suffix), locator)

    def test_equal_price_newer_source_updates_exact_presentation_and_retains_raw(self):
        self.publish("old", "3 M.U.I.")
        before = self.db.execute(
            "SELECT md5(to_jsonb(h)::text) FROM historical_price h"
        ).fetchall()
        self.publish("new", "3 M. U. I.")
        self.assert_current("new", "3 M. U. I.")
        after = self.db.execute(
            "SELECT md5(to_jsonb(h)::text) FROM historical_price h"
        ).fetchall()
        self.assertTrue(set(before) <= set(after))
        self.assertEqual(len(after), 4)
        self.assertTrue(
            self.db.execute(
                "SELECT bool_and((retrieved_at AT TIME ZONE 'UTC')::date=DATE '2026-09-03') FROM input_revision"
            ).fetchone()[0]
        )
        attempts = self.db.execute("SELECT count(*) FROM input_attempt").fetchone()[0]
        self.publish("new", "3 M. U. I.")
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM input_attempt").fetchone()[0],
            attempts,
        )

    def test_same_original_new_pdf_parser_spelling_updates_with_checkpoint(self):
        self.publish("old", "3 M.U.I.", pdf=True, version="inputs-pdf-v7")
        self.publish("old", "3 M. U. I.", pdf=True, version="inputs-pdf-v8")
        self.assert_current("old", "3 M. U. I.", locator_suffix="inputs-pdf-v8")
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 4
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM ingestion_checkpoint WHERE step='inputs-pdf:published'"
            ).fetchone()[0],
            2,
        )
        # A rollback to an old parser must neither revert labels nor remove rows.
        self.publish("old", "3 M.U.I.", pdf=True, version="inputs-pdf-v7")
        self.assert_current("old", "3 M. U. I.", locator_suffix="inputs-pdf-v8")

    def test_older_source_cannot_replace_new_presentation_even_with_changed_value(self):
        self.publish("new", "3 M. U. I.")
        self.publish("old", "3 M.U.I.")
        self.publish("mid", "3 M.U.I.", "11000")
        self.assert_current("new", "3 M. U. I.")
        self.assertTrue(
            self.db.execute(
                "SELECT bool_and((retrieved_at AT TIME ZONE 'UTC')::date=DATE '2026-09-03') FROM input_revision"
            ).fetchone()[0]
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 6
        )

    def test_later_rounded_pdf_still_cannot_replace_structured_precision(self):
        self.publish("old", "3 M. U. I.", "11166.66666666667")
        self.publish("new", "3 M. U. I.", "11167", pdf=True)
        self.assert_current("old", "3 M. U. I.", "11166.66666666667")
        self.assertTrue(
            self.db.execute(
                "SELECT bool_and((retrieved_at AT TIME ZONE 'UTC')::date=DATE '2026-09-01') FROM input_revision"
            ).fetchone()[0]
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 4
        )

    def test_same_original_label_repair_keeps_newer_equal_value_watermark(self):
        self.publish("old", "3 M.U.I.", pdf=True, version="inputs-pdf-v7")
        self.publish("new", "3 M.U.I.", pdf=True, version="inputs-pdf-v7")
        self.assert_current("old", "3 M.U.I.", locator_suffix="inputs-pdf-v7")
        before = self.db.execute(
            "SELECT md5(to_jsonb(h)::text) FROM historical_price h"
        ).fetchall()
        watermark = self.db.execute(
            "SELECT * FROM input_revision ORDER BY municipality"
        ).fetchall()
        self.publish("old", "3 M. U. I.", pdf=True, version="inputs-pdf-v8")
        self.assert_current("old", "3 M. U. I.", locator_suffix="inputs-pdf-v8")
        self.assertEqual(
            self.db.execute(
                "SELECT * FROM input_revision ORDER BY municipality"
            ).fetchall(),
            watermark,
        )
        self.assertTrue(
            set(before)
            <= set(
                self.db.execute(
                    "SELECT md5(to_jsonb(h)::text) FROM historical_price h"
                ).fetchall()
            )
        )
        # The label repair grants no authority to an intermediate price revision.
        self.publish("mid", "3 M. U. I.", "11000", pdf=True, version="inputs-pdf-v8")
        self.assert_current("old", "3 M. U. I.", locator_suffix="inputs-pdf-v8")

    def test_current_version_stale_presentation_repair_is_idempotent(self):
        self.publish("old", "3 M. U. I.", pdf=True, version="inputs-pdf-v8")
        # Simulate the prior projection bug: the correct raw row/locator was
        # retained but its exact presentation was omitted from the UPSERT.
        for table in ("input_price", "input_municipal_price"):
            self.db.execute(f"UPDATE {table} SET presentation='3 M.U.I.'")
        self.publish("new", "3 M.U.I.", pdf=True, version="inputs-pdf-v8")
        watermark = self.db.execute(
            "SELECT * FROM input_revision ORDER BY municipality"
        ).fetchall()
        self.publish("old", "3 M. U. I.", pdf=True, version="inputs-pdf-v8")
        self.assert_current("old", "3 M. U. I.", locator_suffix="inputs-pdf-v8")
        attempts = self.db.execute("SELECT count(*) FROM input_attempt").fetchone()[0]
        self.publish("old", "3 M. U. I.", pdf=True, version="inputs-pdf-v8")
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM input_attempt").fetchone()[0],
            attempts,
        )
        self.assertEqual(
            self.db.execute(
                "SELECT * FROM input_revision ORDER BY municipality"
            ).fetchall(),
            watermark,
        )

    def test_label_repair_never_accepts_other_source_or_changed_price(self):
        self.publish("new", "3 M.U.I.", pdf=True, version="inputs-pdf-v7")
        self.publish("old", "3 M. U. I.", pdf=True, version="inputs-pdf-v8")
        self.assert_current("new", "3 M.U.I.", locator_suffix="inputs-pdf-v7")
        # The same-original provenance path also cannot change a price after
        # a newer equal-value validation has advanced the per-key watermark.
        self.db.execute("UPDATE input_revision SET retrieved_at='2026-09-04'")
        self.publish("new", "3 M. U. I.", "11168", pdf=True, version="inputs-pdf-v8")
        for table in ("input_price", "input_municipal_price"):
            self.assertEqual(
                self.db.execute(
                    f"SELECT presentation,price,document_id FROM {table}"
                ).fetchone(),
                ("3 M.U.I.", Decimal(11167), "new"),
            )


if __name__ == "__main__":
    unittest.main()

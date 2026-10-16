"""Native printed daily supply values remain dated reference cells."""

import unittest
from datetime import date
from hashlib import sha256
from pathlib import Path
from unittest.mock import MagicMock, patch

from . import daily_pdf_supply, worker

ORIGINAL = (
    Path(__file__).resolve().parent
    / "testdata/bol-SIPSADiario-25sep2026.pdf"
)
WRAPPED_ORIGINAL = Path(__file__).resolve().parent / "testdata/bol-SIPSADiario-04sep2026.pdf"


class DailyPdfSupply(unittest.TestCase):
    def _run_mocked_bulletin(self, monetary_rows, supply_rows=None, supply_error=None):
        db = MagicMock()
        db.execute.return_value.fetchone.side_effect = [
            ("prior-processor",), None, ("prior-document", "complete", 0),
        ]
        with patch("pipelines.ingestion.retained_pdf_upgrade.retained_pdf_upgrade", return_value=None), \
             patch.object(worker, "fetch_asset", return_value=b"retained PDF"), \
             patch.object(worker, "archive", return_value="exact-sha"), \
             patch.object(worker, "save_rows", return_value=monetary_rows), \
             patch.object(worker, "retire_daily_pdf_old_cells") as retire_old, \
             patch.object(worker, "project", return_value=0), \
             patch("pipelines.ingestion.pdf_sources.extract_pages"), \
             patch("pipelines.ingestion.pdf_sources.parse_archived_price_pdf", return_value=[1] if monetary_rows else []), \
             patch.object(daily_pdf_supply, "parse", side_effect=ValueError(supply_error) if supply_error else None, return_value=supply_rows), \
             patch.object(daily_pdf_supply, "publish_rows", return_value=len(supply_rows or [])):
            worker._process_asset(db, "https://www.dane.gov.co/bol.pdf", "daily-pdf", date(2026, 9, 25))
        self.assertEqual(retire_old.call_count, 1 if monetary_rows else 0)
        updates = [call.args[1] for call in db.execute.call_args_list
                   if call.args[0].startswith("UPDATE ingestion_asset SET document_id=%s,status=%s,records=%s")]
        self.assertEqual(len(updates), 1)
        return db, updates[0]

    def test_supply_layout_review_does_not_rollback_monetary_prices(self):
        db, update = self._run_mocked_bulletin(3, supply_error="Daily PDF supply market table is incomplete")
        self.assertEqual(update[1:3], ("review", 3))
        self.assertIn("Supply table requires review", update[3])
        self.assertTrue(any("INSERT INTO official_source_review" in call.args[0]
                            for call in db.execute.call_args_list))

    def test_supply_only_bulletin_is_not_a_completed_price_extraction(self):
        db, update = self._run_mocked_bulletin(0, supply_rows=[{"source_locator": "PDF page 4"}])
        self.assertEqual(update[1:3], ("processed", 1))
        self.assertIn("No supported monetary price grid", update[3])
        self.assertFalse(any("INSERT INTO official_source_review" in call.args[0]
                             for call in db.execute.call_args_list))

    def test_exact_printed_values_and_blanks(self):
        original = ORIGINAL.read_bytes()
        self.assertEqual(sha256(original).hexdigest(), "61b2a8a1d98806033f49bfab42898128e9e590a83e9a8c17edbf287de22afe64")
        rows = daily_pdf_supply.parse(original, date(2026, 9, 25))
        self.assertEqual(len(rows), 264)
        self.assertEqual(len({r["name"] for r in rows}), 33)
        self.assertEqual(sum(r["details"]["quantity_tonnes"] is None for r in rows), 44)
        total = next(r for r in rows if r["name"] == "Total" and r["observed_on"] == date(2026, 9, 24))
        corabastos = next(r for r in rows if r["name"] == "Bogotá, D.C., Corabastos" and r["observed_on"] == date(2026, 9, 24))
        self.assertEqual((total["details"]["quantity_tonnes"], total["details"]["literal_value"]), (27004, "27.004"))
        self.assertEqual((corabastos["details"]["quantity_tonnes"], corabastos["details"]["literal_value"]), (7723, "7.723"))
        self.assertEqual((total["details"]["source_page"], corabastos["details"]["source_page"]), (5, 4))
        self.assertEqual(total["details"]["aggregation_level"], "reported_markets_total")
        self.assertEqual(total["details"]["weekday_header"], "Juevesp")
        self.assertTrue(total["details"]["provisional"])
        self.assertTrue(all(r["details"]["provisional"] is None for r in rows if r["observed_on"] < date(2026, 9, 24)))
        self.assertTrue(all(r["details"]["non_additive"] for r in rows))
        self.assertTrue(any(r["details"]["availability"] == "not_reported" for r in rows))

    def test_total_validation_does_not_depend_on_pdf_row_order(self):
        rows = daily_pdf_supply.parse(ORIGINAL.read_bytes(), date(2026, 9, 25))
        daily_pdf_supply._validate_totals(list(reversed(rows)), date(2026, 9, 17))

    def test_archive_date_must_follow_printed_table(self):
        with self.assertRaisesRegex(ValueError, "archive day"):
            daily_pdf_supply.parse(ORIGINAL.read_bytes(), date(2026, 9, 23))

    def test_cross_month_wrapped_dates_from_official_original(self):
        rows = daily_pdf_supply.parse(WRAPPED_ORIGINAL.read_bytes(), date(2026, 9, 4))
        self.assertEqual((len(rows), len({r["name"] for r in rows})), (264, 33))
        self.assertEqual(sum(r["details"]["quantity_tonnes"] is None for r in rows), 42)
        checks = (
            (date(2026, 8, 27), "Total", 26332, "26.332", 5, "27-ago.", "Jueves"),
            (date(2026, 9, 3), "Total", 26644, "26.644", 5, "3-sep.", "Juevesp"),
            (date(2026, 8, 27), "Bogotá, D.C., Corabastos", 7455, "7.455", 4, "27-ago.", "Jueves"),
            (date(2026, 9, 3), "Bogotá, D.C., Corabastos", 8173, "8.173", 4, "3-sep.", "Juevesp"),
        )
        for observed_on, name, tonnes, literal, page, heading, weekday in checks:
            row = next(r for r in rows if r["observed_on"] == observed_on and r["name"] == name)
            details = row["details"]
            self.assertEqual((details["quantity_tonnes"], details["literal_value"],
                              details["source_page"], details["date_header"], details["weekday_header"]),
                             (tonnes, literal, page, heading, weekday))
        self.assertEqual(rows[0]["details"]["period_start"], "2026-08-27")
        self.assertEqual(rows[0]["details"]["period_end"], "2026-09-03")

    def test_retained_older_daily_price_bulletins_have_no_supply_table(self):
        for filename in ("dane_daily_2014_06_09_blank_page4.pdf", "dane_daily_2017_04_19_blank_page4.pdf"):
            with self.subTest(filename=filename):
                original = Path(__file__).resolve().parent / "testdata" / filename
                self.assertEqual(daily_pdf_supply.parse(original.read_bytes()), [])


if __name__ == "__main__":
    unittest.main()

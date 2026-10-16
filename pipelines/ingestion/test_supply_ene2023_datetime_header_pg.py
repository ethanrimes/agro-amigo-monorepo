"""Exact retained January 2023 DANE supply annex and bounded automatic repair."""

import hashlib
import json
import os
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import openpyxl

from . import queue_plan, supply_period_summaries, supply_summaries, worker

ORIGINAL = Path(__file__).with_name("testdata") / "supply-anexo-abastecimiento-ene2023-c8b702.xlsx"
SHA = "c8b702262cbb28612b3f4741cca307029eef5a295b11dfc3a42bb090b348b5a6"
URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/anexo_abastecimiento_ene23.xlsx"
OLD_VERSION = "supply-daily-summary-v1:supply-period-summary-workbook-v2"
ERROR = "TypeError: Object of type datetime is not JSON serializable"


def original():
    body = ORIGINAL.read_bytes()
    assert hashlib.sha256(body).hexdigest() == SHA
    return body


class OriginalNativeHeader(unittest.TestCase):
    def test_literal_date_style_header_and_all_893_rows_are_json_serializable(self):
        body = original()
        book = openpyxl.load_workbook(ORIGINAL, read_only=True, data_only=True)
        try:
            sheet = book["3"]
            self.assertEqual(sheet["A10"].value, "Ciudad, Mercado Mayorista")
            self.assertEqual(sheet["B10"].value, "Diciembre 2022")
            self.assertEqual(sheet["C10"].value, datetime(2023, 1, 1))
            self.assertEqual(sheet["C10"].number_format, "mmm-yy")
            self.assertEqual(sheet["A11"].value, "Bogotá, D.C.,  Corabastos")
            self.assertAlmostEqual(sheet["B11"].value, 0.3572768291423228)
            self.assertAlmostEqual(sheet["C11"].value, 0.34956227486117447)
        finally:
            book.close()
        rows, reviews = supply_period_summaries.parse_workbook(body)
        self.assertEqual(reviews, [])
        self.assertEqual(len(rows), 893)
        self.assertEqual(sum(r["source_locator"].startswith("3!") for r in rows), 58)
        for row in rows:
            json.dumps(row["details"])
        by_locator = {r["source_locator"]: r for r in rows}
        self.assertEqual(len(by_locator), 893)
        for col, day, value in (
            (2, date(2022, 12, 31), 35.727682914232275),
            (3, date(2023, 1, 31), 34.95622748611745),
        ):
            row = by_locator[f"3!row 11,col {col}; supply-period-summary-v8"]
            self.assertEqual((row["observed_on"], row["name"], row["details"]["unit"]),
                             (day, "Bogotá, D.C., Corabastos", "percentage_points"))
            self.assertAlmostEqual(row["details"]["value"], value)
            self.assertEqual(row["details"]["native_headers"]["C10"], "2023-01-01T00:00:00")
        self.assertEqual(worker.asset_parser_version("supply-reference", URL),
                         OLD_VERSION + ":ene23-native-date-header-json-v1")
        self.assertEqual(worker.asset_parser_version("supply-reference", URL + "-other"), OLD_VERSION)


@unittest.skipUnless(os.environ.get("AGRO_DAILY_ZIP_POSTGRES_TEST") == "1",
                     "isolated PostgreSQL opt-in")
class ExactRetainedRepairPostgres(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp,public")
        self.db.execute("SET statement_timeout='15s'")
        for table in ("source_document", "ingestion_asset", "input_reference_row", "ingestion_checkpoint", "historical_price"):
            self.db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")
            self.assertEqual(self.db.execute(
                "SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)", (table,)
            ).fetchone(), ("t",))
        body = original()
        self.db.execute("""INSERT INTO source_document
            (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
            VALUES(%s,'January 2023','DANE',%s,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'original','January 2023',%s,%s::jsonb)""",
            (SHA, URL, body, json.dumps({"ingestion_kind": "supply-reference"})))
        self.db.execute("""INSERT INTO ingestion_asset
            (url,kind,status,document_id,records,processor_version,error,checked_at)
            VALUES(%s,'supply-reference','review',%s,835,%s,%s,now())""",
            (URL, SHA, OLD_VERSION, ERROR))

    def test_repair_lane_exact_recent_review_and_wrong_source_guards(self):
        self.assertEqual(queue_plan.repair_candidates(self.db, 1)[0][0], URL)
        self.assertEqual(worker.retained_ene23_supply_reference_repair(
            self.db, URL, "supply-reference"), original())
        self.assertTrue(worker.retained_reparse_during_host_cooldown(
            self.db, URL, "supply-reference"))
        self.assertFalse(worker.retained_reparse_during_host_cooldown(
            self.db, URL + "-other", "supply-reference"))
        for column, changed, valid in (
            ("status", "complete", "review"),
            ("error", "other error", ERROR),
            ("processor_version", "other-version", OLD_VERSION),
            ("document_id", "0" * 64, SHA),
        ):
            self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s",
                            (changed, URL))
            self.assertIsNone(worker.retained_ene23_supply_reference_repair(
                self.db, URL, "supply-reference"))
            self.assertEqual(queue_plan.repair_candidates(self.db, 1), [])
            self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s",
                            (valid, URL))
        self.db.execute("UPDATE source_document SET source_url=%s WHERE id=%s", (URL + "-changed", SHA))
        self.assertIsNone(worker.retained_ene23_supply_reference_repair(
            self.db, URL, "supply-reference"))
        self.db.execute("UPDATE source_document SET source_url=%s WHERE id=%s", (URL, SHA))
        self.db.execute("UPDATE source_document SET content=%s WHERE id=%s", (original() + b"changed", SHA))
        with self.assertRaisesRegex(ValueError, "SHA mismatch"):
            worker.retained_ene23_supply_reference_repair(self.db, URL, "supply-reference")

    def test_no_http_resume_retains_835_and_publishes_only_missing_58(self):
        body = original()
        rows, reviews = supply_period_summaries.parse_workbook(body)
        self.assertEqual((len(rows), reviews), (893, []))
        already_retained = [r for r in rows if not r["source_locator"].startswith("3!")]
        self.assertEqual(len(already_retained), 835)
        supply_summaries.publish_rows(self.db, already_retained, SHA)
        before = self.db.execute("""SELECT source_locator,details::text FROM input_reference_row
            WHERE document_id=%s ORDER BY source_locator""", (SHA,)).fetchall()
        self.assertEqual(len(before), 835)
        with patch.object(worker, "fetch_asset", side_effect=AssertionError("HTTP was attempted")), \
             patch.object(worker, "archive", return_value=SHA):
            self.assertEqual(worker.process_asset(self.db, URL, "supply-reference", None), 893)
        after = self.db.execute("""SELECT source_locator,details::text FROM input_reference_row
            WHERE document_id=%s ORDER BY source_locator""", (SHA,)).fetchall()
        self.assertEqual(len(after), 893)
        self.assertEqual([row for row in after if row[0] in dict(before)], before)
        self.assertEqual(self.db.execute("""SELECT count(*) FROM input_reference_row
            WHERE document_id=%s AND source_locator LIKE '3!%%'""", (SHA,)).fetchone(), (58,))
        self.assertEqual(self.db.execute("""SELECT status,records,processor_version,error
            FROM ingestion_asset WHERE url=%s""", (URL,)).fetchone(),
            ("complete", 893, worker.asset_parser_version("supply-reference", URL), None))
        self.assertEqual(worker.retained_ene23_supply_reference_repair(
            self.db, URL, "supply-reference"), None)
        # The next ordinary same-URL check must be eligible for HTTP refresh.
        with patch.object(worker, "fetch_asset", return_value=None) as fetch:
            worker.process_asset(self.db, URL, "supply-reference", None)
            fetch.assert_called_once()
        self.assertEqual(self.db.execute("SELECT count(*) FROM input_reference_row").fetchone(), (893,))

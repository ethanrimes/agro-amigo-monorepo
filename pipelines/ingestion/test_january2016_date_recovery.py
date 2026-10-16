"""Actual mislinked 2017 workbook and independent 2016 DANE query evidence."""

import hashlib
import json
import os
import re
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import xlrd

from . import daily_publication, daily_recovery, dane_daily_query, query_publication, worker

FIXTURES = Path(__file__).parent / "testdata"
URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_18_2016.xls"
DAY = date(2016, 1, 18)
ACTUAL_DAY = date(2017, 1, 18)
ORIGINAL = FIXTURES / "daily-january2016-mislinked-2017.xls"
SHA = "fe66e1d1a39637d81bde11325ba60f8ef8c12a96fdf779f5c6ab7f3586d83e2c"


def fetch(url, parameters):
    role = {
        "qryFuente": "1-sources", "qryGrupo": "2-groups",
        "qryArticulo": "3-products", "qryTabla": "4-daily-prices",
    }.get(parameters.get("dataAccessId") if parameters else None, "0-unit-evidence")
    if parameters and parameters["dataAccessId"] == "qryTabla":
        assert parameters["parampardPeriodoIni"] == parameters["parampardPeriodoFin"] == DAY.isoformat()
        assert parameters["pageStart"] == parameters["pageSize"] == 0
    return (FIXTURES / f"daily-january2016-query-{role}.bin").read_bytes()


class NativeDateEvidence(unittest.TestCase):
    def test_every_workbook_price_keeps_2017_native_date_and_literal_cell(self):
        original = ORIGINAL.read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), SHA)
        parsed = daily_recovery.parse_daily(original, DAY)
        self.assertEqual((len(parsed["rows"]), parsed["reviews"]), (315, []))
        book = xlrd.open_workbook(file_contents=original)
        for row in parsed["rows"]:
            sheet, rn, col = re.fullmatch(r"(.+)!row (\d+),col (\d+)", row[0]).groups()
            native = book.sheet_by_name(sheet).cell_value(int(rn) - 1, int(col) - 1)
            self.assertEqual((row[2], row[6]), (ACTUAL_DAY, native))
            self.assertEqual(row[-1]["date_resolution"]["observation_date"], "2017-01-18")
        prices = {(r[3], r[4]): r[6] for r in parsed["rows"]}
        # Independently rendered companion PDF page 1 prints these same prices.
        self.assertEqual(prices[("Habichuela", "Barranquilla")], 2769)
        self.assertEqual(prices[("Habichuela", "Montería")], 2475)
        self.assertEqual(daily_recovery.parse_daily(original, ACTUAL_DAY)["date_resolutions"], [])

    def test_all_1199_requested_day_query_values_match_native_response(self):
        original = ORIGINAL.read_bytes()
        result = dane_daily_query.recover_daily(URL, None, DAY, fetch, original_data=original)
        native = json.loads(fetch(dane_daily_query.API_URL, {"dataAccessId": "qryTabla",
            "parampardPeriodoIni": DAY.isoformat(), "parampardPeriodoFin": DAY.isoformat(),
            "pageStart": 0, "pageSize": 0}))["resultset"]
        self.assertEqual(len(result.rows), 1199)
        for parsed, raw in zip(result.rows, native, strict=True):
            self.assertEqual((str(parsed[2]), parsed[4], parsed[3], parsed[6],
                parsed[-1]["price_min"], parsed[-1]["price_max"]), tuple(raw))
        self.assertEqual(result.evidence["returned_sources"], 23)
        self.assertEqual(result.evidence["returned_products"], 215)
        self.assertEqual(result.rows[0][6], 1244)  # Published mean, not range midpoint.

    def test_wrong_original_or_archive_day_cannot_use_the_approval(self):
        original = ORIGINAL.read_bytes()
        fetcher = Mock(side_effect=AssertionError("Unexpected provider request"))
        with self.assertRaisesRegex(ValueError, "verified original SHA"):
            dane_daily_query.recover_daily(URL, None, DAY, fetcher, original_data=original + b"changed")
        with self.assertRaisesRegex(ValueError, "match the missing source"):
            dane_daily_query.recover_daily(URL, None, date(2016, 1, 19), fetcher, original_data=original)
        with self.assertRaises(worker.SourceDateMismatch):
            daily_recovery.parse_daily(original, date(2016, 1, 19))
        fetcher.assert_not_called()


@unittest.skipUnless(os.environ.get("AGRO_JANUARY_DATE_POSTGRES_TEST") == "1",
    "Explicit opt-in for isolated actual-original PostgreSQL publication")
class ActualDatePublication(unittest.TestCase):
    def test_both_years_publish_idempotently_without_relabelling_original(self):
        with worker.connect() as db, patch.dict(os.environ, {"AzureWebJobsStorage": ""}):
            db.execute("SET search_path=pg_temp;SET statement_timeout='30s'")
            for table in ("source_document", "document_alias", "historical_price", "daily_price",
                "product", "official_price_quote", "official_source_review", "official_catalog_current",
                "retained_record", "ingestion_checkpoint", "ingestion_asset"):
                db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")
                self.assertEqual(db.execute("SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)",
                    (table,)).fetchone(), ("t",))
            db.execute("INSERT INTO ingestion_asset(url,kind,observed_on,status) VALUES(%s,'daily',%s,'review')", (URL, DAY))
            original = ORIGINAL.read_bytes()
            did = worker.archive(db, URL, original, "daily", DAY)
            self.assertEqual(did, SHA)
            with patch.object(worker.SESSION, "get", side_effect=lambda u, **_: SimpleNamespace(
                    content=fetch(u, None), raise_for_status=lambda: None)), \
                 patch.object(worker.SESSION, "post", side_effect=lambda u, data, **_: SimpleNamespace(
                    content=fetch(u, data), raise_for_status=lambda: None)):
                for _ in range(2):
                    self.assertEqual(daily_publication.publish(db, original, did, URL, DAY), 315)
                    self.assertEqual(query_publication.recover(db, URL, None, DAY,
                        original_data=original, original_id=did), 1199)
            self.assertEqual(db.execute("SELECT observed_on,count(*) FROM historical_price GROUP BY observed_on ORDER BY observed_on").fetchall(),
                [(DAY, 1199), (ACTUAL_DAY, 315)])
            self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote").fetchone(), (1199,))
            self.assertEqual(db.execute("SELECT document_id,status,records,observed_on FROM ingestion_asset").fetchone(),
                (did, "review", 315, DAY))
            self.assertEqual(bytes(db.execute("SELECT content FROM source_document WHERE id=%s", (did,)).fetchone()[0]), original)
            self.assertTrue(worker.parser_version("daily").startswith("daily-units-v6:"))

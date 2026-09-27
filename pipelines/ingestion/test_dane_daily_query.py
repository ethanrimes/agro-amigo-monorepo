"""Full native public-query recovery, with exact identity/range/coverage guards."""

import copy
import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock

from pipelines.ingestion.dane_daily_query import (
    API_URL,
    EXPLORER_URL,
    MISSING_DAILY_URLS,
    UNIT_NOTE,
    VERIFIED_DATE_CONFLICTS,
    parse_response,
    recover_daily,
    unit_for,
)

DAY = date(2013, 4, 18)
BROKEN = next(url for url, day in MISSING_DAILY_URLS.items() if day == DAY)
SOURCES = ["Bucaramanga, Centroabastos", "Cúcuta, Cenabastos"]
PRODUCTS = ["Pimentón", "Huevo rojo A", "Aceite vegetal mezcla"]
FIXTURES = Path(__file__).resolve().parents[2] / "artifacts/source-ambiguity-2026-09-27"
COLUMNS = ("FECHA", "FUENTE", "ARTICULO", "PROMEDIO", "MINIMO", "MAXIMO")


def encoded(rows, columns=COLUMNS, total=None):
    return json.dumps(
        {
            "queryInfo": {"totalRows": str(len(rows) if total is None else total)},
            "metadata": [{"colName": c, "colIndex": i} for i, c in enumerate(columns)],
            "resultset": rows,
        },
        ensure_ascii=False,
    ).encode()


def native_rows():
    return [
        ["2013-04-18", SOURCES[0], PRODUCTS[0], 1417, 1333, 1500],
        ["2013-04-18", SOURCES[1], PRODUCTS[1], 235, 220, 250],
        ["2013-04-18", SOURCES[1], PRODUCTS[2], 3792, 3542, 4000],
    ]


def fake_fetcher(url, params):
    if params is None:
        return f"<html><p>{UNIT_NOTE}</p></html>".encode()
    query = params["dataAccessId"]
    if query == "qryFuente":
        return encoded([[x] for x in SOURCES], ("SUBSTR(SFT_NOMBRE,1,50)",))
    if query == "qryGrupo":
        return encoded([["Verduras y hortalizas"], ["Procesados"]], ("SGR_NOMBRE",))
    if query == "qryArticulo":
        return encoded([[x] for x in PRODUCTS], ("SAR_NOMBRE",))
    if query == "qryTabla":
        return encoded(native_rows())
    raise AssertionError("Unexpected unbounded query")


class DailyQueryTests(unittest.TestCase):
    def test_bounded_exact_day_all_options_and_raw_documents_retained(self):
        fetcher = Mock(side_effect=fake_fetcher)
        budget = Mock()
        result = recover_daily(BROKEN, 404, DAY, fetcher, check_budget=budget)
        self.assertEqual(fetcher.call_count, 5)
        self.assertEqual(budget.call_count, 5)
        fetcher.assert_any_call(EXPLORER_URL, None)
        params = fetcher.call_args.args[1]
        self.assertEqual(params["parampardPeriodoIni"], "2013-04-18")
        self.assertEqual(params["parampardPeriodoFin"], "2013-04-18")
        self.assertEqual(params["paramparsPrecio"], "Diario")
        self.assertEqual(params["paramparcFuente"], SOURCES)
        self.assertEqual(params["paramparcArticulo"], PRODUCTS)
        self.assertEqual(params["pageSize"], 0)
        self.assertEqual(params["pageStart"], 0)
        self.assertEqual(result.source_url, API_URL)
        self.assertEqual(len(result.documents), 5)
        final = result.documents[-1]
        self.assertEqual(final.role, "daily-prices")
        self.assertEqual(final.body, encoded(native_rows()))
        self.assertEqual(final.metadata["request_parameters"], params)
        self.assertEqual(final.metadata["original_missing_url"], BROKEN)
        self.assertEqual(result.evidence["returned_records"], 3)

    def test_original_missing_url_and_status_gate_prevents_speculative_query(self):
        fetcher = Mock()
        for status in (200, 304, 401, 403, 429, 500, 503):
            self.assertIsNone(recover_daily(BROKEN, status, DAY, fetcher))
        self.assertIsNone(recover_daily(BROKEN + "?changed=1", 404, DAY, fetcher))
        with self.assertRaisesRegex(ValueError, "missing source"):
            recover_daily(BROKEN, 404, date(2013, 4, 19), fetcher)
        fetcher.assert_not_called()

    def test_date_conflict_requires_exact_original_hash_and_explicit_reason(self):
        url, (day, digest) = next(iter(VERIFIED_DATE_CONFLICTS.items()))
        fetcher = Mock(side_effect=fake_fetcher)
        self.assertIsNone(recover_daily(url, 404, day, fetcher))
        for sha in (None, "wrong-sha"):
            with self.assertRaisesRegex(ValueError, "verified original SHA"):
                recover_daily(
                    url,
                    200,
                    day,
                    fetcher,
                    recovery_reason="verified-date-conflict",
                    source_sha256=sha,
                )
        fetcher.assert_not_called()

        def dated_fetch(target, params):
            if params and params["dataAccessId"] == "qryTabla":
                self.assertEqual(params["parampardPeriodoIni"], day.isoformat())
                self.assertEqual(params["parampardPeriodoFin"], day.isoformat())
                rows = native_rows()
                for row in rows:
                    row[0] = day.isoformat()
                return encoded(rows)
            return fake_fetcher(target, params)

        result = recover_daily(
            url,
            200,
            day,
            dated_fetch,
            recovery_reason="verified-date-conflict",
            source_sha256=digest,
        )
        self.assertEqual(result.evidence["conflicting_original_sha256"], digest)
        self.assertIsNone(result.evidence["original_missing_url"])
        self.assertEqual(result.evidence["original_url"], url)
        self.assertTrue(all(row[2] == day for row in result.rows))

    def test_original_bytes_hash_is_required_before_conflict_fetch(self):
        url, (day, digest) = next(iter(VERIFIED_DATE_CONFLICTS.items()))
        fetcher = Mock()
        with self.assertRaisesRegex(ValueError, "verified original SHA"):
            recover_daily(url, None, day, fetcher, original_data=b"different original")
        with self.assertRaisesRegex(ValueError, "supplied SHA"):
            recover_daily(
                url,
                None,
                day,
                fetcher,
                original_data=b"different original",
                source_sha256=digest,
            )
        fetcher.assert_not_called()

    @unittest.skipUnless(
        all(
            (FIXTURES / "daily" / u.rsplit("/", 1)[1]).exists()
            for u in VERIFIED_DATE_CONFLICTS
        ),
        "audited conflicting XLS originals unavailable",
    )
    def test_all_six_actual_conflict_originals_hash_gate_requested_day_only(self):
        for url, (day, digest) in VERIFIED_DATE_CONFLICTS.items():
            body = (FIXTURES / "daily" / url.rsplit("/", 1)[1]).read_bytes()

            def dated_fetch(target, params, day=day):
                if params and params["dataAccessId"] == "qryTabla":
                    self.assertEqual(params["parampardPeriodoIni"], day.isoformat())
                    self.assertEqual(params["parampardPeriodoFin"], day.isoformat())
                    rows = native_rows()
                    for row in rows:
                        row[0] = day.isoformat()
                    return encoded(rows)
                return fake_fetcher(target, params)

            result = recover_daily(url, None, day, dated_fetch, original_data=body)
            self.assertEqual(result.evidence["conflicting_original_sha256"], digest)
            self.assertEqual(
                result.evidence["recovery_reason"], "verified-date-conflict"
            )
            self.assertTrue(all(row[2] == day for row in result.rows))

    def test_published_mean_is_not_replaced_by_midpoint(self):
        row = parse_response(encoded(native_rows()), DAY, SOURCES, PRODUCTS)[0]
        self.assertEqual(row[1], "dane-daily-query")
        self.assertEqual(row[6], 1417)
        self.assertNotEqual(row[6], (1333 + 1500) / 2)
        self.assertEqual(row[8]["price_mean"], 1417)
        self.assertEqual(row[8]["price_min"], 1333)
        self.assertEqual(row[8]["price_max"], 1500)
        self.assertEqual(row[8]["price_statistic"], "published_mean")
        self.assertEqual(row[8]["currency"], "COP")
        self.assertEqual(row[0], "JSON resultset[0]; PROMEDIO/MINIMO/MAXIMO")

    def test_documented_units_preserved(self):
        rows = parse_response(encoded(native_rows()), DAY, SOURCES, PRODUCTS)
        self.assertEqual([r[5] for r in rows], ["kg", "unit", "litre"])
        for product in ["Bocadillo veleño", "Huevo blanco AA", "Huevos rojos"]:
            self.assertEqual(unit_for(product), "unit")
        for product in ["Jugo de frutas", "Aceite girasol", "Vinagre"]:
            self.assertEqual(unit_for(product), "litre")

    def test_truncated_or_paginated_response_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete or paginated"):
            parse_response(encoded(native_rows(), total=500), DAY, SOURCES, PRODUCTS)

    def test_wrong_date_and_duplicate_identity_rejected(self):
        rows = native_rows()
        rows[-1][0] = "2013-04-19"
        with self.assertRaisesRegex(ValueError, "unexpected observation date"):
            parse_response(encoded(rows), DAY, SOURCES, PRODUCTS)
        rows = native_rows() + [native_rows()[0]]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            parse_response(encoded(rows), DAY, SOURCES, PRODUCTS)

    def test_null_placeholder_and_unknown_product_cannot_claim_full_coverage(self):
        for row in (
            ["2013-04-18", None, None, None, None, None],
            ["2013-04-18", SOURCES[0], "unrequested product", 1, 1, 1],
        ):
            with self.assertRaisesRegex(ValueError, "unknown or empty identity"):
                parse_response(encoded([row]), DAY, SOURCES, PRODUCTS)

    def test_ambiguous_values_or_changed_schema_rejected(self):
        for price in (None, "1.417", True, -1, float("nan"), float("inf")):
            rows = native_rows()
            rows[0][3] = price
            with (
                self.subTest(price=price),
                self.assertRaisesRegex(ValueError, "price value"),
            ):
                parse_response(encoded(rows), DAY, SOURCES, PRODUCTS)
        rows = native_rows()
        rows[0][3] = 1600
        with self.assertRaisesRegex(ValueError, "outside"):
            parse_response(encoded(rows), DAY, SOURCES, PRODUCTS)
        with self.assertRaisesRegex(ValueError, "columns"):
            parse_response(
                encoded(native_rows(), COLUMNS[::-1]), DAY, SOURCES, PRODUCTS
            )

    def test_changed_unit_evidence_stops_before_price_requests(self):
        fetcher = Mock(return_value=b"<html>Service unavailable</html>")
        with self.assertRaisesRegex(ValueError, "unit contract"):
            recover_daily(BROKEN, 404, DAY, fetcher)
        self.assertEqual(fetcher.call_count, 1)

    def test_budget_stop_prevents_next_request_and_no_partial_result(self):
        fetcher = Mock(side_effect=fake_fetcher)
        budget = Mock(side_effect=[None, None, TimeoutError("budget reached")])
        with self.assertRaisesRegex(TimeoutError, "budget reached"):
            recover_daily(BROKEN, 404, DAY, fetcher, check_budget=budget)
        self.assertEqual(fetcher.call_count, 2)

    def test_partial_or_duplicate_options_fail_before_daily_request(self):
        def bad_options(url, params):
            if params and params["dataAccessId"] == "qryFuente":
                return encoded([[SOURCES[0]], [SOURCES[0]]], ("source",))
            return fake_fetcher(url, params)

        fetcher = Mock(side_effect=bad_options)
        with self.assertRaisesRegex(ValueError, "Duplicate SIPSA source"):
            recover_daily(BROKEN, 404, DAY, fetcher)
        self.assertEqual(fetcher.call_count, 2)

    @unittest.skipUnless(
        all(
            (FIXTURES / f"pentaho-full-day-{day}.json").exists()
            for day in ("2013-04-18", "2012-10-23")
        ),
        "actual official daily query fixtures unavailable",
    )
    def test_actual_full_days_and_independent_printed_pdf_prices(self):
        sources = [
            r[0]
            for r in json.loads((FIXTURES / "qryFuente.json").read_text())["resultset"]
        ]
        products = [
            r[0]
            for r in json.loads((FIXTURES / "qryArticulo-all.json").read_text())[
                "resultset"
            ]
        ]
        cases = [
            (
                date(2013, 4, 18),
                1675,
                27,
                303,
                "Bucaramanga, Centroabastos",
                "Pimentón",
                1417,
                1333,
                1500,
            ),
            (
                date(2012, 10, 23),
                1747,
                29,
                313,
                "Cúcuta, Cenabastos",
                "Tomate Riogrande",
                2557,
                2500,
                2727,
            ),
        ]
        for day, count, markets, articles, market, product, mean, low, high in cases:
            with self.subTest(day=day):
                body = (FIXTURES / f"pentaho-full-day-{day}.json").read_bytes()
                rows = parse_response(body, day, sources, products)
                self.assertEqual(len(rows), count)
                self.assertEqual(len({r[4] for r in rows}), markets)
                self.assertEqual(len({r[3] for r in rows}), articles)
                anchor = next(r for r in rows if r[4] == market and r[3] == product)
                self.assertEqual(anchor[6], mean)
                self.assertEqual(anchor[8]["price_min"], low)
                self.assertEqual(anchor[8]["price_max"], high)
                bad = copy.deepcopy(json.loads(body))
                bad["resultset"].pop()
                with self.assertRaisesRegex(ValueError, "incomplete or paginated"):
                    parse_response(json.dumps(bad).encode(), day, sources, products)

    @unittest.skipUnless(
        all(
            (FIXTURES / "daily/july-pentaho" / f"{day}.json").exists()
            for day in ("2012-07-06", "2012-07-09")
        ),
        "independently retrieved official July fixtures unavailable",
    )
    def test_actual_july_query_prices_remain_independent_of_ambiguous_workbooks(self):
        sources = [
            r[0]
            for r in json.loads((FIXTURES / "qryFuente.json").read_text())["resultset"]
        ]
        products = [
            r[0]
            for r in json.loads((FIXTURES / "qryArticulo-all.json").read_text())[
                "resultset"
            ]
        ]
        for day, count in [(date(2012, 7, 6), 1350), (date(2012, 7, 9), 1075)]:
            body = (FIXTURES / "daily/july-pentaho" / f"{day}.json").read_bytes()
            rows = parse_response(body, day, sources, products)
            self.assertEqual(len(rows), count)
            self.assertTrue(
                all(r[1] == "dane-daily-query" and r[2] == day for r in rows)
            )


if __name__ == "__main__":
    unittest.main()

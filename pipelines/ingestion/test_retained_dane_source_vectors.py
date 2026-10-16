"""Offline regressions against two exact retained DANE originals.

The gzip JSONL files are independent SQL business-vector exports with only the
private xmin column stripped. This test intentionally does not require a DB,
network, provider, or files under ignored artifacts outside this fixture folder.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import sys
import unittest

_REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "pipelines").is_dir()
)
sys.path.insert(0, str(_REPO_ROOT))

from pipelines.ingestion import city_product_corrections, city_reports, input_pdf_v17_replay
from pipelines.ingestion import pdf_sources

FIXTURES = Path(__file__).resolve().parent / "testdata" / "dane_retained_source_replay"

FEB_BODY_SHA = "cb2289b8dad52378bc04a9787c7560a93a1feccfd47c64a41e010a33a499f5ab"
FEB_ORACLE_SHA = "76a8fab363c87c265b1b345c5d98afaba1aa908d0d37217458082698c48d275e"
FEB_ORACLE_SOURCE_EXPORT_SHA = "ad6cdde6f12fc7187bec225a949d4fbf890c0130449fa24fdd6b951354b62717"
FEB_FIELDS = (
    "source_locator", "series", "observed_on", "product_name", "market_name",
    "unit", "price", "change_percent", "details",
)
FEB_SERIES_COUNTS = {"dane-inputs-pdf": 8177, "dane-inputs-pdf-unresolved": 602}

MAY_BODY_SHA = "3f4c634f9f0c1b832594384da3ebf7c5329dd05466b28a01a12a79a161b4634b"
MAY_ORACLE_SHA = "714b85e2c6de9731fcefd6dcc2c4cef9c12b357e2d833e1156812348b04ff359"
MAY_ORACLE_SOURCE_EXPORT_SHA = "1efb129326106a2fb37c4546ec6118063d8a96b8d2ec876a7bd7b4e6af377569"
MAY_FIELDS = city_product_corrections.REGIONAL_COLUMNS
MAY_PDF_OFFSET = 16384
MAY_EOF_OFFSET = 164954


def _read_vectors(filename: str, expected_sha: str, expected_fields: tuple[str, ...]):
    raw = (FIXTURES / filename).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise AssertionError(f"Pinned SQL-vector fixture changed: {filename}")
    with gzip.open(FIXTURES / filename, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    for index, row in enumerate(rows):
        if tuple(row) != expected_fields:
            raise AssertionError(
                f"{filename} row {index} field layout changed; expected {len(expected_fields)} business fields"
            )
        if "xmin::text" in row:
            raise AssertionError(f"Private xmin leaked into {filename} row {index}")
    return rows


def _decimal_text(value):
    return None if value is None else format(Decimal(str(value)), "f")


def _first_diff(expected_rows, actual_rows, fields, locator_name="source_locator"):
    if len(expected_rows) != len(actual_rows):
        return f"row count expected={len(expected_rows)} actual={len(actual_rows)}"
    for index, (expected, actual) in enumerate(zip(expected_rows, actual_rows)):
        if tuple(expected) != fields or tuple(actual) != fields:
            return f"row={index} field-layout mismatch"
        for field in fields:
            if expected[field] != actual[field]:
                return (
                    f"row={index} locator={expected.get(locator_name)!r} field={field}: "
                    f"expected={str(expected[field])[:160]!r} actual={str(actual[field])[:160]!r}"
                )
    return None


class RetainedDaneSourceOfflineTests(unittest.TestCase):
    def test_february_2016_context_pdf_full_v17_vector_matches_v14_sql_export(self):
        body = (FIXTURES / "feb2016-context-original.pdf").read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), FEB_BODY_SHA)
        expected = _read_vectors("feb2016_v14_9field.jsonl.gz", FEB_ORACLE_SHA, FEB_FIELDS)
        parsed = list(pdf_sources.parse_input_pdf(
            body, date(2016, 2, 29), parser_version=input_pdf_v17_replay.VERSION,
        ))
        self.assertEqual(len(parsed), 8779)
        self.assertEqual(len({row[0] for row in parsed}), 8779)

        actual = []
        for row in parsed:
            locator, series, observed_on, product, market, unit, price, change, details = row
            if not locator.endswith("; " + input_pdf_v17_replay.VERSION):
                self.fail(f"unexpected parser locator version: {locator[:180]}")
            old_details = dict(details)
            self.assertEqual(old_details.get("parser_version"), input_pdf_v17_replay.VERSION)
            old_details["parser_version"] = input_pdf_v17_replay.OLD_VERSION
            actual.append({
                "source_locator": locator[: -len(input_pdf_v17_replay.VERSION)]
                    + input_pdf_v17_replay.OLD_VERSION,
                "series": series,
                "observed_on": observed_on.isoformat(),
                "product_name": product,
                "market_name": market,
                "unit": unit,
                "price": _decimal_text(price),
                "change_percent": _decimal_text(change),
                "details": old_details,
            })
        actual.sort(key=lambda row: row["source_locator"])
        expected.sort(key=lambda row: row["source_locator"])
        counts = {name: sum(row["series"] == name for row in actual) for name in FEB_SERIES_COUNTS}
        self.assertEqual(counts, FEB_SERIES_COUNTS)
        mismatch = _first_diff(expected, actual, FEB_FIELDS)
        self.assertIsNone(mismatch, mismatch)

    def test_may_2021_full_rtfd_wrapper_parses_to_17_field_sql_export(self):
        wrapper = (FIXTURES / "may2021-corabastos-original.rtfd").read_bytes()
        self.assertEqual(hashlib.sha256(wrapper).hexdigest(), MAY_BODY_SHA)
        self.assertTrue(wrapper.startswith(b"rtfd"))
        self.assertEqual(wrapper.find(b"%PDF"), MAY_PDF_OFFSET)
        self.assertEqual(wrapper[MAY_PDF_OFFSET:MAY_PDF_OFFSET + 8], b"%PDF-1.3")
        self.assertEqual(wrapper.rfind(b"%%EOF"), MAY_EOF_OFFSET)
        # Exercise the exact retained RTFD wrapper bytes through the normal parser.
        expected = _read_vectors("may2021_city_17field.jsonl.gz", MAY_ORACLE_SHA, MAY_FIELDS)
        parsed = list(city_reports.parse_city_pdf(wrapper, date(2021, 5, 1)))
        self.assertEqual(len(parsed), 194)
        self.assertEqual(len({row[0] for row in parsed}), 194)
        actual = [dict(zip(MAY_FIELDS, row)) for row in parsed]
        for row in actual:
            row["observed_on"] = row["observed_on"].isoformat()
            for field in ("quantity", "min_price", "max_price", "min_unit_price", "max_unit_price"):
                row[field] = _decimal_text(row[field])
        actual.sort(key=lambda row: row["source_locator"])
        expected.sort(key=lambda row: row["source_locator"])
        mismatch = _first_diff(expected, actual, MAY_FIELDS)
        self.assertIsNone(mismatch, mismatch)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Offline source-bound Corabastos regression against nine originals.

Run from the repository root with .venv/bin/python -m unittest on this module.
It exercises maintained parsing against bundled public PDFs and independent
read-only SQL exports. No database, network, OCR, provider, or timer is used.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import unittest

from pipelines.ingestion import (
    colombia_sources,
    corabastos_semantic_correction as semantic,
    worker,
)

HERE = Path(__file__).resolve().parent / "testdata" / "corabastos_semantic_correction"
MANIFEST = json.loads((HERE / "TEST_INPUT_MANIFEST.json").read_text())
ALLOWLIST = json.loads((HERE / "expected-diff-allowlist.json").read_text())
KIND = semantic.KIND
QUOTE_FIELDS = (
    "document_id", "source_locator", "parser_version", "quote_key", "product_id",
    "product_name", "category", "publisher", "series", "basis", "currency", "unit",
    "market", "observed_on", "period_start", "price", "min_price", "max_price",
    "source_page", "details",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_row(value: dict) -> dict:
    row = deepcopy(value)
    for field in ("price", "min_price", "max_price"):
        if row.get(field) is not None:
            row[field] = Decimal(str(row[field]))
    if isinstance(row.get("observed_on"), date):
        row["observed_on"] = row["observed_on"].isoformat()
    if isinstance(row.get("period_start"), date):
        row["period_start"] = row["period_start"].isoformat()
    return row


def _stored_quote(parsed: dict, document_id: str, revision: str) -> dict:
    identity = {
        key: parsed[key]
        for key in ("product_id", "series", "market", "currency", "unit", "basis")
    }
    identity["dimensions"] = parsed.get("identity_dimensions", {})
    quote_key = hashlib.sha256(
        json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    details = {**parsed.get("details", {}), "identity_dimensions": identity["dimensions"]}
    day = parsed["date"]
    if isinstance(day, str):
        day = date.fromisoformat(day)
    period_start = parsed.get("period_start")
    if isinstance(period_start, str):
        period_start = date.fromisoformat(period_start)
    return {
        "document_id": document_id,
        "source_locator": parsed["source_locator"],
        "parser_version": revision,
        "quote_key": quote_key,
        "product_id": parsed["product_id"],
        "product_name": parsed["product_name"],
        "category": parsed["category"],
        "publisher": parsed["publisher"],
        "series": parsed["series"],
        "basis": parsed["basis"],
        "currency": parsed["currency"],
        "unit": parsed["unit"],
        "market": parsed["market"],
        "observed_on": day,
        "period_start": period_start,
        "price": parsed["price"],
        "min_price": parsed.get("min"),
        "max_price": parsed.get("max"),
        "source_page": parsed.get("source_page") or details.get("source_page"),
        "details": details,
    }


def _fixtures():
    result = []
    for spec in MANIFEST["fixtures"]:
        body = (HERE / spec["body_fixture"]).read_bytes()
        export_bytes = (HERE / spec["prior_export_fixture"]).read_bytes()
        exported = json.loads(export_bytes)
        if len(body) != spec["body_bytes"] or _sha(body) != spec["body_sha256"]:
            raise AssertionError(f"source PDF pin changed: {spec['document_id']}")
        if _sha(export_bytes) != spec["prior_export_sha256"]:
            raise AssertionError(f"independent prior SQL export pin changed: {spec['document_id']}")
        quotes = exported.get("quotes", [])
        if (exported.get("document_id") != spec["document_id"] or len(quotes) != 350
                or any(not row.get("xmin") for row in quotes)
                or any(row.get("document_id") != spec["document_id"] for row in quotes)):
            raise AssertionError("prior SQL export is not the expected full 350-row xmin-bound cohort")
        result.append((spec, body, exported))
    return result


class CorabastosSemanticSourceVectors(unittest.TestCase):
    def test_fixture_provenance_and_source_pins(self):
        def verify_receipt(key):
            spec = MANIFEST[key]
            data = (HERE / spec["fixture"]).read_bytes()
            self.assertEqual(_sha(data), spec["sha256"])
            return json.loads(data)

        self.assertEqual(_sha((HERE / "expected-diff-allowlist.json").read_bytes()),
                         MANIFEST["expected_diff_sha256"])
        integration = verify_receipt("root_integration_receipt")
        self.assertTrue(integration["integrated"])
        self.assertEqual(integration["runtime_files"], 117)
        self.assertEqual(integration["release_fingerprint"], "4a555596a1bfd1e98507e6b5a69baa121516017d16cf54da7782013861be69a9")
        # The receipt pins the historical capture that produced the fixtures.
        # Runtime/schema freezing belongs to release qualification; unrelated
        # future modules must not invalidate these source regressions.
        self.assertEqual(integration["schema_sha256"], MANIFEST["sql_sha256"])

        downloaded = verify_receipt("source_download_receipt")
        readonly = verify_receipt("prior_readonly_receipt")
        self.assertEqual(readonly["transaction"], "repeatable-read read-only, rolled back")
        self.assertEqual(readonly["production_writes"], 0)
        source_records = {item["url"]: item for item in downloaded["download_attempts"]}
        prior_records = {item["url"]: item for item in readonly["documents"]}
        for spec in MANIFEST["fixtures"]:
            source = source_records[spec["url"]]
            prior = prior_records[spec["url"]]
            self.assertEqual((source["status"], source["bytes"], source["sha256"]),
                             (200, spec["body_bytes"], spec["document_id"]))
            self.assertEqual((prior["document_id"], prior["quotes"], prior["sha256"]),
                             (spec["document_id"], 350, spec["prior_export_sha256"]))

    @classmethod
    def setUpClass(cls):
        cls.cases = _fixtures()
        cls.diff = ALLOWLIST
        cls.moves = {
            (row["document_id"], row["old_locator"]): row["new_locator"]
            for row in ALLOWLIST["locator_retirement_mappings"]
        }
        cls.semantic_targets = {
            (row["prior_quote"]["document_id"], row["prior_quote"]["source_locator"]): row
            for row in ALLOWLIST["quantity_and_label_row_diffs"]
        }
        cls.label_targets = {
            (entry["document_id"], entry["physical_locator_prefix"] + str(column)): entry
            for entry in ALLOWLIST["february_4_label_allowlist"]
            for column in entry["quality_columns"]
        }

    def test_source_bound_full_350_rows_match_independent_v2_exports(self):
        self.assertEqual(MANIFEST["runtime_release_files"], 117)
        self.assertEqual(MANIFEST["sql_files"], 78)
        self.assertEqual(len(self.cases), 9)
        self.assertEqual(len(self.moves), 132)
        self.assertEqual(len(self.semantic_targets), 36)
        self.assertEqual(len(self.label_targets), 4)
        changed_quantity_rows = changed_label_rows = 0
        for spec, body, exported in self.cases:
            with self.subTest(source=spec["url"]):
                token = semantic.select_mode(KIND, spec["url"], spec["document_id"], body)
                self.assertTrue(semantic.accepts_mode(token, KIND, spec["url"], body))
                parsed = list(colombia_sources.parse(body, spec["url"], KIND, semantic_mode=token))
                source_spec = semantic.SOURCES[spec["url"]]
                self.assertEqual(len(semantic.assert_native_v6_token_vector(source_spec, parsed)), 350)
                revision = worker.asset_parser_version(KIND, spec["url"])
                current = [_stored_quote(row, spec["document_id"], revision) for row in parsed]
                by_locator = {row["source_locator"]: row for row in current}
                self.assertEqual(len(by_locator), 350, "new vector must have unique locators")
                prior_by_locator = {row["source_locator"]: row for row in exported["quotes"]}
                self.assertEqual(len(prior_by_locator), 350, "prior vector must have unique locators")
                self.assertEqual(len(current), 350)
                for old_locator, prior_raw in prior_by_locator.items():
                    target = self.semantic_targets.get((spec["document_id"], old_locator))
                    label = self.label_targets.get((spec["document_id"], old_locator))
                    new_locator = self.moves.get((spec["document_id"], old_locator), old_locator)
                    actual = by_locator.get(new_locator)
                    self.assertIsNotNone(actual, f"missing replacement at {new_locator}")
                    prior = {key: deepcopy(prior_raw[key]) for key in QUOTE_FIELDS}
                    prior["source_locator"] = new_locator
                    prior["parser_version"] = revision
                    prior_details = prior["details"]
                    actual_details = actual["details"]
                    prior_details["parser_version"] = actual_details["parser_version"]
                    prior_details["original_price"] = actual_details["original_price"]
                    if target:
                        self.assertEqual(prior_details["quantity"], target["prior_quote"]["details"]["quantity"])
                        self.assertEqual(actual_details["quantity"], 1000.0)
                        self.assertEqual(actual_details["identity_dimensions"]["quantity"], 1000.0)
                        self.assertEqual(actual_details["quantity_as_published"], "1.000")
                        prior_details["quantity"] = actual_details["quantity"]
                        prior_details.setdefault("identity_dimensions", {})["quantity"] = 1000.0
                        prior_details["quantity_as_published"] = "1.000"
                        prior["quote_key"] = actual["quote_key"]
                        changed_quantity_rows += 1
                    else:
                        self.assertNotIn("quantity_as_published", actual_details)
                        self.assertEqual(prior_details["quantity"], actual_details["quantity"])
                    if label:
                        self.assertEqual(actual["product_id"], label["new_product_id"])
                        self.assertEqual(actual["product_name"], label["new_product_name"])
                        self.assertEqual(actual_details["original_product"], label["new_original_product"])
                        prior["product_id"] = actual["product_id"]
                        prior["product_name"] = actual["product_name"]
                        prior["quote_key"] = actual["quote_key"]
                        prior_details["original_product"] = actual_details["original_product"]
                        changed_label_rows += 1
                    self.assertEqual(set(prior), set(QUOTE_FIELDS))
                    self.assertEqual(_canonical_row(prior), _canonical_row(actual),
                                     f"unapproved full-row difference at {old_locator}")
                    # Price and all source basis fields remain exact in both targets.
                    self.assertEqual(Decimal(str(prior_raw["price"])), Decimal(str(actual["price"])))
                    self.assertEqual(prior_raw["unit"], actual["unit"])
                    self.assertEqual(prior_raw["basis"], actual["basis"])
        self.assertEqual(changed_quantity_rows, 36)
        self.assertEqual(changed_label_rows, 4)

    def test_ordinary_parser_and_semantic_capability_are_narrow(self):
        for spec, body, _exported in self.cases:
            with self.subTest(source=spec["url"]):
                # The ordinary/default path keeps the old printed 1.000 quantity
                # and the Feb 4 legacy label. Correction requires the exact token.
                default = list(colombia_sources.parse(body, spec["url"], KIND))
                self.assertEqual(len(default), 350)
                default_by_locator = {row["source_locator"]: row for row in default}
                target_rows = {
                    old_locator: default_by_locator.get(
                        self.moves.get((spec["document_id"], old_locator), old_locator)
                    )
                    for did, old_locator in self.semantic_targets
                    if did == spec["document_id"]
                }
                self.assertEqual(len(target_rows), 4)
                self.assertTrue(all(row is not None and row["details"]["quantity"] == 1.0 and
                                    "quantity_as_published" not in row["details"]
                                    for row in target_rows.values()))
                if spec["document_id"].startswith("0f1f1799"):
                    originals = {
                        row["physical_locator_prefix"] + "1": row["old_original_product"]
                        for row in ALLOWLIST["february_4_label_allowlist"]
                    }
                    self.assertEqual(
                        {old_locator: target_rows[old_locator]["details"]["original_product"]
                         for old_locator in originals},
                        originals,
                    )
                self.assertIsNone(semantic.select_mode(KIND, spec["url"] + ".unlisted", spec["document_id"], body))
                self.assertFalse(semantic.accepts_mode(
                    semantic.select_mode(KIND, spec["url"], spec["document_id"], body),
                    KIND, spec["url"] + ".unlisted", body,
                ))
                with self.assertRaises(ValueError):
                    semantic.select_mode(KIND, spec["url"], spec["document_id"], body + b"\n")

    def test_all_132_retirement_reviews_are_source_bound_to_full_prior_sql_rows(self):
        from datetime import date
        moves = {(row["document_id"], row["old_locator"]): row["new_locator"]
                 for row in ALLOWLIST["locator_retirement_mappings"]}
        observed = 0
        for spec, _body, exported in self.cases:
            source_spec = semantic.SOURCES[spec["url"]]
            revision = worker.asset_parser_version(KIND, spec["url"])
            prior_tuples = []
            prior_by_locator = {}
            for raw in exported["quotes"]:
                quote = {field: raw[field] for field in QUOTE_FIELDS}
                prior_by_locator[quote["source_locator"]] = quote
                tuple_row = []
                for field in semantic.QUOTE_COLUMNS:
                    value = quote[field]
                    if field in {"observed_on", "period_start"} and value is not None:
                        value = date.fromisoformat(value)
                    elif field in {"price", "min_price", "max_price"} and value is not None:
                        value = Decimal(str(value))
                    tuple_row.append(value)
                prior_tuples.append(tuple(tuple_row))
            reviews = semantic.make_retirement_reviews(source_spec, prior_tuples, revision, ALLOWLIST)
            expected = {old: new for (did, old), new in moves.items() if did == spec["document_id"]}
            self.assertEqual(len(reviews), len(expected))
            for document_id, old_locator, parser_version, record, reason in reviews:
                self.assertEqual(document_id, spec["document_id"])
                self.assertEqual(parser_version, revision)
                self.assertEqual(reason, "Source-bound native Corabastos geometry/semantic revision; prior row retained")
                payload = record.obj
                self.assertEqual(payload["retired_by_verified_source"], spec["document_id"])
                self.assertEqual(payload["replacement_locator"], expected[old_locator])
                self.assertEqual(_canonical_row(payload["prior_quote"]),
                                 _canonical_row(prior_by_locator[old_locator]))
                observed += 1
        self.assertEqual(observed, 132)

    def test_ambiguous_grouping_and_other_units_fail_closed(self):
        quantity = colombia_sources._corabastos_quantity
        self.assertEqual(quantity("1.000", legacy=True, presentation="TONELADA",
                                  published_unit="KILO", semantic_correction=True), 1000.0)
        for raw, presentation, unit in (
            ("0.500", "TONELADA", "KILO"),
            ("1.250", "TONELADA", "KILO"),
            ("1.000", "BULTO", "KILO"),
            ("1.000", "TONELADA", "TONELADA"),
            ("1.0000", "TONELADA", "KILO"),
            ("1e3", "TONELADA", "KILO"),
        ):
            with self.subTest(raw=raw, presentation=presentation, unit=unit):
                with self.assertRaises(ValueError):
                    quantity(raw, legacy=True, presentation=presentation,
                             published_unit=unit, semantic_correction=True)
        # Without the exact semantic capability, the same printed text retains
        # the ordinary parser's historical decimal interpretation.
        self.assertEqual(quantity("1.000", legacy=True, presentation="TONELADA",
                                  published_unit="KILO", semantic_correction=False), 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

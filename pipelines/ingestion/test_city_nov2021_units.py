"""Native regression for exact-source-unit identity in the Nov 16, 2021 ZIP.

When promoted, place this module beside testdata/nov16_city_unit_identity.
The 5.67 MB ZIP is stored once; child PDFs are reconstructed by SHA-256.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
import unittest
import zipfile
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from . import city_category_overlay, city_reports
from .test_city_ocr_fallback import HEAD, TABLE

HERE = Path(__file__).resolve().parent
DATA = HERE / "testdata" / "nov16_city_unit_identity"
PARENT_SHA = "e4a8aa221892eb1d7eebb80e23e6d5419d406b87fa4243f205ee1f32b1fa8d10"
DAY = date(2021, 11, 16)
TARGET_IDS = {
    "4ced8283b62ced0ffbf1cdb91e545a810fa2da4b13af52b2287594f547565078",
    "298f734fe2b12f4ed4ee8c9cc35541916a30d76926a36c22e83dcbf377d16c0c",
}


def _decimal(value):
    return None if value is None else format(Decimal(str(value)).normalize(), "f")


def _vector(row):
    return {
        "source_locator": row[0],
        "source_page": row[16],
        "source_table": int(row[0].split(",table ")[1].split(",")[0]),
        "source_row": int(row[0].split(",row ")[1].split(",")[0]),
        "observed_on": row[1].isoformat(),
        "product_slug": row[2],
        "product_name": row[3],
        "market_name": row[4],
        "classification": row[5],
        "presentation": row[6],
        "quantity": _decimal(row[7]),
        "source_unit": row[8],
        "normalized_unit": row[13],
        "normalization_factor": _decimal(
            Decimal(".001") if row[8].casefold() == "gramo" else Decimal(1)
        ),
        "round_number": row[9],
        "round_label": row[10],
        "min_price": _decimal(row[11]),
        "max_price": _decimal(row[12]),
        "normalized_min": _decimal(row[14]),
        "normalized_max": _decimal(row[15]),
        "quantity_derivation": (
            "explicit_quantity"
            if row[6] != row[8] or row[7] != 1
            else "exact_source_unit_identity"
        ),
    }


def _synthetic_section(label, price_cells=("0", "0", "", ""), source_id=None):
    table = [row[:] for row in TABLE[:2]]
    table.append([label, "", "", *price_cells])
    table.append(TABLE[-1][:])
    page = SimpleNamespace(
        extract_text=lambda: HEAD,
        extract_tables=lambda: [table],
        close=lambda: None,
    )
    return list(city_reports.parse_city_pages(
        [page], date(2026, 9, 7), source_document_id=source_id or next(iter(TARGET_IDS))
    ))


def _baseline_row(row):
    fields = city_reports._BULK_TABLES["regional_price"][0].split(",")[1:]
    out = {}
    for field in fields:
        value = row[field]
        if field == "observed_on":
            value = date.fromisoformat(value) if isinstance(value, str) else value
            value = value.isoformat()
        elif field in {
            "quantity", "min_price", "max_price", "min_unit_price", "max_unit_price"
        }:
            value = _decimal(value)
        out[field] = value
    return out


def _synthetic_row(presentation, units, round1=("85.000", "87.000"), round2=("0", "0")):
    # Keep a simple top-level heading only; the source-unit test is unrelated to
    # the synthetic Cítricos subheading used by the shared OCR fixture.
    table = [TABLE[0][:], TABLE[1][:], TABLE[2][:], TABLE[-1][:]]
    table[-1][1] = presentation
    table[-1][2] = units
    table[-1][3:7] = [*round1, *round2]
    page = SimpleNamespace(
        extract_text=lambda: HEAD,
        extract_tables=lambda: [table],
        close=lambda: None,
    )
    return list(city_reports.parse_city_pages(
        [page], date(2026, 9, 7), source_document_id=next(iter(TARGET_IDS))
    ))


class Nov2021NativeUnitIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.version_info[:3] != (3, 11, 9):
            raise RuntimeError("Use the pinned Python 3.11.9 runtime for ZIP member identity")
        cls.fixture = json.loads((DATA / "baseline.json").read_text())
        cls.oracle = json.loads((DATA / "native_source_oracle.json").read_text())
        cls.physical = json.loads((DATA / "physical_category_oracle.json").read_text())
        cls.parent = (DATA / "parent.zip").read_bytes()
        if hashlib.sha256(cls.parent).hexdigest() != PARENT_SHA:
            raise AssertionError("retained ZIP SHA changed")
        with zipfile.ZipFile(io.BytesIO(cls.parent)) as archive:
            cls.members = {
                hashlib.sha256(archive.read(info)).hexdigest(): (
                    info.filename, archive.read(info)
                )
                for info in archive.infolist()
                if not info.is_dir() and info.filename.lower().endswith(".pdf")
            }
        if len(cls.members) != 7:
            raise AssertionError(f"expected seven exact PDF members, found {len(cls.members)}")

    def test_full_native_vectors_overlay_only_categories_and_preserve_base_rows(self):
        expected_new = {
            item["source"]["child_document_id"]: item
            for item in self.oracle["fixtures"].values()
        }
        physical_by_source = {
            (item["document_id"], item["source_locator"]): item
            for item in self.physical["physical_row_classifications"]
        }
        metadata_by_source = {item["document_id"]: item for item in self.fixture["members_and_source_bytes"]}
        raw_by_doc = defaultdict(list)
        classes_by_doc = defaultdict(dict)
        for row in self.fixture["regional_price_rows"]:
            raw_by_doc[row["document_id"]].append(row)
        for row in self.fixture["regional_classification_rows"]:
            classes_by_doc[row["document_id"]][row["source_locator"]] = row["category_path"]

        observed_total = 0
        overlay_counts = {}
        for did, (entry_name, content) in self.members.items():
            with self.subTest(source=entry_name):
                parsed = list(city_reports.parse_city_pdf(content, DAY))
                observed_total += len(parsed)
                physical_rows = [
                    physical_by_source[(did, row[0])] for row in parsed
                ]
                self.assertEqual(len(physical_rows), len(parsed))
                for row, source in zip(parsed, physical_rows):
                    self.assertEqual(row[5], source["physical_group_heading"], row[0])

                if did in expected_new:
                    expected = expected_new[did]
                    self.assertEqual(len(parsed), expected["quote_vector_count"])
                    self.assertEqual([_vector(row) for row in parsed], expected["quote_vectors"])
                    continue

                prior = {row["source_locator"]: row for row in raw_by_doc[did]}
                self.assertEqual(set(prior), {row[0] for row in parsed})
                for row in parsed:
                    actual = dict(zip(
                        city_reports._BULK_TABLES["regional_price"][0].split(",")[1:],
                        row,
                    ))
                    old = _baseline_row(prior[row[0]])
                    actual_typed = _baseline_row(actual)
                    self.assertEqual(
                        {key: value for key, value in actual_typed.items() if key != "category"},
                        {key: value for key, value in old.items() if key != "category"},
                        row[0],
                    )

                changed = [
                    item for item in physical_rows
                    if item["previous_parser_classification"]
                    != item["physical_group_heading"]
                ]
                if changed:
                    meta = metadata_by_source[did]
                    stored_rows = []
                    for source_row in raw_by_doc[did]:
                        item = _baseline_row(source_row)
                        item["observed_on"] = date.fromisoformat(item["observed_on"])
                        for field in ("quantity", "min_price", "max_price", "min_unit_price", "max_unit_price"):
                            if item[field] is not None:
                                item[field] = Decimal(item[field])
                        stored_rows.append(item)
                    native = list(city_reports.parse_city_pdf(content, DAY))
                    proposal = city_category_overlay.plan(
                        parent_zip=self.parent,
                        archive_id=PARENT_SHA,
                        entry_name=entry_name,
                        child_pdf=content,
                        document_id=did,
                        source_url=meta["source_url"],
                        original_metadata={
                            "kind": meta["kind"],
                            "source_url": meta["source_url"],
                            "metadata": meta["metadata"],
                        },
                        native_rows=native,
                        stored_rows=stored_rows,
                        classifications=classes_by_doc[did],
                        product_corrections={},
                        existing_conflicts=0,
                        parser_code_sha256=hashlib.sha256(
                            Path(city_reports.__file__).read_bytes()
                        ).hexdigest(),
                    )
                    self.assertEqual(proposal["proof"]["raw_row_count"], len(prior))
                    self.assertEqual(len(proposal["rows"]), len(changed))
                    self.assertEqual(
                        {item["rule"] for item in proposal["rows"]},
                        {"literal-top-level-heading"},
                    )
                    verified_shape = city_category_overlay._verified_category_mapping(
                        proposal["rows"]
                    )
                    self.assertEqual(set(verified_shape), {
                        item["source_locator"] for item in proposal["rows"]
                    })
                    self.assertTrue(all(
                        isinstance(value, dict)
                        and value["rule"] == "literal-top-level-heading"
                        and value["category_path"]
                        for value in verified_shape.values()
                    ))
                    overlay_counts[did] = len(proposal["rows"])
                else:
                    for row in parsed:
                        self.assertEqual(
                            _baseline_row(dict(zip(
                                city_reports._BULK_TABLES["regional_price"][0].split(",")[1:],
                                row,
                            )))["category"],
                            _baseline_row(prior[row[0]])["category"],
                            row[0],
                        )

        self.assertEqual(set(expected_new), TARGET_IDS)
        legacy_shape = city_category_overlay._verified_category_mapping([{
            "source_locator": "legacy-leaf-locator",
            "old_category": "Frutas",
            "corrected_category": "Frutas > Papas",
            "category_path": ["Frutas", "Papas"],
            "rule": "literal-leaf",
        }])
        self.assertEqual(legacy_shape, {
            "legacy-leaf-locator": ("Frutas", "Frutas > Papas")
        })
        self.assertEqual(sum(len(v["quote_vectors"]) for v in expected_new.values()), 144)
        self.assertEqual(len(self.fixture["regional_price_rows"]), 531)
        self.assertEqual(observed_total, 675)
        self.assertEqual(sorted(overlay_counts.values()), [34, 50, 56])
        self.assertEqual(sum(overlay_counts.values()), 140)
        self.assertEqual(
            sum(not item["classification_matches_physical_header"]
                for item in self.physical["physical_row_classifications"]),
            180,
        )
        self.assertEqual(len(classes_by_doc), 5)
        self.assertEqual(len(self.fixture["regional_classification_rows"]), 531)

    def test_only_exact_unit_identity_is_inferred_and_rounds_remain_literal(self):
        kilogram = _synthetic_row("Kilogramo", "Kilogramo")[0]
        self.assertEqual(kilogram[7:9], (Decimal(1), "Kilogramo"))
        self.assertEqual(kilogram[11:16], (Decimal(85000), Decimal(87000), "kg", Decimal(85000), Decimal(87000)))

        accented = _synthetic_row("KILÓGRAMO", "kilogramo")[0]
        self.assertEqual(accented[7:9], (Decimal(1), "kilogramo"))
        self.assertEqual(accented[13], "kg")

        arroba = _synthetic_row("Arroba", "Arroba")[0]
        self.assertEqual(arroba[7:9], (Decimal(1), "Arroba"))
        self.assertEqual(arroba[11:16], (Decimal(85000), Decimal(87000), "Arroba", None, None))

        # A packaged product remains quantity 50 kg; both rounds and COP prices
        # retain their existing normalization behavior.
        bulto = _synthetic_row("Bulto", "50 Kilogramo", ("340.000", "350.000"), ("340.000", "350.000"))
        self.assertEqual(len(bulto), 2)
        self.assertEqual(bulto[0][7:9], (Decimal(50), "Kilogramo"))
        self.assertEqual(bulto[0][11:16], (Decimal(340000), Decimal(350000), "kg", Decimal(6800), Decimal(7000)))
        self.assertEqual((bulto[0][9], bulto[1][9]), (1, 2))

        # Zero/blank Ronda 1 remains unavailable, while Ronda 2 is still read.
        only_second = _synthetic_row("Kilogramo", "Kilogramo", ("0", ""), ("85.000", "87.000"))
        self.assertEqual(len(only_second), 1)
        self.assertEqual(only_second[0][9], 2)
        self.assertEqual(only_second[0][11:13], (Decimal(85000), Decimal(87000)))

    def test_unit_identity_repair_is_scoped_to_exact_source_members(self):
        table = [row[:] for row in TABLE]
        table[-1][1:3] = ["Kilogramo", "Kilogramo"]
        page = SimpleNamespace(extract_text=lambda: HEAD, extract_tables=lambda: [table], close=lambda: None)
        with self.assertRaisesRegex(ValueError, "Unknown city quantity"):
            list(city_reports.parse_city_pages(
                [page], date(2026, 9, 7), source_document_id="0" * 64
            ))

    def test_known_zero_header_is_not_a_quote_and_unknown_rows_stay_reviewable(self):
        parsed = _synthetic_section("Tuberculos raices platanos")
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0][5], "Tuberculos raices platanos")
        with self.assertRaisesRegex(ValueError, "Unquantified city row has price data"):
            _synthetic_section("Huevos", ("12000", "13000", "", ""))
        with self.assertRaisesRegex(ValueError, "Unrecognized city section heading"):
            _synthetic_section("Producto sin unidades")

    def test_missing_or_ambiguous_units_stay_reviewable(self):
        for presentation, units in (
            ("Atado", "Atado"),
            ("Kilogramo", "Gramo"),
            ("Bolsa", "Arroba"),
            ("Kilogramo", ""),
            ("", "Kilogramo"),
        ):
            with self.subTest(presentation=presentation, units=units):
                with self.assertRaisesRegex(ValueError, "Unknown city quantity"):
                    _synthetic_row(presentation, units)
        with self.assertRaisesRegex(ValueError, "Nonpositive city package"):
            _synthetic_row("Kilogramo", "0Kilogramo")


if __name__ == "__main__":
    unittest.main()

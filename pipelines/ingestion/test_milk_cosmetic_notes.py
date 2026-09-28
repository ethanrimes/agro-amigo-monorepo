"""Exact harmless OCR annotations must not mask uncertain milk chart labels."""

import hashlib
import json
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from . import milk_macroregions as milk
from . import test_milk_macroregions as fixtures

CHART, OLD, reading = fixtures.CHART, fixtures.OLD, fixtures.reading

FOOTER = "The source line 'Fuente: DANE, SIPSA' is partially cropped at the bottom of the image."
CORPUS = Path(
    "artifacts/app-data-audit-2026-09-27/planning/milk-macroregions/corpus-20260928T010052Z"
)


def annotated():
    value = reading()
    value["text"] += "\nFuente: DANE, SIPSA"
    value["review_notes"] = [FOOTER]
    return value


class CosmeticNotes(unittest.TestCase):
    def test_only_agreeing_pair_accepts_and_preserves_both_original_note_arrays(self):
        pair = [annotated(), reading()]
        before = deepcopy(pair)
        with self.assertRaisesRegex(ValueError, "uncertainty"):
            milk.parse_reading(CHART, pair[0])
        rows = milk.paired_rows(CHART, pair)
        self.assertEqual(pair, before)
        self.assertEqual(len(rows), 10)
        self.assertEqual(
            [r["price"] for r in rows],
            [r["price"] for r in milk.parse_reading(CHART, reading())],
        )
        for row in rows:
            self.assertEqual(row["details"]["original_review_notes"], [[FOOTER], []])
            self.assertEqual(
                row["details"]["accepted_cosmetic_note_categories"],
                [["publisher-footer-crop"], []],
            )
        rows[0]["details"]["original_review_notes"][0].append("output mutation")
        self.assertEqual(pair, before)
        self.assertEqual(rows[1]["details"]["original_review_notes"], [[FOOTER], []])

    def test_unknown_or_extended_notes_remain_review_even_if_pairs_agree(self):
        for note in [
            "The chart is clear.",
            FOOTER + " One digit may be 8 or 9.",
            "The price unit may be per kilogram.",
            "The February year is uncertain.",
            "Region names overlap.",
            "The legend colors may be swapped.",
            "All values are clear except the final price.",
            "The source line is cropped.",
            "The bar binding is uncertain.",
        ]:
            first = annotated()
            first["review_notes"] = [note]
            with self.subTest(note=note), self.assertRaises(ValueError):
                milk.paired_rows(CHART, [first, deepcopy(first)])
        for notes in [FOOTER, None, [None], [FOOTER, "Unclear digit"]]:
            first = annotated()
            first["review_notes"] = notes
            with self.subTest(notes=notes), self.assertRaises(ValueError):
                milk.paired_rows(CHART, [first, deepcopy(first)])

    def test_annotation_cannot_bypass_price_unit_header_date_region_or_basis_guards(
        self,
    ):
        mutations = [
            lambda r: r["tables"][0][1].__setitem__(1, "1.?93"),
            lambda r: r["tables"][0][0].__setitem__(0, "Producto"),
            lambda r: r["tables"][0][0].__setitem__(1, "Octubre 2025"),
            lambda r: r["tables"][0][1].__setitem__(0, "Región desconocida"),
            lambda r: r.update(
                text=r["text"].replace("Precio por litro", "Precio por kilogramo")
            ),
            lambda r: r.update(
                text=r["text"].replace("diciembre de 2025", "diciembre de 2024")
            ),
            lambda r: r.update(text=r["text"].replace("Fuente: DANE, SIPSA", "")),
        ]
        for mutate in mutations:
            first = annotated()
            mutate(first)
            with self.subTest(reading=first), self.assertRaises(ValueError):
                milk.paired_rows(CHART, [first, deepcopy(first)])
        with self.assertRaisesRegex(ValueError, "basis"):
            milk.paired_rows(
                replace(CHART, basis_evidence="precio estimado"),
                [annotated(), annotated()],
            )
        changed = annotated()
        changed["tables"][0][1][1] = "1.894"
        with self.assertRaisesRegex(ValueError, "disagree"):
            milk.paired_rows(CHART, [annotated(), changed])

    def test_specific_spelling_and_spacing_notes_require_the_stated_context(self):
        for note in [
            "The subtitle in the image contains the spelling 'macroregiones' with a single 'r'.",
            "The legend label for February is printed as 'Febrero2025' without a space.",
        ]:
            first = reading()
            first["review_notes"] = [note]
            with self.subTest(note=note), self.assertRaises(ValueError):
                milk.paired_rows(CHART, [first, deepcopy(first)])

    def test_new_task_version_preserves_cached_reading_provider_version(self):
        from .worker import parser_version

        self.assertEqual(milk.VERSION, "milk-macroregions-v2")
        self.assertIn(milk.VERSION, CHART.locator)
        self.assertTrue(parser_version("milk-pdf").endswith(":" + milk.VERSION))
        self.assertEqual(parser_version(milk.KIND), milk.VERSION)
        harness = fixtures.MilkMacroregionDrain()
        result, db, publish, provider = harness.run_chart([annotated(), annotated()])
        self.assertEqual((result["processed"], result["review"]), (1, 0))
        self.assertEqual(db.updates[-1][0], "published")
        publish.assert_called_once()
        provider.assert_not_called()

    def test_comma_thousands_requires_all_ten_complete_groups(self):
        valid = reading()
        for row in valid["tables"][0][1:]:
            row[1:] = [v.replace(".", ",") for v in row[1:]]
        rows = milk.paired_rows(CHART, [valid, deepcopy(valid)])
        self.assertEqual(
            [r["price"] for r in rows],
            [1893, 1930, 2094, 2113, 2102, 2108, 1971, 1998, 1911, 1922],
        )
        self.assertEqual(rows[0]["details"]["literal_price"], "1,893")
        for bad in [
            "1,89",
            "1,893.25",
            "1.893,25",
            "1,89,3",
            "1893",
            "1.893",
            "0,893",
            "NaN",
            "Infinity",
        ]:
            value = deepcopy(valid)
            value["tables"][0][1][1] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                milk.paired_rows(CHART, [value, deepcopy(value)])
        changed = deepcopy(valid)
        changed["tables"][0][1][1] = "1,894"
        with self.assertRaisesRegex(ValueError, "disagree"):
            milk.paired_rows(CHART, [valid, changed])
        # Format difference alone must not change the mathematical price.
        self.assertEqual(
            [r["price"] for r in milk.paired_rows(CHART, [valid, reading()])],
            [r["price"] for r in rows],
        )


@unittest.skipUnless(
    (CORPUS / "report.json").exists(), "Retained real paired readings required"
)
class RealCosmeticPairs(unittest.TestCase):
    def test_retained_pairs_keep_all_literal_values_and_cached_bytes(self):
        report = json.loads((CORPUS / "report.json").read_text())
        sources = {r["bulletin_period"]: r for r in report["sources"]}
        oracles = {
            r["document_id"]: r["expected_quotes"]
            for r in json.loads(
                Path(
                    "artifacts/milk-macroregion-publication/all-source-oracles.json"
                ).read_text()
            )
        }

        def signature(rows):
            fields = (
                "product_id",
                "product_name",
                "category",
                "publisher",
                "series",
                "basis",
                "currency",
                "unit",
                "market",
                "date",
                "period_start",
                "price",
                "source_page",
                "source_locator",
                "identity_dimensions",
            )
            values = [{k: r[k] for k in fields} for r in rows]
            return json.loads(
                json.dumps(
                    sorted(values, key=lambda r: (r["market"], str(r["date"]))),
                    default=str,
                )
            )

        count = 0
        self.assertEqual(len(sources), 16)
        for month in sorted(sources):
            with self.subTest(month=month):
                paths = [CORPUS / f"{month}-reading-{i}.json" for i in range(2)]
                original_bytes = [p.read_bytes() for p in paths]
                pair = [json.loads(b) for b in original_bytes]
                did = sources[month]["document_id"]
                pdf = (OLD / (did + ".pdf")).read_bytes()
                self.assertEqual(hashlib.sha256(pdf).hexdigest(), did)
                chart = milk.inspect(pdf, date.fromisoformat(month))
                rows = milk.paired_rows(chart, pair)
                self.assertEqual(len(rows), 10)
                self.assertEqual(signature(rows), signature(oracles[did]))
                # Apart from October's source-verified separator format, the only new behavior is note acceptance; every literal value,
                # identity, month, unit and basis equals the strict numeric oracle.
                clean = [{**r, "review_notes": []} for r in pair]
                expected = milk.paired_rows(chart, clean)
                for actual, prior in zip(rows, expected):
                    trimmed = deepcopy(actual)
                    trimmed["details"].pop("original_review_notes", None)
                    trimmed["details"].pop("accepted_cosmetic_note_categories", None)
                    self.assertEqual(trimmed, prior)
                if any(r["review_notes"] for r in pair):
                    self.assertEqual(
                        rows[0]["details"]["original_review_notes"],
                        [r["review_notes"] for r in pair],
                    )
                self.assertEqual([p.read_bytes() for p in paths], original_bytes)
                count += len(rows)
        self.assertEqual(count, 160)

    def test_versioned_locator_keeps_identical_crop_and_cached_reading_key(self):
        from . import ocr

        report = json.loads((CORPUS / "report.json").read_text())
        source = next(
            r for r in report["sources"] if r["bulletin_period"] == "2025-01-31"
        )
        did = source["document_id"]
        pdf = (OLD / (did + ".pdf")).read_bytes()
        captured = []

        def record(_db, document_id, locator, image, kind, page):
            captured.append(
                (
                    document_id,
                    locator,
                    hashlib.sha256(ocr.png_bytes(image)).hexdigest(),
                    ocr.VERSION,
                    kind,
                    page,
                )
            )
            return True

        with patch.object(ocr, "enqueue_image", side_effect=record):
            for version in ["milk-macroregions-v1", "milk-macroregions-v2"]:
                with patch.object(milk, "VERSION", version):
                    milk.enqueue(None, pdf, did, date(2025, 1, 31))
        self.assertNotEqual(captured[0][1], captured[1][1])
        self.assertEqual(captured[0][2:], captured[1][2:])
        # Cross-platform renderers need not match Linux PNG bytes; within the
        # unchanged deployment, the version bump alone leaves the cache key intact.

    def test_october_retained_comma_chart_matches_ten_visually_verified_labels(self):
        directory = CORPUS.parent / "corpus-20260928T010052Z"
        paths = [directory / f"2025-10-31-reading-{i}.json" for i in range(2)]
        if not all(p.exists() for p in paths):
            self.skipTest("October paired readings required")
        originals = [p.read_bytes() for p in paths]
        pair = [json.loads(b) for b in originals]
        did = "bf6cca678cb969b036378f5e3fffee6059fb9dcc1573cb8a639032769b157b1a"
        pdf = (OLD / (did + ".pdf")).read_bytes()
        self.assertEqual(hashlib.sha256(pdf).hexdigest(), did)
        chart = milk.inspect(pdf, date(2025, 10, 31))
        rows = milk.paired_rows(chart, pair)
        # Read independently from the actual original cover, including commas.
        expected = [1836, 1862, 2067, 2086, 2071, 2090, 1920, 1954, 1879, 1896]
        self.assertEqual([r["price"] for r in rows], expected)
        self.assertEqual([r["market"] for r in rows][::2], list(milk.REGIONS))
        self.assertEqual(
            [r["date"] for r in rows], [date(2025, 9, 30), date(2025, 10, 31)] * 5
        )
        self.assertTrue(
            all(r["currency"] == "COP" and r["unit"] == "litro" for r in rows)
        )
        self.assertEqual(
            [r["details"]["literal_price"] for r in rows], [f"{v:,}" for v in expected]
        )
        self.assertEqual([p.read_bytes() for p in paths], originals)
        self.assertTrue(
            all(
                r["details"]["literal_number_format"] == "whole-chart-comma-thousands"
                for r in rows
            )
        )


if __name__ == "__main__":
    unittest.main()

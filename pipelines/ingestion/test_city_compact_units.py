"""Compact native city quantities preserve package identity and literal prices."""

import inspect
import json
import re
import shutil
import subprocess
import unittest
from collections import Counter
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from . import city_reports, worker
from .test_city_ocr_fallback import HEAD, TABLE

FIXTURES = Path("artifacts/app-data-audit-2026-09-27/planning/city-compact-units")
PRIOR = Path("artifacts/source-ambiguity-2026-09-27/city-milk/july22-recovered-members")


def row_for(units):
    table = [row[:] for row in TABLE]
    table[-1][2] = units
    page = SimpleNamespace(
        extract_text=lambda: HEAD, extract_tables=lambda: [table], close=lambda: None
    )
    return next(city_reports.parse_city_pages([page], date(2026, 9, 7)))


class CompactCityQuantities(unittest.TestCase):
    def test_known_unit_equivalence_with_and_without_native_space(self):
        for compact, spaced in [
            ("1Kilogramo", "1 Kilogramo"),
            ("12.5Kilogramo", "12.5 Kilogramo"),
            ("12,5Kilogramo", "12,5 Kilogramo"),
            ("500Gramo", "500 Gramo"),
            ("24Unidad", "24 Unidad"),
            ("30Unidades", "30 Unidades"),
            ("2Litro", "2 Litro"),
            ("750Mililitro", "750 Mililitro"),
        ]:
            with self.subTest(quantity=compact):
                self.assertEqual(row_for(compact), row_for(spaced))
        self.assertEqual(row_for("12.5Kilogramo")[7], Decimal("12.5"))
        self.assertEqual(
            row_for("12.5Kilogramo")[14:16], (Decimal(6800), Decimal(6960))
        )

    def test_unknown_compound_unit_stays_literal_without_conversion(self):
        for unit in ("Unidad500GR", "Unidad 500 GR", "Unidad1000CC", "Atado"):
            with self.subTest(unit=unit):
                r = row_for("25" + unit)
                self.assertEqual(r[7:9], (Decimal(25), unit))
                self.assertEqual(
                    r[11:16], (Decimal(85000), Decimal(87000), unit, None, None)
                )

    def test_numeric_quantity_cannot_backtrack_into_unknown_unit(self):
        for malformed in (
            "12.5",
            "125",
            "12,5",
            "1.2.3Kilogramo",
            "12,5,0Unidad",
            "1 500Kilogramo",
            ".5Kilogramo",
            "-1Kilogramo",
            "Kilogramo",
            "1%",
        ):
            with (
                self.subTest(quantity=malformed),
                self.assertRaisesRegex(ValueError, "Unknown city quantity"),
            ):
                row_for(malformed)
        with self.assertRaisesRegex(ValueError, "Nonpositive city package"):
            row_for("0Kilogramo")

    def test_default_checkpoint_version_matches_worker_registry(self):
        self.assertEqual(city_reports.VERSION, "city-v5")
        self.assertEqual(
            inspect.signature(city_reports.publish_city_zip)
            .parameters["processor_version"]
            .default,
            city_reports.VERSION,
        )
        self.assertEqual(worker.parser_version("city-zip"), city_reports.VERSION)

    @unittest.skipUnless(
        (FIXTURES / "originals.json").exists() and shutil.which("pdftotext"),
        "Retained official originals and Poppler required",
    )
    def test_four_real_originals_all371_ranges_and_compound_units(self):
        counts = {"992480e3": 198, "a330b111": 40, "eb8b793c": 100, "ae07e7f4": 33}
        number = r"(\d+(?:\.\d{3})*(?:,\d+)?)"
        pattern = re.compile(r"\s{2,}" + r"\s+".join([number] * 4) + r"\s*$")
        all_rows = {}
        for fixture in json.loads((FIXTURES / "originals.json").read_text()):
            did = fixture["document_id"]
            path = FIXTURES / (did + ".pdf")
            with self.subTest(original=fixture["entry_name"]):
                data = path.read_bytes()
                self.assertEqual(sha256(data).hexdigest(), did)
                rows = list(city_reports.parse_city_pdf(data, date(2026, 9, 27)))
                self.assertEqual(len(rows), counts[did[:8]])
                text = subprocess.check_output(
                    ["pdftotext", "-layout", str(path), "-"], text=True
                )
                independent = []
                for line in text.splitlines():
                    found = pattern.search(line)
                    if found:
                        values = [
                            Decimal(v.replace(".", "").replace(",", "."))
                            for v in found.groups()
                        ]
                        independent.extend(
                            (values[i], values[i + 1]) for i in (0, 2) if values[i] > 0
                        )
                self.assertEqual(
                    Counter((r[11], r[12]) for r in rows), Counter(independent)
                )
                all_rows[did[:8]] = rows
        compound = next(r for r in all_rows["a330b111"] if r[8] == "Unidad500GR")
        self.assertEqual(compound[7], 25)
        self.assertEqual(compound[11:16], (50000, 53000, "Unidad500GR", None, None))
        grape = next(r for r in all_rows["eb8b793c"] if r[3] == "Uva verde")
        self.assertEqual(grape[1], date(2025, 1, 7))
        self.assertEqual(grape[6:9], ("Canastilla", Decimal("12.5"), "Kilogramo"))
        self.assertEqual(grape[11:16], (125000, 128000, "kg", 10000, 10240))
        meat = next(
            r for r in all_rows["ae07e7f4"] if r[3] == "Carne de res, lomo fino"
        )
        self.assertEqual(meat[11:16], (44000, 46000, "kg", 44000, 46000))

    @unittest.skipUnless(
        PRIOR.exists(), "Previously audited native city originals required"
    )
    def test_all_previously_audited_cached_city_rows_are_unchanged(self):
        fixtures = sorted(PRIOR.glob("*.pdf.rows.json"))
        self.assertGreaterEqual(len(fixtures), 20)
        for expected_path in fixtures:
            with self.subTest(original=expected_path.name):
                pdf_path = Path(str(expected_path).removesuffix(".rows.json"))
                expected = json.loads(expected_path.read_text())
                actual = list(
                    city_reports.parse_city_pdf(
                        pdf_path.read_bytes(), date(2023, 7, 22)
                    )
                )
                self.assertEqual(json.loads(json.dumps(actual, default=str)), expected)


if __name__ == "__main__":
    unittest.main()

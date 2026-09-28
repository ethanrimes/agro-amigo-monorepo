"""Strict region/period regression; optional original PDF fixture validation.

Run: python -m unittest discover -s pipelines/planning -p test_cost_regions.py
Set PLANNING_COST_FIXTURES to a retained planning/cache directory for real PDFs.
"""

import os
from pathlib import Path
import unittest

try:
    from .cost_regions import ARVEJA_FOOTERS, ARVEJA_SOURCE, arveja_municipalities, cost_region
except ImportError:  # unittest discovery with pipelines/planning as its root
    from cost_regions import ARVEJA_FOOTERS, ARVEJA_SOURCE, arveja_municipalities, cost_region


# Independently transcribed from rendered original pages, not parser output.
ORACLES = {
    9: (2, "Sabana Occidente", "en Sabana Occidente* en 2024",
        11311442, 6171260, 3807982, 1053000, 3750),
    12: (5, "Sur de Nariño", "en el Sur de Nariño*, en 2024",
         18939169, 10780000, 6425836, 2000000, 9360),
    14: (8, "Sugamuxi", "en Sugamuxi*, 2024",
         31340818, 15871457, 12443680, 4848929, 7600),
}


def heading(page):
    table, _, suffix, *_ = ORACLES[page]
    return f"Tabla {table}. Costos de producción de arveja por\nhectárea {suffix}\nActividad ($) (%)"


class CostRegions(unittest.TestCase):
    def test_three_exact_arveja_regions_without_region_keyword(self):
        for page, (_, region, *_) in ORACLES.items():
            with self.subTest(page=page):
                self.assertEqual(cost_region(heading(page), ARVEJA_SOURCE, page, "Arveja", 2024), region)

    def test_changed_year_region_table_and_ambiguous_headings_rejected(self):
        original = heading(9)
        for text in (
            original.replace("2024", "2025"),
            original.replace("Sabana Occidente", "Otra región"),
            original.replace("Tabla 2.", "Tabla 3."),
            original + "\n" + heading(12),
            original.replace("arveja", "frijol"),
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                cost_region(text, ARVEJA_SOURCE, 9, "Arveja", 2024)

    def test_page_and_configured_period_cannot_supply_missing_source_evidence(self):
        for text, page, crop, year in (
            ("Sin encabezado", 9, "Arveja", 2024),
            (heading(9), 15, "Arveja", 2024),
            (heading(9), 9, "Arveja", 2023),
            (heading(9), 9, "Papa", 2024),
        ):
            with self.subTest(page=page, year=year), self.assertRaises(ValueError):
                cost_region(text, ARVEJA_SOURCE, page, crop, year)

    def test_existing_region_heading_and_unrelated_pages_unchanged(self):
        text = "Ficha 1. Costos de producción de papa Región Almeidas (Cundinamarca)* 2023 Actividad"
        self.assertEqual(cost_region(text, "papa.pdf", 2, "Papa", 2023), "Región Almeidas (Cundinamarca)")
        self.assertIsNone(cost_region(heading(9), "unknown.pdf", 9, "Arveja", 2024))

    def test_municipality_is_not_inferred_from_department_or_partial_name(self):
        department, names = ARVEJA_FOOTERS[12]
        municipalities = [(str(i), name.strip().upper(), department.upper())
                          for i, name in enumerate(names.split(","))]
        municipalities += [("extra", "NARIÑO", "NARIÑO"), ("wrong-dep", "CÓRDOBA", "QUINDÍO"),
                           ("partial", "CUASPUD", "NARIÑO")]
        text = f"*Incluye los municipios de {names} ({department}).\n**Otros costos"
        self.assertEqual(arveja_municipalities(text, 12, municipalities), [str(i) for i in range(11)])
        for altered in (text.replace("Aldana, ", ""), text.replace("(Nariño)", "(Boyacá)"), text + text):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                arveja_municipalities(altered, 12, municipalities)
        with self.assertRaises(ValueError):
            arveja_municipalities(text, 12, municipalities[1:])

    @unittest.skipUnless(os.environ.get("PLANNING_COST_FIXTURES"), "retained original fixtures are opt-in")
    def test_all_22_existing_original_region_identities_unchanged(self):
        import json
        from pypdf import PdfReader

        baseline = json.loads(Path(__file__).with_name("cost-extractions.json").read_text())
        self.assertEqual(len(baseline), 22)
        readers = {}
        for row in baseline:
            source = row["source"]
            if source not in readers:
                readers[source] = PdfReader(Path(os.environ["PLANNING_COST_FIXTURES"]) / source)
            with self.subTest(identity=row["id"]):
                text = readers[source].pages[row["page"] - 1].extract_text()
                self.assertEqual(cost_region(text, source, row["page"], "existing", 2023), row["region"])

    @unittest.skipUnless(os.environ.get("PLANNING_COST_FIXTURES"), "retained original fixtures are opt-in")
    def test_actual_three_original_pages(self):
        import re
        from pypdf import PdfReader

        path = Path(os.environ["PLANNING_COST_FIXTURES"]) / ARVEJA_SOURCE
        reader = PdfReader(path)
        for page, (_, region, _, total, labor, inputs, harvest, kg) in ORACLES.items():
            with self.subTest(page=page):
                text = reader.pages[page-1].extract_text()
                self.assertEqual(cost_region(text, ARVEJA_SOURCE, page, "Arveja", 2024), region)
                def literal(label):
                    match = re.search(r"^\s*" + label + r"\s+([\d.,]+)", text, re.M | re.I)
                    self.assertIsNotNone(match)
                    return float(match[1].replace(".", "").replace(",", "."))
                self.assertEqual(literal("Total costos"), total)
                self.assertEqual(literal("Mano de obra/maquinaria"), labor)
                self.assertEqual(literal("Insumos"), inputs)
                self.assertEqual(literal("Cosecha"), harvest)
                self.assertEqual(literal(r"Producción total\s*\(?T/ha\)?") * 1000, kg)
                dep, names = ARVEJA_FOOTERS[page]
                municipality_fixture = [(str(i), name.strip(), dep) for i, name in enumerate(names.split(","))]
                self.assertEqual(arveja_municipalities(text, page, municipality_fixture), [str(i) for i in range(len(municipality_fixture))])


if __name__ == "__main__":
    unittest.main()

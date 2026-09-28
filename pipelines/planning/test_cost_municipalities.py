"""Exact source footers distinguish a department from its namesake town."""
import os
from pathlib import Path
import re
import unittest
try:
    from .cost_municipalities import FOOTERS, corrected_cost_municipalities
except ImportError:
    from cost_municipalities import FOOTERS, corrected_cost_municipalities


def fixtures(department, names):
    return [(str(i), re.sub(r"\s*\([^)]*\)", "", name).strip(), department)
            for i, name in enumerate(names.split(","))] + [("false-town", department, department)]


class CostMunicipalities(unittest.TestCase):
    def test_all_five_department_tokens_are_not_municipalities(self):
        for (source, page), (dep, names) in FOOTERS.items():
            text = f"*Incluye los municipios de {names} ({dep}).\n**Costos indirectos"
            with self.subTest(source=source, page=page):
                found = corrected_cost_municipalities(text, source, page, fixtures(dep, names))
                self.assertEqual(found, [str(i) for i in range(len(names.split(",")))])
                self.assertNotIn("false-town", found)

    def test_changed_footer_missing_identity_and_unknown_source(self):
        (source, page), (dep, names) = next(iter(FOOTERS.items()))
        text = f"*Incluye los municipios de {names} ({dep}).\n**Costos indirectos"
        with self.assertRaises(ValueError):
            corrected_cost_municipalities(text.replace("Cucaita", "Otra"), source, page, fixtures(dep, names))
        with self.assertRaises(ValueError):
            corrected_cost_municipalities(text, source, page, fixtures(dep, names)[1:])
        self.assertIsNone(corrected_cost_municipalities(text, "unverified.pdf", page, fixtures(dep, names)))

    @unittest.skipUnless(os.environ.get("PLANNING_COST_FIXTURES"), "retained original fixtures are opt-in")
    def test_actual_five_original_footers(self):
        from pypdf import PdfReader
        for (source, page), (dep, names) in FOOTERS.items():
            with self.subTest(source=source, page=page):
                text = PdfReader(Path(os.environ["PLANNING_COST_FIXTURES"]) / source).pages[page-1].extract_text()
                found = corrected_cost_municipalities(text, source, page, fixtures(dep, names))
                self.assertEqual(found, [str(i) for i in range(len(names.split(",")))])


if __name__ == "__main__":
    unittest.main()

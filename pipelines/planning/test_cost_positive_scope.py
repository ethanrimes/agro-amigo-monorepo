"""Printed department/municipality identities recover omitted cost scope."""
import os
from pathlib import Path
import unittest
try:
    from .cost_municipalities import POSITIVE_FOOTERS, PRINTED_ALIASES, _name, corrected_cost_municipalities
except ImportError:
    from cost_municipalities import POSITIVE_FOOTERS, PRINTED_ALIASES, _name, corrected_cost_municipalities


def fixtures(department, names):
    aliases = {(_name(dep), _name(n)): (mid, canonical) for (dep, n), (mid, canonical) in PRINTED_ALIASES.items()}
    result = []
    for i, name in enumerate(names.split(",")):
        alias = aliases.get((_name(department), _name(name)))
        if alias:
            mid, name = alias
        else:
            mid = str(i)
            name = {"Villa vieja": "VILLAVIEJA", "Fuentedeoro": "FUENTE DE ORO"}.get(name.strip(), name.strip())
        result.append((mid, name, department))
    return result


class PositiveCostScope(unittest.TestCase):
    def test_exact_source_names_and_explicit_department_recover_five_scopes(self):
        for (source, page), (dep, footer, names, heading) in POSITIVE_FOOTERS.items():
            text = (heading or "") + "\n*Incluye " + footer + "\n**Otros costos"
            rows = fixtures(dep, names)
            with self.subTest(source=source, page=page):
                self.assertEqual(corrected_cost_municipalities(text, source, page, rows), sorted(r[0] for r in rows))
                if dep == "Antioquia":
                    self.assertIn("05674", corrected_cost_municipalities(text, source, page, rows))

    def test_no_neighbor_department_or_unknown_san_vicente_alias(self):
        source, page = "cost-20231018_Ficha_papa_2023.pdf", 7
        dep, footer, names, heading = POSITIVE_FOOTERS[(source, page)]
        text = heading + "\n*Incluye " + footer + "\n**Otros costos"
        rows = fixtures(dep, names)
        for altered in (text.replace("(Antioquia)", "(Caquetá)"), text.replace(heading, ""), text.replace("San Vicente,", "San Vicente del Caguán,")):
            with self.subTest(text=altered), self.assertRaises(ValueError):
                corrected_cost_municipalities(altered, source, page, rows)
        with self.assertRaises(ValueError):
            corrected_cost_municipalities(text, source, page, [(mid, n, "Caquetá" if mid=="05674" else d) for mid,n,d in rows])
        with self.assertRaises(ValueError):
            corrected_cost_municipalities(text, source, page, rows + [("05674", "San Vicente Ferrer", "Antioquia")])

    def test_printed_narino_town_does_not_enable_narino_department(self):
        source, page = "cost-20231009_BolCostos_Frijol.pdf", 17
        dep, footer, names, heading = POSITIVE_FOOTERS[(source, page)]
        text = "*Incluye " + footer + "\n**Otros costos"
        rows = fixtures(dep, names) + [("52254", "EL PEÑOL", "NARIÑO"),
                                      ("52399", "LA UNIÓN", "NARIÑO"),
                                      ("52480", "NARIÑO", "NARIÑO")]
        found = corrected_cost_municipalities(text, source, page, rows)
        self.assertEqual(len(found), 22)
        self.assertFalse(set(found) & {"52254", "52399", "52480"})

    @unittest.skipUnless(os.environ.get("PLANNING_COST_FIXTURES"), "retained original fixtures are opt-in")
    def test_all_five_actual_source_footers_and_heading(self):
        from pypdf import PdfReader
        counts = [11, 22, 17, 13, 13]
        for ((source, page), (dep, footer, names, heading)), count in zip(POSITIVE_FOOTERS.items(), counts):
            with self.subTest(source=source, page=page):
                text = PdfReader(Path(os.environ["PLANNING_COST_FIXTURES"]) / source).pages[page-1].extract_text()
                found = corrected_cost_municipalities(text, source, page, fixtures(dep, names))
                self.assertEqual(len(found), count)
                if dep=="Antioquia": self.assertIn("05674", found)


if __name__ == "__main__":
    unittest.main()

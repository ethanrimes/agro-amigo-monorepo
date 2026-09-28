"""Original-backed junca continuation, exact geography, and source-review tests."""
import os
from pathlib import Path
import unittest

try:
    from .cost_junca import SOURCE, TABLES, parse_junca_tables
except ImportError:
    from cost_junca import SOURCE, TABLES, parse_junca_tables


# Literal source values, independently read from PDF pages9–10,12,15.
LITERALS = {
    9: (31268811, 31057612, 10073593, 20984019, 3043474, 211199, "23,9"),
    12: (18988117, 15392543, 8129131, 6474359, 1638897, 3595575, "16,1"),
    15: (4664743, 4664743, 2824132, 1840611, 1030840, 0, "5,0"),
}


def municipalities():
    return [(f"{first}-{i}", name, department)
            for _, first, _, _, _, _, department, names in TABLES
            for i, name in enumerate(names)] + [("not-published", "Nariño", "Nariño")]


def pages():
    result = [""] * 16
    for _, first, last, _, heading, footer, _, _ in TABLES:
        total, direct, labor, inputs, harvest, indirect, kg = LITERALS[first]
        body = f"\nActividad $ %\nCostos directos {direct} 99\nMano de obra/maquinaria {labor} 30\nCosecha {harvest} 10\nInsumos {inputs} 60\n"
        tail = (f"Costos indirectos** {indirect} 1\n" if indirect else "") + f"Costos totales {total} 100\nRendimientos t/ha\nProducción total {kg} –\n{footer}\n"
        result[first-1] = heading + body + (tail if first == last else "")
        if first != last:
            result[last-1] = "Actividad $ %\n" + tail
    return result


class JuncaCosts(unittest.TestCase):
    def assert_expected(self, result):
        self.assertEqual([r["source_page"] for r in result.rows], [9, 15])
        self.assertEqual([r["yield_kg_ha"] for r in result.rows], [23900, 5000])
        self.assertEqual([sum(c["amount"] for c in r["costs"]) for r in result.rows], [31268811, 4664743])
        self.assertEqual([len(r["municipalities"]) for r in result.rows], [1, 5])
        self.assertTrue(all(r["crop"] == "Cebolla de rama" and "Cebolla junca" in r["title"] for r in result.rows))
        self.assertEqual(len(result.reviews), 1)
        review = result.reviews[0]
        self.assertEqual(review["source_locator"], "PDF page 12; table 5")
        self.assertEqual(review["record"]["total"], 18988117)
        self.assertEqual(review["record"]["direct"], 15392543)
        self.assertEqual(review["record"]["labor"], 8129131)
        self.assertEqual(review["record"]["inputs"], 6474359)
        self.assertEqual(review["record"]["indirect"], 3595575)
        self.assertEqual(review["record"]["direct_minus_components"], 789053)
        self.assertEqual(review["record"]["total_minus_direct_and_indirect"], -1)
        self.assertEqual(review["record"]["yield_kg_ha"], 16100)
        self.assertNotIn("Diferencia", " ".join(c["label"] for r in result.rows for c in r["costs"]))

    def test_two_consistent_tables_and_one_exact_literal_review(self):
        self.assert_expected(parse_junca_tables(pages(), municipalities()))

    def test_wrong_period_region_units_and_continuation_rejected(self):
        for page, old, new in ((8, "2023", "2024"), (11, "Risaralda", "Cauca"),
                               (11, "Actividad $ %", "Actividad %"),
                               (14, "Rendimientos t/ha", "Rendimientos kg/ha"),
                               (9, "Actividad $ %", "Tabla 3. Otra tabla")):
            changed = pages(); changed[page] = changed[page].replace(old, new)
            with self.subTest(page=page, new=new), self.assertRaises(ValueError):
                parse_junca_tables(changed, municipalities())

    def test_no_amount_from_next_quantity_table_or_duplicate_cell(self):
        changed = pages(); changed[9] = changed[9].replace("Costos totales", "Tabla 3. Fertilizantes\nCostos totales")
        with self.assertRaises(ValueError):
            parse_junca_tables(changed, municipalities())
        changed = pages(); changed[14] += "\nCostos totales 100 100\n"
        with self.assertRaises(ValueError):
            parse_junca_tables(changed, municipalities())

    def test_missing_printed_municipality_and_negative_prices_rejected(self):
        with self.assertRaises(ValueError):
            parse_junca_tables(pages(), municipalities()[1:])
        changed = pages(); changed[8] = changed[8].replace("Insumos 20984019", "Insumos -20984019")
        with self.assertRaises(ValueError):
            parse_junca_tables(changed, municipalities())

    @unittest.skipUnless(os.environ.get("PLANNING_COST_FIXTURES"), "retained original fixtures are opt-in")
    def test_actual_three_printed_original_tables(self):
        from pypdf import PdfReader
        reader = PdfReader(Path(os.environ["PLANNING_COST_FIXTURES"]) / SOURCE)
        self.assert_expected(parse_junca_tables([p.extract_text() for p in reader.pages], municipalities()))


if __name__ == "__main__":
    unittest.main()

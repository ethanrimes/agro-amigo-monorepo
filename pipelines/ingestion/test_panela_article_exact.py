"""Independent visual/native controls for the exact June 2014 panela article."""

import copy
import hashlib
import re
import subprocess
import unittest
from pathlib import Path

import pdfplumber

from . import panela_article_exact as MODULE

ORIGINAL = Path(__file__).resolve().parent / "testdata" / "dane_date_repairs" / (MODULE.ORIGINAL_SHA + ".pdf")

# Independently transcribed from the physically inspected original page 43/44
# table pixels, with native Poppler lines cross-checked. These are single
# printed COP/kg article prices, not weekly Cuadro minimum/maximum/mean rows.
EXPECTED = {
    (43, 2): (
        ("Charalá (Santander)", (1406, 1469, 1406, 1344, 1344)),
        ("Güepsa (Santander)", (1175, 1200, 1100, 1100, 1200)),
        ("Moniquirá (Boyacá)", (1350, 1200, 1100, 1175, 1250)),
        ("San Gil (Santander)", (1275, 1275, 1275, 1225, 1225)),
        ("Santana (Boyacá)", (1275, 1225, 1175, 1175, 1225)),
        ("Vélez (Santander)", (1200, 1150, 1150, 1150, 1175)),
    ),
    (44, 3): (
        ("Caparrapí (Cundinamarca)", (1350, 1200, 1200, 1200, 1150)),
        ("Charalá (Santander)", (1281, 1406, 1281, 1219, 1219)),
        ("Nocaima (Cundinamarca)", (1375, 1325, 1225, 1215, 1175)),
        ("San Gil (Santander)", (1275, 1275, 1275, 1225, 1225)),
        ("Villeta (Cundinamarca)", (1356, 1294, 1288, 1250, 1188)),
    ),
    (44, 4): (
        ("Caparrapí (Cundinamarca)", (1350, 1200, 1150, 1150, 1000)),
    ),
}


class PanelaArticleExactSource(unittest.TestCase):
    def test_independent_poppler_table_money_vectors(self):
        for (page, table), expected_rows in EXPECTED.items():
            text = subprocess.check_output(
                ["pdftotext", "-f", str(page), "-l", str(page), "-layout",
                 str(ORIGINAL), "-"], text=True)
            start = text.index(f"Tabla {table}. Precios por kilo de la panela")
            # Poppler interleaves the page-44 left Tabla 3 footer with the
            # right Tabla 4 header; use the rest of page for the right table.
            source_section = (text[start:] if table == 4 else
                              text[start:text.index("Fuente: SIPSA-DANE.", start)])
            for name, values in expected_rows:
                literal_values = [f"{n//1000}.{n%1000:03d}" for n in values]
                pattern = r"\s+".join(map(re.escape, literal_values))
                self.assertRegex(source_section, pattern, f"{page=} {table=} {name=}")

    def test_all_sixty_literal_market_week_cells(self):
        body = ORIGINAL.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), MODULE.ORIGINAL_SHA)
        cells = MODULE.extract(body)
        self.assertEqual(len(cells), 60)
        self.assertEqual(len({cell["source_locator"] for cell in cells}), 60)
        for (page, table), expected_rows in EXPECTED.items():
            group = [cell for cell in cells if (cell["source_page"], cell["source_table"]) == (page, table)]
            self.assertEqual(len(group), len(expected_rows) * 5)
            for row_no, (literal_market, prices) in enumerate(expected_rows, 1):
                row = [cell for cell in group if cell["source_row"] == row_no]
                self.assertEqual([cell["market_literal"] for cell in row], [literal_market] * 5)
                self.assertEqual([cell["price_cop_per_kg"] for cell in row], list(prices))
                self.assertEqual([cell["price_literal"] for cell in row],
                                 [f"{n//1000}.{n%1000:03d}" for n in prices])
                self.assertEqual([(cell["period_start"], cell["period_end"]) for cell in row],
                                 [(start.isoformat(), end.isoformat()) for start, end in MODULE.WEEKS])
                self.assertEqual({cell["series"] for cell in row}, {"panela_article_single_price"})
                self.assertEqual({cell["unit_literal"] for cell in row}, {"Precios por kilo"})
                self.assertEqual({cell["currency"] for cell in row}, {"COP"})
                self.assertTrue(all("min" not in cell and "max" not in cell and "price" not in cell
                                    for cell in row))

    def test_exact_identity_and_native_geometry_fail_closed(self):
        body = ORIGINAL.read_bytes()
        with self.assertRaisesRegex(ValueError, "source identity"):
            MODULE.extract(body, MODULE.SOURCE_URL + "?nearby")
        changed = bytearray(body)
        changed[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "source identity"):
            MODULE.extract(bytes(changed))
        with pdfplumber.open(ORIGINAL) as pdf:
            page43 = pdf.pages[42].extract_words()
            page44 = pdf.pages[43].extract_words()
        for table in MODULE.TABLES:
            words = page43 if table.page == 43 else page44
            self.assertEqual(len(MODULE._extract_table(words, table)), len(table.rows) * 5)
            title_changed = copy.deepcopy(words)
            next(word for word in title_changed
                 if abs(word["top"] - table.title_top) < .2
                 and abs(word["x0"] - table.title_x) < .6)["text"] = "Otro"
            with self.assertRaisesRegex(ValueError, "title changed"):
                MODULE._extract_table(title_changed, table)
            price_changed = copy.deepcopy(words)
            next(word for word in price_changed
                 if abs(word["top"] - table.rows[0][0]) < .2
                 and abs(word["x0"] - table.money_x[0]) < .2)["text"] = "?"
            with self.assertRaisesRegex(ValueError, "Incomplete native panela prices"):
                MODULE._extract_table(price_changed, table)
            shifted = copy.deepcopy(words)
            next(word for word in shifted
                 if abs(word["top"] - table.rows[0][0]) < .2
                 and abs(word["x0"] - table.money_x[0]) < .2)["x0"] += 5
            with self.assertRaisesRegex(ValueError, "price column moved"):
                MODULE._extract_table(shifted, table)
            valid_changed = copy.deepcopy(words)
            first = next(word for word in valid_changed
                         if abs(word["top"] - table.rows[0][0]) < .2
                         and abs(word["x0"] - table.money_x[0]) < .2)
            first["text"] = "1.999" if first["text"] != "1.999" else "1.998"
            with self.assertRaisesRegex(ValueError, "price vector changed"):
                MODULE._extract_table(valid_changed, table)
            valid_market = copy.deepcopy(words)
            name_y = table.rows[0][1] or table.rows[0][0]
            first_name = next(word for word in valid_market
                              if abs(word["top"] - name_y) < .2
                              and table.name_x_min <= word["x0"] < table.name_x_max
                              and "(" not in word["text"])
            first_name["text"] = "Otra"  # Parenthesized department stays intact.
            with self.assertRaisesRegex(ValueError, "market changed"):
                MODULE._extract_table(valid_market, table)
            swapped = copy.deepcopy(words)
            row_money = sorted((word for word in swapped
                                if abs(word["top"] - table.rows[0][0]) < .2
                                and table.money_x[0] - 2 <= word["x0"] <= table.money_x[-1] + 1),
                               key=lambda word: word["x0"])
            left, right = next(((a, b) for a, b in zip(row_money, row_money[1:])
                                if a["text"] != b["text"]), (None, None))
            self.assertIsNotNone(left)
            left["text"], right["text"] = right["text"], left["text"]
            with self.assertRaisesRegex(ValueError, "price vector changed"):
                MODULE._extract_table(swapped, table)


if __name__ == "__main__":
    unittest.main(verbosity=2)

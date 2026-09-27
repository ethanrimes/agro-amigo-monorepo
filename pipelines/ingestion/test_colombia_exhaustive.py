"""Literal values checked against Poppler-rendered official PDF originals."""

import hashlib
import json
import unittest
from datetime import date
from pathlib import Path

from . import colombia_sources as source

ROOT = Path(__file__).resolve().parents[2] / "artifacts/automation-audit-2026-09-26"


def archived(prefix):
    if not (ROOT / "colombia-archive-stress.json").exists():
        raise unittest.SkipTest("Retained official PDF originals unavailable")
    item = next(
        x
        for x in json.loads((ROOT / "colombia-archive-stress.json").read_text())
        if x["document_id"].startswith(prefix)
    )
    body = Path(item["file"]).read_bytes()
    assert hashlib.sha256(body).hexdigest() == item["document_id"]
    return body, item["url"]


class PrintedPriceCoverage(unittest.TestCase):
    def test_compact_quality_prices_and_clipped_rows_retained_for_review(self):
        for prefix in ("32994d7420a5", "70b401b2136d"):
            body, url = archived(prefix)
            rows = source.parse_corabastos(body, url)
            self.assertEqual(len(rows), 350)  # 175 printed rows, two quality columns.
            banana = [r for r in rows if r["product_id"] == "banano-uraba"]
            self.assertEqual([r["price"] for r in banana], [40000, 38000])
            self.assertEqual({r["unit"] for r in banana}, {"CAJA · cantidad 20 · CAJA"})
            self.assertTrue(
                all("unit_price_as_published" not in r["details"] for r in banana)
            )
            self.assertTrue(any("huevo-blanco-a" == r["product_id"] for r in rows))
            clipped = [
                r for r in rows if r["product_id"].startswith("aguacate-pieles-verdes")
            ]
            self.assertEqual(len(clipped), 2)
            self.assertTrue(
                all(
                    r["price"] is None and "clipped" in r["details"]["quality_issue"]
                    for r in clipped
                )
            )
            self.assertEqual(len({r["source_locator"] for r in rows}), 350)

    def test_current_tercile_means_are_distinct_from_weighted_price_and_ranges(self):
        path = ROOT / "colombia-pork-pdf-4047077ee0.pdf"
        if not path.exists():
            self.skipTest("Current official original unavailable")
        rows = source.parse_pork(path.read_bytes())
        tiers = [r for r in rows if r["series"] == "porkcolombia-tercile"]
        self.assertEqual(len(tiers), 27)
        live = [
            r
            for r in tiers
            if r["market"] == "Antioquia" and r["product_id"] == "cerdo-en-pie"
        ]
        self.assertEqual(
            {r["identity_dimensions"]["price_segment"]: r["price"] for r in live},
            {"superior": 6209, "medio": 6075, "inferior": 5950},
        )
        self.assertTrue(
            all(
                r["unit"] == "kg en pie" and "min" not in r and "max" not in r
                for r in live
            )
        )
        mean = [
            r
            for r in rows
            if r["market"] == "Antioquia"
            and r["product_id"] == "cerdo-en-pie"
            and r["series"] == "porkcolombia-current"
            and r["date"] == "2026-09-25"
        ]
        self.assertEqual([r["price"] for r in mean], [6078])
        self.assertTrue(
            all("price_segment" not in r["identity_dimensions"] for r in mean)
        )

    def test_2020_horizontal_terciles_preserve_five_explicit_regions(self):
        body, _ = archived("d9e3e3f08084")
        rows = [
            r for r in source.parse_pork(body) if r["series"] == "porkcolombia-tercile"
        ]
        self.assertEqual(len(rows), 15)
        self.assertEqual({r["market"] for r in rows}, set(source.PORK_MARKETS[:5]))
        self.assertEqual(
            {
                r["identity_dimensions"]["price_segment"]: r["price"]
                for r in rows
                if r["market"] == "Antioquia"
            },
            {"superior": 7584, "medio": 7468, "inferior": 7379},
        )

    def test_literal_ocr_terciles_match_printed_values_without_guessing_product(self):
        table = [
            ["Terciles Precio en Pie"],
            ["Antioquia", "Eje Cafetero", "Valle del Cauca", "Caribe Norte", "Bogotá"],
            ["Tercil Superior", "7.580", "7.550", "7.635", "7.534", "7.196"],
            ["Tercil Medio", "7.500", "7.549", "7.491", "7.341", "7.150"],
            ["Tercil Inferior", "7.440", "7.393", "7.392", "7.241", "7.128"],
        ]
        rows = source._pork_ocr_terciles(table, 2, 1, date(2020, 12, 31), {})
        self.assertEqual(len(rows), 15)
        self.assertEqual(
            [r["price"] for r in rows if r["market"] == "Antioquia"], [7580, 7500, 7440]
        )
        self.assertTrue(all(r["details"]["extraction"] == "ocr" for r in rows))
        with self.assertRaisesRegex(ValueError, "explicit price product"):
            source._pork_ocr_terciles(table[1:], 2, 1, date(2020, 12, 31), {})
        modern = [
            ["Cerdo en pie ($/Kilo)"],
            ["Mercado", "Superior", "Medio", "Inferior"],
            ["Antioquia", "6.209", "6.075", "5.950"],
        ]
        rows = source._pork_ocr_terciles(modern, 1, 1, date(2026, 9, 25), {})
        self.assertEqual([r["price"] for r in rows], [6209, 6075, 5950])


if __name__ == "__main__":
    unittest.main()

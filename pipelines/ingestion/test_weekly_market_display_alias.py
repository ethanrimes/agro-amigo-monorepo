"""Display-only parity checks for exact weekly market source spellings."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

from pipelines.ingestion import label_normalization as labels

ALIASES = {
    "Popayán, Plaza de }mercado del barrio Bolívar": "Popayán, Plaza de mercado del barrio Bolívar",
    "Bogotá, D.C., Frigorífi co Guadalupe": "Bogotá, D.C., Frigorífico Guadalupe",
    "Bogotá, D. C., Frigorífi co Guadalupe": "Bogotá, D.C., Frigorífico Guadalupe",
    "Bogotá, D.C., Frigorífi co Ble Ltda.": "Bogotá, D.C., Frigorífico Ble Ltda.",
    "Bogotá, D. C., Frigorífi co Ble Ltda.": "Bogotá, D.C., Frigorífico Ble Ltda.",
}

class WeeklyMarketDisplayAlias(unittest.TestCase):
    def test_exact_source_spellings_normalize_to_reviewed_display(self):
        for raw, canonical in ALIASES.items():
            with self.subTest(raw=raw):
                self.assertEqual(labels.normalize(raw, "place"), canonical)
                self.assertEqual(labels.normalize(raw.upper(), "place"), canonical)

    def test_near_misses_and_other_domains_are_not_rewritten(self):
        for raw in (
            "Popayán, Plaza de } mercado del barrio Bolívar",
            "Popayán, Plaza de mercado del barrio Bolívar Norte",
            "Bogotá, D. C., Frigorífi co San Martín",
        ):
            self.assertEqual(labels.normalize(raw, "place"), raw)
            self.assertEqual(labels.normalize(raw, "input"), raw)

if __name__ == "__main__":
    unittest.main(verbosity=2)

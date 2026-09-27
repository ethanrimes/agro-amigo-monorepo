"""DANE current publication discovery and bounded supply reference archives."""

import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

from . import worker
from .supply import discover_supply_sources

ROOT = "https://www.dane.gov.co/"
FILES = ROOT + "files/operaciones/SIPSA/"
INDEX = worker.SUPPLY + "/componente-abastecimientos-boletin-quincenal-2026"


class SupplyDiscovery(unittest.TestCase):
    def capture(self, url, links):
        calls = []
        with (
            patch("pipelines.ingestion.worker.links", return_value=links) as fetch,
            patch(
                "pipelines.ingestion.worker.queue",
                side_effect=lambda db, u, k, d=None: calls.append((u, k, d)),
            ),
            patch("pipelines.ingestion.supply.today", return_value=date(2026, 9, 26)),
        ):
            count = discover_supply_sources(None, url)
        self.assertEqual(count, len(calls))
        fetch.assert_called_once_with(url)
        return calls

    def test_current_originals_and_index_are_separate_from_product_microdata(self):
        calls = self.capture(
            worker.SUPPLY,
            [
                ("2026", INDEX),
                (
                    "2026 alternate Joomla route",
                    worker.SUPPLY.rsplit("/", 1)[0]
                    + "/componente-abastecimientos-boletin-quincenal-2026",
                ),
                ("Microdatos2026", FILES + "anex-Microdato-abastecimiento-2026.xlsx"),
                ("Series", FILES + "Series-historicas-abastecimiento-2013-2026.xlsx"),
                ("Anexo", FILES + "anex-SIPSAabastecimiento-ago2026.xlsx"),
                ("Boletín", FILES + "bol-SIPSAabastecimiento-ago2026.pdf"),
                ("Boletín duplicado", FILES + "bol-SIPSAabastecimiento-ago2026.pdf"),
            ],
        )
        by_url = {u: (k, d) for u, k, d in calls}
        self.assertEqual(len(calls), 5)
        self.assertEqual(by_url[INDEX], ("supply-index", date(2026, 1, 1)))
        self.assertEqual(
            by_url[FILES + "anex-Microdato-abastecimiento-2026.xlsx"], ("supply", None)
        )
        self.assertEqual(
            by_url[FILES + "anex-SIPSAabastecimiento-ago2026.xlsx"],
            ("supply-reference", date(2026, 8, 31)),
        )
        self.assertEqual(
            by_url[FILES + "bol-SIPSAabastecimiento-ago2026.pdf"],
            ("supply-reference-pdf", date(2026, 8, 31)),
        )
        self.assertEqual(sum(kind == "supply" for _, kind, _ in calls), 1)

    def test_historical_filenames_and_partial_months_never_guess_dates(self):
        calls = self.capture(
            INDEX,
            [
                ("Self", INDEX),
                (
                    "Boletín",
                    ROOT
                    + "files/investigaciones/agropecuario/sipsa/BolAbas_11_web.pdf",
                ),
                (
                    "Anexo",
                    ROOT
                    + "files/investigaciones/agropecuario/anexo_abastecimiento_1quincena_abr21.xlsx",
                ),
                ("Boletín", FILES + "bol-SIPSAabastecimiento-1raquinsep2026.pdf"),
                ("Future", FILES + "bol-SIPSAabastecimiento-oct2026.pdf"),
                (
                    "Technical context",
                    FILES + "Nota-tecnica-certificacion-SIPSA-abastecimiento.pdf",
                ),
                (
                    "Untrusted",
                    "https://example.org/files/bol-SIPSAabastecimiento-ago2026.pdf",
                ),
            ],
        )
        self.assertEqual(len(calls), 5)
        self.assertIn(
            (
                FILES + "Nota-tecnica-certificacion-SIPSA-abastecimiento.pdf",
                "context-pdf",
                None,
            ),
            calls,
        )
        self.assertTrue(all(day is None for _, _, day in calls))
        self.assertTrue(all(kind != "supply" for _, kind, _ in calls))

    def test_empty_publisher_page_is_not_silent_success(self):
        with self.assertRaisesRegex(ValueError, "No supported supply publications"):
            self.capture(worker.SUPPLY, [])

    def test_captured_current_and_all_year_archives_retain_every_supply_original(self):
        path = Path("artifacts/automation-audit-2026-09-26/dane/snapshots.json")
        if not path.exists():
            self.skipTest("Current DANE snapshots not downloaded")
        snapshots = json.loads(path.read_text())
        pages = {
            u: s
            for u, s in snapshots.items()
            if u == worker.SUPPLY
            or "/componente-abastecimientos-boletin-quincenal-" in u
        }
        expected = set()
        actual = set()
        kinds = {}
        for url, snapshot in pages.items():
            for label, link in snapshot["links"]:
                p = urlparse(link)
                if "/files/" in p.path and p.path.lower().endswith(
                    (".xlsx", ".xls", ".pdf")
                ):
                    expected.add(link)
            for link, kind, day in self.capture(url, snapshot["links"]):
                if kind != "supply-index":
                    actual.add(link)
                kinds[link] = kind
        self.assertEqual(actual, expected)
        self.assertGreater(len(actual), 450)
        self.assertEqual(sum(kind == "supply" for kind in kinds.values()), 14)
        self.assertEqual(sum(kind == "supply-index" for kind in kinds.values()), 14)
        self.assertEqual(
            kinds[FILES + "anex-SIPSAabastecimiento-ago2026.xlsx"], "supply-reference"
        )


class CurrentDailyDiscovery(unittest.TestCase):
    def test_all_september_8_to_26_files_including_saturday_city_archives(self):
        path = Path("artifacts/automation-audit-2026-09-26/dane/snapshots.json")
        if not path.exists():
            self.skipTest("Current DANE snapshot not downloaded")
        links = json.loads(path.read_text())[worker.DAILY]["links"]
        calls = []
        with (
            patch.object(worker, "links", return_value=links),
            patch.object(
                worker,
                "queue",
                side_effect=lambda db, u, k, d=None: calls.append((u, k, d)),
            ),
            patch.object(worker, "today", return_value=date(2026, 9, 26)),
        ):
            worker.discover_daily(None, worker.DAILY)
        current = [
            row for row in calls if date(2026, 9, 8) <= row[2] <= date(2026, 9, 26)
        ]
        self.assertEqual(len(current), 45)
        self.assertEqual(sum(k == "city-zip" for _, k, _ in current), 17)
        self.assertEqual(sum(k == "daily" for _, k, _ in current), 14)
        self.assertEqual(sum(k == "daily-pdf" for _, k, _ in current), 14)
        self.assertEqual(
            {d for _, k, d in current if k == "city-zip" and d.weekday() == 5},
            {date(2026, 9, 12), date(2026, 9, 19), date(2026, 9, 26)},
        )


if __name__ == "__main__":
    unittest.main()

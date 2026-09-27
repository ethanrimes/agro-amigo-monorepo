"""FNC may retain a stale prominent workbook beside a newer download link."""

import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from . import worker


class CoffeeDiscoveryTests(unittest.TestCase):
    def discovered(self, links):
        with (
            patch.object(worker, "links", return_value=links),
            patch.object(worker, "queue") as queue,
        ):
            worker.discover_coffee(object())
        return {(c.args[1], c.args[2]) for c in queue.call_args_list}

    def test_all_official_workbooks_and_mutable_pdf_are_queued(self):
        old = "https://federaciondecafeteros.org/wp-content/uploads/2026/07/Precios-area-y-produccion-de-cafe-Agosto-2026.xlsx"
        new = "https://federaciondecafeteros.org/wp-content/uploads/2026/09/Precios-area-y-produccion-de-cafe-Septiembre-2026-1.xlsx"
        pdf = "https://federaciondecafeteros.org/wp-content/uploads/2026/03/precio_cafe.pdf"
        links = [
            ("Precios, área y producción de café", old),
            ("Descargar", new),
            ("Precio de referencia", pdf),
            ("duplicate", new),
        ]
        self.assertEqual(
            self.discovered(links),
            {(old, "coffee"), (new, "coffee"), (pdf, "coffee-pdf")},
        )
        self.assertEqual(self.discovered(list(reversed(links))), self.discovered(links))

    def test_untrusted_links_do_not_replace_official_originals(self):
        links = [
            ("", "https://untrusted.example/Precios.xlsx"),
            ("", "https://federaciondecafeteros.org.evil.example/precio_cafe.pdf"),
        ]
        with self.assertRaisesRegex(ValueError, "no trusted coffee"):
            self.discovered(links)

    def test_live_september_index_exposes_both_workbook_versions(self):
        fixture = Path("artifacts/automation-audit-2026-09-26/fnc-index.html")
        if not fixture.exists():
            self.skipTest("Official September 2026 index fixture not downloaded")
        links = [
            (a.get_text(" ", strip=True), a["href"])
            for a in BeautifulSoup(fixture.read_bytes(), "html.parser").select(
                "a[href]"
            )
        ]
        found = self.discovered(links)
        self.assertEqual(sum(kind == "coffee" for _, kind in found), 2)
        self.assertTrue(any("Septiembre-2026-1.xlsx" in url for url, _ in found))
        self.assertTrue(any("Agosto-2026.xlsx" in url for url, _ in found))

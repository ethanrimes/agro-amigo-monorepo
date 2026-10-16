"""DANE printed continuation headings are evidence, not product names."""

import csv
import unittest
from hashlib import sha256
from pathlib import Path

from . import dane_weekly as weekly

FIXTURES = Path(__file__).parent / "testdata"


class WeeklyContinuationLabels(unittest.TestCase):
    def test_only_source_observed_terminal_annotations_are_removed(self):
        for suffix in weekly.PRODUCT_CONTINUATION_MARKERS:
            with self.subTest(suffix=suffix):
                self.assertEqual(
                    weekly._product_heading("Café molido " + suffix),
                    ("Café molido", True),
                )
        for name in (
            "Café molido (instantáneo)",
            "Producto de continuación",
            "Café molido (continuación) extra",
            "Café molido continuación",
            "Café molido (continuado)",
            "Café molido (continuacion 9)",
            "Café molido (continuar)",
            "Café molido (continuaci{on extra)",
            "Café molido (continuo)",
            "Café molido (contiunuación) extra",
        ):
            with self.subTest(name=name):
                self.assertEqual(weekly._product_heading(name), (name, False))

    def test_original_2024_tahiti_typo_keeps_all_eight_literal_prices(self):
        # All eight controls were read from the rendered original page before
        # inspecting parser output. The typo continues the plain heading on
        # page 20; its exact terminal annotation is not a separate product.
        body = (FIXTURES / "dane_weekly_2024_03_23_original.pdf").read_bytes()
        self.assertEqual(
            sha256(body).hexdigest(),
            "218d83958d650f3b3035e008a35828aff6a6b2a0098d8ba84adc07596a26ca7e",
        )
        rows = weekly.parse_pdf(
            body,
            "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSASemanal-23mar-27mar-2024.pdf",
        )
        self.assertEqual(len(rows), 4133)
        literal = "Limón Tahití (contiunuación)"
        affected = [row for row in rows
                    if row["details"].get("literal_product_heading") == literal]
        with (FIXTURES / "weekly_20240327_manual_eight_prices.psv").open() as handle:
            controls = list(csv.DictReader(handle, delimiter="|"))
        self.assertEqual(len(affected), len(controls))
        self.assertEqual(len(affected), 8)
        self.assertFalse(any(row["product_name"] == literal for row in rows))
        self.assertEqual(sum(row["product_name"] == "Limón Tahití"
                             for row in rows), 30)
        for control in controls:
            with self.subTest(market=control["market"]):
                found = [row for row in affected
                         if row["market"] == control["market"]]
                self.assertEqual(len(found), 1)
                row = found[0]
                self.assertEqual(row["product_name"], control["product"])
                self.assertEqual((row["min"], row["max"], row["price"]),
                                 tuple(int(control[key]) for key in
                                       ("minimum", "maximum", "mean")))
                self.assertEqual(row["date"], "2024-03-27")
                self.assertEqual(row["period_start"], "2024-03-23")
                self.assertEqual(row["unit"], "kg")
                self.assertTrue(row["source_locator"].startswith(
                    "PDF page 21,table 1,column 1,line "))

    def test_exact_archived_pages_strip_only_marker_and_keep_literal_evidence(self):
        # Each fixture has the exact native DANE page and blank predecessors so
        # its printed page number remains the source locator. Full original
        # SHA-256s are listed separately from the hashes of these small slices.
        cases = (
            (
                "dane_weekly_2012_06_16_page11.pdf",
                "5d8e1432f33e07491619adbb5948858386b6ee2329c22ec36054c557a21d3e9e",
                "dd059a09eecb1fa01cadb24a4f21a7768d97d9e31684dee6a57222c536faf6a8",
                "Semana4_junio_2012.pdf",
                "Manzana verde importada",
                "Manzana verde importada (continuaciòn)",
                7,
                "PDF page 11,table 1,column 2,line 3",
                2697,
            ),
            (
                "dane_weekly_2019_02_23_page41.pdf",
                "c781ea06d50e7efe1f73cd67883b75beb1ebc7f34b2ab485e523a584bed9f47d",
                "6e4d6d86850b821d3a6dd12cc20f5a59ae3532ffd46625806d26688e8217dd9f",
                "Sem_23feb_2019__01mar_2019.pdf",
                "Plátano hartón verde",
                "Plátano hartón verde (continuación9",
                8,
                "PDF page 41,table 1,column 1,line 3",
                440,
            ),
            (
                "dane_weekly_2020_02_01_page22.pdf",
                "8db2977ddea30fc13cf70955d944a37850d45283914cd27c24dbc379c1ea39a5",
                "08f8629ed9d4308b742420a7f7c42c94cb7eef6c3c2f125e88a7354b5f09026c",
                "Sem_01feb_2020__07feb_2020.pdf",
                "Aguacate papelillo",
                "Aguacate papelillo (contnuación)",
                2,
                "PDF page 22,table 1,column 2,line 2",
                4642,
            ),
            (
                "dane_weekly_2021_01_30_page55.pdf",
                "cf5a49b99d3ba742e042873c62c089dfbd35c5da1e6f4fa81f5d8d83cff17b3c",
                "ced49fa4cf3476bde777ca377c1889989b69a1c047bd15642d29165d9c5d5968",
                "Sem_30ene_2021__05feb_2021.pdf",
                "Pechuga de pollo",
                "Pechuga de pollo (continuación",
                28,
                "PDF page 55,table 1,column 1,line 2",
                7175,
            ),
            (
                "dane_weekly_2021_07_10_page57.pdf",
                "c7f386c27161af7b61b5df9fff6544e985d135df4bcab059ea60a5ddd42733bd",
                "60657385fb09fc31a5c2187878cd52970274157e9e54ae05ea45750fcbaa2282",
                "Sem_10jul_2021_16jul_2021.pdf",
                "Pollo entero fresco sin vísceras",
                "Pollo entero fresco sin vísceras (continuaci{on)",
                4,
                "PDF page 57,table 1,column 1,line 3",
                9188,
            ),
            (
                "dane_weekly_2026_01_03_page49.pdf",
                "c56c9e86d9004e472b00c4d61a29149c566096a0dc1ec966c84e4bbf1b466f3b",
                "7d9881394b81d4c2a5cf9cacfd22a11dd6c17889998c0d333d799673da9b3866",
                "bol-SIPSASemanal-03ene09ene-2026.pdf",
                "Carne de res, bola de brazo",
                "Carne de res, bola de brazo (continu",
                18,
                "PDF page 49,table 1,column 2,line 3",
                29750,
            ),
            (
                "dane_weekly_2026_05_02_page55.pdf",
                "5cf7e1eed247f93a2e8148f55b7d7b48d2576bd65f9015da6fb3403b068ded38",
                "a0f4419cd263914fc43cfb7f4391c849dba6c9e8afa1786fd3ad6841f625c382",
                "bol-SIPSASemanal-02may08may-2026.pdf",
                "Pollo entero fresco sin vísceras",
                "Pollo entero fresco sin vísceras (continaución)",
                9,
                "PDF page 55,table 1,column 1,line 3",
                14250,
            ),
        )
        for fixture, fixture_sha, source_sha, url, name, literal, count, locator, price in cases:
            with self.subTest(original=source_sha, heading=literal):
                body = (FIXTURES / fixture).read_bytes()
                self.assertEqual(sha256(body).hexdigest(), fixture_sha)
                rows = weekly.parse_pdf(body, url)
                corrected = [
                    row for row in rows
                    if row["details"].get("literal_product_heading") == literal
                ]
                self.assertEqual(len(corrected), count)
                self.assertEqual({row["product_name"] for row in corrected}, {name})
                self.assertEqual(next(row["price"] for row in corrected if row["source_locator"] == locator), price)

    def test_original_2021_misspelled_carryover_keeps_literal_heading(self):
        # Exact page 62, with blank predecessors to preserve the PDF locator.
        # Full DANE original Sem_02oct_2021_08oct_2021.pdf SHA-256:
        # b97812964b8cbb777e822172e90ddab5a12b146d5a9be6da77ae1473979f8f86
        data = (FIXTURES / "dane_weekly_2021_10_02_page62.pdf").read_bytes()
        self.assertEqual(
            sha256(data).hexdigest(),
            "44079eb802045d372ab56f4036ab0056dd0d7b3273f51bc0d285cea0e59f3ab1",
        )
        rows = weekly.parse_pdf(data, "Sem_02oct_2021_08oct_2021.pdf")
        target = next(
            r for r in rows
            if r["source_locator"] == "PDF page 62,table 1,column 1,line 5"
        )
        self.assertEqual(
            (target["product_name"], target["market"], target["min"], target["max"], target["price"]),
            ("Café molido", "Palmira (Valle del Cauca)", 19200, 19456, 19354),
        )
        self.assertEqual(target["details"]["literal_product_heading"], "Café molido (continución)")
        self.assertEqual(target["date"], "2021-10-08")

    def test_original_2026_empty_carryover_does_not_join_next_product(self):
        # Exact page 64, with blank predecessors to preserve the PDF locator.
        # Full DANE original bol-SIPSASemanal-31ene06feb-2026.pdf SHA-256:
        # 62516d0607efb77f396f8ee4e94d80bbdda499c372bf643d6802fe3b191ca78f
        data = (FIXTURES / "dane_weekly_2026_01_31_page64.pdf").read_bytes()
        self.assertEqual(
            sha256(data).hexdigest(),
            "604a787804b8ce97bc66c22b2360110b6c31c3dea0a32cc6c128fe2899e875bf",
        )
        rows = weekly.parse_pdf(data, "bol-SIPSASemanal-31ene06feb-2026.pdf")
        galletas = [
            r for r in rows
            if r["product_name"] == "Galletas dulces redondas con crema"
        ]
        self.assertEqual(len(galletas), 12)
        self.assertFalse(any("Fríjol enlatado" in r["product_name"] for r in rows))
        target = next(r for r in galletas if r["source_locator"] == "PDF page 64,table 1,column 1,line 10")
        self.assertEqual(
            (target["market"], target["min"], target["max"], target["price"]),
            ("Ibagué, Plaza La 21", 23667, 24333, 24000),
        )
        self.assertEqual(target["date"], "2026-02-06")


if __name__ == "__main__":
    unittest.main()

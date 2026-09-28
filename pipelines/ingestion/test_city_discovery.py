"""Real DANE archive census and literal old city-report publication dates."""

import io
import json
import os
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urljoin

import pdfplumber
from bs4 import BeautifulSoup

from . import worker
from .city_discovery import archive_day
from .city_reports import parse_city_pdf

BASE = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
FIXTURES = Path(
    os.environ.get(
        "AGRO_CITY_DISCOVERY_FIXTURES",
        str(
            Path(__file__).resolve().parents[2]
            / "artifacts/source-verification-2026-09-28/dane-discovery-city"
        ),
    )
)


class CityArchiveDates(unittest.TestCase):
    def test_both_old_numeric_families_and_current_month_names(self):
        for filename, expected in [
            ("sipsa-25-03-2020.zip", date(2020, 3, 25)),
            ("bol-reg-9-12-2022.zip", date(2022, 12, 9)),
            ("bol-SIPSADiario-regionales-26sep2026.zip", date(2026, 9, 26)),
        ]:
            with self.subTest(filename=filename):
                self.assertEqual(archive_day(BASE + filename), expected)

    def test_archive_labels_do_not_license_unknown_dates_or_file_types(self):
        for url in [
            BASE + "bol-reg-02-10-20.zip",  # A short year is not generally inferable.
            BASE + "sipsa-31-02-2020.zip",
            BASE + "sipsa-25-03-2020.pdf",
            BASE + "mayoristas_diciembre_31_2021.zip",  # Workbook container.
            "https://example.org/files/sipsa-25-03-2020.zip",
            "http://www.dane.gov.co/files/sipsa-25-03-2020.zip",
            "https://www.dane.gov.co.example.org/files/sipsa-25-03-2020.zip",
            "https://www.dane.gov.co/other/sipsa-25-03-2020.zip",
        ]:
            with self.subTest(url=url):
                self.assertIsNone(archive_day(url, "Informes por ciudades"))

    def test_three_verified_publisher_typos_keep_original_urls(self):
        for suffix, day in [("7febb2025", 7), ("6eb2025", 6), ("5eb2025", 5)]:
            url = (
                "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-"
                + suffix
                + ".zip"
            )
            self.assertEqual(archive_day(url), date(2025, 2, day))
        self.assertIsNone(
            archive_day(BASE + "bol-SIPSADiario-regionales-8febb2025.zip")
        )

    def test_exact_short_year_source_is_discovered_but_not_native_price_override(self):
        self.assertEqual(archive_day(BASE + "bol-reg-01-10-20.zip"), date(2022, 10, 1))
        self.assertIsNone(archive_day(BASE + "bol-reg-01-10-21.zip"))

    @unittest.skipUnless(
        (FIXTURES / "originals/bol-reg-01-10-20.zip").exists(),
        "short-year source unavailable",
    )
    def test_corrupt_short_year_native_prices_still_require_independent_fallback(self):
        from .ocr import needs_ocr

        with zipfile.ZipFile(FIXTURES / "originals/bol-reg-01-10-20.zip") as bundle:
            body = bundle.read(next(n for n in bundle.namelist() if n.endswith(".pdf")))
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            text = pdf.pages[0].extract_text() or ""
            self.assertIn("(cid:", text)
            self.assertTrue(needs_ocr(pdf.pages[0], text))
        with self.assertRaises(ValueError):
            list(parse_city_pdf(body, date(2022, 10, 1)))

    def test_future_archives_not_queued_and_source_version_forces_rediscovery(self):
        links = [
            ("Informes por ciudades", BASE + "sipsa-25-03-2020.zip"),
            ("Informes por ciudades", BASE + "sipsa-25-03-2099.zip"),
        ]
        with (
            patch.object(worker, "links", return_value=links),
            patch.object(worker, "queue") as queued,
        ):
            self.assertEqual(
                worker.discover_daily(None, "https://www.dane.gov.co/archive"), 1
            )
        self.assertEqual(
            queued.call_args.args[1:], (links[0][1], "city-zip", date(2020, 3, 25))
        )
        self.assertEqual(worker.parser_version("daily-index"), "source-v3")
        self.assertIn("pipelines/ingestion/city_discovery.py", worker.RELEASE_FILES)

    @unittest.skipUnless(
        (FIXTURES / "discovery-audit.json").exists(),
        "167 official archive fixtures unavailable",
    )
    def test_every_existing_leaf_unchanged_and_975_missing_city_links_recovered(self):
        proof = json.loads((FIXTURES / "discovery-audit.json").read_text())
        prior = json.loads((FIXTURES / "official-leaf-inventory.json").read_text())
        found = {}
        for page in proof["pages"]:
            html = Path(page["path"]).read_bytes()
            links = [
                (a.get_text(" ", strip=True), urljoin(page["url"], a["href"]))
                for a in BeautifulSoup(html, "html.parser").select("a[href]")
            ]

            def queue(_db, url, kind, day=None):
                found[url] = (kind, str(day) if day else None)

            with (
                patch.object(worker, "links", return_value=links),
                patch.object(worker, "queue", side_effect=queue),
            ):
                worker.discover_daily(None, page["url"])
        self.assertEqual(len(prior), 7719)
        for entry in prior:
            self.assertEqual(found[entry["url"]], (entry["kind"], entry["observed_on"]))
        new = {
            url: value
            for url, value in found.items()
            if url not in {x["url"] for x in prior}
        }
        self.assertEqual(len(new), 975)
        self.assertTrue(all(kind == "city-zip" for kind, _ in new.values()))
        self.assertEqual(min(day for _, day in new.values()), "2020-03-25")

    @unittest.skipUnless(
        (FIXTURES / "originals/sipsa-25-03-2020.zip").exists(),
        "real original ZIP fixtures unavailable",
    )
    def test_actual_old_and_typo_zip_first_members_have_exact_printed_dates_prices(
        self,
    ):
        originals = [
            (
                "sipsa-25-03-2020.zip",
                date(2020, 3, 25),
                "Montería, Mercado del Sur",
                13800,
                14200,
            ),
            (
                "sipsa-30-04-2020.zip",
                date(2020, 4, 30),
                "Cúcuta, Cenabastos",
                5000,
                5000,
            ),
            (
                "bol-reg-20-04-2023.zip",
                date(2023, 4, 20),
                "Armenia, Mercar",
                5000,
                5000,
            ),
            (
                "bol-SIPSADiario-regionales-7febb2025.zip",
                date(2025, 2, 7),
                "Armenia, Retiro",
                800,
                900,
            ),
            (
                "bol-SIPSADiario-regionales-6eb2025.zip",
                date(2025, 2, 6),
                "Arauca (Arauca)",
                67000,
                70000,
            ),
            (
                "bol-SIPSADiario-regionales-5eb2025.zip",
                date(2025, 2, 5),
                "Ancuya (Nariño)",
                90720,
                97200,
            ),
        ]
        for name, day, market, low, high in originals:
            with (
                self.subTest(name=name),
                zipfile.ZipFile(FIXTURES / "originals" / name) as bundle,
            ):
                entry = next(n for n in bundle.namelist() if n.lower().endswith(".pdf"))
                body = bundle.read(entry)
                with pdfplumber.open(io.BytesIO(body)) as pdf:
                    self.assertEqual(
                        worker.date_from_text(pdf.pages[0].extract_text()), day
                    )
                rows = list(parse_city_pdf(body, day))
                self.assertTrue(rows)
                self.assertEqual(
                    (rows[0][1], rows[0][4], rows[0][11], rows[0][12]),
                    (day, market, low, high),
                )


if __name__ == "__main__":
    unittest.main()

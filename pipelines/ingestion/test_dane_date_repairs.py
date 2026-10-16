"""Exact retained DANE originals: weekly article boundaries and one daily typo."""

import copy
import hashlib
import re
import shutil
import subprocess
import unittest
from collections import Counter
from datetime import date
from pathlib import Path

import pdfplumber

from . import daily_recovery, dane_weekly, worker
from .retained_date_repairs import BASE, REPAIRS
from .weekly_boundary_review import reviewed_article_bottom


FIXTURES = Path(__file__).parent / "testdata/dane_date_repairs"
WEEKLY = {
    "Semana_16jun_20jun_2014.pdf": (4516, 55, 45, "2014-06-14", "2014-06-20"),
    "Semana_16nov_22nov_2013.pdf": (4486, 57, 47, "2013-11-16", "2013-11-22"),
    "Semana_29nov_6dic_2013.pdf": (4382, 55, 45, "2013-11-30", "2013-12-06"),
    "Semana_6dic_13dic_2013.pdf": (4408, 55, 45, "2013-12-07", "2013-12-13"),
}
PRICE_TRIPLET = re.compile(
    r"(?<!\d)(\d{1,3}(?:\.\d{3})+|\d{4,})\s+"
    r"(\d{1,3}(?:\.\d{3})+|\d{4,})\s+"
    r"(\d{1,3}(?:\.\d{3})+|\d{4,})(?!\d)"
)
DAILY_SHA = "58541524d801feadbce7be1059f9e6d924c58b668785ab3023a2725d5114ac4d"
DAILY_PDF_SHA = "87c4ef6e56d87e02a311432d27a4d0e11b296f4e5edfe842d0434fa29206d3a7"


def original(sha, suffix):
    body = (FIXTURES / (sha + suffix)).read_bytes()
    if hashlib.sha256(body).hexdigest() != sha:
        raise AssertionError("Retained DANE fixture SHA changed")
    return body


class DaneDateRepairOriginals(unittest.TestCase):
    def test_both_repair_modules_are_in_release_manifest(self):
        self.assertIn("pipelines/ingestion/retained_date_repairs.py", worker.RELEASE_FILES)
        self.assertIn("pipelines/ingestion/weekly_boundary_review.py", worker.RELEASE_FILES)

    @unittest.skipUnless(shutil.which("pdftotext"), "Independent Poppler extraction required")
    def test_complete_weekly_sources_match_independent_page43_money(self):
        for name, (total, page_count, priced, start, end) in WEEKLY.items():
            url = BASE + name
            sha = REPAIRS[url][1]
            source = FIXTURES / (sha + ".pdf")
            rows = dane_weekly.parse_pdf(original(sha, ".pdf"), url)
            page = [r for r in rows if r["source_page"] == 43]
            text = subprocess.check_output(
                ["pdftotext", "-f", "43", "-l", "43", "-layout", str(source), "-"],
                text=True,
            )
            self.assertEqual(text.count("Tendencias:"), 1)
            self.assertEqual(text.count("Precios de la panela"), 1)
            grid = text.split("Tendencias:", 1)[0]
            native = Counter(
                tuple(int(value.replace(".", "")) for value in match)
                for match in PRICE_TRIPLET.findall(grid)
            )
            parsed = Counter(
                (
                    int(row["min"]), int(row["max"]),
                    int(row["price"] if row["price"] is not None else row["details"]["literal_mean"]),
                )
                for row in page
            )
            with self.subTest(name=name):
                self.assertEqual((len(rows), len(page), sum(r["price"] is not None for r in page)),
                                 (total, page_count, priced))
                self.assertEqual(native, parsed)
                self.assertEqual(sum(native.values()), page_count)
                self.assertEqual({(r["period_start"], r["date"]) for r in page}, {(start, end)})
                self.assertEqual({r["unit"] for r in page if r["price"] is not None}, {"kg"})
                self.assertEqual({r["unit"] for r in page if r["price"] is None}, {"unverified"})
                self.assertTrue(all(r["source_locator"].startswith("PDF page 43,") for r in page))
                expected_version = ("official-v2:jun2014-panela-article-single-price-v1:dane-weekly-v24"
                                    if "16jun_20jun_2014" in name else "official-v2:dane-weekly-v24")
                self.assertEqual(worker.parser_version("dane-weekly-pdf", url), expected_version)
                self.assertEqual(worker.asset_parser_version("dane-weekly-pdf", url),
                                 expected_version if "16jun_20jun_2014" in name
                                 else expected_version + REPAIRS[url][3])

    def test_page_boundary_requires_exact_original_and_unchanged_title(self):
        for name in WEEKLY:
            url = BASE + name
            sha = REPAIRS[url][1]
            with pdfplumber.open(FIXTURES / (sha + ".pdf")) as pdf:
                page = pdf.pages[42]
                words = page.extract_words()
                top = next(w["top"] for w in words if w["text"] == "Cuadro" and w["x0"] < page.width * .2)
                bottom = reviewed_article_bottom(url, sha, 43, words, top, page.height)
                with self.subTest(name=name):
                    self.assertLess(bottom, page.height)
                    self.assertEqual(reviewed_article_bottom(url, "0" * 64, 43, words, top, page.height), page.height)
                    self.assertEqual(reviewed_article_bottom(url, sha, 42, words, top, page.height), page.height)
                    changed = copy.deepcopy(words)
                    for word in changed:
                        if word["text"] == "panela" and abs(word["top"] - (bottom + .1)) < .5:
                            word["text"] = "otro"
                    with self.assertRaisesRegex(ValueError, "boundary changed"):
                        reviewed_article_bottom(url, sha, 43, changed, top, page.height)

    def test_adjacent_weekly_unchanged_and_march_ambiguity_held(self):
        neighbor = "3b907b05e75e303d4acd234c1b720ff3f6a2df73b466ffb03b45592d0cb80cfd"
        rows = dane_weekly.parse_pdf(original(neighbor, ".pdf"), BASE + "Semana_23nov_29nov_2013.pdf")
        self.assertEqual((len(rows), sum(r["price"] is not None for r in rows)), (4498, 4350))
        march = "801da510849a022ed5eb41e0120502ef933faeec783735dcf0645c4c278fc8e6"
        with self.assertRaises(worker.SourceDateMismatch):
            dane_weekly.parse_pdf(original(march, ".pdf"), BASE + "Sem_18mar_24mar_2016.pdf")

    @unittest.skipUnless(shutil.which("pdftotext"), "Independent Poppler extraction required")
    def test_daily_review_binds_three_native_cells_and_rejects_other_dates(self):
        body = original(DAILY_SHA, ".xls")
        pdf = FIXTURES / (DAILY_PDF_SHA + ".pdf")
        original(DAILY_PDF_SHA, ".pdf")
        pdf_text = subprocess.check_output(["pdftotext", "-layout", str(pdf), "-"], text=True)
        self.assertTrue(pdf_text.startswith("20 de febrero de 2017"))
        self.assertTrue(all(value in pdf_text for value in ("$2.425", "$1.604", "$2.389")))
        sheet, iterator = next(iter(worker.workbooks(body)))
        cells = list(iterator)
        self.assertEqual(sheet, "Boletín diario")
        self.assertEqual(cells[1][0], "Lunes 20 de enero de 2017")
        for product, column, price in (("Pimentón", 7, 2425),
                                       ("Cebolla cabezona blanca", 7, 1604),
                                       ("Cebolla junca", 5, 2389)):
            matching = [row for row in cells if row and row[0] == product]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0][column], price)
        parsed = daily_recovery.parse_daily(body, date(2017, 2, 20))
        self.assertEqual((len(parsed["rows"]), len(parsed["reviews"]), len(parsed["date_resolutions"])),
                         (393, 0, 1))
        self.assertEqual(parsed["date_resolutions"][0]["printed_heading"], cells[1][0])
        for wrong in (date(2017, 1, 20), date(2017, 2, 21)):
            with self.assertRaises(worker.SourceDateMismatch):
                daily_recovery.parse_daily(body, wrong)
        changed = bytearray(body)
        changed[-1] ^= 1
        self.assertNotIn(hashlib.sha256(changed).hexdigest(), daily_recovery.VERIFIED_DATE_RECOVERIES)
        self.assertEqual(worker.asset_parser_version("daily", BASE + "mayoristas_febrero_20_2017.xls"),
                         "daily-units-v6:dane-daily-query-v1:feb2017-native-month-review-v1")

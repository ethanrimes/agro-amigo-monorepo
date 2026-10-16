"""Retained DANE pages with cross-month captions and literal five-digit years.

Fixtures contain unchanged original pages, blank-padded to preserve source page
numbers. Full-original hashes and page selections are recorded below.
"""
import hashlib
import io
from datetime import date
from pathlib import Path
import unittest

from pypdf import PdfReader, PdfWriter

from . import dane_weekly as weekly

DATA = Path(__file__).parent / "testdata"
ROOT = "https://www.dane.gov.co/files/operaciones/SIPSA/"
JULY_AUDIT = Path(__file__).resolve().parents[2] / "artifacts/qa-resumed-20261001/web/weekly-date-audit"


class WeeklyCaptionReview(unittest.TestCase):
    @unittest.skipUnless(
        (JULY_AUDIT / (weekly.JULY_2023_BULLETIN_SHA + ".pdf")).exists()
        and (JULY_AUDIT / (weekly.JULY_2023_MATCHING_ANNEX_SHA + ".xlsx")).exists(),
        "Two exact DANE original fixtures are required",
    )
    def test_july2023_misprinted_pdf_captions_need_same_week_annex_parity(self):
        from .worker import SourceDateMismatch

        pdf = (JULY_AUDIT / (weekly.JULY_2023_BULLETIN_SHA + ".pdf")).read_bytes()
        annex = (JULY_AUDIT / (weekly.JULY_2023_MATCHING_ANNEX_SHA + ".xlsx")).read_bytes()
        self.assertEqual(hashlib.sha256(pdf).hexdigest(), weekly.JULY_2023_BULLETIN_SHA)
        self.assertEqual(hashlib.sha256(annex).hexdigest(), weekly.JULY_2023_MATCHING_ANNEX_SHA)
        pdf_rows = weekly.parse_pdf(pdf, weekly.JULY_2023_BULLETIN_URL)
        annex_rows = weekly.parse_workbook(
            annex, ROOT + "anex-SIPSASemanal-22jul-28jul-2023.xlsx"
        )
        self.assertEqual((len(pdf_rows), sum(r["price"] is not None for r in pdf_rows)),
                         (4342, 4210))
        self.assertEqual({(r["period_start"], r["date"]) for r in pdf_rows},
                         {("2023-07-22", "2023-07-28")})
        self.assertEqual({r["details"]["literal_printed_period_end"] for r in pdf_rows},
                         {"2023-07-21"})
        annex_prices = {
            (r["product_name"], r["market"], r["min"], r["max"], r["price"])
            for r in annex_rows if r["price"] is not None
        }
        self.assertTrue(all(
            (r["product_name"], r["market"], r["min"], r["max"], r["price"])
            in annex_prices for r in pdf_rows if r["price"] is not None
        ))
        with self.assertRaises(SourceDateMismatch):
            weekly.parse_pdf(pdf + b"changed-byte", weekly.JULY_2023_BULLETIN_URL)

    def test_native_captions_without_de_and_month_first_cross_month(self):
        # Whole, byte-identical originals; five prices independently read from
        # rendered physical page 10 in each bulletin.
        cases = (
            ("bol-SIPSASemanal-02mar-08mar-2024.pdf",
             "23797dbaba4a9eadc3f9a12695555712f28bb1e4e05867a7defc3c5aff73af2a",
             "2024-03-02", "2024-03-08", 4419, 4288,
             ((1333, 1533, 1400), (533, 1000, 711), (2000, 3000, 2233),
              (700, 800, 763), (14000, 16000, 15278))),
            ("bol-SIPSASemanal-28oct-03nov-2023.pdf",
             "c3aca339061bba713590c1593d4ef10c39b83d5947504fd5ab2d9170b7e9b0d0",
             "2023-10-28", "2023-11-03", 4408, 4279,
             ((1000, 1200, 1100), (200, 533, 365), (2000, 2000, 2000),
              (1000, 1000, 1000), (9000, 10000, 9838))),
        )
        identities = (
            ("Acelga", "Armenia, Mercar"),
            ("Acelga", "Bogotá, D.C., Corabastos"),
            ("Acelga", "Bucaramanga, Centroabastos"),
            ("Ahuyama", "Cali, Santa Elena"),
            ("Ajo", "Bogotá, D.C., Corabastos"),
        )
        for filename, digest, start, end, count, eligible, prices in cases:
            with self.subTest(source=filename):
                body = (DATA / filename).read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), digest)
                rows = weekly.parse_pdf(body, ROOT + filename)
                self.assertEqual(len(rows), count)
                self.assertEqual(sum(r["price"] is not None for r in rows), eligible)
                for (product, market), expected in zip(identities, prices):
                    row = next(r for r in rows if r["source_page"] == 10
                               and r["product_name"] == product and r["market"] == market)
                    self.assertEqual((row["min"], row["max"], row["price"]), expected)
                    self.assertEqual((row["period_start"], row["date"]), (start, end))

    def test_added_caption_forms_require_valid_explicit_weekly_evidence(self):
        for text in (
            "20242 (2 al 8 marzo)", "2023 (octubre 28 al 3 de noviembre) 20252",
            "2 al 8 marzo", "octubre 28 al 3 de noviembre",
        ):
            # A separate later malformed number cannot invalidate a complete
            # explicit caption, but absent/five-digit caption years cannot pass.
            if text.startswith("2023"):
                self.assertEqual(weekly._period(text),
                                 (weekly.date(2023, 10, 28), weekly.date(2023, 11, 3)))
            else:
                self.assertIsNone(weekly._period(text))
        for text in ("2023 (octubre 1 al 3 de noviembre)",
                     "2023 (diciembre 30 al 5 de enero)",
                     "2024 (2 al 31 marzo)"):
            with self.subTest(caption=text), self.assertRaises(ValueError):
                weekly._period(text)

    def test_cross_month_a_captions_keep_literal_price_and_period(self):
        cases = (
            ("bol-SIPSASemanal-28sep-4oct-2024.pdf",
             "dane_weekly_2024_10_04_caption_page10.pdf",
             "92b65677ff439ec6d389cd9430fbb9ec60e1ac3cd1d52fdf2fd24262da37b870",
             # Full original SHA: 6e886d8be1d0fe6be6516e44d41b1cc8dd27746ca9d386481e91229e53acfca2
             10, "2024-09-28", "2024-10-04", (333, 1000, 507)),
            ("bol-SIPSASemanal-30nov-06dic-2024.pdf",
             "dane_weekly_2024_12_06_caption_page11.pdf",
             "c34ba8c8ac0ca3ab659925e694166b550085f96f87453bf9412c0848de06462d",
             # Full original SHA: 11e074cf0f92477582137dc179ad7c5ed69d9396053b1cc0a767bb8aef6e29cd
             11, "2024-11-30", "2024-12-06", (667, 1000, 781)),
        )
        for url, fixture, digest, page, first, last, prices in cases:
            with self.subTest(source=url):
                body = (DATA / fixture).read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), digest)
                rows = weekly.parse_pdf(body, ROOT + url)
                sample = next(r for r in rows if r["product_name"] == "Acelga"
                              and r["market"] == "Bogotá, D.C., Corabastos")
                self.assertEqual((sample["min"], sample["max"], sample["price"]), prices)
                self.assertEqual((sample["period_start"], sample["date"]), (first, last))
                self.assertEqual(sample["source_page"], page)

    def test_malformed_printed_year_withholds_only_that_page(self):
        cases = (
            ("bol-SIPSASemanal-26jul01ago-2025.pdf",
             "dane_weekly_2025_08_01_caption_pages.pdf",
             "0b14b3f7f01918589159f33388d4fe69269161358a84cb6d22418e29cb89c386",
             # Full original SHA: 4ed29c7e57f92ac34c2b7f7d5c05b1726dac18426ab060c6e066af671d511533
             29, "20252", "Manzana roja importada",
             "Medellín, Central Mayorista de Antioquia", (8158, 8947, 8618), 983),
            ("bol-SIPSASemanal-09nov-15nov-2024.pdf",
             "dane_weekly_2024_11_15_caption_pages.pdf",
             "b19c99169b9e0aa21b445a0291c2b6e60df67b7888bde702fefb6a1bcad06b78",
             # Full original SHA: 338741f02a588e6d3cd4a0110625516934f94128f25d20eb8d1becf18224c601
             67, "22024", "Panela cuadrada morena",
             "Bogotá, D.C., Plaza España", (5000, 5145, 5074), 345),
        )
        for url, fixture, digest, bad, literal_year, product, market, prices, good_price in cases:
            with self.subTest(source=url):
                body = (DATA / fixture).read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), digest)
                rows = weekly.parse_pdf(body, ROOT + url)
                reviewed = [r for r in rows if r["source_page"] == bad]
                self.assertGreater(len(reviewed), 50)
                self.assertTrue(all(r["price"] is None for r in reviewed))
                sample = next(r for r in reviewed if r["product_name"] == product
                              and r["market"] == market)
                self.assertEqual((sample["min"], sample["max"],
                                  sample["details"]["literal_mean"]), prices)
                self.assertIn(literal_year, sample["details"]["literal_printed_table_context"])
                self.assertIn("unverified", sample["details"]["period_evidence"])
                valid = next(r for r in rows if r["source_page"] == 11
                             and r["product_name"] == "Acelga"
                             and r["market"] == "Bogotá, D.C., Corabastos")
                self.assertEqual(valid["price"], good_price)

    def test_filename_alone_cannot_corroborate_a_malformed_year(self):
        original = PdfReader(DATA / "dane_weekly_2025_08_01_caption_pages.pdf")
        writer = PdfWriter()
        for number, page in enumerate(original.pages, 1):
            if number == 29:
                writer.add_page(page)
            else:
                writer.add_blank_page(width=page.mediabox.width, height=page.mediabox.height)
        body = io.BytesIO()
        writer.write(body)
        with self.assertRaisesRegex(ValueError, "no verified monetary-table period"):
            weekly.parse_pdf(body.getvalue(), ROOT + "bol-SIPSASemanal-26jul01ago-2025.pdf")

    def test_workbook_printed_zero_preserves_valid_siblings(self):
        body = (DATA / "anex-SIPSASemanal-15jun-21jun-2024.xlsx").read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(),
                         "18ac9df69d3998d464de48f7aeb1594d39b223bcbc84debe18ce3846c280e0b0")
        rows = weekly.parse_workbook(body, ROOT + "anex-SIPSASemanal-15jun-21jun-2024.xlsx")
        self.assertEqual((len(rows), sum(r["price"] is not None for r in rows)), (4421, 4420))
        zero = next(r for r in rows if r["source_locator"] == "1.1!row 754,cols C:E")
        self.assertIsNone(zero["price"])
        self.assertEqual((zero["min"], zero["max"], zero["details"]["literal_mean"]), (0, 1152, 989))
        good = next(r for r in rows if r["source_locator"] == "1.1!row 755,cols C:E")
        self.assertEqual((good["product_name"], good["market"], good["min"], good["max"], good["price"]),
                         ("Remolacha", "Pereira, Mercasa", 1000, 1500, 1200))

    def test_exact_march_workbook_uses_official_printed_period_not_url_typo(self):
        from .worker import SourceDateMismatch

        body = (DATA / "anex-SIPSASemanal-09mar-16mar-2024.xlsx").read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(),
                         "a1d2992f6bee7ce29c12ed1cee92feb31a9204ffe5546cd3276bab0cc09436e6")
        url = ROOT + "anex-SIPSASemanal-09mar-16mar-2024.xlsx"
        rows = weekly.parse_workbook(body, url)
        self.assertEqual(len(rows), 4423)
        self.assertEqual({(r["period_start"], r["date"]) for r in rows},
                         {("2024-03-09", "2024-03-15")})
        self.assertEqual(weekly.source_date(url), date(2024, 3, 15))
        self.assertTrue(all(r["details"]["literal_printed_period_end"] == "2024-03-15"
                            for r in rows))
        with self.assertRaisesRegex(SourceDateMismatch,
                                    "printed 2024-03-09–2024-03-15; filename 2024-03-09–2024-03-16"):
            weekly.parse_workbook(body + b"changed-byte", url)


if __name__ == "__main__":
    unittest.main()

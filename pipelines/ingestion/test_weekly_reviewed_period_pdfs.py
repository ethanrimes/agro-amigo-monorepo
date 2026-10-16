"""Exact-source printed period controls for two archived weekly PDFs."""
import hashlib
import json
import re
import unittest
from datetime import date
from pathlib import Path

import pdfplumber

from . import dane_weekly


FIXTURES = Path(__file__).parent / "testdata" / "weekly_reviewed_period"
CASES = (
    (dane_weekly.APRIL_2017_EXTENDED_PERIOD_URL,
     dane_weekly.APRIL_2017_EXTENDED_PERIOD_SHA,
     dane_weekly.APRIL_2017_EXTENDED_PERIOD_PERIOD,
     40, 4625, 4472, 153,
     "436883ca5e0c0364039977f0c9aeaf281d2de702c2cee9d340096cb9bc56ef67"),
    (dane_weekly.JANUARY_2015_SPACED_YEARS_URL,
     dane_weekly.JANUARY_2015_SPACED_YEARS_SHA,
     dane_weekly.JANUARY_2015_SPACED_YEARS_PERIOD,
     37, 4427, 4291, 136,
     "9e8baef08816e551a1040552b608e7540b95814205a2694bde708091a7c21dfd"),
)


class ReviewedWeeklyPeriodPDFs(unittest.TestCase):
    def test_whole_originals_printed_captions_and_all_native_rows(self):
        for url, did, period, captions, total, priced, review, rows_sha in CASES:
            with self.subTest(url=url):
                body = (FIXTURES / f"{did}.pdf").read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), did)
                with pdfplumber.open(FIXTURES / f"{did}.pdf") as pdf:
                    self.assertEqual(len(pdf.pages), 44)
                    full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
                    cover = pdf.pages[0].crop((0, 0, pdf.pages[0].width * .5,
                                               pdf.pages[0].height)).extract_text() or ""
                source_guard = dane_weekly.REVIEWED_PDF_PERIODS[url]
                self.assertEqual(len(source_guard[2].findall(full_text)), captions)
                self.assertRegex(cover, source_guard[4])
                self.assertEqual(dane_weekly.source_date(url), period[1])
                rows = dane_weekly.parse_pdf(body, url)
                self.assertEqual((len(rows), sum(r["price"] is not None for r in rows),
                                  sum(r["price"] is None for r in rows)),
                                 (total, priced, review))
                self.assertEqual(len({r["source_locator"] for r in rows}), total)
                self.assertEqual({r["date"] for r in rows}, {period[1].isoformat()})
                self.assertEqual({r["period_start"] for r in rows},
                                 {period[0].isoformat()})
                self.assertEqual(hashlib.sha256(json.dumps(
                    rows, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest(), rows_sha)

    def test_changed_bytes_and_nearby_periods_do_not_inherit_review(self):
        for url, did, _period, *_ in CASES:
            with self.subTest(url=url):
                body = (FIXTURES / f"{did}.pdf").read_bytes()
                with self.assertRaisesRegex(ValueError, "source bytes changed"):
                    dane_weekly.parse_pdf(body + b"\n", url)
                near_url = url.replace(".pdf", "-near.pdf")
                self.assertIsNone(dane_weekly.source_date(near_url))
                self.assertNotIn(near_url, dane_weekly.REVIEWED_PDF_PERIODS)
        with self.assertRaisesRegex(ValueError, "not a supported weekly period"):
            dane_weekly._period("2017 (13 al 21 de abril)")
        with self.assertRaisesRegex(ValueError, "not a supported weekly period"):
            dane_weekly._period("2014 - 2015 (27 de diciembre al 2 de enero)")


if __name__ == "__main__":
    unittest.main()

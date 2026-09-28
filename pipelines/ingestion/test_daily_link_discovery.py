"""Real February2014 native originals and official labels for malformed names."""

import io
import json
import unittest
from datetime import date
from unittest.mock import Mock, patch

import pdfplumber

from . import daily_recovery, worker
from .daily_discovery import verified_daily_day
from .pdf_sources import parse_archived_price_pdf
from .test_city_discovery import FIXTURES

BASE = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
SOURCES = [
    ("mayoristas_febrero_199_2014.pdf", "Boletín - 19 de febrero", date(2014, 2, 19)),
    ("mayoristas_febrero_5r_2014.pdf", "Boletín - 5 de febrero", date(2014, 2, 5)),
    ("mayoristas_febreroR_5_2014.xls", "Anexo - 5 de febrero", date(2014, 2, 5)),
]


class VerifiedDailyFilenameTests(unittest.TestCase):
    def test_exact_official_urls_keep_dates_without_filename_repair(self):
        links = [(label, BASE + name) for name, label, _ in SOURCES]
        with (
            patch.object(worker, "links", return_value=links),
            patch.object(worker, "queue") as queued,
        ):
            self.assertEqual(
                worker.discover_daily(None, "https://www.dane.gov.co/archive"), 3
            )
        self.assertEqual(
            [c.args[1:] for c in queued.call_args_list],
            [
                (BASE + n, "daily" if n.endswith("xls") else "daily-pdf", d)
                for n, _, d in SOURCES
            ],
        )
        self.assertEqual(worker.parser_version("daily-index"), "source-v5")

    def test_no_general_typo_guess_or_external_url(self):
        for url in [
            BASE + "mayoristas_febrero_199_2013.pdf",
            BASE + "mayoristas_febrero_6r_2014.pdf",
            BASE + "mayoristas_febreroR_6_2014.xls",
            (BASE + SOURCES[0][0]).replace("https:", "http:"),
            (BASE + SOURCES[0][0]).replace("www.dane.gov.co", "evil.example"),
        ]:
            self.assertIsNone(verified_daily_day(url))

    @unittest.skipUnless(
        (FIXTURES / "february-2014/proof.json").exists(),
        "Actual official original fixtures unavailable",
    )
    def test_exact_original_sha_native_dates_and_readable_narrative_avoids_ocr(self):
        from hashlib import sha256

        proof = json.loads((FIXTURES / "february-2014/proof.json").read_text())
        for name, _, day in SOURCES:
            body = (FIXTURES / "february-2014" / name).read_bytes()
            self.assertEqual(
                sha256(body).hexdigest(),
                next(r["sha256"] for r in proof if r["url"].endswith("/" + name)),
            )
            if name.endswith("pdf"):
                with pdfplumber.open(io.BytesIO(body)) as pdf:
                    self.assertTrue(
                        pdf.pages[0]
                        .extract_text()
                        .startswith(f"Febrero {day.day} de 2014")
                    )
                db = Mock()
                db.execute.side_effect = AssertionError(
                    "Readable narrative does not need OCR or database access"
                )
                with self.assertRaisesRegex(ValueError, "No supported price grids"):
                    list(
                        parse_archived_price_pdf(
                            db, body, sha256(body).hexdigest(), day, "daily-pdf"
                        )
                    )
                db.execute.assert_not_called()
            else:
                result = daily_recovery.parse_daily(body, day)
                self.assertEqual(
                    (len(result["rows"]), len(result["reviews"])), (294, 0)
                )
                anchor = next(
                    r
                    for r in result["rows"]
                    if r[3] == "Pimentón" and r[4] == "Bogotá, D.C., Corabastos"
                )
                self.assertEqual((anchor[2], anchor[5], anchor[6]), (day, "kg", 2800))
                self.assertEqual(anchor[7], 35)


if __name__ == "__main__":
    unittest.main()

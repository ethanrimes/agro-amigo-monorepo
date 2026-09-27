"""Published zero terciles remain review evidence without blocking valid prices."""

import hashlib
import re
import unittest
from collections import Counter
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from . import colombia_sources as source
from . import official_catalog, official_sources

FIXTURE = Path(
    "artifacts/extraction-robustness-2026-09-27/pork-zero-check/Quincena16de2026_.pdf"
)


class PorkZeroTerciles(unittest.TestCase):
    def test_literal_zero_is_review_before_positive_number_decoder(self):
        page = SimpleNamespace(width=600, height=800)
        header = [{"text": "Mercado", "x0": x, "x1": x + 40} for x in (20, 220, 420)]
        original = source._pork_native_number
        for token in ("0", "0,0", "0,00", "0.000"):
            with self.subTest(token=token):

                def lines(_page, bbox=None, printed_zero=token):
                    if bbox is None:
                        return [
                            (10, [], "PRECIOS PROMEDIOS"),
                            (20, header, "Mercado Mercado Mercado"),
                            (60, [], "*Precio promedio"),
                        ]
                    return (
                        [(30, [], f"Antioquia {printed_zero} 6.100 6.035")]
                        if bbox[0] < 100
                        else []
                    )

                with (
                    patch.object(source, "_pdf_lines", side_effect=lines),
                    patch.object(
                        source, "_pork_native_number", wraps=original
                    ) as decoder,
                ):
                    rows = source._pork_terciles(page, 1, date(2026, 7, 31))
                self.assertEqual(len(rows), 3)
                self.assertIsNone(rows[0]["price"])
                self.assertEqual(rows[0]["details"]["original_price"], token)
                self.assertIn("zero", rows[0]["details"]["quality_issue"])
                self.assertEqual([r["price"] for r in rows[1:]], [6100, 6035])
                self.assertNotIn(
                    token, [call.args[0] for call in decoder.call_args_list]
                )

    def test_general_number_decoder_still_rejects_negative_malformed_and_zero(self):
        for token in ("-100", "-0,1", "6,1?0", "0", "0,00"):
            with self.subTest(token=token), self.assertRaises(ValueError):
                source._pork_native_number(token)
        self.assertEqual(source._pork_native_number("6.100"), 6100)

    @unittest.skipUnless(FIXTURE.exists(), "Downloaded authoritative PDF unavailable")
    def test_actual_july31_original_retains_nine_zeros_and_all_valid_neighbors(self):
        body = FIXTURE.read_bytes()
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "eb9ecdd4c2654a8ca27ec19ec7400ab3c1998810bde23ac62c37be268e09271c",
        )
        rows = source.parse(
            body,
            "https://porkcolombia.co/wp-content/uploads/2026/08/Quincena16de2026_.pdf",
            "colombia-pork-pdf",
        )
        reviews = [r for r in rows if r["price"] is None]
        date_reviews = [
            r
            for r in rows
            if r["price"] is not None and r["details"].get("quality_issue")
        ]
        quotes = [r for r in rows if not r["details"].get("quality_issue")]
        self.assertEqual(len(rows), 295)
        self.assertEqual(len(quotes), 280)
        self.assertEqual(len(date_reviews), 6)
        self.assertTrue(
            all(
                "out of sequence" in r["details"]["quality_issue"] for r in date_reviews
            )
        )
        self.assertEqual(
            {r["details"]["original_period"] for r in date_reviews},
            {"Nov-24", "Dic-24"},
        )
        self.assertEqual(
            Counter(r["series"] for r in quotes),
            {
                "porkcolombia-current": 43,
                "porkcolombia-tercile": 33,
                "porkcolombia-monthly": 204,
            },
        )
        expected_reviews = {
            (name, market, segment)
            for name, market in (
                ("Cerdo en pie", "Eje Cafetero"),
                ("Cerdo · canal fría", "Caribe Norte"),
                ("Cerdo · canal fría", "Tolima - Huila"),
            )
            for segment in ("superior", "medio", "inferior")
        }
        self.assertEqual(
            {
                (r["product_name"], r["market"], r["details"]["price_segment"])
                for r in reviews
            },
            expected_reviews,
        )
        self.assertEqual(len(reviews), 9)
        for row in reviews:
            self.assertIsNone(row["price"])
            self.assertEqual(row["details"]["original_price"], "0")
            self.assertEqual(row["details"]["source_page"], 1)
            self.assertEqual(row["date"], "2026-07-31")
            self.assertIn("zero", row["details"]["quality_issue"])
        current = {
            (r["product_name"], r["market"]): r["price"]
            for r in quotes
            if r["series"] == "porkcolombia-current" and r["date"] == "2026-07-31"
        }
        self.assertEqual(
            current,
            {
                ("Cerdo en pie", "Antioquia"): 6101,
                ("Cerdo en pie", "Valle del Cauca"): 6204,
                ("Cerdo en pie", "Caribe Norte"): 6529,
                ("Cerdo en pie", "Bogotá"): 6906,
                ("Cerdo en pie", "Tolima - Huila"): 6741,
                ("Cerdo en pie", "Colombia"): 6380,
                ("Cerdo · canal caliente", "Valle del Cauca"): 8763,
                ("Cerdo · canal caliente", "Caribe Norte"): 9032,
                ("Cerdo · canal caliente", "Colombia"): 9026,
                ("Cerdo · canal fría", "Antioquia"): 9329,
                ("Cerdo · canal fría", "Eje Cafetero"): 8876,
                ("Cerdo · canal fría", "Valle del Cauca"): 9129,
                ("Cerdo · canal fría", "Bogotá"): 10898,
                ("Cerdo · canal fría", "Colombia"): 9280,
            },
        )
        self.assertEqual(len({r["source_locator"] for r in rows}), len(rows))
        self.assertTrue(all(r["price"] > 0 and r["currency"] == "COP" for r in quotes))
        self.assertTrue(
            all(r["details"]["parser_version"] == source.VERSION for r in rows)
        )
        self.assertTrue(
            all(not re.search("ocr", str(r["details"]), re.IGNORECASE) for r in rows)
        )

        # Exercise actual publisher prevalidation/classification without a
        # database connection: only its final SQL transport is captured here.
        class CaptureDB:
            def __init__(self):
                self.quotes = []
                self.reviews = []

            def cursor(self):
                return self

            def transaction(self):
                return nullcontext()

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def execute(self, *_):
                return None

            def executemany(self, _, values):
                self.reviews.extend(values)

            def copy(self, _):
                return self

            def write_row(self, value):
                self.quotes.append(value)

        db = CaptureDB()
        with patch.object(official_catalog, "refresh_document"):
            published = official_sources.publish_rows(
                db, rows, "original", "colombia-pork-pdf"
            )
        self.assertEqual(published, 280)
        self.assertEqual(len(db.quotes), 280)
        self.assertEqual(len(db.reviews), 15)
        self.assertEqual(sum(r[3].obj["price"] is None for r in db.reviews), 9)
        self.assertTrue(all(row[15] > 0 for row in db.quotes))

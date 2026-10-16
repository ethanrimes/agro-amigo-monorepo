"""Readable quoted DANE headings must not become punctuation-only products."""

import unittest
import os
from datetime import date
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from . import dane_weekly as weekly


class WeeklyWrappedQuotation(unittest.TestCase):
    def test_original_december_2022_page_recovers_all_five_literal_prices(self):
        # Unmodified native page 36 preceded by 35 blank pages. Full original:
        # https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/
        # bol_24dic_al_30dic_2022.pdf
        # Full SHA: 0a6cc31643680d8f0614966ed85eda6c0997f60f1f5efdcda4eedc2aed6e91e5
        body = (Path(__file__).parent / "testdata/dane_weekly_2022_12_30_page36.pdf").read_bytes()
        self.assertEqual(sha256(body).hexdigest(),
                         "a68241866fbbfd9743e927a99495c97362cb46b2448087d9e9bd28acd0094ba7")
        rows = weekly.parse_pdf(body, "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_24dic_al_30dic_2022.pdf")
        selected = [r for r in rows if r["product_name"] == "Papa R-12 negra"]
        # Independently transcribed from the rendered original, not parser output.
        expected = {
            "Bogotá, D.C., Corabastos": (2360, 2600, 2496),
            "Cartago (Valle del Cauca)": (2200, 2400, 2315),
            "Manizales, Centro Galerías": (2960, 3000, 2993),
            "Medellín, Central Mayorista de Antioquia": (2800, 3000, 2910),
            "Neiva, Surabastos": (2600, 2800, 2727),
        }
        self.assertEqual({r["market"]: (r["min"], r["max"], r["price"]) for r in selected}, expected)
        for r in selected:
            self.assertEqual(r["product_id"], "papa-r-12-negra")
            self.assertEqual((r["period_start"], r["date"], r["unit"]), ("2022-12-24", "2022-12-30", "kg"))
            self.assertEqual(r["source_page"], 36)
            self.assertEqual(r["details"]["literal_product_heading"], '"Papa R-12 negra "')
        self.assertFalse(any(not r["product_id"] and r["price"] is not None for r in rows))
        # The neighbouring potato must retain its own identity and literal value.
        red = next(r for r in rows if r["product_name"] == "Papa R-12 roja")
        self.assertEqual((red["market"], red["price"]), ("Bogotá, D.C., Corabastos", 2206))
        purace = [r for r in rows if r["product_name"] == "Papa Puracé"]
        self.assertEqual({r["market"]: r["price"] for r in purace}, {
            "La Unión (Antioquia)": 2550,
            "Montería, Mercado del Sur": 3450,
            "Sincelejo, Nuevo Mercado": 3175,
        })

    def test_missing_opening_heading_withholds_prices_and_preserves_literals(self):
        def word(text, x, top, bold=False):
            return {"text": text, "x0": x, "x1": x + len(text) * 3,
                    "top": top, "fontname": "FuturaStd-Bold" if bold else "FuturaStd-Book"}
        lines = [
            [word("Papa Puracé", 36, 10, True)],
            [word("La Unión (Antioquia)", 36, 20), word("2.500", 180, 20), word("2.600", 215, 20), word("2.550", 250, 20)],
            [word('"', 36, 40)],
            [word("Bogotá, D.C., Corabastos", 36, 50), word("2.360", 180, 50), word("2.600", 215, 50), word("2.496", 250, 50)],
        ]
        rows = weekly._native_column(lines, [{"x0": x, "x1": x + 25} for x in (170, 205, 240)],
                                     "tubérculos", (date(2022, 12, 24), date(2022, 12, 30)), 36, 1, 2, {})
        self.assertEqual(rows[0]["price"], 2550)
        self.assertEqual(rows[1]["product_name"], "")
        self.assertIsNone(rows[1]["price"])
        self.assertEqual(rows[1]["details"]["literal_mean"], 2496)
        self.assertEqual(rows[1]["details"]["literal_product_heading"], '"')

    def test_punctuation_product_remains_review_when_identity_is_unavailable(self):
        row = weekly._row('"', "Bogotá, D.C., Corabastos", 2360, 2600, 2496, "+",
                          "tubérculos", (date(2022, 12, 24), date(2022, 12, 30)),
                          "PDF page 36,column 2", allow_missing_identity=True)
        self.assertIsNone(row["price"])
        self.assertEqual(row["details"]["literal_product_name"], '"')
        self.assertEqual(row["details"]["literal_mean"], 2496)


@unittest.skipUnless(os.environ.get("AGRO_OFFICIAL_CATALOG_TEST") == "1",
                     "Explicit opt-in for private PostgreSQL TEMP tables")
class WeeklyQuotationPublication(unittest.TestCase):
    def test_real_page_publishes_every_literal_row_idempotently(self):
        from . import official_sources, worker, write_pacing
        from .test_official_catalog import install_cache

        body = (Path(__file__).parent / "testdata/dane_weekly_2022_12_30_page36.pdf").read_bytes()
        did = sha256(body).hexdigest()
        url = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_24dic_al_30dic_2022.pdf"
        rows = weekly.parse_pdf(body, url)
        expected = sum(r["price"] is not None for r in rows)
        with worker.connect() as db:
            db.execute("SET search_path=pg_temp; SET statement_timeout='15s'")
            for table in ("source_document", "official_price_quote", "official_source_review",
                          "ingestion_asset", "ingestion_checkpoint"):
                db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")
                self.assertEqual(db.execute("SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)",
                                            (table,)).fetchone(), ("t",))
            install_cache(db)
            db.execute("INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content) "
                       "VALUES(%s,'Original page 36','DANE',%s,'application/pdf','original','2022',%s)", (did, url, body))
            db.execute("INSERT INTO ingestion_asset(url,kind,document_id,status) VALUES(%s,'dane-weekly-pdf',%s,'complete')",
                       (url, did))
            with patch.object(write_pacing.time, "sleep"):
                self.assertEqual(official_sources.publish_rows(db, rows, did, "dane-weekly-pdf"), expected)
                self.assertEqual(official_sources.publish_rows(db, rows, did, "dane-weekly-pdf"), expected)
            self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0], expected)
            self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE product_id='papa-r-12-negra'").fetchone()[0], 5)
            self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE product_id=''").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM published_official_price").fetchone()[0], expected)
            self.assertEqual(db.execute("SELECT content FROM source_document WHERE id=%s", (did,)).fetchone()[0], body)

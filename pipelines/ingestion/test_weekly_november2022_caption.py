"""Exact-original weekly date correction requires independent annex parity."""
import collections
import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from . import dane_weekly as weekly

FIXTURES = Path(__file__).with_name("testdata")
PDF = FIXTURES / "dane_weekly_2022_11_18_original.pdf"
ANNEX = FIXTURES / "dane_weekly_2022_11_18_annex.xlsx"
ANNEX_URL = weekly.NOVEMBER_2022_BULLETIN_URL.replace("bol_", "anex_").replace(".pdf", ".xlsx")


class NovemberCaption(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = PDF.read_bytes()
        cls.annex = ANNEX.read_bytes()
        if hashlib.sha256(cls.body).hexdigest() != weekly.NOVEMBER_2022_BULLETIN_SHA:
            raise AssertionError("PDF original changed")
        if hashlib.sha256(cls.annex).hexdigest() != weekly.NOVEMBER_2022_MATCHING_ANNEX_SHA:
            raise AssertionError("Independent annex original changed")
        cls.rows = weekly.parse_pdf(cls.body, weekly.NOVEMBER_2022_BULLETIN_URL)

    def test_all_eligible_monetary_tuples_match_independent_annex(self):
        annex_rows = weekly.parse_workbook(self.annex, ANNEX_URL)
        fields = ("product_id", "market", "unit", "price", "min", "max")
        tuples = lambda rows: collections.Counter(
            tuple(row[field] for field in fields) for row in rows if row["price"] is not None
        )
        expected, actual = tuples(annex_rows), tuples(self.rows)
        self.assertEqual(len(self.rows), 4385)
        self.assertEqual(sum(actual.values()), 4254)
        self.assertFalse(actual - expected)
        self.assertEqual({r["date"] for r in self.rows}, {"2022-11-18"})
        self.assertEqual({r["period_start"] for r in self.rows}, {"2022-11-12"})
        priced = next(r for r in self.rows if r["market"] == "Bogotá, D.C., Corabastos" and r["product_id"] == "acelga")
        self.assertEqual((priced["min"], priced["max"], priced["price"]), (533, 933, 661))
        for row in self.rows:
            self.assertEqual(row["details"]["literal_printed_period_start"], "2022-10-22")
            self.assertEqual(row["details"]["corroborating_annex_sha256"], weekly.NOVEMBER_2022_MATCHING_ANNEX_SHA)

    def test_undeclared_units_and_uncorroborated_row_remain_unpriced(self):
        reviews = [r for r in self.rows if r["price"] is None]
        self.assertEqual(len(reviews), 131)
        units = [r for r in reviews if r["unit"] == "unverified"]
        self.assertEqual(len(units), 130)
        orphan = next(r for r in reviews if r["details"].get("unverified_weekly_date"))
        self.assertEqual((orphan["product_id"], orphan["market"], orphan["details"]["literal_mean"]),
                         ("rabadillas-de-pollo", "Villavicencio, CAV", 9775))

    def test_changed_original_or_different_url_cannot_receive_date_exception(self):
        for body, url in ((self.body + b"changed", weekly.NOVEMBER_2022_BULLETIN_URL),
                          (self.body, weekly.NOVEMBER_2022_BULLETIN_URL.replace("12nov", "11nov"))):
            with self.subTest(url=url, bytes=len(body)):
                with self.assertRaises(ValueError):
                    weekly.parse_pdf(body, url)


@unittest.skipUnless(os.environ.get("AGRO_OFFICIAL_CATALOG_TEST") == "1", "Private PostgreSQL opt-in")
class NovemberPublication(unittest.TestCase):
    def test_repeated_publication_retains_all_original_review_and_valid_rows(self):
        from . import official_sources, worker, write_pacing
        from .test_official_catalog import install_cache

        rows = weekly.parse_pdf(PDF.read_bytes(), weekly.NOVEMBER_2022_BULLETIN_URL)
        did = weekly.NOVEMBER_2022_BULLETIN_SHA
        with worker.connect() as db:
            db.execute("SET search_path=pg_temp; SET statement_timeout='20s'")
            for table in ("source_document", "official_price_quote", "official_source_review",
                          "ingestion_asset", "ingestion_checkpoint"):
                db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")
                self.assertEqual(db.execute("SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)", (table,)).fetchone(), ("t",))
            install_cache(db)
            db.execute("INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content) "
                       "VALUES(%s,'DANE November original','DANE',%s,'application/pdf','original','2022-11-18',%s)",
                       (did, weekly.NOVEMBER_2022_BULLETIN_URL, PDF.read_bytes()))
            db.execute("INSERT INTO ingestion_asset(url,kind,document_id,status) VALUES(%s,'dane-weekly-pdf',%s,'complete')",
                       (weekly.NOVEMBER_2022_BULLETIN_URL, did))
            with patch.object(write_pacing.time, "sleep"):
                self.assertEqual(official_sources.publish_rows(db, rows, did, "dane-weekly-pdf"), 4254)
                self.assertEqual(official_sources.publish_rows(db, rows, did, "dane-weekly-pdf"), 4254)
            self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote").fetchone()[0], 4254)
            self.assertEqual(db.execute("SELECT count(*) FROM official_source_review").fetchone()[0], 131)
            self.assertEqual(bytes(db.execute("SELECT content FROM source_document WHERE id=%s", (did,)).fetchone()[0]), PDF.read_bytes())


if __name__ == "__main__":
    unittest.main()

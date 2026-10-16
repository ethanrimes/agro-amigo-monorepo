"""Exact DANE original: Meta rows copied into the Nariño milk PDF section."""

import hashlib
import json
import os
import unittest
from datetime import date
from pathlib import Path

from . import special_prices, test_special_projection as projection_tests, worker


ROOT = Path(__file__).parent / "testdata"
PDF = ROOT / "milk_nov2024_meta_narino_duplicate_original.pdf"
ORACLE = ROOT / "milk_nov2024_page7_visual_oracle.json"
DAY = date(2024, 11, 30)
URL = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSALeche-nov2024.pdf"


def evidence():
    body = PDF.read_bytes()
    oracle = json.loads(ORACLE.read_text())
    if hashlib.sha256(body).hexdigest() != oracle["pdf_sha256"]:
        raise AssertionError("Exact milk original SHA changed")
    return body, oracle


class MilkNov2024SourceTests(unittest.TestCase):
    def test_independent_visual_rows_match_both_literal_pdf_sections(self):
        body, oracle = evidence()
        rows = list(special_prices.parse_milk_pdf(body, DAY))
        by_locator = {row[0]: row for row in rows}
        self.assertEqual(len(rows), 208)
        self.assertEqual(oracle["unit_heading"], "Pesos por litro")
        for expected in oracle["rows"]:
            for line, department in ((expected["meta_line"], "Meta"),
                                     (expected["narino_line"], "Nariño")):
                locator = f"PDF page 7,col 1,line {line}; parser {special_prices.MILK_PDF_VERSION}"
                row = by_locator[locator]
                self.assertEqual((row[4], row[5], row[6], row[-1]["department"],
                                  row[-1]["min_price"], row[-1]["max_price"]),
                                 (expected["municipality"], "litre", expected["mean"],
                                  department, expected["min"], expected["max"]))
        self.assertEqual(special_prices.NOV2024_DUPLICATE_MILK_SHA, oracle["pdf_sha256"])
        self.assertEqual(special_prices.NOV2024_DUPLICATE_MILK_XLSX_SHA, oracle["xlsx_sha256"])
        row = by_locator[f"PDF page 7,col 1,line 28; parser {special_prices.MILK_PDF_VERSION}"]
        self.assertIsNone(special_prices._nov2024_duplicate_narino(
            "0" * 64, row[0], DAY, row[4], row[6], row[-1]))
        self.assertIsNone(special_prices._nov2024_duplicate_narino(
            oracle["pdf_sha256"], row[0], DAY, row[4], row[6],
            {**row[-1], "department": "Meta"}))


@unittest.skipUnless(os.environ.get("AGRO_MILK_DUPLICATE_POSTGRES_TEST") == "1",
                     "Explicit isolated PostgreSQL TEMP-table opt-in")
class MilkNov2024PublicationTests(unittest.TestCase):
    def setUp(self):
        projection_tests.SpecialProjectionPostgresTests.setUp(self)
        self.db.execute("CREATE TEMP TABLE price_observation_review "
                        "(LIKE public.price_observation_review INCLUDING ALL)")
        self.db.execute("CREATE TEMP TABLE official_source_review "
                        "(LIKE public.official_source_review INCLUDING ALL)")
        self.db.execute("""CREATE TEMP VIEW published_price_observation AS
          SELECT p.* FROM price_observation p WHERE NOT EXISTS(
            SELECT 1 FROM price_observation_review r WHERE
             (r.document_id,r.source_locator,r.product_id,r.market_id,r.source_id,
              r.observed_on,r.period,r.unit)=
             (p.document_id,p.source_locator,p.product_id,p.market_id,p.source_id,
              p.observed_on,p.period,p.unit))""")

    def test_legacy_projection_is_reviewed_while_original_and_meta_prices_survive(self):
        body, oracle = evidence()
        did = oracle["pdf_sha256"]
        self.db.execute(
            """INSERT INTO source_document
               (id,title,publisher,source_url,media_type,kind,reference_period,content)
               VALUES(%s,'November 2024 milk','DANE',%s,'application/pdf','original','2024-11',%s)""",
            (did, URL, body),
        )
        self.db.execute("INSERT INTO ingestion_asset(url,kind,document_id,observed_on,status) "
                        "VALUES(%s,'milk-pdf',%s,%s,'complete')", (URL, did, DAY))
        current = list(special_prices.parse_milk_pdf(body, DAY))
        legacy = [(row[0].replace(special_prices.MILK_PDF_VERSION, "milk-pdf-v10"), *row[1:]) for row in current]
        with self.db.transaction():
            worker.save_rows(self.db, did, legacy)
        with self.db.transaction():
            worker.save_rows(self.db, did, current)
        self.assertEqual(self.db.execute("SELECT count(*) FROM historical_price").fetchone(), (416,))
        pid = worker.slug("Leche cruda en finca")
        self.db.execute("INSERT INTO product(id,name,category) VALUES(%s,'Leche cruda en finca','Leche cruda en finca')", (pid,))
        for expected in oracle["rows"]:
            town = expected["municipality"]
            mid = "finca-narino-" + worker.slug(town)
            locator = f"PDF page 7,col 1,line {expected['narino_line']}; parser milk-pdf-v10; precio en finca, COP/litro"
            self.db.execute("INSERT INTO market(id,name,city,region) VALUES(%s,%s,%s,'Nariño')",
                            (mid, town + " · leche en finca", town))
            self.db.execute(
                """INSERT INTO price_observation(product_id,market_id,source_id,observed_on,
                   period,unit,price,min_price,max_price,source_url,document_id,source_locator)
                   VALUES(%s,%s,'dane-milk-farm',%s,'monthly','litre',%s,%s,%s,%s,%s,%s)""",
                (pid, mid, DAY, expected["mean"], expected["min"], expected["max"],
                 URL, did, locator),
            )
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_price_observation").fetchone(), (8,))
        for _ in range(2):
            self.assertEqual(special_prices.project_special(self.db, did, URL), 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM price_observation_review").fetchone(), (8,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review").fetchone(), (8,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM price_observation WHERE market_id LIKE 'finca-narino-%%'").fetchone()[0] >= 8, True)
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_price_observation WHERE market_id IN "
                                         "(SELECT market_id FROM price_observation_review)").fetchone(), (0,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_price_observation WHERE market_id='finca-meta-acacias'").fetchone(), (1,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_price_observation WHERE market_id='finca-narino-puerres'").fetchone(), (1,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM historical_price").fetchone(), (416,))
        review = self.db.execute("SELECT evidence FROM price_observation_review WHERE market_id='finca-narino-acacias'").fetchone()[0]
        self.assertEqual(review["duplicate_of"], "PDF page 7,col 1,line 19")
        self.assertEqual(review["paired_workbook_sha256"], oracle["xlsx_sha256"])


if __name__ == "__main__":
    unittest.main()

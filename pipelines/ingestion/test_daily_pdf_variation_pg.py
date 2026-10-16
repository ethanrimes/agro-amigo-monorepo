"""Native June 2012 daily Var% and atomic append-only publication regressions."""

import getpass
import hashlib
import io
import random
import re
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pdfplumber
import psycopg
from psycopg.types.json import Jsonb

from .pdf_sources import VerifiedPDFPage
from .queue_plan import expected_versions
from .worker import (
    parse_pdf_pages, parser_version, project, retire_daily_pdf_old_cells, save_rows,
)

DID = "da15a9fe32bec70592853c7c50d24a7500d68c743021d1e206a2f9c3854d21f2"
ORIGINAL = Path(__file__).parent / "testdata/daily_pdf_variation" / (DID + ".pdf")
DAY = date(2012, 6, 27)


def native_rows():
    body = ORIGINAL.read_bytes()
    assert hashlib.sha256(body).hexdigest() == DID
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        return list(parse_pdf_pages(pdf.pages, DAY, False))


class DailyPDFVariationNative(unittest.TestCase):
    def test_all_120_native_prices_and_adjacent_variations(self):
        rows = native_rows()
        self.assertEqual(len(rows), 120)
        self.assertEqual(parser_version("daily-pdf"), "daily-pdf-v6:supply-daily-pdf-summary-v1:unbound-prose-review-v1")
        self.assertEqual(expected_versions().obj["daily-pdf"], parser_version("daily-pdf"))
        expected = {}
        with pdfplumber.open(ORIGINAL) as pdf:
            self.assertEqual(len(pdf.pages), 2)
            self.assertIn(
                "Variación porcentual con respecto al promedio del día de mercado anterior",
                pdf.pages[1].extract_text(),
            )
            for page_no, page in enumerate(pdf.pages, 1):
                cells = page.extract_tables()[0]
                self.assertIn("27 de Junio de 2012", cells[1][0])
                self.assertEqual(cells[2][0], "Precio $/Kg")
                for row_no, row in enumerate(cells[4:], 5):
                    name = " ".join(str(row[0] or "").split())
                    for col in range(1, 15, 2):
                        token = str(row[col] or "")
                        if re.fullmatch(r"\d+(?:\.\d{3})*", token):
                            market = cells[2][col]
                            assert market and cells[3][col:col + 2] == ["Precio", "Var%"]
                            expected[(page_no, row_no, col + 1, name, market)] = (
                                float(token.replace(".", "")),
                                " ".join(str(row[col + 1] or "").split()),
                            )
        actual = {}
        for row in rows:
            m = re.search(r"page (\d+),table 1,row (\d+),col (\d+)", row[0])
            self.assertIsNotNone(m)
            key = (*(int(x) for x in m.groups()), row[3], row[4])
            actual[key] = (row[6], row[-1]["change_percent_literal"])
            self.assertEqual(row[-1]["variation_basis"], "printed-daily-var-percent")
            self.assertEqual(row[-1]["parser_version"], "daily-pdf-v6")
            self.assertTrue(row[0].endswith("; daily-pdf-v6"))
        self.assertEqual(len(expected), 120)
        self.assertEqual(actual, expected)
        by_key = {(r[3], r[4]): r for r in rows}
        for key, value in {
            ("Ahuyama", "Bogotá"): (775, -1),
            ("Pimentón", "Medellín"): (1488, 9),
        }.items():
            row = by_key[key]
            self.assertEqual((row[5], row[6], row[7]), ("kg", *value))

    def test_missing_unrecognized_or_unheaded_percent_stays_null(self):
        table = [
            ["Precio $/Kg. 27 de Junio de 2012", None, None, None, None, None, None],
            ["Producto", "Bogotá", None, "Medellín", None, "Cali", None],
            [None, "Precio", "Var%", "Precio", "Var%", "Precio", "Var%"],
            ["Ahuyama", "900", "-", "525", "n.d.", "587", "~2 %"],
        ]
        page = VerifiedPDFPage({"text": "", "tables": [table]})
        rows = list(parse_pdf_pages([page], DAY, False))
        self.assertEqual([r[6] for r in rows], [900, 525, 587])
        self.assertEqual([r[7] for r in rows], [None, None, None])
        self.assertEqual(rows[2][-1]["change_percent_review"], "Unrecognized printed daily Var% cell")
        table[3][2] = ""
        table[2][2] = "Precio"
        rows = list(parse_pdf_pages([VerifiedPDFPage({"text": "", "tables": [table]})], DAY, False))
        self.assertIsNone(rows[0][7])
        self.assertNotIn("change_percent_literal", rows[0][-1])


class DailyPDFVariationPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-daily-variation-pg-", dir="/tmp"))
        cls.cluster = cls.directory / "data"
        cls.port = random.randrange(41000, 49000)
        try:
            subprocess.run(["initdb", "-D", str(cls.cluster), "--auth=trust", "--no-locale",
                            "--encoding=UTF8"], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["pg_ctl", "-D", str(cls.cluster), "-l", str(cls.directory / "postgres.log"),
                            "-o", f'-k {cls.directory} -p {cls.port} -h ""', "-w", "start"],
                           check=True, stdout=subprocess.DEVNULL)
            cls.db = psycopg.connect(
                f"host={cls.directory} port={cls.port} dbname=postgres user={getpass.getuser()}",
                autocommit=True,
            )
            assert str(cls.db.info.host).startswith("/tmp/agro-daily-variation-pg-")
            cls.db.execute("SET search_path=pg_temp")
            cls.db.execute("""CREATE TEMP TABLE historical_price(
                document_id text,source_locator text,series text,observed_on date,
                product_name text,market_name text,unit text,price numeric,
                change_percent numeric,details jsonb,
                PRIMARY KEY(document_id,source_locator))""")
            cls.db.execute("""CREATE TEMP TABLE historical_price_review(
                document_id text,source_locator text,validator_version text,
                reason text,PRIMARY KEY(document_id,source_locator,validator_version))""")
            cls.db.execute("""CREATE TEMP TABLE source_document(
                id text PRIMARY KEY,kind text,metadata jsonb,retrieved_at timestamptz)""")
            cls.db.execute("""CREATE TEMP TABLE product(id text PRIMARY KEY,name text,category text)""")
            cls.db.execute("""CREATE TEMP TABLE daily_price(
                observed_on date,product_name text,market_name text,product_id text,
                price numeric,change_percent numeric,document_id text,source_page integer,
                source_locator text,unit text,
                PRIMARY KEY(observed_on,product_name,market_name))""")
            cls.db.execute("INSERT INTO source_document VALUES(%s,'original',%s,now())",
                           (DID, Jsonb({"ingestion_kind": "daily-pdf"})))
            cls.db.execute("INSERT INTO source_document VALUES('xls-winner','original',%s,now())",
                           (Jsonb({"ingestion_kind": "daily"}),))
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "db", None) is not None:
            cls.db.close()
        if getattr(cls, "cluster", None) is not None and cls.cluster.exists():
            subprocess.run(["pg_ctl", "-D", str(cls.cluster), "-m", "fast", "-w", "stop"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if getattr(cls, "directory", None) is not None:
            shutil.rmtree(cls.directory, ignore_errors=True)

    def setUp(self):
        self.db.execute("BEGIN")
        rows = native_rows()
        self.selected = [r for r in rows if (r[3], r[4]) in {
            ("Ahuyama", "Bogotá"), ("Pimentón", "Medellín")
        }]
        assert len(self.selected) == 2
        for row in self.selected:
            base = row[0].split("; ")[0]
            for suffix in ("", "; daily-pdf-v4", "; daily-pdf-v5"):
                self.db.execute("""INSERT INTO historical_price VALUES
                  (%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s)""",
                  (DID, base + suffix, row[1], row[2], row[3], row[4], row[5],
                   row[6], Jsonb({"parser_version": suffix.lstrip("; ") or "legacy"})))
            self.db.execute("""INSERT INTO daily_price VALUES
              (%s,%s,%s,NULL,%s,NULL,%s,1,%s,%s)""",
              (row[2], row[3], row[4], row[6], DID, base + "; daily-pdf-v5", row[5]))

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def publish(self, selected=None):
        rows = selected if selected is not None else self.selected
        with self.db.transaction():
            save_rows(self.db, DID, rows)
            retire_daily_pdf_old_cells(self.db, DID)
            project(self.db, DID, "https://www.dane.gov.co/official.pdf", "daily-pdf",
                    source_rows=rows)

    def test_exact_old_rows_retained_and_new_change_selected_idempotently(self):
        self.publish()
        # The outer rollback fixture retains ON COMMIT DROP staging tables;
        # clear them here to model the next real top-level publication transaction.
        self.db.execute("DROP TABLE pg_temp.ingestion_stage")
        self.db.execute("DROP TABLE pg_temp.ingestion_daily_projection_stage")
        self.publish()
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price WHERE document_id=%s", (DID,)
        ).fetchone()[0], 8)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price_review WHERE document_id=%s", (DID,)
        ).fetchone()[0], 6)
        published = self.db.execute("""SELECT h.product_name,h.market_name,h.price,
          h.change_percent,h.source_locator FROM historical_price h
          WHERE h.document_id=%s AND NOT EXISTS(SELECT 1 FROM historical_price_review r
            WHERE r.document_id=h.document_id AND r.source_locator=h.source_locator)
          ORDER BY h.product_name""", (DID,)).fetchall()
        self.assertEqual([(name,market,float(price),float(change),loc.endswith("; daily-pdf-v6"))
                          for name,market,price,change,loc in published],
                         [("Ahuyama","Bogotá",775,-1,True),
                          ("Pimentón","Medellín",1488,9,True)])
        selected = self.db.execute("""SELECT product_name,market_name,price,change_percent,
          document_id,source_locator FROM daily_price ORDER BY product_name""").fetchall()
        self.assertEqual([(name,market,float(price),float(change),did,loc.endswith("; daily-pdf-v6"))
                          for name,market,price,change,did,loc in selected],
                         [("Ahuyama","Bogotá",775,-1,DID,True),
                          ("Pimentón","Medellín",1488,9,DID,True)])

    def test_changed_price_rolls_back_new_parse_reviews_and_projection(self):
        changed = list(self.selected)
        row = list(changed[0]);row[6] += 1;changed[0] = tuple(row)
        with self.assertRaisesRegex(ValueError, "unmatched or changed old price cell"):
            self.publish(changed)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price WHERE document_id=%s", (DID,)
        ).fetchone()[0], 6)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price_review WHERE document_id=%s", (DID,)
        ).fetchone()[0], 0)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM daily_price WHERE change_percent IS NOT NULL"
        ).fetchone()[0], 0)

    def test_complete_original_retains_all_old_cells_and_one_v6_cell_each(self):
        rows = native_rows()
        existing = {(r[3], r[4]) for r in self.selected}
        for row in rows:
            if (row[3], row[4]) in existing:
                continue
            base = row[0].split("; ")[0]
            for suffix in ("", "; daily-pdf-v4", "; daily-pdf-v5"):
                self.db.execute("""INSERT INTO historical_price VALUES
                  (%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s)""",
                  (DID, base + suffix, row[1], row[2], row[3], row[4], row[5],
                   row[6], Jsonb({"parser_version": suffix.lstrip("; ") or "legacy"})))
            self.db.execute("""INSERT INTO daily_price VALUES
              (%s,%s,%s,NULL,%s,NULL,%s,1,%s,%s)""",
              (row[2], row[3], row[4], row[6], DID, base + "; daily-pdf-v5", row[5]))
        self.publish(rows)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price WHERE document_id=%s", (DID,)
        ).fetchone()[0], 480)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price_review WHERE document_id=%s", (DID,)
        ).fetchone()[0], 360)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM daily_price WHERE document_id=%s", (DID,)
        ).fetchone()[0], 120)
        self.assertEqual(self.db.execute("""SELECT count(*) FROM daily_price
          WHERE source_locator NOT LIKE '%%; daily-pdf-v6'""").fetchone()[0], 0)

    def test_daily_xls_winner_has_higher_source_precedence(self):
        self.db.execute("""UPDATE daily_price SET price=900,document_id='xls-winner',
          change_percent=12,source_locator='Sheet1!row 7' WHERE product_name='Ahuyama'""")
        self.publish()
        row = self.db.execute("""SELECT price,change_percent,document_id,source_locator
          FROM daily_price WHERE product_name='Ahuyama'""").fetchone()
        self.assertEqual(row, (900, 12, "xls-winner", "Sheet1!row 7"))
        other = self.db.execute("""SELECT change_percent,source_locator FROM daily_price
          WHERE product_name='Pimentón'""").fetchone()
        self.assertEqual(float(other[0]), 9)
        self.assertTrue(other[1].endswith("; daily-pdf-v6"))


if __name__ == "__main__":
    unittest.main()

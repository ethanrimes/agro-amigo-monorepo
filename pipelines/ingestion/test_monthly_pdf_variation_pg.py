"""Exact v4-to-v5 monthly PDF publication is atomic and append-only."""

import getpass
import random
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from .worker import parser_version, retire_monthly_pdf_v4_cells
from .queue_plan import expected_versions, repair_candidates


class MonthlyPDFVariationPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-monthly-variation-pg-", dir="/tmp"))
        cls.cluster = cls.directory / "data"
        cls.port = random.randrange(41000, 49000)
        try:
            subprocess.run(["initdb", "-D", str(cls.cluster), "--auth=trust", "--no-locale",
                            "--encoding=UTF8"],
                           check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["pg_ctl", "-D", str(cls.cluster),
                            "-l", str(cls.directory / "postgres.log"),
                            "-o", f'-k {cls.directory} -p {cls.port} -h ""',
                            "-w", "start"], check=True, stdout=subprocess.DEVNULL)
            cls.db = psycopg.connect(
                f"host={cls.directory} port={cls.port} dbname=postgres user={getpass.getuser()}",
                autocommit=True,
            )
            assert str(cls.db.info.host).startswith("/tmp/agro-monthly-variation-pg-")
            cls.db.execute("SET search_path=pg_temp")
            cls.db.execute("""CREATE TEMP TABLE ingestion_checkpoint(
                document_id text,processor_version text,step text,records integer DEFAULT 0,
                created_at timestamptz DEFAULT now(),PRIMARY KEY(document_id,processor_version,step))""")
            cls.db.execute("""CREATE TEMP TABLE historical_price(
                document_id text,source_locator text,series text,observed_on date,
                product_name text,market_name text,unit text,price numeric,
                change_percent numeric,details jsonb,
                PRIMARY KEY(document_id,source_locator))""")
            cls.db.execute("""CREATE TEMP TABLE historical_price_review(
                document_id text,source_locator text,validator_version text,
                reason text,PRIMARY KEY(document_id,source_locator,validator_version))""")
            cls.db.execute("""CREATE TEMP TABLE source_document(
                id text PRIMARY KEY,kind text,source_url text,
                media_type text,metadata jsonb,title text,publisher text,
                reference_period text,page_count integer,content bytea)""")
            cls.db.execute("""CREATE TEMP TABLE ingestion_asset(
                url text,kind text,status text,processor_version text,
                document_id text,observed_on date,checked_at timestamptz,
                error text,records integer NOT NULL DEFAULT 0)""")
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

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def add_row(self, version, price=468, change=None, *, col=3, market="Barranquilla"):
        self.db.execute("""INSERT INTO historical_price VALUES
          ('feb2015',%s,'dane-monthly-summary','2015-02-28','Ahuyama',
           %s,'kg',%s,%s,%s)""",
          (f"PDF page 23,table 1,row 4,col {col}; monthly-pdf-{version}",
           market, price, change, Jsonb({"parser_version": f"monthly-pdf-{version}"})))

    def test_exact_replay_retains_raw_v4_and_selects_v5_once(self):
        self.add_row("v4")
        self.add_row("v5", change=6.61)
        self.add_row("v4", price=816, col=5, market="Bogotá")
        self.add_row("v5", price=816, change=-6.96, col=5, market="Bogotá")
        retire_monthly_pdf_v4_cells(self.db, "feb2015")
        retire_monthly_pdf_v4_cells(self.db, "feb2015")
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price WHERE document_id='feb2015'"
        ).fetchone()[0], 4)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM historical_price_review WHERE document_id='feb2015'"
        ).fetchone()[0], 2)
        visible = self.db.execute("""SELECT h.market_name,h.price,h.change_percent
            FROM historical_price h WHERE NOT EXISTS(
              SELECT 1 FROM historical_price_review r WHERE
              r.document_id=h.document_id AND r.source_locator=h.source_locator)
            ORDER BY h.market_name""").fetchall()
        self.assertEqual([(m, float(p), float(v)) for m,p,v in visible],
                         [("Barranquilla", 468, 6.61), ("Bogotá", 816, -6.96)])

    def test_missing_or_changed_v5_cell_cannot_hide_old_publication(self):
        self.add_row("v4")
        with self.assertRaisesRegex(ValueError, "unmatched or changed"):
            retire_monthly_pdf_v4_cells(self.db, "feb2015")
        self.assertEqual(self.db.execute("SELECT count(*) FROM historical_price_review").fetchone()[0], 0)
        self.add_row("v5", price=469, change=6.61)
        with self.assertRaisesRegex(ValueError, "unmatched or changed"):
            retire_monthly_pdf_v4_cells(self.db, "feb2015")
        self.assertEqual(self.db.execute("SELECT count(*) FROM historical_price_review").fetchone()[0], 0)

    def test_v4_completed_original_enters_bounded_repair_lane_only_after_cooldown(self):
        self.assertEqual(parser_version("monthly-pdf"), "monthly-pdf-v5")
        self.assertEqual(expected_versions().obj["monthly-pdf"], "monthly-pdf-v5")
        self.db.execute("""INSERT INTO source_document(id,kind,metadata)
                        VALUES('feb2015','original',%s)""",
                        (Jsonb({"ingestion_kind": "monthly-pdf"}),))
        self.db.execute("""INSERT INTO ingestion_asset
          (url,kind,status,processor_version,document_id,observed_on,checked_at) VALUES
          ('https://example.test/feb2015.pdf','monthly-pdf','complete',
           'monthly-pdf-v4','feb2015','2015-02-28',now()-interval '7 hours')""")
        self.assertIn("https://example.test/feb2015.pdf",
                      [row[0] for row in repair_candidates(self.db)])
        self.db.execute("UPDATE ingestion_asset SET processor_version='monthly-pdf-v5'")
        self.assertNotIn("https://example.test/feb2015.pdf",
                         [row[0] for row in repair_candidates(self.db)])
        self.db.execute("UPDATE ingestion_asset SET processor_version='monthly-pdf-v4',checked_at=now()")
        self.assertNotIn("https://example.test/feb2015.pdf",
                         [row[0] for row in repair_candidates(self.db)])


if __name__ == "__main__":
    unittest.main()

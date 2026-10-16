"""Exact Mar 2024 continuation correction against isolated PostgreSQL TEMP state."""

import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import dane_weekly, official_sources, queue_plan, worker
from .retained_pdf_upgrade import retained_pdf_upgrade


URL = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSASemanal-23mar-27mar-2024.pdf"
SHA = "218d83958d650f3b3035e008a35828aff6a6b2a0098d8ba84adc07596a26ca7e"
OLD = "official-v2:dane-weekly-v20"
KIND = "dane-weekly-pdf"
FILE = Path(__file__).parent / "testdata/dane_weekly_2024_03_23_original.pdf"


class Weekly2024ContinuationRepairPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ.get("AGRO_REFERENCE_TEST_DSN")
        if not dsn and os.environ.get("AGRO_REFERENCE_TEST_SOCKET"):
            dsn = f"host={os.environ['AGRO_REFERENCE_TEST_SOCKET']} port=65443 dbname=postgres"
        dsn = dsn or os.environ.get("DATABASE_URL")
        if not dsn:
            raise RuntimeError("Private PostgreSQL socket required")
        cls.db = psycopg.connect(dsn, autocommit=True)
        if not str(cls.db.info.host).startswith("/tmp/agro-"):
            cls.db.close()
            raise RuntimeError("Only isolated private PostgreSQL is allowed")
        cls.db.execute("SET search_path=pg_temp; SET statement_timeout='30s'")
        cls.db.execute("CREATE TEMP TABLE source_document (LIKE public.source_document INCLUDING ALL)")
        cls.db.execute("CREATE TEMP TABLE ingestion_asset (LIKE public.ingestion_asset INCLUDING ALL)")
        cls.db.execute("CREATE TEMP TABLE official_price_quote (LIKE public.official_price_quote INCLUDING ALL)")
        cls.db.execute("CREATE TEMP TABLE official_source_review (LIKE public.official_source_review INCLUDING ALL)")
        cls.db.execute("CREATE TEMP TABLE ingestion_checkpoint (LIKE public.ingestion_checkpoint INCLUDING ALL)")
        cls.db.execute("CREATE TEMP TABLE historical_price (LIKE public.historical_price INCLUDING ALL)")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.db.execute("BEGIN")
        self.body = FILE.read_bytes()
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), SHA)
        self.db.execute("""INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
          VALUES(%s,'DANE weekly','DANE',%s,'application/pdf','original',
                 '2024-03-27',%s,%s)""",
                        (SHA, URL, self.body, Jsonb({"ingestion_kind": KIND})))
        self.db.execute("""INSERT INTO ingestion_asset
          (url,kind,status,processor_version,document_id,observed_on,checked_at,records)
          VALUES(%s,%s,'complete',%s,%s,'2024-03-27',now(),4133)""",
                        (URL, KIND, OLD, SHA))

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def test_exact_local_repair_and_queue_guards(self):
        expected = worker.asset_parser_version(KIND, URL)
        self.assertEqual(expected, worker.parser_version(KIND) + ':mar2024-continuation-v1')
        self.assertEqual(retained_pdf_upgrade(self.db, URL, KIND, expected), self.body)
        self.assertTrue(worker.retained_reparse_during_host_cooldown(self.db, URL, KIND))
        self.assertEqual([row[0] for row in queue_plan.repair_candidates(self.db, 8)], [URL])
        for column, changed in (("processor_version", expected), ("status", "pending"),
                                ("document_id", "0" * 64), ("kind", "daily-pdf")):
            original = self.db.execute(f"SELECT {column} FROM ingestion_asset WHERE url=%s", (URL,)).fetchone()[0]
            self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s", (changed, URL))
            self.assertNotIn(URL, [r[0] for r in queue_plan.repair_candidates(self.db, 8)])
            self.assertIsNone(retained_pdf_upgrade(self.db, URL, KIND, expected))
            self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s", (original, URL))
        for column, changed in (("source_url", URL + ".other"),
                                ("media_type", "application/octet-stream")):
            original = self.db.execute(f"SELECT {column} FROM source_document WHERE id=%s", (SHA,)).fetchone()[0]
            self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s", (changed, SHA))
            self.assertIsNone(retained_pdf_upgrade(self.db, URL, KIND, expected))
            self.assertNotIn(URL, [r[0] for r in queue_plan.repair_candidates(self.db, 8)])
            self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s", (original, SHA))
        self.assertIsNone(retained_pdf_upgrade(self.db, URL + ".other", KIND, expected))
        self.assertIsNone(retained_pdf_upgrade(self.db, URL, "monthly-pdf", expected))
        with self.assertRaisesRegex(ValueError, "invalid original SHA"):
            self.db.execute("UPDATE source_document SET content=%s WHERE id=%s", (self.body + b"changed", SHA))
            retained_pdf_upgrade(self.db, URL, KIND, expected)

    def test_old_literal_eight_quotes_remain_raw_but_new_same_locators_win(self):
        rows = dane_weekly.parse_pdf(self.body, URL)
        changed = [r for r in rows if r["details"].get("literal_product_heading") ==
                   "Limón Tahití (contiunuación)"]
        self.assertEqual((len(rows), len(changed)), (4133, 8))
        old_rows = []
        for row in changed:
            prior = {**row, "product_name": "Limón Tahití (contiunuación)",
                     "product_id": "limon-tahiti-contiunuacion",
                     "identity_dimensions": {**row.get("identity_dimensions", {}),
                                             "literal_product_heading": "Limón Tahití (contiunuación)"}}
            old_rows.append(prior)
        with (patch.object(worker, "parser_version", return_value=OLD),
              patch("pipelines.ingestion.official_catalog.mark_document_dirty"),
              patch("pipelines.ingestion.official_catalog.refresh_document"),
              patch("pipelines.ingestion.write_pacing.pause_between_batches")):
            self.assertEqual(official_sources.publish_rows(self.db, old_rows, SHA, KIND), 8)
        self.db.execute("UPDATE official_price_quote SET parsed_at=now()-interval '1 minute' WHERE document_id=%s", (SHA,))
        with (patch("pipelines.ingestion.official_catalog.mark_document_dirty"),
              patch("pipelines.ingestion.official_catalog.refresh_document"),
              patch("pipelines.ingestion.write_pacing.pause_between_batches")):
            self.assertEqual(official_sources.publish_rows(self.db, changed, SHA, KIND), 8)
            self.assertEqual(official_sources.publish_rows(self.db, changed, SHA, KIND), 8)
        retained = self.db.execute("""SELECT source_locator,parser_version,product_name,
          product_id,price,min_price,max_price,observed_on,unit,quote_key
          FROM official_price_quote WHERE document_id=%s ORDER BY source_locator,parsed_at""", (SHA,)).fetchall()
        self.assertEqual(len(retained), 16)
        locators = {r[0] for r in retained}
        self.assertEqual(len(locators), 8)
        for locator in locators:
            prior, current = [r for r in retained if r[0] == locator]
            self.assertEqual(prior[1:3], (OLD, "Limón Tahití (contiunuación)"))
            self.assertEqual(current[1:3], (worker.parser_version(KIND), "Limón Tahití"))
            self.assertEqual(prior[4:9], current[4:9])
            self.assertNotEqual(prior[9], current[9])
            winner = self.db.execute("""SELECT product_name FROM official_price_quote
              WHERE document_id=%s AND source_locator=%s
              ORDER BY parsed_at DESC LIMIT 1""", (SHA, locator)).fetchone()
            self.assertEqual(winner, ("Limón Tahití",))

    def test_unbound_old_daily_pdf_zero_grid_enters_normal_outdated_backfill(self):
        # The fallback is review-only for an unregistered prose layout. It
        # still needs a version transition so an old processed/zero asset is
        # eventually reconsidered by the ordinary historical lane.
        from .daily_prose import review_unbound_daily_prose

        other_url = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_abril_18_2013.pdf"
        body = (Path(__file__).parent / "testdata/daily_prose/mayoristas_abril_18_2013.pdf").read_bytes()
        did = hashlib.sha256(body).hexdigest()
        self.assertEqual(did, "31204423a30a31493d2fe4e0608752c5ea2f76913ed3f0f4e2ebe43cde6dfaac")
        self.db.execute("""INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
          VALUES(%s,'DANE daily','DANE',%s,'application/pdf','original','2013-04-18',%s,%s)""",
                        (did, other_url, body, Jsonb({"ingestion_kind": "daily-pdf"})))
        old = "daily-pdf-v6:supply-daily-pdf-summary-v1"
        self.db.execute("""INSERT INTO ingestion_asset
          (url,kind,status,processor_version,document_id,observed_on,checked_at,records)
          VALUES(%s,'daily-pdf','processed',%s,%s,'2013-04-18',now(),0)""",
                        (other_url, old, did))
        self.assertNotEqual(worker.parser_version("daily-pdf"), old)
        selected = [r[0] for r in queue_plan.backfill_candidates(self.db, 1000)]
        self.assertIn(other_url, selected)
        self.assertNotIn(other_url, [r[0] for r in queue_plan.repair_candidates(self.db, 8)])
        reviews = review_unbound_daily_prose(body, other_url, did, "2013-04-18")
        self.assertEqual(len(reviews), 31)
        self.assertFalse(any("price" in record for _, record, _ in reviews))

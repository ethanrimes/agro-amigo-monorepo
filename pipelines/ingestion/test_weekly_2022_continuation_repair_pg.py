"""July 2022 native heading repair preserves raw history and ordinary cooldowns."""

import csv
import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import dane_weekly, official_sources, queue_plan, worker
from .retained_pdf_upgrade import retained_pdf_upgrade


URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_02jul_al_08jul_2022.pdf"
SHA = "9f428bddcef7ede04ba7d91b7e39d2a89413a70f4b132d1f516f4577330c271c"
OLD = "official-v2:dane-weekly-v16"
KIND = "dane-weekly-pdf"
LITERAL = "Aguacate papelillo (comtinuación)"
DATA = Path(__file__).parent / "testdata"


class Weekly2022ContinuationRepairPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ.get("AGRO_REFERENCE_TEST_DSN") or os.environ.get("DATABASE_URL")
        if not dsn:
            raise RuntimeError("Private PostgreSQL DSN required")
        cls.db = psycopg.connect(dsn, autocommit=True)
        if not str(cls.db.info.host).startswith("/tmp/agro-"):
            cls.db.close()
            raise RuntimeError("Only isolated private PostgreSQL is allowed")
        cls.db.execute("SET search_path=pg_temp; SET statement_timeout='30s'")
        for name in ("source_document", "ingestion_asset", "official_price_quote",
                     "official_source_review", "ingestion_checkpoint", "historical_price"):
            cls.db.execute(f"CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING ALL)")
        cls.body = (DATA / "dane_weekly_2022_07_02_original.pdf").read_bytes()
        if hashlib.sha256(cls.body).hexdigest() != SHA:
            raise RuntimeError("Native original checksum mismatch")
        with (DATA / "weekly_20220708_manual_six_prices.psv").open() as handle:
            cls.oracle = list(csv.DictReader(handle, delimiter="|"))
        cls.rows = dane_weekly.parse_pdf(cls.body, URL)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.db.execute("BEGIN")
        self.db.execute("""INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
          VALUES(%s,'DANE weekly','DANE',%s,'application/pdf','original',
                 '2022-07-08',%s,%s)""", (SHA, URL, self.body, Jsonb({"ingestion_kind": KIND})))
        self.db.execute("""INSERT INTO ingestion_asset
          (url,kind,status,processor_version,document_id,observed_on,checked_at,records)
          VALUES(%s,%s,'complete',%s,%s,'2022-07-08',now()-interval '7 hours',4378)""",
                        (URL, KIND, OLD, SHA))

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def test_exact_retained_repair_validates_pointer_kind_media_and_bytes(self):
        expected = worker.asset_parser_version(KIND, URL)
        self.assertEqual(expected, worker.parser_version(KIND) + ':jul2022-continuation-v1')
        self.assertEqual(retained_pdf_upgrade(self.db, URL, KIND, expected), self.body)
        for column, changed in (("processor_version", expected), ("status", "pending"),
                                ("document_id", "0" * 64), ("kind", "daily-pdf")):
            prior = self.db.execute(f"SELECT {column} FROM ingestion_asset WHERE url=%s", (URL,)).fetchone()[0]
            self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s", (changed, URL))
            self.assertIsNone(retained_pdf_upgrade(self.db, URL, KIND, expected))
            self.db.execute(f"UPDATE ingestion_asset SET {column}=%s WHERE url=%s", (prior, URL))
        for column, changed in (("source_url", URL + ".other"),
                                ("media_type", "application/octet-stream")):
            prior = self.db.execute(f"SELECT {column} FROM source_document WHERE id=%s", (SHA,)).fetchone()[0]
            self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s", (changed, SHA))
            self.assertIsNone(retained_pdf_upgrade(self.db, URL, KIND, expected))
            self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s", (prior, SHA))
        self.assertIsNone(retained_pdf_upgrade(self.db, URL + ".other", KIND, expected))
        self.assertIsNone(retained_pdf_upgrade(self.db, URL, "monthly-pdf", expected))
        self.db.execute("UPDATE source_document SET content=%s WHERE id=%s", (self.body + b"changed", SHA))
        with self.assertRaisesRegex(ValueError, "invalid original SHA"):
            retained_pdf_upgrade(self.db, URL, KIND, expected)

    def test_exact_pin_advances_stale_original_without_bypassing_cooldown(self):
        self.assertEqual([r[0] for r in queue_plan.repair_candidates(self.db, 8)], [URL])
        self.db.execute("UPDATE ingestion_asset SET checked_at=now() WHERE url=%s", (URL,))
        self.assertNotIn(URL, [r[0] for r in queue_plan.repair_candidates(self.db, 8)])
        self.db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '7 hours' WHERE url=%s", (URL,))
        other_url = URL + ".unrelated.pdf"
        other_sha = "a" * 64
        self.db.execute("""INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
          VALUES(%s,'Other weekly','DANE',%s,'application/pdf','original','2022-07-08',%s,%s)""",
                        (other_sha, other_url, b"other original", Jsonb({"ingestion_kind": KIND})))
        self.db.execute("""INSERT INTO ingestion_asset
          (url,kind,status,processor_version,document_id,checked_at)
          VALUES(%s,%s,'complete',%s,%s,now()-interval '30 days')""",
                        (other_url, KIND, OLD, other_sha))
        self.assertEqual([r[0] for r in queue_plan.repair_candidates(self.db, 8)], [URL])
        # A different immutable revision is eligible through the ordinary lane,
        # but cannot inherit the audited original's priority or retained repair.
        self.db.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (other_sha, URL))
        self.assertEqual([r[0] for r in queue_plan.repair_candidates(self.db, 8)], [other_url])
        self.assertIsNone(retained_pdf_upgrade(self.db, URL, KIND, worker.asset_parser_version(KIND, URL)))

    def test_six_manual_prices_keep_old_raw_rows_and_append_idempotent_repair(self):
        changed = [r for r in self.rows if r['details'].get('literal_product_heading') == LITERAL]
        self.assertEqual((len(self.rows), len(changed), len(self.oracle)), (4378, 6, 6))
        for row, control in zip(changed, self.oracle):
            self.assertEqual(row['source_locator'], control['source_locator'])
            self.assertEqual(row['market'], control['market'])
            self.assertEqual((row['min'], row['max'], row['price']),
                             tuple(float(control[key]) for key in ('minimum', 'maximum', 'mean')))
        old_rows = [{**r, 'product_name': LITERAL,
                     'product_id': 'aguacate-papelillo-comtinuacion',
                     'details': {k: v for k, v in r['details'].items() if k != 'literal_product_heading'}}
                    for r in changed]
        with (patch.object(worker, 'parser_version', return_value=OLD),
              patch('pipelines.ingestion.official_catalog.mark_document_dirty'),
              patch('pipelines.ingestion.official_catalog.refresh_document'),
              patch('pipelines.ingestion.write_pacing.pause_between_batches')):
            self.assertEqual(official_sources.publish_rows(self.db, old_rows, SHA, KIND), 6)
        self.db.execute("UPDATE official_price_quote SET parsed_at=now()-interval '1 minute' WHERE document_id=%s", (SHA,))
        prior = self.db.execute("SELECT * FROM official_price_quote WHERE document_id=%s AND parser_version=%s ORDER BY source_locator", (SHA, OLD)).fetchall()
        with (patch('pipelines.ingestion.official_catalog.mark_document_dirty'),
              patch('pipelines.ingestion.official_catalog.refresh_document'),
              patch('pipelines.ingestion.write_pacing.pause_between_batches')):
            self.assertEqual(official_sources.publish_rows(self.db, changed, SHA, KIND), 6)
            self.assertEqual(official_sources.publish_rows(self.db, changed, SHA, KIND), 6)
        self.assertEqual(prior, self.db.execute("SELECT * FROM official_price_quote WHERE document_id=%s AND parser_version=%s ORDER BY source_locator", (SHA, OLD)).fetchall())
        retained = self.db.execute("""SELECT source_locator,parser_version,product_name,
          price,min_price,max_price,observed_on,unit,quote_key
          FROM official_price_quote WHERE document_id=%s ORDER BY source_locator,parsed_at""", (SHA,)).fetchall()
        self.assertEqual(len(retained), 12)
        for control in self.oracle:
            old, new = [r for r in retained if r[0] == control['source_locator']]
            self.assertEqual(old[1:3], (OLD, LITERAL))
            self.assertEqual(new[1:3], (worker.parser_version(KIND), 'Aguacate papelillo'))
            self.assertEqual(old[3:8], new[3:8])
            self.assertNotEqual(old[8], new[8])
        original = self.db.execute("SELECT content FROM source_document WHERE id=%s", (SHA,)).fetchone()[0]
        self.assertEqual(hashlib.sha256(original).hexdigest(), SHA)

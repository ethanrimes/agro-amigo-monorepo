"""Exact original quote review hides an invalid identity without erasing history."""
import os
from pathlib import Path
import unittest

import psycopg
from . import worker


@unittest.skipUnless(os.environ.get("AGRO_OBSERVATION_REVIEW_POSTGRES_TEST") == "1", "Explicit TEMP-only PostgreSQL opt-in")
class ObservationReviews(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp")
        self.db.execute("SET statement_timeout='10s'")
        self.db.execute("CREATE TEMP TABLE price_observation(document_id text,source_locator text,product_id text,market_id text,source_id text,observed_on date,period text,unit text,price numeric)")
        self.db.execute("CREATE TEMP TABLE ingestion_asset(document_id text,status text,observed_on date)")
        self.db.execute("CREATE TEMP TABLE price_observation_review(LIKE price_observation)")
        for name in ('price_observation','ingestion_asset','price_observation_review'):
            self.assertEqual(self.db.execute("SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)",(name,)).fetchone(),('t',))
        sql = (Path(__file__).parent / 'migrations/20260927_016_observation_reviews.sql').read_text()
        sql = sql[sql.index('CREATE OR REPLACE VIEW'):sql.index('GRANT SELECT ON published_price_observation')]
        self.db.execute(sql.replace('CREATE OR REPLACE VIEW','CREATE TEMP VIEW'))
        self.base = ['original','PDF page 6,col 2,line 32','leche','merged-name','dane-milk-farm','2024-11-30','monthly','litre',1680]
        self.db.execute('INSERT INTO price_observation VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',self.base)
        self.db.execute('INSERT INTO price_observation_review SELECT * FROM price_observation')

    def test_all_eight_identity_dimensions_are_exact_and_original_is_unchanged(self):
        alternatives = ['other-original','other-row','other-product','correct-market','other-source','2024-10-31','daily','kg']
        for index, value in enumerate(alternatives):
            row = self.base.copy(); row[index] = value
            self.db.execute('INSERT INTO price_observation VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',row)
        self.assertEqual(self.db.execute('SELECT count(*) FROM price_observation').fetchone(),(9,))
        self.assertEqual(self.db.execute('SELECT count(*) FROM published_price_observation').fetchone(),(8,))
        self.assertEqual(self.db.execute("SELECT price FROM price_observation WHERE market_id='merged-name' AND document_id='original' AND source_locator='PDF page 6,col 2,line 32' AND product_id='leche' AND source_id='dane-milk-farm' AND observed_on='2024-11-30' AND period='monthly' AND unit='litre'").fetchone()[0],1680)

    def test_corrected_identity_publishes_and_whole_source_review_still_applies(self):
        row=self.base.copy();row[3]='villapinzon'
        self.db.execute('INSERT INTO price_observation VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',row)
        self.assertEqual(self.db.execute('SELECT market_id FROM published_price_observation').fetchall(),[('villapinzon',)])
        self.db.execute("INSERT INTO ingestion_asset VALUES('original','review',NULL)")
        self.assertEqual(self.db.execute('SELECT count(*) FROM published_price_observation').fetchone(),(0,))
        self.assertEqual(self.db.execute('SELECT count(*) FROM price_observation').fetchone(),(2,))

    def test_review_decisions_cannot_be_changed_or_erased(self):
        self.db.execute('CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON price_observation_review FOR EACH STATEMENT EXECUTE FUNCTION public.prevent_history_removal()')
        self.db.execute('CREATE TRIGGER immutable_history BEFORE UPDATE ON price_observation_review FOR EACH STATEMENT EXECUTE FUNCTION public.prevent_history_removal()')
        for statement in ['DELETE FROM price_observation_review','TRUNCATE price_observation_review',"UPDATE price_observation_review SET market_id='replacement'"]:
            with self.assertRaises(psycopg.errors.RaiseException):
                with self.db.transaction(): self.db.execute(statement)
        self.assertEqual(self.db.execute('SELECT count(*) FROM price_observation_review').fetchone(),(1,))

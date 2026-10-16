"""Disposable PG role control for the exact 073 category-view read rights."""
import os
import unittest
from pathlib import Path

import psycopg

SQL075 = Path(__file__).resolve().parent / 'migrations/20261007_075_verified_city_category_ingestor_read.sql'


@unittest.skipUnless(os.environ.get('AGRO_CITY_POSTGRES_TEST') == '1',
                     'Explicit disposable local PostgreSQL opt-in')
class VerifiedCategoryIngestorACL(unittest.TestCase):
    def test_category_view_read_denied_before_075_and_granted_after(self):
        dsn = os.environ['DATABASE_URL']
        with psycopg.connect(dsn, autocommit=True) as db:
            self.assertTrue((db.info.host or '').startswith('/tmp/agro-'))
            self.assertIsNone(db.execute('SELECT inet_server_addr()').fetchone()[0])
            self.assertTrue(db.execute("SELECT has_table_privilege('agro_ingestor','public.verified_city_pdf_category_resolution','SELECT')").fetchone()[0])
            trigger = db.execute("""SELECT t.tgenabled,p.proname
              FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid
              WHERE t.tgrelid='public.city_pdf_price_resolution'::regclass
                AND t.tgname='validate_exact_price_resolution'""").fetchone()
            self.assertEqual(trigger, ('O','validate_exact_city_pdf_price_resolution'))
            definition = db.execute("SELECT pg_get_functiondef('public.validate_exact_city_pdf_price_resolution()'::regprocedure)").fetchone()[0]
            self.assertIn('verified_city_pdf_category_resolution', definition)
            owner_count = db.execute('SELECT count(*) FROM public.verified_city_pdf_category_resolution').fetchone()[0]
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with db.transaction():
                    db.execute('REVOKE SELECT ON public.verified_city_pdf_category_resolution FROM agro_ingestor')
                    db.execute('SET LOCAL ROLE agro_ingestor')
                    db.execute('SELECT count(*) FROM public.verified_city_pdf_category_resolution').fetchone()
            self.assertTrue(db.execute("SELECT has_table_privilege('agro_ingestor','public.verified_city_pdf_category_resolution','SELECT')").fetchone()[0])
            with db.transaction():
                db.execute('REVOKE SELECT ON public.verified_city_pdf_category_resolution FROM agro_ingestor')
                self.assertFalse(db.execute("SELECT has_table_privilege('agro_ingestor','public.verified_city_pdf_category_resolution','SELECT')").fetchone()[0])
                db.execute(SQL075.read_text())
                db.execute('SET LOCAL ROLE agro_ingestor')
                self.assertEqual(db.execute('SELECT count(*) FROM public.verified_city_pdf_category_resolution').fetchone()[0], owner_count)
            self.assertTrue(db.execute("SELECT has_table_privilege('agro_ingestor','public.verified_city_pdf_category_resolution','SELECT')").fetchone()[0])

"""Disposable-PG source-publication controls for reviewed old catalog keys."""
import hashlib
import json
import os
import re
import threading
import time
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg

from pipelines.ingestion import official_catalog, official_sources, worker

HERE = Path(__file__).parent
OLD = '1' * 64
PRIOR = '2' * 64
CURRENT = '3' * 64

def key(product, market):
    identity = {'product_id': product, 'series': 'dane-weekly', 'market': market,
                'currency': 'COP', 'unit': 'kg', 'basis': 'Precio mayorista semanal',
                'dimensions': {}}
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

MARKET = 'Armenia, Mercar'
CHOC = key('chocolo-mazorca', MARKET)
EGG = key('huevo-rojo', MARKET)



class ReviewedOlderGuardPostgres(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ['AGRO_REFERENCE_TEST_DSN']
        self.db = psycopg.connect(self.dsn, autocommit=True)
        if not str(self.db.info.host).startswith('/tmp/agro-'):
            self.db.close()
            raise RuntimeError('Private isolated PostgreSQL socket required')
        self.schema = 'qa_reviewed_guard_' + uuid.uuid4().hex[:12]
        self.db.execute(f'CREATE SCHEMA {self.schema}')
        self.db.execute(f'SET search_path={self.schema},public')
        self.db.execute("SET statement_timeout='15s'; SET lock_timeout='5s'")
        for table in ('source_document', 'official_price_quote', 'official_source_review',
                      'ingestion_asset', 'ingestion_checkpoint'):
            self.db.execute(f'CREATE TABLE {table} (LIKE public.{table} INCLUDING ALL)')
        migrations = HERE / 'migrations'
        first = (migrations / '20260927_007_official_catalog.sql').read_text()
        self.db.execute(re.sub(r'^GRANT .*;\n', '', first, flags=re.MULTILINE))
        self.db.execute((migrations / '20261004_054_official_catalog_previous_date.sql').read_text())
        self.db.execute((migrations / '20261005_055_official_catalog_dirty_fifo.sql').read_text())
        self.db.execute((migrations / '20261006_068_official_catalog_reviewed_older_guard.sql').read_text())
        self.deadline_token = worker.RUN_DEADLINE.set(None)

    def tearDown(self):
        worker.RUN_DEADLINE.reset(self.deadline_token)
        self.db.execute(f'DROP SCHEMA {self.schema} CASCADE')
        self.db.close()

    def doc(self, did):
        self.db.execute('''INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content)
          VALUES(%s,'verified source','DANE',%s,'application/pdf','original','',%s)''',
          (did, f'https://example.invalid/{did}.pdf', b'verified source'))

    def quote(self, did, locator, version, day, price, product='chocolo-mazorca', name='Chócolo mazorca'):
        self.db.execute('''INSERT INTO official_price_quote
          (document_id,source_locator,parser_version,quote_key,product_id,product_name,
           category,publisher,series,basis,currency,unit,market,observed_on,price,
           min_price,max_price,details)
          VALUES(%s,%s,%s,%s,%s,%s,'Verduras y hortalizas','DANE · SIPSA',
            'dane-weekly','Precio mayorista semanal','COP','kg',%s,%s,%s,%s,%s,'{}')''',
          (did, locator, version, key(product, MARKET), product, name, MARKET, day, price, price, price))

    def state(self, k=CHOC):
        return self.db.execute('''SELECT dirty,payload,winner_observed_on,previous_observed_on
          FROM official_catalog_current WHERE quote_key=%s''', (k,)).fetchone()

    def seed(self, old_day='2014-01-31', old_locator='old choc', previous_doc=PRIOR):
        for did in (OLD, PRIOR, CURRENT): self.doc(did)
        self.quote(OLD, old_locator, 'old', old_day, 437)
        if previous_doc == PRIOR:
            self.quote(PRIOR, 'prior choc', 'prior', '2026-09-25', 1050)
        else:
            self.quote(OLD, 'prior choc', 'old', '2026-09-25', 1050)
        self.quote(CURRENT, 'current choc', 'current', '2026-10-02', 1071)
        official_catalog.refresh_keys(self.db, [CHOC])
        self.assertFalse(self.state()[0])
        return self.state()[1]

    def review(self, locator, did=OLD):
        self.db.execute('''INSERT INTO official_source_review
          (document_id,source_locator,parser_version,record,reason)
          VALUES(%s,%s,'review','{}','source-bound withdrawal')''', (did, locator))

    def row(self, locator, day='2014-01-31', price=437):
        return {'source_locator': locator, 'product_id': 'chocolo-mazorca',
                'product_name': 'Chócolo mazorca', 'category': 'Verduras y hortalizas',
                'publisher': 'DANE · SIPSA', 'series': 'dane-weekly',
                'basis': 'Precio mayorista semanal', 'currency': 'COP',
                'unit': 'kg', 'market': MARKET, 'date': day,
                'price': price, 'min': price, 'max': price, 'details': {}}

    def test_full_reviewed_old_source_keeps_current_card_clean(self):
        payload = self.seed()
        self.quote(OLD, 'old egg', 'old', '2014-01-31', 500, 'huevo-rojo', 'Huevo rojo')
        rows = [self.row('old choc'), {'source_locator': 'old egg', 'price': None,
                'details': {'quality_issue': 'unit footnote missing'}}]
        self.assertEqual(official_sources.publish_rows(self.db, rows, OLD, 'dane-weekly-xlsx',
                         source_url=f'https://example.invalid/{OLD}.pdf'), 1)
        self.assertEqual(self.state(), (False, payload, date(2026, 10, 2), date(2026, 9, 25)))
        self.assertEqual(self.db.execute('SELECT count(*) FROM official_price_quote WHERE document_id=%s', (OLD,)).fetchone()[0], 3)
        self.assertEqual(self.db.execute('SELECT count(*) FROM official_source_review WHERE document_id=%s', (OLD,)).fetchone()[0], 1)
        self.assertTrue(self.db.execute("SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s AND step='official:complete'", (OLD,)).fetchone())

    def test_review_at_old_choc_locator_preserves_newer_winners(self):
        payload = self.seed()
        self.review('old choc')
        self.assertEqual(self.state()[0], False)
        self.assertEqual(self.state()[1], payload)

    def test_review_at_previous_locator_dirties_then_withdraws_previous(self):
        self.seed(previous_doc=OLD)
        self.review('prior choc')
        self.assertTrue(self.state()[0])
        official_catalog.refresh_keys(self.db, [CHOC])
        self.assertEqual(self.state()[3], date(2014, 1, 31))
        self.assertEqual(self.state()[1]['previous_price'], 437)

    def test_review_at_current_locator_dirties_and_withdraws_current(self):
        self.seed()
        self.review('current choc', CURRENT)
        self.assertTrue(self.state()[0])
        official_catalog.refresh_keys(self.db, [CHOC])
        self.assertEqual(self.state()[2], date(2026, 9, 25))
        self.assertEqual(self.state()[1]['price'], 1050)
        self.assertEqual(self.db.execute('SELECT count(*) FROM official_price_quote WHERE quote_key=%s',
                         (CHOC,)).fetchone()[0], 3, 'withdrawn original stays retained')

    def test_asset_review_old_source_preserves_but_current_source_dirties(self):
        payload = self.seed()
        for did in (OLD, CURRENT):
            self.db.execute('''INSERT INTO ingestion_asset(url,kind,document_id,status,observed_on)
              VALUES(%s,'dane-weekly-pdf',%s,'pending',%s)''',
              (f'https://example.invalid/{did}.pdf', did,
               '2014-01-31' if did == OLD else '2026-10-02'))
        self.db.execute("UPDATE ingestion_asset SET status='review' WHERE document_id=%s", (OLD,))
        self.assertEqual(self.state()[0:2], (False, payload))
        self.db.execute("UPDATE ingestion_asset SET status='pending' WHERE document_id=%s", (OLD,))
        self.assertEqual(self.state()[0:2], (False, payload))
        self.db.execute("UPDATE ingestion_asset SET status='review' WHERE document_id=%s", (CURRENT,))
        self.assertTrue(self.state()[0])
        official_catalog.refresh_keys(self.db, [CHOC])
        self.assertEqual(self.state()[2], date(2026, 9, 25))

    def test_asset_review_source_with_previous_day_dirties(self):
        self.seed(previous_doc=OLD)
        self.db.execute('''INSERT INTO ingestion_asset(url,kind,document_id,status,observed_on)
          VALUES(%s,'dane-weekly-pdf',%s,'pending','2026-09-25')''',
          (f'https://example.invalid/{OLD}.pdf', OLD))
        self.db.execute("UPDATE ingestion_asset SET status='review' WHERE document_id=%s", (OLD,))
        self.assertTrue(self.state()[0])

    def test_mixed_source_max_and_cache_metadata_drift_fail_closed(self):
        self.seed()
        self.quote(OLD, 'same doc newer', 'old', '2026-09-25', 1020)
        official_catalog.refresh_keys(self.db, [CHOC])
        official_catalog.mark_document_dirty(self.db, OLD, 'mixed-source', older_only=True)
        self.assertTrue(self.state()[0])
        official_catalog.refresh_keys(self.db, [CHOC])
        self.db.execute("UPDATE official_catalog_current SET version='old' WHERE quote_key=%s", (CHOC,))
        self.review('old choc')
        self.assertTrue(self.state()[0])

    def test_source_with_previous_day_fails_closed(self):
        self.seed(previous_doc=OLD)
        official_catalog.mark_document_dirty(self.db, OLD, 'revised-reviewed', older_only=True)
        self.assertTrue(self.state()[0])

    def test_missing_cached_previous_fails_closed(self):
        self.seed()
        self.db.execute('UPDATE official_catalog_current SET previous_observed_on=NULL WHERE quote_key=%s', (CHOC,))
        self.review('old choc')
        self.assertTrue(self.state()[0])

    def test_missing_payload_observed_on_fails_closed_in_all_four_guards(self):
        for route in ('document', 'review', 'quote', 'asset'):
            with self.subTest(route=route):
                self.seed()
                self.db.execute("UPDATE official_catalog_current SET payload=payload-'observed_on' WHERE quote_key=%s", (CHOC,))
                if route == 'document':
                    official_catalog.mark_document_dirty(self.db, OLD, 'missing-day', older_only=True)
                elif route == 'review':
                    self.review('old choc')
                elif route == 'asset':
                    self.db.execute('''INSERT INTO ingestion_asset(url,kind,document_id,status,observed_on)
                      VALUES(%s,'dane-weekly-pdf',%s,'review','2014-01-31')''',
                      (f'https://example.invalid/{OLD}.pdf', OLD))
                else:
                    self.quote(OLD, 'another old choc', 'new', '2014-02-07', 440)
                self.assertTrue(self.state()[0])
                self.db.execute('TRUNCATE official_price_quote,official_source_review,official_catalog_current,ingestion_asset')
                self.db.execute('TRUNCATE source_document')

    def test_json_null_observed_on_and_null_refreshed_at_fail_closed(self):
        self.seed()
        self.db.execute("UPDATE official_catalog_current SET payload=jsonb_set(payload,'{observed_on}','null'::jsonb) WHERE quote_key=%s", (CHOC,))
        self.review('old choc')
        self.assertTrue(self.state()[0])
        official_catalog.refresh_keys(self.db, [CHOC])
        self.db.execute('UPDATE official_catalog_current SET refreshed_at=NULL WHERE quote_key=%s', (CHOC,))
        official_catalog.mark_document_dirty(self.db, OLD, 'missing-refreshed', older_only=True)
        self.assertTrue(self.state()[0])

    def test_null_version_rejected_by_schema_and_wrong_version_dirties(self):
        self.seed()
        with self.assertRaises(psycopg.errors.NotNullViolation):
            self.db.execute('UPDATE official_catalog_current SET version=NULL WHERE quote_key=%s', (CHOC,))
        self.db.execute("UPDATE official_catalog_current SET version='obsolete' WHERE quote_key=%s", (CHOC,))
        self.review('old choc')
        self.assertTrue(self.state()[0])

    def test_same_locator_new_identity_independent_insert_trigger(self):
        self.seed()
        self.quote(OLD, 'old choc', 'new', '2014-01-31', 437,
                   'changed-product', 'Changed product')
        self.assertTrue(self.state(key('changed-product', MARKET))[0])
        self.assertFalse(self.state()[0])

    def test_new_previous_day_insert_dirties_before_guarded_refresh(self):
        self.seed()
        observed = []
        actual_refresh = official_catalog.refresh_document
        def see_dirty(db, did, revision, *, older_only=False):
            observed.append((self.state()[0], older_only))
            return actual_refresh(db, did, revision, older_only=older_only)
        revised = self.row('old choc', '2026-09-30', 1060)
        with patch.object(official_catalog, 'refresh_document', side_effect=see_dirty):
            self.assertEqual(official_sources.publish_rows(self.db, [revised], OLD,
                             'dane-weekly-xlsx',
                             source_url=f'https://example.invalid/{OLD}.pdf'), 1)
        self.assertEqual(observed, [(True, True)])
        self.assertEqual(self.state()[2:4], (date(2026, 10, 2), date(2026, 9, 30)))
        self.assertEqual(self.state()[1]['previous_price'], 1060)

    def test_same_locator_current_revision_and_retired_different_key_dirties(self):
        self.seed()
        self.quote(CURRENT, 'current choc', 'new-older', '2014-01-31', 437)
        self.assertTrue(self.state()[0], 'same-locator correction may withdraw current winner')
        official_catalog.refresh_keys(self.db, [CHOC])
        self.assertEqual(self.state()[2], date(2026, 9, 25))
        self.review('current choc', CURRENT)
        self.assertTrue(self.state()[0], 'current-source review remains fail-closed')
        self.quote(CURRENT, 'current choc', 'reassigned', '2026-10-02', 1080,
                   'renamed-product', 'Renamed product')
        self.assertTrue(self.state(key('renamed-product', MARKET))[0])

    def test_asset_review_insert_update_day_and_delete_old_source(self):
        payload = self.seed()
        url = f'https://example.invalid/{OLD}.pdf'
        self.db.execute('''INSERT INTO ingestion_asset(url,kind,document_id,status,observed_on)
          VALUES(%s,'dane-weekly-pdf',%s,'review','2014-01-31')''', (url, OLD))
        self.assertEqual(self.state()[0:2], (False, payload))
        self.db.execute("UPDATE ingestion_asset SET observed_on='2014-01-24' WHERE url=%s", (url,))
        self.assertEqual(self.state()[0:2], (False, payload))
        self.db.execute('DELETE FROM ingestion_asset WHERE url=%s', (url,))
        self.assertEqual(self.state()[0:2], (False, payload))

    def test_review_rollback_restores_clean_cache_and_history(self):
        payload = self.seed(previous_doc=OLD)
        with self.assertRaisesRegex(RuntimeError, 'abort private transaction'):
            with self.db.transaction():
                self.review('prior choc')
                self.assertTrue(self.state()[0])
                raise RuntimeError('abort private transaction')
        self.assertEqual(self.state()[0:2], (False, payload))
        self.assertEqual(self.db.execute('SELECT count(*) FROM official_source_review').fetchone()[0], 0)

    def test_review_waits_for_cache_lock_and_reads_committed_drift(self):
        self.seed()
        other = psycopg.connect(self.dsn, autocommit=True)
        self.addCleanup(other.close)
        other.execute(f'SET search_path={self.schema},public')
        other.execute("SET statement_timeout='5s'; SET lock_timeout='5s'")
        errors = []
        def insert_review():
            try:
                other.execute('''INSERT INTO official_source_review
                  (document_id,source_locator,parser_version,record,reason)
                  VALUES(%s,'old choc','locked-review','{}','private lock test')''', (OLD,))
            except Exception as exc: errors.append(type(exc).__name__)
        with self.db.transaction():
            self.db.execute("UPDATE official_catalog_current SET refreshed_at=refreshed_at-interval '1 day' WHERE quote_key=%s", (CHOC,))
            thread = threading.Thread(target=insert_review)
            thread.start()
            time.sleep(0.08)
            self.assertTrue(thread.is_alive())
        thread.join(timeout=4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(self.state()[0], 'guard checks committed cache metadata after lock wait')


if __name__ == '__main__': unittest.main()

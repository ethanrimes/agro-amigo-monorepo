"""Exact November 2019 original and append-only publisher controls, private shadow."""

import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import dane_weekly as weekly, official_sources, queue_plan, worker
from .retained_pdf_upgrade import retained_pdf_upgrade
from .resumable_inputs import WorkDeferred
from .test_official_catalog import install_cache


URL = weekly.NOV2019_COTINUACION_URL
DID = weekly.NOV2019_COTINUACION_SHA
KIND = 'dane-weekly-pdf'
OLD = 'official-v2:dane-weekly-v16'
NEW = 'official-v2:nov2019-cotinuacion-v1:dane-weekly-v24'
ORIGINAL = Path(__file__).parent / 'testdata' / (DID + '.pdf')


class ExactWeeklyCotinuacionPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ.get('AGRO_REFERENCE_TEST_DSN')
        if not dsn:
            raise RuntimeError('Explicit owned PostgreSQL DSN required')
        cls.db = psycopg.connect(dsn, autocommit=True)
        if not str(cls.db.info.host).startswith('/tmp/agro-'):
            cls.db.close()
            raise RuntimeError('Only a private PostgreSQL socket is permitted')
        cls.db.execute("SET search_path=pg_temp; SET statement_timeout='90s'")
        for table in ('source_document', 'ingestion_asset', 'official_price_quote',
                      'official_source_review', 'ingestion_checkpoint', 'historical_price'):
            cls.db.execute(f'CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)')
        cls.db.execute('CREATE INDEX quote_identity_cotinuacion ON official_price_quote(quote_key,observed_on DESC)')
        install_cache(cls.db)
        cls.body = ORIGINAL.read_bytes()
        if hashlib.sha256(cls.body).hexdigest() != DID:
            raise RuntimeError('Private full original fixture SHA changed')
        cls.rows = weekly.parse_pdf(cls.body, URL)
        with patch.object(weekly, 'NOV2019_COTINUACION_SHA', '0' * 64):
            cls.old_rows = weekly.parse_pdf(cls.body, URL)
        cls.by_locator = {row['source_locator']: row for row in cls.rows}
        cls.old_by_locator = {row['source_locator']: row for row in cls.old_rows}
        cls.changed = sorted(loc for loc in cls.by_locator if cls.by_locator[loc] != cls.old_by_locator[loc])
        if (len(cls.rows), len(cls.old_rows), len(cls.changed)) != (4660, 4660, 38):
            raise RuntimeError('Whole-original native grid changed')

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.db.execute('BEGIN')
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) "
            "VALUES(%s,'DANE weekly','DANE',%s,'application/pdf','original','2019-11-02/2019-11-08',%s,%s)",
            (DID, URL, self.body, Jsonb({'ingestion_kind': KIND})),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,observed_on,checked_at,records) "
            "VALUES(%s,%s,'complete',%s,%s,'2019-11-08',now()-interval '7 hours',4497)",
            (URL, KIND, OLD, DID),
        )

    def tearDown(self):
        self.db.execute('ROLLBACK')

    def test_whole_source_identity_and_every_boundary(self):
        changed = set(self.changed)
        self.assertEqual(len(changed), 38)
        old_priced = sum(row['price'] is not None for row in self.old_rows)
        new_priced = sum(row['price'] is not None for row in self.rows)
        self.assertEqual((old_priced, new_priced), (4497, 4497))
        self.assertEqual(set(self.by_locator), set(self.old_by_locator))
        for loc in self.by_locator:
            old, new = self.old_by_locator[loc], self.by_locator[loc]
            if loc not in changed:
                self.assertEqual(new, old)
                continue
            self.assertEqual(old['source_page'], 34)
            self.assertEqual(old['product_id'], 'tomate-de-arbol-cotinuacion')
            self.assertEqual(new['product_id'], 'tomate-de-arbol')
            self.assertEqual(new['product_name'], 'Tomate de árbol')
            self.assertEqual(new['details']['literal_product_heading'], 'Tomate de árbol (cotinuación)')
            old_safe, new_safe = dict(old), dict(new)
            for safe in (old_safe, new_safe):
                safe.pop('product_id')
                safe.pop('product_name')
                safe['identity_dimensions'] = dict(safe['identity_dimensions'])
                safe['identity_dimensions'].pop('source_product')
                safe['details'] = dict(safe['details'])
                safe['details'].pop('literal_product_heading', None)
            self.assertEqual(new_safe, old_safe)
        args = [URL, DID, 34, 1, 1, 'frutas frescas', weekly.NOV2019_COTINUACION_PERIOD]
        self.assertTrue(weekly._reviewed_cotinuacion_source(*args))
        replacements = (URL + '?alias', '0'*64, 33, 2, 2, 'verduras',
                        (weekly.NOV2019_COTINUACION_PERIOD[0], weekly.NOV2019_COTINUACION_PERIOD[1].replace(day=9)))
        for index, replacement in enumerate(replacements):
            wrong = args.copy()
            wrong[index] = replacement
            self.assertFalse(weekly._reviewed_cotinuacion_source(*wrong))
        for name in ('Tomate de árbol (cotiniación)', 'Tomate de árbol cotinuación',
                     'Tomate de árbol (cotinuación) extra', 'Tomate de árbol (continuación) extra'):
            self.assertEqual(weekly._product_heading(name, reviewed_cotinuacion=True), (name, False))

    def test_exact_retained_queue_version_and_drift_guards(self):
        self.assertEqual(worker.parser_version(KIND, URL), NEW)
        self.assertEqual(worker.asset_parser_version(KIND, URL), NEW)
        self.assertEqual(worker.parser_version(KIND, URL + '?alias'), 'official-v2:dane-weekly-v24')
        self.assertEqual(retained_pdf_upgrade(self.db, URL, KIND, NEW), self.body)
        self.assertIn(URL, [r[0] for r in queue_plan.repair_candidates(self.db, 8)])
        self.db.execute('UPDATE ingestion_asset SET checked_at=now() WHERE url=%s', (URL,))
        self.assertNotIn(URL, [r[0] for r in queue_plan.repair_candidates(self.db, 8)])
        self.db.execute('UPDATE ingestion_asset SET checked_at=now()-interval \'7 hours\',document_id=%s WHERE url=%s', ('0'*64, URL))
        self.assertIsNone(retained_pdf_upgrade(self.db, URL, KIND, NEW))
        self.assertNotIn(URL, [r[0] for r in queue_plan.repair_candidates(self.db, 8)])
        self.db.execute('UPDATE ingestion_asset SET document_id=%s WHERE url=%s', (DID, URL))
        self.db.execute('UPDATE source_document SET content=%s WHERE id=%s', (self.body + b'changed', DID))
        with self.assertRaisesRegex(ValueError, 'invalid original SHA'):
            retained_pdf_upgrade(self.db, URL, KIND, NEW)
        self.db.execute('UPDATE source_document SET content=%s WHERE id=%s', (self.body, DID))
        self.db.execute('UPDATE source_document SET source_url=%s WHERE id=%s', (URL+'?alias', DID))
        self.assertIsNone(retained_pdf_upgrade(self.db, URL, KIND, NEW))

    def test_publication_revision_requires_exact_original_owner_and_body(self):
        with self.assertRaisesRegex(ValueError, 'original changed'):
            official_sources.publish_rows(self.db, [], '0'*64, KIND, source_url=URL)
        self.db.execute('UPDATE source_document SET source_url=%s WHERE id=%s', (URL+'?alias', DID))
        with self.assertRaisesRegex(ValueError, 'original changed'):
            official_sources.publish_rows(self.db, [], DID, KIND, source_url=URL)
        self.db.execute('UPDATE source_document SET source_url=%s,content=%s WHERE id=%s',
                        (URL, self.body+b'changed', DID))
        with self.assertRaisesRegex(ValueError, 'original changed'):
            official_sources.publish_rows(self.db, [], DID, KIND, source_url=URL)
        self.db.execute('UPDATE source_document SET content=%s,media_type=%s WHERE id=%s',
                        (self.body, 'text/html', DID))
        with self.assertRaisesRegex(ValueError, 'original changed'):
            official_sources.publish_rows(self.db, [], DID, KIND, source_url=URL)
        self.db.execute('UPDATE source_document SET media_type=%s,metadata=%s WHERE id=%s',
                        ('application/pdf', Jsonb({'ingestion_kind': 'daily-pdf'}), DID))
        with self.assertRaisesRegex(ValueError, 'original changed'):
            official_sources.publish_rows(self.db, [], DID, KIND, source_url=URL)

    def test_full_original_append_only_and_idempotent_catalog(self):
        with patch.object(worker, 'parser_version', return_value=OLD), patch('pipelines.ingestion.write_pacing.pause_between_batches'):
            self.assertEqual(official_sources.publish_rows(self.db, self.old_rows, DID, KIND), 4497)
        old_count = self.db.execute('SELECT count(*) FROM official_price_quote WHERE document_id=%s AND parser_version=%s', (DID, OLD)).fetchone()[0]
        old_review_count = self.db.execute('SELECT count(*) FROM official_source_review WHERE document_id=%s AND parser_version=%s', (DID, OLD)).fetchone()[0]
        self.assertEqual((old_count, old_review_count), (4497, 163))
        self.db.execute("UPDATE official_price_quote SET parsed_at=now()-interval '1 minute' WHERE document_id=%s AND parser_version=%s", (DID, OLD))
        old_xmin = dict(self.db.execute('SELECT source_locator,xmin::text FROM official_price_quote WHERE document_id=%s AND parser_version=%s', (DID, OLD)).fetchall())
        with patch('pipelines.ingestion.write_pacing.pause_between_batches'):
            self.assertEqual(official_sources.publish_rows(self.db, self.rows, DID, KIND, source_url=URL), 4497)
            self.assertEqual(official_sources.publish_rows(self.db, self.rows, DID, KIND, source_url=URL), 4497)
        self.assertEqual(self.db.execute('SELECT count(*) FROM official_price_quote WHERE document_id=%s AND parser_version=%s', (DID, NEW)).fetchone()[0], 4497)
        self.assertEqual(self.db.execute('SELECT count(*) FROM official_source_review WHERE document_id=%s AND parser_version=%s', (DID, NEW)).fetchone()[0], 163)
        self.assertEqual(dict(self.db.execute('SELECT source_locator,xmin::text FROM official_price_quote WHERE document_id=%s AND parser_version=%s', (DID, OLD)).fetchall()), old_xmin)
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='official:complete' AND records=4497", (DID, NEW)).fetchone()[0], 1)
        for loc in self.changed:
            row = self.db.execute('SELECT product_id,product_name,details FROM published_official_price WHERE document_id=%s AND source_locator=%s', (DID, loc)).fetchone()
            self.assertEqual(row[:2], ('tomate-de-arbol', 'Tomate de árbol'))
            self.assertEqual(row[2]['literal_product_heading'], 'Tomate de árbol (cotinuación)')
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_official_price WHERE document_id=%s AND product_id='tomate-de-arbol-cotinuacion'", (DID,)).fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_official_price WHERE document_id=%s AND product_id='tomate-de-arbol'", (DID,)).fetchone()[0], 48)

    def test_partial_batch_resume_keeps_old_rows_and_no_false_completion(self):
        old_subset = [self.old_by_locator[loc] for loc in self.changed]
        with patch.object(worker, 'parser_version', return_value=OLD), patch('pipelines.ingestion.write_pacing.pause_between_batches'):
            official_sources.publish_rows(self.db, old_subset, DID, KIND)
        old_xmin = dict(self.db.execute('SELECT source_locator,xmin::text FROM official_price_quote WHERE document_id=%s AND parser_version=%s', (DID, OLD)).fetchall())
        subset = [self.by_locator[loc] for loc in self.changed]
        subset.extend(row for row in self.rows if row['price'] is not None and row['source_locator'] not in self.changed) 
        subset = subset[:300]
        with patch('pipelines.ingestion.write_pacing.pause_between_batches', side_effect=WorkDeferred('forced after first committed batch')):
            with self.assertRaises(WorkDeferred):
                official_sources.publish_rows(self.db, subset, DID, KIND, source_url=URL)
        self.assertEqual(self.db.execute('SELECT count(*) FROM official_price_quote WHERE document_id=%s AND parser_version=%s', (DID, NEW)).fetchone()[0], 256)
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='official:complete'", (DID, NEW)).fetchone()[0], 0)
        with patch('pipelines.ingestion.write_pacing.pause_between_batches'):
            official_sources.publish_rows(self.db, subset, DID, KIND, source_url=URL)
            official_sources.publish_rows(self.db, subset, DID, KIND, source_url=URL)
        self.assertEqual(self.db.execute('SELECT count(*) FROM official_price_quote WHERE document_id=%s AND parser_version=%s', (DID, NEW)).fetchone()[0], 300)
        self.assertEqual(dict(self.db.execute('SELECT source_locator,xmin::text FROM official_price_quote WHERE document_id=%s AND parser_version=%s', (DID, OLD)).fetchall()), old_xmin)


if __name__ == '__main__':
    unittest.main()

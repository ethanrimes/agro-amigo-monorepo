"""Exact February 2014 readable annexes remain unpriced, retained reviews.

Full-suite runner supplies a fresh, owned local PostgreSQL schema and this
opt-in DSN; the registered suite must enable it and run with zero skips.
"""

import contextlib
import hashlib
import io
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import dane_weekly, official_sources, queue_plan, worker
from .reviewed_weekly_feb2014 import INDEX_SHA, PAIRS, REVIEW_LOCATOR, REVIEW_MARKER, VERSION_SUFFIX


FIXTURES = Path(__file__).parent / 'testdata' / 'weekly_feb2014_reviewed'


@unittest.skipUnless(os.environ.get('AGRO_WEEKLY_FEB2014_TEST_DSN'),
                     'Fresh owned weekly full-schema PostgreSQL DSN required')
class ReviewedFeb2014WeeklyPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = psycopg.connect(os.environ['AGRO_WEEKLY_FEB2014_TEST_DSN'], autocommit=True)
        if (not str(cls.db.info.host).startswith('/tmp/agro-weekly-')
                or not cls.db.info.dbname.startswith('agro_weekly_')
                or cls.db.execute('SELECT inet_server_addr()').fetchone()[0] is not None):
            cls.db.close()
            raise RuntimeError('Only a fresh owned weekly Unix-socket database is allowed')
        cls.db.execute("SET statement_timeout='60s'")
        for table in ('source_document', 'official_price_quote', 'official_source_review',
                      'ingestion_checkpoint'):
            if cls.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:
                cls.db.close()
                raise RuntimeError('February 2014 review test requires an empty database')

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_exact_three_failed_annexes_queue_and_finish_as_review(self):
        db = self.db
        ordinary_version = worker.parser_version('dane-weekly-xlsx')
        for url, case in PAIRS.items():
            with self.subTest(url=url):
                xbody = (FIXTURES / url.rsplit('/', 1)[-1]).read_bytes()
                pbody = (FIXTURES / case['pdf_url'].rsplit('/', 1)[-1]).read_bytes()
                self.assertEqual(hashlib.sha256(xbody).hexdigest(), case['xls_sha'])
                self.assertEqual(hashlib.sha256(pbody).hexdigest(), case['pdf_sha'])
                for did, name, body, kind, media in (
                    (case['xls_sha'], url, xbody, 'dane-weekly-xlsx', 'application/vnd.ms-excel'),
                    (case['pdf_sha'], case['pdf_url'], pbody, 'dane-weekly-pdf', 'application/pdf'),
                ):
                    db.execute('INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,'
                               'reference_period,content,metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                               (did, name.rsplit('/', 1)[-1], 'DANE · SIPSA', name, media,
                                'original', '2014-02', body, Jsonb({'ingestion_kind': kind})))
                printed = [row for row in dane_weekly.parse(pbody, case['pdf_url'], 'dane-weekly-pdf')
                           if row['source_locator'] == 'PDF page 6,table 1,column 1,line 2']
                self.assertEqual(len(printed), 1)
                self.assertEqual(official_sources.publish_rows(
                    db, printed, case['pdf_sha'], 'dane-weekly-pdf', source_url=case['pdf_url']), 1)
                pdf_quote_before = db.execute(
                    'SELECT xmin::text,source_locator,quote_key,price,min_price,max_price '
                    'FROM official_price_quote WHERE document_id=%s', (case['pdf_sha'],)
                ).fetchone()
                self.assertEqual(len(db.execute(
                    'SELECT document_id FROM published_official_price WHERE document_id=%s',
                    (case['pdf_sha'],)).fetchall()), 1)
                day = date.fromisoformat(case['period_end'])
                db.execute('INSERT INTO ingestion_asset(url,kind,observed_on,status,document_id,'
                           'processor_version,records,error) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                           (url, 'dane-weekly-xlsx', day, 'failed', case['xls_sha'],
                            ordinary_version, 0, 'Old grouped-workbook period error'))
                new_version = worker.asset_parser_version('dane-weekly-xlsx', url)
                self.assertEqual(new_version, worker.parser_version('dane-weekly-xlsx', url))
                self.assertIn(VERSION_SUFFIX, new_version)
                self.assertNotEqual(new_version, ordinary_version)
                offered = queue_plan.backfill_candidates(db, limit=100)
                self.assertTrue(any(row[0] == url and row[1] == 'dane-weekly-xlsx'
                                    for row in offered))
                original_xmin = db.execute('SELECT xmin::text FROM source_document WHERE id=%s',
                                           (case['xls_sha'],)).fetchone()[0]
                if url == next(iter(PAIRS)):
                    with self.assertRaisesRegex(ValueError, 'retained review differs'):
                        with db.transaction():
                            db.execute('INSERT INTO official_source_review('
                                       'document_id,source_locator,parser_version,record,reason) '
                                       'VALUES (%s,%s,%s,%s,%s)',
                                       (case['xls_sha'], REVIEW_LOCATOR, new_version,
                                        Jsonb({'price': None, 'details': {'quality_issue': REVIEW_MARKER}}),
                                        REVIEW_MARKER))
                            with patch.object(worker, 'fetch_asset', return_value=xbody), \
                                 patch('pipelines.ingestion.blob_archive.retain_original_blob'):
                                worker.process_asset(db, url, 'dane-weekly-xlsx', day)
                    self.assertEqual(db.execute('SELECT count(*) FROM official_source_review '
                                                'WHERE document_id=%s', (case['xls_sha'],)).fetchone()[0], 0)
                    self.assertEqual(db.execute('SELECT status,document_id FROM ingestion_asset '
                                                'WHERE url=%s', (url,)).fetchone(),
                                     ('failed', case['xls_sha']))
                with (patch.object(worker, 'connect', return_value=contextlib.nullcontext(db)),
                      patch.object(worker, 'fetch_asset', return_value=xbody) as fetched,
                      patch('pipelines.ingestion.blob_archive.retain_original_blob'),
                      patch('pipelines.ingestion.ocr.drain', return_value={'processed': 0}),
                      patch.dict(os.environ, {'AzureWebJobsStorage': ''}),
                      contextlib.redirect_stdout(io.StringIO())):
                    result = worker.run(mode='discover', limit=1, time_budget=180,
                                        ocr_limit=0, ocr_scan_limit=0, asset_url=url)
                self.assertFalse(result['errors'])
                self.assertTrue(fetched.called)
                self.assertTrue(fetched.call_args.kwargs['force'])
                asset = db.execute('SELECT status,records,error,document_id FROM ingestion_asset '
                                   'WHERE url=%s', (url,)).fetchone()
                self.assertEqual(asset[:2], ('review', 0))
                self.assertEqual(asset[3], case['xls_sha'])
                self.assertIn(REVIEW_MARKER, asset[2])
                self.assertIn('Old grouped-workbook period error', asset[2])
                review = db.execute('SELECT source_locator,parser_version,record,reason '
                                    'FROM official_source_review WHERE document_id=%s',
                                    (case['xls_sha'],)).fetchall()
                self.assertEqual(len(review), 1)
                self.assertEqual(review[0][:2], (REVIEW_LOCATOR, new_version))
                self.assertEqual(review[0][3], REVIEW_MARKER)
                details = review[0][2]['details']
                self.assertEqual(details['quality_issue'], REVIEW_MARKER)
                self.assertEqual(details['native_numeric_rows_untyped'], case['numeric_rows'])
                self.assertEqual((details['period_start'], details['period_end']),
                                 (case['period_start'], case['period_end']))
                self.assertEqual(details['official_index_sha256'], INDEX_SHA)
                self.assertEqual(details['paired_pdf_sha256'], case['pdf_sha'])
                self.assertEqual(details['original_sha256'], case['xls_sha'])
                self.assertIsNone(details['literal_unit_heading'])
                self.assertEqual(db.execute('SELECT count(*) FROM official_price_quote WHERE document_id=%s',
                                            (case['xls_sha'],)).fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT records FROM ingestion_checkpoint '
                                            "WHERE document_id=%s AND processor_version=%s AND step='official:complete'",
                                            (case['xls_sha'], new_version)).fetchone(), (0,))
                self.assertEqual(db.execute('SELECT xmin::text FROM source_document WHERE id=%s',
                                            (case['xls_sha'],)).fetchone()[0], original_xmin)
                self.assertEqual(db.execute(
                    'SELECT xmin::text,source_locator,quote_key,price,min_price,max_price '
                    'FROM official_price_quote WHERE document_id=%s', (case['pdf_sha'],)
                ).fetchone(), pdf_quote_before)
                self.assertEqual(len(db.execute(
                    'SELECT document_id FROM published_official_price WHERE document_id=%s',
                    (case['pdf_sha'],)).fetchall()), 1)
                with patch.object(worker, 'fetch_asset', return_value=xbody), \
                     patch('pipelines.ingestion.blob_archive.retain_original_blob'):
                    self.assertEqual(worker.process_asset(db, url, 'dane-weekly-xlsx', day), 0)
                self.assertEqual(db.execute('SELECT count(*) FROM official_source_review WHERE document_id=%s',
                                            (case['xls_sha'],)).fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT count(*) FROM official_price_quote WHERE document_id=%s',
                                            (case['xls_sha'],)).fetchone()[0], 0)

    def test_z_bad_revision_rollback_and_ordinary_versions_unchanged(self):
        db = self.db
        url, case = next(iter(PAIRS.items()))
        body = (FIXTURES / url.rsplit('/', 1)[-1]).read_bytes()
        day = date.fromisoformat(case['period_end'])
        before = db.execute('SELECT status,document_id FROM ingestion_asset WHERE url=%s', (url,)).fetchone()
        with self.assertRaisesRegex(ValueError, 'original changed'):
            with db.transaction():
                with patch.object(worker, 'fetch_asset', return_value=body + b'x'), \
                     patch('pipelines.ingestion.blob_archive.retain_original_blob'):
                    worker.process_asset(db, url, 'dane-weekly-xlsx', day)
        self.assertEqual(db.execute('SELECT status,document_id FROM ingestion_asset WHERE url=%s',
                                    (url,)).fetchone(), before)
        self.assertEqual(db.execute('SELECT count(*) FROM official_source_review WHERE document_id=%s',
                                    (case['xls_sha'],)).fetchone()[0], 1)
        self.assertEqual(db.execute('SELECT count(*) FROM official_price_quote WHERE document_id=%s',
                                    (case['xls_sha'],)).fetchone()[0], 0)
        ordinary = 'https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSASemanal-19sep25sep-2026.xlsx'
        self.assertEqual(worker.asset_parser_version('dane-weekly-xlsx', ordinary),
                         worker.parser_version('dane-weekly-xlsx'))
        self.assertNotIn(VERSION_SUFFIX, worker.asset_parser_version('dane-weekly-xlsx', ordinary))
        self.assertTrue(dane_weekly.UNIT_REVIEW_ORIGINALS)
        old_2018_url = next(iter(dane_weekly.UNIT_REVIEW_ORIGINALS.values()))['url']
        self.assertEqual(worker.asset_parser_version('dane-weekly-xlsx', old_2018_url),
                         worker.parser_version('dane-weekly-xlsx'))
        self.assertIs(official_sources.adapter('dane-weekly-xlsx'), dane_weekly)
        self.assertIn('pipelines/ingestion/reviewed_weekly_feb2014.py', worker.RELEASE_FILES)


if __name__ == '__main__':
    unittest.main()

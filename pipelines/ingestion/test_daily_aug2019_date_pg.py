"""Actual retained worker publication and idempotency on an owned local database."""
import hashlib
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import psycopg

from pipelines.ingestion import worker, daily_recovery
from pipelines.ingestion.test_input_pdf_v17_role import install
from .test_daily_aug2019_date import HERE, XLS_SHA, DAY, URL


@unittest.skipUnless(os.environ.get('AGRO_AUG2019_PRIVATE_DSN'), 'Owned Unix-only PostgreSQL required')
class ActualWorkerPublication(unittest.TestCase):
    def test_retained_native_worker_publication_and_replay_preserve_source_and_rows(self):
        with psycopg.connect(os.environ['AGRO_AUG2019_PRIVATE_DSN'], autocommit=True) as admin:
            self.assertTrue(admin.info.host.startswith('/tmp/agro-aug2019-owned-'))
            self.assertIsNone(admin.execute('SELECT inet_server_addr()').fetchone()[0])
            self.assertEqual(admin.info.dbname, 'postgres')
            install(admin)
            admin.execute('SET statement_timeout=15000')
            admin.execute('SET ROLE agro_ingestor')
            body = (HERE / (XLS_SHA + '.xlsx')).read_bytes()
            expected = daily_recovery.parse_daily(body, DAY)['rows']
            with patch('pipelines.ingestion.blob_archive.retain_original_blob', return_value=True):
                self.assertEqual(worker.archive(admin, URL, body, 'daily', DAY), XLS_SHA)
            admin.execute("""INSERT INTO ingestion_asset
              (url,kind,observed_on,status,processor_version,document_id,records,error)
              VALUES(%s,'daily',%s,'failed',%s,%s,0,%s)""",
              (URL, DAY, worker.parser_version('daily'), XLS_SHA,
               'ValueError: Daily workbook has no verifiable publication date'))
            source_before = admin.execute(
                'SELECT row_to_json(d)::text,d.xmin::text FROM source_document d WHERE id=%s',
                (XLS_SHA,)).fetchone()
            self.assertTrue(worker.retained_reparse_during_host_cooldown(admin, URL, 'daily'))
            forbidden = AssertionError('Network/OCR escaped exact retained native path')
            with patch.object(worker, '_get', side_effect=forbidden), \
                 patch.object(worker.SESSION, 'request', side_effect=forbidden), \
                 patch('pipelines.ingestion.ocr.transcribe', side_effect=forbidden), \
                 patch('pipelines.ingestion.blob_archive.retain_original_blob', return_value=True):
                self.assertEqual(worker.process_asset(admin, URL, 'daily', DAY), 391)
            actual = admin.execute("""SELECT source_locator,series,observed_on,product_name,
                market_name,unit,price,change_percent,details FROM historical_price
                WHERE document_id=%s ORDER BY source_locator""", (XLS_SHA,)).fetchall()
            self.assertEqual(len(actual), 391)
            # PostgreSQL numeric and parser floating values are compared at
            # the native cell precision; all identity/date/details fields exact.
            by_locator = {row[0]: row for row in expected}
            for row in actual:
                wanted = by_locator[row[0]]
                self.assertEqual(row[:6], wanted[:6])
                self.assertEqual(float(row[6]), wanted[6])
                self.assertEqual(float(row[7]) if row[7] is not None else None, wanted[7])
                self.assertEqual(row[8], wanted[8])
            state = admin.execute('SELECT status,records,processor_version FROM ingestion_asset WHERE url=%s', (URL,)).fetchone()
            self.assertEqual(state, ('complete', 391, worker.asset_parser_version('daily', URL)))
            self.assertEqual(admin.execute('SELECT count(*) FROM daily_price WHERE document_id=%s', (XLS_SHA,)).fetchone()[0], 391)
            self.assertEqual(admin.execute('SELECT count(*) FROM source_ocr_task WHERE document_id=%s', (XLS_SHA,)).fetchone()[0], 0)
            self.assertEqual(admin.execute(
                'SELECT row_to_json(d)::text,d.xmin::text FROM source_document d WHERE id=%s', (XLS_SHA,)).fetchone(), source_before)
            snapshot = admin.execute('SELECT row_to_json(h)::text,h.xmin::text FROM historical_price h WHERE document_id=%s ORDER BY source_locator', (XLS_SHA,)).fetchall()
            # Completed assets revalidate upstream; returning the exact same
            # 200 body must retain every quote and its immutable original.
            response = SimpleNamespace(status_code=200, content=body, headers={},
                                       close=lambda: None, raise_for_status=lambda: None)
            with patch.object(worker, '_get', return_value=response), \
                 patch('pipelines.ingestion.blob_archive.retain_original_blob', return_value=True), \
                 patch('pipelines.ingestion.ocr.transcribe', side_effect=forbidden):
                self.assertEqual(worker.process_asset(admin, URL, 'daily', DAY), 0)
            self.assertEqual(admin.execute('SELECT row_to_json(h)::text,h.xmin::text FROM historical_price h WHERE document_id=%s ORDER BY source_locator', (XLS_SHA,)).fetchall(), snapshot)
            self.assertEqual(admin.execute('SELECT row_to_json(d)::text,d.xmin::text FROM source_document d WHERE id=%s', (XLS_SHA,)).fetchone(), source_before)


if __name__ == '__main__':
    unittest.main()

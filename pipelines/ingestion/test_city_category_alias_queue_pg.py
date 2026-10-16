"""Crowded FIFO proof for two exact city source repair pins."""
import os
import unittest

import psycopg
from psycopg.types.json import Jsonb

from . import city_category_alias_checkpoint as alias, city_reports, queue_plan


@unittest.skipUnless(os.environ.get('AGRO_REFERENCE_TEST_DSN'),
                     'Disposable local PostgreSQL opt-in required')
class CityCategoryAliasQueuePg(unittest.TestCase):
    def test_two_exact_pins_cooldown_and_sha_drift_with_generic_progress(self):
        with psycopg.connect(os.environ['AGRO_REFERENCE_TEST_DSN'],autocommit=True) as db:
            self.assertTrue(db.info.host.startswith('/tmp/agro-'))
            self.assertIsNone(db.execute('SELECT inet_server_addr()').fetchone()[0])
            db.execute('SET search_path=pg_temp,public')
            db.execute("SET statement_timeout='20s'")
            for table in ('source_document','ingestion_asset','ingestion_checkpoint','historical_price'):
                db.execute(f'CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)')
            pins=list(alias.SOURCES.values())
            self.assertEqual(len(pins),2)
            for s in pins:
                self.assertIn((s.url,'city-zip',s.parent),queue_plan.PRIORITY_SOURCE_REPAIRS)
                db.execute('''INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,
                  reference_period,content,metadata) VALUES(%s,'Original','DANE',%s,
                  'application/zip','original',%s,''::bytea,%s)''',
                  (s.parent,s.url,s.day,Jsonb({'ingestion_kind':'city-zip','retention':'permanent'})))
                db.execute('''INSERT INTO ingestion_asset(url,kind,observed_on,checked_at,status,
                  processor_version,document_id,records) VALUES(%s,'city-zip',%s,
                  now()-interval '7 hours','complete','city-v5',%s,%s)''',
                  (s.url,s.day,s.parent,s.parent_rows))
            generic='https://www.dane.gov.co/files/operaciones/SIPSA/other-old-city.zip'
            generic_sha='a'*64
            db.execute('''INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,
              reference_period,content,metadata) VALUES(%s,'Other','DANE',%s,
              'application/zip','original','2023-01-01',''::bytea,%s)''',
              (generic_sha,generic,Jsonb({'ingestion_kind':'city-zip'})))
            with db.cursor() as cur:
                with cur.copy('''COPY ingestion_asset(url,kind,observed_on,status,processor_version,
                  document_id) FROM STDIN''') as copy:
                    for i in range(1000):
                        copy.write_row((f'{generic}?backlog={i}','city-zip',None,
                                        'complete','city-v5',generic_sha))
            db.execute('''INSERT INTO ingestion_asset(url,kind,observed_on,checked_at,status,
              processor_version,document_id) VALUES(%s,'city-zip','2023-01-01',
              now()-interval '20 hours','complete','city-v5',%s)''',(generic,generic_sha))
            selected=queue_plan.repair_candidates(db,8)
            self.assertIn(selected[0][0],{s.url for s in pins})
            first=selected[0][0]
            other=next(s.url for s in pins if s.url!=first)
            db.execute('UPDATE ingestion_asset SET processor_version=%s WHERE url=%s',
                       (city_reports.VERSION,first))
            self.assertEqual(queue_plan.repair_candidates(db,8)[0][0],other)
            db.execute('UPDATE ingestion_asset SET processor_version=%s WHERE url=%s',
                       (city_reports.VERSION,other))
            self.assertTrue(queue_plan.repair_candidates(db,8)[0][0].startswith(generic))
            db.execute("UPDATE ingestion_asset SET processor_version='city-v5',checked_at=now()-interval '1 hour' WHERE url=%s",(first,))
            self.assertTrue(queue_plan.repair_candidates(db,8)[0][0].startswith(generic))
            db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '7 hours' WHERE url=%s",(first,))
            self.assertEqual(queue_plan.repair_candidates(db,8)[0][0],first)
            changed='b'*64
            db.execute('''INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,
              reference_period,content,metadata) VALUES(%s,'Changed','DANE',%s,
              'application/zip','original','2025-01-07',''::bytea,%s)''',
              (changed,first,Jsonb({'ingestion_kind':'city-zip'})))
            db.execute('UPDATE ingestion_asset SET document_id=%s WHERE url=%s',(changed,first))
            self.assertTrue(queue_plan.repair_candidates(db,8)[0][0].startswith(generic))

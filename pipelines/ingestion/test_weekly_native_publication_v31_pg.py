"""Actual catalog/quote/review SQL with a full native 2ab original in TEMP PG."""
import hashlib, os, unittest
from pathlib import Path
from unittest.mock import patch
import psycopg
from psycopg.types.json import Jsonb
from . import dane_weekly as NATIVE, official_sources, official_catalog, worker
from .resumable_inputs import WorkDeferred
from .test_official_catalog import install_cache

HERE = Path(__file__).resolve().parent / "testdata"
DOC = {"document_id": "2ab314d876e586aafd8017a50d26762a1a96cbb489a57cc45a51007d63158304", "source_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_09jul_al_15jul_2022.pdf"}
FILE = HERE / "dane_weekly_2022_07_09_native_layout.pdf"

class FullNativePublication(unittest.TestCase):
    def test_full_source_old_identity_withdrawal_and_review_rows(self):
        dsn=os.environ.get('AGRO_REFERENCE_TEST_DSN')
        if not dsn:raise RuntimeError('Explicit private PG socket required')
        db=psycopg.connect(dsn,autocommit=True)
        self.addCleanup(db.close)
        if not str(db.info.host).startswith('/tmp/agro-'):raise RuntimeError('Private PostgreSQL only')
        db.execute("SET search_path=pg_temp; SET statement_timeout='90s'")
        for name in ('source_document','ingestion_asset','official_price_quote','official_source_review','ingestion_checkpoint'):
            db.execute(f'CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING ALL)')
        db.execute('CREATE INDEX quote_identity_private ON official_price_quote(quote_key,observed_on DESC)')
        install_cache(db)
        body=FILE.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(),DOC['document_id'])
        rows=NATIVE.parse_pdf(body,DOC['source_url'])
        self.assertEqual((len(rows),sum(r['price'] is not None for r in rows)),(4828,4225))
        corrected=next(r for r in rows if r['source_locator']=='PDF page 21,table 1,column 1,line 3')
        old={**corrected,'market':'Barranquilla, Barranquillita Bucaramanga, Centroabastos'}
        db.execute('BEGIN')
        try:
            db.execute("INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) VALUES(%s,'DANE weekly','DANE',%s,'application/pdf','original','2022-07-15',%s,%s)",(DOC['document_id'],DOC['source_url'],body,Jsonb({'ingestion_kind':'dane-weekly-pdf'})))
            db.execute("INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,observed_on,checked_at) VALUES(%s,'dane-weekly-pdf','complete','official-v2:dane-weekly-v23',%s,'2022-07-15',now())",(DOC['source_url'],DOC['document_id']))
            with patch.object(worker,'parser_version',return_value='official-v2:dane-weekly-v23'):
                official_sources.publish_rows(db,[old],DOC['document_id'],'dane-weekly-pdf')
            old_key=db.execute("SELECT quote_key FROM official_price_quote WHERE document_id=%s",(DOC['document_id'],)).fetchone()[0]
            self.assertIsNotNone(db.execute("SELECT payload FROM official_catalog_current WHERE quote_key=%s",(old_key,)).fetchone()[0])
            # The fixture stages two historical revisions in one BEGIN. Real
            # retained originals were parsed in separate transactions/days.
            db.execute("UPDATE official_price_quote SET parsed_at=now()-interval '1 minute' WHERE document_id=%s",(DOC['document_id'],))
            with patch.object(worker,'parser_version',return_value='official-v2:dane-weekly-v24'):
                official_sources.publish_rows(db,rows,DOC['document_id'],'dane-weekly-pdf')
                official_sources.publish_rows(db,rows,DOC['document_id'],'dane-weekly-pdf')
            counts=db.execute("SELECT count(*),count(*) FILTER(WHERE parser_version='official-v2:dane-weekly-v23'),count(*) FILTER(WHERE parser_version='official-v2:dane-weekly-v24') FROM official_price_quote WHERE document_id=%s",(DOC['document_id'],)).fetchone()
            self.assertEqual(counts,(4226,1,4225))
            self.assertEqual(db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s",(DOC['document_id'],)).fetchone()[0],603)
            old_cache=db.execute("SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s",(old_key,)).fetchone()
            self.assertEqual(old_cache,(None,False))
            quoted=db.execute("SELECT q.market,q.price,q.min_price,q.max_price,q.source_locator,q.parser_version FROM published_official_price q WHERE q.document_id=%s AND q.source_locator=%s",(DOC['document_id'],corrected['source_locator'])).fetchall()
            self.assertEqual(quoted,[('Bucaramanga, Centroabastos',5750,5500,6000,corrected['source_locator'],'official-v2:dane-weekly-v24')])
            new_key=db.execute("SELECT quote_key FROM official_price_quote WHERE document_id=%s AND source_locator=%s AND parser_version='official-v2:dane-weekly-v24'",(DOC['document_id'],corrected['source_locator'])).fetchone()[0]
            payload,dirty=db.execute("SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s",(new_key,)).fetchone()
            self.assertFalse(dirty);self.assertEqual((payload['market'],float(payload['price'])),('Bucaramanga, Centroabastos',5750))
            self.assertEqual(db.execute("SELECT count(*) FROM published_official_price WHERE document_id=%s AND price=0",(DOC['document_id'],)).fetchone()[0],0)
        finally:db.execute('ROLLBACK')

    def test_committed_first_batch_leaves_old_identity_dirty_then_resumes(self):
        dsn=os.environ.get('AGRO_REFERENCE_TEST_DSN')
        if not dsn:raise RuntimeError('Explicit private PG socket required')
        db=psycopg.connect(dsn,autocommit=True);self.addCleanup(db.close)
        if not str(db.info.host).startswith('/tmp/agro-'):raise RuntimeError('Private PostgreSQL only')
        db.execute("SET search_path=pg_temp; SET statement_timeout='90s'")
        for name in ('source_document','ingestion_asset','official_price_quote','official_source_review','ingestion_checkpoint'):
            db.execute(f'CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING ALL)')
        db.execute('CREATE INDEX quote_identity_private_resume ON official_price_quote(quote_key,observed_on DESC)')
        install_cache(db)
        body=FILE.read_bytes();self.assertEqual(hashlib.sha256(body).hexdigest(),DOC['document_id'])
        rows=NATIVE.parse_pdf(body,DOC['source_url'])
        corrected=next(r for r in rows if r['source_locator']=='PDF page 21,table 1,column 1,line 3')
        subset=[corrected]+[r for r in rows if r['price'] is not None and r['source_locator']!=corrected['source_locator']][:299]
        self.assertEqual(len(subset),300)
        old={**corrected,'market':'Barranquilla, Barranquillita Bucaramanga, Centroabastos'}
        db.execute("INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) VALUES(%s,'DANE weekly','DANE',%s,'application/pdf','original','2022-07-15',%s,%s)",(DOC['document_id'],DOC['source_url'],body,Jsonb({'ingestion_kind':'dane-weekly-pdf'})))
        db.execute("INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,observed_on,checked_at) VALUES(%s,'dane-weekly-pdf','complete','official-v2:dane-weekly-v23',%s,'2022-07-15',now())",(DOC['source_url'],DOC['document_id']))
        with patch.object(worker,'parser_version',return_value='official-v2:dane-weekly-v23'):
            official_sources.publish_rows(db,[old],DOC['document_id'],'dane-weekly-pdf')
        old_key=db.execute("SELECT quote_key FROM official_price_quote WHERE parser_version='official-v2:dane-weekly-v23'").fetchone()[0]
        db.execute("UPDATE official_price_quote SET parsed_at=now()-interval '1 minute' WHERE parser_version='official-v2:dane-weekly-v23'")
        with patch.object(worker,'parser_version',return_value='official-v2:dane-weekly-v24'),patch('pipelines.ingestion.write_pacing.pause_between_batches',side_effect=WorkDeferred('forced after first committed batch')):
            with self.assertRaises(WorkDeferred):official_sources.publish_rows(db,subset,DOC['document_id'],'dane-weekly-pdf')
        self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE parser_version='official-v2:dane-weekly-v24'").fetchone()[0],256)
        self.assertTrue(db.execute("SELECT dirty FROM official_catalog_current WHERE quote_key=%s",(old_key,)).fetchone()[0])
        self.assertEqual(db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE processor_version='official-v2:dane-weekly-v24' AND step='official:complete'").fetchone()[0],0)
        with patch.object(worker,'parser_version',return_value='official-v2:dane-weekly-v24'),patch('pipelines.ingestion.write_pacing.pause_between_batches'),patch.object(official_catalog,'_sleep'):
            official_sources.publish_rows(db,subset,DOC['document_id'],'dane-weekly-pdf')
            official_sources.publish_rows(db,subset,DOC['document_id'],'dane-weekly-pdf')
        self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE parser_version='official-v2:dane-weekly-v24'").fetchone()[0],300)
        self.assertEqual(db.execute("SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s",(old_key,)).fetchone(),(None,False))
        self.assertEqual(db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE processor_version='official-v2:dane-weekly-v24' AND step='official:complete'").fetchone()[0],1)

if __name__=='__main__':unittest.main()

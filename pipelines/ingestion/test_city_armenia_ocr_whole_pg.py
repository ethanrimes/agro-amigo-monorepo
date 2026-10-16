"""Exact Armenia OCR source and worker replay on isolated TEMP PostgreSQL."""
import hashlib
import io
import json
import os
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from psycopg.types.json import Jsonb
from . import city_reports, worker, queue_plan as queue
from . import city_armenia_ocr_proof as proof
from . import city_armenia_ocr_whole as whole
from . import city_exact_source_dispatch_v44_b as dispatch
from . import test_city_publication as publication_tests

FIXTURES = Path(__file__).resolve().parent / 'testdata/city_armenia_20240125_ocr'


@unittest.skipUnless(os.environ.get('AGRO_CITY_POSTGRES_TEST') == '1',
                     'Explicit opt-in for isolated TEMP PostgreSQL city checks')
class ArmeniaOCRWholePostgresTests(unittest.TestCase):
    def setUp(self):
        self.fixture = publication_tests.CityPublicationPostgresTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db = self.fixture.db
        self.assertTrue(self.db.info.host.startswith('/tmp/agro-'))
        self.assertIsNone(self.db.execute('SELECT inet_server_addr()').fetchone()[0])
        for table in ('ingestion_asset', 'source_ocr_task', 'source_ocr_result',
                      'source_ocr_review_history'):
            self.db.execute(f'CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)')
        self.parent = (FIXTURES / (whole.PARENT + '.zip')).read_bytes()
        with zipfile.ZipFile(io.BytesIO(self.parent)) as bundle:
            self.pdf = bundle.read(whole.ENTRY)
        self.images = {p: (FIXTURES / (proof.PAGE[p]['image_id'] + '.png')).read_bytes()
                       for p in (1, 2)}
        for data, digest in [(self.parent,whole.PARENT),(self.pdf,whole.CHILD),
                             *((self.images[p],proof.PAGE[p]['image_id']) for p in (1,2))]:
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
        self.cached = json.loads((FIXTURES / 'cached_four_results.json').read_text())
        self.assertEqual(len(self.cached),4)
        self.db.execute('''INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
          VALUES(%s,%s,'DANE',%s,'application/zip','original',%s,%s,%s)''',
          (whole.PARENT,whole.URL.rsplit('/',1)[-1],whole.URL,whole.DAY.isoformat(),
           self.parent,Jsonb({'ingestion_kind':'city-zip','retention':'permanent',
                             'original_filename':whole.URL.rsplit('/',1)[-1]})))
        self.db.execute('''INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata)
          VALUES(%s,%s,'DANE',%s,'application/pdf','original','Serie histórica completa',2,%s,%s)''',
          (whole.CHILD,whole.ENTRY,whole.URL,self.pdf,
           Jsonb({'ingestion_kind':'city-pdf','retention':'permanent','parents':[whole.PARENT],
                  'archive_entry':whole.ENTRY,'original_filename':whole.ENTRY})))
        self.db.execute('INSERT INTO source_archive_member VALUES(%s,%s,%s)',
                        (whole.PARENT,whole.ENTRY,whole.CHILD))
        self.db.execute('''INSERT INTO ingestion_asset
          (url,kind,observed_on,status,document_id,processor_version,checked_at)
          VALUES(%s,'city-zip',%s,'review',%s,'city-v8',now()-interval '7 hours')''',
          (whole.URL,whole.DAY,whole.PARENT))
        for p in (1,2):
            image_id = proof.PAGE[p]['image_id']
            self.db.execute('''INSERT INTO source_document
              (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
              VALUES(%s,'rendered-source.png','DANE',%s,'image/png','extract',
                'Serie histórica completa',%s,%s)''',
              (image_id,whole.URL,self.images[p],Jsonb({'ingestion_kind':'ocr-image',
               'retention':'permanent','parents':[whole.CHILD],
               'archive_entry':'rendered-source.png','original_filename':'rendered-source.png'})))
            self.db.execute('''INSERT INTO source_ocr_task
              (document_id,source_locator,image_id,source_kind,source_page,status,error)
              VALUES(%s,%s,%s,'city-pdf',%s,'review',%s)''',
              (whole.CHILD,f'PDF page {p}',image_id,p,proof.OLD_ERROR))
        for result in self.cached:
            self.db.execute('''INSERT INTO source_ocr_result(image_id,version,reading,result)
              VALUES(%s,%s,%s,%s)''',
              (result['image_id'],result['version'],result['reading'],Jsonb(result['result'])))
        self.assertEqual(worker.asset_parser_version('city-zip',whole.URL),whole.VERSION)

    def counts(self):
        return {table:self.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                for table in ('regional_price','regional_classification','ingestion_checkpoint',
                              'source_ocr_review_history','source_ocr_task','source_ocr_result')}

    def test_actual_four_bytes_59_full17_append_replay_and_old_review_preserved(self):
        expected = [r['result'] for r in self.cached]
        r = whole.publish_exact_child(self.db,whole.URL,self.parent,whole.PARENT)
        self.assertEqual(r['rows'],59)
        self.assertEqual(r['full17_sha256'],proof.EXPECTED_ROWS_SHA)
        self.assertEqual(self.counts(),{'regional_price':59,'regional_classification':59,
          'ingestion_checkpoint':1,'source_ocr_review_history':2,
          'source_ocr_task':2,'source_ocr_result':4})
        self.assertEqual(self.db.execute('SELECT count(*) FROM published_regional_price WHERE document_id=%s',
                                         (whole.CHILD,)).fetchone()[0],59)
        self.assertEqual(self.db.execute('SELECT DISTINCT status,error FROM source_ocr_task').fetchall(),
                         [('review',proof.OLD_ERROR)])
        self.assertEqual([r[0] for r in self.db.execute('SELECT result FROM source_ocr_result ORDER BY image_id,reading').fetchall()],
                         [r['result'] for r in sorted(self.cached,key=lambda x:(x['image_id'],x['reading']))])
        before=self.counts()
        self.assertEqual(whole.publish_exact_child(self.db,whole.URL,self.parent,whole.PARENT)['rows'],59)
        self.assertEqual(self.counts(),before)

    def test_completed_parent_rechecks_existing_59_and_classifications(self):
        whole.publish_exact_child(self.db,whole.URL,self.parent,whole.PARENT)
        self.db.execute("UPDATE ingestion_asset SET status='complete' WHERE url=%s",(whole.URL,))
        before=self.counts()
        self.assertEqual(whole.publish_exact_child(self.db,whole.URL,self.parent,whole.PARENT)['rows'],59)
        self.assertEqual(self.counts(),before)
        class Undo(Exception): pass
        for sql in (
            "UPDATE regional_price SET min_price=min_price+1 WHERE document_id=%s AND source_locator=(SELECT min(source_locator) FROM regional_price WHERE document_id=%s)",
            "UPDATE regional_classification SET category_path=ARRAY['Wrong']::text[] WHERE document_id=%s AND source_locator=(SELECT min(source_locator) FROM regional_classification WHERE document_id=%s)",
        ):
            try:
                with self.db.transaction():
                    self.db.execute(sql,(whole.CHILD,whole.CHILD))
                    with self.assertRaisesRegex(ValueError,'publication conflict'):
                        whole.publish_exact_child(self.db,whole.URL,self.parent,whole.PARENT)
                    raise Undo()
            except Undo: pass
        try:
            with self.db.transaction():
                self.db.execute('''DELETE FROM source_ocr_review_history
                  WHERE document_id=%s AND source_locator='PDF page 1' ''',(whole.CHILD,))
                with self.assertRaisesRegex(ValueError,'annotation drift'):
                    whole.publish_exact_child(self.db,whole.URL,self.parent,whole.PARENT)
                raise Undo()
        except Undo: pass

    def test_drift_and_partial_source_fail_before_new_publication(self):
        cases=[
          ("UPDATE source_document SET reference_period='2024-01-26' WHERE id=%s",(whole.PARENT,)),
          ("UPDATE source_document SET content=%s WHERE id=%s",(self.pdf,whole.PARENT)),
          ("UPDATE source_document SET metadata='{}'::jsonb WHERE id=%s",(whole.CHILD,)),
          ("UPDATE source_archive_member SET document_id=%s WHERE archive_id=%s AND entry_name=%s",(whole.PARENT,whole.PARENT,whole.ENTRY)),
          ("UPDATE source_ocr_task SET status='pending' WHERE source_page=1",()),
          ("UPDATE source_document SET content='changed'::bytea WHERE id=%s",(proof.PAGE[1]['image_id'],)),
          ("DELETE FROM source_ocr_result WHERE image_id=%s AND reading=1",(proof.PAGE[1]['image_id'],)),
          ("UPDATE source_ocr_result SET result=jsonb_set(result,'{review_notes}','[\"uncertain price\"]'::jsonb) WHERE image_id=%s AND reading=0",(proof.PAGE[1]['image_id'],)),
        ]
        class Undo(Exception): pass
        for sql,args in cases:
            with self.subTest(sql=sql):
                try:
                    with self.db.transaction():
                        self.db.execute(sql,args)
                        before=self.counts()
                        with self.assertRaises((ValueError,KeyError,TypeError)):
                            whole.publish_exact_child(self.db,whole.URL,self.parent,whole.PARENT)
                        self.assertEqual(self.counts(),before)
                        raise Undo()
                except Undo: pass

    def test_after_copy_failure_rolls_back_and_resume(self):
        real=city_reports._bulk_insert
        def fail_after_copy(db,table,values):
            real(db,table,values)
            if table=='regional_price': raise RuntimeError('injected after COPY')
        before=self.counts()
        with patch.object(city_reports,'_bulk_insert',side_effect=fail_after_copy), self.assertRaisesRegex(RuntimeError,'after COPY'):
            whole.publish_exact_child(self.db,whole.URL,self.parent,whole.PARENT)
        self.assertEqual(self.counts(),before)
        self.assertEqual(whole.publish_exact_child(self.db,whole.URL,self.parent,whole.PARENT)['rows'],59)

    def test_retained_dispatch_checkpoints_child_then_leaves_siblings_to_generic(self):
        self.assertEqual(worker.asset_parser_version('city-zip',whole.URL),whole.VERSION)
        self.assertEqual(dispatch.retained_exact_city_zip(self.db,whole.URL,'city-zip',whole.VERSION),self.parent)
        before=self.db.execute('SELECT count(*) FROM source_archive_member WHERE archive_id=%s',(whole.PARENT,)).fetchone()[0]
        self.assertIsNone(dispatch.maybe_publish_exact_city_zip(self.db,whole.URL,self.parent,whole.PARENT))
        self.assertEqual(self.db.execute('SELECT status FROM ingestion_asset WHERE url=%s',(whole.URL,)).fetchone(),('review',))
        self.assertEqual(self.db.execute('SELECT count(*) FROM source_archive_member WHERE archive_id=%s',(whole.PARENT,)).fetchone()[0],before)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s',(whole.PARENT,)).fetchone()[0],1)
        self.assertEqual(dispatch.retained_exact_city_zip(self.db,whole.URL,'city-zip',whole.VERSION),self.parent)
        self.assertIsNone(dispatch.maybe_publish_exact_city_zip(self.db,whole.URL,self.parent,whole.PARENT))

    def test_actual_worker_retained_route_and_exact_queue_cooldown(self):
        # A synthetic prior row tied to a different real ZIP member tests
        # append-only preservation; its price is not asserted as DANE data.
        with zipfile.ZipFile(io.BytesIO(self.parent)) as bundle:
            peer = next(m for m in bundle.infolist() if m.filename != whole.ENTRY)
            peer_bytes = bundle.read(peer)
        peer_id = hashlib.sha256(peer_bytes).hexdigest()
        self.db.execute('''INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
          VALUES(%s,%s,'DANE',%s,'application/pdf','original','Serie histórica completa',%s,%s)''',
          (peer_id,peer.filename,whole.URL,peer_bytes,
           Jsonb({'ingestion_kind':'city-pdf','retention':'permanent','parents':[whole.PARENT],
                  'archive_entry':peer.filename,'original_filename':peer.filename})))
        self.db.execute('INSERT INTO source_archive_member VALUES(%s,%s,%s)',
                        (whole.PARENT,peer.filename,peer_id))
        _,pdf,tasks,cached,_,_=whole.source_rows(self.db,self.parent)
        rows,_=whole.verified_rows(pdf,tasks,cached)
        self.db.execute('''INSERT INTO regional_price VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (peer_id,*rows[0]))
        old_xmin=self.db.execute('''SELECT xmin::text FROM regional_price
          WHERE document_id=%s''',(peer_id,)).fetchone()[0]
        self.assertIn((whole.URL,'city-zip',whole.DAY), queue.repair_candidates(self.db))
        generic_calls=[]
        def pending_generic(db,body,did,url,day,*,processor_version):
            self.assertEqual((body,did,url,day,processor_version),
                             (self.parent,whole.PARENT,whole.URL,whole.DAY,whole.VERSION))
            self.assertEqual(db.execute('''SELECT count(*) FROM regional_price
              WHERE document_id=%s''',(whole.CHILD,)).fetchone()[0],59)
            generic_calls.append('pending')
            raise city_reports.CityZipPartialReview(60,[{
              'filename':peer.filename,'document_id':peer_id,'error_type':'PDFOCRPending',
              'error':'Other member still awaits independent OCR'}])
        with patch.object(worker, 'fetch_asset', side_effect=AssertionError('unexpected source HTTP')), \
             patch('pipelines.ingestion.blob_archive.retain_original_blob', return_value=False), \
             patch.object(city_reports,'publish_city_zip',side_effect=pending_generic):
            self.assertEqual(worker.process_asset(self.db,whole.URL,'city-zip',whole.DAY),60)
        self.assertEqual(generic_calls,['pending'])
        self.assertEqual(self.db.execute('''SELECT status,records,processor_version
          FROM ingestion_asset WHERE url=%s''',(whole.URL,)).fetchone(),
          ('review',60,whole.VERSION))
        self.assertEqual(self.counts()['regional_price'],60)
        self.assertEqual(self.db.execute('''SELECT xmin::text FROM regional_price
          WHERE document_id=%s''',(peer_id,)).fetchone()[0],old_xmin)
        self.assertEqual(self.db.execute('''SELECT count(*) FROM ingestion_checkpoint
          WHERE document_id=%s AND processor_version=%s''',
          (whole.PARENT,whole.VERSION)).fetchone()[0],1)
        self.assertNotIn((whole.URL,'city-zip',whole.DAY), queue.repair_candidates(self.db))
        self.db.execute('''UPDATE ingestion_asset SET status='pending',
          checked_at=now()-interval '7 hours'
          WHERE url=%s''',(whole.URL,))
        self.assertIn((whole.URL,'city-zip',whole.DAY), queue.repair_candidates(self.db))
        self.assertEqual(dispatch.retained_exact_city_zip(self.db,whole.URL,'city-zip',whole.VERSION),
                         self.parent)
        def ready_generic(db,body,did,url,day,*,processor_version):
            self.assertEqual(db.execute('''SELECT count(*) FROM regional_price
              WHERE document_id=%s''',(whole.CHILD,)).fetchone()[0],59)
            generic_calls.append('ready')
            return 60
        with patch.object(worker, 'fetch_asset', side_effect=AssertionError('unexpected source HTTP')), \
             patch('pipelines.ingestion.blob_archive.retain_original_blob', return_value=False), \
             patch.object(city_reports,'publish_city_zip',side_effect=ready_generic):
            self.assertEqual(worker.process_asset(self.db,whole.URL,'city-zip',whole.DAY),60)
        self.assertEqual(generic_calls,['pending','ready'])
        self.assertEqual(self.db.execute('SELECT status,records FROM ingestion_asset WHERE url=%s',
                                         (whole.URL,)).fetchone(),('complete',60))
        self.assertNotIn((whole.URL,'city-zip',whole.DAY), queue.repair_candidates(self.db))

    def test_generic_failure_after_exact_commit_keeps_59_for_resume(self):
        with patch.object(worker,'fetch_asset',side_effect=AssertionError('unexpected HTTP')), \
             patch('pipelines.ingestion.blob_archive.retain_original_blob',return_value=False), \
             patch.object(city_reports,'publish_city_zip',side_effect=RuntimeError('later generic failure')), \
             self.assertRaisesRegex(RuntimeError,'later generic failure'):
            worker.process_asset(self.db,whole.URL,'city-zip',whole.DAY)
        self.assertEqual(self.counts()['regional_price'],59)
        self.assertEqual(self.counts()['ingestion_checkpoint'],1)
        self.assertEqual(self.db.execute('SELECT status FROM ingestion_asset WHERE url=%s',
                                         (whole.URL,)).fetchone(),('review',))
        self.db.execute('''UPDATE ingestion_asset SET status='pending',
          checked_at=now()-interval '7 hours' WHERE url=%s''',(whole.URL,))
        self.assertEqual(self.db.execute('SELECT processor_version FROM ingestion_asset WHERE url=%s',
                                         (whole.URL,)).fetchone(),('city-v8',))
        self.assertIn((whole.URL,'city-zip',whole.DAY),queue.repair_candidates(self.db))
        before=self.counts()
        with patch.object(worker,'fetch_asset',side_effect=AssertionError('unexpected HTTP')), \
             patch('pipelines.ingestion.blob_archive.retain_original_blob',return_value=False), \
             patch.object(city_reports,'publish_city_zip',side_effect=city_reports.CityZipPartialReview(
               59,[{'filename':'other.pdf','error':'still held','error_type':'PDFOCRPending'}])):
            self.assertEqual(worker.process_asset(self.db,whole.URL,'city-zip',whole.DAY),59)
        self.assertEqual(self.counts(),before)

    def test_real_generic_publisher_visits_remaining_actual_29_pdf_members(self):
        with patch.object(worker,'fetch_asset',side_effect=AssertionError('unexpected HTTP')), \
             patch('pipelines.ingestion.blob_archive.retain_original_blob',return_value=False):
            count=worker.process_asset(self.db,whole.URL,'city-zip',whole.DAY)
        self.assertGreaterEqual(count,59)
        self.assertEqual(self.db.execute('''SELECT count(*) FROM source_archive_member
          WHERE archive_id=%s''',(whole.PARENT,)).fetchone()[0],30)
        self.assertEqual(self.db.execute('''SELECT count(*) FROM regional_price
          WHERE document_id=%s''',(whole.CHILD,)).fetchone()[0],59)
        self.assertEqual(self.db.execute('SELECT DISTINCT status,error FROM source_ocr_task WHERE document_id=%s',
                                         (whole.CHILD,)).fetchall(),[('review',proof.OLD_ERROR)])
        self.assertEqual(self.db.execute('''SELECT status,records FROM ingestion_asset WHERE url=%s''',
                                         (whole.URL,)).fetchone(),('review',count))
        completed=self.db.execute('''SELECT count(*) FROM ingestion_checkpoint
          WHERE document_id=%s AND processor_version=%s AND step LIKE 'city-member:%%' ''',
          (whole.PARENT,whole.VERSION)).fetchone()[0]
        self.assertLess(completed,30)
        print('actual-generic-count',count,'archive-members',30,
              'member-checkpoints',completed,'parent-status','review')

    def test_wrong_route_and_conflicting_existing_row_do_not_complete(self):
        for url, parent, sha in [('wrong',self.parent,whole.PARENT),
                                 (whole.URL,b'wrong',whole.PARENT),
                                 (whole.URL,self.parent,'0'*64)]:
            with self.subTest(url=url,sha=sha), self.assertRaises(ValueError):
                whole.publish_exact_child(self.db,url,parent,sha)
        member,pdf,tasks,cached,raw,status=whole.source_rows(self.db,self.parent)
        rows,_=whole.verified_rows(pdf,tasks,cached)
        wrong=list(rows[0]);wrong[11]+=1
        self.db.execute('''INSERT INTO regional_price VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (whole.CHILD,*wrong))
        before=self.counts()
        with self.assertRaisesRegex(ValueError,'partial preexisting source rows'):
            whole.publish_exact_child(self.db,whole.URL,self.parent,whole.PARENT)
        self.assertEqual(self.counts(),before)


if __name__=='__main__': unittest.main()

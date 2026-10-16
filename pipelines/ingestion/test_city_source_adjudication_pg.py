"""Disposable TEMP-PG controls for the source-bound CMA city member."""
import json
import os
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from psycopg import errors, sql
from psycopg.types.json import Jsonb

from pipelines.ingestion import city_reports,worker,queue_plan
from pipelines.ingestion import city_source_adjudication as engine
from pipelines.ingestion import city_source_adjudication_jan2023 as registration
from pipelines.ingestion import city_exact_source_dispatch_v44_b as dispatch
from pipelines.ingestion import test_city_publication as publication_tests

HERE=Path(__file__).resolve().parent
CMA=HERE/'testdata/city_cma_20230103_adjudication'
TEST_ONLY=HERE/'testdata/city_cma_20230103_adjudication_test_only'
CACHE=TEST_ONLY/'cached-readings.json'
IMAGES=TEST_ONLY
PARENT_FILE=TEST_ONLY/'parent-original.zip'

@unittest.skipUnless(os.environ.get('AGRO_CITY_POSTGRES_TEST')=='1','Owned Unix-socket TEMP PostgreSQL opt-in')
class ExactCmaPrivatePg(unittest.TestCase):
    def setUp(self):
        self.fixture=publication_tests.CityPublicationPostgresTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db=self.fixture.db
        self.assertTrue(self.db.info.host.startswith('/tmp/agro-'))
        self.assertIsNone(self.db.execute('SELECT inet_server_addr()').fetchone()[0])
        for table in ('ingestion_asset','source_ocr_task','source_ocr_result'):
            self.db.execute(f'CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)')
        self.db.execute('''CREATE TEMP TABLE city_source_adjudication (
          document_id text,policy_version text,archive_id text,entry_name text,
          evidence_document_id text,full17_sha256 text,records integer,
          source_grid_sha256 text,provider_result_hashes jsonb,prior_tasks jsonb,
          PRIMARY KEY(document_id,policy_version));''')
        self.zip=PARENT_FILE.read_bytes()
        self.spec,self.grid,self.cache,self.member,self.child=engine.checked_private_inputs(
          CMA/'spec.json',CMA/'source-grid.json',CMA/'projection.json',
          CMA/'source-diff.json',CACHE,CMA,self.zip)
        ident=self.spec['source_identity'];self.id=ident['child_sha256_independently_verified_from_local_original']
        self.parent=ident['parent_sha256_from_retained_db_metadata'];self.url=ident['official_url']
        self.db.execute('''INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
          VALUES(%s,%s,'DANE',%s,'application/zip','original',%s,%s,%s)''',
          (self.parent,self.url.rsplit('/',1)[-1],self.url,ident['archive_day'],self.zip,
           Jsonb(dict(ingestion_kind='city-zip',retention='permanent',
                      original_filename=self.url.rsplit('/',1)[-1]))))
        self.db.execute('''INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata)
          VALUES(%s,%s,'DANE',%s,'application/pdf','original','Serie histórica completa',3,%s,%s)''',
          (self.id,ident['archive_member_exact'],self.url,self.child,
           Jsonb(dict(ingestion_kind='city-pdf',retention='permanent',parents=[self.parent],
                      archive_entry=ident['archive_member_exact'],original_filename=ident['archive_member_exact']))))
        self.db.execute('INSERT INTO source_archive_member VALUES(%s,%s,%s)',
                        (self.parent,ident['archive_member_exact'],self.id))
        for sibling in ident['ordered_full_zip_roster']:
            if sibling['entry_name'] != ident['archive_member_exact']:
                self.db.execute('INSERT INTO source_archive_member VALUES(%s,%s,%s)',
                    (self.parent,sibling['entry_name'],sibling['sha256']))
        self.db.execute('''INSERT INTO ingestion_asset(url,kind,observed_on,status,document_id)
          VALUES(%s,'city-zip',%s,'review',%s)''',(self.url,ident['archive_day'],self.parent))
        cached=[x for x in self.cache['rows'] if x['document_id']==self.id]
        self.assertEqual(len(cached),6)
        for p in ident['page_bindings']:
            page=p['page'];image=p['image_id'];img=(IMAGES/f'{image}.png').read_bytes()
            self.assertEqual(engine.digest(img),image)
            self.db.execute('''INSERT INTO source_document
              (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
              VALUES(%s,'rendered-source.png','DANE',%s,'image/png','extract',
                     'Serie histórica completa',%s,%s)''',
              (image,self.url,img,Jsonb(dict(ingestion_kind='ocr-image',retention='permanent',
                parents=[self.id],archive_entry='rendered-source.png',original_filename='rendered-source.png'))))
            self.db.execute('''INSERT INTO source_ocr_task
              (document_id,source_locator,image_id,source_kind,source_page,status,error)
              VALUES(%s,%s,%s,'city-pdf',%s,'review',%s)''',
              (self.id,f'PDF page {page}',image,page,
               'Independent OCR readings disagree or contain uncertainty; not published as prices'))
        for x in cached:
            self.db.execute('''INSERT INTO source_ocr_result(image_id,version,reading,result)
              VALUES(%s,%s,%s,%s)''',(x['image_id'],x['version'],x['reading'],Jsonb(x['result'])))
    def run_publish(self,**kwargs):
        if not kwargs:
            return engine.publish_registered_exact_child(self.db,self.url,self.zip,self.parent,registration.FILES)
        return engine.publish_exact_child(self.db,self.url,self.zip,self.parent,
                                         self.spec,self.grid,self.member,self.child,**kwargs)
    def counts(self):
        return {x:self.db.execute(f'SELECT count(*) FROM {x}').fetchone()[0]
          for x in ('regional_price','regional_classification','ingestion_checkpoint',
                    'source_ocr_result','source_ocr_task','city_source_adjudication')}
    def test_206_full17_class_evidence_checkpoint_replay_sibling_hold(self):
        before_cache=self.db.execute('SELECT image_id,version,reading,result FROM source_ocr_result ORDER BY image_id,reading').fetchall()
        result=self.run_publish();self.assertEqual(result['status'],'published')
        self.assertEqual(self.counts(),dict(regional_price=206,regional_classification=206,
          ingestion_checkpoint=1,source_ocr_result=6,source_ocr_task=3,city_source_adjudication=1))
        rows=engine.verify_source(self.spec,self.grid,[engine._record_from_cache(x) for x in
          self.cache['rows'] if x['document_id']==self.id])
        _,_,details=city_reports._publication_parity(self.db,self.id,rows,require_all=True)
        self.assertEqual(details['difference_count'],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM published_regional_price WHERE document_id=%s',(self.id,)).fetchone()[0],206)
        self.assertEqual(self.db.execute('SELECT image_id,version,reading,result FROM source_ocr_result ORDER BY image_id,reading').fetchall(),before_cache)
        self.assertEqual(self.db.execute('SELECT DISTINCT status,error FROM source_ocr_task').fetchall(),
          [('review','Independent OCR readings disagree or contain uncertainty; not published as prices')])
        self.assertEqual(self.run_publish()['status'],'replay')
        self.assertEqual(self.counts(),dict(regional_price=206,regional_classification=206,
          ingestion_checkpoint=1,source_ocr_result=6,source_ocr_task=3,city_source_adjudication=1))
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',
          (self.spec['source_identity']['distinct_bogota_sibling_zip_metadata']['sha256'],)).fetchone()[0],0)
    def test_money_common_mode_and_exact_projection_fail_closed(self):
        before=self.counts()
        for page,ordinal,key in ((1,12,'r2_max'),(2,19,'r2_max'),(3,12,'r1_max')):
            changed=deepcopy(self.grid)
            changed['pages'][page-1]['rows'][ordinal-1][key]='9.999'
            with self.subTest(page=page,key=key),self.assertRaises(engine.Hold):
                engine.verify_source(self.spec,changed,[engine._record_from_cache(x) for x in
                  self.cache['rows'] if x['document_id']==self.id])
        both=deepcopy([engine._record_from_cache(x) for x in self.cache['rows'] if x['document_id']==self.id])
        for x in both:
            if x['page']==1:
                rows=[r for r in x['result']['tables'][0] if len(r)>=7 and all(r[k] for k in (1,2,3,4,5,6))]
                rows[11][6]='5.200'
        with self.assertRaises(engine.Hold): engine.verify_source(self.spec,self.grid,both)
        self.assertEqual(self.counts(),before)
    def test_parent_roster_child_projection_and_local_image_proof_reject_drift(self):
        with self.assertRaises(engine.Hold):engine.checked_zip(self.zip[:-1]+b'0',self.spec)
        changed=deepcopy(self.spec)
        changed['source_identity']['ordered_full_zip_roster'][1]['crc32']+=1
        with self.assertRaises(engine.Hold):engine.checked_zip(self.zip,changed)
        changed=deepcopy(self.spec)
        changed['full_17_field_projection']['rows'][0]['max_price']='9999'
        cache=[engine._record_from_cache(x) for x in self.cache['rows'] if x['document_id']==self.id]
        with self.assertRaises(engine.Hold):engine.verify_source(changed,self.grid,cache)
        original=IMAGES/self.spec['source_identity']['page_bindings'][0]['image_id']
        self.assertEqual(engine.digest((original.with_suffix('.png')).read_bytes()),
                         self.spec['source_identity']['page_bindings'][0]['image_id'])
    def test_source_identity_mutations_and_partial_checkpoint_fail_closed(self):
        cases=[
          ('UPDATE ingestion_asset SET observed_on=observed_on+1 WHERE url=%s',(self.url,)),
          ("UPDATE ingestion_asset SET kind='daily' WHERE url=%s",(self.url,)),
          ("UPDATE ingestion_asset SET status='archived' WHERE url=%s",(self.url,)),
          ('UPDATE ingestion_asset SET document_id=%s WHERE url=%s',(self.id,self.url)),
          ('UPDATE source_document SET source_url=%s WHERE id=%s',('https://wrong.invalid',self.parent)),
          ("UPDATE source_document SET media_type='application/pdf' WHERE id=%s",(self.parent,)),
          ("UPDATE source_document SET reference_period='2023-01-04' WHERE id=%s",(self.parent,)),
          ("UPDATE source_document SET kind='extract' WHERE id=%s",(self.parent,)),
          ('UPDATE source_document SET content=%s WHERE id=%s',(self.child,self.parent)),
          ('UPDATE source_document SET metadata=\'{}\'::jsonb WHERE id=%s',(self.id,)),
          ("UPDATE source_document SET page_count=2 WHERE id=%s",(self.id,)),
          ("UPDATE source_document SET reference_period='2023-01-03' WHERE id=%s",(self.id,)),
          ('UPDATE source_document SET content=%s WHERE id=%s',(self.zip,self.id)),
          ('UPDATE source_archive_member SET document_id=%s WHERE archive_id=%s AND entry_name=%s',(self.parent,self.parent,self.member.filename)),
          ('DELETE FROM source_archive_member WHERE archive_id=%s AND entry_name=%s',
           (self.parent,self.spec['source_identity']['distinct_bogota_sibling_zip_metadata']['entry_name'])),
          ('UPDATE source_document SET content=\'wrong\'::bytea WHERE id=%s',(self.spec['source_identity']['page_bindings'][0]['image_id'],)),
          ("UPDATE source_document SET media_type='image/jpeg' WHERE id=%s",(self.spec['source_identity']['page_bindings'][0]['image_id'],)),
          ("UPDATE source_document SET metadata='{}'::jsonb WHERE id=%s",(self.spec['source_identity']['page_bindings'][0]['image_id'],)),
          ('UPDATE source_ocr_task SET status=\'pending\' WHERE source_page=1',()),
          ("UPDATE source_ocr_task SET source_kind='daily-pdf' WHERE source_page=1",()),
          ("UPDATE source_ocr_task SET error='other' WHERE source_page=1",()),
          ("UPDATE source_ocr_task SET source_page=4 WHERE source_page=1",()),
          ('DELETE FROM source_ocr_result WHERE image_id=%s AND reading=1',(self.spec['source_identity']['page_bindings'][0]['image_id'],)),
          ("UPDATE source_ocr_result SET version='future-ocr-v3' WHERE image_id=%s AND reading=0",(self.spec['source_identity']['page_bindings'][0]['image_id'],)),
          ("UPDATE source_ocr_result SET result=jsonb_set(result,'{review_notes}','[\"uncertain\"]'::jsonb) WHERE image_id=%s AND reading=0",(self.spec['source_identity']['page_bindings'][0]['image_id'],)),
          ("INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) VALUES(%s,%s,%s,1)",
           (self.parent,engine.VERSION,city_reports._member_step(self.member,engine.date(2023,1,3)))),
        ]
        for sql,args in cases:
            with self.subTest(sql=sql):
                isolated=ExactCmaPrivatePg()
                isolated.setUp()
                try:
                    isolated.db.execute(sql,args)
                    before=isolated.counts()
                    if sql.startswith('INSERT INTO ingestion_checkpoint'):
                        self.assertEqual(isolated.run_publish()['status'],'held')
                        self.assertEqual(isolated.counts()['regional_price'],0)
                        self.assertEqual(isolated.counts()['city_source_adjudication'],0)
                    else:
                        with self.assertRaises(engine.Hold):isolated.run_publish()
                        self.assertEqual(isolated.counts(),before)
                finally:
                    isolated.doCleanups()
    def test_post_copy_crash_rolls_back_then_exact_resume(self):
        before=self.counts();real=city_reports._bulk_insert
        def inject(db,table,values):
            real(db,table,values)
            if table=='regional_price':raise RuntimeError('injected-after-copy')
        with patch.object(city_reports,'_bulk_insert',side_effect=inject),self.assertRaisesRegex(RuntimeError,'injected-after-copy'):
            self.run_publish()
        self.assertEqual(self.counts(),before)
        self.assertEqual(self.run_publish()['status'],'published')
    def test_replay_rejects_price_class_evidence_and_annotation_drift(self):
        self.assertEqual(self.run_publish()['status'],'published')
        cases=[
          ('UPDATE regional_price SET max_price=max_price+1 WHERE document_id=%s AND source_locator=%s',
           (self.id,'PDF page 1,table 1,row 5,round 1')),
          ("UPDATE regional_classification SET category_path=ARRAY['Wrong'] WHERE document_id=%s AND source_locator=%s",
           (self.id,'PDF page 1,table 1,row 5,round 1')),
          ("UPDATE city_source_adjudication SET provider_result_hashes='{}'::jsonb WHERE document_id=%s",(self.id,)),
          ("UPDATE city_source_adjudication SET prior_tasks='[]'::jsonb WHERE document_id=%s",(self.id,)),
          ("UPDATE source_document SET metadata='{}'::jsonb WHERE id=(SELECT evidence_document_id FROM city_source_adjudication WHERE document_id=%s)",(self.id,)),
          ('DELETE FROM regional_price WHERE document_id=%s AND source_locator=%s',
           (self.id,'PDF page 1,table 1,row 5,round 1')),
        ]
        class Rollback(Exception):pass
        for sql,args in cases:
            with self.subTest(sql=sql):
                try:
                    with self.db.transaction():
                        self.db.execute(sql,args)
                        result=self.run_publish()
                        expected_conflict=sql.startswith('UPDATE regional_') or sql.startswith('DELETE FROM regional_')
                        if expected_conflict:
                            self.assertEqual(result['status'],'held')
                        else:
                            self.fail('Expected exact replay hold')
                        raise Rollback()
                except engine.Hold:
                    pass
                except Rollback:
                    pass
        self.assertEqual(self.run_publish()['status'],'replay')
    def test_other_member_checkpoint_does_not_block_eligible_cma(self):
        self.db.execute('''INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records)
          VALUES(%s,%s,'city-member:synthetic-other-sibling',12)''',(self.parent,engine.VERSION))
        self.assertEqual(self.run_publish()['status'],'published')
        self.assertEqual(self.db.execute('SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s',
          (self.parent,)).fetchone()[0],2)
    def test_caller_owned_transaction_rejected_before_any_child_write(self):
        before=self.counts()
        with self.db.transaction():
            with self.assertRaisesRegex(engine.Hold,'caller-owned transaction'):
                self.run_publish()
        self.assertEqual(self.counts(),before)
    def test_ingestor_locks_only_mutable_rows_and_publishes_with_source_select(self):
        schema=self.db.execute('SELECT pg_my_temp_schema()::regnamespace::text').fetchone()[0]
        self.db.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO agro_ingestor').format(sql.Identifier(schema)))
        self.db.execute('GRANT USAGE ON SCHEMA public TO agro_ingestor')
        self.db.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA {} TO agro_ingestor').format(sql.Identifier(schema)))
        self.db.execute('''GRANT INSERT ON source_document,source_archive_member,regional_price,
          regional_classification,ingestion_checkpoint,city_source_adjudication,market,
          product,city_pdf_publication_conflict,city_insert_attempt TO agro_ingestor''')
        self.db.execute('GRANT UPDATE ON ingestion_asset,source_ocr_task TO agro_ingestor')
        for name in ('source_document','source_archive_member'):
            self.assertFalse(self.db.execute('SELECT has_table_privilege(%s,%s,\'UPDATE\')',
                ('agro_ingestor',f'{schema}.{name}')).fetchone()[0])
        originals=self.db.execute('''SELECT id,md5(content),xmin::text FROM source_document
          WHERE id=ANY(%s) ORDER BY id''',([self.parent,self.id,*[x['image_id']
            for x in self.spec['source_identity']['page_bindings']]],)).fetchall()
        self.db.execute('REVOKE UPDATE ON ingestion_asset FROM agro_ingestor')
        self.db.execute('SET ROLE agro_ingestor')
        try:
            with self.assertRaisesRegex(errors.InsufficientPrivilege,'ingestion_asset'):
                with self.db.transaction():
                    engine.read_current_binding(self.db,self.spec,self.zip,self.member,self.child)
        finally:
            self.db.execute('RESET ROLE')
        self.db.execute('GRANT UPDATE ON ingestion_asset TO agro_ingestor')
        self.db.execute('REVOKE UPDATE ON source_ocr_task FROM agro_ingestor')
        self.db.execute('SET ROLE agro_ingestor')
        try:
            with self.assertRaisesRegex(errors.InsufficientPrivilege,'source_ocr_task'):
                with self.db.transaction():
                    engine.read_current_binding(self.db,self.spec,self.zip,self.member,self.child)
        finally:
            self.db.execute('RESET ROLE')
        self.db.execute('GRANT UPDATE ON source_ocr_task TO agro_ingestor')
        self.db.execute('SET ROLE agro_ingestor')
        try:
            def crash(_db):
                raise RuntimeError('controlled child crash')
            with self.assertRaisesRegex(RuntimeError,'controlled child crash'):
                self.run_publish(after_price_hook=crash)
            self.assertEqual(self.counts()['regional_price'],0)
            self.assertEqual(self.counts()['ingestion_checkpoint'],0)
            self.assertEqual(self.run_publish()['status'],'published')
            self.assertEqual(self.run_publish()['status'],'replay')
        finally:
            self.db.execute('RESET ROLE')
        self.assertEqual(self.counts()['regional_price'],206)
        self.assertEqual(self.counts()['regional_classification'],206)
        self.assertEqual(self.counts()['ingestion_checkpoint'],1)
        self.assertEqual(self.db.execute('''SELECT id,md5(content),xmin::text FROM source_document
          WHERE id=ANY(%s) ORDER BY id''',([self.parent,self.id,*[x['image_id']
            for x in self.spec['source_identity']['page_bindings']]],)).fetchall(),originals)
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price WHERE document_id<>%s',
            (self.id,)).fetchone()[0],0)
    def test_registered_retained_and_dispatch_exact_only(self):
        self.assertEqual(registration.retained_exact_parent(self.db,self.url,'city-zip',engine.VERSION),self.zip)
        self.assertIsNone(registration.retained_exact_parent(self.db,self.url,'city-zip','city-v8'))
        self.assertIsNone(registration.maybe_publish(self.db,self.url,self.zip,'f'*64))
        self.assertIsNone(registration.maybe_publish(self.db,self.url,self.zip,self.parent))
    def test_registered_retained_changed_body_fails_before_dispatch(self):
        class Restore(Exception):pass
        for status in ('review','pending','failed','complete'):
            with self.subTest(status=status):
                try:
                    with self.db.transaction():
                        self.db.execute('UPDATE ingestion_asset SET status=%s WHERE url=%s',(status,self.url))
                        self.assertEqual(registration.retained_exact_parent(self.db,self.url,'city-zip',engine.VERSION),self.zip)
                        self.db.execute('UPDATE source_document SET content=%s WHERE id=%s',(self.zip[:-1]+b'0',self.parent))
                        with self.assertRaises(engine.Hold):
                            registration.retained_exact_parent(self.db,self.url,'city-zip',engine.VERSION)
                        raise Restore()
                except Restore:
                    pass
        self.assertEqual(registration.retained_exact_parent(self.db,self.url,'city-zip',engine.VERSION),self.zip)
    def test_packaged_registry_paths_and_imports_publish_exact_child(self):
        release_root='pipelines/ingestion/testdata/city_cma_20230103_adjudication/'
        expected={'spec.json','source-grid.json','projection.json','source-diff.json'}
        expected.update(f'{self.id}-{page}.png' for page in (1,2,3))
        self.assertTrue({release_root+name for name in expected}.issubset(set(worker.RELEASE_FILES)))
        self.assertNotIn('pipelines/ingestion/testdata/city_cma_20230103_adjudication_test_only/parent-original.zip',worker.RELEASE_FILES)
        self.assertNotIn('pipelines/ingestion/testdata/city_cma_20230103_adjudication_test_only/cached-readings.json',worker.RELEASE_FILES)
        self.assertEqual(registration.retained_exact_parent(self.db,self.url,'city-zip',engine.VERSION),self.zip)
        self.assertIsNone(registration.maybe_publish(self.db,self.url,self.zip,self.parent))
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',
            (self.id,)).fetchone()[0],206)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s',
            (self.parent,)).fetchone()[0],1)
    def test_real_central_retained_dispatch_and_queue(self):
        self.assertEqual(worker.asset_parser_version('city-zip',self.url),engine.VERSION)
        self.assertIn((self.url,'city-zip',engine.date(2023,1,3)),queue_plan.repair_candidates(self.db))
        self.assertEqual(dispatch.retained_exact_city_zip(self.db,self.url,'city-zip',engine.VERSION),self.zip)
        class Restore(Exception):pass
        try:
            with self.db.transaction():
                self.db.execute('UPDATE source_document SET content=%s WHERE id=%s',
                    (self.zip[:-1]+b'0',self.parent))
                with self.assertRaises(engine.Hold):
                    dispatch.retained_exact_city_zip(self.db,self.url,'city-zip',engine.VERSION)
                raise Restore()
        except Restore:
            pass
        self.assertIsNone(dispatch.maybe_publish_exact_city_zip(self.db,self.url,self.zip,self.parent))
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',
            (self.id,)).fetchone()[0],206)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s',
            (self.parent,engine.VERSION)).fetchone()[0],1)
        self.assertIsNone(dispatch.maybe_publish_exact_city_zip(self.db,self.url,self.zip,'f'*64))
    def test_exact_checkpoint_skips_only_cma_other_nine_stay_generic_review(self):
        import pipelines.ingestion.pdf_sources as pdf_sources
        self.assertEqual(self.run_publish()['status'],'published')
        visited=[]
        def sibling_parser(db,content,did,day):
            visited.append(did)
            raise ValueError('private test sibling parser reached')
        with patch.object(pdf_sources,'extract_pages',return_value=None),\
             patch.object(city_reports,'parse_archived_city_pdf',side_effect=sibling_parser):
            with self.assertRaises(city_reports.CityZipPartialReview) as cm:
                city_reports.publish_city_zip(self.db,self.zip,self.parent,self.url,
                    engine.date(2023,1,3),processor_version=engine.VERSION)
        self.assertEqual(cm.exception.count,206)
        self.assertEqual(len(cm.exception.failures),9)
        self.assertEqual(len(set(visited)),9)
        self.assertNotIn(self.id,visited)
        self.assertIn(self.spec['source_identity']['distinct_bogota_sibling_zip_metadata']['sha256'],visited)
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',
            (self.id,)).fetchone()[0],206)
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',
            (self.spec['source_identity']['distinct_bogota_sibling_zip_metadata']['sha256'],)).fetchone()[0],0)
        checkpoints=self.db.execute('SELECT step, records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s',
            (self.parent,engine.VERSION)).fetchall()
        self.assertEqual(len(checkpoints),10)
        self.assertEqual(sum(step.startswith('city-member:') and count==206 for step,count in checkpoints),1)
        self.assertEqual(sum(step.startswith('review:') and count==0 for step,count in checkpoints),9)
        self.assertIsNone(registration.maybe_publish(self.db,self.url,self.zip,self.parent))
    def test_prior_wrong_row_creates_durable_conflict_without_new_publication(self):
        rows=engine.verify_source(self.spec,self.grid,[engine._record_from_cache(x) for x in
          self.cache['rows'] if x['document_id']==self.id])
        with self.db.transaction():
            city_reports.save_classifications(self.db,self.id,rows[:1])
            city_reports._bulk_insert(self.db,'regional_price',[(self.id,*rows[0][:12],rows[0][12]+1,*rows[0][13:])])
        result=self.run_publish()
        self.assertEqual(result['status'],'held')
        self.assertEqual(self.db.execute('SELECT count(*) FROM city_pdf_publication_conflict WHERE document_id=%s',(self.id,)).fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s',(self.parent,)).fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',(self.id,)).fetchone()[0],1)
    def test_matching_partial_raw_and_class_cannot_become_checkpoint(self):
        rows=engine.verify_source(self.spec,self.grid,[engine._record_from_cache(x) for x in
          self.cache['rows'] if x['document_id']==self.id])
        with self.db.transaction():
            city_reports.save_classifications(self.db,self.id,rows[:1])
            city_reports._bulk_insert(self.db,'regional_price',[(self.id,*rows[0])])
        with self.assertRaisesRegex(engine.Hold,'partial preexisting source rows'):
            self.run_publish()
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',(self.id,)).fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s',(self.parent,)).fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM city_source_adjudication').fetchone()[0],0)
    def test_post_insert_wrong_row_rolls_back_price_and_records_durable_hold(self):
        # Trigger-like mutation inside the child savepoint changes one attempted row.
        def mutate(db):
            db.execute('UPDATE regional_price SET max_price=max_price+1 WHERE document_id=%s AND source_locator=%s',
                       (self.id,'PDF page 1,table 1,row 5,round 1'))
        result=self.run_publish(after_price_hook=mutate)
        self.assertEqual(result['status'],'held')
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',(self.id,)).fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM city_pdf_publication_conflict WHERE document_id=%s',(self.id,)).fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s',(self.parent,)).fetchone()[0],0)

if __name__=='__main__':unittest.main()

"""Disposable PostgreSQL integration for private OCR scheduler; no provider use."""
import io
import os
import time
import unittest
from unittest.mock import patch
from PIL import Image
import psycopg
from pipelines.ingestion import monthly_pdf_recovery

DSN = os.environ.get("AGRO_REFERENCE_TEST_DSN")
assert DSN and ("host=/tmp/" in DSN or "host=/tmp&" in DSN), (
    "AGRO_REFERENCE_TEST_DSN must use a private Unix socket"
)
from pipelines.ingestion import ocr as m

class OCRPriorityPostgres(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.db=psycopg.connect(DSN,connect_timeout=3,autocommit=True,options='-c statement_timeout=3000 -c timezone=UTC')
  assert cls.db.execute("select current_database()").fetchone()[0]=='postgres'
  cls.db.execute('''CREATE TEMP TABLE source_ocr_task (
   document_id text,source_locator text,image_id text,source_kind text,source_page int,
   status text default 'pending',created_at timestamptz default now(),checked_at timestamptz,error text,
   PRIMARY KEY(document_id,source_locator))''')
  cls.db.execute('''CREATE TEMP TABLE source_ocr_attempt
   (id bigint generated always as identity,image_id text,started_at timestamptz default now())''')
  cls.db.execute('''CREATE TEMP TABLE source_ocr_result
   (image_id text,version text,reading int,result jsonb,
    PRIMARY KEY(image_id,version,reading))''')
  cls.db.execute('''CREATE TEMP TABLE source_document (id text primary key,content bytea,media_type text,metadata jsonb,retrieved_at timestamptz default now())''')
  cls.db.execute('''CREATE TEMP TABLE source_ocr_scan (document_id text,version text)''')
 @classmethod
 def tearDownClass(cls):cls.db.close()
 def setUp(self):self.db.execute('TRUNCATE source_ocr_task,source_ocr_attempt,source_ocr_result,source_document,source_ocr_scan')
 def task(self,did,loc,kind,image=None,minutes_ago=0,status='pending',checked_hours_ago=None):
  self.db.execute('''INSERT INTO source_ocr_task(document_id,source_locator,image_id,source_kind,source_page,status,created_at,checked_at)
   VALUES(%s,%s,%s,%s,1,%s,now()-(%s*interval '1 minute'),CASE WHEN %s::numeric IS NULL THEN NULL ELSE now()-(%s*interval '1 hour') END)''',
   (did,loc,image or did+'-image',kind,status,minutes_ago,checked_hours_ago,checked_hours_ago))
 def attempt(self,image,n=1,old=False):
  for _ in range(n):self.db.execute("INSERT INTO source_ocr_attempt(image_id,started_at) VALUES(%s,CASE WHEN %s THEN (date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')-interval '1 second' ELSE now() END)",(image,old))
 def cache(self,image,readings=2):
  for idx in range(readings):self.db.execute('INSERT INTO source_ocr_result(image_id,version,reading,result) VALUES(%s,%s,%s,%s::jsonb)',(image,m.VERSION,idx,'{"text":"retained"}'))
 def snapshot(self,doc=None,limit=2):return m._priority_snapshot(self.db,40,doc,limit)
 def allowance(self,image,kind,count,city,other,cached_only=False,deadline=None,now=None):
  return m._reading_budget(self.db,image,kind,count,40,city,other,24,16,cached_only,deadline,now=now)
 def image(self,image_id):
  out=io.BytesIO();Image.new('RGB',(3,3),'white').save(out,format='PNG')
  self.db.execute("INSERT INTO source_document(id,content,media_type,metadata) VALUES(%s,%s,'image/png','{}'::jsonb)",(image_id,out.getvalue()))
 def drain_mocked(self,provider=None,**kwargs):
  calls=[]
  def fake_provider(content,**opts):
   calls.append(opts)
   return provider(content,**opts) if provider else {'text':'fixture','tables':[]}
  with patch.object(m,'retire_audited_decorative_pdf_pages',return_value=0), \
       patch.object(m,'requeue_cached_typed_reviews',return_value={'checked':0}), \
       patch.object(m,'compare_typed_task_readings',return_value=False), \
       patch.object(m,'compare_readings',return_value=False), \
       patch.object(m,'_finalize_milk_task',return_value=None), \
       patch.object(m,'retire_native_daily_tasks',return_value={'checked':0}), \
       patch.object(monthly_pdf_recovery,'retire_tasks',return_value={'checked':0}), \
       patch.object(m,'transcribe',side_effect=fake_provider), \
       patch.dict(os.environ,{'GEMINI_API_KEY':'mock-only-no-network'}):
   result=m.drain(self.db,limit=kwargs.pop('limit',2),scan_limit=0,**kwargs)
  return result,calls
 def test_full_drain_both_caps_exhausted_fair_cached_lanes_no_provider(self):
  self.task('city-old','a','city-pdf',image='city1',minutes_ago=30)
  self.task('city-next','a','city-pdf',image='city2',minutes_ago=20)
  self.task('other','a','fixture-pdf',image='other1',minutes_ago=40)
  for image in ('city1','city2','other1'):self.image(image);self.cache(image)
  self.attempt('city1',24);self.attempt('other1',16)
  result,calls=self.drain_mocked(limit=2)
  self.assertEqual(result['processed'],2);self.assertEqual(calls,[])
  self.assertEqual(self.snapshot()[0],40)
  self.assertEqual(self.db.execute("SELECT document_id FROM source_ocr_task WHERE status='review' ORDER BY document_id").fetchall(),[('city-old',),('other',)])
 def test_legacy_day_40_external_zero_city_fair_cached_full_drain(self):
  # A day spent before this policy lands has no global requests left even
  # though the new city lane counter still reads zero.
  self.task('city-uncached','a','city-pdf',image='cu',minutes_ago=60)
  self.task('city-cache-1','a','city-pdf',image='c1',minutes_ago=40)
  self.task('city-cache-2','a','city-pdf',image='c2',minutes_ago=30)
  self.task('other-uncached','a','fixture-pdf',image='ou',minutes_ago=70)
  self.task('other-cache','a','fixture-pdf',image='o1',minutes_ago=20)
  for image in ('cu','c1','c2','ou','o1'):self.image(image)
  for image in ('c1','c2','o1'):self.cache(image)
  self.attempt('ou',40)
  count,city,other,_,_,scheduled=self.snapshot(limit=2)
  self.assertEqual((count,city,other),(40,0,40))
  self.assertEqual([r[0] for r in scheduled],['city-cache-1','other-cache'])
  result,calls=self.drain_mocked(limit=2)
  self.assertEqual(result['processed'],2);self.assertEqual(calls,[])
  self.assertEqual(result['provider_quota'],{
   'global_limit':40,'global_used':40,'city_reserved':24,'city_used':0,
   'other_limit':16,'other_used':40,'selected_city':1,'selected_other':1,
   'cached_only':False,'global_exhausted':True,
  })
  self.assertEqual(self.snapshot()[:3],(40,0,40))
  self.assertEqual(self.db.execute("SELECT document_id FROM source_ocr_task WHERE status='review' ORDER BY document_id").fetchall(),[('city-cache-1',),('other-cache',)])
 def test_exhausted_uncached_backlog_reports_quota_not_empty_backlog(self):
  self.task('city-uncached','a','city-pdf',image='cu')
  self.task('other-uncached','a','fixture-pdf',image='ou')
  self.attempt('ou',40)
  result,calls=self.drain_mocked(limit=2)
  self.assertEqual((result['processed'],result['deferred'],calls),(0,0,[]))
  quota=result['provider_quota']
  self.assertEqual((quota['global_limit'],quota['global_used']), (40,40))
  self.assertEqual((quota['city_reserved'],quota['city_used'],quota['other_limit'],quota['other_used']), (24,0,16,40))
  self.assertEqual((quota['selected_city'],quota['selected_other'],quota['global_exhausted']), (0,0,True))
  self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_task WHERE status='pending'").fetchone()[0],2)
 def test_full_drain_restarts_from_one_cached_reading_with_one_city_slot(self):
  self.task('old','a','city-pdf',image='old',minutes_ago=30)
  self.task('partial','a','city-pdf',image='partial',minutes_ago=1)
  self.image('old');self.image('partial');self.attempt('old',23);self.cache('partial',1)
  result,calls=self.drain_mocked(limit=1)
  self.assertEqual(result['processed'],1);self.assertEqual(len(calls),1)
  self.assertEqual(self.snapshot()[:3],(24,24,0))
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='old'").fetchone()[0],'pending')
  self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_result WHERE image_id='partial'").fetchone()[0],2)
 def test_full_drain_cached_only_restart_needs_no_key_or_provider(self):
  self.task('city','a','city-pdf',image='city-image');self.image('city-image');self.cache('city-image')
  result,calls=self.drain_mocked(document_id='city',cached_only=True,limit=1)
  self.assertEqual(result['processed'],1);self.assertEqual(calls,[])
  self.assertEqual(self.snapshot()[0],0)
 def test_full_drain_restart_after_interrupted_second_read(self):
  self.task('city','a','city-pdf',image='city-image');self.image('city-image')
  calls=[]
  def interrupted(content,**opts):
   calls.append(opts)
   if len(calls)==2:raise RuntimeError('simulated worker process interruption')
   return {'text':'first retained','tables':[]}
  with self.assertRaisesRegex(RuntimeError,'simulated worker'):
   self.drain_mocked(provider=interrupted,limit=1)
  self.assertEqual(len(calls),2)
  self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_result WHERE image_id='city-image'").fetchone()[0],1)
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='city'").fetchone()[0],'pending')
  self.assertEqual(self.snapshot()[:3],(2,2,0))
  result,restarted_calls=self.drain_mocked(limit=1)
  self.assertEqual(result['processed'],1);self.assertEqual(len(restarted_calls),1)
  self.assertEqual(self.snapshot()[:3],(3,3,0))
  self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_result WHERE image_id='city-image'").fetchone()[0],2)
 def test_full_drain_deadline_short_circuits_before_provider(self):
  self.task('city','a','city-pdf',image='city-image');self.image('city-image')
  result,calls=self.drain_mocked(deadline=time.monotonic()+1,limit=1)
  self.assertIn('deferred',result);self.assertEqual(calls,[])
  self.assertEqual(self.snapshot()[0],0)
 def test_real_sql_lanes_priority_and_document_scope(self):
  self.task('pork','a','colombia-pork-pdf',minutes_ago=100)
  self.task('city-new','a','city-pdf',minutes_ago=1)
  self.task('city-old','a','city-pdf',minutes_ago=10)
  count,city,other,cc,oc,rows=self.snapshot(limit=2)
  self.assertEqual((count,city,other,cc,oc),(0,0,0,24,16))
  self.assertEqual([(r[0],r[3]) for r in rows],[('city-old','city-pdf'),('pork','colombia-pork-pdf')])
  self.assertEqual([r[0] for r in self.snapshot(doc='city-new')[5]],['city-new'])
 def test_old_external_attempts_cannot_exhaust_later_city_reserve(self):
  self.task('pork','a','colombia-pork-pdf',image='pork-image',minutes_ago=100)
  self.task('city','a','city-pdf',image='city-image',minutes_ago=1)
  self.attempt('pork-image',16)
  count,city,other,cc,oc,rows=self.snapshot(limit=2)
  self.assertEqual((count,city,other),(16,0,16))
  self.assertEqual(rows[0][0],'city')
  self.assertTrue(self.allowance('city-image','city-pdf',count,city,other)[2])
  self.assertFalse(self.allowance('pork-image','colombia-pork-pdf',count,city,other)[2])
  self.attempt('city-image',2)
  self.assertEqual(self.snapshot()[1:3],(2,16))
 def test_full_quota_cached_zero_cost_and_uncached_deferral(self):
  self.task('city','a','city-pdf',image='city-image')
  self.task('pork','a','colombia-pork-pdf',image='pork-image')
  self.attempt('city-image',24);self.attempt('pork-image',16)
  count,city,other,_,_,rows=self.snapshot()
  self.assertEqual((count,city,other),(40,24,16))
  self.assertEqual(len(rows),0) # Full lanes skip uncached work.
  self.assertFalse(self.allowance('city-image','city-pdf',count,city,other)[2])
  self.assertFalse(self.allowance('pork-image','colombia-pork-pdf',count,city,other)[2])
  self.cache('city-image');self.cache('pork-image')
  self.assertEqual([r[0] for r in self.snapshot()[5]],['city','pork'])
  for image,kind in [('city-image','city-pdf'),('pork-image','colombia-pork-pdf')]:
   cached,missing,allowed=self.allowance(image,kind,count,city,other,cached_only=True)
   self.assertEqual(missing,0);self.assertTrue(allowed)
   self.assertEqual(len([x for x in cached if x is not None]),2)
  self.assertEqual(self.snapshot()[0],40) # No provider attempt inserted by cached budget check.
 def test_one_remaining_city_attempt_selects_partially_cached_task(self):
  self.task('old-uncached','a','city-pdf',image='old-image',minutes_ago=20)
  self.task('new-partial','a','city-pdf',image='new-image',minutes_ago=1)
  self.attempt('old-image',23)
  self.cache('new-image',1)
  count,city,other,_,_,rows=self.snapshot(limit=1)
  self.assertEqual((count,city,other),(23,23,0))
  self.assertEqual([r[0] for r in rows],['new-partial'])
  self.assertTrue(self.allowance('new-image','city-pdf',count,city,other)[2])
  self.assertFalse(self.allowance('old-image','city-pdf',count,city,other)[2])
 def test_cached_only_snapshot_reaches_deep_complete_pair(self):
  self.task('old-uncached','a','city-pdf',image='old-image',minutes_ago=20)
  self.task('new-cached','a','city-pdf',image='new-image',minutes_ago=1)
  self.cache('new-image')
  self.assertEqual([r[0] for r in m._priority_snapshot(self.db,40,None,1,cached_only=True)[5]],['new-cached'])
 def test_cached_only_rejects_one_missing_read(self):
  self.task('city','a','city-pdf',image='city-image');self.cache('city-image',1)
  cached,missing,allowed=self.allowance('city-image','city-pdf',0,0,0,cached_only=True)
  self.assertEqual(missing,1);self.assertFalse(allowed)
  self.assertEqual(self.snapshot()[0],0)
 def test_deadline_uses_two_read_provider_reserve_and_no_read_budget(self):
  self.task('city','a','city-pdf',image='city-image')
  required=sum(m.PROVIDER_TIMEOUT)*2+m.PUBLICATION_RESERVE_SECONDS
  self.assertFalse(self.allowance('city-image','city-pdf',0,0,0,deadline=100+required,now=100)[2])
  self.assertTrue(self.allowance('city-image','city-pdf',0,0,0,deadline=100+required+1,now=100)[2])
  self.cache('city-image')
  self.assertFalse(self.allowance('city-image','city-pdf',0,0,0,deadline=100+m.PUBLICATION_RESERVE_SECONDS,now=100)[2])
  self.assertTrue(self.allowance('city-image','city-pdf',0,0,0,deadline=100+m.PUBLICATION_RESERVE_SECONDS+1,now=100)[2])
 def test_utc_day_rollover_drops_yesterday_attempts(self):
  self.task('city','a','city-pdf',image='city-image')
  self.task('pork','a','colombia-pork-pdf',image='pork-image')
  self.attempt('pork-image',40,old=True);self.attempt('city-image',1)
  self.assertEqual(self.snapshot()[:3],(1,1,0))
  self.assertEqual(self.db.execute("select current_setting('TimeZone')").fetchone()[0],'UTC')
 def test_utc_rollover_independent_of_session_timezone(self):
  self.db.execute("SET TIME ZONE 'America/Los_Angeles'")
  try:
   self.task('city','a','city-pdf',image='city-image')
   self.attempt('city-image',1,old=True)
   self.attempt('city-image',1)
   self.assertEqual(self.snapshot()[:3],(1,1,0))
  finally:self.db.execute("SET TIME ZONE 'UTC'")
 def test_shared_image_is_conservatively_counted_as_city(self):
  self.task('city','a','city-pdf',image='same-image')
  self.task('pork','a','colombia-pork-pdf',image='same-image')
  self.attempt('same-image',2)
  self.assertEqual(self.snapshot()[:3],(2,2,0))
  self.cache('same-image')
  self.assertTrue(self.allowance('same-image','colombia-pork-pdf',2,2,0,cached_only=True)[2])
 def test_later_city_task_does_not_reclassify_prior_external_attempt(self):
  self.task('pork','a','colombia-pork-pdf',image='same-image')
  self.attempt('same-image',2)
  self.assertEqual(self.snapshot()[:3],(2,0,2))
  self.task('city-later','a','city-pdf',image='same-image')
  self.assertEqual(self.snapshot()[:3],(2,0,2))
 def test_status_checked_at_and_lane_limit_are_real_sql_filters(self):
  self.task('city-eligible','a','city-pdf',minutes_ago=5)
  self.task('city-recent','a','city-pdf',minutes_ago=10,checked_hours_ago=1)
  self.task('city-review','a','city-pdf',minutes_ago=20,status='review')
  self.task('pork-eligible','a','colombia-pork-pdf',minutes_ago=30)
  self.assertEqual([r[0] for r in self.snapshot(limit=2)[5]],['city-eligible','pork-eligible'])
  self.assertEqual(len(self.snapshot(limit=1)[5]),1)

if __name__=='__main__':unittest.main(verbosity=2)

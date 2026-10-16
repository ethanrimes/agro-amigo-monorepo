"""Source-derived crash, retention, quarantine and lineage regression fixtures."""
import hashlib,io,json,pathlib,zipfile
from datetime import date
from unittest.mock import patch

import psycopg
from psycopg import sql
from pipelines.ingestion import blob_archive,city_reports,worker
from pipelines.ingestion import city_sep2021_native_v44 as sep
from pipelines.ingestion import city_pereira_20220106_native_b as pereira

HERE=pathlib.Path(__file__).resolve().parent
PKG=HERE
FIX=HERE/'testdata/city_native_recovery'
SEP=FIX/(sep.v43.PARENT_SHA+'.zip')
PEREIRA=FIX/(pereira.PARENT_SHA+'.zip')

def temp_tables(db):
 db.execute('''CREATE TEMP TABLE regional_price(document_id text,source_locator text,observed_on date,
 product_id text,product_name text,market_name text,category text,presentation text,quantity numeric,
 source_unit text,round integer,round_label text,min_price numeric,max_price numeric,unit text,
 min_unit_price numeric,max_unit_price numeric,source_page integer,PRIMARY KEY(document_id,source_locator))''')
 db.execute('CREATE TEMP TABLE regional_classification(document_id text,source_locator text,category_path text[],PRIMARY KEY(document_id,source_locator))')
 db.execute('CREATE TEMP TABLE market(id text PRIMARY KEY,name text,city text,region text,municipality_id text)')
 db.execute('CREATE TEMP TABLE municipality(id text,name text,department text)')
 db.execute('CREATE TEMP TABLE product(id text PRIMARY KEY,name text,category text)')
 db.execute('CREATE TEMP TABLE regional_price_product_correction(document_id text,source_locator text,corrected_product_id text,corrected_product_name text)')
 db.execute('CREATE TEMP TABLE city_pdf_publication_conflict(document_id text,archive_id text,entry_name text,processor_version text,native_sha256 text,stored_sha256 text,details jsonb)')

class RollbackVariant(Exception):pass

def run_fixture(dsn):
 assert hashlib.sha256(pathlib.Path(city_reports.__file__).read_bytes()).hexdigest()=='e492493f04acb1c3179418b2880b4adba5b7d3791b041eaffbdbfaf4b41a2bf0'
 sep_bytes=SEP.read_bytes();per_bytes=PEREIRA.read_bytes()
 assert hashlib.sha256(sep_bytes).hexdigest()==sep.v43.PARENT_SHA
 assert hashlib.sha256(per_bytes).hexdigest()==pereira.PARENT_SHA
 bodies={sep.v43.URL:sep_bytes,pereira.URL:per_bytes}
 fetch_calls=[]
 blobs={}
 def transport(digest,data,suffix,media):
  assert hashlib.sha256(data).hexdigest()==digest
  assert (suffix,media) in (('.pdf','application/pdf'),('.zip','application/zip'))
  assert blobs.setdefault((digest,suffix),bytes(data))==data
  return True
 def source_fetch(db,url,*,force=False):
  assert url in bodies
  fetch_calls.append((url,force))
  return bodies[url]
 def process_as_ingestor(db,url,kind,day):
  db.execute('SET ROLE agro_ingestor')
  try:return worker.process_asset(db,url,kind,day)
  finally:db.execute('RESET ROLE')
 with patch.object(blob_archive,'retain_original_blob',transport),patch.object(worker,'fetch_asset',source_fetch),psycopg.connect(dsn,autocommit=True) as db:
  assert db.info.host.startswith('/'), 'Fixture requires a local Unix socket'
  db.execute("SET statement_timeout='20s'")
  temp_tables(db)
  temp_schema=db.execute('SELECT pg_my_temp_schema()::regnamespace::text').fetchone()[0]
  db.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO agro_ingestor').format(sql.Identifier(temp_schema)))
  db.execute('GRANT USAGE ON SCHEMA public TO agro_ingestor')
  db.execute('GRANT SELECT ON source_document,source_archive_member,ingestion_asset,ingestion_checkpoint,regional_price,regional_classification,market,product,municipality,regional_price_product_correction,city_pdf_publication_conflict TO agro_ingestor')
  db.execute('GRANT INSERT ON source_document,source_archive_member,ingestion_checkpoint,regional_price,regional_classification,market,product,city_pdf_publication_conflict TO agro_ingestor')
  db.execute('GRANT UPDATE ON ingestion_asset TO agro_ingestor')
  worker.queue(db,sep.v43.URL,'city-zip',date(2021,9,1))
  worker.queue(db,pereira.URL,'city-zip',date(2022,1,6))
  # Seed two exact immutable locators: source-local repair may append missing
  # rows, but it must never replace these existing field/class tuples.
  sep_derived=sep.parse_exact_parent(sep.v43.URL,sep_bytes)
  first=sep_derived['children'][0]
  member_manifest=json.loads((PKG/'city_sep2021_members.json').read_text())
  sep_entry=next(x['entry_name'] for x in member_manifest['children'] if x['document_id']==first['child_sha256'])
  with zipfile.ZipFile(io.BytesIO(sep_bytes)) as z: child=z.read(sep_entry)
  sep_parent=worker.archive(db,sep.v43.URL,sep_bytes,'city-zip',date(2021,9,1))
  db.execute("UPDATE ingestion_asset SET document_id=%s,status='review',processor_version='city-v6' WHERE url=%s",(sep_parent,sep.v43.URL))
  sep_did=worker.archive(db,sep.v43.URL,child,'city-pdf',date(2021,9,1),filename=sep_entry,parents=[sep_parent])
  db.execute('INSERT INTO source_archive_member VALUES(%s,%s,%s)',(sep_parent,sep_entry,sep_did))
  r=tuple(first['priced'][0]['fields_17'])
  db.execute('INSERT INTO regional_price VALUES('+','.join(['%s']*18)+')',(sep_did,*r))
  db.execute('INSERT INTO regional_classification VALUES(%s,%s,%s)',(sep_did,r[0],r[5].split(' > ')))
  per_derived=pereira.parse_exact_parent(pereira.URL,per_bytes)
  per_parent=worker.archive(db,pereira.URL,per_bytes,'city-zip',date(2022,1,6))
  db.execute("UPDATE ingestion_asset SET document_id=%s,status='review',records=1435,processor_version='city-v8' WHERE url=%s",(per_parent,pereira.URL))
  per_did=worker.archive(db,pereira.URL,per_derived['child_bytes'],'city-pdf',date(2022,1,6),filename=pereira.ENTRY,parents=[per_parent])
  db.execute('INSERT INTO source_archive_member VALUES(%s,%s,%s)',(per_parent,pereira.ENTRY,per_did))
  for r in per_derived['rows'][:2]:
   db.execute('INSERT INTO regional_price VALUES('+','.join(['%s']*18)+')',(per_did,*r))
   db.execute('INSERT INTO regional_classification VALUES(%s,%s,%s)',(per_did,r[0],r[5].split(' > ')))
  # Reproduce the actual production shape: the unchanged generic city-v8
  # publisher has already completed all other 12 members (1435 rows) and
  # retained only this Pereira child for review.
  try:city_reports.publish_city_zip(db,per_bytes,per_parent,pereira.URL,date(2022,1,6))
  except city_reports.CityZipPartialReview as exc:
   assert exc.count==1435 and len(exc.failures)==1 and exc.failures[0]['document_id']==per_did
  else:raise AssertionError('Generic publisher falsely completed Pereira child')
  sibling_checkpoints=db.execute("SELECT count(*),sum(records) FROM ingestion_checkpoint WHERE document_id=%s AND processor_version='city-v8' AND step LIKE 'city-member:%%'",(per_parent,)).fetchone()
  assert sibling_checkpoints==(12,1435)
  sibling_ids=[x[0] for x in db.execute('SELECT document_id FROM source_archive_member WHERE archive_id=%s AND document_id<>%s ORDER BY document_id',(per_parent,per_did)).fetchall()]
  assert len(sibling_ids)==12
  sibling_before=db.execute('SELECT document_id,source_locator,min_price,max_price,category FROM regional_price WHERE document_id=ANY(%s) ORDER BY document_id,source_locator',(sibling_ids,)).fetchall()
  assert len(sibling_before)==1435
  assert worker.retained_reparse_during_host_cooldown(db,sep.v43.URL,'city-zip')
  assert worker.retained_reparse_during_host_cooldown(db,pereira.URL,'city-zip')
  assert not worker.retained_reparse_during_host_cooldown(db,'https://www.dane.gov.co/other.zip','city-zip')
  try:
   with db.transaction():
    db.execute('UPDATE ingestion_asset SET document_id=%s WHERE url=%s',(per_parent,sep.v43.URL))
    assert not worker.retained_reparse_during_host_cooldown(db,sep.v43.URL,'city-zip')
    raise RollbackVariant()
  except RollbackVariant:pass
  # Exercise the real worker's source dispatch, archive path, status update
  # and exact source-local versions. A controlled later-child crash leaves
  # committed earlier children; the next run resumes without raw replacement.
  old=city_reports._bulk_insert; calls=0
  def crash(db_,table,rows):
   nonlocal calls
   if table=='regional_price':
    calls+=1
    if calls==5:raise RuntimeError('controlled fifth child crash')
   return old(db_,table,rows)
  with patch.object(city_reports,'_bulk_insert',crash):
   try:process_as_ingestor(db,sep.v43.URL,'city-zip',date(2021,9,1))
   except RuntimeError as exc:assert 'fifth child' in str(exc)
   else:raise AssertionError('Fifth-child crash did not occur')
  sep_count='SELECT count(*) FROM regional_price WHERE document_id IN (SELECT document_id FROM source_archive_member WHERE archive_id=%s)'
  partial=db.execute(sep_count,(sep_parent,)).fetchone()[0]
  assert 1<partial<865
  assert process_as_ingestor(db,sep.v43.URL,'city-zip',date(2021,9,1))==865
  assert process_as_ingestor(db,pereira.URL,'city-zip',date(2022,1,6))==104
  assert fetch_calls==[],fetch_calls
  assert db.execute(sep_count,(sep_parent,)).fetchone()[0]==865
  assert db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',(per_did,)).fetchone()[0]==104
  assert db.execute('SELECT count(*) FROM regional_classification').fetchone()[0]==2404
  assert db.execute('SELECT count(*) FROM public.city_native_sep2021_source_v44').fetchone()[0]==11
  assert db.execute('SELECT count(*) FROM public.city_native_sep2021_evidence_v44').fetchone()[0]==712
  assert db.execute('SELECT count(*) FROM public.city_pereira_native_source_private').fetchone()[0]==1
  for url,count,asset_records,version in ((sep.v43.URL,865,865,'city-v8:sep2021-native-geometry-v44-private-v1'),
                            (pereira.URL,104,1539,'city-v8:pereira-20220106-native-category-private-v2')):
   row=db.execute('SELECT status,records,processor_version FROM ingestion_asset WHERE url=%s',(url,)).fetchone()
   assert row==('review',asset_records,version),row
   assert process_as_ingestor(db,url,'city-zip',date(2021,9,1) if count==865 else date(2022,1,6))==count
   assert not worker.retained_reparse_during_host_cooldown(db,url,'city-zip')
  assert db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s AND step LIKE 'city-member:%%'",(sep_parent,)).fetchone()[0]==0
  assert db.execute("SELECT count(*),sum(records) FROM ingestion_checkpoint WHERE document_id=%s AND processor_version='city-v8' AND step LIKE 'city-member:%%'",(per_parent,)).fetchone()==sibling_checkpoints
  assert db.execute('SELECT document_id,source_locator,min_price,max_price,category FROM regional_price WHERE document_id=ANY(%s) ORDER BY document_id,source_locator',(sibling_ids,)).fetchall()==sibling_before
  assert db.execute('SELECT count(*) FROM public.source_document').fetchone()[0]==26
  assert len(blobs)==26
  assert db.execute('SELECT count(*) FROM city_pdf_publication_conflict').fetchone()[0]==0
  # Each failure is rolled back after demonstrating reader exclusion. Product
  # corrections never permit raw typed/source-value drift in this proposal.
  tested=[]
  for did,mode in ((sep_did,'money'),(per_did,'category'),(per_did,'extra')):
   try:
    with db.transaction():
     row=db.execute('SELECT source_locator,min_price FROM regional_price WHERE document_id=%s ORDER BY source_locator LIMIT 1',(did,)).fetchone()
     if mode=='money':db.execute('UPDATE regional_price SET min_price=min_price+1 WHERE document_id=%s AND source_locator=%s',(did,row[0]))
     elif mode=='category':db.execute("UPDATE regional_classification SET category_path=ARRAY['wrong'] WHERE document_id=%s AND source_locator=%s",(did,row[0]))
     else:
      db.execute('INSERT INTO regional_price SELECT document_id,%s,observed_on,product_id,product_name,market_name,category,presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page FROM regional_price WHERE document_id=%s AND source_locator=%s',('source-only-extra-locator',did,row[0]))
      db.execute("INSERT INTO regional_classification VALUES(%s,%s,ARRAY['wrong'])",(did,'source-only-extra-locator'))
     url=sep.v43.URL if did==sep_did else pereira.URL
     try:process_as_ingestor(db,url,'city-zip',date(2021,9,1) if did==sep_did else date(2022,1,6))
     except ValueError:pass
     else:raise AssertionError(mode+' existing source discrepancy accepted')
     assert db.execute('SELECT count(*) FROM city_pdf_publication_conflict WHERE document_id=%s',(did,)).fetchone()[0]>=1
     tested.append(mode)
     raise RollbackVariant()
   except RollbackVariant:pass
  assert tested==['money','category','extra']
  assert db.execute('SELECT count(*) FROM city_pdf_publication_conflict').fetchone()[0]==0
  assert not db.execute("SELECT 1 FROM regional_price WHERE source_locator='source-only-extra-locator'").fetchone()
  # Public-schema source evidence is immutable and reader role cannot write.
  for table in ('city_native_sep2021_source_v44','city_native_sep2021_evidence_v44',
                'city_pereira_native_source_private'):
   grants=db.execute('''SELECT has_table_privilege('agro_reader',%s,'SELECT'),
      has_table_privilege('agro_reader',%s,'INSERT'),
      has_table_privilege('agro_ingestor',%s,'SELECT'),
      has_table_privilege('agro_ingestor',%s,'INSERT'),
      has_table_privilege('agro_ingestor',%s,'UPDATE'),
      has_table_privilege('agro_ingestor',%s,'DELETE')''',
      tuple('public.'+table for _ in range(6))).fetchone()
   assert grants==(True,False,True,True,False,False),(table,grants)
  try:
   with db.transaction():
    db.execute('SET LOCAL ROLE agro_reader')
    db.execute("INSERT INTO public.city_pereira_native_source_private SELECT * FROM public.city_pereira_native_source_private LIMIT 1")
  except psycopg.errors.InsufficientPrivilege:pass
  else:raise AssertionError('Reader role wrote native evidence')
  try:
   with db.transaction():
    db.execute('SET LOCAL ROLE agro_ingestor')
    assert db.execute('SELECT count(*) FROM public.city_pereira_native_source_private').fetchone()[0]==1
    db.execute("DELETE FROM public.city_pereira_native_source_private WHERE false")
  except psycopg.errors.InsufficientPrivilege:pass
  else:raise AssertionError('Ingestor role could delete native evidence')
  out={'actual_worker_process_asset':True,'restricted_ingestor_role_publication':True,'real_archive_blob_bytes':len(blobs),
       'first_recovery_used_exact_retained_bytes_without_http':True,
       'retained_originals':26,'sep_crash_committed_partial':partial,'sep_resumed_typed':865,
       'pereira_existing_matching_two_then_typed':104,'pereira_prior_twelve_typed':1435,
       'pereira_prior_twelve_unchanged':True,'classification_rows':2404,
       'sept_source_attestations':11,'sept_evidence_rows':712,'pereira_source_attestations':1,
       'asset_status_both_review':True,'sep_city_member_complete_markers':0,
       'pereira_old_city_v8_member_markers':12,
       'host_cooldown_exact_local_repair_only':True,
       'wrong_money_category_extra_held':tested,'raw_history_preserved':True,
       'reader_insert_denied':True,'production_writes':0}
  return out

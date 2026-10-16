"""Exact archived category aliases: whole old-v5 state, deadline, sibling and queue replay.

Set AGRO_REFERENCE_TEST_DSN to a disposable /tmp/agro-* Unix PostgreSQL socket.
All source fixtures are repository testdata, not private artifacts or live sites.
"""
import io
import os
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import unittest
import zipfile
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import city_category_alias_checkpoint as alias
from . import city_exact_source_dispatch_v44_b as dispatch
from . import city_reports, queue_plan, worker
from .city_category_overlay import FIELDS

HERE=Path(__file__).resolve().parent
FIX=HERE/'testdata/city_category_alias_exact'
PARENTS={s.child: FIX/(s.parent+'.zip') for s in alias.SOURCES.values()}

def schema(db):
    db.execute('SET search_path=pg_temp,public')
    db.execute("SET statement_timeout='30s'")
    for name in ('source_document','source_archive_member','regional_price','regional_classification',
                 'market','municipality','product','ingestion_checkpoint','ingestion_asset',
                 'city_pdf_publication_conflict','regional_price_product_correction',
                 'ingestion_run','source_host_cooldown'):
        db.execute(f'CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING ALL)')
    db.execute('CREATE TEMP VIEW unresolved_city_pdf_publication_conflict AS SELECT * FROM city_pdf_publication_conflict')
    db.execute('CREATE TEMP TABLE official_source_review(document_id text)')

def local_archive(db,url,body,kind,*unused,filename=None,parents=None,**kwargs):
    did=alias.sha(body)
    media='application/pdf' if kind=='city-pdf' else 'application/zip'
    day=unused[0] if unused else alias.SOURCES[url].day
    original_filename=filename or url.rsplit('/',1)[-1]
    db.execute('''INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,
        reference_period,content,metadata) VALUES(%s,%s,'DANE',%s,%s,'original',%s,%s,%s)
        ON CONFLICT(id) DO NOTHING''',
        (did,filename or kind,url,media,str(day),body,Jsonb({'ingestion_kind':kind,
           'archive_entry':filename,'parents':parents or [],'retention':'permanent',
           'original_filename':original_filename})))
    return did

def seed(db,s,parent):
    local_archive(db,s.url,parent,'city-zip')
    db.execute('''INSERT INTO ingestion_asset(url,kind,observed_on,status,document_id,processor_version,records)
        VALUES(%s,'city-zip',%s,'complete',%s,'city-v5',%s)''',
        (s.url,s.day,s.parent,s.parent_rows))
    target=[];total=0;member_count=0
    with zipfile.ZipFile(io.BytesIO(parent)) as archive:
        for member in archive.infolist():
            if member.is_dir() or not member.filename.lower().endswith('.pdf'):
                continue
            child=archive.read(member)
            did=local_archive(db,s.url,child,'city-pdf',filename=member.filename,parents=[s.parent])
            db.execute('INSERT INTO source_archive_member VALUES(%s,%s,%s)',
                       (s.parent,member.filename,did))
            rows=list(city_reports.parse_city_pdf(child,s.day))
            for native in rows:
                row=list(native)
                if did==s.child and row[0] in s.changed_locators:
                    row[FIELDS.index('category')]=s.old_category
                db.execute('''INSERT INTO regional_price (document_id,source_locator,observed_on,product_id,
                    product_name,market_name,category,presentation,quantity,source_unit,round,round_label,
                    min_price,max_price,unit,min_unit_price,max_unit_price,source_page)
                    VALUES ('''+','.join(['%s']*18)+')',(did,*row))
                db.execute('INSERT INTO regional_classification VALUES(%s,%s,%s)',
                           (did,row[0],row[FIELDS.index('category')].split(' > ')))
            db.execute('INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) VALUES(%s,%s,%s,%s)',
                       (s.parent,'city-v5',city_reports._member_step(member,s.day),len(rows)))
            if did==s.child:target=rows
            total+=len(rows);member_count+=1
    assert len(target)==s.rows and total==s.parent_rows
    return target,total,member_count

def run(s):
    parent=PARENTS[s.child].read_bytes()
    assert alias.sha(parent)==s.parent
    with psycopg.connect(os.environ['AGRO_REFERENCE_TEST_DSN'],autocommit=True) as db:
        assert db.info.host.startswith('/tmp/agro-') and db.execute('SELECT inet_server_addr()').fetchone()[0] is None
        schema(db)
        with zipfile.ZipFile(io.BytesIO(parent)) as archive:
            matches=[m for m in archive.infolist() if m.filename==s.entry]
            assert len(matches)==1 and archive.read(matches[0])==(HERE/'testdata'/(
                'city_arauca_2025_01_07_category_original.pdf' if s.rows==48 else
                'city_tuquerres_20240717_category_original.pdf')).read_bytes()
        old,total_old,member_count_old=seed(db,s,parent)
        old_snapshot=db.execute('''SELECT document_id,source_locator,category,min_price,max_price,xmin::text
            FROM regional_price ORDER BY document_id,source_locator''').fetchall()
        old_classes=db.execute('''SELECT document_id,source_locator,category_path,xmin::text
            FROM regional_classification ORDER BY document_id,source_locator''').fetchall()
        old_checkpoints=db.execute('''SELECT document_id,processor_version,step,records,xmin::text
            FROM ingestion_checkpoint WHERE processor_version='city-v5'
            ORDER BY document_id,step''').fetchall()
        assert dispatch.retained_exact_city_zip(db,s.url,'city-zip',city_reports.VERSION)==parent
        class UndoTamper(Exception):pass
        def retained_rejects(change):
            try:
                with db.transaction():
                    change()
                    try:dispatch.retained_exact_city_zip(db,s.url,'city-zip',city_reports.VERSION)
                    except ValueError:pass
                    else:raise AssertionError('retained route accepted changed source binding')
                    raise UndoTamper()
            except UndoTamper:pass
        retained_rejects(lambda:db.execute('UPDATE ingestion_asset SET records=records-1 WHERE url=%s',(s.url,)))
        retained_rejects(lambda:db.execute('UPDATE ingestion_asset SET observed_on=observed_on+1 WHERE url=%s',(s.url,)))
        retained_rejects(lambda:db.execute('UPDATE source_document SET source_url=%s WHERE id=%s',('https://wrong.example/zip',s.parent)))
        retained_rejects(lambda:db.execute("UPDATE source_document SET metadata=jsonb_set(metadata,'{retention}','\"temporary\"') WHERE id=%s",(s.parent,)))
        retained_rejects(lambda:db.execute('UPDATE source_document SET content=%s WHERE id=%s',(parent+b'x',s.parent)))
        assert dispatch.retained_exact_city_zip(db,s.url,'city-zip',city_reports.VERSION)==parent
        assert dispatch.retained_exact_city_zip(db,s.url,'daily',city_reports.VERSION) is None
        expected_step,expected_proof_step,_=alias.attest_child(db,s,parent)
        locator=old[0][0]
        def proof_rejects(change):
            try:
                with db.transaction():
                    change()
                    try:alias.attest_child(db,s,parent)
                    except alias.Ineligible:pass
                    else:raise AssertionError('whole-child proof accepted changed source tuple')
                    raise UndoTamper()
            except UndoTamper:pass
        proof_rejects(lambda:db.execute('UPDATE regional_price SET max_price=max_price+1 WHERE document_id=%s AND source_locator=%s',(s.child,locator)))
        proof_rejects(lambda:db.execute('UPDATE regional_price SET quantity=quantity+1 WHERE document_id=%s AND source_locator=%s',(s.child,locator)))
        proof_rejects(lambda:db.execute("UPDATE regional_price SET source_locator=source_locator||':tamper' WHERE document_id=%s AND source_locator=%s",(s.child,locator)))
        proof_rejects(lambda:db.execute("UPDATE regional_classification SET category_path=ARRAY['wrong'] WHERE document_id=%s AND source_locator=%s",(s.child,locator)))
        proof_rejects(lambda:db.execute('UPDATE source_document SET content=content||%s WHERE id=%s',(b'x',s.child)))
        real_monotonic=city_reports.time.monotonic
        def member_deadline_clock():
            count=db.execute('''SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s
                AND processor_version=%s AND step LIKE 'city-member:%%' ''',
                (s.parent,city_reports.VERSION)).fetchone()[0]
            deadline=worker.RUN_DEADLINE.get()
            return deadline+1 if count>=3 and deadline is not None else real_monotonic()
        with patch.object(worker,'archive',side_effect=local_archive), \
             patch.object(worker,'fetch_asset',side_effect=AssertionError('retained original must win')), \
             patch('pipelines.ingestion.pdf_sources.extract_pages',return_value=0), \
             patch.object(worker,'connect',return_value=nullcontext(db)), \
             patch('pipelines.ingestion.ocr.drain',return_value={'processed':0}), \
             patch.object(city_reports,'time',SimpleNamespace(monotonic=member_deadline_clock)):
            first=worker.run(mode='backfill',asset_url=s.url,time_budget=300,ocr_limit=0,ocr_scan_limit=0)
        assert not first['errors'],first
        assert len(first['deferred'])==1,first
        assert first['deferred'][0]['url']==s.url,first
        pending=db.execute('''SELECT status,processor_version,records,
            checked_at<=now()-interval '5 hours',error FROM ingestion_asset WHERE url=%s''',
            (s.url,)).fetchone()
        assert pending[0:4]==('pending','city-v5',s.parent_rows,True),pending
        assert 'deferred before' in (pending[4] or '').lower(),pending
        resumed_count=db.execute('''SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s
            AND processor_version=%s AND step LIKE 'city-member:%%' ''',
            (s.parent,city_reports.VERSION)).fetchone()[0]
        assert resumed_count==3,resumed_count
        assert db.execute('''SELECT step,records FROM ingestion_checkpoint WHERE document_id=%s
            AND processor_version=%s AND step=%s''',
            (s.parent,city_reports.VERSION,expected_step)).fetchone()==(expected_step,s.rows)
        assert db.execute('SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step=%s',
                          (s.parent,city_reports.VERSION,expected_proof_step)).fetchone()==(0,)
        assert db.execute('''SELECT document_id,source_locator,category,min_price,max_price,xmin::text
            FROM regional_price ORDER BY document_id,source_locator''').fetchall()==old_snapshot
        assert db.execute('''SELECT document_id,source_locator,category_path,xmin::text
            FROM regional_classification ORDER BY document_id,source_locator''').fetchall()==old_classes
        assert db.execute('''SELECT document_id,processor_version,step,records,xmin::text
            FROM ingestion_checkpoint WHERE processor_version='city-v5'
            ORDER BY document_id,step''').fetchall()==old_checkpoints
        with patch.object(worker,'archive',side_effect=local_archive), \
             patch.object(worker,'fetch_asset',side_effect=AssertionError('retained original must win')), \
             patch('pipelines.ingestion.pdf_sources.extract_pages',return_value=0), \
             patch.object(worker,'connect',return_value=nullcontext(db)), \
             patch('pipelines.ingestion.ocr.drain',return_value={'processed':0}):
            resumed=worker.run(mode='backfill',asset_url=s.url,time_budget=300,ocr_limit=0,ocr_scan_limit=0)
        assert not resumed['errors'] and not resumed['deferred'],resumed
        result=resumed['rows']
        assert db.execute('SELECT status,processor_version,records FROM ingestion_asset WHERE url=%s',
                          (s.url,)).fetchone()==('complete',city_reports.VERSION,s.parent_rows)
        with zipfile.ZipFile(io.BytesIO(parent)) as archive:
            members=[m for m in archive.infolist() if not m.is_dir() and m.filename.lower().endswith('.pdf')]
        cps=db.execute('''SELECT step,records FROM ingestion_checkpoint WHERE document_id=%s
            AND processor_version=%s AND step LIKE 'city-member:%%' ''',(s.parent,city_reports.VERSION)).fetchall()
        assert len(cps)==len(members),(len(cps),len(members))
        assert result==sum(records for _,records in cps),(result,sum(records for _,records in cps))
        assert (expected_step,s.rows) in cps
        assert db.execute('SELECT count(*) FROM city_pdf_publication_conflict').fetchone()==(0,)
        assert db.execute('''SELECT document_id,source_locator,category,min_price,max_price,xmin::text
            FROM regional_price ORDER BY document_id,source_locator''').fetchall()==old_snapshot
        assert db.execute('''SELECT document_id,source_locator,category_path,xmin::text
            FROM regional_classification ORDER BY document_id,source_locator''').fetchall()==old_classes
        assert db.execute('''SELECT document_id,processor_version,step,records,xmin::text
            FROM ingestion_checkpoint WHERE processor_version='city-v5'
            ORDER BY document_id,step''').fetchall()==old_checkpoints
        validated_documents=db.execute('SELECT count(DISTINCT document_id) FROM regional_price WHERE document_id<>%s',(s.child,)).fetchone()[0]
        assert validated_documents==member_count_old-1
        all_before_rerun=db.execute('''SELECT document_id,source_locator,xmin::text FROM regional_price
            ORDER BY document_id,source_locator''').fetchall()
        with patch.object(worker,'archive',side_effect=local_archive), \
             patch.object(worker,'fetch_asset',side_effect=AssertionError('retained original must win')), \
             patch('pipelines.ingestion.pdf_sources.extract_pages',return_value=0):
            rerun_result=worker.process_asset(db,s.url,'city-zip',s.day)
        assert rerun_result==0,rerun_result
        assert db.execute('''SELECT document_id,source_locator,xmin::text FROM regional_price
            ORDER BY document_id,source_locator''').fetchall()==all_before_rerun
        return {'child':s.child,'member_count':len(members),'old_rows':len(old),
               'old_parent_rows':total_old,'old_v5_members':member_count_old,
               'sibling_documents_validated':validated_documents,'total_rows':result,
               'worker_rerun_return':rerun_result,
               'registered_shadow_route':'PASS',
               'deadline_deferred_member_checkpoints':resumed_count,
               'all_member_checkpoints':'PASS','no_conflicts':'PASS','old_xmin':'PASS',
               'full_rerun_idempotence':'PASS'}


@unittest.skipUnless(os.environ.get('AGRO_REFERENCE_TEST_DSN'),
                     'Disposable local PostgreSQL opt-in required')
class ExactCategoryAliasReplayPg(unittest.TestCase):
    def test_arauca_old_parent_deadline_and_siblings(self):
        result=run(next(s for s in alias.SOURCES.values() if s.rows==48))
        self.assertEqual((result['old_parent_rows'],result['member_count']), (1996,28))

    def test_tuquerres_old_parent_deadline_and_siblings(self):
        result=run(next(s for s in alias.SOURCES.values() if s.rows==19))
        self.assertEqual((result['old_parent_rows'],result['member_count']), (1856,30))

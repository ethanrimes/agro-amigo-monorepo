"""Exact-source, per-child city PDF adjudication from retained evidence.

The caller supplies a retained parent ZIP and a pinned source registry. This
module makes no network or OCR-provider calls.
"""
import io
import json
import re
import zipfile
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from psycopg.types.json import Jsonb
from psycopg.pq import TransactionStatus
from pipelines.ingestion import city_reports

VERSION = 'city-v8:jan2023-local-source-adjudication-v1'
FIELDS = ('source_locator','observed_on','product_id','product_name','market_name',
          'category','presentation','quantity','source_unit','round','round_label',
          'min_price','max_price','unit','min_unit_price','max_unit_price','source_page')
NUMERIC = {'quantity','min_price','max_price','min_unit_price','max_unit_price'}
MONEY = ('r1_min','r1_max','r2_min','r2_max')
HEADING_SEQUENCE = {
  1: ['Frutas','Cítricos','Otras frutas'],
  2: ['Tuberculos, raices y platanos','Otros tuberculos','PlÁtano','Papa','Yuca',
      'Verduras y hortalizas','Leguminosas','Otras hortalizas y verduras','Zanahorias','Cebollas'],
  3: ['Tomates','Hortalizas'],
}

class Hold(ValueError):
    """Fail closed before any publication; source/caches stay immutable."""

def require(test, message):
    if not test:
        raise Hold('Exact city source adjudication: ' + message)

def digest(data):
    return sha256(bytes(data)).hexdigest()

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

def canonical_digest(value):
    return digest(canonical(value))

def file_bound(path, expected):
    data = Path(path).read_bytes()
    require(digest(data) == expected, 'private pinned proof file changed')
    return json.loads(data)

def checked_zip(parent_bytes, spec):
    identity = spec['source_identity']
    parent = identity['parent_sha256_from_retained_db_metadata']
    require(len(parent_bytes) == identity['parent_bytes_from_retained_db_metadata']
            and digest(parent_bytes) == parent, 'parent ZIP bytes or size changed')
    try:
        with zipfile.ZipFile(io.BytesIO(parent_bytes)) as archive:
            members = archive.infolist()
            require(len(members) == identity['member_count_in_retained_db_inventory']
                    and len({m.filename for m in members}) == len(members)
                    and all(not m.is_dir() and m.filename.lower().endswith('.pdf') for m in members),
                    'parent ZIP roster changed')
            roster = []
            for member in members:
                require(0 < member.file_size <= 16 * 1024 * 1024, 'unbounded PDF member')
                raw = archive.read(member)  # zipfile validates CRC.
                roster.append(dict(compressed_bytes=member.compress_size, crc32=member.CRC,
                  entry_name=member.filename, header_offset=member.header_offset,
                  sha256=digest(raw), uncompressed_bytes=len(raw)))
            roster_identity=[(r['entry_name'],r['header_offset'],r['crc32'],
                              r['uncompressed_bytes'],r['sha256']) for r in roster]
            require(roster == identity['ordered_full_zip_roster']
                    and digest(json.dumps(roster_identity,ensure_ascii=False,separators=(',',':')).encode())
                    == identity['ordered_full_zip_roster_sha256'], 'full parent member identity changed')
            exact = [m for m in members if m.filename == identity['archive_member_exact']]
            require(len(exact) == 1, 'selected member is not unique')
            member = exact[0]
            child = archive.read(member)
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise Hold('Parent ZIP unreadable') from exc
    require(digest(child) == identity['child_sha256_independently_verified_from_local_original']
            and len(child) == identity['child_bytes'], 'selected PDF bytes changed')
    return member, child

def source_pages(spec, source):
    """Rebuild literal source-image table cells, then invoke ordinary city parser."""
    identity = spec['source_identity']
    require(source['source_pdf_sha256'] == identity['child_sha256_independently_verified_from_local_original']
            and source['product_rows'] == 103 and source['money_cells'] == 412
            and source['blank_or_zero_round_cells'] == 0, 'source-only grid changed')
    heading = '\n'.join(spec['original_printed_headings'][:4])
    header = ['Producto','Presentación','Unidades','Ronda 1\n04:00 - 06:00','',
              'Ronda 2\n06:30 - 08:30','']
    sub = ['','','','Mínimo','Máximo','Mínimo','Máximo']
    expected = spec['full_17_field_projection']['rows']
    categories = {}
    for record in expected:
        m = re.fullmatch(r'PDF page (\d+),table 1,row (\d+),round ([12])',record['source_locator'])
        require(bool(m), 'source locator changed')
        key = (int(m[1]), int(m[2]))
        require(key not in categories or categories[key] == record['category'], 'round category changed')
        categories[key] = record['category']
    pages = []
    previous_category = []
    expected_index = 0
    class Page:
        def __init__(self, table): self.table = table
        def extract_text(self): return heading
        def extract_tables(self): return [self.table]
        def close(self): pass
    for page in source['pages']:
        n = page['page']
        table = [header[:],sub[:]]
        observed_headings = []
        require(len(page['rows']) == identity['page_bindings'][n-1]['source_product_rows'],
                'source page row count changed')
        for row in page['rows']:
            require(row['page'] == n and row['source_row_ordinal'] > 0, 'source row page changed')
            projected = expected[expected_index]
            require(projected['round'] == 1, 'source round ordering changed')
            locator = projected['source_locator']
            match = re.fullmatch(r'PDF page (\d+),table 1,row (\d+),round 1',locator)
            require(match and int(match[1]) == n, 'source page locator changed')
            path = row['printed_category'].split(' > ')
            same = 0
            while same < min(len(path),len(previous_category)) and path[same] == previous_category[same]:
                same += 1
            for component in path[same:]:
                table.append([component,'','','','','',''])
                observed_headings.append(component)
            previous_category = path
            require(len(table) + 1 == int(match[2]), 'heading or product row locator changed')
            values = [row['product'],row['presentation'],row['units']]
            for key in MONEY:
                v = row[key]
                require(isinstance(v,str) and bool(re.fullmatch(r'\d{1,3}(?:\.\d{3})*',v)),
                        'source money cell invalid')
                values.append(v)
            table.append(values)
            expected_index += 2
        require(observed_headings == HEADING_SEQUENCE[n], 'literal category heading sequence changed')
        pages.append(Page(table))
    require(expected_index == 206, 'source product/round count changed')
    return pages, heading

def verify_source(spec, source, cached_rows):
    """Independent numeric grid and exact two-read differences; never trusts agreement."""
    grid = spec['source_independent_numeric_grid']
    flat = [r for page in source['pages'] for r in page['rows']]
    require(len(flat) == len(grid) == 103, 'whole numeric grid length changed')
    for row, witness in zip(flat,grid):
        require(all(row.get(k) == witness.get(k) for k in witness),
                'source-only numeric cell or package differs')
    expected_differences = {
      (x['page'],x['cached_reading'],x['source_row_ordinal'],x['field'],x['cached'],x['source'])
      for x in spec['literal_money_corrections_for_specific_cached_readings']
      + spec['literal_product_or_presentation_differences']
    }
    actual_differences = set()
    seen = set()
    for item in cached_rows:
        page, reading = item['page'], item['reading']
        require((page,reading) not in seen, 'duplicate cached reading')
        seen.add((page,reading))
        table = item['result']['tables'][0]
        rows = [r for r in table if len(r) >= 7 and all(r[k] for k in (1,2,3,4,5,6))]
        page_rows = source['pages'][page-1]['rows']
        require(len(rows) == len(page_rows), 'cached reading product count changed')
        for native, prior in zip(page_rows,rows):
            for col,key in enumerate(('product','presentation','units',*MONEY)):
                if native[key] != prior[col]:
                    actual_differences.add((page,reading,native['source_row_ordinal'],key,prior[col],native[key]))
    require(seen == {(p,r) for p in (1,2,3) for r in (0,1)}, 'missing/extra cached reading')
    require(actual_differences == expected_differences, 'cached reading differences not exact source witness')
    pages, heading = source_pages(spec,source)
    parsed = list(city_reports.parse_city_pages(pages, archive_day=date(2023,1,3), heading=heading))
    require(len(parsed) == 206 and len({r[0] for r in parsed}) == 206,
            'current parser source row count or locators changed')
    expected = spec['full_17_field_projection']
    require(expected['field_order'] == list(FIELDS) and expected['row_count'] == 206,
            '17-field contract changed')
    for tuple_row, record in zip(parsed,expected['rows']):
        require(set(record) == set(FIELDS), '17-field projection schema changed')
        for key, value in zip(FIELDS,tuple_row):
            desired = record[key]
            if key in NUMERIC:
                require((value is None and desired is None) or
                        (value is not None and desired is not None and Decimal(value) == Decimal(desired)),
                        'source 17-field numeric value changed: ' + key)
            elif key == 'observed_on':
                require(value.isoformat() == desired, 'source observed date changed')
            else:
                require(value == desired, 'source 17-field value changed: ' + key)
    return parsed

def checked_registry_inputs(spec_path, grid_path, projection_path, diff_path,
                            rendered_dir, parent_bytes):
    # The registry would carry these SHA pins in tracked, reviewable data.
    require(digest(Path(spec_path).read_bytes()) == 'b943fbcd46fa05e786af30850afa86b047f401f13811f085b37b5123fbb8dcc9',
            'CMA registry spec changed')
    spec = json.loads(Path(spec_path).read_bytes())
    identity = spec['source_identity']
    source = file_bound(grid_path,identity['source_grid_sha256'])
    for page in identity['page_bindings']:
        rendered=Path(rendered_dir) / f"{identity['child_sha256_independently_verified_from_local_original']}-{page['page']}.png"
        require(digest(rendered.read_bytes()) == page['rendered_png_sha256']
                == source['pages'][page['page']-1]['rendered_png_sha256'],
                'independent source-image proof changed')
    projection = file_bound(projection_path,
        spec['full_17_field_projection']['source_grid_projection_sha256'])
    require(projection['rows'] == spec['full_17_field_projection']['rows']
            and projection['source_grid_sha256'] == identity['source_grid_sha256'],
            'full 17-field projection file changed')
    diff = file_bound(diff_path,identity['source_to_cached_diff_sha256'])
    require(diff['source_grid_sha256'] == identity['source_grid_sha256']
            and diff['source_pdf_sha256'] == identity['child_sha256_independently_verified_from_local_original']
            and diff['source_category_heading_sequence'] ==
                {str(k):v for k,v in HEADING_SEQUENCE.items()}
            and diff['source_printed_headings'] == spec['original_printed_headings']
            and diff['source_money_cells'] == 412 and len(diff['reads']) == 6,
            'source comparison witness changed')
    mismatches=[dict(item,cached_reading=read['reading'])
                for read in diff['reads'] for item in read['mismatches']]
    money=[x for x in mismatches if x['field'] in MONEY]
    money.sort(key=lambda x:(x['page'],x['source_row_ordinal'],x['field']))
    literal=[x for x in mismatches if x['field'] not in MONEY]
    headings=[dict(page=read['page'],cached_reading=read['reading'],**x)
              for read in diff['reads'] for x in read['heading_mismatches']]
    require(money == spec['literal_money_corrections_for_specific_cached_readings']
            and literal == spec['literal_product_or_presentation_differences']
            and headings == spec['literal_heading_differences'],
            'source-to-cache correction set changed')
    member, child = checked_zip(parent_bytes,spec)
    return spec,source,member,child

def checked_private_inputs(spec_path, grid_path, projection_path, diff_path,
                           cached_path, rendered_dir, parent_bytes):
    spec,source,member,child=checked_registry_inputs(spec_path,grid_path,projection_path,
        diff_path,rendered_dir,parent_bytes)
    cached=file_bound(cached_path,spec['source_identity']['cached_eight_file_sha256'])
    return spec,source,cached,member,child

def _record_from_cache(x):
    return dict(page=x['source_page'],image_id=x['image_id'],reading=x['reading'],
                version=x['version'],result=x['result'])

def read_current_binding(db,spec,parent_bytes,member,child):
    ident = spec['source_identity']; url=ident['official_url']; parent=ident['parent_sha256_from_retained_db_metadata']
    did=ident['child_sha256_independently_verified_from_local_original']; entry=ident['archive_member_exact']
    a=db.execute('''SELECT a.kind,a.observed_on,a.document_id,a.status,
      d.kind,d.source_url,d.media_type,d.reference_period,d.metadata,d.content
      FROM ingestion_asset a JOIN source_document d ON d.id=a.document_id
      WHERE a.url=%s FOR SHARE OF a''',(url,)).fetchone()
    require(a and (a[0],a[1],a[2],a[4],a[5],a[6],a[7]) ==
            ('city-zip',date.fromisoformat(ident['archive_day']),parent,'original',url,'application/zip',ident['archive_day'])
            and a[3] in ('review','failed','pending','complete'), 'parent asset/source identity changed')
    meta=a[8]
    require(meta.get('ingestion_kind')=='city-zip' and meta.get('retention')=='permanent'
            and meta.get('original_filename')==url.rsplit('/',1)[-1]
            and bytes(a[9])==parent_bytes, 'retained ZIP metadata/bytes changed')
    c=db.execute('''SELECT kind,source_url,media_type,reference_period,page_count,metadata,content
      FROM source_document WHERE id=%s''',(did,)).fetchone()
    require(c and (c[0],c[1],c[2],c[3],c[4]) ==
            ('original',url,'application/pdf','Serie histórica completa',3)
            and c[5].get('ingestion_kind')=='city-pdf' and c[5].get('retention')=='permanent'
            and c[5].get('parents')==[parent] and c[5].get('archive_entry')==entry
            and c[5].get('original_filename')==entry and bytes(c[6])==child,
            'child original identity changed')
    m=db.execute('''SELECT document_id FROM source_archive_member
      WHERE archive_id=%s AND entry_name=%s''',(parent,entry)).fetchone()
    require(m==(did,), 'archive member pointer changed')
    whole_mapping=db.execute('''SELECT entry_name,document_id FROM source_archive_member
      WHERE archive_id=%s ORDER BY entry_name''',(parent,)).fetchall()
    require(whole_mapping == sorted((x['entry_name'],x['sha256'])
            for x in ident['ordered_full_zip_roster']),
            'whole parent archive-member map changed')
    tasks=db.execute('''SELECT t.source_locator,t.image_id,t.source_kind,t.source_page,t.status,t.error,
      d.kind,d.source_url,d.media_type,d.reference_period,d.metadata,d.content
      FROM source_ocr_task t JOIN source_document d ON d.id=t.image_id
      WHERE t.document_id=%s ORDER BY t.source_page FOR UPDATE OF t''',(did,)).fetchall()
    require(len(tasks)==3, 'OCR task count changed')
    cache=[]
    for p,t in enumerate(tasks,1):
        proof=ident['page_bindings'][p-1]; image=proof['image_id']
        require((t[0],t[1],t[2],t[3],t[4],t[5]) ==
                (f'PDF page {p}',image,'city-pdf',p,'review',
                 'Independent OCR readings disagree or contain uncertainty; not published as prices'),
                'OCR task prior state changed')
        require((t[6],t[7],t[8],t[9])==('extract',url,'image/png','Serie histórica completa')
                and t[10].get('ingestion_kind')=='ocr-image' and t[10].get('retention')=='permanent'
                and t[10].get('parents')==[did] and t[10].get('original_filename')=='rendered-source.png'
                and t[10].get('archive_entry')=='rendered-source.png'
                and digest(t[11])==image,
                'page image bytes/metadata changed')
        reads=db.execute('''SELECT image_id,version,reading,result FROM source_ocr_result
          WHERE image_id=%s ORDER BY version,reading''',(image,)).fetchall()
        require(len(reads)==2 and [(r[1],r[2]) for r in reads] ==
                [(x['version'],x['reading']) for x in proof['cached_readings']],
                'cached reading count/version changed')
        for r,expected in zip(reads,proof['cached_readings']):
            require(r[0]==image and canonical_digest(r[3])==expected['private_canonical_result_sha256'],
                    'cached provider result changed')
            cache.append(dict(page=p,image_id=image,reading=r[2],version=r[1],result=r[3]))
    return cache

def checked_evidence_bytes(spec, source, rows, cache):
    # Stored as a derived extract. It is never labeled a provider result or a PDF original.
    evidence=dict(method='independent_original_image_grid_and_two_cached_readings',
                  parent=spec['source_identity']['parent_sha256_from_retained_db_metadata'],
                  child=spec['source_identity']['child_sha256_independently_verified_from_local_original'],
                  source_grid_sha256=spec['source_identity']['source_grid_sha256'],
                  source_projection_sha256=spec['full_17_field_projection']['source_grid_projection_sha256'],
                  source_numeric_grid=spec['source_independent_numeric_grid'],
                  literal_money_corrections=spec['literal_money_corrections_for_specific_cached_readings'],
                  page_images=[x['image_id'] for x in spec['source_identity']['page_bindings']],
                  cached_result_sha256={f"p{x['page']}:r{x['reading']}":canonical_digest(x['result']) for x in cache},
                  full17_rows=spec['full_17_field_projection']['rows'])
    require(len(rows)==206 and len(evidence['full17_rows'])==206,'evidence row count changed')
    return canonical(evidence)

def annotation_payload(spec,cache):
    ident=spec['source_identity']
    hashes={f"p{x['page']}:r{x['reading']}":canonical_digest(x['result']) for x in cache}
    tasks=[dict(page=p['page'],image_id=p['image_id'],source_kind='city-pdf',
                status='review',error='Independent OCR readings disagree or contain uncertainty; not published as prices')
           for p in ident['page_bindings']]
    return hashes,tasks

def _complete_state(db,spec,rows,member,evidence_id,step,cache):
    ident=spec['source_identity']; did=ident['child_sha256_independently_verified_from_local_original']
    parent=ident['parent_sha256_from_retained_db_metadata']
    cp=db.execute('''SELECT records FROM ingestion_checkpoint WHERE document_id=%s
      AND processor_version=%s AND step=%s''',(parent,VERSION,step)).fetchone()
    review=db.execute('''SELECT archive_id,entry_name,evidence_document_id,full17_sha256,records,
      source_grid_sha256,provider_result_hashes,prior_tasks FROM city_source_adjudication
      WHERE document_id=%s AND policy_version=%s''',
      (did,VERSION)).fetchone()
    hashes,tasks=annotation_payload(spec,cache)
    price_count=db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',(did,)).fetchone()[0]
    class_count=db.execute('SELECT count(*) FROM regional_classification WHERE document_id=%s',(did,)).fetchone()[0]
    require(price_count in (0,206) and class_count in (0,206), 'partial preexisting source rows')
    if cp or review or price_count or class_count:
        require(cp==(206,) and review==(parent,ident['archive_member_exact'],evidence_id,
                 canonical_digest(spec['full_17_field_projection']['rows']),
                 206,ident['source_grid_sha256'],hashes,tasks)
                and price_count==class_count==206,
                'checkpoint, evidence, price, or class incomplete')
        _,_,details=city_reports._publication_parity(db,did,rows,require_all=True)
        require(details['difference_count']==0, 'replay row/classification parity changed')
        evidence=db.execute('''SELECT title,publisher,kind,source_url,media_type,
          reference_period,content,metadata FROM source_document
          WHERE id=%s''',(evidence_id,)).fetchone()
        require(evidence and evidence[:6]==('local-source-adjudication.json','DANE',
                'extract',ident['official_url'],'application/json','2023-01-03')
                and digest(evidence[6])==evidence_id and evidence[7]==dict(
                ingestion_kind='city-source-adjudication',retention='permanent',parents=[did],
                original_filename='local-source-adjudication.json'),
                'replay derived evidence changed')
        return True
    return False

def publish_exact_child(db,source_url,parent_bytes,parent_id,spec,source,member,child,*,
                        after_price_hook=None):
    """One-child atomic publication from verified source registry and grid files.

    A conflict marker is committed only in a *separate* transaction after a
    failed insertion savepoint has rolled back. No sibling is affected.
    """
    require(db.autocommit and db.info.transaction_status == TransactionStatus.IDLE,
            'caller-owned transaction would roll back durable conflict marker')
    ident=spec['source_identity']; did=ident['child_sha256_independently_verified_from_local_original']
    require((source_url,parent_id)==(ident['official_url'],ident['parent_sha256_from_retained_db_metadata']),
            'nonexact source route')
    checked_member,checked_child=checked_zip(parent_bytes,spec)
    require((checked_member.filename,checked_member.header_offset,checked_member.CRC)==
            (member.filename,member.header_offset,member.CRC) and checked_child==child,
            'supplied member/source changed')
    step=city_reports._member_step(member,date.fromisoformat(ident['archive_day']))
    # No caller-owned outer transaction: a hold is durable after rollback.
    with db.transaction():
        # Originals, archive mappings, and cached readings are append-only.
        # A single snapshot binds their identity without UPDATE privilege on
        # those immutable tables. Mutable asset/task rows remain row-locked.
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        cache=read_current_binding(db,spec,parent_bytes,member,child)
        rows=verify_source(spec,source,cache)
        evidence_bytes=checked_evidence_bytes(spec,source,rows,cache)
        evidence_id=digest(evidence_bytes)
        cp_present=db.execute('''SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s
          AND processor_version=%s AND step=%s''',(parent_id,VERSION,step)).fetchone() is not None
        # Conflict check precedes the completeness gate, so an old conflicting
        # row produces a durable marker. A partial but matching row still fails
        # the completeness gate without pretending to be a conflict.
        conflict=city_reports._publication_conflict(db,did,rows,VERSION,parent_id,
                    member.filename,require_all=cp_present,native_source=None)
        if conflict:
            outcome=('held',conflict,None)
        else:
            replay=_complete_state(db,spec,rows,member,evidence_id,step,cache)
            if replay:
                outcome=('replay',None,evidence_id)
            else:
                # Other children under this ZIP can have their own checkpoints.
                # Only this exact member step participates in this decision.
                outcome=None
        if outcome is None:
            # Entire child insert, annotation and checkpoint roll back on crash.
            # A post-COPY disagreement is caught below after the savepoint.
            try:
                with db.transaction():
                    city_reports.save_classifications(db,did,rows)
                    city_reports._bulk_insert(db,'regional_price',((did,*r) for r in rows))
                    if after_price_hook: after_price_hook(db)
                    native_hash,stored_hash,details=city_reports._publication_parity(
                        db,did,rows,require_all=True)
                    if details['difference_count']:
                        raise _PostInsertConflict(dict(native_sha256=native_hash,
                            stored_sha256=stored_hash,parity=details))
                    db.execute('''INSERT INTO source_document
                      (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
                      VALUES(%s,'local-source-adjudication.json','DANE',%s,'application/json','extract',
                             '2023-01-03',%s,%s)''',
                      (evidence_id,source_url,evidence_bytes,Jsonb(dict(
                       ingestion_kind='city-source-adjudication',retention='permanent',parents=[did],
                       original_filename='local-source-adjudication.json'))))
                    hashes,tasks=annotation_payload(spec,cache)
                    db.execute('''INSERT INTO city_source_adjudication
                      (document_id,policy_version,archive_id,entry_name,evidence_document_id,
                       full17_sha256,records,source_grid_sha256,provider_result_hashes,prior_tasks)
                      VALUES(%s,%s,%s,%s,%s,%s,206,%s,%s,%s)''',
                      (did,VERSION,parent_id,member.filename,evidence_id,
                       canonical_digest(spec['full_17_field_projection']['rows']),
                       ident['source_grid_sha256'],
                       Jsonb(hashes),Jsonb(tasks)))
                    db.execute('''INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records)
                      VALUES(%s,%s,%s,206)''',(parent_id,VERSION,step))
                    require(db.execute('''SELECT records FROM ingestion_checkpoint WHERE document_id=%s
                      AND processor_version=%s AND step=%s''',(parent_id,VERSION,step)).fetchone()==(206,),
                      'checkpoint did not persist')
                outcome=('published',None,evidence_id)
            except _PostInsertConflict as exc:
                # Savepoint rollback has removed *all* tentative rows. Calling
                # existing conflict helper again now records only old-state
                # discrepancy; if none remains, persist attempted-state details
                # explicitly in a separate transaction after outer rollback.
                outcome=('post_conflict',exc.details,None)
    if outcome[0]=='post_conflict':
        from psycopg.types.json import Jsonb as _Jsonb
        # The failed child savepoint committed nothing. Persist the *attempted*
        # mismatch evidence, not a fabricated old row. A separate transaction
        # ensures the marker survives returning the hold.
        details=outcome[1]
        with db.transaction():
            db.execute('''INSERT INTO city_pdf_publication_conflict
              (document_id,archive_id,entry_name,processor_version,native_sha256,stored_sha256,details)
              VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
              (did,parent_id,member.filename,VERSION,details['native_sha256'],
               details['stored_sha256'],_Jsonb(details['parity'])))
        return dict(status='held',rows=0,reason='post-insert parity conflict',parent=parent_id,child=did)
    if outcome[0]=='held':
        return dict(status='held',rows=0,reason=outcome[1],parent=parent_id,child=did)
    return dict(status=outcome[0],rows=206,parent=parent_id,child=did,
                evidence_document_id=outcome[2],member_step=step,full17_count=206)

class _PostInsertConflict(Exception):
    def __init__(self,details): self.details=details

def publish_registered_exact_child(db, source_url, parent_bytes, parent_id, files):
    """Private integration seam: one eligible child, no sibling loop or OCR calls.

    `files` is a SHA-reviewed registry bundle with spec/grid/projection/diff and
    independently rendered page PNGs. The current candidate bundle has CMA
    only. A future second entry requires its own visual decision and tests.
    """
    spec,source,member,child=checked_registry_inputs(
        files['spec'],files['grid'],files['projection'],files['diff'],
        files['rendered_dir'],parent_bytes)
    return publish_exact_child(db,source_url,parent_bytes,parent_id,
                               spec,source,member,child)

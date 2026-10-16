"""Source-bound Sep 2021 partial publication with immutable native evidence."""
import hashlib
import io
import json
import time
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from psycopg.types.json import Jsonb

from . import city_reports
from .city_sep2021_geo import source_geo
from .city_sep2021_native_v44 import VERSION, parse_exact_parent
from .worker import RUN_DEADLINE
from .resumable_inputs import WorkDeferred
from .city_native_subset_private import checked_missing_rows, hold_subset_conflict


def _archive_exact_child(db, parent_id, url, child, content):
    from .worker import archive

    did = archive(db, url, content, 'city-pdf', date(2021, 9, 1),
                  filename=child['entry_name'], parents=[parent_id])
    if did != child['child_sha256'] or hashlib.sha256(content).hexdigest() != did:
        raise ValueError('Verified source child bytes changed')
    db.execute('INSERT INTO source_archive_member VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',
               (parent_id, child['entry_name'], did))
    if db.execute('SELECT document_id FROM source_archive_member WHERE archive_id=%s AND entry_name=%s',
                  (parent_id,child['entry_name'])).fetchone() != (did,):
        raise ValueError('Source member lineage collision')
    return did


def _register_exact_market(db, did, child):
    literal = child['priced'][0]['fields_17'][4] if child['priced'] else None
    if not literal:
        raise ValueError('Source market missing')
    geo = source_geo(did,literal)
    existing = db.execute('SELECT name,city,region,municipality_id FROM market WHERE id=%s',
                          (geo['literal_market_id'],)).fetchone()
    expected=(literal,geo['city'],geo['region'],geo['municipality_id'])
    if existing is not None and existing != expected:
        raise ValueError('Printed market identity collision')
    if existing is None:
        db.execute('INSERT INTO market(id,name,city,region,municipality_id) VALUES(%s,%s,%s,%s,%s)',
                   (geo['literal_market_id'],*expected))


def _evidence_rows(did,parent,entry,child):
    for state in ('review','noquote','blank'):
        for item in child['reviews' if state=='review' else 'noquotes' if state=='noquote' else 'blanks']:
            rnd=item.get('round')
            locator=(f"PDF page {item['page']},native-y {item['native_y']:.2f},round {rnd}"
                     if rnd else f"PDF page {item['page']},native-y {item['native_y']:.2f},blank")
            reason=','.join(item.get('reasons',[])) if state=='review' else state
            yield (did,parent,entry,locator,VERSION,state,item['page'],rnd,
                   item['native_y'],Jsonb(item['literal_cells']),reason)


def _insert_exact(db,table,columns,values,identity):
    placeholders=','.join(['%s']*len(values))
    db.execute(f'INSERT INTO {table} ({columns}) VALUES({placeholders}) ON CONFLICT DO NOTHING',values)
    # A conflict is only idempotent when every protected field is byte/typed
    # equal. Caller provides the matching primary-key selector.
    old=db.execute(f'SELECT {columns} FROM {table} WHERE {identity[0]}',identity[1]).fetchone()
    expected=tuple(v.obj if isinstance(v,Jsonb) else
                   Decimal(str(v)) if old is not None and isinstance(old[i],Decimal) else v
                   for i,v in enumerate(values))
    if old is None or tuple(old) != expected:
        raise ValueError('Source-local native evidence locator collision')


def publish_exact(db, source_url, parent_bytes, parent_sha256):
    """Return None for every other ZIP, else raise source-backed partial review.

    No city-member completion checkpoint is written while 75 rounds remain
    unresolved. Numeric rows are published child-by-child with immutable
    evidence in the same transaction; crash/retry remains idempotent.
    """
    derived=parse_exact_parent(source_url,parent_bytes)
    if derived is None:return None
    if hashlib.sha256(parent_bytes).hexdigest()!=parent_sha256 or parent_sha256!=derived['parent_sha256']:
        raise ValueError('Exact Sep 2021 parent source changed')
    if db.execute("SELECT to_regclass('public.city_native_sep2021_source_v44')").fetchone()[0] is None:
        raise ValueError('Native source evidence migration missing')
    code_sha=hashlib.sha256(Path(__file__).with_name('city_sep2021_native_v44.py').read_bytes()).hexdigest()
    oracle_sha=hashlib.sha256(Path(__file__).with_name('city_sep2021_v44_pins.json').read_bytes()).hexdigest()
    total=0;failures=[]
    with zipfile.ZipFile(io.BytesIO(parent_bytes)) as bundle:
        for child in derived['children']:
            deadline=RUN_DEADLINE.get()
            if deadline is not None and time.monotonic()>=deadline:
                raise WorkDeferred(f'Sep 2021 native source deferred after {total} committed prices')
            entry=next(c['entry_name'] for c in json.loads(
                Path(__file__).with_name('city_sep2021_members.json').read_text())['children']
                if c['document_id']==child['child_sha256'])
            content=bundle.read(entry)
            did=child['child_sha256']
            rows=[tuple(x['fields_17']) for x in child['priced']]
            if {r[4] for r in rows}!={rows[0][4]}:
                raise ValueError('Printed market changed within source child')
            conflict=None
            with db.transaction():
                db.execute("SELECT pg_advisory_xact_lock(hashtextextended('city-pdf-publication:' || %s,0))",(did,))
                _archive_exact_child(db,parent_sha256,source_url,{'entry_name':entry,**child},content)
                source_values=(parent_sha256,did,entry,VERSION,code_sha,oracle_sha)
                _insert_exact(db,'city_native_sep2021_source_v44',
                  'parent_document_id,document_id,entry_name,parser_version,parser_code_sha256,oracle_sha256',
                  source_values,('document_id=%s AND parser_version=%s',(did,VERSION)))
                for values in _evidence_rows(did,parent_sha256,entry,child):
                    _insert_exact(db,'city_native_sep2021_evidence_v44',
                      'document_id,parent_document_id,entry_name,source_locator,parser_version,state,source_page,source_round,native_y,literal_cells,reason',
                      values,('document_id=%s AND source_locator=%s AND parser_version=%s',(did,values[3],VERSION)))
                if db.execute('SELECT 1 FROM city_pdf_publication_conflict WHERE document_id=%s LIMIT 1',(did,)).fetchone():
                    conflict='Existing city publication conflict remains unresolved'
                else:
                    try: missing=checked_missing_rows(db,did,rows)
                    except ValueError as exc:
                        hold_subset_conflict(db,did,rows,VERSION,parent_sha256,entry,exc)
                        conflict=str(exc)
                if conflict is None:
                    _register_exact_market(db,did,child)
                    city_reports.save_classifications(db,did,rows)
                    city_reports._bulk_insert(db,'regional_price',((did,*r) for r in missing))
                    conflict=city_reports._publication_conflict(db,did,rows,VERSION,parent_sha256,entry,require_all=True)
                    if conflict is not None:
                        raise RuntimeError(conflict)
            if conflict is not None:
                # Commit the immutable conflict evidence first. A later
                # review exception must not roll it back or expose this child.
                raise ValueError(conflict)
            total+=len(rows)
            failures.append({'filename':entry,'document_id':did,
               'error':f"{len(child['reviews'])} native review rounds retained; {len(child['noquotes'])} source noquotes; {len(child['blanks'])} blank products",
               'error_type':'SourceNativeRoundReview'})
    if total!=865 or sum(len(c['reviews']) for c in derived['children'])!=75:
        raise ValueError('Verified source partial-publication count changed')
    raise city_reports.CityZipPartialReview(total,failures)

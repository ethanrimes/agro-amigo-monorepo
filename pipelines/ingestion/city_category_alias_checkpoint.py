"""Source-bound checkpoints for two historical city category spellings.

The generic city parser, overlay, original bytes, prices and classifications
remain unchanged. Only the exact old child receives a reviewed city-v8 member
checkpoint before the ordinary publisher handles every ZIP sibling.
"""
import hashlib
import io
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pipelines.ingestion import city_reports
from pipelines.ingestion.city_category_overlay import FIELDS, digest

PARSER_SHA = 'e492493f04acb1c3179418b2880b4adba5b7d3791b041eaffbdbfaf4b41a2bf0'

@dataclass(frozen=True)
class Source:
    parent: str
    child: str
    url: str
    entry: str
    day: date
    member_size: int
    crc32: int
    rows: int
    parent_rows: int
    native_sha: str
    changed_locators: tuple[str, ...]
    old_category: str
    native_category: str

SOURCES = {
    'https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-7ene2025.zip':
        Source('11123eb2b38ce43b133b076c65542015f27507fbafaa3a8dea10993d7b604c8f',
               'f955e19e02fae8927610bcc104f74bf90121f0f8bea63ee5ac1333fd03ec0737',
               'https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-7ene2025.zip',
               'Arauca (Arauca)-07-01-2025.pdf', date(2025,1,7), 226313,2530840445,48,1996,
               'bcbb79bf2d9e120f62ffc959e4388d9899a791f54d7ce9df22853b3b303a53aa',
               tuple(f'PDF page 1,table 1,row {row},round 1' for row in range(16,32)),
               'Frutas > Otrasfrutas','Frutas > Otras frutas'),
    'https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-17jul2024.zip':
        Source('3910c7199e7c5545863d4f35f8a5d09632f1e4d2ed8aabe8391044724f5a328f',
               'e64e083358cfbc92d541b47e76c2188f4f3888dbf87786ce0bdbea91e5d3e7ab',
               'https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-17jul2024.zip',
               'Túquerres (Nariño)-17-07-2024.pdf', date(2024,7,17),125965,3810289248,19,1856,
               '814190678cd097c803d2747519ebbc41aecdcc7c9aa1bf8377b20daf8742811b',
               ('PDF page 1,table 1,row 16,round 1',),
               'Tuberculos, raices y platanos > Otrostuberculos',
               'Tuberculos, raices y platanos > Otros tuberculos'),
}

class Ineligible(ValueError):
    pass

def require(ok, reason):
    if not ok:
        raise Ineligible(reason)

def sha(body):
    return hashlib.sha256(body).hexdigest()

def _source_rows(db, spec, body):
    parent=db.execute('''SELECT kind,publisher,source_url,media_type,content FROM source_document
        WHERE id=%s''',(spec.parent,)).fetchone()
    child=db.execute('''SELECT kind,publisher,source_url,media_type,metadata,content
        FROM source_document WHERE id=%s''',(spec.child,)).fetchone()
    require(parent is not None and child is not None,'original_source_missing')
    require(parent[:4]==('original','DANE',spec.url,'application/zip') and bytes(parent[4])==body,
            'parent_original_changed')
    require(child[:4]==('original','DANE',spec.url,'application/pdf'),'child_original_owner_changed')
    metadata=child[4]
    require(metadata.get('ingestion_kind')=='city-pdf' and metadata.get('archive_entry')==spec.entry
            and spec.parent in metadata.get('parents',[]),'child_original_metadata_changed')
    require(sha(bytes(child[5]))==spec.child,'child_original_hash_changed')
    member=db.execute('''SELECT document_id FROM source_archive_member
        WHERE archive_id=%s AND entry_name=%s''',(spec.parent,spec.entry)).fetchone()
    require(member==(spec.child,),'archive_member_binding_changed')
    asset=db.execute('''SELECT kind,status,document_id,processor_version,records FROM ingestion_asset
        WHERE url=%s''',(spec.url,)).fetchone()
    require(asset is not None and asset[0]=='city-zip' and asset[1] in ('pending','complete','failed','review')
            and asset[2]==spec.parent and asset[3] in ('city-v5',city_reports.VERSION)
            and asset[4]==spec.parent_rows,'parent_asset_not_eligible')
    rows=db.execute('SELECT '+','.join(FIELDS)+''' FROM regional_price
        WHERE document_id=%s ORDER BY source_locator''',(spec.child,)).fetchall()
    classes=db.execute('''SELECT source_locator,category_path FROM regional_classification
        WHERE document_id=%s ORDER BY source_locator''',(spec.child,)).fetchall()
    require(len(rows)==len(classes)==spec.rows,'old_row_or_class_count_changed')
    require(not db.execute('''SELECT 1 FROM city_pdf_publication_conflict WHERE document_id=%s LIMIT 1''',
                           (spec.child,)).fetchone(),'publication_conflict_present')
    require(not db.execute('''SELECT 1 FROM official_source_review WHERE document_id=%s LIMIT 1''',
                           (spec.child,)).fetchone(),'source_review_present')
    require(not db.execute('''SELECT 1 FROM regional_price_product_correction WHERE document_id=%s LIMIT 1''',
                           (spec.child,)).fetchone(),'product_correction_requires_separate_review')
    return rows,classes,bytes(child[5]),(asset[1],asset[3])

def attest_child(db, spec, parent_bytes):
    """Return exact source/member steps; caller owns the transaction and parent URL."""
    require(city_reports.VERSION=='city-v8' and
            sha(Path(city_reports.__file__).read_bytes())==PARSER_SHA,'generic_parser_fingerprint_changed')
    require(sha(parent_bytes)==spec.parent,'parent_bytes_changed')
    with zipfile.ZipFile(io.BytesIO(parent_bytes)) as z:
        matches=[i for i in z.infolist() if i.filename==spec.entry]
        require(len(matches)==1,'member_missing_or_duplicate')
        member=matches[0]
        require(member.file_size==spec.member_size and member.CRC==spec.crc32,'member_header_changed')
        child_bytes=z.read(member)
    require(len(child_bytes)==spec.member_size and sha(child_bytes)==spec.child,'child_bytes_or_crc_changed')
    native=list(city_reports.parse_city_pdf(child_bytes,spec.day))
    require(len(native)==spec.rows and digest(native)==spec.native_sha,'native_whole_grid_changed')
    rows,classes,stored_child,asset_state=_source_rows(db,spec,parent_bytes)
    require(stored_child==child_bytes,'retained_child_bytes_changed')
    native_map={row[0]:row for row in native}
    old_map={row[0]:row for row in rows}
    class_map=dict(classes)
    require(len(native_map)==len(old_map)==len(class_map)==spec.rows and
            set(native_map)==set(old_map)==set(class_map),'full_locator_set_changed')
    changed=[]
    category_index=FIELDS.index('category')
    for locator in sorted(native_map):
        want=tuple(native_map[locator]);got=tuple(old_map[locator])
        for field,left,right in zip(FIELDS,want,got):
            if left==right:continue
            require(field=='category' and locator in spec.changed_locators and
                    left==spec.native_category and right==spec.old_category,
                    'nonreviewed_raw_field_changed')
            changed.append(locator)
        expected_path=got[category_index].split(' > ')
        require(class_map[locator]==expected_path,'old_classification_path_changed')
    require(tuple(sorted(changed))==tuple(sorted(spec.changed_locators)),
            'category_alias_locator_set_changed')
    step=city_reports._member_step(member,spec.day)
    proof=digest((spec.parent,spec.child,spec.url,spec.entry,member.header_offset,
                  member.CRC,member.file_size,spec.day,PARSER_SHA,
                  [(loc,native_map[loc],old_map[loc],class_map[loc]) for loc in sorted(native_map)]))
    proof_step='city-category-alias-proof:'+spec.child+':'+proof
    return step,proof_step,asset_state

def checkpoint_exact_aliases(db, url, parent_bytes, parent_sha):
    """Checkpoint one exact old child; generic ZIP publisher handles all siblings."""
    spec=SOURCES.get(url)
    if spec is None:
        return None
    require(parent_sha==spec.parent,'requested_parent_sha_changed')
    with db.transaction():
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended('city-pdf-publication:' || %s,0))",
                   (spec.child,))
        step,proof_step,(asset_status,asset_version)=attest_child(db,spec,parent_bytes)
        existing=db.execute('''SELECT step,records FROM ingestion_checkpoint WHERE document_id=%s
            AND processor_version=%s AND (step=%s OR step LIKE %s)
            ORDER BY step''',(spec.parent,city_reports.VERSION,step,'city-category-alias-proof:'+spec.child+':%')).fetchall()
        if existing:
            require(dict(existing)=={step:spec.rows,proof_step:0},'existing_alias_checkpoint_changed')
        else:
            require(asset_status in ('complete','pending') and asset_version=='city-v5',
                    'first_alias_checkpoint_asset_not_eligible')
            db.execute('''INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records)
                VALUES(%s,%s,%s,%s),(%s,%s,%s,0)''',
                (spec.parent,city_reports.VERSION,step,spec.rows,
                 spec.parent,city_reports.VERSION,proof_step))
    return {'child':spec.child,'rows':spec.rows,'member_step':step,'proof_step':proof_step}

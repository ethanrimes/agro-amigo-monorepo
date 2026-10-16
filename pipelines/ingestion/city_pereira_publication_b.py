"""Publish one source-verified Pereira PDF while retaining whole-ZIP review."""
import hashlib
from datetime import date
from pathlib import Path

from . import city_reports
from .city_pereira_20220106_native_b import (
    CHILD_SHA, DAY, ENTRY, PARENT_SHA, URL, VERSION, parse_exact_parent,
)
from .city_native_subset_private import checked_missing_rows, hold_subset_conflict


def publish_exact_child(db, source_url, parent_bytes, parent_sha256):
    from .worker import archive

    parsed = parse_exact_parent(source_url, parent_bytes)
    if parsed is None:
        return None
    if parent_sha256 != PARENT_SHA or hashlib.sha256(parent_bytes).hexdigest() != PARENT_SHA:
        raise ValueError('Pereira parent byte identity differs')
    if db.execute("SELECT to_regclass('public.city_pereira_native_source_private')").fetchone()[0] is None:
        raise ValueError('Pereira evidence migration missing')
    rows = parsed['rows']
    code_sha = hashlib.sha256(Path(__file__).with_name('city_pereira_20220106_native_b.py').read_bytes()).hexdigest()
    with db.transaction():
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended('city-pdf-publication:' || %s,0))", (CHILD_SHA,))
        did = archive(db, URL, parsed['child_bytes'], 'city-pdf', DAY,
                      filename=ENTRY, parents=[PARENT_SHA])
        if did != CHILD_SHA:
            raise ValueError('Pereira archived PDF byte identity differs')
        db.execute('INSERT INTO source_archive_member VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',
                   (PARENT_SHA, ENTRY, CHILD_SHA))
        if db.execute('SELECT document_id FROM source_archive_member WHERE archive_id=%s AND entry_name=%s',
                      (PARENT_SHA, ENTRY)).fetchone() != (CHILD_SHA,):
            raise ValueError('Pereira archive lineage differs')
        db.execute('''INSERT INTO public.city_pereira_native_source_private
          (parent_document_id,document_id,entry_name,parser_version,parser_code_sha256,oracle_sha256)
          VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
          (PARENT_SHA,CHILD_SHA,ENTRY,VERSION,code_sha,parsed['independent_oracle_sha256']))
        evidence = db.execute('''SELECT parent_document_id,entry_name,parser_code_sha256,oracle_sha256
          FROM public.city_pereira_native_source_private WHERE document_id=%s AND parser_version=%s''',
          (CHILD_SHA,VERSION)).fetchone()
        if evidence != (PARENT_SHA,ENTRY,code_sha,parsed['independent_oracle_sha256']):
            raise ValueError('Pereira immutable evidence collision')
        if db.execute('SELECT 1 FROM city_pdf_publication_conflict WHERE document_id=%s LIMIT 1',(CHILD_SHA,)).fetchone():
            conflict='Existing city publication conflict remains unresolved'
        else:
            try: missing=checked_missing_rows(db,CHILD_SHA,rows)
            except ValueError as exc:
                hold_subset_conflict(db,CHILD_SHA,rows,VERSION,PARENT_SHA,ENTRY,exc)
                conflict=str(exc)
            else: conflict=None
        if conflict is None:
            city_reports.save_classifications(db,CHILD_SHA,rows)
            city_reports._bulk_insert(db,'regional_price',((CHILD_SHA,*r) for r in missing))
            conflict = city_reports._publication_conflict(
                db,CHILD_SHA,rows,VERSION,PARENT_SHA,ENTRY,require_all=True)
            if conflict:
                raise RuntimeError(conflict)
    if conflict:
        raise ValueError(conflict)
    # Other ZIP members are outside this exact one-child attestation. The
    # caller must retain the parent partial/review state and process them
    # separately; no parent or city-member completion marker is written here.
    return {'typed_rows':len(rows),'child_sha256':CHILD_SHA,'parent_partial':True}

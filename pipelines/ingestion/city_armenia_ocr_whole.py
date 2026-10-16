"""Source-bound publication of one Armenia OCR PDF before normal ZIP processing.

The other 29 members keep the ordinary city publisher's validation and state.
"""
import io
import json
import zipfile
from datetime import date
from hashlib import sha256

from pipelines.ingestion import city_reports, ocr
from pipelines.ingestion.pdf_sources import VerifiedPDFPage

from . import city_armenia_ocr_proof as proof

VERSION = 'city-v8:armenia-jan2024-ocr-whole-v1'
DAY = date(2024, 1, 25)


URL = proof.URL
PARENT = proof.PARENT_ID
CHILD = proof.PDF_ID
ENTRY = proof.ENTRY
MEMBER_CRC = 4033156100
MEMBER_SIZE = 461108
MEMBER_OFFSET = 22977
ROSTER_SHA = 'caead03dd510cb3bf0c4565d8a8a804840f5a28a61eab07529ca7e398ca750fe'


def require(ok, message):
    if not ok:
        raise ValueError('Exact Armenia OCR source gate: ' + message)


def digest(data):
    return sha256(bytes(data)).hexdigest()


def checked_member(parent):
    require(digest(parent) == PARENT, 'parent ZIP bytes changed')
    with zipfile.ZipFile(io.BytesIO(parent)) as bundle:
        members = [m for m in bundle.infolist() if not m.is_dir()]
        require(len(members) == 30 and all(m.filename.lower().endswith('.pdf') for m in members),
                'ZIP member roster changed')
        roster = [(m.filename, m.header_offset, m.CRC, m.file_size,
                   digest(bundle.read(m))) for m in members]
        require(digest(json.dumps(roster, ensure_ascii=False,
                                  separators=(',', ':')).encode()) == ROSTER_SHA,
                'ZIP member identities or bytes changed')
        matching = [m for m in members if m.filename == ENTRY]
        require(len(matching) == 1 and len({m.filename for m in members}) == len(members),
                'ZIP member identity changed')
        member = matching[0]
        require((member.header_offset, member.CRC, member.file_size) ==
                (MEMBER_OFFSET, MEMBER_CRC, MEMBER_SIZE), 'child ZIP metadata changed')
        child = bundle.read(member)
    require(len(child) == MEMBER_SIZE and digest(child) == CHILD, 'child PDF bytes changed')
    return member, child


def source_rows(db, parent_bytes):
    asset = db.execute('''SELECT a.kind,a.observed_on,a.document_id,a.status,
      d.kind,d.source_url,d.media_type,d.reference_period,d.metadata,d.content FROM ingestion_asset a
      JOIN source_document d ON d.id=a.document_id WHERE a.url=%s''', (URL,)).fetchone()
    require(asset is not None, 'parent asset absent')
    kind, day, did, status, doc_kind, url, media, period, metadata, parent = asset
    require((kind, day, did, doc_kind, url, media) ==
            ('city-zip', DAY, PARENT, 'original', URL, 'application/zip'),
            'parent asset binding changed')
    require(status in ('review', 'failed', 'pending', 'complete') and period == DAY.isoformat(),
            'parent asset status or source period changed')
    require(metadata.get('ingestion_kind') == 'city-zip' and
            metadata.get('retention') == 'permanent' and
            metadata.get('original_filename') == URL.rsplit('/', 1)[-1],
            'parent metadata changed')
    require(bytes(parent) == parent_bytes, 'supplied and retained ZIP bytes disagree')
    member, pdf = checked_member(bytes(parent))
    source = db.execute('''SELECT kind,source_url,media_type,reference_period,page_count,
      metadata,content FROM source_document WHERE id=%s''', (CHILD,)).fetchone()
    require(source is not None, 'child source absent')
    skind, surl, smedia, period, pages, smeta, retained = source
    require((skind, surl, smedia, period) ==
            ('original', URL, 'application/pdf', 'Serie histórica completa') and
            smeta.get('ingestion_kind') == 'city-pdf' and
            smeta.get('retention') == 'permanent' and
            smeta.get('parents') == [PARENT] and
            smeta.get('archive_entry') == ENTRY and
            smeta.get('original_filename') == ENTRY and
            pages == 2 and bytes(retained) == pdf and digest(retained) == CHILD,
            'child source metadata/bytes changed')
    mapping = db.execute('''SELECT document_id FROM source_archive_member
      WHERE archive_id=%s AND entry_name=%s''', (PARENT, ENTRY)).fetchone()
    require(mapping == (CHILD,), 'archive-member pointer changed')
    tasks = db.execute('''SELECT t.document_id,t.source_locator,t.image_id,t.source_kind,
      t.source_page,t.status,t.error,d.kind,d.source_url,d.media_type,
      d.reference_period,d.metadata,d.content
      FROM source_ocr_task t JOIN source_document d ON d.id=t.image_id
      WHERE t.document_id=%s ORDER BY t.source_page FOR UPDATE OF t''', (CHILD,)).fetchall()
    require(len(tasks) == 2, 'task count changed')
    task_proof = []
    image_ids = []
    for expected_page, row in enumerate(tasks, 1):
        t_did, locator, image, source_kind, source_page, status, error, ikind, iurl, imedia, iperiod, imeta, image_bytes = row
        require((t_did, locator, source_page, status, error) ==
                (CHILD, f'PDF page {expected_page}', expected_page, 'review', proof.OLD_ERROR),
                'old task status/page changed')
        require(source_kind == 'city-pdf' and image == proof.PAGE[expected_page]['image_id'] and
                (ikind, iurl, imedia, iperiod) ==
                ('extract', URL, 'image/png', 'Serie histórica completa') and
                imeta.get('ingestion_kind') == 'ocr-image' and
                imeta.get('retention') == 'permanent' and
                imeta.get('parents') == [CHILD] and
                imeta.get('archive_entry') == 'rendered-source.png' and
                imeta.get('original_filename') == 'rendered-source.png' and
                digest(image_bytes) == image,
                'retained page image/source binding changed')
        task_proof.append(dict(document_id=t_did, source_locator=locator, image_id=image,
                               source_page=source_page, error=error, source_url=surl,
                               media_type=smedia, kind=skind, metadata=smeta))
        image_ids.append(image)
    raw_count = db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',
                           (CHILD,)).fetchone()[0]
    require(raw_count in (0, 59), 'partial preexisting source rows')
    results = db.execute('''SELECT image_id,version,reading,result FROM source_ocr_result
      WHERE image_id=ANY(%s::text[]) AND version=%s ORDER BY image_id,reading''',
                         (image_ids, ocr.VERSION)).fetchall()
    require(len(results) == 4, 'current OCR reading count changed')
    cached = [dict(image_id=r[0], version=r[1], reading=r[2], result=r[3]) for r in results]
    return member, pdf, task_proof, cached, raw_count, status


def verified_rows(pdf, tasks, cached):
    # The existing generic comparator is deliberately unchanged. This only
    # accepts four SHA-pinned readings of one image-only original.
    attestation = proof.adjudicate(pdf, tasks, cached)
    projected = {}
    for item in cached:
        projected[(next(p for p in (1, 2) if proof.PAGE[p]['image_id'] == item['image_id']),
                   item['reading'])] = proof.project(item['result'])
    pages = [VerifiedPDFPage(projected[(p, 0)]) for p in (1, 2)]
    rows = list(city_reports.parse_city_pages(pages, heading=pages[0].extract_text()))
    require(len(rows) == 59 and proof.rows_digest(rows) == attestation['projected_full17_sha256'],
            'typed row projection changed')
    return rows, attestation


def publish_exact_child(db, source_url, parent_bytes, parent_sha256):
    """Commit or verify all 59 rows, leaving siblings to the normal publisher."""
    require(source_url == URL and parent_sha256 == PARENT and digest(parent_bytes) == PARENT,
            'nonexact source route or changed parent bytes')
    with db.transaction():
        member, pdf, tasks, cached, prior_count, status = source_rows(db, parent_bytes)
        rows, attestation = verified_rows(pdf, tasks, cached)
        step = city_reports._member_step(member, DAY)
        cp = db.execute('''SELECT records FROM ingestion_checkpoint
          WHERE document_id=%s AND processor_version=%s AND step=%s''',
                        (PARENT, VERSION, step)).fetchone()
        require(cp is None or cp == (59,), 'member checkpoint changed')
        if cp is not None:
            require(prior_count == 59, 'checkpoint without complete rows')
        else:
            require(status in ('review', 'failed'), 'unreviewed first publication status')
        before = city_reports._publication_conflict(db, CHILD, rows, VERSION,
                                                     PARENT, ENTRY,
                                                     require_all=cp is not None,
                                                     native_source=None)
        require(before is None, 'preexisting publication conflict')
        if cp is None:
            city_reports.save_classifications(db, CHILD, rows)
            city_reports._bulk_insert(db, 'regional_price', ((CHILD, *r) for r in rows))
            after = city_reports._publication_conflict(db, CHILD, rows, VERSION,
                                                        PARENT, ENTRY,
                                                        require_all=True, native_source=None)
            require(after is None, 'post-insert publication conflict')
        for page in (1, 2):
            e = proof.PAGE[page]
            policy = f'{VERSION}:page-{page}:{attestation["projected_full17_sha256"]}'
            if cp is None:
                db.execute('''INSERT INTO source_ocr_review_history
                  (document_id,source_locator,policy_version,source_kind,prior_status,prior_error,
                   reading0_sha256,reading1_sha256)
                  VALUES(%s,%s,%s,'city-pdf','review',%s,%s,%s) ON CONFLICT DO NOTHING''',
                  (CHILD, f'PDF page {page}', policy, proof.OLD_ERROR,
                   e['reading_sha'][0], e['reading_sha'][1]))
            stored = db.execute('''SELECT prior_status,prior_error,reading0_sha256,reading1_sha256
              FROM source_ocr_review_history WHERE document_id=%s AND source_locator=%s
              AND policy_version=%s''',
              (CHILD, f'PDF page {page}', policy)).fetchone()
            require(stored == ('review', proof.OLD_ERROR,
                               e['reading_sha'][0], e['reading_sha'][1]),
                    'append-only adjudication annotation drift')
        if cp is None:
            db.execute('''INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records)
              VALUES(%s,%s,%s,59) ON CONFLICT DO NOTHING''', (PARENT, VERSION, step))
        require(db.execute('''SELECT records FROM ingestion_checkpoint WHERE document_id=%s
          AND processor_version=%s AND step=%s''',
          (PARENT, VERSION, step)).fetchone() == (59,), 'checkpoint drift')
    return dict(child=CHILD, rows=59, parent=PARENT, member_step=step,
                full17_sha256=attestation['projected_full17_sha256'],
                parent_complete=False, old_task_status_preserved=True)

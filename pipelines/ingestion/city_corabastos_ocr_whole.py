"""Publish one exact Corabastos OCR child, then normal-process all ZIP siblings.

Candidate lives privately until reviewed; no generic OCR or city gate is changed.
"""

from hashlib import sha256

from psycopg.types.json import Jsonb

from pipelines.ingestion import city_reports
from . import city_corabastos_ocr_proof as proof


def _source_rows(db, parent_bytes):
    asset = db.execute('''SELECT a.kind,a.observed_on,a.document_id,a.status,
      d.kind,d.source_url,d.media_type,d.reference_period,d.metadata,d.content
      FROM ingestion_asset a JOIN source_document d ON d.id=a.document_id
      WHERE a.url=%s''', (proof.URL,)).fetchone()
    proof.require(asset is not None, 'parent asset absent')
    kind, day, did, status, dkind, url, media, period, meta, retained = asset
    proof.require((kind, day, did, dkind, url, media, period) ==
                  ('city-zip', proof.DAY, proof.PARENT, 'original', proof.URL,
                   'application/zip', proof.DAY.isoformat()) and
                  status in ('review', 'failed', 'pending', 'complete') and
                  meta.get('ingestion_kind') == 'city-zip' and
                  meta.get('retention') == 'permanent' and
                  meta.get('original_filename') == proof.URL.rsplit('/', 1)[-1] and
                  bytes(retained) == parent_bytes,
                  'parent asset metadata or retained bytes changed')
    member, child = proof.checked_member(parent_bytes)
    source = db.execute('''SELECT kind,source_url,media_type,reference_period,
      page_count,metadata,content FROM source_document WHERE id=%s''',
      (proof.CHILD,)).fetchone()
    proof.require(source is not None, 'child PDF absent')
    skind, surl, smedia, sper, pages, smeta, pdf = source
    proof.require((skind, surl, smedia, sper, pages) ==
                  ('original', proof.URL, 'application/pdf', 'Serie histórica completa', 3)
                  and smeta.get('ingestion_kind') == 'city-pdf'
                  and smeta.get('retention') == 'permanent'
                  and smeta.get('parents') == [proof.PARENT]
                  and smeta.get('archive_entry') == proof.ENTRY
                  and smeta.get('original_filename') == proof.ENTRY
                  and bytes(pdf) == child and proof.digest(pdf) == proof.CHILD,
                  'child PDF metadata or bytes changed')
    linked = db.execute('''SELECT document_id FROM source_archive_member
      WHERE archive_id=%s AND entry_name=%s''', (proof.PARENT, proof.ENTRY)).fetchone()
    proof.require(linked == (proof.CHILD,), 'archive-member pointer changed')
    tasks = db.execute('''SELECT t.document_id,t.source_locator,t.image_id,t.source_kind,
      t.source_page,t.status,t.error,d.kind,d.source_url,d.media_type,
      d.reference_period,d.metadata,d.content
      FROM source_ocr_task t JOIN source_document d ON d.id=t.image_id
      WHERE t.document_id=%s ORDER BY t.source_page FOR UPDATE OF t''',
      (proof.CHILD,)).fetchall()
    proof.require(len(tasks) == 3, 'OCR task count changed')
    prior = []
    for page, row in enumerate(tasks, 1):
        (task_did, locator, image_id, source_kind, source_page, task_status,
         error, ikind, iurl, imedia, iper, imeta, image_bytes) = row
        proof.require((task_did, locator, image_id, source_kind, source_page,
                       task_status, error) ==
                      (proof.CHILD, f'PDF page {page}', proof.IMAGES[page],
                       'city-pdf', page, 'review', proof.OLD_ERRORS[page]) and
                      (ikind, iurl, imedia, iper) ==
                      ('extract', proof.URL, 'image/png', 'Serie histórica completa') and
                      imeta.get('ingestion_kind') == 'ocr-image' and
                      imeta.get('retention') == 'permanent' and
                      imeta.get('parents') == [proof.CHILD] and
                      imeta.get('archive_entry') == 'rendered-source.png' and
                      imeta.get('original_filename') == 'rendered-source.png' and
                      proof.digest(image_bytes) == image_id,
                      f'page {page} archived image or review state changed')
        prior.append({'page': page, 'image_id': image_id,
                      'status': task_status, 'error': error})
    result_rows = db.execute('''SELECT image_id,version,reading,result
      FROM source_ocr_result WHERE image_id=ANY(%s::text[])
      ORDER BY image_id,version,reading''', (list(proof.IMAGES.values()),)).fetchall()
    proof.require(len(result_rows) == 5, 'cached OCR result count changed')
    cached = {}
    for image_id, version, reading, result in result_rows:
        page = next((p for p, expected in proof.IMAGES.items() if image_id == expected), None)
        proof.require(page is not None and version == 'gemini-image-ocr-v2'
                      and (page, reading) in proof.READINGS,
                      'cached result identity or version changed')
        cached[(page, reading)] = result
    proof.require(set(cached) == set(proof.READINGS), 'cached result set changed')
    return member, cached, prior, status


def _record_evidence(db, body, *, initial):
    from psycopg.types.json import Jsonb

    metadata = {'ingestion_kind': 'city-ocr-local-geometry-proof',
                'retention': 'permanent', 'parents': [proof.CHILD],
                'archive_entry': proof.EVIDENCE_NAME,
                'original_filename': proof.EVIDENCE_NAME,
                'evidence_method': 'local_retained_source_geometry',
                'source_pdf_sha256': proof.CHILD}
    if initial:
        db.execute('''INSERT INTO source_document
          (id,title,publisher,source_url,media_type,kind,reference_period,
           content,metadata)
          VALUES(%s,%s,'AgroAmigo source review',%s,'application/zip','extract',
           %s,%s,%s) ON CONFLICT(id) DO NOTHING''',
          (proof.EVIDENCE_SHA, proof.EVIDENCE_NAME, proof.URL,
           proof.DAY.isoformat(), body, Jsonb(metadata)))
    actual = db.execute('''SELECT kind,source_url,media_type,reference_period,
      metadata,content FROM source_document WHERE id=%s''',
      (proof.EVIDENCE_SHA,)).fetchone()
    proof.require(actual is not None and
                  actual[:4] == ('extract', proof.URL, 'application/zip',
                                  proof.DAY.isoformat()) and
                  actual[4] == metadata and bytes(actual[5]) == body,
                  'retained derived evidence changed')


def _record_adjudication(db, prior, *, initial):
    provider_hashes = {f'p{p}_r{r}': value for (p, r), value in proof.READINGS.items()}
    provider_hashes['p2_r1'] = None  # Explicitly absent, never a synthetic reading.
    method = 'local_retained_source_geometry_plus_five_cached_provider_readings'
    args = (proof.CHILD, proof.VERSION, proof.PARENT, proof.ENTRY,
            proof.EVIDENCE_SHA, method, list(proof.IMAGES.values()),
            Jsonb(provider_hashes), Jsonb(prior), proof.ROWS_SHA, 196)
    if initial:
        db.execute('''INSERT INTO city_corabastos_ocr_adjudication
          (document_id,policy_version,archive_id,entry_name,evidence_document_id,
           evidence_method,image_ids,provider_result_hashes,prior_tasks,
           full17_sha256,records)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''', args)
    row = db.execute('''SELECT archive_id,entry_name,evidence_document_id,
      evidence_method,image_ids,provider_result_hashes,prior_tasks,
      full17_sha256,records FROM city_corabastos_ocr_adjudication
      WHERE document_id=%s AND policy_version=%s''',
      (proof.CHILD, proof.VERSION)).fetchone()
    proof.require(row == (proof.PARENT, proof.ENTRY, proof.EVIDENCE_SHA,
                          method, list(proof.IMAGES.values()), provider_hashes,
                          prior, proof.ROWS_SHA, 196),
                  'append-only child adjudication changed')


def publish_exact_child(db, source_url, parent_bytes, parent_sha256):
    proof.require(source_url == proof.URL and parent_sha256 == proof.PARENT and
                  proof.digest(parent_bytes) == proof.PARENT,
                  'wrong source route or parent bytes')
    with db.transaction():
        member, cached, prior, status = _source_rows(db, parent_bytes)
        local_bytes, local_grid = proof.local_evidence()
        rows = proof.checked_rows(cached, local_grid)
        step = city_reports._member_step(member, proof.DAY)
        proof.require(step == proof.MEMBER_STEP, 'member step changed')
        cp = db.execute('''SELECT records FROM ingestion_checkpoint
          WHERE document_id=%s AND processor_version=%s AND step=%s''',
          (proof.PARENT, proof.VERSION, step)).fetchone()
        raw = db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',
                         (proof.CHILD,)).fetchone()[0]
        classes = db.execute('SELECT count(*) FROM regional_classification WHERE document_id=%s',
                             (proof.CHILD,)).fetchone()[0]
        proof.require((cp is None and raw == classes == 0) or
                      (cp == (196,) and raw == classes == 196),
                      'partial source or checkpoint state')
        if cp is None:
            proof.require(status in ('review', 'failed'),
                          'first publication is not an identified source review')
        conflict = city_reports._publication_conflict(
            db, proof.CHILD, rows, proof.VERSION, proof.PARENT, proof.ENTRY,
            require_all=cp is not None, native_source=None)
        proof.require(conflict is None, 'preexisting publication conflict')
        if cp is None:
            city_reports.save_classifications(db, proof.CHILD, rows)
            city_reports._bulk_insert(db, 'regional_price',
                                      ((proof.CHILD, *row) for row in rows))
            conflict = city_reports._publication_conflict(
                db, proof.CHILD, rows, proof.VERSION, proof.PARENT, proof.ENTRY,
                require_all=True, native_source=None)
            proof.require(conflict is None, 'post-insert publication conflict')
        _record_evidence(db, local_bytes, initial=cp is None)
        _record_adjudication(db, prior, initial=cp is None)
        if cp is None:
            db.execute('''INSERT INTO ingestion_checkpoint
              (document_id,processor_version,step,records)
              VALUES(%s,%s,%s,196) ON CONFLICT DO NOTHING''',
              (proof.PARENT, proof.VERSION, step))
        proof.require(db.execute('''SELECT records FROM ingestion_checkpoint
          WHERE document_id=%s AND processor_version=%s AND step=%s''',
          (proof.PARENT, proof.VERSION, step)).fetchone() == (196,),
          'whole-child checkpoint changed')
    return {'document_id': proof.CHILD, 'rows': 196,
            'full17_sha256': proof.ROWS_SHA, 'checkpoint': proof.MEMBER_STEP}


def publish_exact_parent(db, source_url, parent_bytes, parent_sha256):
    """Commit the proven child, then leave all other members to the normal gate."""
    publish_exact_child(db, source_url, parent_bytes, parent_sha256)
    # This call sees the same-version exact child checkpoint, skips that one
    # member only, and proceeds through each of the other 27 PDFs. Any sibling
    # review raises CityZipPartialReview with its actual cumulative count.
    return city_reports.publish_city_zip(
        db, parent_bytes, proof.PARENT, proof.URL, proof.DAY,
        processor_version=proof.VERSION)

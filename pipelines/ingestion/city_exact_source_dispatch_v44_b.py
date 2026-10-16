"""Exact-source city ZIP recovery dispatched by the ingestion worker.

Returning None delegates every other ZIP to the unchanged city-v8 publisher.
The two exact source routes remain partial/review until their independent
whole-parent publication gates are fulfilled. No generic source relaxation.
"""
import hashlib
import io
import zipfile
from . import city_reports
from . import city_source_adjudication_jan2023 as jan2023_source
from . import city_category_alias_checkpoint as category_alias
from . import city_corabastos_ocr_proof as corabastos_proof
from .city_corabastos_ocr_whole import publish_exact_parent as publish_corabastos
from .city_sep2021_native import URL as SEP_URL, PARENT_SHA as SEP_SHA
from .city_sep2021_publication_v44_b import publish_exact as publish_sep
from .city_pereira_20220106_native_b import (
    URL as PEREIRA_URL, ENTRY as PEREIRA_ENTRY, PARENT_SHA as PEREIRA_SHA,
)
from .city_pereira_publication_b import publish_exact_child as publish_pereira_child
from .city_native_geometry import (
    DAY as ARMENIA_DAY, ENTRY as ARMENIA_ENTRY, PARENT as ARMENIA_SHA, URL as ARMENIA_URL,
    _exact_member as armenia_exact_member, publish_exact_parent as publish_armenia,
)
from .city_valledupar_partial import (
    DAY as VALLEDUPAR_DAY, ENTRY as VALLEDUPAR_ENTRY,
    PARENT as VALLEDUPAR_SHA, REVIEW_STEP as VALLEDUPAR_REVIEW_STEP,
    URL as VALLEDUPAR_URL, VERSION as VALLEDUPAR_VERSION,
    exact_member as valledupar_exact_member,
    publish_exact_parent as publish_valledupar,
)
from .city_armenia_ocr_whole import (
    URL as ARMENIA_OCR_URL, PARENT as ARMENIA_OCR_SHA,
    DAY as ARMENIA_OCR_DAY, VERSION as ARMENIA_OCR_VERSION,
    checked_member as armenia_ocr_member,
    publish_exact_child as publish_armenia_ocr_child,
)


_REVIEWED_NEXTDAY = {
    'https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-20oct2023.zip':
        ('51c4a6fdf9440ffdf95daab2c8f81afe092f956f366dea493181604ef784855b', '2023-10-20', 32, 1974, 'city-v8:reviewed-oct2023-nextday-v1'),
    'https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-30mar2024.zip':
        ('584bc4da5ed1c9f5fa44cf93f7a2e1a8c2e2606616aa1bb7024e99db55e07dda', '2024-03-30', 18, 875, 'city-v8:reviewed-mar2024-nextday-v1'),
    'https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-17may2024.zip':
        ('563c1c05f36a3db36404d85ddefe974c595d0c4833ec8b485c14bde7cf7bf785', '2024-05-17', 32, 2034, 'city-v8:reviewed-may2024-nextday-v1'),
}


_RETAINED = {
    # Exact retained Nov 16 source for a source-scoped native unit/category replay.
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-16-11-2021.zip':
        'e4a8aa221892eb1d7eebb80e23e6d5419d406b87fa4243f205ee1f32b1fa8d10',
    SEP_URL: SEP_SHA,
    PEREIRA_URL: PEREIRA_SHA,
    # The normal city publisher applies the exact whole-grid source-date review;
    # this retained-byte route only avoids HTTP during a publisher cooldown.
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-10-02-2021.zip':
        '2ca39b0eacb32edb497e0be527f93e581de9edecdd5364cda7b7ba7b381a1857',
    ARMENIA_OCR_URL: ARMENIA_OCR_SHA,
    # Normal whole-parent publication recovers the verified 53-row native grid
    # and preserves the 1,202 previously published sibling observations.
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-11-01-2022.zip':
        '343f20fb88142be933f1fbc537257f427d40aecd6f59fdb69589b5c05da1c6ed',
}


def retained_exact_city_zip(db, url, kind, expected_version):
    """Reparse only the exact archived review asset, without an HTTP request."""
    from . import city_nonprice_context as nonprice

    category_source = category_alias.SOURCES.get(url)
    if category_source is not None:
        if kind != 'city-zip' or expected_version != city_reports.VERSION:
            return None
        row = db.execute('''SELECT a.kind,a.observed_on,a.status,a.document_id,
          a.processor_version,a.records,d.kind,d.publisher,d.source_url,
          d.media_type,d.reference_period,d.metadata,d.content
          FROM ingestion_asset a LEFT JOIN source_document d ON d.id=a.document_id
          WHERE a.url=%s''',(url,)).fetchone()
        if row is None or row[3] != category_source.parent:
            # A newly published revision keeps its own source identity and
            # follows the ordinary fetch/parser route.
            return None
        if (row[:2] != ('city-zip',category_source.day)
                or row[2] not in ('pending','complete','failed','review')
                or row[4] not in ('city-v5',city_reports.VERSION)
                or row[5] != category_source.parent_rows
                or row[6:10] != ('original','DANE',url,'application/zip')
                or row[10] != category_source.day.isoformat()
                or not isinstance(row[11],dict)
                or row[11].get('ingestion_kind') != 'city-zip'
                or row[11].get('retention') != 'permanent'
                or row[11].get('original_filename') != url.rsplit('/',1)[-1]):
            raise ValueError('Exact category alias retained parent binding changed')
        body = bytes(row[12])
        if category_alias.sha(body) != category_source.parent:
            raise ValueError('Exact category alias retained ZIP bytes changed')
        return body

    if url == jan2023_source.URL:
        return jan2023_source.retained_exact_parent(db,url,kind,expected_version)
    if url == ARMENIA_OCR_URL:
        from .city_jan25_ocr_whole import VERSION as JAN25_OCR_VERSION
        if kind != 'city-zip' or expected_version not in (ARMENIA_OCR_VERSION, JAN25_OCR_VERSION):
            return None
        row = db.execute('''SELECT d.content,a.status FROM ingestion_asset a
          JOIN source_document d ON d.id=a.document_id
          WHERE a.url=%s AND a.kind='city-zip' AND a.observed_on=%s
          AND a.status IN ('review','failed','pending','complete') AND a.document_id=%s
          AND d.id=%s AND d.kind='original' AND d.source_url=a.url
          AND d.media_type='application/zip'
          AND d.reference_period=%s
          AND d.metadata->>'ingestion_kind'='city-zip'
          AND d.metadata->>'retention'='permanent'
          AND d.metadata->>'original_filename'=%s''',
          (ARMENIA_OCR_URL, ARMENIA_OCR_DAY, ARMENIA_OCR_SHA,
           ARMENIA_OCR_SHA, ARMENIA_OCR_DAY.isoformat(),
           ARMENIA_OCR_URL.rsplit('/', 1)[-1])).fetchone()
        if row is None:
            return None
        body = bytes(row[0])
        member, _ = armenia_ocr_member(body)
        step = city_reports._member_step(member, ARMENIA_OCR_DAY)
        checkpoint = db.execute('''SELECT records FROM ingestion_checkpoint
          WHERE document_id=%s AND processor_version=%s AND step=%s''',
          (ARMENIA_OCR_SHA, ARMENIA_OCR_VERSION, step)).fetchone()
        if checkpoint is not None:
            if checkpoint != (59,):
                raise ValueError('Exact Armenia OCR checkpoint drift')
            # The generic publisher still needs a chance to finish siblings.
            # The child publisher below verifies full stored parity on replay.
        elif row[1] not in ('review', 'failed'):
            # A newly pending parent may resume siblings only after this
            # exact child's review was already atomically published.
            return None
        return body

    if url == nonprice.URL:
        if kind != 'city-zip' or expected_version != nonprice.VERSION:
            return None
        row = db.execute('''SELECT d.content FROM ingestion_asset a
          JOIN source_document d ON d.id=a.document_id WHERE a.url=%s
          AND a.kind='city-zip' AND a.observed_on=%s
          AND a.status IN ('review','failed','pending','complete')
          AND a.document_id=%s AND d.id=%s AND d.kind='original'
          AND d.source_url=a.url AND d.media_type='application/zip'
          AND d.metadata->>'ingestion_kind'='city-zip' ''',
          (nonprice.URL, nonprice.DAY, nonprice.PARENT_SHA256, nonprice.PARENT_SHA256)).fetchone()
        if row is None:
            return None
        body = bytes(row[0] or b'')
        verified = nonprice.verify_exact_nonprice_parent(
            url, body, nonprice.PARENT_SHA256, nonprice.DAY,
        )
        completed = dict(db.execute('''SELECT step,records FROM ingestion_checkpoint
          WHERE document_id=%s AND processor_version=%s''',
          (nonprice.PARENT_SHA256, nonprice.VERSION)).fetchall())
        if (completed.get(verified.step) == 0
                and all(completed.get(step, 0) > 0 for step in verified.peer_steps)):
            # A matching checkpoint cannot conceal a different retained grid.
            nonprice._check_no_agricultural_rows(db)
            nonprice._check_existing_peer_parity(db, body, completed)
            return None
        return body
    if url == corabastos_proof.URL:
        if kind != "city-zip" or expected_version != corabastos_proof.VERSION:
            return None
        row = db.execute("""SELECT d.content,a.status,a.processor_version,a.records
          FROM ingestion_asset a JOIN source_document d ON d.id=a.document_id
          WHERE a.url=%s AND a.kind='city-zip' AND a.observed_on=%s
          AND a.document_id=%s AND a.status IN ('review','failed','pending','complete')
          AND d.id=%s AND d.kind='original' AND d.source_url=a.url
          AND d.media_type='application/zip'
          AND d.metadata->>'ingestion_kind'='city-zip'
          AND d.metadata->>'retention'='permanent'
          AND d.metadata->>'original_filename'=%s""",
          (url,corabastos_proof.DAY,corabastos_proof.PARENT,
           corabastos_proof.PARENT,url.rsplit("/",1)[-1])).fetchone()
        if row is None:
            state = db.execute("""SELECT status FROM ingestion_asset
              WHERE url=%s AND kind='city-zip'""", (url,)).fetchone()
            if state is not None and state[0] == 'pending':
                raise ValueError('Exact Corabastos pending source binding changed')
            return None
        body = bytes(row[0])
        corabastos_proof.checked_member(body)
        if row[1] == "pending":
            # A crash may leave the asset on its old version after the exact
            # child committed. The child checkpoint, not the asset version,
            # identifies that state. The replay below also verifies all 196
            # stored tuples, classifications, source bytes and local proof.
            child = db.execute("""SELECT records FROM ingestion_checkpoint
              WHERE document_id=%s AND processor_version=%s AND step=%s""",
              (corabastos_proof.PARENT,corabastos_proof.VERSION,
               corabastos_proof.MEMBER_STEP)).fetchone()
            if child != (196,):
                raise ValueError('Exact Corabastos pending child checkpoint absent')
            from .city_corabastos_ocr_whole import publish_exact_child
            publish_exact_child(db, url, body, corabastos_proof.PARENT)
            return body
        if row[1] == "complete" and row[2] == expected_version:
            with zipfile.ZipFile(io.BytesIO(body)) as bundle:
                steps = [city_reports._member_step(member, corabastos_proof.DAY)
                         for member in bundle.infolist() if not member.is_dir()]
            cps = dict(db.execute("""SELECT step,records FROM ingestion_checkpoint
              WHERE document_id=%s AND processor_version=%s
              AND step=ANY(%s::text[])""",
              (corabastos_proof.PARENT,expected_version,steps)).fetchall())
            if (len(cps) == 28 and cps.get(corabastos_proof.MEMBER_STEP) == 196
                    and all(cps.get(step,0) > 0 for step in steps)):
                stored = db.execute("""SELECT count(*) FROM regional_price r
                  JOIN source_archive_member m ON m.document_id=r.document_id
                  WHERE m.archive_id=%s""", (corabastos_proof.PARENT,)).fetchone()[0]
                conflict = db.execute("""SELECT 1 FROM unresolved_city_pdf_publication_conflict c
                  JOIN source_archive_member m ON m.document_id=c.document_id
                  WHERE m.archive_id=%s LIMIT 1""", (corabastos_proof.PARENT,)).fetchone()
                if (stored == sum(cps.values()) == row[3] and not conflict):
                    # Existing child and truthful evidence must still pass
                    # exact source comparison; this replay is read-only.
                    from .city_corabastos_ocr_whole import publish_exact_child
                    publish_exact_child(db, url, body, corabastos_proof.PARENT)
                    return None
        return body
    if url == ARMENIA_URL:
        if kind != 'city-zip' or expected_version != 'city-v8:jan2022-native-geometry-v1':
            return None
        row = db.execute('''SELECT d.content,a.processor_version FROM ingestion_asset a
          JOIN source_document d ON d.id=a.document_id WHERE a.url=%s
          AND a.kind='city-zip' AND a.observed_on=%s
          AND a.status IN ('review','failed') AND a.document_id=%s
          AND d.id=%s AND d.kind='original' AND d.source_url=a.url
          AND d.media_type='application/zip'
          AND d.metadata->>'ingestion_kind'='city-zip' ''',
          (ARMENIA_URL, ARMENIA_DAY, ARMENIA_SHA, ARMENIA_SHA)).fetchone()
        if row is None:
            return None
        body = bytes(row[0])
        if hashlib.sha256(body).hexdigest() != ARMENIA_SHA:
            raise ValueError('Exact retained Armenia ZIP bytes changed')
        armenia_exact_member(body)
        if row[1] == expected_version:
            # A failed/review run stamps its current version even when a child
            # transaction rolled back. Resume only while exact work remains.
            with zipfile.ZipFile(io.BytesIO(body)) as bundle:
                members = [m for m in bundle.infolist() if not m.is_dir()
                           and m.filename.lower().endswith('.pdf')]
            steps = [city_reports._member_step(member, ARMENIA_DAY) for member in members]
            completed = dict(db.execute('''SELECT step,records FROM ingestion_checkpoint
              WHERE document_id=%s AND processor_version=%s AND step=ANY(%s::text[])''',
              (ARMENIA_SHA, expected_version, steps)).fetchall())
            child_step = city_reports._member_step(next(m for m in members if m.filename == ARMENIA_ENTRY), ARMENIA_DAY)
            if (len(completed) == len(steps) and all(value > 0 for value in completed.values())
                    and completed.get(child_step) == 53
                    and sum(completed.values()) == 1255):
                return None
        return body
    if url == VALLEDUPAR_URL:
        if kind != 'city-zip' or expected_version != VALLEDUPAR_VERSION:
            return None
        row = db.execute('''SELECT d.content,a.processor_version FROM ingestion_asset a
          JOIN source_document d ON d.id=a.document_id WHERE a.url=%s
          AND a.kind='city-zip' AND a.observed_on=%s
          AND a.status IN ('review','failed') AND a.document_id=%s
          AND d.id=%s AND d.kind='original' AND d.source_url=a.url
          AND d.media_type='application/zip'
          AND d.metadata->>'ingestion_kind'='city-zip'
          AND d.metadata->>'retention'='permanent'
          AND d.metadata->>'original_filename'=%s''',
          (VALLEDUPAR_URL, VALLEDUPAR_DAY, VALLEDUPAR_SHA,
           VALLEDUPAR_SHA, VALLEDUPAR_URL.rsplit('/', 1)[-1])).fetchone()
        if row is None:
            return None
        body = bytes(row[0])
        if hashlib.sha256(body).hexdigest() != VALLEDUPAR_SHA:
            raise ValueError('Exact retained Valledupar ZIP bytes changed')
        child, _ = valledupar_exact_member(body)
        if row[1] == expected_version:
            with zipfile.ZipFile(io.BytesIO(body)) as bundle:
                members = [m for m in bundle.infolist() if not m.is_dir()
                           and m.filename.lower().endswith('.pdf')]
            steps = [city_reports._member_step(member, VALLEDUPAR_DAY) for member in members]
            completed = dict(db.execute('''SELECT step,records FROM ingestion_checkpoint
              WHERE document_id=%s AND processor_version=%s
                AND (step=ANY(%s::text[]) OR step=%s)''',
              (VALLEDUPAR_SHA, expected_version, steps,
               VALLEDUPAR_REVIEW_STEP)).fetchall())
            child_step = city_reports._member_step(child, VALLEDUPAR_DAY)
            if (len(members) == len(steps) == 18
                    and all(step in completed and completed[step] > 0 for step in steps)
                    and completed.get(child_step) == 35
                    and completed.get(VALLEDUPAR_REVIEW_STEP) == 0
                    and sum(completed[step] for step in steps) == 1418):
                return None
        return body
    exact = _REVIEWED_NEXTDAY.get(url)
    if exact is not None:
        from datetime import date
        from .reviewed_city_dates import reviewed_parent, reviewed_member, source_review

        parent_sha, parent_day, member_count, total_rows, version = exact
        if kind != 'city-zip' or expected_version != version:
            return None
        asset = db.execute(
            "SELECT kind,observed_on,status,document_id,processor_version "
            "FROM ingestion_asset WHERE url=%s", (url,),
        ).fetchone()
        if asset is None:
            return None
        if asset[0] != kind or asset[1] != date.fromisoformat(parent_day):
            raise ValueError('Reviewed next-day city ZIP asset binding changed')
        if asset[3] is None:
            if asset[2] == 'pending':
                return None
            raise ValueError('Reviewed next-day city ZIP asset pointer is missing')
        source = db.execute(
            "SELECT content,source_url,media_type,kind,metadata,reference_period "
            "FROM source_document WHERE id=%s",
            (asset[3],),
        ).fetchone()
        if (source is None or source[1:4] != (url,'application/zip','original')
                or source[4].get('ingestion_kind') != kind
                or source[4].get('retention') != 'permanent'
                or source[4].get('original_filename') != url.rsplit('/',1)[-1]
                or source[5] != parent_day):
            raise ValueError('Reviewed next-day city ZIP source binding changed')
        body = bytes(source[0])
        if hashlib.sha256(body).hexdigest() != asset[3]:
            raise ValueError('Reviewed next-day city ZIP SHA changed')
        # The same official URL may carry a later immutable revision. Once its
        # own original is bound, let the normal fetch/parser validate it rather
        # than trapping the URL behind the older exact-review SHA.
        if asset[3] != parent_sha or asset[2] not in ('review','failed','pending'):
            return None
        review = reviewed_parent(body, parent_sha, url, asset[1])
        if review is None or len(review['members']) != 1:
            raise ValueError('Reviewed next-day city ZIP registry binding changed')
        with zipfile.ZipFile(io.BytesIO(body)) as bundle:
            pdfs = [member for member in bundle.infolist()
                    if not member.is_dir() and member.filename.lower().endswith('.pdf')]
            if len(pdfs) != member_count or len({member.filename for member in pdfs}) != member_count:
                raise ValueError('Reviewed next-day city ZIP member roster changed')
            selected = [member for member in pdfs
                        if member.filename == review['members'][0]['entry_name']]
            if len(selected) != 1 or reviewed_member(
                    review, selected[0].filename, bundle.read(selected[0])) is None:
                raise ValueError('Reviewed next-day city ZIP child binding changed')
            steps = [city_reports._member_step(member, asset[1]) for member in pdfs]
        if asset[4] == version:
            completed = dict(db.execute(
                "SELECT step,records FROM ingestion_checkpoint WHERE document_id=%s "
                "AND processor_version=%s AND step=ANY(%s::text[])",
                (parent_sha, version, steps),
            ).fetchall())
            review_step = city_reports._review_step(source_review(review, review['members'][0]))
            date_review = db.execute(
                "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
                "AND processor_version=%s AND step=%s",
                (parent_sha, version, review_step),
            ).fetchone()
            stored_count = db.execute(
                "SELECT count(*) FROM regional_price r JOIN source_archive_member m "
                "ON m.document_id=r.document_id WHERE m.archive_id=%s",
                (parent_sha,),
            ).fetchone()[0]
            if (len(completed) == member_count and all(completed.get(step, 0) > 0 for step in steps)
                    and sum(completed.values()) == total_rows and stored_count == total_rows
                    and date_review == (0,)):
                return None
        return body
    source_sha = _RETAINED.get(url)
    if kind != 'city-zip' or source_sha is None:
        return None
    row = db.execute('''SELECT d.content FROM ingestion_asset a JOIN source_document d
      ON d.id=a.document_id WHERE a.url=%s AND a.kind='city-zip'
      AND a.status='review' AND a.document_id=%s
      AND a.processor_version IS DISTINCT FROM %s
      AND d.id=%s AND d.kind='original' AND d.source_url=a.url
      AND d.media_type='application/zip'
      AND d.metadata->>'ingestion_kind'='city-zip' ''',
      (url,source_sha,expected_version,source_sha)).fetchone()
    if row is None:
        return None
    body=bytes(row[0])
    if hashlib.sha256(body).hexdigest()!=source_sha:
        raise ValueError('Exact retained city ZIP bytes changed')
    return body


def maybe_publish_exact_city_zip(db, source_url, parent_bytes, parent_sha256):
    from . import city_nonprice_context as nonprice

    category_source = category_alias.SOURCES.get(source_url)
    if category_source is not None and parent_sha256 == category_source.parent:
        category_alias.checkpoint_exact_aliases(db,source_url,parent_bytes,parent_sha256)
        # Same base city-v8 version: the ordinary publisher skips only this
        # attested historical member and completes all other ZIP siblings.
        return None

    if source_url == jan2023_source.URL and parent_sha256 == jan2023_source.PARENT:
        return jan2023_source.maybe_publish(db,source_url,parent_bytes,parent_sha256)
    if source_url == ARMENIA_OCR_URL:
        publish_armenia_ocr_child(db, source_url, parent_bytes, parent_sha256)
        # The Jan 25 same-body bridge projects only the exact 66 cached OCR
        # readings. It commits complete missing children and leaves Peñol's
        # Jan 23 measurement in explicit review; no generic OCR relaxation.
        from .city_jan25_ocr_whole import DAY as JAN25_DAY, VERSION as JAN25_VERSION
        from .city_jan25_ocr_whole import publish_exact_jan25
        if parent_sha256 != ARMENIA_OCR_SHA:
            raise ValueError('Exact Jan 25 parent SHA changed')
        return publish_exact_jan25(db, parent_bytes, ARMENIA_OCR_SHA, source_url,
                                   JAN25_DAY, JAN25_VERSION)

    if source_url == nonprice.URL:
        return nonprice.maybe_publish_exact_nonprice_city_zip(
            db, source_url, parent_bytes, parent_sha256, nonprice.DAY,
            processor_version=nonprice.VERSION,
        )
    if source_url == corabastos_proof.URL:
        return publish_corabastos(db, source_url, parent_bytes, parent_sha256)
    if source_url == ARMENIA_URL:
        return publish_armenia(db, source_url, parent_bytes, parent_sha256)
    if source_url == VALLEDUPAR_URL:
        completed = publish_valledupar(db, source_url, parent_bytes, parent_sha256)
        if completed is None:
            raise ValueError('Exact Valledupar URL could not bind retained bytes')
        total, review = completed
        raise city_reports.CityZipPartialReview(total, [review])
    if source_url == SEP_URL:
        # Raises CityZipPartialReview with all 75 unresolved rounds preserved.
        return publish_sep(db, source_url, parent_bytes, parent_sha256)
    if source_url == PEREIRA_URL:
        child = publish_pereira_child(db, source_url, parent_bytes, parent_sha256)
        if child is None:
            raise ValueError('Pereira exact URL could not bind retained bytes')
        # Only this previously failed child is repaired. Do not set a parent
        # or member completion marker or change the other 12 members' existing
        # city-v8 checkpoint/price state.
        raise city_reports.CityZipPartialReview(child['typed_rows'], [{
            'filename': PEREIRA_ENTRY,
            'document_id': child['child_sha256'],
            'error_type': 'ExactChildPartialReview',
            'error': 'One verified native child published; other 12 members retain their prior city-v8 state; parent remains review',
        }])
    return None

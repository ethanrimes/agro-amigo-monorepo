"""Exact-source partial native recovery for Valledupar, 7 January 2022.

It verifies the complete immutable PDF grid, emits only 35 intact native
quotes, and returns a separate review for Coco's missing numeric quantity.
No generic parser/source date/quantity policy is changed.
"""
import copy
import hashlib
import io
import json
import zipfile
from datetime import date
from decimal import Decimal

import pdfplumber

from . import city_reports

URL = 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-07-01-2022.zip'
PARENT = '3e3e990d35d925f102ecab674c674fd65135222117f0bbd268b2201f91a1be9a'
CHILD = '908f8667c0f0880525062f7c812dcbfc433433aaa24d6ee9952c4a36dabcf337'
ENTRY = 'Valledupar, Mercabastos 7-1-2022.pdf'
CRC = 2151196080
SIZE = 128456
DAY = date(2022, 1, 7)
GRID_SHA = '06547664b49a2a9907b5703f58b56c6f7645fceba520db7a0c5e8e37f0f4b771'
ROWS_SHA = '27ee8dc5face21369599dc08a334e8fb628db1b2b848f3fb01c271f4d91e14fc'
COCO = ['Coco', 'Kilogramo', 'Kilogramo', '3.550', '4.150', '', '']
REVIEW = {
    'filename': ENTRY,
    'document_id': CHILD,
    'error_type': 'SourceQuantityOmitted',
    'error': 'La fila de Coco imprime Kilogramo como presentación y unidades, sin cantidad numérica. Las otras 35 cotizaciones del PDF se publicaron; Coco sigue pendiente de verificación.',
}
REVIEW_STEP = city_reports._review_step(REVIEW)
VERSION = 'city-v8:valledupar-jan2022-partial-v1'
EXPECTED_SIBLINGS = 1383
EXPECTED_TOTAL = 1418


def _require(value):
    if not value:
        raise ValueError('Exact Valledupar partial-source proof changed; retain all quotes for review')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_sha(value):
    return _sha(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())


def exact_member(parent):
    _require(_sha(parent) == PARENT)
    with zipfile.ZipFile(io.BytesIO(parent)) as bundle:
        members = [m for m in bundle.infolist() if not m.is_dir() and m.filename.lower().endswith('.pdf')]
        _require(len(members) == 18 and len({m.filename for m in members}) == 18)
        matches = [m for m in members if m.filename == ENTRY]
        _require(len(matches) == 1)
        member = matches[0]
        _require(member.CRC == CRC and member.file_size == SIZE)
        child = bundle.read(member)
    _require(len(child) == SIZE and _sha(child) == CHILD)
    return member, child


def _encode(value):
    return str(value) if isinstance(value, (date, Decimal)) else value


class _ReviewedPage:
    def __init__(self, page, table):
        self.page, self.table = page, table

    def extract_tables(self, *args, **kwargs):
        _require(not args and not kwargs)
        return [copy.deepcopy(self.table)]

    def __getattr__(self, name):
        return getattr(self.page, name)


def parse_exact_child(child):
    _require(_sha(child) == CHILD)
    with pdfplumber.open(io.BytesIO(child)) as pdf:
        _require(len(pdf.pages) == 2)
        tables = [city_reports._city_tables(page) for page in pdf.pages]
        _require([len(t) for t in tables] == [1, 1])
        _require([len(t[0]) for t in tables] == [39, 6])
        _require(_json_sha(tables) == GRID_SHA)
        _require(tables[0][0][5] == COCO)
        reviewed = copy.deepcopy(tables)
        reviewed[0][0][5] = [''] * 7  # Same native row number; no guessed quantity.
        rows = list(city_reports.parse_city_pages(
            [_ReviewedPage(page, reviewed[i][0]) for i, page in enumerate(pdf.pages)], DAY,
        ))
    _require(len(rows) == 35 and all(len(r) == 17 and r[1] == DAY
              and r[4] == 'Valledupar, Mercabastos' and r[9] == 1
              and r[0] != 'PDF page 1,table 1,row 6,round 1' for r in rows))
    _require(_json_sha([[_encode(v) for v in row] for row in rows]) == ROWS_SHA)
    return rows, REVIEW


def _source_identity(db, parent_bytes):
    asset = db.execute('''SELECT a.kind,a.observed_on,a.document_id,a.status,
      d.kind,d.source_url,d.media_type,d.metadata,d.content
      FROM ingestion_asset a JOIN source_document d ON d.id=a.document_id
      WHERE a.url=%s''', (URL,)).fetchone()
    _require(asset is not None)
    kind, day, did, status, source_kind, source_url, media, metadata, retained = asset
    _require((kind, day, did, source_kind, source_url, media) ==
             ('city-zip', DAY, PARENT, 'original', URL, 'application/zip'))
    _require(status in ('pending', 'review', 'failed', 'complete'))
    _require(metadata.get('ingestion_kind') == 'city-zip'
             and metadata.get('retention') == 'permanent'
             and metadata.get('original_filename') == URL.rsplit('/', 1)[-1])
    _require(hashlib.sha256(bytes(retained)).hexdigest() == PARENT
             and bytes(retained) == parent_bytes)


def publish_exact_parent(db, source_url, parent_bytes, parent_sha256):
    """Append only the 35 fully specified rows; keep Coco in source review."""
    if source_url != URL:
        return None
    _require(parent_sha256 == PARENT and hashlib.sha256(parent_bytes).hexdigest() == PARENT)
    _source_identity(db, parent_bytes)
    member, content = exact_member(parent_bytes)
    rows, review = parse_exact_child(content)
    step = city_reports._member_step(member, DAY)
    review_step = REVIEW_STEP

    from .pdf_sources import extract_pages
    from .worker import archive, asset_parser_version

    _require(asset_parser_version('city-zip', URL) == VERSION)
    conflict = None
    with db.transaction():
        did = archive(db, URL, content, 'city-pdf', DAY, filename=ENTRY, parents=[PARENT])
        _require(did == CHILD)
        source = db.execute('''SELECT kind,source_url,media_type,metadata,content
          FROM source_document WHERE id=%s''', (CHILD,)).fetchone()
        _require(source is not None)
        source_kind, child_url, media, metadata, retained = source
        _require((source_kind, child_url, media) == ('original', URL, 'application/pdf')
                 and metadata.get('ingestion_kind') == 'city-pdf'
                 and metadata.get('parents') == [PARENT]
                 and metadata.get('archive_entry') == ENTRY
                 and hashlib.sha256(bytes(retained)).hexdigest() == CHILD)
        db.execute('''INSERT INTO source_archive_member VALUES(%s,%s,%s)
          ON CONFLICT DO NOTHING''', (PARENT, ENTRY, CHILD))
        _require(db.execute('''SELECT document_id FROM source_archive_member
          WHERE archive_id=%s AND entry_name=%s''', (PARENT, ENTRY)).fetchone() == (CHILD,))
        extract_pages(db, content, CHILD)
        conflict = city_reports._publication_conflict(db, CHILD, rows, VERSION,
                                                      PARENT, ENTRY, native_source=None)
        if conflict is None:
            city_reports.save_classifications(db, CHILD, rows)
            city_reports._bulk_insert(db, 'regional_price', ((CHILD, *row) for row in rows))
            conflict = city_reports._publication_conflict(db, CHILD, rows, VERSION,
                                                          PARENT, ENTRY, require_all=True,
                                                          native_source=None)
        if conflict is None:
            for checkpoint_step, count in ((step, 35), (review_step, 0)):
                db.execute('''INSERT INTO ingestion_checkpoint
                  (document_id,processor_version,step,records) VALUES(%s,%s,%s,%s)
                  ON CONFLICT DO NOTHING''', (PARENT, VERSION, checkpoint_step, count))
                _require(db.execute('''SELECT records FROM ingestion_checkpoint
                  WHERE document_id=%s AND processor_version=%s AND step=%s''',
                  (PARENT, VERSION, checkpoint_step)).fetchone() == (count,))
    if conflict is not None:
        raise ValueError(conflict)
    total = city_reports.publish_city_zip(db, parent_bytes, PARENT, URL, DAY,
                                          processor_version=VERSION)
    _require(total == EXPECTED_TOTAL)
    counts = db.execute('''SELECT count(*) FROM regional_price price
      JOIN source_archive_member member ON member.document_id=price.document_id
      WHERE member.archive_id=%s''', (PARENT,)).fetchone()[0]
    _require(counts == EXPECTED_TOTAL)
    return total, review

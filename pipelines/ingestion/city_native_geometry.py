"""Guarded native recovery for one retained Armenia city-report original.

Missing border segments hide two product cells; a literal Gr unit crosses a
price-cell border. Verify the complete grid before publication. No OCR,
quantity conversion, generic name repair or broad geometry relaxation.
"""
import hashlib
import io
import json
import zipfile
from datetime import date
from decimal import Decimal

import pdfplumber

from pipelines.ingestion.city_unit_overflow import _baseline, _chars_in, _gap

CHILD = 'c0725993f1fbe245a35dc8c097285322952c549fe105e3faa1fbc8023fe0e149'
PARENT = '343f20fb88142be933f1fbc537257f427d40aecd6f59fdb69589b5c05da1c6ed'
DAY = date(2022, 1, 11)
URL = 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-11-01-2022.zip'
ENTRY = 'Armenia 11 ene 22.pdf'
ENTRY_CRC = 3567478468
ENTRY_SIZE = 62189
EXPECTED_GRID_SHA256 = '0b4a9bbc567ce14d3f87086ce24cdccb8d60607bde64cc7eb36ae9380e21244b'
ERROR = 'Reviewed Armenia native geometry changed; retain source review'


def _require(value):
    if not value:
        raise ValueError(ERROR)


def reviewed_tables(page):
    # Run the unchanged ordinary native reader first. No OCR is used.
    from pipelines.ingestion.city_reports import _city_tables

    tables = _city_tables(page)
    shapes = page.find_tables()
    _require(len(tables) == len(shapes) == 1 and page.page_number in (1, 2))
    rows, shape = tables[0], shapes[0]
    _require(len(rows) == len(shape.rows) == (39 if page.page_number == 1 else 23))
    if page.page_number == 1:
        row, cells = rows[32], shape.rows[32].cells
        _require(row == ['Uva Isabela', 'Caja de Cartón', '25 Unidad 454', 'G r 40.000', '42.000', '', ''])
        ub, pb = cells[2], cells[3]
        _require(ub is not None and pb is not None
                 and abs(ub[2] - pb[0]) <= .01 and abs(ub[1] - pb[1]) <= .01
                 and abs(ub[3] - pb[3]) <= .01)
        uc, pc = _chars_in(page, ub), _chars_in(page, pb)
        _require(''.join(c['text'] for c in uc) == '25Unidad454'
                 and ''.join(c['text'] for c in pc) == 'Gr40.000')
        spill, money = pc[:2], pc[2:]
        previous = uc[-1]
        _require(_baseline([previous, *spill]) and _baseline(money)
                 and all(c['fontname'] == previous['fontname'] and abs(c['size'] - previous['size']) <= .2 for c in money)
                 and abs(money[0]['top'] - previous['top']) <= 1.2
                 and abs((money[0]['bottom'] - previous['bottom']) - (money[0]['top'] - previous['top'])) <= .1
                 and -.1 <= _gap(previous, spill[0]) <= 3.5
                 and -.1 <= _gap(spill[0], spill[1]) <= 3.5
                 and 5 <= _gap(spill[-1], money[0]) <= 30
                 and all(-.3 <= _gap(a, b) <= 1.5 for a, b in zip(money, money[1:])))
        row[2], row[3] = '25 Unidad 454 Gr', '40.000'
    else:
        for index, name, rest in (
            (7, 'Habichuela', ['Arroba', '12,5 Kilogramo', '40.000', '45.000', '', '']),
            (9, 'Pimentón', ['Kilogramo', '1 Kilogramo', '2.500', '2.600', '', '']),
        ):
            row, cells = rows[index], shape.rows[index].cells
            _require(row == [None, *rest] and cells[0] is None and cells[1] is not None)
            presentation_box = cells[1]
            product_box = (shape.bbox[0], presentation_box[1], presentation_box[0], presentation_box[3])
            chars = _chars_in(page, product_box)
            _require(''.join(c['text'] for c in chars) == name and _baseline(chars)
                     and all(c['x0'] >= product_box[0] and c['x1'] <= product_box[2]
                             and c['top'] >= product_box[1] and c['bottom'] <= product_box[3] for c in chars)
                     and all(-.1 <= _gap(a, b) <= .1 for a, b in zip(chars, chars[1:])))
            row[0] = name
    return tables


def canonical_grid(rows):
    def value(v):
        if isinstance(v, Decimal):
            return format(v.normalize(), 'f')
        if isinstance(v, date):
            return v.isoformat()
        return v
    return json.dumps([[value(v) for v in row] for row in rows], ensure_ascii=False, separators=(',', ':')).encode()


def validate_rows(rows):
    _require(len(rows) == 53 and all(len(r) == 17 and r[1] == DAY and r[4] == 'Armenia, Mercar' for r in rows))
    _require(hashlib.sha256(canonical_grid(rows)).hexdigest() == EXPECTED_GRID_SHA256)
    return rows


class _ReviewedPage:
    """Supply one exact PDF's reviewed tables to the unchanged city parser."""

    def __init__(self, original):
        self.original = original

    def extract_tables(self, *args, **kwargs):
        _require(not args and not kwargs)
        return reviewed_tables(self.original)

    def __getattr__(self, name):
        return getattr(self.original, name)


def parse_exact_child(data):
    _require(hashlib.sha256(data).hexdigest() == CHILD)
    from . import city_reports

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        _require(len(pdf.pages) == 2)
        rows = list(city_reports.parse_city_pages([_ReviewedPage(page) for page in pdf.pages], DAY))
    return validate_rows(rows)


def _exact_member(parent_bytes):
    with zipfile.ZipFile(io.BytesIO(parent_bytes)) as bundle:
        members = [m for m in bundle.infolist() if not m.is_dir() and m.filename.lower().endswith('.pdf')]
        matching = [m for m in members if m.filename == ENTRY]
        _require(len(members) == 12 and len(matching) == 1)
        member = matching[0]
        _require(member.CRC == ENTRY_CRC and member.file_size == ENTRY_SIZE)
        content = bundle.read(member)
    _require(hashlib.sha256(content).hexdigest() == CHILD)
    return member, content


def _source_identity(db, parent_bytes):
    row = db.execute('''SELECT a.kind,a.observed_on,a.document_id,a.status,
      d.kind,d.source_url,d.media_type,d.metadata,d.content
      FROM ingestion_asset a JOIN source_document d ON d.id=a.document_id
      WHERE a.url=%s''', (URL,)).fetchone()
    _require(row is not None)
    kind, observed_on, document_id, status, source_kind, source_url, media, metadata, retained = row
    _require((kind, observed_on, document_id, source_kind, source_url, media) ==
             ('city-zip', DAY, PARENT, 'original', URL, 'application/zip'))
    _require(status in ('pending', 'review', 'failed', 'complete'))
    _require(metadata.get('ingestion_kind') == 'city-zip')
    _require(hashlib.sha256(bytes(retained)).hexdigest() == PARENT
             and bytes(retained) == parent_bytes)


def publish_exact_parent(db, source_url, parent_bytes, parent_sha256):
    """Publish only the verified Armenia child, then resume 11 ordinary peers."""
    if source_url != URL:
        return None
    _require(parent_sha256 == PARENT and hashlib.sha256(parent_bytes).hexdigest() == PARENT)
    _source_identity(db, parent_bytes)
    member, content = _exact_member(parent_bytes)
    rows = parse_exact_child(content)  # Also required when a checkpoint exists.

    from . import city_reports
    from .pdf_sources import extract_pages
    from .worker import archive, asset_parser_version

    version = asset_parser_version('city-zip', URL)
    _require(version == 'city-v8:jan2022-native-geometry-v1')
    step = city_reports._member_step(member, DAY)
    conflict = None
    with db.transaction():
        # _publication_conflict takes the same child transaction lock used by
        # every ordinary city publication and compares all old locators first.
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
        db.execute('INSERT INTO source_archive_member VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',
                   (PARENT, ENTRY, CHILD))
        _require(db.execute('''SELECT document_id FROM source_archive_member
          WHERE archive_id=%s AND entry_name=%s''', (PARENT, ENTRY)).fetchone() == (CHILD,))
        # The ordinary publisher caches pages before parsing a member. Keep
        # the exact child independently viewable even on a first-time source.
        extract_pages(db, content, CHILD)
        conflict = city_reports._publication_conflict(db, CHILD, rows, version, PARENT, ENTRY,
                                                      native_source=None)
        if conflict is None:
            city_reports.save_classifications(db, CHILD, rows)
            city_reports._bulk_insert(db, 'regional_price', ((CHILD, *row) for row in rows))
            conflict = city_reports._publication_conflict(db, CHILD, rows, version, PARENT,
                                                          ENTRY, require_all=True,
                                                          native_source=None)
        if conflict is None:
            db.execute('''INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records)
              VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING''', (PARENT, version, step, len(rows)))
            _require(db.execute('''SELECT records FROM ingestion_checkpoint
              WHERE document_id=%s AND processor_version=%s AND step=%s''',
              (PARENT, version, step)).fetchone() == (53,))
    if conflict is not None:
        raise ValueError(conflict)
    # The ordinary source-date and publication gates still process every peer.
    total = city_reports.publish_city_zip(db, parent_bytes, PARENT, URL, DAY,
                                          processor_version=version)
    retained_count = db.execute('''SELECT count(*) FROM regional_price price
      JOIN source_archive_member member ON member.document_id=price.document_id
      WHERE member.archive_id=%s''', (PARENT,)).fetchone()[0]
    _require(total == retained_count == 1255)
    return total

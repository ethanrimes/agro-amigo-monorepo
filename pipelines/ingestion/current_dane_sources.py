"""Bounded rechecks of mutable, recent DANE price originals.

The URL remains the asset identity while every changed byte revision keeps its
own immutable source_document, children, prices and checkpoints.
"""
import hashlib
import io
import re
import zipfile
from datetime import date, timedelta
from urllib.parse import urlsplit

from . import city_reports

KINDS = ('city-zip', 'city-pdf', 'daily-zip', 'daily-pdf', 'daily')
PREFIXES = (
    'https://www.dane.gov.co/files/operaciones/SIPSA/',
    'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/',
)
RECENT_DAYS = 3
HOURLY_SLOTS = 2
DAILY_BYTE_KINDS = frozenset((
    'daily', 'daily-pdf', 'daily-zip', 'city-pdf', 'city-zip',
    'dane-weekly-xlsx', 'dane-weekly-pdf', 'monthly', 'monthly-annex',
    'monthly-pdf', 'supply', 'supply-reference', 'supply-reference-pdf',
    'milk', 'milk-pdf', 'inputs', 'inputs-municipal', 'inputs-annex',
    'inputs-reference', 'inputs-pdf', 'rice',
))


def is_recent_dane(url, kind, observed_on, bogota_day):
    return (kind in KINDS and isinstance(observed_on, date)
            and bogota_day - timedelta(days=RECENT_DAYS) <= observed_on <= bogota_day
            and any(url.startswith(prefix) for prefix in PREFIXES)
            and '?' not in url and '#' not in url)


def needs_daily_bytes(url, kind, observed_on, bogota_day):
    """Use real bytes for selected current DANE originals in the six-hour lane.

    Selection and pacing remain with daily_candidates. In particular an old
    supply-reference or input workbook cannot enter merely because its kind is
    generally eligible: it needs a current/previous-year source basename or a
    recent observed day. Publisher archive and index pages are excluded.
    """
    if kind not in DAILY_BYTE_KINDS or not any(url.startswith(p) for p in PREFIXES):
        return False
    if '#' in url:
        return False
    name = urlsplit(url).path.rsplit('/', 1)[-1].lower()
    if not name.endswith(('.xls', '.xlsx', '.pdf', '.zip', '.csv')):
        return False
    if isinstance(observed_on, date) and bogota_day - timedelta(days=70) <= observed_on <= bogota_day:
        return True
    return bool(re.search(r'(?<!\d)(?:' + str(bogota_day.year) + r'|'
                          + str(bogota_day.year - 1) + r')(?!\d)', name))


def retained_unfinished(db, url, kind, observed_on, version, bogota_day):
    """Resume a validated pending original before asking a mutable URL again."""
    if not is_recent_dane(url, kind, observed_on, bogota_day):
        return None
    row = db.execute('''SELECT a.status,a.processor_version,a.error,a.attempts,a.records,
      d.id,d.kind,d.source_url,
      d.media_type,d.metadata,d.content FROM ingestion_asset a JOIN source_document d
      ON d.id=a.document_id WHERE a.url=%s AND a.kind=%s AND a.observed_on=%s
      AND a.status IN ('pending','failed') ''', (url, kind, observed_on)).fetchone()
    if row is None:
        return None
    (status, prior_version, error, _attempts, records, did, source_kind,
     source_url, media, metadata, content) = row
    if (status == 'failed' and not (error or '').startswith(
            ('RuntimeError:', 'OperationalError:'))):
        return None
    if (error or '').startswith('HostRateLimited:'):
        return None
    if kind != 'city-zip' and records:
        return None
    if prior_version not in ('', version) or source_kind != 'original' or source_url != url:
        raise ValueError('Recent DANE retained source identity changed')
    if (metadata.get('ingestion_kind') != kind or metadata.get('retention') != 'permanent'
            or metadata.get('original_filename') != url.rsplit('/', 1)[-1]):
        raise ValueError('Recent DANE retained source metadata changed')
    expected_media = ('application/zip' if kind.endswith('-zip') else
                      'application/pdf' if kind.endswith('-pdf') else
                      'application/vnd.ms-excel' if url.lower().endswith('.xls') else
                      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    if media != expected_media:
        raise ValueError('Recent DANE retained source media changed')
    body = bytes(content)
    if hashlib.sha256(body).hexdigest() != did:
        raise ValueError('Recent DANE retained source bytes changed')
    if kind == 'city-zip':
        with zipfile.ZipFile(io.BytesIO(body)) as bundle:
            members = [member for member in bundle.infolist()
                       if not member.is_dir() and member.filename.lower().endswith('.pdf')]
            if not members or len(members) > 500:
                raise ValueError('Recent DANE retained city member list changed')
            by_step = {city_reports._member_step(member, observed_on): member
                       for member in members}
            if len(by_step) != len(members):
                raise ValueError('Recent DANE retained city member steps collide')
            member_ids = {member.filename: hashlib.sha256(bundle.read(member)).hexdigest()
                          for member in members}
        completed = db.execute('''SELECT step,records FROM ingestion_checkpoint
          WHERE document_id=%s AND processor_version=%s AND step=ANY(%s::text[])''',
          (did, version, list(by_step))).fetchall()
        # A crash after the final member checkpoint can still leave the
        # asset pending/failed before its parent status and count were saved.
        # Finish that retained revision before observing newer URL bytes.
        if completed:
            stored = {entry: (child_id, count) for entry, child_id, count in db.execute('''SELECT m.entry_name,m.document_id,count(r.source_locator)
              FROM source_archive_member m LEFT JOIN regional_price r
              ON r.document_id=m.document_id WHERE m.archive_id=%s
              GROUP BY m.entry_name,m.document_id''', (did,)).fetchall()}
            for step, count in completed:
                member = by_step[step]
                child_id = member_ids[member.filename]
                if stored.get(member.filename) != (child_id, count):
                    raise ValueError('Recent DANE retained member checkpoint changed')
    return body

"""Direct, publisher-linked DANE city PDFs with full native-source parity."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from urllib.parse import urlparse

from pipelines.ingestion import city_reports, worker
from pipelines.ingestion.pdf_sources import extract_pages

KIND = "city-pdf"
VERSION = "city-direct-pdf-v1"
COMPLETE_STEP = "city-direct:complete"
_DATE_NUMERIC = re.compile(r"(?:^|[/_-])(\d{1,2})-(\d{1,2})-(20\d{2})\.pdf$", re.I)


def linked_city_pdf_day(url: str, label: str) -> date | None:
    """Classify only dated official daily-index city links; no URL invention."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    if parsed.scheme != "https" or parsed.hostname not in ("www.dane.gov.co", "dane.gov.co"):
        return None
    if not path.startswith("/files/") or not path.endswith(".pdf"):
        return None
    stem = path.rsplit("/", 1)[-1]
    # The concrete 2024 family and older regional/city PDF filenames are
    # admitted only from the official daily-index link context. The PDF's
    # printed identity remains the final publication gate.
    if not (
        stem.startswith("bol-sipsadiario-regionales-")
        or stem.startswith("bol-reg-")
        or stem.startswith("sipsa-regionales-")
        or stem.startswith("sipsa-ciudades-")
    ):
        return None
    if not re.search(r"regional|ciudad", label, re.I):
        return None
    try:
        day = worker.date_from_text(path) or worker.date_from_text(label)
    except ValueError:
        return None
    if day is None:
        match = _DATE_NUMERIC.search(path)
        if match:
            try:
                day = date(int(match[3]), int(match[2]), int(match[1]))
            except ValueError:
                return None
    return day if day is not None and day <= worker.today() else None


def queue_linked_city_pdf(db, url, day):
    """Retype only an untouched misclassified pending asset or retain this kind."""
    row = db.execute(
        "INSERT INTO ingestion_asset(url,kind,observed_on) VALUES(%s,%s,%s) "
        "ON CONFLICT(url) DO UPDATE SET kind=excluded.kind "
        "WHERE ingestion_asset.observed_on=excluded.observed_on AND ("
        "ingestion_asset.kind=%s OR (ingestion_asset.kind='daily-pdf' "
        "AND ingestion_asset.status='pending' "
        "AND ingestion_asset.document_id IS NULL "
        "AND ingestion_asset.records=0 AND ingestion_asset.attempts=0)) "
        "RETURNING url",
        (url, KIND, day, KIND),
    ).fetchone()
    return row is not None


def migrate_discovered_city_pdf_assets(db, limit=100):
    """Retype exact already-discovered untouched assets, including old index links.

    No URLs are created here. The strict filename date must equal the date
    recorded when the official daily index originally discovered each asset.
    """
    limit = max(0, min(int(limit), 100))
    if not limit:
        return 0
    candidates = db.execute(
        "SELECT url,observed_on FROM ingestion_asset "
        "WHERE kind='daily-pdf' AND status='pending' AND document_id IS NULL "
        "AND records=0 AND attempts=0 AND observed_on IS NOT NULL "
        "AND url LIKE 'https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-%%.pdf' "
        "ORDER BY observed_on,url LIMIT %s",
        (limit,),
    ).fetchall()
    migrated = 0
    for url, day in candidates:
        if not re.fullmatch(
            r"https://www\.dane\.gov\.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-"
            r"\d{1,2}[a-z]{3}20\d{2}\.pdf",
            url,
        ):
            continue
        try:
            url_day = worker.date_from_text(url)
        except ValueError:
            continue
        if url_day != day or day > worker.today():
            continue
        migrated += queue_linked_city_pdf(db, url, day)
    return migrated


def _bound_asset(db, url, day):
    row = db.execute(
        "SELECT kind,observed_on,status,document_id FROM ingestion_asset WHERE url=%s",
        (url,),
    ).fetchone()
    if row is None or row[0] != KIND or row[1] != day:
        raise ValueError("Direct city PDF asset URL/kind/day binding changed")
    return row


def _retained_source(db, did, url, body):
    row = db.execute(
        "SELECT source_url,media_type,kind,metadata,content,page_count "
        "FROM source_document WHERE id=%s", (did,),
    ).fetchone()
    if row is None or (
        row[0] != url or row[1] != "application/pdf" or row[2] != "original"
        or row[3].get("ingestion_kind") != KIND
        or row[3].get("parents") is not None
        or row[3].get("archive_entry") is not None
        or row[3].get("retention") != "permanent"
        or bytes(row[4]) != body
        or hashlib.sha256(bytes(row[4])).hexdigest() != did
        or not row[5]
    ):
        raise ValueError("Direct city PDF retained source identity changed")
    return row[5]


def retained_replay(db, url, day):
    """Resume an incomplete exact original before another network fetch."""
    kind, observed, status, did = _bound_asset(db, url, day)
    if did is None or status not in ("pending", "failed", "review", "awaiting-ocr"):
        return None
    row = db.execute("SELECT content FROM source_document WHERE id=%s", (did,)).fetchone()
    if row is None:
        raise ValueError("Direct city PDF retained pointer is missing")
    body = bytes(row[0])
    _retained_source(db, did, url, body)
    # A concluded native conflict/review must be able to revalidate this
    # mutable publisher URL. Only unfinished parsing and OCR replay old bytes.
    if status in ("failed", "review"):
        return None
    complete = db.execute(
        "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
        "AND processor_version=%s AND step=%s",
        (did, VERSION, COMPLETE_STEP),
    ).fetchone()
    if complete is not None:
        return None
    return body


def _asset_status(db, url, did, status, records, error=None):
    db.execute(
        "UPDATE ingestion_asset SET document_id=%s,status=%s,records=%s,"
        "processor_version=%s,checked_at=now(),attempts=attempts+1,error=%s "
        "WHERE url=%s AND kind=%s",
        (did, status, records, VERSION, error, url, KIND),
    )


def completed_source_is_still_valid(db, url, day, did, records):
    """Guard an unchanged complete asset against stale/mismatched source rows."""
    kind, observed, status, pointer = _bound_asset(db, url, day)
    if status != "complete" or pointer != did or records <= 0:
        raise ValueError("Direct city completed asset binding changed")
    original = db.execute(
        "SELECT content FROM source_document WHERE id=%s", (did,),
    ).fetchone()
    if original is None:
        raise ValueError("Direct city completed original is missing")
    body = bytes(original[0])
    _retained_source(db, did, url, body)
    checkpoint = db.execute(
        "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
        "AND processor_version=%s AND step=%s", (did, VERSION, COMPLETE_STEP),
    ).fetchone()
    if checkpoint != (records,):
        raise ValueError("Direct city completed checkpoint changed")
    rows = list(city_reports.parse_archived_city_pdf(db, body, did, day))
    if len(rows) != records or any(len(row) != 17 or row[1] != day for row in rows):
        raise ValueError("Direct city completed native grid changed")
    with db.transaction():
        conflict = city_reports._publication_conflict(
            db, did, rows, VERSION, require_all=True,
        )
    # Commit the source-wide conflict marker before surfacing the failure.
    # Otherwise the public projection could continue serving stale rows.
    if conflict is not None:
        raise ValueError(conflict)
    return True


def process_direct_city_pdf(db, url, body, day, *, archived_did=None):
    """Retain exact PDF and publish only a complete, parity-checked 17-field source."""
    _bound_asset(db, url, day)
    if not isinstance(body, bytes) or not body.startswith(b"%PDF-"):
        raise ValueError("Direct city source is not PDF bytes")
    did = hashlib.sha256(body).hexdigest()
    archived = (
        archived_did if archived_did is not None
        else worker.archive(db, url, body, KIND, day, register_alias=False)
    )
    if archived != did:
        raise ValueError("Direct city archive SHA changed")
    _retained_source(db, did, url, body)
    extract_pages(db, body, did)
    try:
        rows = list(city_reports.parse_archived_city_pdf(db, body, did, day))
    except ValueError as exc:
        message = str(exc)
        if re.fullmatch(r"City PDF pages \[[0-9, ]+\] await agreeing OCR readings", message):
            # parse_archived_city_pdf enqueues only failed native pages under
            # source_kind=city-pdf. The OCR drain must call resume after an
            # independently agreeing pair, not publish a partial PDF.
            with db.transaction():
                _asset_status(db, url, did, "awaiting-ocr", 0, message)
            return {"status": "awaiting-ocr", "rows": 0, "document_id": did}
        with db.transaction():
            _asset_status(db, url, did, "review", 0, message[:1000])
        return {"status": "review", "rows": 0, "document_id": did, "error": message}
    if not rows or any(len(row) != 17 or row[1] != day for row in rows):
        with db.transaction():
            _asset_status(db, url, did, "review", 0, "No complete direct city price rows on printed day")
        return {"status": "review", "rows": 0, "document_id": did}
    with db.transaction():
        conflict = city_reports._publication_conflict(db, did, rows, VERSION)
        if conflict is None:
            city_reports.save_classifications(db, did, rows)
            city_reports._bulk_insert(db, "regional_price", ((did, *row) for row in rows))
            conflict = city_reports._publication_conflict(
                db, did, rows, VERSION, require_all=True,
            )
        if conflict is None:
            db.execute(
                "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
                "VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (did, VERSION, COMPLETE_STEP, len(rows)),
            )
            checkpoint = db.execute(
                "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
                "AND processor_version=%s AND step=%s",
                (did, VERSION, COMPLETE_STEP),
            ).fetchone()
            if checkpoint != (len(rows),):
                raise ValueError("Direct city PDF checkpoint count changed")
            _asset_status(db, url, did, "complete", len(rows))
            db.execute(
                "UPDATE source_ocr_task SET status='published',checked_at=now(),error=NULL "
                "WHERE document_id=%s AND source_kind='city-pdf' AND status='verified'",
                (did,),
            )
        else:
            _asset_status(db, url, did, "review", 0, conflict)
    return {
        "status": "review" if conflict else "complete",
        "rows": 0 if conflict else len(rows),
        "document_id": did,
        **({"error": conflict} if conflict else {}),
    }


def resume_after_ocr(db, did):
    """Proposed OCR-drain hook for direct assets, after agreeing readings exist."""
    assets = db.execute(
        "SELECT url,observed_on,status,records FROM ingestion_asset "
        "WHERE document_id=%s AND kind=%s", (did, KIND),
    ).fetchall()
    if not assets:
        return None
    if len(assets) != 1:
        raise ValueError("Direct city OCR document has ambiguous asset identity")
    url, day, status, records = assets[0]
    original = db.execute("SELECT content FROM source_document WHERE id=%s", (did,)).fetchone()
    if original is None:
        raise ValueError("Direct city OCR source original is missing")
    body = bytes(original[0])
    _retained_source(db, did, url, body)
    if status == 'complete':
        checkpoint = db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step=%s",
            (did, VERSION, COMPLETE_STEP),
        ).fetchone()
        if checkpoint != (records,) or records <= 0:
            raise ValueError("Direct city OCR completion has no matching whole-source checkpoint")
        return {"status": "complete", "rows": records, "document_id": did}
    if status in ('review', 'failed'):
        return {"status": "review", "rows": 0, "document_id": did}
    if status not in ('awaiting-ocr', 'pending'):
        raise ValueError("Direct city OCR asset status is unsupported")
    return process_direct_city_pdf(db, url, body, day, archived_did=did)

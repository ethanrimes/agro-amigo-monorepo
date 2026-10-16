"""Bounded hourly scan of retained city PDFs for exact-source name corrections."""

import logging
import time

import psycopg
from pdfminer.pdfexceptions import PDFException

from .city_product_corrections import (
    VERSION as CORRECTION_VERSION,
    _regional_rows,
    apply_corrections,
    load_original,
    verified_corrections,
)
from .label_normalization import LEXICON, key as label_key
from .worker import slug

LOG = logging.getLogger(__name__)
# Revisit terminal scan evidence after isolating name-only glyph verification.
# The immutable correction method/version itself is unchanged.
VERSION = CORRECTION_VERSION + ":product-cells-only-v2"
MAX_PER_RUN = 250
COOLDOWN_SECONDS = 3600
PAGE_SIZE = 64
SELECTION_SECONDS = 20
PRIORITY_LIMIT = 16
MIN_FIFO = 180
PRIORITY_SECONDS = 8
MAX_PRODUCT_METADATA = 5000
# Exact old terminal review predates the verified dual-store source check.
# This append-only revision is limited to the independently retained original.
WRAPPED_PDF_RECOVERY_VERSION = VERSION + ":exact-rtfd-wrapper-v1"
WRAPPED_PDF_DID = "373bd8410358196648af87471c9f6a061960b0d06e85ee612c1409e7635dd776"
WRAPPED_PDF_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "sipsa-16-08-2021.zip"
)
WRAPPED_PDF_OLD_REASON = "Archived city PDF bytes differ from immutable SHA-256"


def _compact_reviewed_food_ids():
    """Suspicious IDs only; this never supplies a corrected name or identity."""
    names = {}
    for name in LEXICON["domains"]["product"]:
        canonical = slug(name)
        if " " not in name or "-" not in canonical:
            continue
        compact = canonical.replace("-", "")
        if compact != canonical:
            names.setdefault(compact, set()).add(canonical)
    # An ambiguous compact spelling is not a safe priority signal.
    return tuple(sorted(key for key, matches in names.items() if len(matches) == 1))


COMPACT_FOOD_IDS = _compact_reviewed_food_ids()


def _reviewed_food_keys():
    names = {}
    for name in LEXICON["domains"]["product"]:
        names.setdefault(label_key(name).replace(" ", ""), set()).add(name)
    return {compact: next(iter(matches)) for compact, matches in names.items()
            if len(matches) == 1}


REVIEWED_FOOD_KEYS = _reviewed_food_keys()


def _priority_ids_from_products(rows):
    """Match a whole reviewed food name with only native spacing missing."""
    ids = set()
    for ident, literal in rows:
        canonical = REVIEWED_FOOD_KEYS.get(label_key(literal).replace(" ", ""))
        if canonical and ident == slug(literal) and ident != slug(canonical):
            ids.add(ident)
    return sorted(ids)


def priority_query(limit, cooldown_seconds=COOLDOWN_SECONDS):
    """Seek only indexed product IDs, then apply the ordinary scan guards."""
    return (
        """WITH matched AS MATERIALIZED (
            SELECT DISTINCT r.document_id
            FROM regional_price r
            WHERE r.product_id=ANY(%s::text[])
        ), eligible AS MATERIALIZED (
            SELECT m.document_id
            FROM matched m
            WHERE NOT EXISTS (
                SELECT 1 FROM city_product_scan s
                WHERE s.document_id=m.document_id AND s.scan_version=%s
                  AND s.status IN ('complete','review')
            )
              AND NOT EXISTS (
                SELECT 1 FROM city_product_scan s
                WHERE s.document_id=m.document_id AND s.scan_version=%s
                  AND s.status='retry'
                  AND s.scanned_at>now()-(%s * interval '1 second')
            )
        )
        SELECT d.id,d.source_url
        FROM eligible e
        CROSS JOIN LATERAL (
            SELECT sd.id,sd.source_url,sd.metadata->>'ingestion_kind' AS ingestion_kind
            FROM source_document sd
            WHERE sd.id=e.document_id
            OFFSET 0
        ) d
        WHERE d.ingestion_kind='city-pdf'
        ORDER BY d.id
        LIMIT %s""",
        (VERSION, VERSION, cooldown_seconds, limit),
    )


def select_priority_candidates(db, limit, *, deadline=None, cooldown_seconds=COOLDOWN_SECONDS):
    if not limit or not COMPACT_FOOD_IDS:
        return [], None
    selection_deadline = time.monotonic() + PRIORITY_SECONDS
    if deadline is not None:
        selection_deadline = min(selection_deadline, deadline)
    if time.monotonic() >= selection_deadline:
        return [], None
    try:
        with db.transaction():
            _timeout(db, selection_deadline, 4000)
            products = db.execute(
                "SELECT id,name FROM product ORDER BY id LIMIT %s",
                (MAX_PRODUCT_METADATA + 1,),
            ).fetchall()
            if len(products) > MAX_PRODUCT_METADATA:
                # Never scan an unbounded product table. Exact compact IDs
                # retain the old bounded fast path when metadata outgrows it.
                _timeout(db, selection_deadline, 4000)
                products = db.execute(
                    "SELECT id,name FROM product WHERE id=ANY(%s::text[]) ORDER BY id",
                    (list(COMPACT_FOOD_IDS),),
                ).fetchall()
            existing = _priority_ids_from_products(products)
            if not existing:
                return [], None
            _timeout(db, selection_deadline, 4000)
            sql, params = priority_query(limit, cooldown_seconds)
            found = db.execute(sql, (existing, *params)).fetchall()
        return found, None
    except psycopg.Error as exc:
        LOG.warning("City product priority seek failed: %s", type(exc).__name__)
        return [], "priority:" + type(exc).__name__


def candidate_query(limit, cooldown_seconds=COOLDOWN_SECONDS):
    """Find published city PDFs without terminal evidence; no PDF bytes loaded."""
    return (
        """SELECT d.id,d.source_url FROM source_document d
        WHERE d.metadata->>'ingestion_kind'='city-pdf'
          AND EXISTS(SELECT 1 FROM regional_price r WHERE r.document_id=d.id)
          AND NOT EXISTS(SELECT 1 FROM city_product_scan s
            WHERE s.document_id=d.id AND s.scan_version=%s
              AND s.status IN ('complete','review'))
          AND NOT EXISTS(SELECT 1 FROM city_product_scan s
            WHERE s.document_id=d.id AND s.scan_version=%s
              AND s.status='retry'
              AND s.scanned_at>now()-(%s * interval '1 second'))
        ORDER BY d.id LIMIT %s""",
        (VERSION, VERSION, cooldown_seconds, limit),
    )


def candidate_page_query(after, page_size, cooldown_seconds=COOLDOWN_SECONDS):
    """Check only one ordered city-PDF page, including ineligible IDs.

    Returning every page member is essential: the caller advances past checked
    terminal/retry documents even when a page has no eligible documents.
    MATERIALIZED prevents the eligibility joins from escaping the page limit.
    """
    return (
        """WITH page AS MATERIALIZED (
            SELECT d.id,d.source_url FROM source_document d
            WHERE d.metadata->>'ingestion_kind'='city-pdf' AND d.id>%s
            ORDER BY d.id LIMIT %s
        )
        SELECT p.id,p.source_url,
          EXISTS(SELECT 1 FROM regional_price r WHERE r.document_id=p.id)
          AND NOT EXISTS(SELECT 1 FROM city_product_scan s
            WHERE s.document_id=p.id AND s.scan_version=%s
              AND s.status IN ('complete','review'))
          AND NOT EXISTS(SELECT 1 FROM city_product_scan s
            WHERE s.document_id=p.id AND s.scan_version=%s
              AND s.status='retry'
              AND s.scanned_at>now()-(%s * interval '1 second'))
          AS eligible
        FROM page p ORDER BY p.id""",
        (after, page_size, VERSION, VERSION, cooldown_seconds),
    )


def select_candidates(db, limit, *, deadline=None, cooldown_seconds=COOLDOWN_SECONDS):
    """Reserve most slots for FIFO; priority only changes document order."""
    priority_cap = min(PRIORITY_LIMIT, max(0, limit - MIN_FIFO))
    candidates, priority_error = select_priority_candidates(
        db, priority_cap, deadline=deadline, cooldown_seconds=cooldown_seconds
    )
    seen = {did for did, _ in candidates}
    after = ""
    page_size = PAGE_SIZE
    selection_deadline = time.monotonic() + SELECTION_SECONDS
    if deadline is not None:
        selection_deadline = min(selection_deadline, deadline)
    error = priority_error
    while len(candidates) < limit and time.monotonic() < selection_deadline:
        size = page_size
        try:
            with db.transaction():
                _timeout(db, selection_deadline, 5000)
                page = db.execute(
                    *candidate_page_query(after, size, cooldown_seconds)
                ).fetchall()
        except psycopg.errors.QueryCanceled:
            if size == 1:
                error = "QueryCanceled"
                break
            page_size = max(1, size // 2)
            continue  # Retry the same key; no page member has been skipped.
        except psycopg.Error as exc:
            error = type(exc).__name__
            break
        if not page:
            break
        after = page[-1][0]
        for did, url, eligible in page:
            if eligible and did not in seen:
                candidates.append((did, url))
                seen.add(did)
    return candidates[:limit], error


def select_integrity_recovery(db, *, deadline=None):
    """One indexed, source-bound replay after exact wrapped-PDF recognition."""
    if deadline is not None and time.monotonic() >= deadline:
        return None
    with db.transaction():
        _timeout(db, deadline, 4000)
        return db.execute(
            """SELECT d.id,d.source_url FROM source_document d
            WHERE d.id=%s AND d.source_url=%s AND d.kind='original'
              AND d.publisher='DANE' AND d.media_type='application/pdf'
              AND d.metadata->>'ingestion_kind'='city-pdf'
              AND EXISTS (SELECT 1 FROM regional_price r WHERE r.document_id=d.id)
              AND EXISTS (SELECT 1 FROM city_product_scan s WHERE s.document_id=d.id
                AND s.scan_version=%s AND s.status='review' AND s.reason_code=%s)
              AND NOT EXISTS (SELECT 1 FROM city_product_scan s WHERE s.document_id=d.id
                AND s.scan_version=%s AND s.status IN ('complete','review'))
              AND NOT EXISTS (SELECT 1 FROM city_product_scan s WHERE s.document_id=d.id
                AND s.scan_version=%s AND s.status='retry'
                AND s.scanned_at>now()-(%s * interval '1 second'))
            LIMIT 1""",
            (WRAPPED_PDF_DID, WRAPPED_PDF_URL, VERSION,
             WRAPPED_PDF_OLD_REASON, WRAPPED_PDF_RECOVERY_VERSION,
             WRAPPED_PDF_RECOVERY_VERSION, COOLDOWN_SECONDS),
        ).fetchone()


def _timeout(db, deadline, maximum_ms):
    remaining = maximum_ms
    if deadline is not None:
        remaining = min(remaining, max(1, int((deadline - time.monotonic()) * 1000)))
    db.execute("SELECT set_config('statement_timeout',%s,true)", (str(remaining),))


def _mark(db, did, source_url, status, *, storage=None, candidates=0, inserted=0, reason=None, scan_version=VERSION):
    db.execute(
        """INSERT INTO city_product_scan(
        document_id,scan_version,status,source_sha256,source_url,storage,
        candidate_rows,inserted_rows,reason_code)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (did, scan_version, status, did, source_url, storage, candidates, inserted, reason),
    )


def drain(db, *, storage_connection, limit=MAX_PER_RUN, deadline=None):
    """Commit each PDF's corrections and scan evidence together.

    A deterministic source/parity failure gets a terminal review for this scan
    version. Transport/database failures are immutable retry evidence with an
    hourly cooldown. The next scan version can revisit either outcome.
    """
    limit = max(0, min(int(limit), MAX_PER_RUN))
    summary = {
        "selected": 0,
        "completed": 0,
        "review": 0,
        "retry": 0,
        "corrections": 0,
        "deferred": 0,
        "errors": [],
    }
    if not limit or (deadline is not None and time.monotonic() >= deadline):
        return summary
    if not storage_connection:
        summary["errors"].append({"phase": "configuration", "error": "Azure Blob storage is unavailable"})
        return summary
    recovery = None
    try:
        recovery = select_integrity_recovery(db, deadline=deadline)
    except psycopg.Error as exc:
        summary["errors"].append({"phase": "integrity-recovery-selection",
                                  "error_type": type(exc).__name__})
    candidates, selection_error = select_candidates(
        db, limit - bool(recovery), deadline=deadline
    )
    candidates = ([(recovery[0], recovery[1], WRAPPED_PDF_RECOVERY_VERSION)]
                  if recovery else []) + [(did, url, VERSION) for did, url in candidates]
    if selection_error:
        summary["errors"].append({"phase": "selection", "error_type": selection_error})
        LOG.warning("City product scan selection failed: %s", selection_error)
    summary["selected"] = len(candidates)
    for did, source_url, scan_version in candidates:
        if deadline is not None and time.monotonic() >= deadline:
            summary["deferred"] += 1
            continue
        storage = None
        try:
            body, storage = load_original(
                db, did, storage_connection=storage_connection, request_timeout=20,
                expected_source_url=source_url
            )
            corrections = verified_corrections(
                body, did, source_url, _regional_rows(db, did)
            )
            if deadline is not None and time.monotonic() >= deadline:
                summary["deferred"] += 1
                continue
            with db.transaction():
                _timeout(db, deadline, 15000)
                if not db.execute(
                    "SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0))",
                    ("city-product-scan:" + did + ":" + scan_version,),
                ).fetchone()[0]:
                    summary["deferred"] += 1
                    continue
                if db.execute(
                    """SELECT 1 FROM city_product_scan WHERE document_id=%s
                    AND scan_version=%s AND status IN ('complete','review') LIMIT 1""",
                    (did, scan_version),
                ).fetchone():
                    continue
                inserted = apply_corrections(db, corrections)
                _mark(
                    db, did, source_url, "complete", storage=storage,
                    candidates=len(corrections), inserted=inserted, scan_version=scan_version,
                )
            summary["completed"] += 1
            summary["corrections"] += inserted
        except Exception as exc:  # noqa: BLE001 - isolate malformed archived PDFs and parser failures.
            # Statement cancellation rolls back this document's transaction;
            # retain a retry checkpoint and continue the run. QueryCanceled
            # inherits OperationalError, but does not imply a lost connection.
            if isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError)) \
                    and not isinstance(exc, psycopg.errors.QueryCanceled):
                raise
            deterministic = isinstance(exc, (ValueError, PDFException))
            status = "review" if deterministic else "retry"
            reason = (
                str(exc)[:200] if isinstance(exc, ValueError) else type(exc).__name__
            )
            summary[status] += 1
            summary["errors"].append(
                {"document_id": did, "status": status, "reason": reason}
            )
            LOG.warning("City product scan %s %s: %s", did, status, reason)
            try:
                with db.transaction():
                    _timeout(db, deadline, 5000)
                    _mark(db, did, source_url, status, storage=storage, reason=reason,
                          scan_version=scan_version)
            except psycopg.Error as mark_error:
                summary["errors"].append(
                    {"document_id": did, "phase": "checkpoint", "error_type": type(mark_error).__name__}
                )
    return summary

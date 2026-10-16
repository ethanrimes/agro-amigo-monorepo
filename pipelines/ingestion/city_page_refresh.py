"""Bounded observation and byte rechecks for DANE city ZIP sources.

The existing worker cycle polls a bounded page and refreshes at most one
registered archive body. Hints never change the published asset or cohort;
source validation and normal publication rules remain authoritative.
"""

from __future__ import annotations

import hashlib
import io
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from .city_page_revision_hint import parse_current_month_rows


POLL_INTERVAL = timedelta(hours=24)
MIN_RETRY = timedelta(hours=6)
MAX_PAGE_SLOTS = 1
MAX_BODY_REFRESHES_PER_CYCLE = 1
HOURLY_CYCLES_PER_DAY = 24
NEWEST_DAILY_SLOTS = 1
OLDER_SLOTS_PER_DAY = HOURLY_CYCLES_PER_DAY - NEWEST_DAILY_SLOTS
PERIODIC_LATEST_INTERVAL = timedelta(days=1)
PERIODIC_ROTATION_INTERVAL = timedelta(days=30)
PERIODIC_ROTATION_CAPACITY_30D = OLDER_SLOTS_PER_DAY * 30
MAX_PAGE_BODY_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_BODY_REFRESH_TRANSFER_BYTES_PER_CYCLE = MAX_ARCHIVE_BYTES
MAX_BODY_REFRESH_SOFT_SECONDS = 180
STREAM_CHUNK_BYTES = 64 * 1024
DANE_HOST = "www.dane.gov.co"


@dataclass(frozen=True)
class DownloadedSource:
    body: bytes
    etag: str | None
    last_modified: str | None
    content_type: str | None = None
    response_url: str | None = None
    response_status: int | None = None


class OversizedSourceResponse(ValueError):
    def __init__(self, response, limit: int, bytes_read: int):
        self.response_status = getattr(response, "status_code", None)
        self.content_type = response.headers.get("Content-Type")
        self.response_url = getattr(response, "url", None)
        self.limit = limit
        self.bytes_read = bytes_read
        super().__init__(f"unconditional city refresh exceeds {limit} bytes")


class RefreshBudgetExpired(TimeoutError):
    pass


def _download_unconditionally(
    worker, url: str, *, max_bytes: int = MAX_ARCHIVE_BYTES,
    max_duration_seconds: float = MAX_BODY_REFRESH_SOFT_SECONDS,
    budget_expired=None,
) -> DownloadedSource:
    """Stream under a byte cap and cooperative wallclock/run deadline.

    The callback is checked before every iterator read, so a caller can stop
    before another network chunk is consumed when its existing cycle budget
    expires. Per-attempt timeouts use the remaining worker deadline. The
    worker's session may retry 5xx responses with that same per-attempt
    timeout, so an HTTP call can outlive the overall deadline; such a response
    is discarded immediately after the call returns. No response.content
    access is used.
    """
    max_bytes = min(MAX_ARCHIVE_BYTES, max(0, int(max_bytes)))
    max_duration_seconds = min(
        MAX_BODY_REFRESH_SOFT_SECONDS, max(0.0, float(max_duration_seconds))
    )
    deadline = time.monotonic() + max_duration_seconds
    run_deadline_context = getattr(worker, "RUN_DEADLINE", None)
    if run_deadline_context is not None:
        run_deadline = run_deadline_context.get()
        if run_deadline is not None:
            deadline = min(deadline, float(run_deadline))

    def expired(bytes_read: int) -> bool:
        return time.monotonic() >= deadline or bool(
            budget_expired is not None and budget_expired(bytes_read)
        )

    if expired(0):
        raise RefreshBudgetExpired("city refresh wallclock budget expired before request")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RefreshBudgetExpired("city refresh run deadline expired before request")
    # requests applies these timeouts per adapter attempt. Session-level 5xx
    # retries can therefore outlive this deadline; the response is discarded
    # as soon as the call returns and the deadline check below runs.
    request_timeout = (min(20.0, remaining), min(120.0, remaining))
    response = worker._get(
        url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
        stream=True, timeout=request_timeout,
    )
    try:
        if expired(0):
            raise RefreshBudgetExpired("city refresh run deadline expired during request")
        if response.status_code == 304:
            raise ValueError("unconditional city refresh returned 304 without bytes")
        response.raise_for_status()
        body = bytearray()
        chunks = iter(response.iter_content(chunk_size=STREAM_CHUNK_BYTES))
        while True:
            if expired(len(body)):
                raise RefreshBudgetExpired(
                    f"city refresh wallclock budget expired after {len(body)} bytes"
                )
            try:
                chunk = next(chunks)
            except StopIteration:
                break
            # A slow blocking read must not let bytes cross an expired cycle
            # deadline into the parser or source-retention path.
            if expired(len(body)):
                raise RefreshBudgetExpired(
                    f"city refresh run deadline expired while reading after {len(body)} bytes"
                )
            if not chunk:
                continue
            if len(body) + len(chunk) > max_bytes:
                raise OversizedSourceResponse(response, max_bytes, len(body))
            body.extend(chunk)
        if expired(len(body)):
            raise RefreshBudgetExpired(
                f"city refresh run deadline expired before accepting response after {len(body)} bytes"
            )
        if not body:
            raise ValueError("unconditional city refresh body is empty")
        return DownloadedSource(
            bytes(body), response.headers.get("ETag"),
            response.headers.get("Last-Modified"),
            response.headers.get("Content-Type"), getattr(response, "url", url),
            response.status_code,
        )
    finally:
        response.close()


def _classify_zip_body(body: bytes, content_type: str | None) -> str | None:
    """Return None for a readable ZIP; classify rejected HTTP bodies for audit."""
    prefix = bytes(body[:512]).lstrip().lower()
    if ((content_type or "").split(";", 1)[0].strip().lower() in
            ("text/html", "application/xhtml+xml")
            or prefix.startswith((b"<!doctype html", b"<html", b"<?xml"))):
        return "html"
    if zipfile.is_zipfile(io.BytesIO(body)):
        return None
    if body.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return "truncated_zip"
    return "other_non_zip"


def _official_final_url(response_url: str, requested_url: str) -> bool:
    actual, requested = urlparse(response_url), urlparse(requested_url)
    if not _official_city_zip_url(requested_url):
        return False
    try:
        actual_port = actual.port
    except ValueError:
        return False
    if (actual.scheme != "https" or actual.hostname != requested.hostname
            or actual.path != requested.path or actual.query
            or actual.username or actual.password or actual_port not in (None, 443)
            or actual.fragment):
        return False
    return (requested.scheme == "https" and requested.hostname == "www.dane.gov.co"
            and requested.query == "" and requested.fragment == ""
            and requested.username is None and requested.password is None)


def _candidate_day_classification(body: bytes, requested_day: date) -> str | None:
    """Check every changed member's readable printed title before source binding."""
    import pdfplumber
    from pipelines.ingestion.worker import date_from_text

    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            members = [m for m in archive.infolist()
                       if not m.is_dir() and m.filename.lower().endswith(".pdf")]
            if not members or len(members) > 500 or sum(m.file_size for m in members) > MAX_ARCHIVE_BYTES:
                return "invalid_zip_members"
            printed_days = set()
            for member in members:
                content = archive.read(member)
                with pdfplumber.open(io.BytesIO(content)) as pdf:
                    text = pdf.pages[0].extract_text() if pdf.pages else None
                printed_day = date_from_text(text or "")
                if printed_day is None:
                    return "unverifiable_member_date"
                if printed_day > requested_day:
                    return "wrong_day_zip"
                printed_days.add(printed_day)
            # A valid archive can include older market reports, but its newest
            # printed city date must agree with the link date. Never replace a
            # complete source with an adjacent-day archive body.
            if max(printed_days) != requested_day:
                return "wrong_day_zip"
    except Exception:
        return "invalid_zip_members"
    return None


def page_body_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _official_page_final_url(response_url: str | None, requested_url: str) -> bool:
    from .city_page_revision_hint import is_exact_official_month_page_url
    return (is_exact_official_month_page_url(requested_url)
            and response_url is not None
            and is_exact_official_month_page_url(response_url)
            and response_url == requested_url)


def record_month_page_attempt(db, page_url: str, outcome: str, error: str | None = None) -> None:
    """Record an exact monthly-page poll outcome for fair bounded rotation."""
    from .city_page_revision_hint import is_exact_official_month_page_url
    if not is_exact_official_month_page_url(page_url):
        raise ValueError("monthly page poll attempt requires an exact official DANE page URL")
    if outcome not in ("observed", "failed"):
        raise ValueError("monthly page poll attempt outcome is not recognized")
    db.execute(
        "INSERT INTO dane_city_page_poll_attempt(page_url,outcome,error) VALUES(%s,%s,%s)",
        (page_url, outcome, error[:500] if isinstance(error, str) else None),
    )


def observe_month_page(db, page_url: str, body: bytes, *, current_year: int) -> dict:
    """Append one page snapshot and its row observations, emit exact hints.

    First observation is a forward-only baseline. New/removed links are not
    source revisions and known failed/review/pending assets are never reset.
    """
    body = bytes(body)
    if len(body) > MAX_PAGE_BODY_BYTES:
        raise ValueError("monthly publisher page exceeds the bounded snapshot limit")
    rows = parse_current_month_rows(body, page_url, current_year=current_year)
    digest = page_body_sha256(body)
    snapshot_id = db.execute(
        "INSERT INTO dane_city_page_snapshot(page_url,page_sha256,page_bytes) "
        "VALUES(%s,%s,%s) RETURNING snapshot_id",
        (page_url, digest, body),
    ).fetchone()[0]
    previous = {}
    for url in rows:
        old = db.execute(
            """SELECT r.snapshot_id,r.observed_on,r.row_date_label,r.archive_label,r.row_signature
            FROM dane_city_page_row r JOIN dane_city_page_snapshot s USING(snapshot_id)
            WHERE s.page_url=%s AND r.source_url=%s
            ORDER BY s.captured_at DESC,s.snapshot_id DESC LIMIT 1""",
            (page_url, url),
        ).fetchone()
        if old is not None:
            previous[url] = old
    with db.cursor() as cur:
        cur.executemany(
            """INSERT INTO dane_city_page_row(snapshot_id,source_url,observed_on,
                row_date_label,archive_label,row_signature) VALUES(%s,%s,%s,%s,%s,%s)""",
            [(snapshot_id, row.url, row.observed_on, row.row_date_label,
              row.archive_label, row.row_signature) for row in rows.values()],
        )
    requests = []
    for url, current in rows.items():
        old = previous.get(url)
        if old is None:
            continue
        old_snapshot_id, old_day, _old_date_label, _old_label, old_signature = old
        if old_day != current.observed_on or old_signature == current.row_signature:
            continue
        asset = db.execute(
            "SELECT kind,observed_on,status FROM ingestion_asset WHERE url=%s", (url,)
        ).fetchone()
        if asset != ("city-zip", current.observed_on, "complete"):
            continue
        row = db.execute(
            """INSERT INTO dane_city_refresh_request(from_snapshot_id,to_snapshot_id,
                source_url,observed_on,old_signature,new_signature)
            VALUES(%s,%s,%s,%s,%s,%s) RETURNING request_id""",
            (old_snapshot_id, snapshot_id, url, current.observed_on,
             old_signature, current.row_signature),
        ).fetchone()
        requests.append(row[0])
    return {"snapshot_id": snapshot_id, "page_sha256": digest,
            "observed_links": len(rows), "refresh_requests": requests}


def current_year_month_page_candidates(db, *, year: int, active_month: int,
                                       limit: int = MAX_PAGE_SLOTS,
                                       poll_interval: timedelta = POLL_INTERVAL):
    """Select the current page, then rotate registered historical pages fairly.

    The unversioned current page remains first when due. Exact registered
    monthly pages from every year up to the cycle year rotate by oldest
    observation; unregistered URLs are never discovered by this selector.
    """
    limit = max(0, min(int(limit), MAX_PAGE_SLOTS))
    if not limit:
        return []
    from .city_page_revision_hint import CURRENT_DAILY_PAGE_URL
    return db.execute(
        """WITH pages AS (
          SELECT %s::text AS url,make_date(%s,%s,1) AS observed_on,
            (SELECT max(seen_at) FROM (
              SELECT s.captured_at AS seen_at FROM dane_city_page_snapshot s WHERE s.page_url=%s
              UNION ALL SELECT p.attempted_at FROM dane_city_page_poll_attempt p WHERE p.page_url=%s
            ) current_page_seen) AS last_seen,%s::text AS month_label,0 AS archive_rank
          UNION ALL
          SELECT a.url,a.observed_on,
            (SELECT max(seen_at) FROM (
              SELECT s.captured_at AS seen_at FROM dane_city_page_snapshot s WHERE s.page_url=a.url
              UNION ALL SELECT p.attempted_at FROM dane_city_page_poll_attempt p WHERE p.page_url=a.url
            ) historical_page_seen),
            substring(a.url from '-([a-z]+)-de-(20[0-9]{2})$'),1
          FROM ingestion_asset a
          WHERE a.kind='daily-index' AND a.status='complete'
            AND a.observed_on < make_date(%s+1,1,1)
            AND a.observed_on<=current_date
            AND a.url ~ '^https://www[.]dane[.]gov[.]co/index[.]php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-[a-z]+-de-20[0-9]{2}$'
        )
        SELECT url,observed_on FROM pages
        WHERE last_seen IS NULL OR last_seen<=now()-%s::interval
        ORDER BY archive_rank,last_seen ASC NULLS FIRST,
                 CASE WHEN month_label=ANY(%s::text[]) THEN 0 ELSE 1 END,
                 observed_on ASC,url
        LIMIT %s""",
        (CURRENT_DAILY_PAGE_URL, year, active_month, CURRENT_DAILY_PAGE_URL,
         CURRENT_DAILY_PAGE_URL, _month_label(active_month), year, poll_interval,
         [_month_label(active_month)], limit),
    ).fetchall()


def _month_label(month: int) -> str:
    from .city_page_revision_hint import MONTHS
    if month not in MONTHS.values():
        raise ValueError("invalid active month")
    return next(name for name, value in MONTHS.items() if value == month)


def refresh_request_candidates(db, *, limit: int = 1):
    """Select at most one request per existing worker cycle, labels first."""
    limit = max(0, min(int(limit), MAX_BODY_REFRESHES_PER_CYCLE))
    if not limit:
        return []
    return db.execute(
        """WITH latest_current AS (
          SELECT url,observed_on FROM ingestion_asset
          WHERE kind='city-zip' AND status='complete' AND records>0
            AND observed_on<=current_date
            AND url ~ '^https://www[.]dane[.]gov[.]co/files/.+[.]zip$'
          ORDER BY observed_on DESC,url ASC LIMIT 1
        ), last_attempt AS (
          SELECT DISTINCT ON (request_id) request_id,outcome,attempted_at,next_attempt_at
          FROM dane_city_refresh_attempt ORDER BY request_id,attempt_no DESC
        )
        SELECT r.request_id,r.source_url,r.observed_on
        FROM dane_city_refresh_request r
        JOIN ingestion_asset a ON a.url=r.source_url AND a.kind='city-zip'
        LEFT JOIN last_attempt la ON la.request_id=r.request_id
        WHERE a.status='complete' AND a.observed_on=r.observed_on
          AND a.observed_on<=current_date
          AND NOT EXISTS (
            SELECT 1 FROM source_host_cooldown h
            WHERE h.host='www.dane.gov.co' AND h.retry_at>now()
          )
          AND (la.request_id IS NULL OR
               (la.outcome IN ('failed','held') AND la.next_attempt_at<=now()
                AND la.next_attempt_at>=la.attempted_at+interval '6 hours'))
        ORDER BY CASE r.request_reason WHEN 'label_change' THEN 0
                        WHEN 'worker_observed_body_change' THEN 1 ELSE 2 END,
                 CASE WHEN r.request_reason='periodic_byte_verification'
                       AND (r.source_url,r.observed_on)=(SELECT url,observed_on FROM latest_current)
                      THEN 0 ELSE 1 END,
                 r.created_at,r.request_id LIMIT %s""", (limit,),
    ).fetchall()


def periodic_byte_check_candidates(db, *, year: int, limit: int = MAX_BODY_REFRESHES_PER_CYCLE,
                                   latest_interval: timedelta = PERIODIC_LATEST_INTERVAL,
                                   rotation_interval: timedelta = PERIODIC_ROTATION_INTERVAL):
    """Select at most one periodic body check for this existing worker cycle.

    The newest complete source through the cycle year is due once per 24 hours.
    Other complete sources across every prior year rotate FIFO by oldest
    successful check, due every 30 days. Label-change requests are selected before periodic requests by the
    request drain. No new timer is introduced; one archive body is the hard
    per-cycle transfer ceiling.
    """
    limit = max(0, min(int(limit), MAX_BODY_REFRESHES_PER_CYCLE))
    if not limit:
        return []
    return db.execute(
        """WITH complete AS (
          SELECT a.url,a.observed_on,
            (SELECT max(at.attempted_at)
             FROM dane_city_refresh_request r JOIN dane_city_refresh_attempt at USING(request_id)
             WHERE r.source_url=a.url AND r.observed_on=a.observed_on
               AND r.request_reason='periodic_byte_verification'
               AND at.outcome IN ('unchanged','published')) AS checked_at,
            la.request_id AS last_request_id,la.outcome AS last_outcome,la.next_attempt_at
          FROM ingestion_asset a
          LEFT JOIN LATERAL (
            SELECT r.request_id,attempt.outcome,attempt.next_attempt_at
            FROM dane_city_refresh_request r
            LEFT JOIN LATERAL (
              SELECT at.outcome,at.next_attempt_at FROM dane_city_refresh_attempt at
              WHERE at.request_id=r.request_id
              ORDER BY at.attempt_no DESC LIMIT 1
            ) attempt ON true
            WHERE r.source_url=a.url AND r.observed_on=a.observed_on
              AND r.request_reason='periodic_byte_verification'
            ORDER BY r.request_id DESC LIMIT 1
          ) la ON true
          WHERE a.kind='city-zip' AND a.status='complete' AND a.records>0
            AND a.observed_on < make_date(%s+1,1,1)
            AND a.observed_on<=current_date
            AND a.url ~ '^https://www[.]dane[.]gov[.]co/files/.+[.]zip$'
        ), latest AS (
          SELECT url,observed_on FROM complete ORDER BY observed_on DESC,url ASC LIMIT 1
        )
        SELECT c.url,c.observed_on,c.checked_at
        FROM complete c CROSS JOIN latest newest
        WHERE ((c.url=newest.url AND c.observed_on=newest.observed_on
                  AND (c.checked_at IS NULL OR c.checked_at<=now()-%s::interval))
            OR ((c.url,c.observed_on)<>(newest.url,newest.observed_on)
                  AND (c.checked_at IS NULL OR c.checked_at<=now()-%s::interval)))
          AND (c.last_request_id IS NULL OR c.last_outcome IN ('unchanged','published')
               OR (c.last_outcome IN ('failed','held') AND c.next_attempt_at<=now()))
          AND NOT EXISTS (
            SELECT 1 FROM dane_city_refresh_request r2
            LEFT JOIN LATERAL (
              SELECT at.outcome,at.next_attempt_at FROM dane_city_refresh_attempt at
              WHERE at.request_id=r2.request_id ORDER BY at.attempted_at DESC,at.attempt_no DESC LIMIT 1
            ) last ON true
            WHERE r2.source_url=c.url AND r2.observed_on=c.observed_on
              AND r2.request_reason='label_change'
              AND (last.outcome IS NULL OR last.outcome IN ('failed','held')
                   AND coalesce(last.next_attempt_at,now()+interval '1 second')>now())
          )
          AND NOT EXISTS (
            SELECT 1 FROM source_host_cooldown h
            WHERE h.host='www.dane.gov.co' AND h.retry_at>now()
          )
        ORDER BY CASE WHEN c.url=newest.url AND c.observed_on=newest.observed_on THEN 0 ELSE 1 END,
                 c.checked_at ASC NULLS FIRST,c.observed_on ASC,c.url
        LIMIT %s""",
        (year, latest_interval, rotation_interval, limit),
    ).fetchall()


def periodic_byte_lane_limits(db, *, year: int) -> dict:
    """Report bounded coverage across all registered years through ``year``."""
    counts = db.execute(
        """SELECT count(*) FILTER (WHERE a.observed_on BETWEEN make_date(%s,1,1)
                    AND make_date(%s+1,1,1)-1) AS current_year,
                  count(*) FILTER (WHERE a.observed_on<make_date(%s,1,1)) AS prior_years,
                  count(*) AS eligible
        FROM ingestion_asset a
        WHERE a.kind='city-zip' AND a.status='complete' AND a.records>0
          AND a.observed_on<make_date(%s+1,1,1)
          AND a.observed_on<=current_date
          AND a.url ~ '^https://www[.]dane[.]gov[.]co/files/.+[.]zip$'""",
        (year,year,year,year),
    ).fetchone()
    current_year, prior_years, eligible = (int(value or 0) for value in counts)
    older = max(0, eligible - 1)
    per_day = OLDER_SLOTS_PER_DAY
    full_cycle_capacity = per_day * 30
    initial_days = (older + per_day - 1) // per_day
    return {
        "complete_current_year_sources": current_year,
        "complete_prior_year_sources": prior_years,
        "complete_eligible_sources_through_cycle_year": eligible,
        "max_body_refreshes_per_existing_cycle": MAX_BODY_REFRESHES_PER_CYCLE,
        "max_transfer_bytes_per_existing_cycle": MAX_BODY_REFRESH_TRANSFER_BYTES_PER_CYCLE,
        "existing_hourly_cycles_per_day_assumed": HOURLY_CYCLES_PER_DAY,
        "newest_source_slots_per_day": NEWEST_DAILY_SLOTS,
        "newest_source_interval_hours": 24,
        "older_source_interval_days": 30,
        "older_rotation_slots_per_day": per_day,
        "older_sources_coverable_in_30_days": full_cycle_capacity,
        "older_sources_over_30_cycle_capacity": max(0, older - full_cycle_capacity),
        "estimated_initial_older_coverage_days": initial_days,
        "lag_assumptions": [
            "up to 24 existing hourly worker cycles run each day",
            "one cycle services the newest completed source when due, leaving 23 older rotation slots per day",
            "older registered DANE ZIP sources across years rotate by oldest successful check",
            "no active DANE host cooldown or unresolved higher-priority label request",
            "each selected archive finishes within the cycle time budget",
        ],
    }


def enqueue_periodic_byte_check(db, url: str, day: date, *, year: int,
                                latest_interval: timedelta = PERIODIC_LATEST_INTERVAL,
                                rotation_interval: timedelta = PERIODIC_ROTATION_INTERVAL):
    """Create one periodic byte-verification request without resetting assets."""
    parsed = urlparse(url)
    if not _official_city_zip_url(url):
        return None
    with db.transaction():
        lock_key = db.execute(
            "SELECT hashtextextended('dane-city-periodic:'||%s,0)", (url,),
        ).fetchone()[0]
        db.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
        candidate = db.execute(
            "SELECT 1 FROM ingestion_asset a WHERE a.url=%s AND a.kind='city-zip' "
            "AND a.observed_on=%s AND a.status='complete' AND a.records>0 "
            "AND a.observed_on < make_date(%s+1,1,1) "
            "AND a.observed_on<=current_date",
            (url, day, year),
        ).fetchone()
        if candidate is None:
            return None
        # The newest dated complete ZIP through this cycle year is rechecked
        # daily; every other registered year uses the slower bounded rotation.
        latest = db.execute(
            "SELECT url,observed_on FROM ingestion_asset WHERE kind='city-zip' "
            "AND status='complete' AND records>0 "
            "AND observed_on < make_date(%s+1,1,1) "
            "AND observed_on<=current_date "
            "AND url ~ '^https://www[.]dane[.]gov[.]co/files/.+[.]zip$' "
            "ORDER BY observed_on DESC,url ASC LIMIT 1", (year,),
        ).fetchone()
        interval = latest_interval if latest == (url, day) else rotation_interval
        cooldown = db.execute(
            "SELECT 1 FROM source_host_cooldown WHERE host='www.dane.gov.co' AND retry_at>now() LIMIT 1",
        ).fetchone()
        if cooldown is not None:
            return None
        due = db.execute(
            """SELECT coalesce(max(at.attempted_at)<=now()-%s::interval,true)
            FROM dane_city_refresh_request r
            JOIN dane_city_refresh_attempt at USING(request_id)
            WHERE r.source_url=%s AND r.observed_on=%s
              AND r.request_reason='periodic_byte_verification'
              AND at.outcome IN ('unchanged','published')""", (interval, url, day),
        ).fetchone()[0]
        if not due:
            return None
        unresolved = db.execute(
            """SELECT 1 FROM dane_city_refresh_request r
            LEFT JOIN LATERAL (SELECT at.outcome,at.next_attempt_at FROM dane_city_refresh_attempt at
              WHERE at.request_id=r.request_id ORDER BY at.attempted_at DESC,at.attempt_no DESC LIMIT 1) last ON true
            WHERE r.source_url=%s AND r.observed_on=%s
              AND r.request_reason IN ('periodic_byte_verification','label_change')
              AND (last.outcome IS NULL OR last.outcome IN ('failed','held')
                   AND coalesce(last.next_attempt_at,now()+interval '1 second')>now())
            LIMIT 1""", (url, day),
        ).fetchone()
        if unresolved is not None:
            return None
        return db.execute(
            """INSERT INTO dane_city_refresh_request(source_url,observed_on,request_reason)
            VALUES(%s,%s,'periodic_byte_verification') RETURNING request_id""",
            (url, day),
        ).fetchone()[0]


def run_automatic_refresh_cycle(db, worker, *, year: int, active_month: int,
                                deadline: float, page_body_cache: dict | None = None) -> dict:
    """Observe one due official page and drain at most one exact ZIP request.

    The caller owns the existing scheduled worker budget. This function adds no
    timer or queue seed: page observations produce label hints, while the
    existing retained-source rotation supplies ordinary byte checks. It leaves
    the current asset/history untouched until the existing atomic publisher
    accepts a full cohort.
    """
    started = time.monotonic()
    result = {
        "page_selected": False, "page_observed": False, "page_source": None,
        "page_bytes": 0, "page_sha256": None, "label_requests_created": 0,
        "periodic_request_created": False, "request_selected": 0,
        "archive_attempted": False, "archive_outcome": None, "results": [],
        "remaining_seconds": None,
    }
    if deadline - time.monotonic() < MAX_BODY_REFRESH_SOFT_SECONDS + 25:
        result["deferred"] = "insufficient reserved window for page and bounded ZIP attempt"
        result["remaining_seconds"] = round(max(0, deadline-time.monotonic()), 1)
        return result

    pages = current_year_month_page_candidates(
        db, year=year, active_month=active_month, limit=MAX_PAGE_SLOTS,
    )
    if pages:
        page_url, _page_day = pages[0]
        result["page_selected"] = True
        result["page_url"] = page_url
        cache_has_result = page_body_cache is not None and page_url in page_body_cache
        cached = page_body_cache.get(page_url) if cache_has_result else None
        blocked_until = worker.HOST_COOLDOWNS.get().blocked(page_url)
        if cached is not None:
            body = bytes(cached)
            result["page_source"] = "same-run discovery body"
        elif blocked_until is not None:
            result["page_source"] = "deferred by DANE host cooldown"
            result["deferred"] = "DANE host cooldown"
            body = None
            if page_body_cache is not None:
                page_body_cache[page_url] = None
        elif cache_has_result:
            result["page_source"] = "same-run discovery fetch already failed"
            result["deferred"] = "page fetch already attempted in this cycle"
            body = None
        else:
            remaining = deadline-time.monotonic()
            if remaining <= MAX_BODY_REFRESH_SOFT_SECONDS + 25:
                result["deferred"] = "reserved archive window"
                body = None
            else:
                try:
                    downloaded = _download_unconditionally(
                        worker, page_url, max_bytes=MAX_PAGE_BODY_BYTES,
                        max_duration_seconds=min(25, remaining-MAX_BODY_REFRESH_SOFT_SECONDS),
                        budget_expired=lambda _bytes: (
                            time.monotonic() >= deadline-MAX_BODY_REFRESH_SOFT_SECONDS
                        ),
                    )
                    if not _official_page_final_url(downloaded.response_url, page_url):
                        raise ValueError("monthly page response did not retain its exact official URL")
                    body = downloaded.body
                    if page_body_cache is not None:
                        page_body_cache[page_url] = body
                    result["page_source"] = "bounded official page fetch"
                except Exception as exc:
                    body = None
                    if page_body_cache is not None:
                        page_body_cache[page_url] = None
                    result["deferred"] = type(exc).__name__ + ": " + str(exc)[:240]
        page_attempt_outcome = None
        page_attempt_error = None
        if body is not None:
            try:
                observed = observe_month_page(db, page_url, body, current_year=year)
                result.update({
                    "page_observed": True, "page_bytes": len(body),
                    "page_sha256": observed["page_sha256"],
                    "page_snapshot_id": observed["snapshot_id"],
                    "label_requests_created": len(observed["refresh_requests"]),
                })
                page_attempt_outcome = "observed"
            except Exception as exc:
                page_attempt_outcome = "failed"
                page_attempt_error = type(exc).__name__ + ": " + str(exc)
                result["deferred"] = "page observation " + page_attempt_error[:240]
        elif result.get("deferred") and not any(
                marker in result["deferred"].lower()
                for marker in ("cooldown", "reserved archive window", "insufficient reserved window")):
            page_attempt_outcome = "failed"
            page_attempt_error = result["deferred"]
        if page_attempt_outcome is not None:
            record_month_page_attempt(db, page_url, page_attempt_outcome, page_attempt_error)
            result["page_attempt_outcome"] = page_attempt_outcome

    requests = refresh_request_candidates(db, limit=MAX_BODY_REFRESHES_PER_CYCLE)
    if not requests:
        due = periodic_byte_check_candidates(db, year=year, limit=MAX_BODY_REFRESHES_PER_CYCLE)
        if due:
            url, day, _checked_at = due[0]
            request_id = enqueue_periodic_byte_check(db, url, day, year=year)
            if request_id is not None:
                result["periodic_request_created"] = True
                requests = refresh_request_candidates(db, limit=MAX_BODY_REFRESHES_PER_CYCLE)
    if requests:
        request_id, source_url, source_day = requests[0]
        result["request_selected"] = 1
        result["request_reason"] = db.execute(
            "SELECT request_reason FROM dane_city_refresh_request WHERE request_id=%s",
            (request_id,),
        ).fetchone()[0]
        result["request_url"] = source_url
        result["request_observed_on"] = source_day.isoformat()
        if deadline-time.monotonic() >= 10:
            result["archive_attempted"] = True
            result["archive_outcome"] = process_refresh_request(db, request_id)
            result["results"].append({
                "request_id": request_id, "url": source_url,
                "observed_on": source_day.isoformat(),
                "outcome": result["archive_outcome"],
            })
        else:
            result["deferred"] = "run deadline before archive attempt"
    result["elapsed_seconds"] = round(time.monotonic()-started, 2)
    result["remaining_seconds"] = round(max(0, deadline-time.monotonic()), 1)
    return result


def _official_city_zip_url(url: str) -> bool:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:
        return False
    return (parsed.scheme == "https" and parsed.hostname == DANE_HOST
            and port in (None, 443) and parsed.username is None
            and parsed.password is None and parsed.query == ""
            and parsed.fragment == "" and parsed.path.startswith("/files/")
            and parsed.path.lower().endswith(".zip"))

def _verify_current_complete_asset(db, url: str, day: date):
    if not _official_city_zip_url(url):
        raise ValueError("refresh URL is not an exact official DANE city ZIP URL")
    row = db.execute(
        """SELECT a.kind,a.observed_on,a.status,a.document_id,a.records,a.processor_version,
                  d.source_url,d.media_type,d.kind,d.reference_period,d.content,d.metadata
        FROM ingestion_asset a JOIN source_document d ON d.id=a.document_id
        WHERE a.url=%s FOR UPDATE OF a""", (url,),
    ).fetchone()
    if row is None:
        raise ValueError("refresh asset/original is missing")
    (kind, observed_on, status, did, records, current_version, original_url,
     media_type, doc_kind, reference_period, content, metadata) = row
    if ((kind, observed_on, status) != ("city-zip", day, "complete")
            or not isinstance(current_version, str) or not current_version):
        raise ValueError("refresh asset is not the exact completed source revision")
    content = bytes(content)
    if (hashlib.sha256(content).hexdigest() != did or original_url != url
            or media_type != "application/zip" or doc_kind != "original"
            or reference_period != day.isoformat()
            or not isinstance(metadata, dict)
            or metadata.get("retention") != "permanent"
            or metadata.get("ingestion_kind") != "city-zip"):
        raise ValueError("refresh original source identity or metadata changed")
    child_count = db.execute(
        """SELECT count(*) FROM source_archive_member m
        JOIN source_document d ON d.id=m.document_id
        WHERE m.archive_id=%s AND d.kind='original'""", (did,),
    ).fetchone()[0]
    price_count = db.execute(
        "SELECT count(*) FROM regional_price r JOIN source_archive_member m ON m.document_id=r.document_id WHERE m.archive_id=%s",
        (did,),
    ).fetchone()[0]
    class_count = db.execute(
        "SELECT count(*) FROM regional_classification c JOIN source_archive_member m ON m.document_id=c.document_id WHERE m.archive_id=%s",
        (did,),
    ).fetchone()[0]
    if not records or not child_count or price_count != records or class_count != records:
        raise ValueError("refresh completed source does not have a full published city cohort")
    return did, content, current_version


def _record_attempt(db, request_id: int, outcome: str, *, fetched_sha256=None,
                    fetched_document_id=None, error=None, retry_at=None,
                    response_status=None, response_content_type=None,
                    response_url=None, body_classification=None):
    no = db.execute(
        "SELECT coalesce(max(attempt_no),0)+1 FROM dane_city_refresh_attempt WHERE request_id=%s",
        (request_id,),
    ).fetchone()[0]
    return db.execute(
        """WITH attempt_clock AS MATERIALIZED (SELECT clock_timestamp() AS at)
        INSERT INTO dane_city_refresh_attempt(request_id,attempt_no,outcome,
            attempted_at,next_attempt_at,fetched_sha256,fetched_document_id,error,
            response_status,response_content_type,response_url,body_classification)
        SELECT %s,%s,%s,at,
            CASE WHEN %s IN ('failed','held') THEN
                greatest(%s::timestamptz,at+interval '6 hours')
                ELSE NULL END,%s,%s,%s,%s,%s,%s,%s FROM attempt_clock""",
        (request_id, no, outcome, outcome, retry_at, fetched_sha256,
         fetched_document_id, error, response_status, response_content_type,
         response_url, body_classification),
    )


def _retain_response_audit(db, request_id: int, body: bytes, *, response_status: int,
                           content_type: str | None, response_url: str,
                           classification: str) -> int:
    digest = hashlib.sha256(body).hexdigest()
    attempt_no = db.execute(
        "SELECT coalesce(max(attempt_no),0)+1 FROM dane_city_refresh_attempt WHERE request_id=%s",
        (request_id,),
    ).fetchone()[0]
    db.execute(
        """INSERT INTO dane_city_refresh_response_audit(request_id,attempt_no,
             response_sha256,response_bytes,response_status,response_content_type,
             response_url,body_classification)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
        (request_id, attempt_no, digest, body, response_status, content_type,
         response_url, classification),
    )
    return attempt_no


def _hold_response_audit(db, request_id: int, body: bytes, *, response_status: int,
                         content_type: str | None, response_url: str,
                         classification: str):
    digest = hashlib.sha256(body).hexdigest()
    with db.transaction():
        _retain_response_audit(
            db, request_id, body, response_status=response_status,
            content_type=content_type, response_url=response_url,
            classification=classification,
        )
        _record_attempt(
            db, request_id, "held", fetched_sha256=digest,
            error="HTTP response is not an authoritative same-day DANE ZIP",
            retry_at=datetime.now(timezone.utc)+MIN_RETRY,
            response_status=response_status,
            response_content_type=content_type,
            response_url=response_url,
            body_classification=classification,
        )
    return "held"


def _verify_candidate_original(db, url: str, day: date, document_id: str,
                               body: bytes) -> None:
    """Verify an independently retained candidate original before parsing it."""
    digest = hashlib.sha256(body).hexdigest()
    if document_id != digest:
        raise ValueError("retained city candidate ID does not match its body SHA")
    row = db.execute(
        """SELECT publisher,source_url,media_type,kind,reference_period,content,metadata
        FROM source_document WHERE id=%s""", (document_id,),
    ).fetchone()
    if row is None:
        raise ValueError("retained city candidate original is missing")
    publisher, source_url, media_type, kind, reference_period, content, metadata = row
    expected_name = Path(urlparse(url).path).name
    if (publisher != "DANE" or source_url != url or media_type != "application/zip"
            or kind != "original" or reference_period != day.isoformat()
            or bytes(content) != body or not isinstance(metadata, dict)
            or metadata.get("retention") != "permanent"
            or metadata.get("ingestion_kind") != "city-zip"
            or metadata.get("original_filename") != expected_name):
        raise ValueError("retained city candidate source identity or metadata changed")


def _link_candidate_original(db, request_id: int, day: date,
                             document_id: str) -> None:
    digest = document_id
    db.execute(
        """INSERT INTO dane_city_refresh_source(request_id,observed_on,document_id,source_sha256)
        VALUES(%s,%s,%s,%s) ON CONFLICT(request_id,document_id) DO NOTHING""",
        (request_id, day, document_id, digest),
    )
    row = db.execute(
        """SELECT observed_on,document_id,source_sha256
        FROM dane_city_refresh_source WHERE request_id=%s AND document_id=%s""",
        (request_id, document_id),
    ).fetchone()
    if row != (day, document_id, digest):
        raise ValueError("refresh request source link does not match retained original")


def _retain_candidate_original(db, request_id: int, url: str, day: date,
                               body: bytes) -> str:
    """Commit exact bytes and request linkage before attempting price publication.

    The source row and refresh-source witness intentionally survive a later
    parser/cohort rollback. The current complete asset pointer is untouched.
    """
    from pipelines.ingestion import worker

    body = bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    with db.transaction():
        document_id = worker.archive(db, url, body, "city-zip", day)
        _verify_candidate_original(db, url, day, document_id, body)
        _link_candidate_original(db, request_id, day, document_id)
    return document_id


def process_refresh_request(db, request_id: int, *, fetcher=None):
    """Fetch or resume one exact source; publish only a fully accepted cohort."""
    from datetime import datetime
    from pipelines.ingestion import worker
    from pipelines.ingestion.source_http_backoff import HostCooldowns, HostRateLimited
    from .city_refresh_cohort_worker import publish_retained_candidate

    request = db.execute(
        """SELECT source_url,observed_on FROM dane_city_refresh_request
        WHERE request_id=%s""", (request_id,),
    ).fetchone()
    if request is None:
        raise ValueError("unknown city refresh request")
    url, day = request
    lock_key = db.execute(
        "SELECT hashtextextended('dane-city-refresh:'||%s,0)", (url,),
    ).fetchone()[0]
    if not db.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,)).fetchone()[0]:
        return "locked"
    try:
        processor_version = worker.asset_parser_version("city-zip", url)
        # The lock/fresh metadata check is repeated in the publication
        # transaction. This first check ensures a stale/review asset is held
        # without any publisher request.
        try:
            prior_id, prior_body, prior_asset_parser_version = _verify_current_complete_asset(db, url, day)
        except Exception as exc:
            _record_attempt(
                db, request_id, "held",
                error=(type(exc).__name__+": "+str(exc))[:1000],
                retry_at=datetime.now(timezone.utc)+MIN_RETRY,
            )
            return "held"

        def publish_candidate(candidate_id, *, etag=None, last_modified=None,
                              response_status=None, response_content_type=None,
                              response_url=None):
            def record_published(proof):
                _record_attempt(
                    db, request_id, "published", fetched_sha256=candidate_id,
                    fetched_document_id=candidate_id,
                    response_status=response_status,
                    response_content_type=response_content_type,
                    response_url=response_url,
                    body_classification="zip",
                )

            try:
                publish_retained_candidate(
                    db, request_id=request_id, source_url=url, day=day,
                    candidate_id=candidate_id, parser_version=processor_version,
                    prior_asset_id=prior_id,
                    prior_asset_parser_version=prior_asset_parser_version, etag=etag,
                    last_modified=last_modified, on_published=record_published,
                )
                return "published"
            except Exception as exc:
                _record_attempt(
                    db, request_id, "held", fetched_sha256=candidate_id,
                    fetched_document_id=candidate_id,
                    error=(type(exc).__name__+": "+str(exc))[:1000],
                    retry_at=datetime.now(timezone.utc)+MIN_RETRY,
                    response_status=response_status,
                    response_content_type=response_content_type,
                    response_url=response_url,
                    body_classification="retained_candidate_review",
                )
                return "held"

        # OCR may have verified staged pages since the prior attempt. Resume
        # those exact retained bytes before making another HTTP request.
        retained_candidate = db.execute(
            """SELECT s.document_id FROM dane_city_refresh_source s
            WHERE s.request_id=%s AND s.observed_on=%s AND s.document_id<>%s
            ORDER BY s.retained_at DESC,s.document_id LIMIT 1""",
            (request_id, day, prior_id),
        ).fetchone()
        if retained_candidate is not None:
            return publish_candidate(retained_candidate[0])

        fetcher = fetcher or (
            lambda _db, source_url, **_kwargs: _download_unconditionally(worker, source_url)
        )
        cooldown_token = None
        if worker.HOST_COOLDOWNS.get() is None:
            cooldown_token = worker.HOST_COOLDOWNS.set(HostCooldowns(db, writer=worker.connect))
        try:
            downloaded = fetcher(db, url, force=True, require_bytes=True)
            if not isinstance(downloaded, DownloadedSource):
                downloaded = DownloadedSource(bytes(downloaded or b""), None, None)
            body = downloaded.body
            if not body:
                raise ValueError("unconditional city refresh returned no bytes")
        except OversizedSourceResponse as exc:
            retry = datetime.now(timezone.utc)+MIN_RETRY
            _record_attempt(
                db, request_id, "failed", error=str(exc)[:1000], retry_at=retry,
                response_status=exc.response_status,
                response_content_type=exc.content_type,
                response_url=exc.response_url or url,
                body_classification="oversized_incomplete",
            )
            return "failed"
        except HostRateLimited as exc:
            retry = max(exc.retry_at, datetime.now(timezone.utc)+MIN_RETRY)
            _record_attempt(db, request_id, "failed", error=str(exc)[:1000], retry_at=retry)
            return "failed"
        except Exception as exc:
            retry = datetime.now(timezone.utc)+MIN_RETRY
            _record_attempt(db, request_id, "failed", error=(type(exc).__name__+": "+str(exc))[:1000], retry_at=retry)
            return "failed"
        finally:
            if cooldown_token is not None:
                worker.HOST_COOLDOWNS.reset(cooldown_token)
        body = bytes(body)
        digest = hashlib.sha256(body).hexdigest()
        content_type = downloaded.content_type
        response_url = downloaded.response_url or url
        response_status = downloaded.response_status or 200
        classification = _classify_zip_body(body, content_type)
        if classification is None and not _official_final_url(response_url, url):
            classification = "redirect_target_mismatch"
        if classification is not None:
            return _hold_response_audit(
                db, request_id, body, response_status=response_status,
                content_type=content_type, response_url=response_url,
                classification=classification,
            )
        if digest == prior_id:
            with db.transaction():
                _link_candidate_original(db, request_id, day, prior_id)
                update = db.execute(
                    """UPDATE ingestion_asset SET http_etag=%s,http_last_modified=%s,
                    checked_at=now(),attempts=attempts+1,error=NULL
                    WHERE url=%s AND kind='city-zip' AND observed_on=%s
                      AND document_id=%s AND status='complete' AND processor_version=%s""",
                    (downloaded.etag, downloaded.last_modified, url, day, prior_id, processor_version),
                )
                if update.rowcount != 1:
                    raise ValueError("city asset changed before unchanged-byte confirmation")
                _record_attempt(db, request_id, "unchanged", fetched_sha256=digest,
                                fetched_document_id=prior_id,
                                response_status=response_status,
                                response_content_type=content_type,
                                response_url=response_url,
                                body_classification="zip")
            return "unchanged"

        try:
            # Persist and verify the fetched publisher bytes in a separate
            # commit. A later parser/cohort failure must not erase this source.
            candidate_id = _retain_candidate_original(db, request_id, url, day, body)
        except Exception as exc:
            retry = datetime.now(timezone.utc)+MIN_RETRY
            _record_attempt(db, request_id, "held", fetched_sha256=digest,
                            error=(type(exc).__name__+": "+str(exc))[:1000], retry_at=retry)
            return "held"
        return publish_candidate(
            candidate_id, etag=downloaded.etag,
            last_modified=downloaded.last_modified,
            response_status=response_status, response_content_type=content_type,
            response_url=response_url,
        )
    finally:
        db.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))

"""Durable, publisher-host scoped HTTP 429 backoff for source ingestion."""

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from urllib3.util.retry import Retry


FALLBACK_SECONDS = 15 * 60


class NoThrottleRetry(Retry):
    """Leave 429 to the worker, while retaining ordinary 5xx retries."""

    def is_retry(self, method, status_code, has_retry_after=False):
        if status_code == 429:
            return False
        return super().is_retry(method, status_code, has_retry_after)


class HostRateLimited(Exception):
    def __init__(self, host, retry_at, literal_header):
        self.host = host
        self.retry_at = retry_at
        self.literal_header = literal_header
        super().__init__(f"HTTP 429 from {host}; retry after {retry_at.isoformat()}")


def host_for(url):
    host = urlparse(url).hostname
    if not host:
        raise ValueError(f"Source URL has no hostname: {url}")
    return host.lower().rstrip(".")


def retry_deadline(header, now=None):
    """Honor a valid Retry-After; use a finite fallback only if it is absent/bad."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("retry clock must be timezone-aware")
    literal = (header or "").strip()
    if literal.isascii() and literal.isdecimal():
        try:
            deadline = now + timedelta(seconds=int(literal))
            return deadline if deadline > now else now + timedelta(seconds=FALLBACK_SECONDS)
        except (OverflowError, ValueError):
            pass
    if literal:
        try:
            deadline = parsedate_to_datetime(literal)
            if deadline.tzinfo is not None:
                deadline = deadline.astimezone(timezone.utc)
                return deadline if deadline > now else now + timedelta(seconds=FALLBACK_SECONDS)
        except (TypeError, ValueError, OverflowError):
            pass
    return now + timedelta(seconds=FALLBACK_SECONDS)


class HostCooldowns:
    """A run-local map backed by PostgreSQL, shared by discovery and asset reads."""

    def __init__(self, db, now=None, writer=None):
        self.db = db
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.writer = writer
        rows = db.execute(
            "SELECT host,retry_at FROM source_host_cooldown WHERE retry_at > now()"
        ).fetchall()
        self.deadlines = {
            row[0]: row[1] for row in rows
            if len(row) >= 2 and isinstance(row[0], str)
            and isinstance(row[1], datetime)
        }

    def blocked(self, url):
        # Queue-planning tests may use synthetic asset IDs; only HTTP requests
        # require a real hostname. Such IDs cannot have a publisher cooldown.
        host = urlparse(url).hostname
        if not host:
            return None
        host = host.lower().rstrip(".")
        deadline = self.deadlines.get(host)
        return deadline if deadline and deadline > self.now() else None

    def check(self, url):
        deadline = self.blocked(url)
        if deadline:
            raise HostRateLimited(host_for(url), deadline, None)

    def record(self, url, response):
        host = host_for(url)
        literal = response.headers.get("Retry-After")
        retry_at = retry_deadline(literal, self.now())
        statement = """INSERT INTO source_host_cooldown(host,retry_at,checked_at,response_status,retry_after_literal)
               VALUES(%s,%s,now(),429,%s)
               ON CONFLICT(host) DO UPDATE SET
                 retry_at=greatest(source_host_cooldown.retry_at,excluded.retry_at),
                 checked_at=excluded.checked_at,response_status=429,
                 retry_after_literal=CASE WHEN excluded.retry_at>=source_host_cooldown.retry_at
                   THEN excluded.retry_after_literal ELSE source_host_cooldown.retry_after_literal END"""
        if self.writer is None:
            connection = self.db
            connection.execute(statement, (host, retry_at, literal))
            durable = connection.execute(
                "SELECT retry_at FROM source_host_cooldown WHERE host=%s", (host,)
            ).fetchone()[0]
        else:
            # A source parser may fetch inside db.transaction(); a separate
            # autocommit connection survives that transaction's rollback.
            with self.writer() as connection:
                connection.execute(statement, (host, retry_at, literal))
                durable = connection.execute(
                    "SELECT retry_at FROM source_host_cooldown WHERE host=%s", (host,)
                ).fetchone()[0]
        self.deadlines[host] = durable
        return HostRateLimited(host, durable, literal)

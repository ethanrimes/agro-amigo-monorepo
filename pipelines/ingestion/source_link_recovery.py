"""Verified repairs for broken publisher links, with native-content validation.

Call only after the original URL returns 404/410. This is deliberately not a
general filename guesser: each entry was checked against the official archive
page and a downloadable original whose printed date and complete price matrix
were validated. Preserve the broken ingestion URL and archive returned bytes
under ``canonical_url``; persist ``evidence`` as an immutable resolution record.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256

VERSION = "source-link-recovery-v1"
_FILES = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
_AUGUST_ARCHIVE = (
    "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/"
    "sistema-de-informacion-de-precios-sipsa/"
    "componente-precios-mayoristas-agosto-de-2014"
)


@dataclass(frozen=True)
class VerifiedAlias:
    canonical_url: str
    observed_on: date
    archive_url: str
    reason: str
    audit_sha256: str
    audit_records: int


VERIFIED_ALIASES = {
    _FILES + "mayoristas_agosto_11_2014s.xls": VerifiedAlias(
        _FILES + "mayoristas_agosto_11_2014.xls",
        date(2014, 8, 11),
        _AUGUST_ARCHIVE,
        "Official archive link has an extra s before .xls; corrected official "
        "original has the expected printed publication date and price matrix.",
        "c30bf4b5410421097f2418a8c50d230dde0553ac32540552a56fdd48d1e843dd",
        406,
    ),
    _FILES
    + "mayoristas_files/investigaciones/agropecuario/sipsa/"
    + "mayoristas_agosto_8_2014.xls": VerifiedAlias(
        _FILES + "mayoristas_agosto_8_2014.xls",
        date(2014, 8, 8),
        _AUGUST_ARCHIVE,
        "Official archive link repeats a directory fragment; corrected official "
        "original has the expected printed publication date and price matrix.",
        "717eea56fcbdba29171f4d970a902f171c65e3c0b8ba99c295125433616687e5",
        470,
    ),
}


@dataclass(frozen=True)
class RecoveredLink:
    canonical_url: str
    body: bytes = field(repr=False)
    evidence: dict


def recover_link(
    url: str,
    error_status: int,
    expected_day: date,
    fetcher: Callable[[str], bytes],
    *,
    validator: Callable[[bytes, date], Iterable] | None = None,
) -> RecoveredLink | None:
    """Fetch one vetted replacement after a permanent missing-link response.

    No fallback runs on rate limits, access failures, timeouts or server errors.
    Any candidate fetch/native validation failure propagates to normal review;
    neither a successful HTTP response nor a matching filename is sufficient.
    Audit hashes document the initial check, not a pin that blocks later valid
    publisher corrections. Every changed body is fully validated again.
    """
    alias = VERIFIED_ALIASES.get(url)
    if error_status not in (404, 410) or alias is None:
        return None
    if expected_day != alias.observed_on:
        raise ValueError("Link recovery date does not match the verified alias")

    body = fetcher(alias.canonical_url)
    if not isinstance(body, bytes) or not body.startswith(
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", b"PK\x03\x04")
    ):
        raise ValueError("Link recovery did not return a native Excel workbook")
    if validator is None:
        # Lazy import avoids a cycle when worker imports this module. Reuse the
        # production date/market/unit checks instead of a weaker second parser.
        from .daily_recovery import parse_daily

        result = parse_daily(body, expected_day)
        if result["reviews"]:
            raise ValueError("Link recovery workbook contains unresolved daily cells")
        validator = lambda *_: result["rows"]
    count = 0
    for row in validator(body, expected_day):
        if row[2] != expected_day or not row[3] or not row[4] or not row[5]:
            raise ValueError("Link recovery has an invalid daily quote identity")
        count += 1
    if not count:
        raise ValueError("Link recovery workbook has no validated daily prices")

    digest = sha256(body).hexdigest()
    return RecoveredLink(
        alias.canonical_url,
        body,
        {
            "processor_version": VERSION,
            "original_url": url,
            "canonical_url": alias.canonical_url,
            "archive_url": alias.archive_url,
            "original_http_status": error_status,
            "observed_on": expected_day.isoformat(),
            "reason": alias.reason,
            "validation": "complete-native-daily-workbook",
            "validated_records": count,
            "sha256": digest,
            "bytes": len(body),
            "audit_sha256": alias.audit_sha256,
            "matches_audited_bytes": digest == alias.audit_sha256,
        },
    )

"""Narrow FNC workbook-link reconciliation helpers for discovery integration.

This module performs no HTTP calls and does not queue work. Discovery supplies
only URLs it linked from the trusted FNC index, then may pass that set here to
revive an exact previously retired URL and retire a unique, proven replacement
for an obsolete failed 404. Source documents, observations, quote rows, record
counts, attempts, and checked timestamps are append-only evidence and are never
changed here.
"""
from __future__ import annotations

from collections import defaultdict
import re
from urllib.parse import urlsplit

TRUSTED_HOSTS = frozenset({
    "federaciondecafeteros.org",
    "www.federaciondecafeteros.org",
})
RETIREMENT_PREFIX = "FNC index replaced verified 404 URL:"
MONTHS = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)
_MONTH_ALT = "|".join(MONTHS)
_MONTH_NUM = {name: index for index, name in enumerate(MONTHS, 1)}
_MONTHLY_NAME = re.compile(
    rf"^Precios-area-y-produccion-de-cafe-({_MONTH_ALT})-(20\d{{2}})(?:-([1-9]\d*))?\.xlsx$"
)
_UPLOAD_PATH = re.compile(r"^(/wp-content/uploads/20\d{2}/(?:0[1-9]|1[0-2]))/(.+)$")
_RAW_404 = re.compile(r"^(?:HTTPError:\s*)?404(?:\b|:)")


def _trusted_workbook_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.netloc in TRUSTED_HOSTS
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
            and not parsed.query
            and not parsed.fragment
            and parsed.path.lower().endswith(".xlsx")
            and "precios" in parsed.path.rsplit("/", 1)[-1].lower()
        )
    except ValueError:
        return False


def upload_equivalence_key(url: str):
    """Return a strict key for one known monthly FNC workbook upload family.

    Revisions may be the unsuffixed name or an explicit positive ``-N`` suffix.
    The exact HTTPS host and upload directory stay part of the key; the report
    month and report year are parsed from the filename and are never inferred
    from the upload directory or a numeric suffix.
    """
    if not _trusted_workbook_url(url):
        return None
    parsed = urlsplit(url)
    path_match = _UPLOAD_PATH.fullmatch(parsed.path)
    if not path_match:
        return None
    directory, filename = path_match.groups()
    name_match = _MONTHLY_NAME.fullmatch(filename)
    if not name_match:
        return None
    month_name, report_year, _revision = name_match.groups()
    return (parsed.netloc, directory, int(report_year), _MONTH_NUM[month_name])


def _raw_not_found(error) -> bool:
    return isinstance(error, str) and _RAW_404.match(error) is not None


def _complete_linked_original(db, url: str) -> bool:
    row = db.execute(
        """SELECT a.document_id,a.records,d.source_url,d.publisher,d.media_type,d.kind,
                  d.metadata->>'ingestion_kind'
             FROM ingestion_asset a JOIN source_document d ON d.id=a.document_id
            WHERE a.url=%s AND a.kind='coffee' AND a.status='complete'
              AND a.document_id IS NOT NULL""",
        (url,),
    ).fetchone()
    return bool(row and row[0] and isinstance(row[1], int) and row[1] > 0 and row[2:] == (
        url,
        "FNC",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "original",
        "coffee",
    ))


def reconcile_fnc_workbook_assets(db, linked_workbook_urls) -> dict[str, int]:
    """Revive relinked retired uploads and retire unique completed 404 replacements.

    ``linked_workbook_urls`` must be the current index's workbook URLs. This
    function rechecks the FNC HTTPS host and workbook shape before any mutation.
    It only edits ``status`` and ``error`` on exact target asset rows; attempts,
    checked_at, records, document IDs, source documents and quote rows remain
    untouched.
    """
    linked = sorted({url for url in linked_workbook_urls if _trusted_workbook_url(url)})
    stats = {"revived": 0, "retired": 0, "ambiguous": 0}

    # A current trusted index link revives only the exact status+error marker
    # written by this module's retirement flow. Preserve the full old string as
    # provenance, but move the exclusion marker away from error's first bytes.
    for url in linked:
        row = db.execute(
            """SELECT status,error FROM ingestion_asset
                WHERE url=%s AND kind='coffee' AND status IN ('review','archived')""",
            (url,),
        ).fetchone()
        if not row or not isinstance(row[1], str) or not row[1].startswith(RETIREMENT_PREFIX):
            continue
        old_error = row[1]
        revived_error = "FNC official index relinked this upload; prior retirement/error: " + old_error
        result = db.execute(
            """UPDATE ingestion_asset SET status='pending',error=%s
                WHERE url=%s AND kind='coffee' AND status=%s AND error=%s
                RETURNING url""",
            (revived_error, url, row[0], old_error),
        ).fetchone()
        stats["revived"] += bool(result)

    # Build keys only from current trusted monthly filename links. The complete
    # candidate set must be unique before its retained original can authorize
    # retirement of an obsolete URL.
    linked_by_key = defaultdict(list)
    for url in linked:
        key = upload_equivalence_key(url)
        if key is not None:
            linked_by_key[key].append(url)

    old_assets = db.execute(
        """SELECT url,error FROM ingestion_asset
            WHERE kind='coffee' AND status='failed'""",
    ).fetchall()
    for old_url, old_error in old_assets:
        if old_url in linked or not _raw_not_found(old_error):
            continue
        old_key = upload_equivalence_key(old_url)
        if old_key is None:
            continue
        replacements = [url for url in linked_by_key.get(old_key, ()) if url != old_url]
        if len(replacements) > 1:
            stats["ambiguous"] += 1
            continue
        if len(replacements) != 1:
            continue
        replacement = replacements[0]
        if not _complete_linked_original(db, replacement):
            continue
        next_status = "archived" if db.execute(
            "SELECT document_id FROM ingestion_asset WHERE url=%s AND kind='coffee'",
            (old_url,),
        ).fetchone()[0] is not None else "review"
        marker = f"{RETIREMENT_PREFIX} {replacement}; prior error: {old_error}"
        result = db.execute(
            """UPDATE ingestion_asset SET status=%s,error=%s
                WHERE url=%s AND kind='coffee' AND status='failed' AND error IS NOT DISTINCT FROM %s
                RETURNING url""",
            (next_status, marker, old_url, old_error),
        ).fetchone()
        stats["retired"] += bool(result)
    return stats

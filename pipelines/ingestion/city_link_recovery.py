"""Native-verified recovery from a later, explicitly linked DANE city archive.

A later ZIP can retain older member PDFs. It is never a substitute date: every
member keeps its printed date, package and market, and the unavailable original
archive's complete roster remains unknown. No database or OCR provider calls.
"""

import io
import re
import zipfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256

import pdfplumber

VERSION = "city-link-recovery-v1"
_ARCHIVE_URL = (
    "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/"
    "sistema-de-informacion-de-precios-sipsa/"
    "componente-precios-mayoristas-julio-de-2023"
)
_BASE = "https://www.dane.gov.co/files/operaciones/SIPSA/"


@dataclass(frozen=True)
class CityAlias:
    canonical_url: str
    requested_day: date
    archive_day: date
    minimum_requested_price_members: int
    audit_sha256: str


ALIASES = {
    _BASE + "bol-SIPSADiario-regionales-22jul2023.zip": CityAlias(
        _BASE + "bol-SIPSADiario-regionales-24jul2023.zip",
        date(2023, 7, 22),
        date(2023, 7, 24),
        23,
        "a4f67faf5b18b081dd6b0075a12bc601bfaec0cf265af241ac8c90d6d9edd051",
    ),
}


@dataclass(frozen=True)
class RecoveredCityLink:
    canonical_url: str
    body: bytes = field(repr=False)
    archive_day: date
    evidence: dict


def _validate_member(body, filename, archive_day):
    from .city_reports import parse_city_pages
    from .ocr import needs_ocr
    from .pdf_sources import has_table_sized_image
    from .worker import clean, date_from_text

    if not body.startswith(b"%PDF"):
        raise ValueError("City recovery member is not a native PDF")
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        if not pdf.pages:
            raise ValueError("City recovery PDF has no pages")
        heading = pdf.pages[0].extract_text() or ""
        day = date_from_text(heading)
        recognized_grid = False
        empty_cells = True
        for page in pdf.pages:
            text = page.extract_text() or ""
            if needs_ocr(page, text) or has_table_sized_image(page):
                raise ValueError(
                    "City recovery member requires independent image review"
                )
            for table in page.extract_tables():
                header = next(
                    (
                        index
                        for index, row in enumerate(table)
                        if len(row) >= 7
                        and clean(row[0]) == "Producto"
                        and clean(row[1]) == "Presentación"
                    ),
                    None,
                )
                if header is None:
                    continue
                recognized_grid = True
                empty_cells = empty_cells and all(
                    clean(value) in ("", "0", "-", "n.d.")
                    for row in table[header + 2 :]
                    if len(row) >= 7
                    for value in row[3:7]
                )
        # Fully materialize before accepting a candidate. Date, market, package,
        # quantity and both bounds use the same native checks as publication.
        rows = list(parse_city_pages(pdf.pages, archive_day, allow_empty=True))
    if not rows and not (recognized_grid and empty_cells):
        raise ValueError("City recovery member has no verifiable native price grid")
    if day is None or any(row[1] != day for row in rows):
        raise ValueError("City recovery member has inconsistent printed dates")
    filename_date = re.search(
        r"(\d{1,2})-(\d{1,2})-(20\d{2})\.pdf$", filename, re.IGNORECASE
    )
    named_day = None
    filename_issue = None
    if filename_date:
        try:
            named_day = date(
                int(filename_date[3]), int(filename_date[2]), int(filename_date[1])
            )
        except ValueError:
            # The actual later ZIP contains "24-27-2023". An impossible
            # filename date cannot establish or override the printed date.
            filename_issue = (
                "Invalid calendar date in filename; explicit native date retained"
            )
        if named_day is not None and named_day != day:
            raise ValueError(
                "City recovery member filename conflicts with its printed date"
            )
    return {
        "filename": filename,
        "sha256": sha256(body).hexdigest(),
        "bytes": len(body),
        "observed_on": day.isoformat(),
        "filename_date_verified": named_day is not None,
        "filename_date_issue": filename_issue,
        "records": len(rows),
        "empty_template": not rows,
        "markets": sorted({row[4] for row in rows}),
    }


def recover_link(
    url: str,
    status: int,
    expected_day: date,
    fetcher: Callable[[str], bytes],
) -> RecoveredCityLink | None:
    """Validate an exact known alternate only after HTTP 404/410.

    ``ALIASES[url].archive_day`` is available before fetch so callers can archive
    the candidate with its actual ZIP date on the first immutable write. Changed
    bytes are revalidated; the audit SHA is evidence, not a content pin.
    """
    alias = ALIASES.get(url)
    if status not in (404, 410) or alias is None:
        return None
    if expected_day != alias.requested_day:
        raise ValueError("City recovery request differs from the verified missing date")
    body = fetcher(alias.canonical_url)
    if (
        not isinstance(body, bytes)
        or not body.startswith(b"PK\x03\x04")
        or len(body) > 128 * 1024 * 1024
    ):
        raise ValueError("City recovery did not return a bounded ZIP archive")
    with zipfile.ZipFile(io.BytesIO(body)) as bundle:
        files = [member for member in bundle.infolist() if not member.is_dir()]
        members = [
            member for member in files if member.filename.lower().endswith(".pdf")
        ]
        if (
            not members
            or len(files) > 500
            or sum(member.file_size for member in files) > 512 * 1024 * 1024
            or len({member.filename for member in files}) != len(files)
        ):
            raise ValueError("City recovery has unexpected ZIP contents or size")
        checked = [
            _validate_member(bundle.read(member), member.filename, alias.archive_day)
            for member in members
        ]
    requested = [
        member
        for member in checked
        if member["observed_on"] == expected_day.isoformat() and member["records"] > 0
    ]
    if len(requested) < alias.minimum_requested_price_members:
        raise ValueError(
            "City recovery does not retain all audited requested-day reports"
        )
    digest = sha256(body).hexdigest()
    evidence = {
        "processor_version": VERSION,
        "original_url": url,
        "original_http_status": status,
        "canonical_url": alias.canonical_url,
        "archive_url": _ARCHIVE_URL,
        "requested_day": expected_day.isoformat(),
        "archive_day": alias.archive_day.isoformat(),
        "validation": "all-native-city-members",
        "sha256": digest,
        "bytes": len(body),
        "audit_sha256": alias.audit_sha256,
        "matches_audited_bytes": digest == alias.audit_sha256,
        "member_count": len(checked),
        "requested_day_price_members": len(requested),
        "requested_day_records": sum(member["records"] for member in requested),
        "records": sum(member["records"] for member in checked),
        "members_by_date": dict(Counter(member["observed_on"] for member in checked)),
        "members": checked,
        "coverage_note": (
            "The later official ZIP retains these original requested-day PDFs. "
            "The unavailable earlier ZIP's full roster is unknown; this does not "
            "claim complete recovery of that missing ZIP. Every member retains "
            "its own printed date, market and package."
        ),
    }
    return RecoveredCityLink(alias.canonical_url, body, alias.archive_day, evidence)

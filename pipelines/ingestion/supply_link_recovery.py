"""One verified DANE supply bulletin whose official archive href is broken."""

import io
import re
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256

import pdfplumber

VERSION = "supply-link-recovery-v1"
FILES = "https://www.dane.gov.co/files/operaciones/SIPSA/"
ARCHIVE = (
    "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/"
    "sistema-de-informacion-de-precios-sipsa/componente-abastecimientos-1/"
    "componente-abastecimientos-boletin-quincenal-2024"
)
BROKEN_PDF = FILES + "bol-SIPSAabastecimiento-1raquinabr2024.pdf"
CANONICAL_PDF = FILES + "bol-SIPSAabastecimiento-1raquincenaAbril2024.pdf"
AUDITED_SHA256 = "5f13827ea2517a6238cb79108eb88a8efbeda30ca7df3a22224b13fd38848791"
PERIOD_START = date(2024, 4, 1)
PERIOD_END = date(2024, 4, 15)


@dataclass(frozen=True)
class RecoveredSupplyPDF:
    canonical_url: str
    body: bytes = field(repr=False)
    archive_day: None
    evidence: dict


def recover_link(url, status, expected_day, fetcher):
    """Accept only the audited original after its exact archive href returns 404/410.

    Candidate retention belongs to the caller and happens before this function
    checks the immutable hash and native printed publication/period. A changed
    source therefore remains reviewable but cannot silently replace the audit.
    """
    if url != BROKEN_PDF or status not in (404, 410):
        return None
    if expected_day is not None:
        raise ValueError("Supply recovery requires the archive's undated fortnight asset")

    body = fetcher(CANONICAL_PDF)
    if not isinstance(body, bytes) or not body.startswith(b"%PDF"):
        raise ValueError("Supply recovery candidate is not a native PDF")
    digest = sha256(body).hexdigest()
    if digest != AUDITED_SHA256:
        raise ValueError("Supply recovery candidate differs from immutable audited SHA-256")

    from .supply_period_summaries import period
    from .worker import date_from_text

    with pdfplumber.open(io.BytesIO(body)) as pdf:
        if len(pdf.pages) != 15:
            raise ValueError("Supply recovery candidate page count changed")
        cover = pdf.pages[0].extract_text() or ""
    if not re.search(r"Componente de Abastecimiento de Alimentos\s*\(SIPSA_A\)", cover):
        raise ValueError("Supply recovery lacks the native SIPSA_A heading")
    if date_from_text(cover[:200]) != date(2024, 5, 3):
        raise ValueError("Supply recovery printed publication date differs")
    captions = re.findall(
        r"^Primera quincena de abril de 2024\s*$",
        cover,
        re.MULTILINE | re.IGNORECASE,
    )
    if len(captions) != 1 or period(captions[0]) != (
        PERIOD_START,
        PERIOD_END,
        "first_fortnight",
    ):
        raise ValueError("Supply recovery native report period differs")
    if not re.search(
        r"1 al 15 de marzo y 1 al 15 de abril de 2024", cover, re.IGNORECASE
    ):
        raise ValueError("Supply recovery native comparison period differs")

    return RecoveredSupplyPDF(
        CANONICAL_PDF,
        body,
        None,
        {
            "recovery_version": VERSION,
            "original_url": url,
            "original_http_status": status,
            "canonical_url": CANONICAL_PDF,
            "archive_url": ARCHIVE,
            "archive_label": "Abril 2024; Boletín 1ra quincena",
            "printed_publication_date": "2024-05-03",
            "period_start": PERIOD_START.isoformat(),
            "period_end": PERIOD_END.isoformat(),
            "frequency": "first_fortnight",
            "sha256": digest,
            "audited_sha256": AUDITED_SHA256,
            "bytes": len(body),
            "pages": 15,
            "coverage_note": (
                "Recovered only the verified first-fortnight April 2024 PDF. "
                "The archive's companion XLSX remains HTTP 404 with no verified "
                "alternate. Native rounded PDF market summaries can be published; "
                "the missing workbook's detailed values are not inferred."
            ),
        },
    )

"""Exact official PDF alias repairs with native date and period validation.

A replacement is used only after its broken publisher alias returns404/410.
The caller retains candidate bytes before validation and archives accepted bytes
under the working URL, preserving the original alias in resolution evidence.
"""

import io
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256

import pdfplumber

VERSION = "pdf-link-recovery-v1"
_FILES = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
_PAGE = "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/"


@dataclass(frozen=True)
class PDFAlias:
    canonical_url: str
    kind: str
    observed_on: date
    period_start: date
    archive_url: str
    archive_label: str
    audit_sha256: str


ALIASES = {
    _FILES + "mayoristas_Julio_25_2014.pdf": PDFAlias(
        _FILES + "mayoristas_julio_25_2014.pdf",
        "daily-pdf",
        date(2014, 7, 25),
        date(2014, 7, 25),
        _PAGE + "componente-precios-mayoristas-julio-de-2014-1",
        "Boletín - 25 de Julio",
        "eccd3f5e010e8e67cd6f83d23c83487573327c59c87ba37b2e68f4524c610c17",
    ),
    _FILES + "bol_23jul_al_29jul_202.pdf": PDFAlias(
        _FILES + "bol_23jul_al_29jul_2022.pdf",
        "dane-weekly-pdf",
        date(2022, 7, 29),
        date(2022, 7, 23),
        _PAGE + "mayoristas-boletin-semanal-1/boletin-mayorista-semanal-2022",
        "Julio · Semana del 23 al 29 · Boletín Técnico; companion anex_23jul_al_29jul_2022.xlsx",
        "dedc4f59a2a6eaba26f9eb838c93a318df42b2f8c5d2e7d81c8dfc8f6dfb0c15",
    ),
}


@dataclass(frozen=True)
class RecoveredPDF:
    canonical_url: str
    body: bytes = field(repr=False)
    archive_day: date
    evidence: dict


def recover_link(url, status, expected_day, fetcher, *, kind):
    from . import dane_weekly
    from .worker import date_from_text

    rule = ALIASES.get(url)
    if status not in (404, 410) or rule is None or kind != rule.kind:
        return None
    if expected_day is not None and expected_day != rule.observed_on:
        raise ValueError("PDF link recovery date conflicts with the verified archive")
    body = fetcher(rule.canonical_url)
    if not isinstance(body, bytes) or not body.startswith(b"%PDF"):
        raise ValueError("PDF link recovery did not return an original PDF")
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        heading = (pdf.pages[0].extract_text() or "")[:700] if pdf.pages else ""
        if date_from_text(heading) != rule.observed_on:
            raise ValueError("PDF link recovery printed date differs from archive")
        if not any(word in heading.lower() for word in ("sipsa", "precios mayoristas")):
            raise ValueError(
                "PDF link recovery lacks the official price-report heading"
            )
        pages = len(pdf.pages)
    valid = review = 0
    if kind == "dane-weekly-pdf":
        rows = dane_weekly.parse_pdf(body, rule.canonical_url)
        if not rows or any(
            row["date"] != rule.observed_on.isoformat()
            or row["period_start"] != rule.period_start.isoformat()
            for row in rows
        ):
            raise ValueError("PDF link recovery monetary period differs from archive")
        valid = sum(row["price"] is not None for row in rows)
        review = len(rows) - valid
        if not valid:
            raise ValueError("PDF link recovery has no verified monetary rows")
    digest = sha256(body).hexdigest()
    return RecoveredPDF(
        rule.canonical_url,
        body,
        rule.observed_on,
        {
            "recovery_version": VERSION,
            "original_url": url,
            "original_http_status": status,
            "canonical_url": rule.canonical_url,
            "archive_url": rule.archive_url,
            "archive_label": rule.archive_label,
            "observed_on": rule.observed_on.isoformat(),
            "period_start": rule.period_start.isoformat(),
            "printed_heading": heading,
            "sha256": digest,
            "pages": pages,
            "matches_audited_bytes": digest == rule.audit_sha256,
            "validated_price_rows": valid,
            "review_rows": review,
            "validation_basis": "Exact native dated daily bulletin; normal extraction follows"
            if kind == "daily-pdf"
            else "All native weekly monetary rows retain the exact printed week",
        },
    )

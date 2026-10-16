"""Parse DANE city-page observations used to schedule source rechecks.

Page labels and row signatures are hints to verify retained ZIP bytes; they do
not replace source documents, printed dates, or publication evidence. Matching
registered sources and unchanged printed dates are required for a hint.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


BASE = "https://www.dane.gov.co"
MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}
PAGE_RE = re.compile(
    r"^/index\.php/estadisticas-por-tema/agropecuario/"
    r"sistema-de-informacion-de-precios-sipsa/"
    r"componente-precios-mayoristas-[a-z]+-de-(20\d{2})$"
)
CURRENT_DAILY_PAGE_URL = (
    "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/"
    "sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas"
)
CURRENT_DAILY_PAGE_PATH = "/index.php/estadisticas-por-tema/agropecuario/" \
    "sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas"
ZIP_RE = re.compile(
    r"^/files/operaciones/SIPSA/bol-SIPSADiario-regionales-"
    r"(\d{2})([a-z]{3})(20\d{2})\.zip$"
)
LABEL_RE = re.compile(
    r"^(?:Informes por ciudades\s*\(actualizado a .+\)|"
    r"Informes por ciudades sábado \d{1,2} de [a-záéíóú]+)$", re.I
)
MONTH_ABBR = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


@dataclass(frozen=True)
class RowObservation:
    url: str
    observed_on: date
    row_date_label: str
    archive_label: str
    row_signature: str


def _ascii(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()


def is_exact_official_month_page_url(page_url: str) -> bool:
    parsed = urlparse(page_url)
    try:
        port = parsed.port
    except ValueError:
        return False
    return (parsed.scheme == "https" and parsed.hostname == "www.dane.gov.co"
            and port in (None, 443) and parsed.username is None and parsed.password is None
            and not parsed.query and not parsed.fragment
            and (parsed.path == CURRENT_DAILY_PAGE_PATH or PAGE_RE.fullmatch(parsed.path) is not None))


def parse_current_month_rows(html: bytes | str, page_url: str, *, current_year: int) -> dict[str, RowObservation]:
    """Return exact DANE city ZIP row observations; reject ambiguous duplicates.

    `current_year` is explicit so callers cannot turn a historical page scan
    into an unbounded archive refresh. This extracts only links in dated table
    rows on an exact DANE monthly page and only their literal source labels.
    """
    parsed = urlparse(page_url)
    current_page = parsed.path == CURRENT_DAILY_PAGE_PATH
    match = PAGE_RE.fullmatch(parsed.path)
    if not is_exact_official_month_page_url(page_url):
        raise ValueError("not an exact official DANE monthly page")
    year = current_year if current_page else int(match.group(1))
    if year > current_year:
        raise ValueError("monthly page is later than the explicitly selected cycle year")

    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, RowObservation] = {}
    for anchor in soup.select("a[href]"):
        absolute = urljoin(page_url, anchor["href"])
        target = urlparse(absolute)
        zip_match = ZIP_RE.fullmatch(target.path)
        if (target.scheme != "https" or target.netloc.lower() != "www.dane.gov.co"
                or target.query or target.fragment or not zip_match):
            continue
        day, month_abbr, archive_year = zip_match.groups()
        if int(archive_year) != year:
            continue
        cell = anchor.find_parent("td")
        row = cell.find_parent("tr") if cell else None
        if row is None:
            raise ValueError("official city ZIP link has no table row")
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 2:
            raise ValueError("official city ZIP row has no date/context cells")
        row_date = " ".join(cells[0].get_text(" ", strip=True).split())
        label = " ".join(anchor.get_text(" ", strip=True).split())
        if not LABEL_RE.fullmatch(label):
            raise ValueError("city ZIP row label is not a recognized update label")
        date_match = re.search(r"\b(\d{1,2})\b", _ascii(row_date))
        if not date_match:
            raise ValueError("city ZIP row date is not explicit")
        row_day = int(date_match.group(1))
        observed_on = date(year, MONTH_ABBR[month_abbr], int(day))
        if row_day != observed_on.day or MONTHS[_ascii(row_date).strip().lower().split()[-1]] != observed_on.month:
            raise ValueError("table row date and ZIP path date disagree")
        # Exact literal context and label are retained. This digest only marks
        # a re-fetch hint; it never establishes changed ZIP bytes or authority.
        import hashlib
        signature_bytes = "\0".join((row_date, label, absolute)).encode("utf-8")
        observation = RowObservation(
            url=absolute,
            observed_on=observed_on,
            row_date_label=row_date,
            archive_label=label,
            row_signature=hashlib.sha256(signature_bytes).hexdigest(),
        )
        prior = result.get(absolute)
        if prior is not None and prior != observation:
            raise ValueError("duplicate city ZIP URL has conflicting row observations")
        result[absolute] = observation
    return result


def changed_complete_asset_hints(previous: dict[str, RowObservation], current: dict[str, RowObservation], *, registered: dict[str, tuple[date, str]]) -> list[tuple[str, str, str]]:
    """Return URL, old signature, new signature for exact complete sources only.

    The caller supplies the status snapshot. Failed/review assets, additions,
    removals, changed dates, and unregistered links intentionally do not yield
    an automatic refresh request here.
    """
    hints = []
    for url in sorted(previous.keys() & current.keys()):
        before, after = previous[url], current[url]
        row = registered.get(url)
        if row is None or row != (after.observed_on, "complete"):
            continue
        if before.observed_on != after.observed_on:
            continue
        if before.row_signature != after.row_signature:
            hints.append((url, before.row_signature, after.row_signature))
    return hints

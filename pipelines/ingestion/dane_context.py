"""Narrow discovery of official SIPSA explanatory PDFs, never guessed prices."""

import re
from urllib.parse import unquote, urlsplit

_REFERENCE_NAMES = re.compile(
    r"(?:acerca-de-sipsa-mensual|"
    r"inf-monitoreomesatecnicanacionalcompraspublicas-(?:i|ii|iii|iv)trim20\d{2}|"
    r"informe-especial-sipsa-comportamiento-precios-mayoristas-abastecimiento-20\d{2}-[a-z]+-\d{2}a\d{2}|"
    r"cp_sipsa_[a-z]+_20\d{2}|presentacion_sipsa_[a-z]+_20\d{2}|"
    r"nota-tecnica-certificacion-sipsa-abastecimiento|cp_mensual_abr_20133)\.pdf$"
)


def is_context_source(url):
    """Only audited families: a price PDF cannot be reclassified by its label."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"dane.gov.co", "www.dane.gov.co"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or not parsed.path.startswith("/files/")
    ):
        return False
    return bool(
        _REFERENCE_NAMES.fullmatch(unquote(parsed.path.rsplit("/", 1)[-1]).lower())
    )


def queue_context_sources(db, entries):
    """Accept worker.links' (label, URL) entries; retain printed periods as text.

    Dates in filenames identify documents, not observations. Generic page
    extraction preserves monetary prose, percentages, supply totals and charts
    as context without manufacturing a quote or assigning a guessed month.
    """
    from .worker import queue

    urls = dict.fromkeys(url for _label, url in entries if is_context_source(url))
    for url in urls:
        queue(db, url, "context-pdf")
    return len(urls)

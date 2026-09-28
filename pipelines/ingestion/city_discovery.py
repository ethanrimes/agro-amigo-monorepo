"""DANE city ZIP filename generations with explicit publication dates.

Discovery identifies the source archive day; every PDF still independently
validates its printed date and price identity during normal city publication.
No date is inferred from ZIP member order, download time, or an adjacent report.
"""

import re
from datetime import date
from urllib.parse import urlparse

# The February 2025 official archive explicitly labels these rows 5, 6 and 7
# February. Their downloaded PDF members independently print the same dates.
# The October 2022 archive links a shortened -01-10-20 filename. Its sole
# Bogotá member visually prints 01 October 2022 (native CID text needs OCR).
# This only discovers/archives it; normal independent price validation still applies.
# These are publisher filenames, not replacements: retain the literal URL.
_VERIFIED_ARCHIVE_DATES = {
    "/files/operaciones/sipsa/bol-sipsadiario-regionales-7febb2025.zip": date(
        2025, 2, 7
    ),
    "/files/operaciones/sipsa/bol-sipsadiario-regionales-6eb2025.zip": date(2025, 2, 6),
    "/files/operaciones/sipsa/bol-sipsadiario-regionales-5eb2025.zip": date(2025, 2, 5),
    "/files/investigaciones/agropecuario/sipsa/bol-reg-01-10-20.zip": date(2022, 10, 1),
}


def archive_day(url, label=""):
    """Return only an explicit valid day from an official city archive link."""
    from .worker import date_from_text

    parsed = urlparse(url)
    path = parsed.path.lower()
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ("www.dane.gov.co", "dane.gov.co")
        or not path.startswith("/files/")
        or not path.endswith(".zip")
    ):
        return None
    if path in _VERIFIED_ARCHIVE_DATES:
        return _VERIFIED_ARCHIVE_DATES[path]
    # The old reports use numeric dates and omit 'regional'/'ciudad' entirely.
    # Both exact filename families were checked against actual native PDFs.
    numeric = re.search(r"/(?:sipsa|bol-reg)-(\d{1,2})-(\d{2})-(20\d{2})\.zip$", path)
    if numeric:
        try:
            return date(int(numeric[3]), int(numeric[2]), int(numeric[1]))
        except ValueError:
            return None
    if any(word in path for word in ("regional", "ciudad")):
        return date_from_text(path) or date_from_text(label)
    return None

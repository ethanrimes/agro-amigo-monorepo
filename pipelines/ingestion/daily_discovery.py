"""Exact DANE daily publisher filenames whose dates are not machine-parseable.

These are existing official download URLs, not alternate guesses. The February
2014 official archive labels and each downloaded original independently agree.
Normal native date/price validation still applies after discovery.
"""

from datetime import date
from urllib.parse import urlparse

VERIFIED_DAILY_DATES = {
    "/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_199_2014.pdf": date(
        2014, 2, 19
    ),
    "/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_5r_2014.pdf": date(
        2014, 2, 5
    ),
    "/files/investigaciones/agropecuario/sipsa/mayoristas_febreror_5_2014.xls": date(
        2014, 2, 5
    ),
}


def verified_daily_day(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in (
        "www.dane.gov.co",
        "dane.gov.co",
    ):
        return None
    return VERIFIED_DAILY_DATES.get(parsed.path.lower())

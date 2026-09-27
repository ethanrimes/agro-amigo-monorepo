"""Bounded official SIPSA query recovery for verified daily source problems.

The public explorer is linked from DANE's SIPSA homepage. Its table explicitly
distinguishes PROMEDIO, MINIMO and MAXIMO. These observations retain a separate
series from daily annexes; no midpoint, adjacent date, or narrative guess is
substituted. The caller archives every returned native document and performs
publication. This module makes no database calls.
"""

import json
import math
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256

from bs4 import BeautifulSoup

VERSION = "dane-daily-query-v1"
EXPLORER_URL = (
    "https://apps.dane.gov.co/pentaho/api/repos/"
    "%3Apublic%3ASIPSA%3ASIPSAV17.wcdf/generatedContent"
)
ROOT_URL = (
    "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/"
    "sistema-de-informacion-de-precios-sipsa"
)
API_URL = "https://apps.dane.gov.co/pentaho/plugin/cda/api/doQuery"
QUERY_PATH = "/public/SIPSA/SIPSAV17.cda"
GUIDE_URL = "https://www.dane.gov.co/files/operaciones/SIPSA/brochure-SIPSA-2023.pdf"
UNIT_NOTE = (
    "Los precios reportados son $/kg, para los huevos y el bocadillo son "
    "$/unidad y los del aceite, el jugo y el vinagre $/litro."
)
MISSING_DAILY_URLS = {
    "https://www.dane.gov.co/files/operaciones/SIPSA/"
    "bol-SIPSADiario-regionales-22jul2023.zip": date(2023, 7, 22),
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "mayoristas_abril_18_2013.xls": date(2013, 4, 18),
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "mayoristas_anexo_oct_23_2012.xls": date(2012, 10, 23),
}
VERIFIED_DATE_CONFLICTS = {
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "mayoristas_julio_06_2012.xls": (
        date(2012, 7, 6),
        "e4ef45aa4c396d3aab17db715a07f7e5cb1b16afaf825539e4031b8b5c45d221",
    ),
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "mayoristas_julio_09_2012.xls": (
        date(2012, 7, 9),
        "12bcf11046762dc6c9d3804aa8334caa2afd1171f1194fc2b22d947755627ef2",
    ),
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "mayoristas_anexo_dic_5_2012.xls": (
        date(2012, 12, 5),
        "cf3a0c3e001b5cc867ac43d609afb9aafe9a51eba4c4d638315febe6978d8445",
    ),
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "mayoristas_julio_12_2013.xls": (
        date(2013, 7, 12),
        "302aa6336d7b53016c2afcf79bdc03499637663effb575341606e1dbb9ebb3f9",
    ),
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "mayoristas_mayo_20_2013.xls": (
        date(2013, 5, 20),
        "7e3dd859361ac543fe71f740b9898117ebcefc6b69a9ae2815a94155bc1f7088",
    ),
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "mayoristas_junio_11_2014.xls": (
        date(2014, 6, 11),
        "82cc122be75103f787e1e84d92ffee9da227e693c22dfcb7190c8e8430aac3fc",
    ),
}
_COLUMNS = ("FECHA", "FUENTE", "ARTICULO", "PROMEDIO", "MINIMO", "MAXIMO")
_MAX_BYTES = 10_000_000
_MAX_ROWS = 20_000


@dataclass(frozen=True)
class NativeQueryDocument:
    role: str
    url: str
    body: bytes = field(repr=False)
    media_type: str
    metadata: dict


@dataclass(frozen=True)
class DailyQueryRecovery:
    source_url: str
    documents: tuple[NativeQueryDocument, ...]
    rows: tuple[tuple, ...]
    evidence: dict


def _json_table(body):
    if not isinstance(body, bytes) or len(body) > _MAX_BYTES:
        raise ValueError("SIPSA query response exceeds the bounded native size")
    data = json.loads(body)
    if not isinstance(data, dict) or not isinstance(data.get("resultset"), list):
        raise ValueError("SIPSA query did not return a native resultset")  # noqa: TRY004 -- malformed publisher content is reviewable data
    total = str(data.get("queryInfo", {}).get("totalRows", ""))
    if not total.isdigit() or int(total) > _MAX_ROWS:
        raise ValueError("SIPSA query has no bounded verifiable totalRows")
    if int(total) != len(data["resultset"]):
        raise ValueError("SIPSA query resultset is incomplete or paginated")
    return data


def _options(body, label, maximum):
    rows = _json_table(body)["resultset"]
    if not rows or len(rows) > maximum:
        raise ValueError(f"SIPSA {label} options are empty or exceed the bound")
    options = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 1:
            raise ValueError(f"Unexpected SIPSA {label} selector schema")
        value = row[0]
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ValueError(f"Invalid SIPSA {label} selector identity")
        options.append(value)
    if len(options) != len(set(options)):
        raise ValueError(f"Duplicate SIPSA {label} selector identities")
    return options


def unit_for(product):
    """Literal explorer unit-note exception groups; no package conversion."""
    name = unicodedata.normalize("NFKD", product).encode("ascii", "ignore").decode()
    if re.match(r"^(huevos?|bocadillos?)\b", name, re.IGNORECASE):
        return "unit"
    if re.match(r"^(aceites?|jugos?|vinagres?)\b", name, re.IGNORECASE):
        return "litre"
    return "kg"


def parse_response(body, expected_day, sources, products):
    """Validate every identity/date/price before returning any publishable rows."""
    data = _json_table(body)
    metadata = data.get("metadata", [])
    if (
        len(metadata) != len(_COLUMNS)
        or tuple(m.get("colName") for m in metadata) != _COLUMNS
        or [m.get("colIndex") for m in metadata] != list(range(len(_COLUMNS)))
    ):
        raise ValueError("Unexpected SIPSA daily price columns")
    source_set, product_set = set(sources), set(products)
    rows, identities = [], set()
    for index, values in enumerate(data["resultset"]):
        if not isinstance(values, list) or len(values) != 6:
            raise ValueError("Malformed SIPSA daily price row")
        day, market, product, mean, low, high = values
        if day != expected_day.isoformat():
            raise ValueError("SIPSA query returned an unexpected observation date")
        # Empty selections return [date,null,null,null,null,null], not all data.
        if (
            not isinstance(market, str)
            or not isinstance(product, str)
            or market not in source_set
            or product not in product_set
        ):
            raise ValueError("SIPSA query returned an unknown or empty identity")
        prices = (mean, low, high)
        if any(
            isinstance(x, bool)
            or not isinstance(x, (int, float))
            or not math.isfinite(x)
            or x <= 0
            for x in prices
        ):
            raise ValueError("Invalid SIPSA daily price value")
        if not low <= mean <= high:
            raise ValueError("SIPSA published mean is outside the printed range")
        key = (day, market, product)
        if key in identities:
            raise ValueError("Duplicate SIPSA daily quote identity")
        identities.add(key)
        rows.append(
            (
                f"JSON resultset[{index}]; PROMEDIO/MINIMO/MAXIMO",
                "dane-daily-query",
                expected_day,
                product,
                market,
                unit_for(product),
                float(mean),
                None,
                {
                    "parser_version": VERSION,
                    "extraction_method": "native-official-json",
                    "price_statistic": "published_mean",
                    "price_mean": mean,
                    "price_min": low,
                    "price_max": high,
                    "currency": "COP",
                    "currency_basis": "DANE Colombia wholesale prices in pesos ($)",
                    "period": "daily",
                    "source_columns": list(_COLUMNS),
                    "unit_evidence_url": EXPLORER_URL,
                    "unit_evidence": UNIT_NOTE,
                    "source_page": EXPLORER_URL,
                    "query_date": day,
                },
            )
        )
    if not rows:
        raise ValueError("SIPSA query has no validated prices for the exact day")
    return tuple(rows)


def recover_daily(
    url: str,
    error_status: int | None,
    expected_day: date,
    fetcher: Callable[[str, dict | None], bytes],
    *,
    check_budget: Callable[[], None] | None = None,
    original_data: bytes | None = None,
    recovery_reason: str | None = None,
    source_sha256: str | None = None,
) -> DailyQueryRecovery | None:
    """Five bounded requests: unit-page GET and four native JSON POSTs.

    ``fetcher(url, None)`` performs GET; ``fetcher(url, parameters)`` performs
    a form POST with repeated keys for list values (CDF traditional=true).
    It must raise on HTTP failures and honor the caller's network deadline.
    The last document is the complete daily response used by every row locator.
    """
    if original_data is not None:
        computed_sha = sha256(original_data).hexdigest()
        if source_sha256 is not None and source_sha256 != computed_sha:
            raise ValueError("SIPSA original bytes do not match the supplied SHA")
        source_sha256 = computed_sha
    if recovery_reason is None:
        recovery_reason = (
            "verified-date-conflict"
            if error_status is None and original_data is not None
            else "missing-source"
        )
    if recovery_reason == "missing-source":
        if error_status not in (404, 410) or url not in MISSING_DAILY_URLS:
            return None
        approved_day = MISSING_DAILY_URLS[url]
    elif recovery_reason == "verified-date-conflict":
        approved = VERIFIED_DATE_CONFLICTS.get(url)
        if approved is None:
            return None
        if source_sha256 != approved[1] or error_status not in (None, 200):
            raise ValueError(
                "SIPSA source-date recovery requires the verified original SHA"
            )
        approved_day = approved[0]
    else:
        return None
    if expected_day != approved_day:
        raise ValueError("SIPSA recovery date does not match the missing source")
    documents = []

    def fetch(role, target, params=None):
        if check_budget:
            check_budget()
        body = fetcher(target, params)
        if not isinstance(body, bytes) or len(body) > _MAX_BYTES:
            raise ValueError("SIPSA native response exceeds the bounded size")
        documents.append(
            NativeQueryDocument(
                role,
                target,
                body,
                "application/json" if params is not None else "text/html",
                {
                    "request_method": "POST" if params is not None else "GET",
                    "request_parameters": params,
                    "observed_on": expected_day.isoformat(),
                    "original_url": url,
                    "original_missing_url": url
                    if recovery_reason == "missing-source"
                    else None,
                    "recovery_reason": recovery_reason,
                    "conflicting_original_sha256": source_sha256,
                    "sha256": sha256(body).hexdigest(),
                    "publisher": "DANE",
                    "processor_version": VERSION,
                },
            )
        )
        return body

    page = fetch("unit-evidence", EXPLORER_URL)
    text = " ".join(
        BeautifulSoup(page, "html.parser").get_text(" ", strip=True).split()
    )
    if UNIT_NOTE not in text:
        raise ValueError("Official SIPSA explorer unit contract changed or unavailable")
    base = {
        "path": QUERY_PATH,
        "outputIndexId": 1,
        "pageSize": 0,
        "pageStart": 0,
        "sortBy": "",
    }
    sources = _options(
        fetch("sources", API_URL, {**base, "dataAccessId": "qryFuente"}),
        "source",
        512,
    )
    groups = _options(
        fetch("groups", API_URL, {**base, "dataAccessId": "qryGrupo"}), "group", 50
    )
    products = _options(
        fetch(
            "products",
            API_URL,
            {**base, "dataAccessId": "qryArticulo", "paramparcGrupo": groups},
        ),
        "product",
        4096,
    )
    params = {
        **base,
        "dataAccessId": "qryTabla",
        "parampardPeriodoIni": expected_day.isoformat(),
        "parampardPeriodoFin": expected_day.isoformat(),
        "paramparsPrecio": "Diario",
        "paramparcFuente": sources,
        "paramparcArticulo": products,
    }
    body = fetch("daily-prices", API_URL, params)
    rows = parse_response(body, expected_day, sources, products)
    return DailyQueryRecovery(
        API_URL,
        tuple(documents),
        rows,
        {
            "processor_version": VERSION,
            "original_url": url,
            "original_missing_url": url
            if recovery_reason == "missing-source"
            else None,
            "original_http_status": error_status,
            "recovery_reason": recovery_reason,
            "conflicting_original_sha256": source_sha256,
            "canonical_source_url": API_URL,
            "source_page": EXPLORER_URL,
            "official_discovery_page": ROOT_URL,
            "publisher_guide": GUIDE_URL,
            "query_date": expected_day.isoformat(),
            "series": "dane-daily-query",
            "statistic": "published_mean",
            "coverage": "all public explorer source/product selector identities",
            "requested_sources": len(sources),
            "requested_groups": len(groups),
            "requested_products": len(products),
            "returned_records": len(rows),
            "returned_sources": len({r[4] for r in rows}),
            "returned_products": len({r[3] for r in rows}),
            "pagination": {
                "pageSize": 0,
                "pageStart": 0,
                "totalRows": len(rows),
                "native_resultset_count_verified": True,
            },
            "daily_response_sha256": sha256(body).hexdigest(),
        },
    )

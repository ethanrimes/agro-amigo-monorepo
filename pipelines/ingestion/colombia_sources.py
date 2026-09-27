"""Primary Colombian price sources, with explicit currency, basis and provenance.

Pure parsers: no requests, credentials or database operations. ``discover()`` returns
trusted roots; ``discover(body, url, kind)`` follows only public, observed links.
Every returned row has an exact source locator. Rows with ``quality_issue`` retain
ambiguous source data and MUST NOT enter a published price projection.
"""

from __future__ import annotations

import calendar
import csv
import io
import json
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

VERSION = "colombia-prices-v3"
AGRONET_CACAO = "https://agronet.gov.co/noticias/precio-de-referencia-semanal-de-compra-de-cacao-fuente-industria-nacional-exportadores-0"
FEDEPALMA_FFP = "https://fedepalma.org/fondo-de-fomento-palmero-ffp/"
FEDEGAN_PRICES = "https://estadisticas.fedegan.org.co/Indicadores/13"
PORK_PRICES = "https://porkcolombia.co/ronda_de_precios/"
CORABASTOS_PRICES = "https://corabastos.com.co/boletin-precios-corabastos/"
CORABASTOS_MEDIA = (
    "https://corabastos.com.co/wp-json/wp/v2/media?search=Boletin&per_page=100&page=1"
)
PORK_POSTS = (
    "https://porkcolombia.co/wp-json/wp/v2/ronda_de_precios?per_page=100&page=1"
)
ROOTS = (
    (AGRONET_CACAO, "colombia-agronet-cacao"),
    (AGRONET_CACAO.removesuffix("-0"), "colombia-agronet-cacao"),
    (FEDEPALMA_FFP, "colombia-fedepalma-ffp"),
    (FEDEGAN_PRICES, "colombia-fedegan-index"),
    (PORK_PRICES, "colombia-pork-index"),
    (CORABASTOS_PRICES, "colombia-corabastos-index"),
    (CORABASTOS_MEDIA, "colombia-corabastos-media"),
    (PORK_POSTS, "colombia-pork-posts"),
)
MONTHS = dict(
    zip(
        [
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ],
        range(1, 13),
    )
)
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["setiembre"] = 9
PUBLISHERS = {
    "colombia-corabastos-media": "Corabastos S.A.",
    "colombia-pork-posts": "Porkcolombia / FNP",
    "colombia-agronet-cacao": "UPRA / AgroNET",
    "colombia-fedepalma-ffp": "MADR / Fedepalma FFP",
    "colombia-fedegan-index": "Fedegán / FNG",
    "colombia-fedegan-csv": "Fedegán / FNG",
    "colombia-pork-index": "Porkcolombia / FNP",
    "colombia-pork-pdf": "Porkcolombia / FNP",
    "colombia-corabastos-index": "Corabastos S.A.",
    "colombia-corabastos-pdf": "Corabastos S.A.",
    "colombia-evidence": "MADR / Fedepalma FFP",
}
INDEX_KINDS = {
    "colombia-fedegan-index",
    "colombia-pork-index",
    "colombia-corabastos-index",
    "colombia-corabastos-media",
    "colombia-pork-posts",
}
TRUSTED_HOSTS = {urlparse(u).hostname for u, _ in ROOTS}
TRUSTED_HOSTS.update({"www.fedepalma.org", "www.minagricultura.gov.co"})


class NormalExtractionFailed(ValueError):
    """Price-table image pages need OCR after native text extraction failed."""

    def __init__(self, message, pages):
        super().__init__(message)
        self.pages = tuple(pages)
        self.required_pages = self.pages


def clean(value):
    """Strip invisible formatting without inserting spaces inside years/prices."""
    value = "" if value is None else str(value)
    return " ".join(
        "".join(c for c in value if unicodedata.category(c) != "Cf").split()
    )


def slug(value):
    value = (
        unicodedata.normalize("NFKD", clean(value))
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def _soup(body, *, latin1=False):
    if isinstance(body, bytes):
        body = body.decode("latin1" if latin1 else "utf-8-sig")
    return BeautifulSoup(body, "html.parser")


def _trusted(url):
    p = urlparse(url)
    return (
        p.scheme == "https"
        and p.hostname in TRUSTED_HOSTS
        and not p.username
        and not p.password
    )


def discover(body=None, url=None, kind=None, today=None):
    """Discover source pages, original PDFs and public full-history CSV exports.

    The caller archives every fetched body, rechecks roots daily, revisits completed
    mutable URLs, and recursively queues returned links. Evidence-only PDFs are
    preserved without pretending their narrative text is a transactional quote.
    """
    if body is None:
        return list(ROOTS)
    if not url or not _trusted(url):
        raise ValueError("Untrusted Colombian source URL")
    if kind in {
        "colombia-fedegan-csv",
        "colombia-pork-pdf",
        "colombia-corabastos-pdf",
        "colombia-evidence",
    }:
        return []
    now = today or datetime.now(ZoneInfo("America/Bogota")).date()
    found = set()

    def add(candidate, child_kind):
        candidate = urljoin(url, candidate.strip()).split("#", 1)[0]
        if _trusted(candidate):
            found.add((candidate, child_kind))

    if kind in {"colombia-corabastos-media", "colombia-pork-posts"}:
        records = json.loads(body)
        if not isinstance(records, list):
            raise ValueError("Public WordPress price archive did not return a list")
        for entry in records:
            if kind == "colombia-corabastos-media":
                candidate = entry.get("source_url", "")
                if urlparse(candidate).path.lower().endswith(".pdf"):
                    add(candidate, "colombia-corabastos-pdf")
            elif entry.get("status") == "publish":
                add(entry.get("link", ""), "colombia-pork-index")
        if len(records) == 100:
            parsed = urlparse(url)
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            query["page"] = str(int(query.get("page", 1)) + 1)
            add(parsed._replace(query=urlencode(query)).geturl(), kind)
        return sorted(found)
    soup = _soup(body, latin1="fedegan.org.co" in url)
    if kind == "colombia-fedegan-index":
        # Match the publisher's export button arguments, not invented indicator IDs.
        text = body.decode("latin1") if isinstance(body, bytes) else body
        for block in re.findall(
            r"function exportData\d+\(\)\{(.*?)\n\s*\}", text, re.DOTALL
        ):
            values = dict(
                re.findall(
                    r"exportForm\.(p\w+)\.value\s*=\s*['\"]?([^;'\"]+)['\"]?;", block
                )
            )
            if values.get("pId", "").strip() not in FEDEGAN:
                continue
            values = {k: v.strip() for k, v in values.items()}
            values["pSd"] = "01-01-1900"
            # Constant within a year, so daily updates revise the same asset URL.
            values["pEd"] = f"31-12-{now.year}"
            add(
                "https://estadisticas.fedegan.org.co/DOC/export.jsp?"
                + urlencode(values),
                "colombia-fedegan-csv",
            )
    elif kind == "colombia-corabastos-index":
        for calendar_node in soup.select("[data-events]"):
            events = json.loads(calendar_node["data-events"])
            for event in events:
                if event.get("start", "9999")[:10] <= now.isoformat():
                    candidate = event.get("url") or event.get("event_link", {}).get(
                        "url", ""
                    )
                    if re.search(r"/Boletin[^/]*\.pdf$", candidate, re.IGNORECASE):
                        add(candidate, "colombia-corabastos-pdf")
    elif kind == "colombia-pork-index":
        for a in soup.select("a[href], iframe[src]"):
            href = a.get("href") or a.get("src", "")
            target = urljoin(url, href.strip())
            if urlparse(target).hostname != "porkcolombia.co":
                continue
            path = urlparse(target).path
            if path.startswith("/ronda_de_precios/"):
                add(target, "colombia-pork-index")
            elif path.lower().endswith(".pdf") and (
                a.name == "iframe" or "descargar" in clean(a.get_text()).lower()
            ):
                add(target, "colombia-pork-pdf")
    elif kind == "colombia-fedepalma-ffp":
        for table in soup.select("table"):
            if "Aceite de palma crudo" not in table.get_text():
                continue
            for a in table.select("a[href]"):
                if urlparse(a["href"]).path.lower().endswith(".pdf"):
                    add(a["href"], "colombia-evidence")
    elif kind == "colombia-agronet-cacao":
        for a in soup.select("a[href]"):
            target = urljoin(url, a["href"])
            if "precio-de-referencia-semanal-de-compra-de-cacao" in target:
                add(target, kind)
    found.discard((url, kind))
    return sorted(found)


def colombian_number(value, *, cacao=False):
    value = clean(value).replace("$", "").replace("/kg", "").replace(" ", "")
    if value in {"", "-", "N/R", "N.D.", "ND"}:
        return None
    if cacao and re.fullmatch(r"\d{1,3}\.\d{3}\.\d{2}", value):
        # The AgroNET historical table uses 33.968.30 in place of 33.968,30.
        integer, decimal = value.rsplit(".", 1)
        value = integer.replace(".", "") + "." + decimal
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", value):
        value = value.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+(?:,\d{1,2})?", value):
        value = value.replace(",", ".")
    else:
        raise ValueError("Ambiguous publisher number: " + value)
    number = Decimal(value)
    if number <= 0:
        raise ValueError("Nonpositive source price")
    return float(number)


def _row(
    name,
    publisher,
    series,
    basis,
    unit,
    market,
    day,
    value,
    locator,
    *,
    start=None,
    **details,
):
    return {
        "product_id": slug(name),
        "product_name": name,
        "category": details.pop("category", "Referencias oficiales de Colombia"),
        "publisher": publisher,
        "series": series,
        "basis": basis,
        "currency": "COP",
        "unit": unit,
        "market": market,
        "date": day.isoformat(),
        "period_start": (start or day).isoformat(),
        "price": value,
        "source_locator": locator,
        "identity_dimensions": {
            key: details[key]
            for key in (
                "presentation",
                "quantity",
                "published_unit",
                "quality",
                "statistic",
            )
            if details.get(key) is not None
        },
        "details": {"parser_version": VERSION, **details},
    }


def weekly_period(value):
    """Read explicit Spanish ranges, including dates crossing months or years."""
    value = clean(value).lower()
    sides = re.split(r"\s+al\s+", value)
    if len(sides) != 2:
        raise ValueError("Unknown weekly date: " + value)
    start, end = sides
    m = re.fullmatch(r"(\d{1,2})\s+(?:de\s+)?([a-z]+)\s+(?:de\s+)?(\d{4})", end)
    if not m or m[2] not in MONTHS:
        raise ValueError("Unknown weekly ending: " + end)
    last = date(int(m[3]), MONTHS[m[2]], int(m[1]))
    m = re.fullmatch(
        r"(\d{1,2})(?:\s+(?:de\s+)?([a-z]+))?(?:\s+(?:de\s+)?(\d{4}))?", start
    )
    if not m:
        raise ValueError("Unknown weekly starting: " + start)
    month = MONTHS[m[2]] if m[2] else last.month - (int(m[1]) > last.day)
    year = int(m[3]) if m[3] else last.year
    if month == 0:
        month, year = 12, year - 1
    elif not m[3] and month > last.month:
        year -= 1
    first = date(year, month, int(m[1]))
    if not 0 <= (last - first).days <= 8:
        raise ValueError("Invalid source weekly span: " + value)
    return first, last


def parse_cacao(body):
    soup = _soup(body)
    tables = [
        t
        for t in soup.select("table")
        if "Precio" in clean(t.get_text()) and "/kg" in clean(t.get_text())
    ]
    if len(tables) != 1:
        raise ValueError("AgroNET cacao table missing or ambiguous")
    output = []
    for n, tr in enumerate(tables[0].select("tr"), 1):
        cells = [clean(x.get_text()) for x in tr.select("td")]
        if len(cells) != 2 or "$" not in cells[1]:
            continue
        start, end = weekly_period(cells[0])
        issue = None
        try:
            value = colombian_number(cells[1], cacao=True)
            # One published $22.421.720 row is ambiguous between a typo and decimal.
            if value is not None and value > 100000:
                raise ValueError("Cacao source number has ambiguous decimal/grouping")
        except ValueError as error:
            value, issue = None, str(error)
        output.append(
            _row(
                "Cacao en grano",
                "UPRA / AgroNET",
                "agronet-cacao-weekly",
                "Referencia semanal de compra: industria nacional y exportadores",
                "kg",
                "Colombia",
                start,
                value,
                f"HTML table 1, row {n}",
                start=start,
                category="Cacao",
                period_end=end.isoformat(),
                period_type="semana de referencia",
                original_period=cells[0],
                original_price=cells[1],
                quality_issue=issue,
                source_note="Indicador de referencia; no oferta individual ni precio garantizado",
            )
        )
    if not output:
        raise ValueError("No cacao prices extracted")
    return output


def parse_palm(body, url):
    soup = _soup(body)
    table = next(
        (t for t in soup.select("table") if "Aceite de palma crudo" in t.get_text()),
        None,
    )
    if table is None:
        raise ValueError("Fedepalma FFP price table missing")
    output = []
    for n, tr in enumerate(table.select("tr"), 1):
        cells = [clean(c.get_text(" ")) for c in tr.select("td")]
        if len(cells) < 3:
            continue
        period = re.fullmatch(
            r"(Primer|Segundo) semestre(?: de)? (\d{4})", cells[0], re.IGNORECASE
        )
        if not period:
            continue
        start = date(int(period[2]), 1 if period[1].lower() == "primer" else 7, 1)
        end = date(start.year, 6, 30) if start.month == 1 else date(start.year, 12, 31)
        for column, name in [(1, "Aceite de palma crudo"), (2, "Palmiste")]:
            value = colombian_number(cells[column])
            if value is None:
                continue  # The publisher's separate explanatory-note row has no quote.
            links = [urljoin(url, a["href"]) for a in tr.select("a[href]")]
            output.append(
                _row(
                    name,
                    "MADR / Fedepalma FFP",
                    "fedepalma-ffp-semiannual",
                    "Referencia regulatoria para liquidar la cuota de fomento palmero",
                    "kg",
                    "Colombia",
                    start,
                    value,
                    f"HTML FFP table, row {n}, column {column + 1}",
                    start=start,
                    category="Palma y aceites",
                    period_end=end.isoformat(),
                    period_type="semestre",
                    resolution=cells[3] if len(cells) > 3 else None,
                    resolution_urls=links,
                    source_note="Precio fijado por MADR para contribución parafiscal; no cotización de compraventa",
                )
            )
    if not output:
        raise ValueError("No FFP reference prices extracted")
    return output


FEDEGAN = {
    "56": ("046", "Leche cruda", "litro", "Precio pagado al productor, USP / MADR"),
    "63": (
        "053",
        "Ganado gordo en pie",
        "kg en pie",
        "Promedio indicativo nacional de subastas",
    ),
    "67": (
        "057",
        "Ganado gordo en pie",
        "kg en pie",
        "Transacciones de facturas registradas en la BMC",
    ),
    "74": (
        "064",
        "Ganado flaco en pie · machos",
        "kg en pie",
        "Promedio indicativo regional de subastas",
    ),
    "75": (
        "065",
        "Ganado flaco en pie · hembras",
        "kg en pie",
        "Promedio indicativo regional de subastas",
    ),
    "81": (
        "071",
        "Ganado gordo en pie · macho ceba",
        "kg en pie",
        "Promedio indicativo regional de subastas",
    ),
}


def _fedegan_date(text):
    m = re.fullmatch(r"([a-z]{3})/(\d{4})", text.lower())
    if m:
        y, mo = int(m[2]), MONTHS[m[1]]
        return date(y, mo, calendar.monthrange(y, mo)[1]), date(y, mo, 1), "mensual"
    m = re.fullmatch(r"\w+, ([a-z]{3}) (\d{1,2}), '(\d{2})", text.lower())
    if m:
        d = date(2000 + int(m[3]), MONTHS[m[1]], int(m[2]))
        return d, d, "semanal"
    raise ValueError("Unknown Fedegán date: " + text)


def parse_fedegan(body, url):
    indicator = parse_qs(urlparse(url).query).get("pId", [None])[0]
    if indicator not in FEDEGAN:
        raise ValueError("Unregistered Fedegán price indicator")
    code, name, unit, basis = FEDEGAN[indicator]
    lines = list(csv.reader(io.StringIO(body.decode("latin1")), delimiter=";"))
    if not lines or not clean(lines[0][0]).startswith(code + "-"):
        raise ValueError("Fedegán indicator identity mismatch")
    headers = [clean(v) for v in lines[1]]
    while headers and not headers[-1]:
        headers.pop()
    if "Fecha" not in headers:
        raise ValueError("Fedegán date column missing")
    date_col = headers.index("Fecha")
    output = []
    for n, line in enumerate(lines[2:], 3):
        cells = [clean(v) for v in line]
        while cells and not cells[-1]:
            cells.pop()
        if not cells:
            continue
        if len(cells) != len(headers):
            raise ValueError(f"Fedegán row {n} has unexpected column count")
        day, start, frequency = _fedegan_date(cells[date_col])
        for col in range(date_col + 1, len(headers)):
            issue = None
            try:
                value = colombian_number(cells[col])
            except ValueError as error:
                value, issue = None, str(error)
            if value is None and not issue:
                continue
            label = cells[0] if date_col == 1 else headers[col]
            market = label if indicator in {"67", "74", "75", "81"} else "Colombia"
            row_basis, suffix = basis, ""
            method = "promedio"
            if indicator in {"74", "75"} and day >= date(2026, 8, 1):
                method = (
                    "transición de promedio a máximo"
                    if start == date(2026, 8, 1)
                    else "máximo reportado"
                )
                suffix = (
                    "-transition-202608" if start == date(2026, 8, 1) else "-maximum"
                )
                row_basis = "Subastas: " + method + " (cambio el 14 de agosto de 2026)"
            if indicator == "56":
                row_basis += " · " + label
                suffix = (
                    "-without-bonus"
                    if "sin bonificaciones" in label.lower()
                    else "-with-bonus"
                )
            output.append(
                _row(
                    name,
                    "Fedegán / FNG",
                    f"fedegan-{indicator}{suffix}",
                    row_basis,
                    unit,
                    market,
                    day,
                    value,
                    f"CSV row {n}, column {col + 1}",
                    start=start,
                    category="Leche" if indicator == "56" else "Ganado bovino",
                    indicator=code,
                    period_type=frequency,
                    original_date=cells[date_col],
                    header=label,
                    quality_issue=issue,
                    original_price=cells[col],
                    statistic=method,
                    methodology_change="2026-08-14"
                    if indicator in {"74", "75"}
                    else None,
                    methodology_url=FEDEGAN_PRICES,
                    source_note="Valores indicativos de la fuente; kg de animal vivo"
                    if unit == "kg en pie"
                    else "Fuente original: USP / MADR",
                )
            )
    if not output:
        raise ValueError("No Fedegán prices extracted")
    return output


def _pdf_lines(page, bbox=None, *, upright_only=False):
    """Coordinate-aligned native text; keeps nearby charts outside table crops."""
    words = (page.crop(bbox) if bbox else page).extract_words(
        x_tolerance=2, y_tolerance=2
    )
    if upright_only:
        words = [w for w in words if w.get("upright", True)]
    grouped = []
    for w in sorted(words, key=lambda x: (x["top"], x["x0"])):
        row = next((r for r in grouped[-3:] if abs(r[0] - w["top"]) < 3), None)
        if row is None:
            row = [w["top"], []]
            grouped.append(row)
        row[1].append(w)
    return [
        (
            y,
            sorted(ws, key=lambda w: w["x0"]),
            " ".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"])),
        )
        for y, ws in grouped
    ]


def _pdf_date(page):
    return _pdf_date_text(page.extract_text())


def _pdf_date_text(text):
    text = clean(text)
    m = re.search(
        r"\b(\d{1,2}) de (" + "|".join(MONTHS) + r") (?:de )?(\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if m:
        return date(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
    m = re.search(
        r"\b(" + "|".join(MONTHS) + r") (\d{1,2}) de (\d{4})\b", text, re.IGNORECASE
    )
    if m:
        return date(int(m[3]), MONTHS[m[1].lower()], int(m[2]))
    raise ValueError("PDF has no explicit observation date")


def _corabastos_category(name):
    name = slug(name)
    for pattern, category in (
        (r"^(banano|platano)", "Banano y plátano"),
        (r"^(azucar|panela)", "Azúcar y panela"),
        (r"^cafe", "Café"),
        (r"^coco(?:-|$)", "Coco y aceites"),
        (
            r"pollo|pechuga|pernil|menudencia|^(cadera|chatas|costilla|lomo|pierna|sobrebarriga)$",
            "Carnes",
        ),
        (r"^(aceite|manteca|margarina)", "Aceites y grasas"),
        (r"^(leche|queso|cuajada)", "Lácteos"),
        (r"^huevo", "Huevos"),
    ):
        if re.search(pattern, name):
            return category
    return "Productos de Corabastos"


def _corabastos_legacy(page):
    """Older bulletins have native text but no table grid: use printed columns."""
    lines = _pdf_lines(page, upright_only=True)
    headers = []
    for y, ws, text in lines:
        if "Nombre" not in text or "Presentación" not in text:
            continue
        ws = list(ws)
        nearby = [w for yy, words, _ in lines if abs(yy - y) < 13 for w in words]
        for label in ("Cantidad", "Unidad"):
            if any(w["text"] == label for w in ws):
                continue
            split = next(
                (
                    w
                    for w in nearby
                    if w["text"] == label[:-1]
                    and any(
                        v["text"] == label[-1] and abs(v["x0"] - w["x0"]) < 7
                        for v in nearby
                    )
                ),
                None,
            )
            if split:
                ws.append({**split, "text": label})
                text += " " + label
        if all(any(w["text"] == label for w in ws) for label in ("Cantidad", "Unidad")):
            headers.append((y, ws, text))
    for hindex, (top, words, title) in enumerate(headers):
        if not ("Extra" in title or "Desde" in title):
            continue
        bottom = headers[hindex + 1][0] if hindex + 1 < len(headers) else page.height
        col_x = [
            next(w["x0"] for w in words if w["text"] == name)
            for name in ("Nombre", "Presentación", "Cantidad", "Unidad")
        ]
        boundaries = [
            max(0, col_x[0] - 2),
            col_x[1] - 3,
            col_x[2] - 3,
            col_x[3] - 3,
            (col_x[3] + page.width * 0.6) / 2,
        ]
        body_words = [
            w
            for w in page.extract_words(x_tolerance=2, y_tolerance=2)
            if w.get("upright", True) and top + 10 < w["top"] < bottom
        ]
        money_rows = []
        for y, ws, _ in lines:
            prices = [
                w
                for w in ws
                if w["x0"] > boundaries[-1]
                and re.fullmatch(r"\$?\d+(?:\.\d{3})*", w["text"])
            ]
            if top + 10 < y < bottom and len(prices) == 3:
                money_rows.append((y, prices))
        parsed, misaligned = [], False
        for i, (y, prices) in enumerate(money_rows):
            low = (money_rows[i - 1][0] + y) / 2 if i else top + 10
            high = (money_rows[i + 1][0] + y) / 2 if i + 1 < len(money_rows) else y + 12
            cells = []
            for left, right in pairwise(boundaries):
                selected = [
                    w
                    for w in body_words
                    if left <= w["x0"] < right and low <= w["top"] < high
                ]
                # Text baselines can be displaced by a point relative to price glyphs.
                selected.sort(key=lambda w: (round(w["top"] / 3), w["x0"]))
                cells.append(clean(" ".join(w["text"] for w in selected)))
            if not any(cells):
                # Some publisher PDFs visibly repeat orphan price glyphs below
                # the dairy table. Retain these as review evidence, never assign
                # them to the preceding product or the following egg table.
                parsed.append(
                    (
                        y,
                        ["Producto sin identificar", "", "0", ""]
                        + [w["text"] for w in prices],
                        "unidentified",
                    )
                )
                continue
            if not cells[0] or not re.fullmatch(r"\d+(?:[.,]\d+)?", cells[2]):
                misaligned = True
                cells = [
                    cells[0] or "Producto sin identificar",
                    cells[1],
                    "0",
                    cells[3],
                ]
            if cells[1].replace(" ", "") == "KILO":
                cells[1] = "KILO"
            parsed.append(
                (
                    y,
                    cells + [w["text"] for w in prices],
                    "range" if "Desde" in title else "quality",
                )
            )
        for y, cells, semantics in parsed:
            yield y, cells, "unidentified" if misaligned else semantics


def _corabastos_quote_rows(
    cells, day, locator, page_no, *, legacy=False, semantics="quality"
):
    name, presentation, quantity, published_unit = cells[:4]
    if not re.fullmatch(r"\d+(?:[.,]\d+)?", quantity):
        raise ValueError("Corabastos nonnumeric presentation quantity")

    def number(value):
        separator = r"\." if legacy else ","
        pattern = (
            r"\$?\d+(?:\.\d{3})*"
            if legacy
            else r"\$\d{1,3}(?:" + separator + r"\d{3})*"
        )
        if not re.fullmatch(pattern, value):
            raise ValueError("Unexpected Corabastos currency format")
        return float(value.removeprefix("$").replace(",", "").replace(".", ""))

    extra, first, per_unit = map(number, cells[4:7])
    for column, quality, price in [
        (1, "desde" if semantics == "range" else "extra", extra),
        (2, "hasta" if semantics == "range" else "primera", first),
    ]:
        issue = None
        if semantics == "unidentified":
            issue = "Publisher table has unlabelled price rows; product alignment requires review"
            price = None
        elif price <= 0:
            issue = "Publisher zero price; no positive quote available"
            price = None
        elif semantics == "range" and extra > first:
            issue = "Publisher range Desde exceeds Hasta"
        yield _row(
            name.title(),
            "Corabastos S.A.",
            "corabastos-" + semantics + "-" + quality,
            "Precio en bodega · "
            + (quality if semantics == "range" else "calidad " + quality),
            f"{presentation} · cantidad {quantity} · {published_unit}",
            "Bogotá · Corabastos",
            day,
            price,
            locator + f"; price column {column}",
            category=_corabastos_category(name),
            presentation=presentation,
            quantity=float(quantity.replace(",", ".")),
            published_unit=published_unit,
            quality=quality,
            unit_price_as_published=per_unit,
            original_price=cells[3 + column],
            variation_label=cells[7] if len(cells) > 7 else None,
            source_page=page_no,
            original_product=name,
            quality_issue=issue,
            source_note="Cantidad/unidad literales del original. No se asume que cajas o bultos equivalgan a kg. Las columnas de calidad o Desde/Hasta permanecen separadas.",
        )


def _corabastos_unruled(page):
    """2025 native tables have column headings but no usable PDF grid."""
    lines = _pdf_lines(page, upright_only=True)
    header = next(
        (
            (y, ws)
            for y, ws, t in lines
            if all(
                word in t
                for word in (
                    "Nombre",
                    "Presentación",
                    "Cantidad",
                    "Unidad de medida",
                    "Variación",
                )
            )
        ),
        None,
    )
    if not header:
        return
    top, words = header

    def center(label):
        w = next(w for w in words if w["text"] == label)
        return (w["x0"] + w["x1"]) / 2

    unit_left = next(w["x0"] for w in words if w["text"] == "Unidad")
    boundaries = [
        0,
        (center("Nombre") + center("Presentación")) / 2,
        (center("Presentación") + center("Cantidad")) / 2,
        unit_left - 5,
        next(w["x0"] for w in words if w["text"] == "Precio") - 5,
    ]
    price_rows = [
        (y, ws)
        for y, ws, _ in lines
        if y > top + 20
        and len(
            [
                w
                for w in ws
                if w["x0"] > boundaries[-1]
                and re.fullmatch(r"\$\d{1,3}(?:,\d{3})*", w["text"])
            ]
        )
        == 3
    ]
    all_words = page.extract_words(x_tolerance=2, y_tolerance=2)
    parsed = []
    for i, (y, words) in enumerate(price_rows):
        low = (price_rows[i - 1][0] + y) / 2 if i else top + 20
        high = (price_rows[i + 1][0] + y) / 2 if i + 1 < len(price_rows) else y + 10
        selected = [
            w
            for w in all_words
            if w.get("upright", True) and low - 0.8 <= w["top"] < high - 0.8
        ]
        selected.sort(key=lambda w: (round(w["top"] / 3), w["x0"]))
        cells = [
            clean(" ".join(w["text"] for w in selected if left <= w["x0"] < right))
            for left, right in pairwise(boundaries)
        ]
        prices = [
            w
            for w in words
            if w["x0"] > boundaries[-1]
            and re.fullmatch(r"\$\d{1,3}(?:,\d{3})*", w["text"])
        ]
        if not re.fullmatch(r"\d+(?:[.,]\d+)?", cells[2]):
            raise ValueError("Corabastos unruled native row has no quantity")
        variation = " ".join(w["text"] for w in words if w["x0"] > prices[-1]["x1"])
        parsed.append((y, [*cells, *[w["text"] for w in prices], variation]))
    incomplete = any(not cells[0] for _, cells in parsed)
    for y, cells in parsed:
        if not cells[0]:
            cells[0] = "Producto sin identificar"
        yield y, cells, "unidentified" if incomplete else "quality"


def _corabastos_printed(pdf, day):
    """Spreadsheet print exports repeat explicit columns across page breaks."""
    output, boundaries, semantics = [], None, None
    for page_no, page in enumerate(pdf.pages, 1):
        lines = _pdf_lines(page, upright_only=True)
        for i, (y, words, text) in enumerate(lines):
            if all(
                label in text
                for label in ("Nombre", "Presentación", "Cantidad", "Unidad")
            ):
                context = " ".join(t for yy, _, t in lines if y - 25 <= yy <= y + 15)
                if "Desde" in context and "Hasta" in context:
                    semantics = "range"
                elif "Extra" in context and "primera" in context.lower():
                    semantics = "quality"
                else:
                    boundaries = None
                    continue
                bounds = [0]
                for label, margin in (
                    ("Presentación", 10),
                    ("Cantidad", 3),
                    ("Unidad", 3),
                ):
                    bounds.append(
                        next(w["x0"] for w in words if w["text"] == label) - margin
                    )
                bounds.append(next(w["x1"] for w in words if w["text"] == "Unidad") + 5)
                boundaries = bounds
                continue
            if not boundaries:
                continue
            amount_text = " ".join(
                w["text"] for w in words if w["x0"] >= boundaries[-1]
            )
            amounts = re.findall(r"\$\s*\d+(?:\.\d{3})*", amount_text)
            if len(amounts) != 3:
                continue
            cells = [
                clean(" ".join(w["text"] for w in words if left <= w["x0"] < right))
                for left, right in pairwise(boundaries)
            ]
            if not cells[0] or not re.fullmatch(r"\d+(?:[.,]\d+)?", cells[2]):
                raise ValueError(
                    "Corabastos printed native row has no product or quantity"
                )
            cells.extend(value.replace(" ", "") for value in amounts)
            output.extend(
                _corabastos_quote_rows(
                    cells,
                    day,
                    f"PDF page {page_no}, printed table y {y:.1f}",
                    page_no,
                    legacy=True,
                    semantics=semantics,
                )
            )
    return output


def parse_corabastos(body, url):
    import pdfplumber

    output, seen = [], set()
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        day = _pdf_date(pdf.pages[0])
        stamp = re.search(r"(20\d{6})\.pdf$", url, re.IGNORECASE)
        if stamp and day.strftime("%Y%m%d") != stamp[1]:
            raise ValueError("Corabastos PDF date differs from linked filename")
        for page_no, page in enumerate(pdf.pages, 1):
            for table_no, table in enumerate(page.extract_tables(), 1):
                header = " ".join(clean(v) for row in table[:3] for v in row if v)
                if not all(
                    v in header.lower()
                    for v in ["nombre", "presentaci", "cantidad", "precio"]
                ):
                    continue
                for row_no, raw in enumerate(table, 1):
                    cells = [clean(v) for v in raw if clean(v)]
                    if len(cells) != 8 or not all(
                        v.startswith("$") for v in cells[4:7]
                    ):
                        continue
                    identity = tuple(cells[:4])
                    if identity in seen:
                        continue
                    seen.add(identity)
                    output.extend(
                        _corabastos_quote_rows(
                            cells,
                            day,
                            f"PDF page {page_no}, table {table_no}, row {row_no}",
                            page_no,
                        )
                    )
            for y, cells, semantics in _corabastos_unruled(page):
                identity = tuple(cells[:4]) + (
                    (page_no, y) if semantics == "unidentified" else ()
                )
                if identity in seen:
                    continue
                seen.add(identity)
                output.extend(
                    _corabastos_quote_rows(
                        cells,
                        day,
                        f"PDF page {page_no}, native table y {y:.1f}",
                        page_no,
                        semantics=semantics,
                    )
                )
            # Only invoke the geometric native-text reader on the older header layout.
            if "$ Cal. Extra" in (page.extract_text() or "") or "$ Desde" in (
                page.extract_text() or ""
            ):
                for y, cells, semantics in _corabastos_legacy(page):
                    identity = tuple(cells[:4]) + (
                        (page_no, y) if semantics == "unidentified" else ()
                    )
                    if identity in seen:
                        continue
                    seen.add(identity)
                    output.extend(
                        _corabastos_quote_rows(
                            cells,
                            day,
                            f"PDF page {page_no}, y {y:.1f}",
                            page_no,
                            legacy=True,
                            semantics=semantics,
                        )
                    )
        if not output:
            output.extend(_corabastos_printed(pdf, day))
    if not output:
        raise ValueError(
            "No known Corabastos price table extracted; preserve PDF for review"
        )
    # A print export can contain two different prices for the same product and
    # package on the same date. Preserve both and require review; never choose
    # whichever duplicate happened to be printed first.
    groups = {}
    for row in output:
        key = (row["product_id"], row["series"], row["unit"], row["date"])
        group = groups.setdefault(key, [])
        if any(prior["price"] != row["price"] for prior in group):
            row["details"]["quality_issue"] = (
                "Publisher repeats the same product/package with different prices"
            )
            for prior in group:
                prior["details"]["quality_issue"] = row["details"]["quality_issue"]
        group.append(row)
    return output


PORK_NAMES = ["Cerdo en pie", "Cerdo · canal caliente", "Cerdo · canal fría"]
PORK_MARKETS = [
    "Antioquia",
    "Eje Cafetero",
    "Valle del Cauca",
    "Caribe Norte",
    "Bogotá",
    "Tolima - Huila",
    "Colombia",
]
PORK_NUMBER = r"(?:\d{1,3}(?:[.,]\d{3})*(?:,\d{1,2})?|-)"
PORK_REGION = r"(?:Antioquia|Eje Cafetero|Valle del Cauca|Caribe Norte|Bogot[aá]|Tolima\s*-\s*Huila|Promedio(?: nacional)?)"


def _word_spans(words, label):
    """Locate a literal header even when PDF text exposes one letter per word."""
    joined = "".join(w["text"] for w in words)
    starts, offset = [], 0
    for w in words:
        starts.append((offset, offset + len(w["text"]), w))
        offset += len(w["text"])
    for match in re.finditer(re.escape(label), joined):
        selected = [w for a, b, w in starts if a < match.end() and b > match.start()]
        yield min(w["x0"] for w in selected), max(w["x1"] for w in selected)


def _pork_legacy_monthly(page, page_no, report_day):
    """Recover letter-spaced native PDF tables without OCR or invented cells."""
    lines = _pdf_lines(page)
    for index, (top, _, title) in enumerate(lines):
        product = next(
            (
                i
                for i, phrase in [
                    (0, "cerdo en pie promedio mensual"),
                    (1, "canal caliente promedio mensual"),
                    (2, "canal fría promedio mensual"),
                ]
                if title.lower().startswith(phrase)
            ),
            None,
        )
        if product is None:
            continue
        following = lines[index + 1 :]
        header = "".join(t.replace(" ", "").lower() for _, _, t in following[:5])
        if "tolima" in header or "período" not in header:
            continue  # The newer layout is parsed by its native columns separately.
        if not all(x in header for x in ("valle", "caribe", "promedio")):
            continue
        markets = (
            PORK_MARKETS[:5] + ["Colombia"]
            if "antioquia" in header
            else ["Valle del Cauca", "Caribe Norte", "Colombia"]
        )
        labels = {
            "Antioquia": "Antioquia",
            "Eje Cafetero": "Eje",
            "Valle del Cauca": "Valle",
            "Caribe Norte": "Caribe",
            "Bogotá": "Bogotá",
            "Colombia": "Promedio",
        }
        centers = []
        for label in ["Período", *[labels[m] for m in markets]]:
            spans = [
                span for _, ws, _ in following[:5] for span in _word_spans(ws, label)
            ]
            if not spans:
                raise ValueError(
                    "Monthly pork table has no explicit market column: " + label
                )
            left, right = min(spans)
            centers.append((left + right) / 2)
        if centers != sorted(centers):
            raise ValueError("Monthly pork market columns are out of order")
        boundaries = [max(0, centers[0] - (centers[1] - centers[0]) / 2)]
        boundaries += [(a + b) / 2 for a, b in pairwise(centers)]
        boundaries += [centers[-1] + (centers[-1] - centers[-2]) / 2]
        # Graph ticks and legends share the same y coordinates. Only the
        # explicitly headed table columns define price cells.
        following = _pdf_lines(
            page, (boundaries[0], top + 12, boundaries[-1], page.height)
        )
        if product != 1 and not all(
            x in header for x in ("antioquia", "bogotá", "cafetero")
        ):
            continue
        last_period = None
        for y, row_words, text in following:
            compact = text.replace(" ", "")
            if (
                compact.lower().startswith("fuente:")
                or "promediomensual" in compact.lower()
            ):
                break
            match = re.fullmatch(
                r"([A-Za-z]{3}-\d{2}|\d{1,2}-[A-Za-z]{3}-\d{2})(.*)", compact
            )
            if not match:
                continue
            cells = [
                "".join(
                    w["text"]
                    for w in row_words
                    if left <= (w["x0"] + w["x1"]) / 2 < right
                )
                for left, right in pairwise(boundaries)
            ]
            if cells[0] != match[1]:
                raise ValueError("Monthly pork period crosses a column boundary")
            tokens = cells[1:]
            if any(
                token and not re.fullmatch(r"\d{1,2}[.,]\d{3}|-", token)
                for token in tokens
            ):
                raise ValueError("Letter-spaced native monthly pork row is incomplete")
            parts = match[1].lower().split("-")
            if len(parts) == 2:
                year, month = 2000 + int(parts[1]), MONTHS[parts[0]]
                start = date(year, month, 1)
                day = date(year, month, calendar.monthrange(year, month)[1])
                frequency = "mensual"
            else:
                day = date(2000 + int(parts[2]), MONTHS[parts[1]], int(parts[0]))
                start, frequency = day, "semanal"
            issue = None
            if last_period and day <= last_period:
                issue = (
                    "Publisher monthly period is out of sequence; date requires review"
                )
            if day > report_day:
                issue = "Publisher period is later than report date"
            last_period = max(day, last_period or day)
            for market, token in zip(markets, tokens):
                value = _pork_ocr_number(token)
                if value is None:
                    continue
                yield _row(
                    PORK_NAMES[product],
                    "Porkcolombia / FNP",
                    "porkcolombia-monthly"
                    if frequency == "mensual"
                    else "porkcolombia-current",
                    "Promedio mensual pagado al porcicultor · encuesta"
                    if frequency == "mensual"
                    else "Promedio ponderado pagado al porcicultor · encuesta",
                    "kg en pie" if product == 0 else "kg canal",
                    market,
                    day,
                    value,
                    f"PDF page {page_no}, native monthly table {PORK_NAMES[product]}, y {y:.1f}, market {market}",
                    start=start,
                    category="Porcinos",
                    source_page=page_no,
                    original_period=match[1],
                    period_type=frequency,
                    quality_issue=issue,
                )


def _pork_native_matrix(page, page_no, report_day):
    """Older survey pages put regions across columns and products down rows."""
    lines = _pdf_lines(page)
    output = []
    sections = [
        (i, _pork_heading(text))
        for i, (_, _, text) in enumerate(lines)
        if _pork_heading(text) in (0, 1, 2)
        and ("CORRIENTE" in text or text.startswith("Precio en "))
    ]
    for index, product in sections:
        top = lines[index][0]
        history = "CORRIENTE" in lines[index][2]
        header_lines = (
            lines[index + 1 : index + 7]
            if history
            else [line for line in lines[:index] if top - 70 < line[0] < top]
        )
        centers = []
        for label in ("Antioquia", "Eje", "Valle", "Caribe", "Bogotá", "Promedio"):
            spans = [
                span for _, ws, _ in header_lines for span in _word_spans(ws, label)
            ]
            if not spans:
                # Current matrices share one header above all three products.
                spans = [
                    span
                    for _, ws, _ in lines[: sections[0][0]]
                    for span in _word_spans(ws, label)
                ]
            if not spans:
                raise ValueError("Native pork matrix lacks market header " + label)
            a, b = min(spans)
            centers.append((a + b) / 2)
        bounds = [centers[0] - (centers[1] - centers[0]) / 2]
        bounds += [(a + b) / 2 for a, b in pairwise(centers)]
        bounds += [min(page.width, b + 12)]
        end = (
            next((lines[i][0] for i, _ in sections if i > index), page.height)
            if history
            else next(
                (
                    y
                    for y, _, text in lines[index + 1 :]
                    if _pork_heading(text) is not None
                ),
                page.height,
            )
        )
        for y, words, text in _pdf_lines(page, (0, top + 10, bounds[-1], end)):
            label = clean(
                " ".join(
                    w["text"] for w in words if (w["x0"] + w["x1"]) / 2 < bounds[0]
                )
            ).lower()
            stamp = re.search(r"\b(\d{1,2})-([a-z]{3})-(\d{2})\b", label)
            if label == "semana actual" and not history:
                day, start, frequency = report_day, report_day, "semanal"
            elif history and label in MONTHS and len(label) > 3:
                mo = MONTHS[label]
                start = date(report_day.year, mo, 1)
                day = date(
                    report_day.year, mo, calendar.monthrange(report_day.year, mo)[1]
                )
                frequency = "mensual"
            elif history and stamp:
                day = date(2000 + int(stamp[3]), MONTHS[stamp[2]], int(stamp[1]))
                start, frequency = day, "semanal"
            else:
                continue
            vals = [
                "".join(
                    w["text"] for w in words if left <= (w["x0"] + w["x1"]) / 2 < right
                )
                for left, right in pairwise(bounds)
            ]
            for market, raw in zip(PORK_MARKETS[:5] + ["Colombia"], vals):
                value = _pork_ocr_number(raw)
                if value is None:
                    continue
                output.append(
                    _row(
                        PORK_NAMES[product],
                        "Porkcolombia / FNP",
                        "porkcolombia-monthly"
                        if frequency == "mensual"
                        else "porkcolombia-current",
                        "Promedio mensual pagado al porcicultor · encuesta"
                        if frequency == "mensual"
                        else "Promedio ponderado pagado al porcicultor · encuesta",
                        "kg en pie" if product == 0 else "kg canal",
                        market,
                        day,
                        value,
                        f"PDF page {page_no}, native matrix {PORK_NAMES[product]}, y {y:.1f}, market {market}",
                        start=start,
                        category="Porcinos",
                        source_page=page_no,
                        original_period=label,
                        period_type=frequency,
                        quality_issue="Publisher period is later than report date"
                        if day > report_day
                        else None,
                    )
                )
    return output


def parse_pork(body):
    """Read current native-text weighted survey quotes and monthly history.

    Scope is national/regional COP/kg pork, never the adjacent international feed
    quotes, animal counts, live weights or simple averages by sample third.
    """
    import pdfplumber

    output = []
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        first = pdf.pages[0]
        try:
            day = _pdf_date(first)
        except ValueError:
            if not clean(first.extract_text()) and any(
                image.get("width", 0) * image.get("height", 0)
                > first.width * first.height * 0.5
                for image in first.images
            ):
                raise NormalExtractionFailed(
                    "Scanned Porkcolombia report has no native date or price text",
                    tuple(range(1, len(pdf.pages) + 1)),
                ) from None
            if (first.extract_text() or "").count("(cid:") > 20 and len(pdf.pages) >= 3:
                # The older survey layout has the cover/date followed by the
                # current and historical price matrices. Do not guess its date
                # from a later WordPress upload path or graph labels.
                raise NormalExtractionFailed(
                    "Porkcolombia has a broken native font map; cover date and price matrices require OCR",
                    (1, 2, 3),
                ) from None
            raise
        lines = _pdf_lines(first)
        section = next(
            (
                y
                for y, _, t in lines
                if t.startswith(
                    ("PRECIOS (", "PRECIOS Pagados", "PRECIOS CORRIENTES (")
                )
            ),
            None,
        )
        if section is None:
            if len(pdf.pages) >= 3 and "INFORME DE PRECIOS CORRIENTES REPORTADOS" in (
                pdf.pages[1].extract_text() or ""
            ):
                matrix = _pork_native_matrix(pdf.pages[1], 2, day)
                if matrix:
                    matrix.extend(_pork_native_matrix(pdf.pages[2], 3, day))
                    return _pork_deduplicate(matrix)
            image_pages = []
            for pn, pg in enumerate(pdf.pages[:3], 1):
                text = pg.extract_text() or ""
                if (
                    "PRECIO" in text.upper()
                    and not re.search(r"\d{1,3}[.,]\d{3}", text)
                    and any(
                        image.get("width", 0) * image.get("height", 0)
                        > pg.width * pg.height * 0.05
                        for image in pg.images
                    )
                ):
                    image_pages.append(pn)
            if image_pages:
                raise NormalExtractionFailed(
                    "Porkcolombia price tables are images; native extraction returned headings only",
                    [p for p in image_pages if p != 1] or image_pages,
                )
            raise ValueError("Unsupported Porkcolombia current-price layout")
        header = next(
            (
                (y, ws)
                for y, ws, t in lines
                if y > section and t.replace(" ", "").count("Mercado") == 3
            ),
            None,
        )
        if not header:
            raise ValueError("Porkcolombia current-price columns missing")
        y, words = header
        anchors = [left for left, _ in _word_spans(words, "Mercado")]
        end = next(
            (yy for yy, _, text in lines if yy > y and text.startswith("Fuente:")),
            y + first.height * 0.14,
        )
        for col, name in enumerate(PORK_NAMES):
            left = max(0, anchors[col] - 15)
            right = anchors[col + 1] - 25 if col < 2 else first.width
            pending_national = False
            for yy, _, text in _pdf_lines(first, (left, y, right, end)):
                if text.replace(" ", "") == "Promedio":
                    pending_national = True
                    continue
                if pending_national and re.fullmatch(
                    rf"{PORK_NUMBER}\s+{PORK_NUMBER}(?:\s+[-\d.,]+\s*%)?", clean(text)
                ):
                    text = "Promedio " + text
                    pending_national = False
                match = re.fullmatch(
                    rf"({PORK_REGION})\s+({PORK_NUMBER})\s+({PORK_NUMBER})(?:\s+(?:[-\d.,]+\s*%|-))?",
                    clean(text),
                    re.IGNORECASE,
                )
                if not match:
                    compact = text.replace(" ", "")
                    if pending_national and re.fullmatch(
                        r"\d{1,2}[.,]\d{3}\d{1,2}[.,]\d{3}[-\d.,]+%", compact
                    ):
                        compact = "Promedio" + compact
                        pending_national = False
                    match = re.fullmatch(
                        rf"({PORK_REGION.replace(' ', '')})(\d{{1,2}}[.,]\d{{3}})(\d{{1,2}}[.,]\d{{3}})(?:[-\d.,]+%|-)?",
                        compact,
                        re.IGNORECASE,
                    )
                if not match:
                    compact = text.replace(" ", "")
                    raw_market = next(
                        (
                            m
                            for m in PORK_MARKETS
                            if compact.lower().startswith(m.replace(" ", "").lower())
                        ),
                        None,
                    )
                    if compact.startswith("Promedio") or (
                        pending_national and re.search(r"\d", compact)
                    ):
                        raw_market = "Colombia"
                        pending_national = False
                    if raw_market and re.search(r"\d", compact):
                        output.append(
                            _row(
                                name,
                                "Porkcolombia / FNP",
                                "porkcolombia-current",
                                "Promedio ponderado pagado al porcicultor · encuesta",
                                "kg en pie" if col == 0 else "kg canal",
                                raw_market,
                                day,
                                None,
                                f"PDF page 1, current prices column {col + 1}, y {yy:.1f}",
                                category="Porcinos",
                                source_page=1,
                                quality_issue="Publisher current row has overlapping or unsupported numeric text",
                                original_price=text,
                            )
                        )
                    continue
                market = match[1]
                market = (
                    "Colombia"
                    if market.startswith("Promedio")
                    else next(
                        (
                            m
                            for m in PORK_MARKETS
                            if slug(m).replace("-", "") == slug(market).replace("-", "")
                        ),
                        market.replace("Bogota", "Bogotá"),
                    )
                )
                zero_price = bool(re.fullmatch(r"0+(?:[.,]0+)?", match[3]))
                value = None if zero_price else _pork_native_number(match[3])
                if value is None and not zero_price:
                    continue
                output.append(
                    _row(
                        name,
                        "Porkcolombia / FNP",
                        "porkcolombia-current",
                        "Promedio ponderado pagado al porcicultor · encuesta",
                        "kg en pie" if col == 0 else "kg canal",
                        market,
                        day,
                        value,
                        f"PDF page 1, current prices column {col + 1}, y {yy:.1f}",
                        category="Porcinos",
                        source_page=1,
                        period_type="quincenal"
                        if "Quincena" in first.extract_text()
                        else "semanal",
                        previous_price=None
                        if re.fullmatch(r"0+(?:[.,]0+)?", match[2])
                        else _pork_native_number(match[2]),
                        quality_issue="Publisher zero price; no positive quote available"
                        if zero_price
                        else None,
                        original_price=match[3],
                        source_note="Promedio ponderado de la muestra; no oferta individual ni garantía de precio",
                    )
                )
        # Historical tables are selected by their explicit title and period header.
        for page_no, page in enumerate(pdf.pages[1:], 2):
            output.extend(_pork_legacy_monthly(page, page_no, day))
            lines = _pdf_lines(page)
            for index, (top, _, title) in enumerate(lines):
                lowered = title.lower()
                name_index = next(
                    (
                        i
                        for i, phrase in [
                            (0, "cerdo en pie promedio mensual"),
                            (1, "canal caliente promedio mensual"),
                            (2, "canal fría promedio mensual"),
                        ]
                        if lowered.startswith(phrase)
                    ),
                    None,
                )
                if name_index is None:
                    continue
                following = lines[index + 1 :]
                header = next(
                    (
                        (yy, ws, t)
                        for yy, ws, t in following[:8]
                        if "Período" in t or "Periodo" in t
                    ),
                    None,
                )
                if (
                    not header
                    or "Promedio" not in header[2]
                    or "Caribe" not in header[2]
                ):
                    continue  # Adjacent international table may reuse an incorrect heading.
                hy, hw, _ = header
                start_x = next(
                    w["x0"] for w in hw if w["text"] in {"Período", "Periodo"}
                )
                end_x = next(w["x1"] for w in hw if w["text"] == "Promedio") + 15
                bottom = next(
                    (
                        yy
                        for yy, _, t in following
                        if yy > hy and t.startswith("Fuente:")
                    ),
                    None,
                )
                if not bottom:
                    continue
                markets = (
                    PORK_MARKETS
                    if name_index != 1
                    else [
                        "Valle del Cauca",
                        "Caribe Norte",
                        "Tolima - Huila",
                        "Colombia",
                    ]
                )
                latest_month = None
                for yy, _, text in _pdf_lines(
                    page,
                    (max(0, start_x - 35), hy + 12, min(page.width, end_x), bottom),
                ):
                    m = re.fullmatch(
                        rf"([A-Za-z]{{3}}-\d{{2}}|\d{{1,2}}-[A-Za-z]{{3}})\s+((?:{PORK_NUMBER}\s+){{{len(markets) - 1}}}{PORK_NUMBER})",
                        clean(text),
                    )
                    if not m:
                        continue
                    stamp, vals = m[1], m[2].split()
                    issue = None
                    if stamp[:3].isalpha():
                        mo = MONTHS[stamp[:3].lower()]
                        year = 2000 + int(stamp[-2:])
                        end_day = date(year, mo, calendar.monthrange(year, mo)[1])
                        period_start = date(year, mo, 1)
                        frequency = "mensual"
                        if latest_month and end_day <= latest_month:
                            issue = "Publisher monthly period is out of sequence; date requires review"
                        latest_month = max(end_day, latest_month or end_day)
                    else:
                        dd, month = stamp.split("-")
                        mo = MONTHS[month.lower()]
                        end_day = date(day.year - (mo > day.month), mo, int(dd))
                        period_start, frequency = end_day, "quincenal"
                    if end_day > day:
                        issue = "Publisher period is later than report date"
                    for market, raw_value in zip(markets, vals):
                        zero_price = bool(re.fullmatch(r"0+(?:[.,]0+)?", raw_value))
                        value = None if zero_price else _pork_native_number(raw_value)
                        if value is None and not zero_price:
                            continue
                        output.append(
                            _row(
                                PORK_NAMES[name_index],
                                "Porkcolombia / FNP",
                                "porkcolombia-monthly"
                                if frequency == "mensual"
                                else "porkcolombia-current",
                                "Promedio mensual pagado al porcicultor · encuesta"
                                if frequency == "mensual"
                                else "Promedio ponderado pagado al porcicultor · encuesta",
                                "kg en pie" if name_index == 0 else "kg canal",
                                market,
                                end_day,
                                value,
                                f"PDF page {page_no}, {PORK_NAMES[name_index]}, y {yy:.1f}, market {market}",
                                start=period_start,
                                category="Porcinos",
                                source_page=page_no,
                                period_type=frequency,
                                original_period=stamp,
                                quality_issue="Publisher zero price; no positive quote available"
                                if zero_price
                                else issue,
                                original_price=raw_value,
                            )
                        )
    if not output:
        raise ValueError("No known Porkcolombia price tables extracted")
    return _pork_deduplicate(output)


def _pork_deduplicate(output):
    # The same current survey is also repeated on the report's historical page.
    unique = {}
    for row in output:
        key = tuple(row[k] for k in ("product_id", "series", "market", "date", "unit"))
        group = unique.setdefault(key, [])
        if any(prior["price"] != row["price"] for prior in group):
            issue = "Publisher repeats same period with different values"
            row["details"]["quality_issue"] = issue
            for prior in group:
                prior["details"]["quality_issue"] = issue
            group.append(row)
        elif not group:
            group.append(row)
    return [row for group in unique.values() for row in group]


def parse(body, url, kind):
    if not _trusted(url):
        raise ValueError("Untrusted Colombian price source")
    parsers = {
        "colombia-agronet-cacao": lambda: parse_cacao(body),
        "colombia-fedepalma-ffp": lambda: parse_palm(body, url),
        "colombia-fedegan-csv": lambda: parse_fedegan(body, url),
        "colombia-corabastos-pdf": lambda: parse_corabastos(body, url),
        "colombia-pork-pdf": lambda: parse_pork(body),
    }
    if kind in parsers:
        return parsers[kind]()
    if kind in INDEX_KINDS | {"colombia-evidence"}:
        return []
    raise ValueError("Unsupported Colombian source kind: " + kind)


def _pork_native_number(value):
    if re.fullmatch(r"\d{1,2},\d{3}", value):
        return float(value.replace(",", ""))
    return colombian_number(value)


def _pork_ocr_number(value):
    """COP/kg integer cells; the older image reports use comma thousands."""
    value = clean(value).replace("$", "").replace(" ", "")
    if value in {"", "-", "--", "N/R"}:
        return None
    if not re.fullmatch(r"\d{1,3}(?:[.,]\d{3})*|\d+", value):
        raise ValueError("Uncertain or noninteger OCR pork price: " + value)
    number = float(value.replace(",", "").replace(".", ""))
    if number <= 0:
        raise ValueError("Nonpositive OCR pork price")
    return number


def _pork_heading(value):
    value = slug(value)
    if "tercil" in value or "peso-en" in value or "numero-de-animales" in value:
        return -1
    if (
        "precio" not in value
        and "promedio-mensual" not in value
        and "kilo" not in value
    ):
        return None
    if "canal-caliente" in value:
        return 1
    if "canal-fria" in value:
        return 2
    if "en-pie" in value:
        return 0
    return None


def _pork_market(value):
    value = slug(value)
    aliases = {
        "antioquia": "Antioquia",
        "eje-cafetero": "Eje Cafetero",
        "valle-del-cauca": "Valle del Cauca",
        "valle": "Valle del Cauca",
        "caribe-norte": "Caribe Norte",
        "bogota": "Bogotá",
        "promedio-muestra": "Colombia",
        "promedio-de-la-muestra": "Colombia",
        "promedio-nacional": "Colombia",
        "nacional": "Colombia",
        "promedio": "Colombia",
        "colombia": "Colombia",
        "tolima-huila": "Tolima - Huila",
    }
    return aliases.get(value)


def _pork_vertical_ocr(table, page_no, table_no, day, reading):
    """Literal modern scanned tables: Mercado / anterior / actual columns."""
    headings = [
        _pork_heading(" ".join(row))
        for row in table
        if isinstance(row, list) and all(isinstance(v, str) for v in row)
    ]
    product_ids = {v for v in headings if v is not None and v >= 0}
    header = next(
        (
            (i, row)
            for i, row in enumerate(table)
            if isinstance(row, list)
            and any(slug(v) == "mercado" for v in row)
            and any("actual" in slug(v) for v in row)
        ),
        None,
    )
    if header is None:
        return None
    if len(product_ids) != 1:
        raise ValueError("OCR vertical market table lacks one explicit product title")
    product = next(iter(product_ids))
    hi, header = header
    market_col = next(i for i, c in enumerate(header) if slug(c) == "mercado")
    value_col = next(i for i, c in enumerate(header) if "actual" in slug(c))
    rows = []
    for rn, cells in enumerate(table[hi + 1 :], hi + 2):
        if not isinstance(cells, list) or len(cells) <= max(market_col, value_col):
            continue
        market = _pork_market(cells[market_col])
        if not market:
            continue
        value = _pork_ocr_number(cells[value_col])
        if value is None:
            continue
        rows.append(
            _row(
                PORK_NAMES[product],
                "Porkcolombia / FNP",
                "porkcolombia-current",
                "Promedio ponderado pagado al porcicultor · encuesta",
                "kg en pie" if product == 0 else "kg canal",
                market,
                day,
                value,
                f"PDF page {page_no}, OCR table {table_no}, row {rn}, column {value_col + 1}",
                category="Porcinos",
                source_page=page_no,
                extraction="ocr",
                ocr_model=reading.get("model"),
                ocr_version=reading.get("version"),
                original_period="Semana Actual",
                period_type="semanal",
            )
        )
    if not rows:
        raise ValueError("OCR vertical market table has no literal positive prices")
    return rows


def parse_with_ocr(body, url, kind, readings_by_page):
    """Use agreed literal OCR only for image tables that native extraction failed.

    ``readings_by_page`` maps 1-based original PDF page numbers to an OCR result
    dict (text, tables, review_notes, model, version). The caller must already have
    two agreeing readings for each result. Original files and both readings remain
    immutable evidence. Never accepts a generic model-estimated price.
    """
    try:
        return parse(body, url, kind)
    except NormalExtractionFailed as failure:
        if kind != "colombia-pork-pdf":
            raise
        required = failure.required_pages
    readings = {int(key): value for key, value in readings_by_page.items()}
    missing = [page for page in required if page not in readings]
    if missing:
        raise NormalExtractionFailed(
            "Required price-table OCR readings missing", missing
        )
    import pdfplumber

    with pdfplumber.open(io.BytesIO(body)) as pdf:
        try:
            day = _pdf_date(pdf.pages[0])
        except ValueError:
            if 1 not in readings:
                raise NormalExtractionFailed(
                    "OCR cover date is missing", (1,)
                ) from None
            day = _pdf_date_text(readings[1].get("text", ""))
        native_headings = {
            page: {
                _pork_heading(text)
                for text in (pdf.pages[page - 1].extract_text() or "").splitlines()
            }
            for page in required
        }
    output = []
    for page_no in required:
        reading = readings[page_no]
        if not isinstance(reading.get("tables"), list):
            raise TypeError("OCR result has no literal table array")
        # A title or an exact cross-page value match is required. A table's array
        # position cannot determine whether it reports prices, weights or counts.
        for table_no, table in enumerate(reading["tables"], 1):
            product = None
            columns = {}
            pending_heading = None
            if not isinstance(table, list):
                raise TypeError("OCR table is malformed")
            vertical = _pork_vertical_ocr(table, page_no, table_no, day, reading)
            if vertical is not None:
                output.extend(vertical)
                continue
            explicit_titles = [
                _pork_heading(" ".join(row))
                for row in table
                if isinstance(row, list) and all(isinstance(c, str) for c in row)
            ]
            if not any(title is not None and title >= 0 for title in explicit_titles):
                # OCR can place titles in the separate text field. Bind a historical
                # table to a named current-price table by ALL reported market/value
                # pairs, and require the corresponding native PDF heading as well.
                # Never assign product identity merely from table array order.
                candidate_columns = next(
                    (
                        {
                            i: _pork_market(c)
                            for i, c in enumerate(row)
                            if _pork_market(c)
                        }
                        for row in table
                        if isinstance(row, list)
                        and sum(bool(_pork_market(c)) for c in row) >= 3
                    ),
                    {},
                )
                signature = None
                if candidate_columns:
                    for raw in table:
                        if not isinstance(raw, list) or len(raw) <= max(
                            candidate_columns
                        ):
                            continue
                        explicit_current = any(
                            re.fullmatch(
                                r"0?"
                                + str(day.day)
                                + r"-"
                                + next(
                                    month
                                    for month, number in MONTHS.items()
                                    if number == day.month and len(month) == 3
                                )
                                + r"-(?:"
                                + str(day.year)
                                + "|"
                                + str(day.year)[2:]
                                + ")",
                                clean(label).lower(),
                            )
                            for label in raw[: min(candidate_columns)]
                        )
                        if explicit_current:
                            signature = {
                                market: _pork_ocr_number(raw[column])
                                for column, market in candidate_columns.items()
                            }
                            signature = {
                                k: v for k, v in signature.items() if v is not None
                            }
                            break
                if signature:
                    matches = []
                    for product_index, name in enumerate(PORK_NAMES):
                        known = {
                            row["market"]: row["price"]
                            for row in output
                            if row["product_name"] == name
                            and row["date"] == day.isoformat()
                        }
                        if (
                            known == signature
                            and product_index in native_headings[page_no]
                        ):
                            matches.append(product_index)
                    if len(matches) != 1:
                        raise ValueError(
                            "OCR historical table cannot be uniquely linked to a named current-price table"
                        )
                    product = matches[0]
                    pending_heading = product
                    columns = candidate_columns
                elif candidate_columns:
                    raise ValueError(
                        "OCR table with market columns lacks an explicit price title or a verifiable current-price row"
                    )
            for row_no, raw in enumerate(table, 1):
                if not isinstance(raw, list) or not all(
                    isinstance(c, str) for c in raw
                ):
                    raise ValueError("OCR row is not a literal cell array")
                cells = [clean(c) for c in raw]
                whole = " ".join(cells)
                header_columns = {
                    i: _pork_market(c) for i, c in enumerate(cells) if _pork_market(c)
                }
                if len(header_columns) >= 3:
                    columns = header_columns
                    if pending_heading is not None:
                        product = pending_heading
                heading = _pork_heading(whole)
                if heading is not None:
                    product = heading
                    pending_heading = heading
                    continue
                if product is None or product < 0 or not columns:
                    continue
                if max(columns) >= len(cells):
                    continue
                row_label = " ".join(cells[: min(columns)])
                period = None
                frequency = "semanal"
                if slug(row_label) == "semana-actual":
                    period, start = day, day
                else:
                    # Original historical rows may start with a round-number cell.
                    candidates = cells[: min(columns)]
                    for label in candidates:
                        label = clean(label).lower()
                        match = re.fullmatch(r"(\d{1,2})-([a-z]{3})-(\d{2,4})", label)
                        if match:
                            year = int(match[3]) + (2000 if len(match[3]) == 2 else 0)
                            period = date(year, MONTHS[match[2]], int(match[1]))
                            start = period
                            break
                        match = re.fullmatch(r"([a-z]{3})[-/](\d{2,4})", label)
                        if match:
                            year = int(match[2]) + (2000 if len(match[2]) == 2 else 0)
                            month = MONTHS[match[1]]
                            start = date(year, month, 1)
                            period = date(
                                year, month, calendar.monthrange(year, month)[1]
                            )
                            frequency = "mensual"
                            break
                        if label in MONTHS and len(label) > 3:
                            month = MONTHS[label]
                            start = date(day.year, month, 1)
                            period = date(
                                day.year, month, calendar.monthrange(day.year, month)[1]
                            )
                            frequency = "mensual"
                            break
                if period is None:
                    continue
                if period > day:
                    raise ValueError("OCR price period is later than the report date")
                for column, market in columns.items():
                    value = _pork_ocr_number(cells[column])
                    if value is None:
                        continue
                    output.append(
                        _row(
                            PORK_NAMES[product],
                            "Porkcolombia / FNP",
                            "porkcolombia-monthly"
                            if frequency == "mensual"
                            else "porkcolombia-current",
                            "Promedio mensual pagado al porcicultor · encuesta"
                            if frequency == "mensual"
                            else "Promedio ponderado pagado al porcicultor · encuesta",
                            "kg en pie" if product == 0 else "kg canal",
                            market,
                            period,
                            value,
                            f"PDF page {page_no}, OCR table {table_no}, row {row_no}, column {column + 1}",
                            start=start,
                            category="Porcinos",
                            source_page=page_no,
                            extraction="ocr",
                            ocr_model=reading.get("model"),
                            ocr_version=reading.get("version"),
                            original_period=row_label,
                            period_type=frequency,
                        )
                    )
        # A recognized image-table page cannot silently produce no price rows.
        if not any(row["details"]["source_page"] == page_no for row in output):
            text_slug = slug(reading.get("text", ""))
            if page_no == 1 and 1 in required:
                continue  # Cover date was verified; all three price bases remain required below.
            if (
                "peso-en-pie" in text_slug
                and "numero-de-animales" in text_slug
                and not any(
                    _pork_heading(" ".join(row)) in (0, 1, 2)
                    for table in reading["tables"]
                    for row in table
                    if isinstance(row, list)
                    and all(isinstance(cell, str) for cell in row)
                )
            ):
                continue  # Explicit non-price survey statistics; do not turn weights into prices.
            raise ValueError(
                f"OCR page {page_no} lacks explicit price headings and market columns"
            )
    # Cross-check duplicated current observations appearing in the historical page.
    groups = {}
    for row in output:
        key = tuple(row[k] for k in ("product_id", "series", "market", "date", "unit"))
        prior = groups.get(key)
        if prior and prior["price"] != row["price"]:
            raise ValueError("OCR current and historical tables disagree")
        if not prior:
            groups[key] = row
    current = [r for r in groups.values() if r["date"] == day.isoformat()]
    if {r["product_name"] for r in current} != set(PORK_NAMES):
        raise ValueError("OCR did not identify all three current pork price bases")
    return list(groups.values())

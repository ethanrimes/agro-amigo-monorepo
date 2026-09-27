"""DANE weekly wholesale quotations, distinct from daily and monthly prices."""

import io
import math
import re
import unicodedata
from collections import Counter
from datetime import date
from urllib.parse import unquote, urldefrag, urljoin, urlsplit

VERSION = "dane-weekly-v3"
WEEKLY = "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/mayoristas-boletin-semanal-1"
ROOTS = ((WEEKLY, "dane-weekly-index"),)
INDEX_KINDS = {"dane-weekly-index"}
PUBLISHERS = {
    kind: "DANE · SIPSA"
    for kind in ("dane-weekly-index", "dane-weekly-xlsx", "dane-weekly-pdf")
}
MONTHS = [
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
]
MONTH_NUM = {v: i for i, m in enumerate(MONTHS, 1) for v in (m, m[:3])}
MONTH_NUM["setiembre"] = 9
MONTH = "(?:" + "|".join(sorted(MONTH_NUM, key=len, reverse=True)) + ")"
NUMBER = re.compile(r"\d+(?:\.\d{3})*(?:,\d+)?")


def folded(value):
    return "".join(
        c
        for c in unicodedata.normalize("NFD", str(value))
        if not unicodedata.combining(c)
    ).lower()


def clean(value):
    return " ".join(str(value or "").replace("\xad", "").split())


class NormalExtractionFailed(ValueError):
    def __init__(self, required_pages):
        self.required_pages = tuple(sorted(set(required_pages)))
        super().__init__(
            f"Weekly native price extraction failed on pages {self.required_pages}"
        )


def _period(text):
    """Only explicit weekly ranges; neither publication days nor graph dates."""
    text = folded(text).replace("_", " ")
    prefix = re.search(
        rf"(20\d{{2}})[-–](20\d{{2}})\s*\(\s*(\d{{1,2}})\s+de\s+({MONTH})\s+al\s+(\d{{1,2}})\s+de\s+({MONTH})\s*\)",
        text,
    )
    if prefix:
        y1, y2, d1, m1, d2, m2 = prefix.groups()
        first, last = (
            date(int(y1), MONTH_NUM[m1], int(d1)),
            date(int(y2), MONTH_NUM[m2], int(d2)),
        )
        if not 1 <= (last - first).days <= 7:
            raise ValueError("Weekly printed range is not a supported weekly period")
        return first, last
    # A single printed year applies to both months of an ordinary cross-month
    # week: 2021 (27 de febrero al 5 de marzo). A December/January range needs
    # explicit two-year evidence handled above, not an inferred year change.
    year_first = re.search(
        rf"\b(20\d{{2}})\s*\(\s*(\d{{1,2}})\s+de\s+({MONTH})\s+al\s+(\d{{1,2}})\s+de\s+({MONTH})\s*\)",
        text,
    )
    if year_first:
        year, first, m1, last, m2 = year_first.groups()
        result = (
            date(int(year), MONTH_NUM[m1], int(first)),
            date(int(year), MONTH_NUM[m2], int(last)),
        )
        if not 1 <= (result[1] - result[0]).days <= 7:
            raise ValueError("Weekly printed range is not a supported weekly period")
        return result
    # Explicit years on both sides of a New Year week.
    cross = re.search(
        rf"\b(\d{{1,2}})\s*(?:de\s*)?({MONTH})\s*(?:de\s*)?(20\d{{2}})\s*(?:al|a|-)\s*(\d{{1,2}})\s*(?:de\s*)?({MONTH})\s*(?:de\s*)?(20\d{{2}})\b",
        text,
    )
    if cross:
        d1, m1, y1, d2, m2, y2 = cross.groups()
        start, end = (
            date(int(y1), MONTH_NUM[m1], int(d1)),
            date(int(y2), MONTH_NUM[m2], int(d2)),
        )
        if not 1 <= (end - start).days <= 7:
            raise ValueError("Weekly printed range is not a supported weekly period")
        return start, end
    # Modern caption: 19 al 25 de septiembre de 2026; cross-month ranges too.
    match = re.search(
        rf"\b(\d{{1,2}})\s*(?:de\s*)?({MONTH})?\s*(?:al|a|-)\s*(\d{{1,2}})\s*(?:de\s*)?({MONTH})\s*(?:de\s*)?(20\d{{2}})\b",
        text,
    )
    if match:
        first, m1, last, m2, year = match.groups()
        month2 = MONTH_NUM[m2]
        month1 = MONTH_NUM[m1] if m1 else month2
        y = int(year)
        result = (
            date(y - int(month1 > month2), month1, int(first)),
            date(y, month2, int(last)),
        )
    else:
        # Original 2012 monetary caption: 2012 (agosto 4 a 10).
        match = re.search(
            rf"\b(20\d{{2}})\s*\(\s*({MONTH})\s+(\d{{1,2}})\s*(?:a|al|-)\s*(?:({MONTH})\s*)?(\d{{1,2}})\s*\)",
            text,
        )
        if not match:
            reverse = re.search(
                rf"\b(20\d{{2}})\s*\(\s*(\d{{1,2}})\s*(?:a|al|-)\s*(\d{{1,2}})\s+de\s+({MONTH})\s*\)",
                text,
            )
            if not reverse:
                return None
            year, first, last, month = reverse.groups()
            result = (
                date(int(year), MONTH_NUM[month], int(first)),
                date(int(year), MONTH_NUM[month], int(last)),
            )
            if not 1 <= (result[1] - result[0]).days <= 7:
                raise ValueError(
                    "Weekly printed range is not a supported weekly period"
                )
            return result
        year, m1, first, m2, last = match.groups()
        month1 = MONTH_NUM[m1]
        month2 = MONTH_NUM[m2] if m2 else month1
        result = (
            date(int(year), month1, int(first)),
            date(int(year) + int(month2 < month1), month2, int(last)),
        )
    if not 1 <= (result[1] - result[0]).days <= 7:
        raise ValueError("Weekly printed range is not a supported weekly period")
    return result


def _url_period(url):
    text = folded(unquote(urlsplit(url).path.rsplit("/", 1)[-1]))
    explicit = re.search(
        rf"(\d{{1,2}})({MONTH})[_-]?(20\d{{2}})[_-]?(\d{{1,2}})({MONTH})[_-]?(20\d{{2}})",
        text,
    )
    if explicit:
        first = date(int(explicit[3]), MONTH_NUM[explicit[2]], int(explicit[1]))
        last = date(int(explicit[6]), MONTH_NUM[explicit[5]], int(explicit[4]))
    else:
        years = re.findall(r"20\d{2}", text)
        if len(years) != 1:
            return None
        pairs = re.findall(rf"(\d{{1,2}})({MONTH})", text)
        if len(pairs) == 2:
            (d1, m1), (d2, m2) = pairs
        else:
            match = re.search(
                rf"semana[_-]?(\d{{1,2}})[_-](\d{{1,2}})({MONTH})[_-](20\d{{2}})", text
            )
            if not match:
                return None
            d1, d2, m2, _ = match.groups()
            m1 = m2
        last = date(int(years[0]), MONTH_NUM[m2], int(d2))
        first = date(
            last.year - int(MONTH_NUM[m1] > last.month), MONTH_NUM[m1], int(d1)
        )
    return (first, last) if 1 <= (last - first).days <= 7 else None


def source_date(url):
    period = _url_period(url)
    return period[1] if period else None


def discover(body=None, url=None, kind=None):
    if body is None:
        return list(ROOTS)
    if kind != "dane-weekly-index":
        return []
    from bs4 import BeautifulSoup

    found = []
    for a in BeautifulSoup(body, "html.parser").select("a[href]"):
        child = urldefrag(urljoin(url, a["href"]))[0]
        parts = urlsplit(child)
        if (
            parts.scheme != "https"
            or parts.hostname not in {"www.dane.gov.co", "dane.gov.co"}
            or parts.username
            or parts.password
        ):
            continue
        path = unquote(parts.path).lower()
        if "/mayoristas-boletin-semanal-" in path and not path.startswith("/files/"):
            child_kind = "dane-weekly-index"
        elif path.startswith("/files/") and re.search(
            r"(?:semanal|semana|sem[_-]|(?:anexo|anex|bol)[_-]\d)[^/]*\.(?:pdf|xlsx?)$",
            path,
        ):
            child_kind = (
                "dane-weekly-pdf" if path.endswith(".pdf") else "dane-weekly-xlsx"
            )
        else:
            continue
        if child != urldefrag(url)[0]:
            found.append((child, child_kind))
    return list(dict.fromkeys(found))


def _exceptions(text):
    text = folded(clean(text))
    return {
        "eggs": bool(
            re.search(
                r"\bhuevos?\b.{0,160}(?:\$\s*/\s*unidad|pesos\s*(?:/|por)\s*unidad|por\s+unidad)",
                text,
            )
        ),
        "liquids": bool(
            re.search(
                r"aceite vegetal mezcla.{0,100}jugo de frutas.{0,100}vinagre.{0,100}(?:\$\s*/\s*litro|pesos\s*(?:/|por)\s*litro|por\s+litro)",
                text,
            )
        ),
    }


def _unit(name, exceptions):
    name = folded(name)
    if name.startswith("huevo"):
        return "unit" if exceptions.get("eggs") else None
    if name in {"aceite vegetal mezcla", "jugo de frutas", "vinagre"}:
        return "litre" if exceptions.get("liquids") else None
    return "kg"


def _row(
    name,
    market,
    low,
    high,
    mean,
    trend,
    category,
    period,
    locator,
    *,
    page=None,
    exceptions=None,
    allow_missing_identity=False,
):
    from .worker import slug, today

    start, end = period
    if end > today():
        raise ValueError("Weekly monetary table period is in the future")
    numbers = [float(v) for v in (low, high, mean)]
    if not all(math.isfinite(v) for v in numbers) or not (
        0 < numbers[0] <= numbers[2] <= numbers[1]
    ):
        raise ValueError(f"Weekly mean is outside the printed min/max at {locator}")
    name, market = clean(name), clean(market)
    missing_identity = not name or not market
    if missing_identity and not allow_missing_identity:
        raise ValueError("Weekly price lacks a literal product or market")
    unit = _unit(name, exceptions or {}) if name else None
    row = {
        "product_id": slug(name),
        "product_name": name,
        "category": clean(category),
        "publisher": "DANE · SIPSA",
        "series": "dane-weekly",
        "basis": "Precio mayorista semanal",
        "identity_dimensions": {"source_product": name},
        "currency": "COP",
        "unit": unit or "unverified",
        "market": market,
        "date": end.isoformat(),
        "period_start": start.isoformat(),
        "price": numbers[2],
        "min": numbers[0],
        "max": numbers[1],
        "source_locator": locator,
        "source_page": page,
        "details": {
            "period_type": "weekly",
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "price_statistic": "published_mean",
            "trend": clean(trend),
            "source_note": "Media semanal publicada por DANE; mínimo y máximo de la misma semana. La tendencia es el símbolo literal de la fuente.",
            "unit_basis": "Pesos por kilogramo; excepciones de huevos/líquidos solo según nota explícita de la publicación.",
        },
    }
    if unit is None:
        row["price"] = None
        row["details"].update(
            {
                "quality_issue": "La tabla no declara la excepción de unidad para huevos/líquidos; se conserva el precio literal sin asignar kg, unidad o litro.",
                "literal_min": numbers[0],
                "literal_max": numbers[1],
                "literal_mean": numbers[2],
                "literal_unit_heading": "Pesos por kilogramo",
            }
        )
    if missing_identity:
        row["price"] = None
        row["details"].update(
            {
                "quality_issue": "La fila monetaria tiene una celda de producto o mercado vacía; no se arrastra una identidad de filas vecinas.",
                "literal_product_name": name or None,
                "literal_market_name": market or None,
                "literal_min": numbers[0],
                "literal_max": numbers[1],
                "literal_mean": numbers[2],
            }
        )
    return row


def _review_workbook_conflicts(rows):
    """A named workbook row is independent; withhold only conflicting keys."""
    groups = {}
    for row in rows:
        if row.get("price") is None:
            continue
        key = (
            row["product_id"],
            row["product_name"],
            row["market"],
            row["currency"],
            row["unit"],
            row["basis"],
            row["date"],
        )
        groups.setdefault(key, []).append(row)
    for group in groups.values():
        if len({(r["min"], r["max"], r["price"]) for r in group}) <= 1:
            continue
        locators = [r["source_locator"] for r in group]
        for row in group:
            row["details"].update(
                {
                    "quality_issue": "El anexo publica precios distintos para el mismo producto, mercado, unidad y semana; todas las filas en conflicto se conservan para revisión.",
                    "literal_min": row["min"],
                    "literal_max": row["max"],
                    "literal_mean": row["price"],
                    "conflicting_source_locators": locators,
                }
            )
            row["price"] = None
    return rows


def _verify_url(period, url):
    expected = source_date(url)
    if expected is not None and period[1] != expected:
        raise ValueError("Weekly printed period conflicts with the dated source URL")


def parse_workbook(body, url):
    from .worker import workbooks

    sheets = [(name, list(rows)) for name, rows in workbooks(body)]
    notes = "\n".join(
        clean(value)
        for _, rows in sheets
        for row in rows
        for value in row
        if isinstance(value, str)
    )
    exceptions = _exceptions(notes)
    declared_kg = "pesos por kilogramo" in folded(notes)
    result = []
    global_period = _period(
        "\n".join(
            clean(value)
            for _, rows in sheets
            for row in rows[:10]
            for value in row
            if isinstance(value, str)
        )
    )
    for name, rows in sheets:
        grouped = any(
            len(row) >= 4
            and folded(clean(row[0])) == "productos y mercados"
            and [folded(clean(v)) for v in row[1:4]]
            == ["precio minimo", "precio maximo", "precio medio"]
            for row in rows
        )
        if grouped:
            period = global_period or _url_period(url)
            if period is None:
                raise ValueError(
                    "Weekly grouped workbook has no explicit period in cells or URL"
                )
            _verify_url(period, url)
            product = ""
            category = ""
            active = False
            for row_no, row in enumerate(rows, 1):
                label = clean(row[0]) if row else ""
                if re.match(
                    r"Cuadro \d+\. Mercados mayoristas\. Precios de venta de ", label
                ):
                    category = re.sub(r"^.*?Precios de venta de ", "", label).strip()
                    active = False
                    product = ""
                    continue
                if len(row) >= 4 and folded(label) == "productos y mercados":
                    if [folded(clean(v)) for v in row[1:4]] != [
                        "precio minimo",
                        "precio maximo",
                        "precio medio",
                    ]:
                        raise ValueError(
                            "Weekly grouped monetary column meanings changed"
                        )
                    active = True
                    continue
                if not active or not label:
                    continue
                prices = row[1:4]
                if not any(v not in (None, "") for v in prices):
                    product = label
                    continue
                if not all(
                    isinstance(v, (int, float)) and not isinstance(v, bool)
                    for v in prices
                ):
                    raise ValueError(
                        "Weekly grouped workbook has incomplete monetary cells"
                    )
                record = _row(
                    product,
                    label,
                    *prices,
                    row[4] if len(row) > 4 else "",
                    category,
                    period,
                    f"{name}!row {row_no},cols B:D",
                    exceptions=exceptions,
                )
                if not declared_kg:
                    record["price"] = None
                    record["unit"] = "unverified"
                    record["details"].update(
                        {
                            "quality_issue": "El anexo conserva cifras monetarias pero no declara la unidad; consultar el PDF compañero de la misma semana.",
                            "literal_min": float(prices[0]),
                            "literal_max": float(prices[1]),
                            "literal_mean": float(prices[2]),
                            "literal_unit_heading": None,
                            "unit_basis": "No se declara la unidad en las celdas ni encabezados de impresión del anexo.",
                            "period_evidence": "workbook cells"
                            if global_period
                            else "explicit publisher filename range",
                        }
                    )
                result.append(record)
            continue
        header = next(
            (
                i
                for i, row in enumerate(rows)
                if len(row) >= 5
                and clean(row[0]) == "Producto"
                and "mercado" in folded(row[1])
                and "pesos por kilogramo" in folded(row[2])
            ),
            None,
        )
        if header is None:
            continue  # Index, supply tonnes and narrative are not monetary tables.
        subheader = [folded(clean(v)) for v in rows[header + 1]]
        if subheader[2:5] != ["precio minimo", "precio maximo", "precio medio"]:
            raise ValueError("Weekly workbook monetary column meanings changed")
        heading = "\n".join(clean(v) for row in rows[:header] for v in row if v)
        period = _period(heading)
        if period is None:
            raise ValueError("Weekly workbook has no explicit table period")
        _verify_url(period, url)
        category = next(
            (
                re.sub(r"^\d+\.\d+\.\s*", "", clean(row[0])).rstrip("*")
                for row in rows[:header]
                if row and re.match(r"^\d+\.\d+\.\s", clean(row[0]))
            ),
            "Productos mayoristas",
        )
        for row_no, row in enumerate(rows[header + 2 :], header + 3):
            if len(row) < 5 or not any(isinstance(v, (int, float)) for v in row[2:5]):
                continue
            if not all(
                isinstance(v, (int, float)) and not isinstance(v, bool)
                for v in row[2:5]
            ):
                raise ValueError("Weekly workbook has incomplete numeric price cells")
            result.append(
                _row(
                    row[0],
                    row[1],
                    *row[2:5],
                    row[5] if len(row) > 5 else "",
                    category,
                    period,
                    f"{name}!row {row_no},cols C:E",
                    exceptions=exceptions,
                    allow_missing_identity=True,
                )
            )
    if not result:
        raise ValueError(
            "Weekly workbook native extraction failed: no supported monetary tables; original requires layout/OCR review"
        )
    return _review_workbook_conflicts(result)


def _lines(words):
    lines = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        line = next(
            (line for line in lines[-3:] if abs(line[0]["top"] - word["top"]) <= 2),
            None,
        )
        if line is None:
            lines.append([word])
        else:
            line.append(word)
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _native_column(
    lines, headers, category, period, page_no, table_no, side, exceptions
):
    result = []
    boundary = headers[0]["x0"] - 6
    product = ""
    block = []
    continuation = False

    def flush():
        if not block:
            return
        anchors = []
        labels = []
        for number, line in block:
            label = clean(" ".join(w["text"] for w in line if w["x0"] < boundary))
            values = [
                w for w in line if w["x0"] >= boundary and NUMBER.fullmatch(w["text"])
            ]
            if values:
                if len(values) != 3 or not product:
                    raise ValueError(
                        f"Weekly PDF unbound/incomplete monetary row at page {page_no}, column {side}, line {number}: {product!r} / {label!r} / {[v['text'] for v in values]}"
                    )
                anchors.append(
                    {
                        "number": number,
                        "top": values[0]["top"],
                        "values": values,
                        "labels": [],
                        "trend": clean(
                            " ".join(
                                w["text"] for w in line if w["x0"] > values[-1]["x1"]
                            )
                        ),
                    }
                )
            if label:
                labels.append((line[0]["top"], label))
        if not anchors and labels:
            raise ValueError(
                f"Weekly PDF named product has no prices at page {page_no}: {product!r} / {labels!r}"
            )
        for top, label in labels:
            # Historical prices align with the last line of a wrapped market;
            # newer layouts center them between its two lines. A nearest-row
            # heuristic would attach the first line to the preceding market.
            prior = [a for a in anchors if a["top"] < top]
            following = [a for a in anchors if a["top"] >= top - 2]
            aligned = [a for a in anchors if abs(a["top"] - top) <= 2.5]
            if aligned:
                anchor = min(aligned, key=lambda a: abs(a["top"] - top))
            elif prior and top - prior[-1]["top"] <= 7:
                anchor = prior[-1]
            elif following:
                anchor = following[0]
            elif prior and 0 < top - prior[-1]["top"] <= 28:
                # Readable text can contain an orphan heading at a page end.
                # Keep its literal evidence and withhold the adjacent quote;
                # neither a guessed product nor repeated OCR resolves it.
                prior[-1].setdefault("unbound_tail_labels", []).append(label)
                continue
            else:
                raise ValueError(
                    f"Weekly PDF unresolved final market line at page {page_no}: {label}"
                )
            if abs(anchor["top"] - top) > 28:
                raise ValueError(
                    f"Weekly PDF unbound wrapped market at page {page_no}: {label}"
                )
            anchor["labels"].append(label)
        for anchor in anchors:
            values = [
                float(w["text"].replace(".", "").replace(",", "."))
                for w in anchor["values"]
            ]
            record = _row(
                product,
                " ".join(anchor["labels"]),
                *values,
                anchor["trend"],
                category,
                period,
                f"PDF page {page_no},table {table_no},column {side},line {anchor['number']}",
                page=page_no,
                exceptions=exceptions,
            )
            if anchor.get("unbound_tail_labels"):
                record["details"].update(
                    {
                        "quality_issue": "El final del bloque contiene texto sin una fila monetaria vinculable; se conserva el texto literal y la cotización adyacente para revisión.",
                        "literal_unbound_tail_labels": anchor["unbound_tail_labels"],
                        "literal_min": values[0],
                        "literal_max": values[1],
                        "literal_mean": values[2],
                    }
                )
                record["price"] = None
            result.append(record)

    column_left = min(
        (w["x0"] for line in lines for w in line if w["x0"] < boundary), default=0
    )
    for number, line in enumerate(lines, 1):
        literal = clean(" ".join(w["text"] for w in line))
        if literal == str(page_no):
            continue
        if ("variacion" in folded(literal) and "%" in literal) or folded(
            literal
        ).startswith(("tendencias", "fuente:", "nota:", "*")):
            break
        label_words = [w for w in line if w["x0"] < boundary]
        label = clean(" ".join(w["text"] for w in label_words))
        bold = label and any("bold" in w["fontname"].lower() for w in label_words)
        numeric = any(w["x0"] >= boundary and NUMBER.fullmatch(w["text"]) for w in line)
        # Original reports occasionally forgot bold on a standalone product
        # heading. A short left-aligned label followed by a complete, separately
        # named market row has a different geometry from a wrapped market.
        following = lines[number] if number < len(lines) else []
        next_label = clean(" ".join(w["text"] for w in following if w["x0"] < boundary))
        next_values = [
            w for w in following if w["x0"] >= boundary and NUMBER.fullmatch(w["text"])
        ]
        previous_prices = [
            w
            for prior in lines[max(0, number - 3) : number - 1]
            for w in prior
            if w["x0"] >= boundary and NUMBER.fullmatch(w["text"])
        ]
        follows_centered_price = any(
            0 < line[0]["top"] - w["top"] <= 7 for w in previous_prices
        )
        plain_heading = bool(
            label
            and not follows_centered_price
            and not numeric
            and not bold
            and not re.search(
                r"[,.(]",
                re.sub(r"\((?:bolsita|caja)\)", "", label, flags=re.IGNORECASE),
            )
            and label_words[0]["x0"] <= column_left + 3
            and max(w["x1"] for w in label_words)
            < column_left + (boundary - column_left) * 0.85
            and len(next_values) == 3
            and re.search(r"[,.(]", next_label)
            and abs(following[0]["top"] - next_values[0]["top"]) <= 2
        )
        if bold and label_words[0]["x0"] > column_left + 25 and not numeric:
            # Centered section captions (e.g. Carne de cerdo) are not the
            # following left-aligned product's first line.
            flush()
            block = []
            product = ""
            continuation = False
            continue
        if bold or plain_heading:
            flush()
            block = []
            label = re.sub(
                r"\s*\(?(?:continuaci[oó]n|conclusi[oó]n)\)$",
                "",
                label,
                flags=re.IGNORECASE,
            ).strip()
            product = clean(product + " " + label) if continuation else label
            continuation = True
        else:
            block.append((number, line))
            continuation = False
    flush()
    return result


def _column_headers(words, width):
    minima = sorted(
        (word for word in words if folded(word["text"]) == "minimo"),
        key=lambda word: word["x0"],
    )
    if len(minima) != 2:
        return None
    columns = []
    for side, minimum in enumerate(minima):
        lo, hi = (0, width / 2) if side == 0 else (width / 2, width)
        headers = sorted(
            (
                word
                for word in words
                if lo < word["x0"] < hi
                and abs(word["top"] - minimum["top"]) < 3
                and folded(word["text"]) in {"minimo", "maximo", "medio"}
            ),
            key=lambda word: word["x0"],
        )
        if [folded(word["text"]) for word in headers] != ["minimo", "maximo", "medio"]:
            return None
        columns.append(headers)
    return columns


def _overprint_column_headers(page, top, bottom):
    """Recover exact overprinted headers; never repair monetary body text."""
    deduped = page.dedupe_chars(
        tolerance=0, extra_attrs=("fontname", "size", "x1", "bottom")
    )
    if len(deduped.chars) == len(page.chars):
        return None
    words = deduped.extract_words(extra_attrs=["fontname", "size"])
    columns = _column_headers(
        [word for word in words if top <= word["top"] < bottom], page.width
    )
    if columns is None:
        return None
    attrs = ("upright", "text", "fontname", "size", "doctop", "x0", "x1", "bottom")
    remaining = Counter(tuple(char[attr] for attr in attrs) for char in deduped.chars)
    repaired_header = False
    for char in page.chars:
        key = tuple(char[attr] for attr in attrs)
        if remaining[key]:
            remaining[key] -= 1
            continue
        for side, headers in enumerate(columns):
            lo, hi = (0, page.width / 2) if side == 0 else (page.width / 2, page.width)
            if not lo < char["x0"] < hi:
                continue
            if char["top"] > max(header["bottom"] for header in headers) + 2 and char[
                "bottom"
            ] < min(bottom, page.height - 22):
                # Duplicated body digits/names need separate validation. Their
                # existence must not turn a header repair into a guessed price.
                return None
            if any(
                header["x0"] <= char["x0"] < header["x1"]
                and header["top"] <= char["top"] < header["bottom"]
                for header in headers
            ):
                repaired_header = True
    return columns if repaired_header else None


def parse_pdf(body, url, readings_by_page=None):
    import pdfplumber

    result = []
    failed = []
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        texts = [page.extract_text() or "" for page in pdf.pages]
        exceptions = _exceptions("\n".join(texts))
        for page_no, (page, text) in enumerate(zip(pdf.pages, texts), 1):
            if readings_by_page and page_no in readings_by_page:
                result.extend(
                    _ocr_page(readings_by_page[page_no], url, page_no, exceptions)
                )
                continue
            if len(re.sub(r"\W", "", text)) < 25:
                from .pdf_sources import has_table_sized_image

                if has_table_sized_image(page):
                    failed.append(page_no)
                continue
            # A readable DANE title does not make an image-only price table
            # readable. Require a large image and explicit publication context;
            # normal photographs/logos and fully readable monetary pages stay
            # on the native path.
            if len(re.sub(r"\W", "", text)) < 250 and re.search(
                r"sipsa|precios mayoristas", folded(text)
            ):
                from .pdf_sources import has_table_sized_image

                if has_table_sized_image(page):
                    failed.append(page_no)
                    continue
            # Multiple independent monetary tables can share one old PDF page.
            words = page.extract_words(extra_attrs=["fontname", "size"])
            starts = sorted(
                {
                    w["top"]
                    for w in words
                    if w["text"] == "Cuadro" and w["x0"] < page.width * 0.20
                }
            )
            for table_no, top in enumerate(starts, 1):
                bottom = starts[table_no] if table_no < len(starts) else page.height
                section = page.crop((0, max(0, top - 1), page.width, bottom))
                table_text = section.extract_text() or ""
                caption = re.search(
                    r"Cuadro\s+\d+\.\s*Mercados mayoristas\.\s*Precios de venta de\s+([^\n]+)",
                    table_text,
                    re.IGNORECASE,
                )
                if not caption:
                    continue
                context = table_text[:550]
                period = _period(context)
                if period is None:
                    raise ValueError(
                        f"Weekly PDF page {page_no} has no verified monetary-table period"
                    )
                _verify_url(period, url)
                category = re.sub(
                    r"\s*\((?:continuaci[oó]n|conclusi[oó]n)\)",
                    "",
                    caption[1],
                    flags=re.IGNORECASE,
                ).strip()
                local = [w for w in words if top <= w["top"] < bottom]
                columns = _column_headers(local, page.width)
                recovered_headers = False
                if columns is None:
                    columns = _overprint_column_headers(page, top, bottom)
                    recovered_headers = columns is not None
                if columns is None or "pesos por kilogramo" not in folded(context):
                    failed.append(page_no)
                    continue
                for side, headers in enumerate(columns, 1):
                    lo, hi = (
                        (0, page.width / 2)
                        if side == 1
                        else (page.width / 2, page.width)
                    )
                    body_words = [
                        w
                        for w in local
                        if w.get("upright", True)
                        and lo + (page.width * 0.04 if side == 1 else 1)
                        < w["x0"]
                        < hi - 7
                        and w["top"] > max(h["bottom"] for h in headers) + 2
                        and w["bottom"] < min(bottom, page.height - 22)
                    ]
                    try:
                        column_rows = _native_column(
                            _lines(body_words),
                            headers,
                            category,
                            period,
                            page_no,
                            table_no,
                            side,
                            exceptions,
                        )
                        if recovered_headers:
                            for row in column_rows:
                                row["details"]["native_header_recovery"] = (
                                    "exact_overprinted_glyphs"
                                )
                        result.extend(column_rows)
                    except ValueError as error:
                        if str(error).startswith(
                            (
                                "Weekly PDF unbound",
                                "Weekly PDF unresolved",
                                "Weekly PDF named product has no prices",
                            )
                        ):
                            failed.append(page_no)
                        else:
                            raise
    if failed:
        raise NormalExtractionFailed(failed)
    if not result:
        raise ValueError(
            "Weekly PDF native extraction failed: no supported monetary tables; original requires layout/OCR review"
        )
    # The first 2012 reports sometimes omit a product heading altogether. Two
    # different values for the same literal product/market reveal an ambiguous
    # block. Preserve every row as review; never invent the absent heading.
    seen = {}
    ambiguous = set()
    orphaned_products = {
        row["product_name"]
        for row in result
        if row["details"].get("literal_unbound_tail_labels")
    }
    for row in result:
        identity = (row["product_name"], row["market"], row["date"], row["unit"])
        values = (
            row["min"],
            row["max"],
            row["price"] or row["details"].get("literal_mean"),
        )
        if identity in seen and seen[identity] != values:
            ambiguous.add(row["product_name"])
        seen[identity] = values
    for row in result:
        if row["product_name"] in ambiguous or row["product_name"] in orphaned_products:
            issue = (
                "El bloque contiene un encabezado final sin filas vinculables; las cotizaciones con ese producto, incluidas sus continuaciones, se conservan para revisión."
                if row["product_name"] in orphaned_products
                else "El bloque repite mercados con precios distintos y no permite verificar un encabezado de producto único; se conservan las cifras literales para revisión."
            )
            row["details"].update(
                {
                    "quality_issue": issue,
                    "literal_min": row["min"],
                    "literal_max": row["max"],
                    "literal_mean": row["price"] or row["details"].get("literal_mean"),
                }
            )
            row["price"] = None
    return result


def parse(body, url, kind):
    if kind in INDEX_KINDS:
        return []
    if kind == "dane-weekly-xlsx":
        return parse_workbook(body, url)
    if kind == "dane-weekly-pdf":
        return parse_pdf(body, url)
    raise ValueError("Unsupported weekly source kind")


def _ocr_page(reading, url, page_no, document_exceptions):
    """Only agreed literal OCR tables with explicit weekly monetary headings."""
    text = clean(reading.get("text", ""))
    if not re.search(r"mercados mayoristas.*precios de venta", folded(text)):
        # Fully scanned narrative pages may have been required to find tables.
        if not reading.get("tables"):
            return []
        raise ValueError(f"Weekly OCR page {page_no} lacks a monetary-table caption")
    monetary_caption = re.search(
        r"mercados mayoristas.*?precios de venta", folded(text)
    )
    period = _period(text[monetary_caption.start() : monetary_caption.start() + 550])
    if period is None or "pesos por kilogramo" not in folded(text):
        raise ValueError(f"Weekly OCR page {page_no} lacks explicit period/unit")
    _verify_url(period, url)
    category_match = re.search(
        r"precios de venta de (.*?)(?:\b20\d{2}|\d{1,2} al|\(continuaci|\(conclusi)",
        text,
        re.IGNORECASE,
    )
    category = clean(category_match[1]) if category_match else "Productos mayoristas"
    exceptions = {
        key: value or _exceptions(text)[key]
        for key, value in document_exceptions.items()
    }
    result = []
    for table_no, table in enumerate(reading.get("tables", []), 1):
        if isinstance(table, dict):
            table = [table.get("headers", []), *table.get("rows", [])]
        header = next(
            (
                i
                for i, row in enumerate(table)
                if all(
                    any(word in folded(clean(cell)) for cell in row)
                    for word in ["minimo", "maximo", "medio"]
                )
            ),
            None,
        )
        if header is None:
            if any(NUMBER.fullmatch(clean(cell)) for row in table for cell in row):
                raise ValueError(
                    "Weekly OCR contains numeric table cells without explicit monetary columns"
                )
            continue
        headings = [folded(clean(cell)) for cell in table[header]]
        indices = [
            next(i for i, h in enumerate(headings) if word in h)
            for word in ["minimo", "maximo", "medio"]
        ]
        if indices != list(range(indices[0], indices[0] + 3)) or indices[0] not in (
            1,
            2,
        ):
            raise ValueError("Weekly OCR price columns are ambiguous")
        explicit_product_column = indices[0] == 2
        product = ""
        for row_no, row in enumerate(table[header + 1 :], header + 2):
            cells = [clean(v) for v in row]
            if not any(cells):
                continue
            tokens = [cells[i] if i < len(cells) else "" for i in indices]
            if not any(tokens):
                if cells[0]:
                    product = re.sub(
                        r"\s*\(continuaci[oó]n\)", "", cells[0], flags=re.IGNORECASE
                    )
                continue
            if not all(NUMBER.fullmatch(token) for token in tokens):
                raise ValueError("Weekly OCR has incomplete literal monetary cells")
            values = [
                float(token.replace(".", "").replace(",", ".")) for token in tokens
            ]
            if explicit_product_column:
                product = cells[0]
            result.append(
                _row(
                    product,
                    cells[1] if explicit_product_column else cells[0],
                    *values,
                    cells[indices[-1] + 1] if len(cells) > indices[-1] + 1 else "",
                    category,
                    period,
                    f"PDF page {page_no},OCR table {table_no},row {row_no}",
                    page=page_no,
                    exceptions=exceptions,
                )
            )
    if not result:
        raise ValueError(
            f"Weekly OCR page {page_no} contains no supported monetary rows"
        )
    return result


def parse_with_ocr(body, url, kind, readings_by_page):
    if kind != "dane-weekly-pdf":
        raise ValueError("Weekly workbook OCR requires a typed workbook review")
    return parse_pdf(body, url, readings_by_page)

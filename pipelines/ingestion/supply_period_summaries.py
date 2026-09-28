"""Native DANE monthly/first-fortnight aggregates, never additive microdata.

XLSX summary sheets retain their native precision. PDF market tables retain only
printed rounded quantities; chart axes and unlabeled curves are never readings.
"""

import calendar
import io
import math
import re
from datetime import date

import openpyxl
import pdfplumber

from .supply_summaries import publish_rows

VERSION = "supply-period-summary-v1"
KIND = "supply-period-summary"


def period(text):
    from .worker import MONTH_NUM, clean

    text = clean(text).lower()
    match = re.search(
        r"(?:(primera quincena) de )?([a-z]+)(?: de)? (20\d{2})(?:\s|$|[•*])", text
    )
    if not match or match[2] not in MONTH_NUM:
        raise ValueError("Missing explicit monthly/first-fortnight report period")
    half, month, year = bool(match[1]), MONTH_NUM[match[2]], int(match[3])
    first = date(year, month, 1)
    last = date(year, month, 15 if half else calendar.monthrange(year, month)[1])
    return first, last, "first_fortnight" if half else "monthly"


def periods(caption, left, right):
    from .worker import MONTHS, today

    start, end, frequency = period(caption)
    prev = date(
        start.year - (start.month == 1), 12 if start.month == 1 else start.month - 1, 1
    )
    prev_end = date(
        prev.year,
        prev.month,
        15
        if frequency == "first_fortnight"
        else calendar.monthrange(prev.year, prev.month)[1],
    )
    for label, expected in [(left, prev), (right, start)]:
        names = [m for m in MONTHS if re.search(r"\b" + m + r"\b", label.lower())]
        years = set(map(int, re.findall(r"20\d{2}", label)))
        if names != [MONTHS[expected.month - 1]] or (
            years and years != {expected.year}
        ):
            raise ValueError(
                f"Summary column period conflicts with report caption: {left!r} / {right!r} vs {caption!r}"
            )
        if "quincena" in label.lower() and (
            frequency != "first_fortnight" or "primera" not in label.lower()
        ):
            raise ValueError("Conflicting summary fortnight qualifier")
    if end > today():
        raise ValueError("Future supply reference period")
    return [(prev, prev_end, frequency), (start, end, frequency)]


def _number(cell, percent=False):
    from .daily_recovery import percentage_change

    value = cell.value
    if value is None:
        return None
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError("Invalid summary cell " + cell.coordinate)
    if percent:
        result, _ = percentage_change(value, cell.number_format)
        return result
    if value < 0:
        raise ValueError("Negative supply quantity " + cell.coordinate)
    return value


def _row(locator, value, unit, name, dates, statistic, level, **details):
    start, end, frequency = dates
    if (
        statistic in ("group_share", "market_share")
        and value is not None
        and not 0 <= value <= 100 + 1e-9
    ):
        raise ValueError("Native supply share outside 0–100 at " + locator)
    return {
        "source_locator": locator + "; " + VERSION,
        "kind": KIND,
        "observed_on": end,
        "name": name,
        "category": "Abastecimiento — resúmenes por período",
        "details": {
            "value": value,
            "unit": unit,
            "quantity_tonnes": value if unit == "t" else None,
            "statistic": statistic,
            "aggregation_level": level,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "frequency": frequency,
            "non_additive": True,
            "availability": "not_reported" if value is None else "reported",
            "parser_version": VERSION,
            **details,
        },
    }


def parse_workbook(data, expected_day=None):
    """Three proved native summary layouts: market totals, groups, and shares."""
    from .worker import clean

    if not data.startswith(b"PK"):
        return [], ["Unsupported native summary workbook format"]
    book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    rows, reviews = [], []
    try:
        for sheet in book:
            if sheet.title not in ("1", "2", "3"):
                continue
            # Several official share sheets format thousands of empty columns.
            # Only the seven declared summary columns are read; a native footer
            # below is required before accepting the bounded 500-row window.
            cells = list(sheet.iter_rows(max_row=500, max_col=7))
            if len(cells) < 11:
                continue

            def get(r, c, cells=cells):
                return cells[r - 1][c - 1]

            caption = clean(get(4, 1).value)
            heading = clean(get(6, 1).value)
            supported = (
                "Variación en el abastecimiento de alimentos según ciudad y mercado mayorista",
                "Cantidad y participación del abastecimiento por grupos de alimentos en los mercados mayoristas",
                "Participación de los mercados mayoristas en el total de abastecimiento",
            )
            if not any(title in heading for title in supported):
                continue
            staged = []
            try:
                current = period(caption)
                if expected_day and (current[0].year, current[0].month) != (
                    expected_day.year,
                    expected_day.month,
                ):
                    raise ValueError(
                        "Native supply reference month conflicts with archive date"
                    )

                def emit(
                    rownum,
                    col,
                    name,
                    dates,
                    statistic,
                    level,
                    unit="t",
                    *,
                    get=get,
                    staged=staged,
                    sheet=sheet,
                    caption=caption,
                    heading=heading,
                    **extras,
                ):
                    cell = get(rownum, col)
                    staged.append(
                        _row(
                            f"{sheet.title}!row {rownum},col {col}",
                            _number(cell, unit == "percentage_points"),
                            unit,
                            name,
                            dates,
                            statistic,
                            level,
                            sheet=sheet.title,
                            row=rownum,
                            column=col,
                            cell=cell.coordinate,
                            literal_value=cell.value,
                            number_format=cell.number_format,
                            caption=caption,
                            table_heading=heading,
                            extraction_method="native-workbook-cells",
                            precision="native_workbook_value",
                            native_headers={
                                get(rr, cc).coordinate: get(rr, cc).value
                                for rr in (10, 11)
                                for cc in range(1, 7)
                                if get(rr, cc).value is not None
                            },
                            **extras,
                        )
                    )

                if sheet.title == "1":
                    if [clean(get(10, c).value) for c in (1, 2, 5)] != [
                        "Ciudad",
                        "Central",
                        "Variación (%)",
                    ] or not all("(t)" in clean(get(10, c).value) for c in (3, 4)):
                        raise ValueError(
                            "Unsupported native market-total headers/units"
                        )
                    dates = periods(
                        caption, clean(get(10, 3).value), clean(get(10, 4).value)
                    )
                    seen = set()
                    for r in range(11, len(cells) + 1):
                        a, b = clean(get(r, 1).value), clean(get(r, 2).value)
                        if a.startswith(("Fuente", "Nota", "*")):
                            break
                        if not a:
                            continue
                        total = a.lower().startswith("total")
                        if not total and not b:
                            raise ValueError("Missing literal market identity")
                        name = a if total else a + ", " + b
                        if name in seen:
                            raise ValueError("Duplicate native market identity")
                        seen.add(name)
                        level = "reported_markets_total" if total else "market_total"
                        emit(r, 3, name, dates[0], "market_arrivals", level)
                        emit(r, 4, name, dates[1], "market_arrivals", level)
                        emit(
                            r,
                            5,
                            name,
                            dates[1],
                            "period_change",
                            level,
                            "percentage_points",
                            compared_period_start=dates[0][0].isoformat(),
                            compared_period_end=dates[0][1].isoformat(),
                        )
                elif sheet.title == "2":
                    if [clean(get(10, c).value) for c in (1, 6)] != [
                        "Grupo",
                        "Variación (%)",
                    ] or [clean(get(11, c).value) for c in (2, 3, 4, 5)] != [
                        "Cantidad (t)",
                        "Participación (%)",
                        "Cantidad (t)",
                        "Participación (%)",
                    ]:
                        raise ValueError(
                            "Unsupported native group-summary headers/units"
                        )
                    dates = periods(
                        caption, clean(get(10, 2).value), clean(get(10, 4).value)
                    )
                    market = None
                    seen = set()
                    for r in range(12, len(cells) + 1):
                        name = clean(get(r, 1).value)
                        if name.startswith(("Fuente", "Nota", "*")):
                            break
                        if not name:
                            continue
                        groups = {
                            "Frutas",
                            "Tubérculos, raíces y plátanos",
                            "Verduras y hortalizas",
                            "Otros grupos",
                            "Total",
                        }
                        if name not in groups and all(
                            get(r, c).value is None for c in range(2, 7)
                        ):
                            market = name
                            continue
                        if not market:
                            raise ValueError(
                                "Group values without literal market heading"
                            )
                        if (market, name) in seen:
                            raise ValueError("Duplicate native group identity")
                        seen.add((market, name))
                        level = (
                            "market_group_total"
                            if name.lower().startswith("total")
                            else "market_group"
                        )
                        if market.lower().startswith("total"):
                            level = (
                                "reported_markets_group_total"
                                if name.lower().startswith("total")
                                else "reported_markets_group"
                            )
                        for col, dp, stat, unit in [
                            (2, 0, "group_arrivals", "t"),
                            (3, 0, "group_share", "percentage_points"),
                            (4, 1, "group_arrivals", "t"),
                            (5, 1, "group_share", "percentage_points"),
                            (6, 1, "period_change", "percentage_points"),
                        ]:
                            emit(
                                r,
                                col,
                                market,
                                dates[dp],
                                stat,
                                level,
                                unit,
                                food_group=name,
                                compared_period_start=dates[0][0].isoformat()
                                if col == 6
                                else None,
                            )
                else:
                    if clean(get(10, 1).value) != "Ciudad, Mercado Mayorista":
                        raise ValueError("Unsupported native market-share identity")
                    dates = periods(
                        caption, clean(get(10, 2).value), clean(get(10, 3).value)
                    )
                    seen = set()
                    for r in range(11, len(cells) + 1):
                        name = clean(get(r, 1).value)
                        if name.startswith(("Fuente", "Nota", "*")):
                            break
                        if not name:
                            continue
                        if name in seen:
                            raise ValueError("Duplicate native market-share identity")
                        seen.add(name)
                        for col, dp in [(2, 0), (3, 1)]:
                            emit(
                                r,
                                col,
                                name,
                                dates[dp],
                                "market_share",
                                "market_total",
                                "percentage_points",
                            )
                if not any(
                    clean(get(r, 1).value).startswith("Fuente")
                    for r in range(11, len(cells) + 1)
                ):
                    raise ValueError(
                        "Native summary has no source footer within bounded rows"
                    )
                if not staged:
                    raise ValueError("Recognized native summary has no bound rows")
                rows.extend(staged)
            except ValueError as exc:
                reviews.append(sheet.title + ": " + str(exc))
    finally:
        book.close()
    return rows, reviews


def _pdf_number(text):
    if not re.fullmatch(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?%?", text):
        raise ValueError("Invalid literal PDF supply number: " + text)
    return float(text.rstrip("%").replace(".", "").replace(",", "."))


def _lines(words):
    lines = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if not lines or abs(word["top"] - lines[-1][0]["top"]) > 3:
            lines.append([word])
        else:
            lines[-1].append(word)
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def parse_pdf(data, expected_day=None):
    """Explicit native market-total tables only; no narrative/chart digitization."""
    from .worker import MONTHS, clean

    rows = []
    reviews = []
    active = False
    finished = False
    seen = set()
    period_pair = None
    expected_markets = None
    with pdfplumber.open(io.BytesIO(data)) as doc:
        cover = doc.pages[0].extract_text() or ""
        candidates = [
            line
            for line in cover.splitlines()
            if re.match(
                r"^(?:Primera quincena de )?(?:"
                + "|".join(MONTHS)
                + r")(?: de)? 20\d{2}",
                line,
                re.IGNORECASE,
            )
        ]
        if len(candidates) != 1:
            return [], ["Missing unique native monthly/fortnight cover period"]
        caption = candidates[0]
        # Only the native 13-market and 32-market bulletin layouts are proved.
        # The count is read from the original, not filled from a registry/date.
        intro = " ".join((p.extract_text() or "") for p in doc.pages[:4])
        if re.search(r"32 mercados mayoristas", intro):
            expected_markets = 32
        elif re.search(r"trece mercados|13 mercados", intro):
            expected_markets = 13
        else:
            return [], ["Unsupported or absent native market coverage count"]
        current = period(caption)
        if expected_day and (current[0].year, current[0].month) != (
            expected_day.year,
            expected_day.month,
        ):
            return [], ["Native PDF summary month conflicts with archive date"]
        for page_number, page in enumerate(doc.pages, 1):
            if finished:
                break
            text = page.extract_text() or ""
            marker = any(
                s in text
                for s in [
                    "Volúmenes mensuales ingresados a los mercados",
                    "Toneladas quincenales ingresadas a los mercados",
                    "Variación en el abastecimiento de alimentos según ciudad y mercado mayorista",
                ]
            )
            if not marker and not active:
                continue
            words = page.extract_words()
            headers = []
            for w in words:
                if w["text"] not in ("Ciudades", "Ciudad"):
                    continue
                central = next(
                    (
                        v
                        for v in words
                        if v["text"] in ("Sitio", "Central")
                        and abs(v["top"] - w["top"]) < 4
                        and v["x0"] > w["x1"]
                    ),
                    None,
                )
                if central:
                    headers.append((w, central))
            if len(headers) != 1:
                reviews.append(
                    f"PDF page {page_number}: no unique native market-table header"
                )
                continue
            city, central = headers[0]
            old = city["text"] == "Ciudades"
            right = page.width / 2 if old else page.width
            header_band = " ".join(
                w["text"]
                for w in words
                if w["x0"] < right and abs(w["top"] - city["top"]) < 26
            )
            names = [
                m
                for m in MONTHS
                if re.search(r"\b" + m + r"\b", header_band, re.IGNORECASE)
            ]
            prev = MONTHS[(current[0].month - 2) % 12]
            now = MONTHS[current[0].month - 1]
            if set(names) != {prev, now}:
                reviews.append(
                    f"PDF page {page_number}: market-table months conflict with cover"
                )
                continue
            period_pair = periods(caption, prev, now)
            table_caption = " ".join(
                w["text"]
                for w in words
                if w["x0"] < right and city["top"] - 60 <= w["top"] < city["top"]
            )
            if not active:
                years = set(map(int, re.findall(r"20\d{2}", table_caption)))
                if years != {dp[0].year for dp in period_pair}:
                    return [], [
                        f"PDF page {page_number}: table caption years conflict with report: {table_caption}"
                    ]
                if len(years) == 2:
                    for dp in period_pair:
                        year, month = dp[0].year, MONTHS[dp[0].month - 1]
                        if not re.search(
                            rf"{year}\s*\(\s*{month}\s*\)|{month}\s+{year}",
                            table_caption,
                            re.IGNORECASE,
                        ):
                            return [], [
                                f"PDF page {page_number}: unbound caption month/year: {table_caption}"
                            ]
            if "toneladas" not in text.lower() and not active:
                return [], [f"PDF page {page_number}: no native tonne-unit evidence"]
            active = True
            split = 94 if old else 110 if city["x0"] < 90 else 155
            if not old and not (60 <= city["x0"] <= 130):
                reviews.append(
                    f"PDF page {page_number}: unsupported native market column geometry"
                )
                continue
            below = [
                w for w in words if w["top"] > city["bottom"] + 2 and w["x0"] < right
            ]
            numeric = []
            for line in _lines(below):
                ns = [
                    w
                    for w in line
                    if w["x0"] > central["x1"] + 8
                    and re.fullmatch(
                        r"-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?%?", w["text"]
                    )
                ]
                if len(ns) == 3:
                    numeric.append(ns)
            for i, ns in enumerate(numeric):
                y = ns[0]["top"]
                low = (numeric[i - 1][0]["top"] + y) / 2 if i else city["bottom"] + 2
                high = (
                    (numeric[i + 1][0]["top"] + y) / 2
                    if i + 1 < len(numeric)
                    else max(w["bottom"] for w in ns) + 3
                )
                left = [
                    w
                    for w in below
                    if low <= w["top"] < high and w["x1"] < ns[0]["x0"] - 2
                ]
                city_text = clean(
                    " ".join(
                        w["text"]
                        for w in sorted(left, key=lambda w: (w["top"], w["x0"]))
                        if w["x0"] < split
                    )
                )
                market_text = clean(
                    " ".join(
                        w["text"]
                        for w in sorted(left, key=lambda w: (w["top"], w["x0"]))
                        if w["x0"] >= split
                    )
                )
                total = city_text.lower() == "total"
                if not city_text or (not total and not market_text):
                    reviews.append(
                        f"PDF page {page_number}, y{y:.2f}: missing literal city/market binding"
                    )
                    continue
                name = city_text if total else city_text + ", " + market_text
                if name in seen:
                    reviews.append(
                        f"PDF page {page_number}, y{y:.2f}: duplicate market {name}"
                    )
                    continue
                seen.add(name)
                level = "reported_markets_total" if total else "market_total"
                for j, (w, stat, unit, dp) in enumerate(
                    zip(
                        ns,
                        ["market_arrivals", "market_arrivals", "period_change"],
                        ["t", "t", "percentage_points"],
                        [0, 1, 1],
                    )
                ):
                    value = _pdf_number(w["text"])
                    if j < 2 and value < 0:
                        raise ValueError("Negative native PDF quantity")
                    rows.append(
                        _row(
                            f"PDF page {page_number}, row y{y:.2f}, column {j + 1}",
                            value,
                            unit,
                            name,
                            period_pair[dp],
                            stat,
                            level,
                            source_page=page_number,
                            table_caption=table_caption,
                            literal_value=w["text"],
                            caption=caption,
                            extraction_method="native-pdf-word-geometry",
                            precision="printed_pdf_value",
                            native_bbox=[w[k] for k in ("x0", "top", "x1", "bottom")],
                            compared_period_start=period_pair[0][0].isoformat()
                            if j == 2
                            else None,
                        )
                    )
                if total:
                    finished = True
                    break
    if not rows or not finished or len(rows) != (expected_markets + 1) * 3 or reviews:
        return [], reviews + [
            "Native market summary incomplete or ambiguous; full declared market count and Total required"
        ]
    return rows, reviews


def publish(db, data, document_id, kind, expected_day=None):
    """Keep source-scoped values/reviews without touching food or price models."""
    from .daily_publication import retain_resolution

    rows, reviews = (parse_pdf if kind.endswith("pdf") else parse_workbook)(
        data, expected_day
    )
    with db.transaction():
        count = publish_rows(db, rows, document_id)
        for reason in reviews:
            retain_resolution(
                db,
                "supply_period_summary_review",
                {
                    "document_id": document_id,
                    "parser_version": VERSION,
                    "reason": reason,
                    "scope": "source table; original bytes retained",
                    "non_additive": True,
                },
            )
    return count, reviews

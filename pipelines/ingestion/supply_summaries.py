"""Non-additive DANE daily market totals from explicitly labelled annex sheets.

These provisional tonne totals are source references, never food microdata or
prices. Missing cells remain missing and the separate Total row is not a market.
"""

import io
import math
import re
from datetime import date, datetime

import openpyxl
from psycopg.types.json import Jsonb

VERSION = "supply-daily-summary-v1"
KIND = "supply-daily-summary"


def _period(text):
    from .worker import MONTH_NUM, clean

    match = re.fullmatch(
        r"([a-záéíóúñ]+) (\d{1,2}) a (?:(\w+) )?(\d{1,2}) de (20\d{2})\*?",
        clean(text).lower(),
    )
    if not match:
        raise ValueError("Unsupported daily supply caption period")
    first, left, last, right, year = match.groups()
    a, b = MONTH_NUM.get(first), MONTH_NUM.get(last or first)
    if not a or not b:
        raise ValueError("Unknown daily supply caption month")
    return date(int(year) - (a > b), a, int(left)), date(int(year), b, int(right))


def _number(cell):
    value = cell.value
    if value is None:
        return None
    if (
        not isinstance(value, (float, int))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError("Invalid native daily supply number at " + cell.coordinate)
    return value


def _comparison(label, days):
    """Resolve both literal day/month labels against validated native dates."""
    from .worker import MONTH_NUM

    match = re.fullmatch(
        r"(\d{1,2})([a-z]+)\.?\s*/\s*(\d{1,2})([a-z]+)\.?", label.lower()
    )
    if not match:
        raise ValueError("Ambiguous daily supply variation dates")
    result = []
    for day, month in (match.groups()[:2], match.groups()[2:]):
        matches = [
            d for d in days if d.day == int(day) and d.month == MONTH_NUM.get(month)
        ]
        if len(matches) != 1:
            raise ValueError("Daily supply variation date absent from native columns")
        result.append(matches[0])
    if result[0] != max(days) or result[1] >= result[0]:
        raise ValueError("Daily supply variation comparison is not the latest day")
    return result


def parse(data, expected_day=None):
    """Return exact cell references, or [] for a different summary layout.

    Only this proven native XLSX schema is supported. Unrecognized XLS and monthly
    summaries retain their originals without claiming typed daily coverage.
    """
    from .worker import SourceDateMismatch, clean, today

    if not data.startswith(b"PK"):
        return []
    book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    try:
        for sheet in book:
            if clean(sheet.title).lower() != "abastecimiento":
                continue
            # Materialize the bounded native summary, not unrelated price sheets.
            if (sheet.max_row or 0) > 500 or (sheet.max_column or 0) > 400:
                raise ValueError("Daily supply summary exceeds supported bounds")
            rows = list(sheet.iter_rows())
            if len(rows) < 4:
                continue

            def get(r, c=1, rows=rows):
                return rows[r - 1][c - 1]

            title = clean(get(4).value)
            match = re.fullmatch(
                r"Toneladas de alimentos ingresados diariamente, según ciudad y mercado mayorista \((\d+) mercados\)",
                title,
            )
            if not match:
                continue
            if len(rows) < 11:
                raise ValueError("Incomplete recognized daily supply summary")
            market_count = int(match[1])
            end = 11 + market_count
            if not (1 <= market_count <= 100) or len(rows) < end + 2:
                raise ValueError("Invalid daily supply market count")
            if (
                clean(get(7).value) != "Mercado mayorista"
                or clean(get(7, 2).value) != "Información provisional"
                or clean(get(11).value) != "Total"
                or clean(get(end + 1).value) != "Fuente DANE- SIPSA"
                or clean(get(end + 2).value) != "*Datos provisionales"
            ):
                raise ValueError(
                    "Unrecognized daily supply total/provisional/source labels"
                )
            names = [clean(get(r).value) for r in range(12, end + 1)]
            if (
                any(not n or n == "Total" for n in names)
                or len(set(names)) != market_count
            ):
                raise ValueError("Missing or duplicate daily supply market labels")
            dated, changes = [], []
            for col in range(2, len(rows[8]) + 1):
                value = get(9, col).value
                if isinstance(value, (datetime, date)):
                    day = value.date() if isinstance(value, datetime) else value
                    if clean(get(10, col).value) != "Toneladas":
                        raise ValueError(
                            "Daily supply column has no literal tonne unit"
                        )
                    dated.append((col, day))
                elif value is not None:
                    if clean(get(10, col).value):
                        raise ValueError("Unknown daily supply numeric column unit")
                    changes.append((col, clean(value)))
            days = [d for _, d in dated]
            if not days or len(days) != len(set(days)) or days != sorted(days):
                raise SourceDateMismatch(
                    "Missing, duplicate or unordered daily supply dates"
                )
            if [c for c, _ in dated] != list(range(2, 2 + len(dated))):
                raise ValueError("Daily supply dates are not contiguous native columns")
            first, last = _period(get(5).value)
            if (days[0], days[-1]) != (first, last) or (last - first).days + 1 != len(
                days
            ):
                raise SourceDateMismatch(
                    "Daily supply native dates disagree with caption"
                )
            if last > today() or (expected_day and last > expected_day):
                raise SourceDateMismatch("Daily supply dates exceed archive date")
            comparisons = [(c, label, _comparison(label, days)) for c, label in changes]
            for row in range(11, end + 1):
                variations = []
                for col, label, (current, previous) in comparisons:
                    cell = get(row, col)
                    value = _number(cell)
                    # Proven native styles; a literal/escaped percent or arbitrary
                    # custom format must not silently alter the numeric scale.
                    if value is not None and not re.fullmatch(
                        r"0(?:\.0+)?%", cell.number_format
                    ):
                        raise ValueError("Unsupported daily supply percentage format")
                    variations.append(
                        {
                            "source_cell": cell.coordinate,
                            "source_locator": f"{sheet.title}!row {row},col {col}",
                            "comparison_label": label,
                            "observed_on": current.isoformat(),
                            "compared_on": previous.isoformat(),
                            "value": value * 100 if value is not None else None,
                            "unit": "percentage_points",
                            "literal_value": value,
                            "number_format": cell.number_format,
                        }
                    )
                for col, day in dated:
                    cell = get(row, col)
                    amount = _number(cell)
                    if amount is not None and amount < 0:
                        raise ValueError(
                            "Negative daily supply quantity at " + cell.coordinate
                        )
                    details = {
                        "statistic": "daily_market_arrivals",
                        "quantity_tonnes": amount,
                        "unit": "t",
                        "source_unit": "Toneladas",
                        "literal_value": amount,
                        "number_format": cell.number_format,
                        "availability": "not_reported"
                        if amount is None
                        else "reported",
                        "aggregation_level": "reported_markets_total"
                        if row == 11
                        else "market_total",
                        "market_count": market_count,
                        "provisional": True,
                        "provisional_note": clean(get(end + 2).value),
                        "non_additive": True,
                        "extraction_method": "native-workbook-cells",
                        "parser_version": VERSION,
                        "sheet": sheet.title,
                        "cell": cell.coordinate,
                        "row": row,
                        "column": col,
                        "date_cell": get(9, col).coordinate,
                        "unit_cell": get(10, col).coordinate,
                        "market_cell": get(row).coordinate,
                        "coverage_caption": clean(get(5).value),
                        "period_start": first.isoformat(),
                        "period_end": last.isoformat(),
                    }
                    if day == last:
                        details["variations"] = variations
                    out.append(
                        {
                            "source_locator": f"{sheet.title}!row {row},col {col}; {VERSION}",
                            "kind": KIND,
                            "observed_on": day,
                            "name": clean(get(row).value),
                            "category": "Abastecimiento diario — totales de mercado",
                            "details": details,
                        }
                    )
    finally:
        book.close()
    return out


def publish_rows(db, rows, document_id):
    """Idempotently retain source cells; deliberately no supply/price projection."""
    if not rows:
        return 0
    with db.cursor() as cur:
        cur.executemany(
            """INSERT INTO input_reference_row
            (document_id,source_locator,kind,observed_on,name,category,details)
            VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            [
                (
                    document_id,
                    r["source_locator"],
                    r["kind"],
                    r["observed_on"],
                    r["name"],
                    r["category"],
                    Jsonb(r["details"]),
                )
                for r in rows
            ],
        )
    return len(rows)

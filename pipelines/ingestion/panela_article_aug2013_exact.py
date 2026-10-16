"""Native exact-original extraction for the three Aug. 2013 panela article tables.

These 60 single-price article cells remain separate from the weekly Cuadro 8
min/max/mean table and from Gráfico 8. Source identity, page count, captions,
periods, units, week headings, geometry, row count and price-cell positions all
fail closed. No OCR, network, database, or pipeline integration is performed.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO

import pdfplumber

ORIGINAL_SHA = "5a8af3b10894d3241907e149a39451d09488bf827d79b52d3789e5a8cfa60f4d"
SOURCE_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_20ago_23ago_2013.pdf"
ARTICLE_PERIOD = "2013 (20 de julio al 23 de agosto)"
UNIT_LITERAL = "Precios por kilo"
WEEKS = (
    (date(2013, 7, 20), date(2013, 7, 26)),
    (date(2013, 7, 27), date(2013, 8, 2)),
    (date(2013, 8, 3), date(2013, 8, 9)),
    (date(2013, 8, 10), date(2013, 8, 16)),
    (date(2013, 8, 17), date(2013, 8, 23)),
)
WEEK_LABELS = ("20 al 26", "27 al 2 de agosto", "3 al 9", "10 al 16", "17 al 23")
MONEY = re.compile(r"^[1-9][0-9]?\.[0-9]{3}$")


@dataclass(frozen=True)
class Table:
    page: int
    number: int
    product: str
    title: str
    title_y: float
    title_x_min: float
    title_x_max: float
    period_y: float
    month_y: float
    markets_y: float
    name_x_min: float
    name_x_max: float
    money_x: tuple[float, ...]
    # Each row is (price/market continuation line, preceding market-name line).
    rows: tuple[tuple[float, float | None], ...]
    table_x_max: float
    month_tokens: tuple[tuple[str, float], ...]


TABLES = (
    Table(43, 1, "panela cuadrada morena",
          "Tabla 1. Precios por kilo de la panela cuadrada morena",
          602.3, 33.5, 307.0, 613.1, 636.8, 645.6, 34.0, 116.0,
          (122.7, 160.7, 193.7, 229.7, 266.7),
          ((684.0, 674.0), (694.0, None), (714.0, 704.0),
           (724.0, None), (734.0, None)), 305.0,
          (("Julio", 124.8), ("Julio", 157.7), ("Agosto", 229.4))),
    Table(44, 2, "panela cuadrada blanca",
          "Tabla 2. Precios por kilo de la panela cuadrada blanca",
          264.1, 33.5, 307.0, 274.9, 298.7, 307.4, 34.0, 116.0,
          (122.6, 160.6, 193.6, 229.6, 266.6),
          ((335.8, None), (345.8, None), (355.8, None),
           (365.8, None), (375.8, None), (385.8, None)), 305.0,
          (("Julio", 124.7), ("Julio", 157.6), ("Agosto", 229.4))),
    Table(44, 3, "panela redonda morena",
          "Tabla 3. Precios por kilo de la panela redonda morena",
          356.2, 312.0, 590.0, 367.0, 390.7, 399.4, 312.0, 397.0,
          (401.1, 439.1, 472.1, 508.1, 545.1),
          ((437.9, 427.9),), 590.0,
          (("Julio", 403.2), ("Julio", 436.1), ("Agosto", 507.8))),
)


def _at(words: list[dict], y: float, x_min: float, x_max: float) -> list[dict]:
    return sorted((w for w in words if abs(w["top"] - y) < 0.35
                   and x_min <= w["x0"] < x_max), key=lambda w: w["x0"])


def _line(words: list[dict], y: float, x_min: float, x_max: float) -> str:
    return " ".join(w["text"] for w in _at(words, y, x_min, x_max))


def _week_headers(words: list[dict], table: Table) -> tuple[str, ...]:
    first_row_top = table.rows[0][1] if table.rows[0][1] is not None else table.rows[0][0]
    left = table.money_x[0] - 19
    edges = [left]
    edges.extend((a + b) / 2 for a, b in zip(table.money_x, table.money_x[1:]))
    edges.append(table.money_x[-1] + 18)
    result = []
    for column in range(5):
        tokens = [w for w in words
                  if edges[column] <= w["x0"] < edges[column + 1]
                  and table.month_y - 2 < w["top"] < first_row_top - 6
                  and w["text"] not in {"Julio", "Agosto"}]
        tokens.sort(key=lambda w: (w["top"], w["x0"]))
        result.append(" ".join(w["text"] for w in tokens))
    return tuple(result)


def _header(words: list[dict], table: Table) -> None:
    title = _line(words, table.title_y, table.title_x_min, table.title_x_max)
    if title != table.title or UNIT_LITERAL not in title:
        raise ValueError(f"Printed article title/unit changed: page {table.page}, table {table.number}")
    if _line(words, table.period_y, table.title_x_min, table.title_x_max) != ARTICLE_PERIOD:
        raise ValueError(f"Printed article period changed: page {table.page}, table {table.number}")
    if _line(words, table.markets_y, table.name_x_min, table.name_x_max) != "Mercados":
        raise ValueError(f"Printed article market heading changed: table {table.number}")
    for expected, x in table.month_tokens:
        found = [w for w in words if w["text"] == expected
                 and abs(w["top"] - table.month_y) < 0.5 and abs(w["x0"] - x) < 1.5]
        if len(found) != 1:
            raise ValueError(f"Printed article month heading/geometry changed: table {table.number}")
    headers = _week_headers(words, table)
    if headers != WEEK_LABELS:
        raise ValueError(f"Printed article week columns changed: table {table.number}: {headers}")


def _table_rows(words: list[dict], table: Table) -> list[dict]:
    _header(words, table)
    cells = []
    for row_index, (price_y, prefix_y) in enumerate(table.rows, 1):
        row_words = _at(words, price_y, table.name_x_min, table.table_x_max)
        prefix = [] if prefix_y is None else _at(words, prefix_y, table.name_x_min, table.table_x_max)
        market_words = prefix + [w for w in row_words if w["x0"] < table.name_x_max]
        market = " ".join(w["text"] for w in market_words)
        prices = [w for w in row_words if w["x0"] >= table.money_x[0] - 2]
        if not market or len(prices) != 5 or any(not MONEY.fullmatch(w["text"]) for w in prices):
            raise ValueError(f"Incomplete article price row: table {table.number}, row {row_index}")
        for column, (word, anchor, (start, end)) in enumerate(zip(prices, table.money_x, WEEKS), 1):
            if abs(word["x0"] - anchor) > 1.5:
                raise ValueError(f"Article price column moved: table {table.number}, row {row_index}")
            cells.append({
                "source_sha256": ORIGINAL_SHA,
                "source_url": SOURCE_URL,
                "source_page": table.page,
                "source_table": table.number,
                "source_row": row_index,
                "source_column": column,
                "source_locator": f"PDF page {table.page}, Tabla {table.number}, row {row_index}, week {column}",
                "series": "panela_article_single_price",
                "product_literal": table.product,
                "market_literal": market,
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "unit_literal": UNIT_LITERAL,
                "currency": "COP",
                "price_literal": word["text"],
                "price_cop_per_kg": int(word["text"].replace(".", "")),
            })
    return cells


def extract(body: bytes, source_url: str = SOURCE_URL) -> list[dict]:
    if source_url != SOURCE_URL or hashlib.sha256(body).hexdigest() != ORIGINAL_SHA:
        raise ValueError("Exact Aug 2013 panela article original changed")
    with pdfplumber.open(BytesIO(body)) as pdf:
        if len(pdf.pages) != 44:
            raise ValueError("Aug 2013 source page count changed")
        words = {43: pdf.pages[42].extract_words(), 44: pdf.pages[43].extract_words()}
    cells = [cell for table in TABLES for cell in _table_rows(words[table.page], table)]
    if len(cells) != 60 or len({cell["source_locator"] for cell in cells}) != 60:
        raise ValueError("Aug 2013 article cell coverage changed")
    if [sum(cell["source_table"] == n for cell in cells) for n in (1, 2, 3)] != [25, 30, 5]:
        raise ValueError("Aug 2013 article table cell distribution changed")
    return cells

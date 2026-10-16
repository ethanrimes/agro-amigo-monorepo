"""Native, exact-original extraction for the Aug 9–15 2014 panela tables.

These are single published article prices, separate from weekly Cuadro 8
min/max/mean quotes and from the adjacent plotted chart. This source-bound adapter
fails closed on source identity, printed titles, periods, table geometry, and
the fixed native PDF coordinates and exact printed headings.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO

import pdfplumber

ORIGINAL_SHA = "b6558d09580b038bbc077dc02475eb0d6a22ef32bb5979ba5b5a271e22148442"
SOURCE_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_11ago_15ago_2014.pdf"
ARTICLE_PERIOD = "2014 (12 de julio al 15 de agosto)"
UNIT_LITERAL = "Precios por kilo"
WEEKS = (
    (date(2014, 7, 12), date(2014, 7, 18)),
    (date(2014, 7, 19), date(2014, 7, 25)),
    (date(2014, 7, 26), date(2014, 8, 1)),
    (date(2014, 8, 2), date(2014, 8, 8)),
    (date(2014, 8, 9), date(2014, 8, 15)),
)
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
    rows: tuple[tuple[float, float | None], ...]
    table_x_max: float


TABLES = (
    Table(43, 2, "panela cuadrada blanca",
          "Tabla 2. Precios por kilo de la panela cuadrada blanca",
          617.8, 33.5, 307.0, 628.6, 648.4, 655.4, 34.0, 116.0,
          (122.7, 160.7, 193.7, 229.7, 266.7),
          ((687.5, 677.5), (697.5, None), (707.5, None),
           (717.5, None), (727.5, None), (737.5, None)), 305.0),
    Table(44, 3, "panela cuadrada morena",
          "Tabla 3. Precios por kilo de la panela cuadrada morena",
          385.2, 33.5, 307.0, 396.0, 415.8, 422.8, 34.0, 116.0,
          (122.7, 160.7, 193.7, 229.7, 266.7),
          ((454.9, 444.9), (464.9, None), (484.9, 474.9),
           (494.9, None), (504.9, None)), 305.0),
    Table(44, 4, "panela redonda morena",
          "Tabla 4. Precios por kilo de la panela redonda morena",
          433.2, 311.8, 602.0, 444.0, 463.8, 470.8, 312.0, 397.0,
          (401.1, 439.1, 472.1, 508.1, 545.1),
          ((502.9, 492.9),), 590.0),
)

WEEK_LABELS = (
    "12 al 18", "19 al 25", "26 de julio al 1 de agosto", "2 al 8", "9 al 15",
)


def _at(words: list[dict], y: float, x_min: float, x_max: float) -> list[dict]:
    return sorted((w for w in words
                   if abs(w["top"] - y) < 0.35 and x_min <= w["x0"] < x_max),
                  key=lambda w: w["x0"])


def _line(words: list[dict], y: float, x_min: float, x_max: float) -> str:
    return " ".join(w["text"] for w in _at(words, y, x_min, x_max))


def _header(words: list[dict], table: Table) -> None:
    title = _line(words, table.title_y, table.title_x_min, table.title_x_max)
    if title != table.title or UNIT_LITERAL not in title:
        raise ValueError(f"Printed article title/unit changed: page {table.page}, table {table.number}")
    period = _line(words, table.period_y, table.title_x_min, table.title_x_max)
    if period != ARTICLE_PERIOD:
        raise ValueError(f"Printed article period changed: page {table.page}, table {table.number}")
    month_x_min = table.money_x[0] + 17
    month_x_max = table.money_x[-1] + 18
    if _line(words, table.month_y, month_x_min, month_x_max) != "Julio Agosto":
        raise ValueError(f"Printed article month headings changed: table {table.number}")
    if _line(words, table.markets_y, table.name_x_min, table.name_x_max) != "Mercados":
        raise ValueError(f"Printed article market header changed: table {table.number}")
    data_top = table.rows[0][1] if table.rows[0][1] is not None else table.rows[0][0]
    edges = [table.money_x[0] - 19]
    edges.extend((left + right) / 2 for left, right in zip(table.money_x, table.money_x[1:]))
    edges.append(table.money_x[-1] + 18)
    labels = []
    for col in range(5):
        tokens = [w for w in words
                  if edges[col] <= w["x0"] < edges[col + 1]
                  and table.month_y - 2 < w["top"] < data_top - 6
                  and w["text"] not in {"Julio", "Agosto"}]
        labels.append(" ".join(w["text"] for w in sorted(tokens,
                      key=lambda w: (w["top"], w["x0"]))))
    if tuple(labels) != WEEK_LABELS:
        raise ValueError(f"Printed article week columns changed: table {table.number}: {labels}")


def _table_rows(words: list[dict], table: Table) -> list[dict]:
    _header(words, table)
    cells = []
    for row_index, (money_y, prefix_y) in enumerate(table.rows, 1):
        row_words = _at(words, money_y, table.name_x_min, table.table_x_max)
        prefix = [] if prefix_y is None else _at(
            words, prefix_y, table.name_x_min, table.table_x_max)
        names = prefix + [w for w in row_words if w["x0"] < table.name_x_max]
        market = " ".join(w["text"] for w in names)
        prices = [w for w in row_words if w["x0"] >= table.money_x[0] - 2]
        if not market or len(prices) != 5 or any(not MONEY.fullmatch(w["text"]) for w in prices):
            raise ValueError(f"Incomplete article price row: table {table.number}, row {row_index}")
        for column, (word, anchor, (start, end)) in enumerate(
                zip(prices, table.money_x, WEEKS), 1):
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
        raise ValueError("Exact Aug 2014 panela article original changed")
    with pdfplumber.open(BytesIO(body)) as pdf:
        if len(pdf.pages) != 44:
            raise ValueError("Aug 2014 source page count changed")
        words = {43: pdf.pages[42].extract_words(), 44: pdf.pages[43].extract_words()}
    cells = [cell for table in TABLES for cell in _table_rows(words[table.page], table)]
    if len(cells) != 60 or len({cell["source_locator"] for cell in cells}) != 60:
        raise ValueError("Aug 2014 article cell coverage changed")
    return cells

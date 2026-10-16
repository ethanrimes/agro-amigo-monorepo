"""Exact-original native transcription of the June 2014 panela article.

This returns article cells only. They are not weekly Cuadro min/max/mean rows
and this module does not publish them by itself.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO

import pdfplumber


ORIGINAL_SHA = "7c05255c9634e7f9fec2d482368c69bae544c027d49b20d7c4c99f2ac64f90a9"
SOURCE_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_16jun_20jun_2014.pdf"
WEEKS = (
    (date(2014, 5, 17), date(2014, 5, 23)),
    (date(2014, 5, 24), date(2014, 5, 30)),
    (date(2014, 5, 31), date(2014, 6, 6)),
    (date(2014, 6, 7), date(2014, 6, 13)),
    (date(2014, 6, 14), date(2014, 6, 20)),
)
MONEY = re.compile(r"^[1-9][0-9]?\.[0-9]{3}$")


@dataclass(frozen=True)
class Table:
    page: int
    number: int
    product_literal: str
    title_top: float
    title_x: float
    title: str
    rows: tuple[tuple[float, float | None], ...]
    money_x: tuple[float, ...]
    name_x_min: float
    name_x_max: float


TABLES = (
    Table(43, 2, "panela cuadrada blanca", 627.0, 34.0,
          "Tabla 2. Precios por kilo de la panela cuadrada blanca",
          ((687.4, None), (697.4, None), (707.4, None), (717.4, None),
           (727.4, None), (737.4, None)),
          (122.7, 160.7, 193.7, 229.7, 266.7), 34.0, 115.0),
    Table(44, 3, "panela cuadrada morena", 267.2, 34.0,
          "Tabla 3. Precios por kilo de la panela cuadrada morena",
          ((337.5, 327.5), (347.5, None), (367.5, 357.5),
           (377.5, None), (387.5, None)),
          (122.7, 160.7, 193.7, 229.7, 266.7), 34.0, 115.0),
    Table(44, 4, "panela redonda morena", 343.1, 312.4,
          "Tabla 4. Precios por kilo de la panela redonda morena",
          ((414.2, 404.2),),
          (401.1, 439.1, 472.1, 508.1, 545.1), 312.0, 397.0),
)

# Independently transcribed from the exact page-43/44 table pixels and checked
# against Poppler's separate text-layout engine. Read the native PDF first;
# these literals are a fail-closed oracle, never substitute returned prices.
EXPECTED_GRID = {
    (43, 2): (
        ("Charalá (Santander)", (1406, 1469, 1406, 1344, 1344)),
        ("Güepsa (Santander)", (1175, 1200, 1100, 1100, 1200)),
        ("Moniquirá (Boyacá)", (1350, 1200, 1100, 1175, 1250)),
        ("San Gil (Santander)", (1275, 1275, 1275, 1225, 1225)),
        ("Santana (Boyacá)", (1275, 1225, 1175, 1175, 1225)),
        ("Vélez (Santander)", (1200, 1150, 1150, 1150, 1175)),
    ),
    (44, 3): (
        ("Caparrapí (Cundinamarca)", (1350, 1200, 1200, 1200, 1150)),
        ("Charalá (Santander)", (1281, 1406, 1281, 1219, 1219)),
        ("Nocaima (Cundinamarca)", (1375, 1325, 1225, 1215, 1175)),
        ("San Gil (Santander)", (1275, 1275, 1275, 1225, 1225)),
        ("Villeta (Cundinamarca)", (1356, 1294, 1288, 1250, 1188)),
    ),
    (44, 4): (
        ("Caparrapí (Cundinamarca)", (1350, 1200, 1150, 1150, 1000)),
    ),
}


def _at(words: list[dict], y: float, x_min: float, x_max: float) -> list[dict]:
    return sorted((word for word in words
                   if abs(word["top"] - y) < 0.35 and x_min <= word["x0"] < x_max),
                  key=lambda word: word["x0"])


def _title(words: list[dict], table: Table) -> None:
    title_words = _at(words, table.title_top, table.title_x - 0.5,
                      table.title_x + (275 if table.number == 4 else 265))
    printed = " ".join(word["text"] for word in title_words)
    if printed != table.title:
        raise ValueError(f"Exact panela article title changed: table {table.number}")
    # The printed article heading covers five weeks. Its column headers are
    # verified independently below; the Cuadro's one-week date is not reused.
    heading_y = 353.9 if table.number == 4 else 278.0 if table.number == 3 else 637.8
    heading = _at(words, heading_y, table.title_x - 0.5,
                  table.title_x + 180)
    if " ".join(w["text"] for w in heading) != "2014 (17 de mayo al 20 de junio)":
        raise ValueError(f"Exact panela article five-week period changed: table {table.number}")
    columns_y = 387.8 if table.number == 4 else 311.9 if table.number == 3 else 671.7
    columns = _at(words, columns_y, table.money_x[0] - 4, table.money_x[-1] + 23)
    column_text = " ".join(w["text"] for w in columns)
    if column_text != "17 al 23 24 al 30 7 al 13 14 al 20":
        raise ValueError(f"Exact panela article week columns changed: table {table.number}")
    third_top_y = 373.3 if table.number == 4 else 297.3 if table.number == 3 else 657.2
    third_middle_y = 381.3 if table.number == 4 else 305.3 if table.number == 3 else 665.2
    third_top = _at(words, third_top_y, table.money_x[2] - 4,
                    table.money_x[2] + 35)
    third_middle = _at(words, third_middle_y, table.money_x[2] - 7,
                       table.money_x[2] + 32)
    if (" ".join(w["text"] for w in third_top) != "31 de"
            or " ".join(w["text"] for w in third_middle) != "mayo al 6"):
        raise ValueError(f"Exact panela article third-week date changed: table {table.number}")
    split_y = 389.3 if table.number == 4 else 313.3 if table.number == 3 else 673.2
    split = _at(words, split_y, table.money_x[2] - 1.5, table.money_x[2] + 45)
    if " ".join(w["text"] for w in split) != "de junio":
        raise ValueError(f"Exact panela article third-week heading changed: table {table.number}")


def _extract_table(words: list[dict], table: Table) -> list[dict]:
    _title(words, table)
    expected_rows = EXPECTED_GRID[(table.page, table.number)]
    if len(table.rows) != len(expected_rows):
        raise ValueError("Exact panela article row count changed")
    result = []
    for row_index, (money_y, prefix_y) in enumerate(table.rows, 1):
        row = _at(words, money_y, table.name_x_min, table.money_x[-1] + 43)
        prefix = [] if prefix_y is None else _at(words, prefix_y, table.name_x_min, table.name_x_max)
        names = prefix + [w for w in row if w["x0"] < table.name_x_max]
        name = " ".join(w["text"] for w in names)
        if not name or "(" not in name or ")" not in name:
            raise ValueError(f"Incomplete native market name: table {table.number}, row {row_index}")
        money = [w for w in row if w["x0"] >= table.money_x[0] - 2]
        if len(money) != 5 or any(not MONEY.fullmatch(w["text"]) for w in money):
            raise ValueError(f"Incomplete native panela prices: table {table.number}, row {row_index}")
        expected_name, expected_prices = expected_rows[row_index - 1]
        if name != expected_name:
            raise ValueError(f"Exact panela article market changed: table {table.number}, row {row_index}")
        parsed_prices = tuple(int(word["text"].replace(".", "")) for word in money)
        if parsed_prices != expected_prices:
            raise ValueError(f"Exact panela article price vector changed: table {table.number}, row {row_index}")
        for column_index, (word, anchor, (start, end)) in enumerate(zip(money, table.money_x, WEEKS), 1):
            if abs(word["x0"] - anchor) > 1.5:
                raise ValueError(f"Native panela price column moved: table {table.number}, row {row_index}")
            result.append({
                "source_sha256": ORIGINAL_SHA,
                "source_url": SOURCE_URL,
                "source_page": table.page,
                "source_table": table.number,
                "source_row": row_index,
                "source_column": column_index,
                "source_locator": f"PDF page {table.page}, Tabla {table.number}, row {row_index}, week {column_index}",
                "series": "panela_article_single_price",
                "product_literal": table.product_literal,
                "market_literal": name,
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "unit_literal": "Precios por kilo",
                "currency": "COP",
                "price_literal": word["text"],
                "price_cop_per_kg": int(word["text"].replace(".", "")),
            })
    return result


def extract(body: bytes, source_url: str = SOURCE_URL) -> list[dict]:
    if source_url != SOURCE_URL or hashlib.sha256(body).hexdigest() != ORIGINAL_SHA:
        raise ValueError("Panela article source identity changed")
    with pdfplumber.open(BytesIO(body)) as pdf:
        if len(pdf.pages) != 44:
            raise ValueError("Panela article PDF page count changed")
        words_by_page = {43: pdf.pages[42].extract_words(),
                         44: pdf.pages[43].extract_words()}
    rows = [cell for table in TABLES
            for cell in _extract_table(words_by_page[table.page], table)]
    if len(rows) != 60 or len({row["source_locator"] for row in rows}) != 60:
        raise ValueError("Panela article cell coverage changed")
    return rows

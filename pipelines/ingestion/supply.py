"""Stream dated DANE arrivals into permanent monthly supply snapshots."""

import io
import math
import re
from array import array
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from functools import lru_cache
from xml.etree.ElementTree import iterparse

import openpyxl
from openpyxl.worksheet._reader import WorkSheetParser
from psycopg.types.json import Jsonb

from pipelines.ingestion.worker import clean, slug, today


class _RowRanges(Sequence):
    """Exact worksheet row ranges, with two uint32 values per range in memory."""

    __slots__ = ("_pairs",)

    def __init__(self):
        self._pairs = array("I")

    def add(self, row):
        if self._pairs and row == self._pairs[-1] + 1:
            self._pairs[-1] = row
        else:
            self._pairs.extend((row, row))

    def __len__(self):
        return len(self._pairs) // 2

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        index = range(len(self))[index]
        return [self._pairs[2 * index], self._pairs[2 * index + 1]]

    def __eq__(self, other):
        if not isinstance(other, Sequence):
            return NotImplemented
        return len(self) == len(other) and all(a == b for a, b in zip(self, other))


def _supply_rows(sheet):
    """Stream values without retaining openpyxl's per-row formatting metadata.

    Keep openpyxl's cell decoder for shared strings, cached formulas and Excel
    date styles. Its normal read-only iterator still accumulates row dimensions
    and empty XML elements for heavily formatted million-row worksheets.
    """
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    width = sheet.max_column or 0
    with sheet._get_source() as source:
        parser = WorkSheetParser(
            source,
            sheet._shared_strings,
            data_only=True,
            epoch=sheet.parent.epoch,
            date_formats=sheet.parent._date_formats,
            timedelta_formats=sheet.parent._timedelta_formats,
        )
        sheet_data = None
        for event, element in iterparse(source, events=("start", "end")):
            if event == "start" and element.tag == namespace + "sheetData":
                sheet_data = element
            elif event == "end" and element.tag == namespace + "row":
                rownum, cells = parser.parse_row(element)
                parser.row_dimensions.clear()
                width = max(width, max((cell["column"] for cell in cells), default=0))
                values = [None] * width
                for cell in cells:
                    values[cell["column"] - 1] = cell["value"]
                element.clear()
                if sheet_data is not None:
                    sheet_data.clear()
                yield rownum, values


def _source_rows(group):
    # Expand only the one group being copied; stored JSON stays unchanged.
    return {sheet: list(ranges) for sheet, ranges in group["rows"].items()}


def _supply_day(value, reporting_year):
    """Read DANE day/month/year text without guessing the two-digit century."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = clean(value)
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})", text)
    if match:
        day, month, year = match.groups()
        if len(year) == 2:
            if reporting_year is None or reporting_year % 100 != int(year):
                raise ValueError("Two-digit date does not match the reporting year")
            year = reporting_year
        return date(int(year), int(month), int(day))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return date.fromisoformat(text)
    return None


def parse_supply(data):
    groups = {}
    read_day = lru_cache(maxsize=512)(_supply_day)
    cutoff = today()
    book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    source = None
    try:
        for sheet in book:
            source = _supply_rows(sheet)
            header = None
            years = set()
            if re.fullmatch(r"(?:19|20)\d{2}", clean(sheet.title)):
                years.add(int(sheet.title))
            for rownum, row in source:
                for cell in row:
                    years.update(
                        int(y)
                        for y in re.findall(
                            r"\ba[nñ]o\s+((?:19|20)\d{2})\b", clean(cell), re.IGNORECASE
                        )
                    )
                columns = {clean(v): i for i, v in enumerate(row) if clean(v)}
                market = next(
                    (
                        columns[n]
                        for n in [
                            "Ciudad, Mercado Mayorista",
                            "Cuidad, Mercado Mayorista",
                        ]
                        if n in columns
                    ),
                    None,
                )
                if market is not None and all(
                    n in columns for n in ["Fecha", "Alimento", "Cant Kg", "Grupo"]
                ):
                    header = columns
                    break
                if rownum >= 20:
                    break
            if header is None:
                source.close()
                continue
            reporting_year = next(iter(years)) if len(years) == 1 else None
            for rownum, row in source:
                value = row[header["Fecha"]]
                try:
                    day = read_day(value, reporting_year)
                except ValueError as error:
                    raise ValueError(
                        f"Invalid supply date {sheet.title}:{rownum}: {error}"
                    ) from error
                if day is None:
                    if (
                        clean(value) != "Fecha"
                        and clean(row[market])
                        and clean(row[header["Alimento"]])
                    ):
                        raise ValueError(f"Invalid supply date {sheet.title}:{rownum}")
                    continue
                if day > cutoff:
                    continue
                quantity = row[header["Cant Kg"]]
                food = row[header["Alimento"]]
                if (
                    not row[market]
                    or not food
                    or not isinstance(quantity, (int, float))
                    or isinstance(quantity, bool)
                    or not math.isfinite(quantity)
                    or quantity < 0
                ):
                    raise ValueError(f"Invalid supply row {sheet.title}:{rownum}")
                key = (clean(row[market]), clean(food), day.replace(day=1))
                g = groups.get(key)
                if g is None:
                    g = groups[key] = {
                        "kg": 0,
                        "days": set(),
                        "category": clean(row[header["Grupo"]]),
                        "rows": defaultdict(_RowRanges),
                    }
                g["kg"] += quantity
                g["days"].add(day)
                g["rows"][sheet.title].add(rownum)
    finally:
        if source is not None:
            source.close()
        book.close()
    if not groups:
        raise ValueError("No supply microdata parsed")
    return groups


def publish_supply(db, data, did):
    groups = parse_supply(data)
    products = {
        slug(n): pid for pid, n in db.execute("SELECT id,name FROM product").fetchall()
    }
    places = db.execute("SELECT id,name,department FROM municipality").fetchall()
    aliases = {
        "bogota": "bogota-d-c",
        "santafe-de-bogota-d-c": "bogota-d-c",
        "cucuta": "san-jose-de-cucuta",
        "buga": "guadalajara-de-buga",
        "cartagena": "cartagena-de-indias",
        "cali": "santiago-de-cali",
    }
    with db.transaction():
        with db.cursor() as cur:
            for market in sorted({k[0] for k in groups}):
                city = market.split(",")[0]
                key = aliases.get(slug(city), slug(city))
                found = [r for r in places if slug(r[1]) == key]
                municipality, name, department = (
                    found[0] if len(found) == 1 else (None, city, "")
                )
                cur.execute(
                    "INSERT INTO market(id,name,city,region,municipality_id) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING",
                    ("sipsa-" + slug(market), market, name, department, municipality),
                )
            cur.execute(
                "CREATE TEMP TABLE supply_stage (LIKE supply_observation) ON COMMIT DROP"
            )
            with cur.copy("COPY supply_stage FROM STDIN") as copy:
                for (market, food, period), g in groups.items():
                    copy.write_row(
                        (
                            "sipsa-" + slug(market),
                            slug(food),
                            food,
                            products.get(slug(food)),
                            g["category"],
                            period,
                            max(g["days"]),
                            min(g["days"]),
                            g["kg"],
                            len(g["days"]),
                            did,
                            Jsonb(_source_rows(g)),
                        )
                    )
            cur.execute("""INSERT INTO supply_observation SELECT * FROM supply_stage
                ON CONFLICT(market_id,food_id,period_start) DO UPDATE SET
                observed_on=excluded.observed_on,first_reported_on=excluded.first_reported_on,
                quantity_kg=excluded.quantity_kg,reporting_days=excluded.reporting_days,
                document_id=excluded.document_id,source_rows=excluded.source_rows
                WHERE (supply_observation.quantity_kg,supply_observation.document_id) IS DISTINCT FROM (excluded.quantity_kg,excluded.document_id)""")
    return len(groups)

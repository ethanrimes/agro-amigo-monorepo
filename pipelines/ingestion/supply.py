"""Stream dated DANE arrivals into permanent monthly supply snapshots."""

import io
import math
import re
from array import array
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from functools import lru_cache
from urllib.parse import urlparse
from xml.etree.ElementTree import iterparse

import openpyxl
from openpyxl.worksheet._reader import WorkSheetParser
from psycopg.types.json import Jsonb

from pipelines.ingestion.worker import clean, slug, today


def discover_supply_sources(db, url):
    """Queue microdata and retain published summaries without double-counting them.

    Year pages are independent bounded index jobs, so routine discovery never
    downloads fourteen archive pages before it can reach current publications.
    Summary workbooks/PDFs describe market totals, groups, shares and vehicles;
    they must not be projected as individual-food microdata observations.
    """
    from .worker import SUPPLY, links, publication_month, queue

    count = 0
    seen = set()
    from .dane_context import queue_context_sources

    entries = links(url)
    count += queue_context_sources(db, entries)
    for label, link in entries:
        parsed = urlparse(link)
        if parsed.hostname not in ("www.dane.gov.co", "dane.gov.co"):
            continue
        path = parsed.path.lower()
        index = re.search(
            r"/componente-abastecimientos-boletin-quincenal-(20\d{2})(?:-\d+)*$",
            path,
        )
        if index:
            # Joomla exposes the same year page under several parent routes.
            # The main supply page's canonical parent prevents duplicate jobs.
            link = SUPPLY + "/" + parsed.path.rsplit("/", 1)[-1]
        if link in seen:
            continue
        seen.add(link)
        if index:
            year = int(index[1])
            if (
                year <= today().year
                and parsed.path.rsplit("/", 1)[-1]
                != urlparse(url).path.rsplit("/", 1)[-1]
            ):
                queue(db, link, "supply-index", date(year, 1, 1))
                count += 1
            continue
        if "/files/" not in path or not path.endswith((".xlsx", ".xls", ".pdf")):
            continue
        if re.search(r"microdato-abastecimiento-20\d{2}\.xlsx$", path):
            kind, day = "supply", None
        elif "series-historicas-abastecimiento" in path and path.endswith(
            (".xlsx", ".xls")
        ):
            kind, day = "supply-reference", None
        else:
            filename = path.rsplit("/", 1)[-1]
            if not (filename.startswith(("bol", "anex")) and "abas" in filename):
                continue
            kind = (
                "supply-reference-pdf" if path.endswith(".pdf") else "supply-reference"
            )
            # Quincenal files are partial periods; do not label them with an
            # invented month-end observation date (or a guessed two-digit year).
            day = None if "quin" in filename else publication_month(label, link)
            if day and day > today():
                day = None
        queue(db, link, kind, day)
        count += 1
    if not count:
        raise ValueError("No supported supply publications discovered: " + url)
    return count


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
    revision = db.execute(
        "SELECT retrieved_at FROM source_document WHERE id=%s", (did,)
    ).fetchone()
    if not revision or revision[0] is None:
        raise ValueError("Supply publication requires a retained source timestamp")
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
            columns = (
                "market_id,food_id,food_name,product_id,category,period_start,"
                "observed_on,first_reported_on,quantity_kg,reporting_days,"
                "document_id,source_rows"
            )
            with cur.copy(f"COPY supply_stage ({columns}) FROM STDIN") as copy:
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
            # Keep the whole document atomic while bounding each INSERT to one
            # source month. Existing retention triggers preserve every previous
            # published tuple, including changed metadata or equal-value evidence.
            cur.execute("CREATE INDEX ON supply_stage(period_start)")
            for period in sorted({key[2] for key in groups}):
                cur.execute(
                    f"""INSERT INTO supply_observation ({columns})
                SELECT {columns} FROM supply_stage WHERE period_start=%s
                ON CONFLICT(market_id,food_id,period_start) DO UPDATE SET
                food_name=excluded.food_name,product_id=excluded.product_id,
                category=excluded.category,
                observed_on=excluded.observed_on,first_reported_on=excluded.first_reported_on,
                quantity_kg=excluded.quantity_kg,reporting_days=excluded.reporting_days,
                document_id=excluded.document_id,source_rows=excluded.source_rows
                WHERE (supply_observation.food_name,supply_observation.product_id,
                       supply_observation.category,supply_observation.observed_on,
                       supply_observation.first_reported_on,supply_observation.quantity_kg,
                       supply_observation.reporting_days,supply_observation.document_id,
                       supply_observation.source_rows)
                  IS DISTINCT FROM (excluded.food_name,excluded.product_id,
                       excluded.category,excluded.observed_on,excluded.first_reported_on,
                       excluded.quantity_kg,excluded.reporting_days,excluded.document_id,
                       excluded.source_rows)
                  AND %s::timestamptz >= (SELECT retrieved_at FROM source_document
                      WHERE id=supply_observation.document_id)""",
                    (period, revision[0]),
                )
    return len(groups)

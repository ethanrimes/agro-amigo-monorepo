"""FNC price series with explicit periods, units and purchasing/benchmark bases.

Volumes, cultivated area and total harvest values are context, never unit prices.
The worker retains the original and publishes these rows as official references.
"""

from __future__ import annotations

import calendar
import io
import math
import re
from datetime import date, datetime

import openpyxl
from pypdf import PdfReader

VERSION = "coffee-prices-v1"
PUBLISHERS = {"coffee": "FNC", "coffee-pdf": "FNC"}
COFFEE_YEAR_DEFINITION = (
    "https://cauca.federaciondecafeteros.org/glosario/ano-cafetero/"
)


def _amount(value, locator):
    if (
        value
        == "Cambio en sistema de compra de almendra sana por factor de rendimiento"
    ):
        return None  # Explicit structural notice in the original, not a price.
    if value is None or str(value).strip() in {"", "-", "...", "..", "n.d.", "ND"}:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Unrecognized FNC price at {locator}: {value!r}")  # noqa: TRY004 -- malformed source values use the ingestion review path
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"Invalid FNC price at {locator}")
    return float(value) if value > 0 else None


def _day(value):
    return value.date() if isinstance(value, datetime) else value


def _month(value):
    start = _day(value).replace(day=1)
    return start, start.replace(day=calendar.monthrange(start.year, start.month)[1])


def _quote(
    *,
    series,
    name,
    market,
    basis,
    currency,
    unit,
    day,
    start,
    value,
    locator,
    url,
    frequency,
    literal_unit,
    cents=False,
    **details,
):
    return {
        "product_id": series,
        "product_name": name,
        "category": "Café",
        "publisher": "FNC",
        "series": series,
        "basis": basis,
        "currency": currency,
        "unit": unit,
        "market": market,
        "date": day,
        "period_start": start,
        "price": value / 100 if cents else value,
        "source_locator": locator,
        "details": {
            "source_url": url,
            "frequency": frequency,
            "literal_price": value,
            "literal_unit": literal_unit,
            "normalization": "US cents divided by 100 to USD" if cents else "none",
            **details,
        },
    }


def parse_workbook(data, url, *, as_of):
    book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    quotes = []
    sheets = {}
    try:
        for sheet in book:
            number = re.match(r"\s*([1-6])\.", sheet.title)
            if number and "precio" in sheet.title.lower():
                key = int(number[1])
                if key in sheets:
                    raise ValueError(f"Duplicate FNC price sheet {key}")
                sheets[key] = sheet
        if set(sheets) != set(range(1, 7)):
            raise ValueError("FNC workbook lacks one of its six native price sheets")
        for number, sheet in sheets.items():
            # Some FNC sheets report 16,383 formatted columns with only five
            # populated data columns. Never materialize that empty grid.
            rows = list(sheet.iter_rows(max_col=15, values_only=True))
            headings = " ".join(str(v) for row in rows[:7] for v in row if v)
            if number == 1:
                if not all(
                    v in headings
                    for v in ("125 Kg", "Almendra Sana", "Incentivo a la Calidad")
                ):
                    raise ValueError("FNC daily price headers changed")
                columns = (
                    (
                        2,
                        "fnc-internal-daily",
                        "Café pergamino seco · referencia diaria FNC",
                        "125kg",
                        "Precio interno base de compra FoNC por carga de café pergamino seco",
                    ),
                    (
                        3,
                        "fnc-sound-bean-daily",
                        "Café · almendra sana",
                        "kg",
                        "Precio de compra por kilogramo de almendra sana",
                    ),
                    (
                        4,
                        "fnc-quality-incentive-daily",
                        "Café · incentivo a la calidad",
                        "kg",
                        "Bonificación por calidad; no es el precio total del café",
                    ),
                )
                for rownum, row in enumerate(rows, 1):
                    if not isinstance(row[1], (date, datetime)):
                        continue
                    day = _day(row[1])
                    if day > as_of:
                        continue
                    for col, series, name, unit, basis in columns:
                        locator = f"{sheet.title}!row {rownum},col {col + 1}"
                        value = _amount(row[col], locator)
                        if value is not None:
                            quotes.append(
                                _quote(
                                    series=series,
                                    name=name,
                                    market="FNC nacional",
                                    basis=basis,
                                    currency="COP",
                                    unit=unit,
                                    day=day,
                                    start=day,
                                    value=value,
                                    locator=locator,
                                    url=url,
                                    frequency="daily",
                                    literal_unit="COP/" + unit,
                                )
                            )
            elif number in (2, 3, 4, 5):
                internal = number == 2
                if (internal and "125 kg" not in headings.lower()) or (
                    not internal and "Centavos de dólar por libra" not in headings
                ):
                    raise ValueError(f"FNC sheet {number} price unit changed")
                for rownum, row in enumerate(rows, 1):
                    label = row[3]
                    if number in (2, 3):
                        if not isinstance(label, (date, datetime)):
                            continue
                        start, day = _month(label)
                        frequency = "monthly"
                    elif number == 4:
                        if not isinstance(label, int) or not 1900 <= label <= 2100:
                            continue
                        start, day = date(label, 1, 1), date(label, 12, 31)
                        frequency = "annual-calendar"
                    else:
                        match = re.fullmatch(r"(\d{4})/(\d{2}|\d{4})", str(label))
                        if not match:
                            continue
                        year = int(match[1])
                        end = (
                            int(match[2])
                            if len(match[2]) == 4
                            else year // 100 * 100 + int(match[2])
                        )
                        if end < year:
                            end += 100
                        if end != year + 1:
                            raise ValueError("FNC coffee-year interval is not one year")
                        start, day = date(year, 10, 1), date(end, 9, 30)
                        frequency = "annual-coffee-year"
                    if day > as_of:
                        continue
                    locator = f"{sheet.title}!row {rownum},col 5"
                    value = _amount(row[4], locator)
                    if value is None:
                        continue
                    series = (
                        "fnc-internal-monthly"
                        if internal
                        else "fnc-exdock-" + frequency
                    )
                    period_name = {
                        "monthly": "mensual",
                        "annual-calendar": "año calendario",
                        "annual-coffee-year": "año cafetero",
                    }[frequency]
                    quotes.append(
                        _quote(
                            series=series,
                            name=(
                                "Café pergamino seco · referencia mensual FNC"
                                if internal
                                else "Café colombiano excelso · ex-dock · "
                                + period_name
                            ),
                            market="FNC nacional"
                            if internal
                            else "FNC · referencia externa ex-dock",
                            basis="Promedio mensual del precio interno base de compra"
                            if internal
                            else "Precio externo ex-dock; promedio " + period_name,
                            currency="COP" if internal else "USD",
                            unit="125kg" if internal else "lb (453.6 g)",
                            day=day,
                            start=start,
                            value=value,
                            locator=locator,
                            url=url,
                            frequency=frequency,
                            literal_unit="COP/125kg"
                            if internal
                            else "US cents/lb (453.6 g)",
                            cents=not internal,
                            source_period_label=str(label),
                            **(
                                {"coffee_year_definition": COFFEE_YEAR_DEFINITION}
                                if number == 5
                                else {}
                            ),
                        )
                    )
            else:
                if "Centavos de dólar por libra" not in headings:
                    raise ValueError("FNC ICO price unit changed")
                groups = {
                    2: (
                        "composite",
                        "Indicador compuesto OIC",
                        "OIC · indicador compuesto",
                    ),
                }
                for col, code, group in (
                    (3, "colombian-milds", "Suaves colombianos (arábigo)"),
                    (6, "other-milds", "Otros suaves (arábigo)"),
                    (9, "brazilian-naturals", "Naturales del Brasil (arábigo)"),
                    (12, "robustas", "Robustas"),
                ):
                    if rows[5][col] != group:
                        raise ValueError("FNC ICO group headers changed")
                    for offset, market in enumerate(
                        ("Nueva York", "Europa", "Promedio ponderado")
                    ):
                        if rows[6][col + offset] != market:
                            raise ValueError("FNC ICO market headers changed")
                        groups[col + offset] = (code, group, "OIC · " + market)
                for rownum, row in enumerate(rows, 1):
                    if not isinstance(row[1], (date, datetime)):
                        continue
                    start, day = _month(row[1])
                    if day > as_of:
                        continue
                    for col, (code, group, market) in groups.items():
                        locator = f"{sheet.title}!row {rownum},col {col + 1}"
                        value = _amount(row[col], locator)
                        if value is not None:
                            quotes.append(
                                _quote(
                                    series="fnc-ico-" + code + "-monthly",
                                    name="Café · " + group + " · " + market,
                                    market=market,
                                    basis="Precio indicativo OIC; promedio mensual, republicado por FNC",
                                    currency="USD",
                                    unit="lb",
                                    day=day,
                                    start=start,
                                    value=value,
                                    locator=locator,
                                    url=url,
                                    frequency="monthly",
                                    literal_unit="US cents/lb",
                                    cents=True,
                                    upstream_publisher="International Coffee Organization",
                                    source_group=group,
                                )
                            )
        if not quotes:
            raise ValueError("No FNC workbook prices parsed")
        return quotes
    finally:
        book.close()


def parse_pdf_extras(data, url, *, as_of):
    reader = PdfReader(io.BytesIO(data))
    text = reader.pages[0].extract_text() or ""
    match = re.search(r"([A-Za-z]+)\s+(\d{1,2})\s*/\s*(20\d{2})", text)
    months = [
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
    if not match or match[1].lower() not in months:
        raise ValueError("FNC PDF publication date missing")
    day = date(int(match[3]), months.index(match[1].lower()) + 1, int(match[2]))
    if day > as_of:
        raise ValueError("FNC PDF publication is in the future")
    external = re.search(r"Cierre contrato C Nueva York\s+([\d,.]+)\s+USCent/Lb", text)
    pasilla = re.search(
        r"Precio total\s+de pasilla contenida en el pergamino\s+([\d,]+)\s+COP/Kg", text
    )
    if not external or not pasilla:
        raise ValueError("FNC PDF external/pasilla native prices missing")
    rows = []
    for series, name, market, basis, value, currency, unit, literal, cents in (
        (
            "fnc-ny-contract-c-daily",
            "Café · cierre contrato C Nueva York",
            "Nueva York · contrato C",
            "Cotización de cierre de futuros contrato C; referencia externa, no precio al productor",
            float(external[1].replace(",", "")),
            "USD",
            "lb",
            "USCent/Lb",
            True,
        ),
        (
            "fnc-pasilla-daily",
            "Café · pasilla contenida en el pergamino",
            "FNC nacional",
            "Precio de pasilla contenida en café pergamino; componente del precio interno",
            float(pasilla[1].replace(",", "")),
            "COP",
            "kg",
            "COP/Kg",
            False,
        ),
    ):
        value = _amount(value, series)
        if value is None:
            raise ValueError("FNC PDF price is zero")
        row = _quote(
            series=series,
            name=name,
            market=market,
            basis=basis,
            currency=currency,
            unit=unit,
            day=day,
            start=day,
            value=value,
            locator="PDF page 1; " + series,
            url=url,
            frequency="daily",
            literal_unit=literal,
            cents=cents,
        )
        row["source_page"] = 1
        rows.append(row)
    return rows


def parse(data, url, kind, *, as_of=None):
    if as_of is None:
        from .worker import today

        as_of = today()
    if kind == "coffee":
        return parse_workbook(data, url, as_of=as_of)
    if kind == "coffee-pdf":
        return parse_pdf_extras(data, url, as_of=as_of)
    raise ValueError("Unsupported FNC source kind")

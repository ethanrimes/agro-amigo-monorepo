"""Input summary ranges, electricity tariffs, and workbook context tables."""

import calendar
import re
from datetime import date

from psycopg.types.json import Jsonb


def extract_reference_rows(db, data, did, day=None):
    from .worker import MONTH_NUM, SourceDateMismatch, clean, positive, today, workbooks

    found = 0
    batch = []

    def flush():
        if batch:
            with db.cursor() as cursor:
                cursor.executemany(
                    """INSERT INTO input_reference_row(document_id,source_locator,kind,observed_on,name,category,details)
                    VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    batch,
                )
            batch.clear()

    for sheet, rows in workbooks(data):
        header = None
        mode = None
        provider = ""
        legacy_period = None
        for row_no, row in enumerate(rows, 1):
            names = [clean(v) for v in row]
            if "Proveedor de servicios y estrato" in names:
                tariff = [
                    (i, re.fullmatch(r"Tarifa (\w+)", v, re.IGNORECASE))
                    for i, v in enumerate(names)
                ]
                tariff = [(i, m) for i, m in tariff if m and m[1].lower() in MONTH_NUM]
                stamp = re.search(
                    r"\b([A-ZÁÉÍÓÚ]+)\s?(20\d{2}|\d{2})$", sheet, re.IGNORECASE
                )
                if (
                    not stamp
                    or len(tariff) != 1
                    or MONTH_NUM.get(stamp[1].lower())
                    != MONTH_NUM[tariff[0][1][1].lower()]
                ):
                    raise ValueError(f"Unverified legacy electricity period: {sheet}")
                year = int(stamp[2]) + (2000 if len(stamp[2]) == 2 else 0)
                month = MONTH_NUM[stamp[1].lower()]
                legacy_period = date(year, month, calendar.monthrange(year, month)[1])
                if day and day != legacy_period:
                    raise SourceDateMismatch(
                        "Electricity table month differs from archive link"
                    )
                header = {v: i for i, v in enumerate(names) if v}
                legacy_tariff_header = names[tariff[0][0]]
                mode = "electricity-legacy"
                provider = ""
                continue
            if "Producto y presentación" in names and "Mínimo precio promedio" in names:
                header = {v: i for i, v in enumerate(names) if v}
                mode = "summary"
                continue
            if "Proveedor de servicios" in names and "Tarifa mes" in names:
                header = {v: i for i, v in enumerate(names) if v}
                mode = "electricity"
                continue
            if not header:
                continue
            values = {name: row[i] for name, i in header.items() if i < len(row)}
            if mode == "electricity-legacy":
                label = values.get("Proveedor de servicios y estrato")
                tariff = values.get(legacy_tariff_header)
                if not positive(tariff):
                    if (
                        isinstance(label, str)
                        and clean(label)
                        and not any(positive(v) for v in row[1:])
                    ):
                        provider = clean(label)
                    continue
                if (
                    not provider
                    or not isinstance(label, (int, float))
                    or label not in range(1, 7)
                ):
                    raise ValueError(
                        f"Unverified electricity provider/stratum: {sheet}, row {row_no}"
                    )
                period, name, category = legacy_period, provider, "Energía eléctrica"
                values.update(
                    {
                        "provider": provider,
                        "stratum": int(label),
                        "extraction_method": "native-workbook-provider-stratum",
                    }
                )
            elif mode == "summary":
                if not positive(values.get("Mínimo precio promedio")) or not positive(
                    values.get("Máximo precio promedio")
                ):
                    continue
                period = day
                name = clean(values.get("Producto y presentación"))
                category = clean(values.get("Grupo"))
                if not period:
                    raise ValueError("Summary workbook has no publication month")
            else:
                year = clean(values.get("Año"))
                month = MONTH_NUM.get(clean(values.get("Mes")).lower())
                if (
                    not re.fullmatch(r"20\d{2}", year)
                    or not month
                    or not positive(values.get("Tarifa mes"))
                ):
                    continue
                period = date(
                    int(year), month, calendar.monthrange(int(year), month)[1]
                )
                name = clean(values.get("Proveedor de servicios"))
                category = "Energía eléctrica"
            if period > today():
                continue
            batch.append(
                (
                    did,
                    f"{sheet}!row {row_no}",
                    "electricity" if mode == "electricity-legacy" else mode,
                    period,
                    name,
                    category,
                    Jsonb(values),
                )
            )
            if len(batch) >= 1000:
                flush()
            found += 1
    flush()
    return found


def context_rows(data):
    """Select the native reader from file bytes, preserving old XLS hyperlinks."""
    import io

    import openpyxl

    from .worker import clean

    if data.startswith(b"\xd0\xcf\x11\xe0"):
        import xlrd

        book = xlrd.open_workbook(file_contents=data)
        try:
            for sheet in book.sheets():
                for row in range(sheet.nrows):
                    links = [
                        link.url_or_path
                        for link in sheet.hyperlink_list
                        if link.frowx <= row <= link.lrowx and link.url_or_path
                    ]
                    yield (
                        sheet.name,
                        row + 1,
                        [clean(v) for v in sheet.row_values(row)],
                        links,
                    )
        finally:
            book.release_resources()
        return
    if not data.startswith(b"PK"):
        raise ValueError("Unrecognized native workbook format")

    book = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    try:
        for sheet in book:
            for number, row in enumerate(sheet, 1):
                yield (
                    sheet.title,
                    number,
                    [clean(c.value) for c in row],
                    [
                        c.hyperlink.target
                        for c in row
                        if c.hyperlink and c.hyperlink.target
                    ],
                )
    finally:
        book.close()


def extract_context(db, data, did):
    """Preserve every populated row and hyperlink of the context workbook."""
    from .worker import queue

    count = 0
    for sheet, number, values, links in context_rows(data):
        if not any(values) and not links:
            continue
        db.execute(
            """INSERT INTO input_reference_row(document_id,source_locator,kind,name,category,details)
                VALUES(%s,%s,'context',%s,'Informes de contexto',%s) ON CONFLICT DO NOTHING""",
            (
                did,
                f"{sheet}!row {number}",
                next((v for v in values if v), sheet),
                Jsonb({"cells": values, "links": links}),
            ),
        )
        for u in links:
            if u.startswith("https://www.dane.gov.co/") and u.lower().endswith(".pdf"):
                queue(db, u, "context-pdf")
        count += 1
    return count

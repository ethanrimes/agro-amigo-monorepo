"""Input summary ranges, electricity tariffs, and workbook context tables."""

import calendar
import re
from datetime import date

from psycopg.types.json import Jsonb


def extract_reference_rows(db, data, did, day=None):
    from .worker import MONTH_NUM, clean, positive, today, workbooks

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
        for row_no, row in enumerate(rows, 1):
            names = [clean(v) for v in row]
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
            if mode == "summary":
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
                    mode,
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


def extract_context(db, data, did):
    """Preserve every populated row and hyperlink of the context workbook."""
    import io

    import openpyxl

    from .worker import clean, queue

    book = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    count = 0
    for sheet in book:
        for number, row in enumerate(sheet, 1):
            values = [clean(c.value) for c in row]
            links = [
                c.hyperlink.target for c in row if c.hyperlink and c.hyperlink.target
            ]
            if not any(values) and not links:
                continue
            db.execute(
                """INSERT INTO input_reference_row(document_id,source_locator,kind,name,category,details)
                VALUES(%s,%s,'context',%s,'Informes de contexto',%s) ON CONFLICT DO NOTHING""",
                (
                    did,
                    f"{sheet.title}!row {number}",
                    next((v for v in values if v), sheet.title),
                    Jsonb({"cells": values, "links": links}),
                ),
            )
            for u in links:
                if u.startswith("https://www.dane.gov.co/") and u.lower().endswith(
                    ".pdf"
                ):
                    queue(db, u, "context-pdf")
            count += 1
    book.close()
    return count

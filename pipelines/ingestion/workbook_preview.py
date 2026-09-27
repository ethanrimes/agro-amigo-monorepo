"""Bounded, read-only previews of immutable source Excel files."""

import io
import math
from datetime import date, datetime

import openpyxl
import xlrd


def preview(data, sheet="", start=1, limit=100):
    start = max(1, min(int(start), 1048576))
    limit = max(1, min(int(limit), 200))

    def value(v, number_format="General"):
        if isinstance(v, (datetime, date)):
            return {"value": v.isoformat(), "type": "date"}
        if isinstance(v, float) and not math.isfinite(v):
            return {"value": str(v), "type": "text"}
        return {
            "value": v,
            "number_format": number_format,
            "type": "number"
            if isinstance(v, (int, float)) and not isinstance(v, bool)
            else "text",
        }

    if data.startswith(b"PK"):
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            names = book.sheetnames
            if sheet and sheet not in names:
                raise ValueError("Worksheet not found")
            s = book[sheet or names[0]]
            total = s.max_row or 0
            columns = min(s.max_column or 1, 100)
            rows = (
                [
                    [value(c.value, c.number_format) for c in row]
                    for row in s.iter_rows(
                        min_row=start,
                        max_row=min(start + limit - 1, total),
                        max_col=columns,
                    )
                ]
                if start <= total
                else []
            )
            return {
                "sheets": names,
                "sheet": s.title,
                "start": start,
                "totalRows": total,
                "totalColumns": s.max_column or 1,
                "displayedColumns": columns,
                "rows": rows,
                "readOnly": True,
            }
        finally:
            book.close()
    book = xlrd.open_workbook(
        file_contents=data, on_demand=True, formatting_info=True
    )
    try:
        names = book.sheet_names()
        if sheet and sheet not in names:
            raise ValueError("Worksheet not found")
        s = book.sheet_by_name(sheet or names[0])
        rows = []
        for n in range(start - 1, min(start + limit - 1, s.nrows)):
            row = []
            for c in s.row(n)[:100]:
                v = (
                    xlrd.xldate.xldate_as_datetime(c.value, book.datemode)
                    if c.ctype == xlrd.XL_CELL_DATE
                    else c.value
                )
                cell_format = book.format_map.get(book.xf_list[c.xf_index].format_key)
                row.append(value(v, cell_format.format_str if cell_format else "General"))
            rows.append(row)
        return {
            "sheets": names,
            "sheet": s.name,
            "start": start,
            "totalRows": s.nrows,
            "totalColumns": s.ncols,
            "displayedColumns": min(s.ncols, 100),
            "rows": rows,
            "readOnly": True,
        }
    finally:
        book.release_resources()

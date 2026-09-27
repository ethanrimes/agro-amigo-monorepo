"""Materialized daily price matrices with cell-level source-quality reviews.

Unknown market labels remain absent. Date exceptions require a reviewed original
hash and independent official publication evidence, never neighboring columns.
"""

import hashlib
import math
from datetime import date, datetime

VERSION = "daily-units-v3"

# Populated only for exact authoritative originals with independent date evidence.
VERIFIED_DATE_RECOVERIES = {
    "09bcafd697b554afe4bac3953bd5459140dcf356b95f70c42bf569beebac3043": {
        "archive_date": "2014-02-11",
        "observation_date": "2014-02-11",
        "printed_heading": "Martes 11 de febrera de 2014",
        "basis": "native_month_typo",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-febrero-de-2014-1",
        "archive_label": "Anexo - 11 de febrero",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_11_2014.pdf",
        "corroborating_sha256": "afde49f7efa5911624b0c9687a87d2679ad4971c25ab6b849454c6592462579a",
        "corroborating_locator": "PDF page 1: printed date and named-market prices",
    },
    "60f8375806bc73d3f64596bbb199248300151f978837d23e8fad68142fbbc57e": {
        "archive_date": "2013-11-13",
        "observation_date": "2013-11-13",
        "printed_heading": "Miércoles 13 de noviembre",
        "basis": "native_year_omitted",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-noviembre-de-2013-1",
        "archive_label": "Anexo - 13 de noviembre",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_noviembre_13_2013.pdf",
        "corroborating_sha256": "710cffdcb2bbf0bd8efc7b71eedb72b07ca26d4d08fdd7f82f4c6c17ab9ed9bc",
        "corroborating_locator": "PDF page 1: printed date and named-market prices",
    },
    "ba1bcc4bca12a82b9bcc25d8005a8a30c18656c4404efb6a4bfbe5729903062f": {
        "archive_date": "2013-09-26",
        "observation_date": "2013-09-26",
        "printed_heading": "Jueves 26 de septiembe de 2013",
        "basis": "native_month_typo",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-septiembre-de-2013-1",
        "archive_label": "Anexo - 26 de septiembre",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_septiembre_26_2013.pdf",
        "corroborating_sha256": "f4a11b500fa47ae7f57972750cb4de3f4efcb56ecde1f0f69d16d09613c80c22",
        "corroborating_locator": "PDF page 1: printed date and named-market prices",
    },
    "3fdf93edbe09ab0319f411ffd1ffd93d80b340b0dbaae27ce4c2b0c61b670d3a": {
        "archive_date": "2013-02-11",
        "observation_date": "2013-02-11",
        "printed_heading": "Lunes 11 de enero de 2013",
        "basis": "native_month_typo",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-febrero-de-2013-1",
        "archive_label": "Anexo - 11 de febrero",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_feb_11_2013.pdf",
        "corroborating_sha256": "d1fc15f9581bb74637a96017f5ef8313e17599b06233dac877aef2c00624bfc8",
        "corroborating_locator": "PDF page 1: printed date and named-market prices",
        "price_disagreements": [
            {
                "product_name": "Zanahoria",
                "market_name": "Cartagena, Bazurto",
                "workbook_price": 1292,
                "companion_pdf_price": 1229,
                "policy": "Preserve literal workbook price; companion prose is not a replacement.",
            }
        ],
    },
    "ad0c02b5ef2edf4fbacdb6b9ce1537d03260236e7dd19dbc52aa2b7048b35ada": {
        "archive_date": "2013-12-06",
        "observation_date": "2013-12-06",
        "printed_heading": "Viernes 6 de noviembre de 2013",
        "basis": "native_month_typo",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-diciembre-de-2013",
        "archive_label": "Anexo - 6 de diciembre",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_diciembre_6_2013.pdf",
        "corroborating_sha256": "58ad7142b079af8a190c7a51d36c4006e674c99d84701cf4a649a97496ae4bcc",
        "corroborating_locator": "PDF page 1: printed date and named-market prices",
    },
    "cf3a0c3e001b5cc867ac43d609afb9aafe9a51eba4c4d638315febe6978d8445": {
        "archive_date": "2012-12-05",
        "observation_date": "2012-12-06",
        "printed_heading": "Jueves 6 de diciembre de 2012",
        "basis": "mislinked_identical_original",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-diciembre-de-2012-1",
        "archive_label": "Anexo - 5 de diciembre",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_anexo_dic_6_2012.xls",
        "corroborating_sha256": "cf3a0c3e001b5cc867ac43d609afb9aafe9a51eba4c4d638315febe6978d8445",
        "corroborating_locator": "All native cells and the official archive dated link",
    },
    "302aa6336d7b53016c2afcf79bdc03499637663effb575341606e1dbb9ebb3f9": {
        "archive_date": "2013-07-12",
        "observation_date": "2013-07-15",
        "printed_heading": "Lunes 15 de julio de 2013",
        "basis": "mislinked_identical_original",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-julio-de-2013-1",
        "archive_label": "Anexo - 12 de julio",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_julio_15_2013.xls",
        "corroborating_sha256": "302aa6336d7b53016c2afcf79bdc03499637663effb575341606e1dbb9ebb3f9",
        "corroborating_locator": "All native cells and the official archive dated link",
    },
    "7e3dd859361ac543fe71f740b9898117ebcefc6b69a9ae2815a94155bc1f7088": {
        "archive_date": "2013-05-20",
        "observation_date": "2013-05-21",
        "printed_heading": "Martes 21 de mayo de 2013",
        "basis": "mislinked_identical_original",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-mayo-de-2013-1",
        "archive_label": "Anexo - 20 de mayo",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_mayo_21_2013.xls",
        "corroborating_sha256": "7e3dd859361ac543fe71f740b9898117ebcefc6b69a9ae2815a94155bc1f7088",
        "corroborating_locator": "All native cells and the official archive dated link",
    },
    "82cc122be75103f787e1e84d92ffee9da227e693c22dfcb7190c8e8430aac3fc": {
        "archive_date": "2014-06-11",
        "observation_date": "2014-06-10",
        "printed_heading": "Martes 10 de junio de 2014",
        "basis": "mislinked_identical_native_cells",
        "archive_url": "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas-junio-de-2014-1",
        "archive_label": "Anexo - 11 de junio",
        "corroborating_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_junio_10_2014.xls",
        "corroborating_sha256": "eb968f3e7bdb8ee9f0e75c06d1fa985fb523039faaf88ec72847df07b127e6ef",
        "corroborating_locator": "All native cells and the official archive dated link",
    },
}


def _publication_day(data, rows, expected_day):
    from .worker import SourceDateMismatch, clean, date_from_text

    headings = [clean(value) for row in rows[:4] for value in row if clean(value)]
    typed = {
        value.date() if isinstance(value, datetime) else value
        for row in rows[:4]
        for value in row
        if isinstance(value, (date, datetime))
    }
    if len(typed) > 1:
        raise SourceDateMismatch("Conflicting typed daily publication dates")
    day = next(iter(typed), None) or date_from_text(" ".join(headings))
    if day == expected_day:
        return day, None, headings
    evidence = VERIFIED_DATE_RECOVERIES.get(hashlib.sha256(data).hexdigest())
    if evidence and evidence["archive_date"] == expected_day.isoformat():
        if evidence["printed_heading"] not in headings:
            raise SourceDateMismatch("Reviewed daily date heading no longer agrees")
        return date.fromisoformat(evidence["observation_date"]), evidence, headings
    if day is None:
        raise ValueError("Daily workbook has no verifiable publication date")
    raise SourceDateMismatch(
        f"Daily link date {expected_day} differs from workbook {day}"
    )


def parse_daily(data, expected_day):
    """Validate the whole original, returning rows, reviews and date evidence.

    Callers must persist ``reviews`` with the original's document id before
    considering the asset complete. A late invalid sheet raises before this
    function returns any prices to the publication layer.
    """
    from .worker import clean, positive, record, unit_for, workbooks

    output, reviews, resolutions = [], [], []
    for sheet, source in workbooks(data):
        rows = list(source)
        if not rows or not any(clean(value) for row in rows for value in row):
            continue
        day, evidence, headings = _publication_day(data, rows, expected_day)
        if evidence and evidence not in resolutions:
            resolutions.append(evidence)
        header = next(
            (
                index
                for index, row in enumerate(rows[:12])
                if sum(clean(value).lower() == "precio" for value in row) >= 3
            ),
            None,
        )
        if header is None:
            raise ValueError("Daily price matrix header not found")
        columns = [
            col
            for col, value in enumerate(rows[header])
            if clean(value).lower() == "precio"
        ]
        market_header = next(
            (
                index
                for index, row in enumerate(rows[:header])
                if row and "precio" in clean(row[0]).lower()
            ),
            header - 1,
        )
        market_cells = {
            col: [
                clean(rows[index][col]) if col < len(rows[index]) else ""
                for index in range(market_header, header)
            ]
            for col in columns
        }
        markets = {
            col: ", ".join(dict.fromkeys(value for value in cells if value))
            for col, cells in market_cells.items()
        }
        for rownum, row in enumerate(rows[header + 1 :], header + 2):
            name = clean(row[0]) if row else ""
            for col in columns:
                raw_price = row[col] if col < len(row) else None
                if not positive(raw_price):
                    continue
                raw_variation = row[col + 1] if col + 1 < len(row) else None
                variation = (
                    float(raw_variation) * 100
                    if isinstance(raw_variation, (int, float))
                    and math.isfinite(raw_variation)
                    else None
                )
                locator = f"{sheet}!row {rownum},col {col + 1}"
                if not name or not markets[col]:
                    reviews.append(
                        {
                            "source_locator": locator,
                            "reason": "Daily price has no explicit "
                            + ("product" if not name else "market")
                            + " header",
                            "record": {
                                "sheet": sheet,
                                "row": rownum,
                                "column": col + 1,
                                "product_name": name,
                                "market_name": markets[col] or None,
                                "price": float(raw_price),
                                "raw_change": raw_variation,
                                "market_header_cells": market_cells[col],
                                "printed_heading_cells": headings,
                                "archive_date": expected_day.isoformat(),
                                "observation_date": day.isoformat(),
                                "parser_version": VERSION,
                            },
                        }
                    )
                    continue
                details = {
                    "predominant_variety": "*" in name,
                    "parser_version": VERSION,
                }
                if evidence:
                    details["date_resolution"] = evidence
                output.append(
                    record(
                        "dane-daily",
                        day,
                        name,
                        markets[col],
                        unit_for(name),
                        raw_price,
                        locator,
                        variation,
                        details,
                    )
                )
    if not output and not reviews:
        raise ValueError("No daily prices parsed")
    return {"rows": output, "reviews": reviews, "date_resolutions": resolutions}

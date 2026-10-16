"""Retain three exact DANE annexes with undeclared dates and units as reviews.

These readable originals emit no price rows. A paired bulletin corroborates
the reporting period, but its unit heading cannot establish units for
unmatched annex rows. The complete source files remain available.
"""

from __future__ import annotations

from hashlib import sha256
import re

import xlrd


BASE = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
VERSION_SUFFIX = ":reviewed-feb2014-period-untyped-v1"
INDEX_SHA = "c9a01cc27f30af72b6bfd857a3bfcaa5a7447add6224d048022323550f7a24aa"
INDEX_URL = "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/mayoristas-boletin-semanal-1/boletin-mayorista-semanal-2014-1"
REVIEW_LOCATOR = "XLS document-level paired-period and undeclared-unit review"
REVIEW_MARKER = "DANE 2014 grouped annex: PDF and index corroborate period; XLS monetary unit undeclared"
PAIRS = {
    BASE + "Anexo_Bol_Semanal_feb8_2014.xls": {
        "xls_sha": "011380f52918f5af902d1742f14182e3258f7bda665bc56df51aeb85f677d33a",
        "xls_size": 446976, "sheet": "Boletin-74", "sheet_rows": 4953,
        "numeric_rows": 4577, "first_money": (1533.0, 1833.0, 1683.0),
        "pdf_url": BASE + "Semana_8feb_14feb_2014.pdf",
        "pdf_sha": "86f30b98b91c8454b8a5f8dc6efdf7af9f82a642a6c8346148a382a378f8a458",
        "period_start": "2014-02-08", "period_end": "2014-02-14",
    },
    BASE + "Anexo_Bol_Semanal_feb15_2014.xls": {
        "xls_sha": "4a0cdfc8e3a6253de3f96b2bf5f8687fff32e704fd01e7fb0867086ae99ac899",
        "xls_size": 447488, "sheet": "Boletin-8", "sheet_rows": 4962,
        "numeric_rows": 4587, "first_money": (1433.0, 1500.0, 1467.0),
        "pdf_url": BASE + "Semana_15feb_21feb_2014.pdf",
        "pdf_sha": "3760aeb4c807d5ff63e4e9f265b4b4c8ec11e23fc4e08a65c43ab24e555a426e",
        "period_start": "2014-02-15", "period_end": "2014-02-21",
    },
    BASE + "Anexo_Bol_Semanal_feb22_2014.xls": {
        "xls_sha": "0c5d68740b40d56b0001ed85b3c46897fb135e3bedc75741802043c0c5117f26",
        "xls_size": 448000, "sheet": "Boletin-13", "sheet_rows": 4973,
        "numeric_rows": 4599, "first_money": (1400.0, 1600.0, 1500.0),
        "pdf_url": BASE + "Semana_22feb_28feb_2014.pdf",
        "pdf_sha": "5352b2308706c3bbdff52726669ac06f37e33d134850b97c69733e4f7da773b1",
        "period_start": "2014-02-22", "period_end": "2014-02-28",
    },
}


def review(db, body: bytes, document_id: str, url: str):
    """Return one unpriced review row for exact originals; None for all others."""
    case = PAIRS.get(url)
    if case is None:
        return None
    if len(body) != case["xls_size"] or sha256(body).hexdigest() != case["xls_sha"]:
        raise ValueError("Reviewed weekly XLS original changed")
    if document_id != case["xls_sha"]:
        raise ValueError("Reviewed weekly XLS document identity changed")
    original = db.execute(
        "SELECT source_url,kind,media_type,metadata,content FROM source_document WHERE id=%s",
        (document_id,),
    ).fetchone()
    if (not original or original[0] != url or original[1] != "original"
            or original[2] != "application/vnd.ms-excel"
            or original[3].get("ingestion_kind") != "dane-weekly-xlsx"
            or sha256(bytes(original[4])).hexdigest() != document_id):
        raise ValueError("Reviewed weekly XLS archived binding changed")
    book = xlrd.open_workbook(file_contents=body)
    if book.nsheets != 1:
        raise ValueError("Reviewed weekly XLS sheet count changed")
    sheet = book.sheet_by_index(0)
    if (sheet.name != case["sheet"] or sheet.nrows != case["sheet_rows"]
            or sheet.ncols != 5
            or sheet.cell_value(0, 0) != "Cuadro 1. Mercados mayoristas. Precios de venta de verduras y hortalizas"
            or list(sheet.row_values(1)[:4]) != ["Productos y mercados", "Precio mínimo", "Precio máximo", "Precio medio"]
            or sheet.cell_value(2, 0) != "Acelga"
            or sheet.cell_value(3, 0) != "Armenia, Mercar"
            or tuple(sheet.row_values(3)[1:4]) != case["first_money"]):
        raise ValueError("Reviewed weekly XLS layout or first source row changed")
    numeric = 0
    for i in range(sheet.nrows):
        for cell in sheet.row(i):
            if cell.ctype == xlrd.XL_CELL_DATE:
                raise ValueError("Reviewed weekly XLS now has a native date")
            if cell.ctype == xlrd.XL_CELL_TEXT and re.search(
                r"\b(?:20\d{2}|febrero|kilogramo|kg|pesos\s+por)\b", cell.value, re.I
            ):
                raise ValueError("Reviewed weekly XLS now has period or unit text")
        if (sheet.cell_value(i, 0) and all(
            sheet.cell(i, j).ctype == xlrd.XL_CELL_NUMBER for j in (1, 2, 3)
        )):
            numeric += 1
    if numeric != case["numeric_rows"]:
        raise ValueError("Reviewed weekly XLS money row count changed")
    paired = db.execute(
        "SELECT source_url,kind,media_type,metadata,content FROM source_document WHERE id=%s",
        (case["pdf_sha"],),
    ).fetchone()
    if (not paired or paired[0] != case["pdf_url"] or paired[1] != "original"
            or paired[2] != "application/pdf"
            or paired[3].get("ingestion_kind") != "dane-weekly-pdf"
            or sha256(bytes(paired[4])).hexdigest() != case["pdf_sha"]):
        raise ValueError("Reviewed weekly paired PDF original unavailable or changed")
    return [{
        "source_locator": REVIEW_LOCATOR,
        "price": None,
        "details": {
            "quality_issue": REVIEW_MARKER,
            "original_sha256": document_id,
            "source_url": url,
            "period_start": case["period_start"],
            "period_end": case["period_end"],
            "period_evidence": "same-row official DANE 2014 index and exact paired PDF monetary-table caption",
            "official_index_sha256": INDEX_SHA,
            "official_index_url": INDEX_URL,
            "paired_pdf_url": case["pdf_url"],
            "paired_pdf_sha256": case["pdf_sha"],
            "native_numeric_rows_untyped": numeric,
            "literal_unit_heading": None,
            "unit_basis": "No unit/date appears in XLS cells; PDF unit does not establish XLS-only rows' units.",
        },
    }]

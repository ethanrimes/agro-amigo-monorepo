"""Private proposal: two page-27 witnessed Aug-2013 egg quotes only."""
from __future__ import annotations

from copy import deepcopy
import hashlib

SOURCE_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_20ago_23ago_2013.pdf"
SOURCE_SHA = "5a8af3b10894d3241907e149a39451d09488bf827d79b52d3789e5a8cfa60f4d"
VERSION_SUFFIX = ":aug2013-huevo-rojo-extra-unit-p27-v1"
EVIDENCE = {
    "source_url": SOURCE_URL,
    "document_id": SOURCE_SHA,
    "narrative_locator": "PDF page 27, Granos, carnes y procesados, narrative paragraph on huevos rojos",
    "narrative_literal": "Para la variedad rojo extra ... la unidad se pagó a $221 y a $200 en las ciudades de Cúcuta y Bucaramanga ...",
    "table_period": "2013 (17 al 23 de agosto)",
    "table_unit_heading_literal": "Pesos por kilogramo",
}
TARGETS = (
    {
        "source_locator": "PDF page 30,table 1,column 2,line 32",
        "market": "Bucaramanga, Centroabastos",
        "literal": 200.0,
    },
    {
        "source_locator": "PDF page 30,table 1,column 2,line 33",
        "market": "Cúcuta, Cenabastos",
        "literal": 221.0,
    },
)


def _is_exact_review(row: dict, target: dict) -> bool:
    details = row.get("details")
    identity = row.get("identity_dimensions")
    return (
        row.get("source_locator") == target["source_locator"]
        and row.get("product_id") == "huevo-rojo-extra"
        and row.get("product_name") == "Huevo rojo extra"
        and row.get("category") == "huevos y lácteos"
        and row.get("market") == target["market"]
        and row.get("publisher") == "DANE · SIPSA"
        and row.get("series") == "dane-weekly"
        and row.get("basis") == "Precio mayorista semanal"
        and row.get("currency") == "COP"
        and row.get("date") == "2013-08-23"
        and row.get("period_start") == "2013-08-17"
        and row.get("source_page") == 30
        and row.get("unit") == "unverified"
        and row.get("price") is None
        and row.get("min") == target["literal"]
        and row.get("max") == target["literal"]
        and isinstance(details, dict)
        and details.get("literal_min") == target["literal"]
        and details.get("literal_max") == target["literal"]
        and details.get("literal_mean") == target["literal"]
        and details.get("literal_unit_heading") == EVIDENCE["table_unit_heading_literal"]
        and details.get("period_type") == "weekly"
        and details.get("period_start") == "2013-08-17"
        and details.get("period_end") == "2013-08-23"
        and details.get("price_statistic") == "published_mean"
        and bool(details.get("quality_issue"))
        and isinstance(identity, dict)
        and identity == {"source_product": "Huevo rojo extra"}
    )


def apply(body: bytes, url: str, rows: list[dict]) -> list[dict]:
    """Return a copy with only the two witnessed review rows promoted."""
    if url != SOURCE_URL or hashlib.sha256(body).hexdigest() != SOURCE_SHA:
        raise ValueError("Exact Aug 2013 narrative unit witness source changed")
    selected = []
    for target in TARGETS:
        indices = [index for index, row in enumerate(rows)
                   if row.get("source_locator") == target["source_locator"]]
        if len(indices) != 1 or not _is_exact_review(rows[indices[0]], target):
            raise ValueError("Aug 2013 egg unit review tuple changed or is ambiguous")
        selected.append((indices[0], target))
    # Keep unchanged native rows identical by reference; isolate only the two
    # records whose fields are changed below.
    output = list(rows)
    for index, target in selected:
        row = deepcopy(rows[index])
        output[index] = row
        details = row["details"]
        row["unit"] = "unit"
        row["price"] = target["literal"]
        details.pop("quality_issue", None)
        details["unit_basis"] = (
            "Pesos por unidad para este precio de Huevo rojo extra: la narración "
            "de la página 27 identifica el pago por unidad en este mercado; la "
            "tabla de la página 30 conserva el encabezado general «Pesos por kilogramo»."
        )
        details["source_note"] = (
            details["source_note"]
            + " Para Huevo rojo extra, la página 27 precisa que los importes de este "
            "mercado son por unidad; la tabla de la página 30 conserva su encabezado "
            "general «Pesos por kilogramo»."
        )
        details["unit_exception_evidence"] = deepcopy(EVIDENCE)
    return output

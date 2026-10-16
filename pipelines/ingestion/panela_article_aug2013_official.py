"""Source-bound single-price article rows for the exact Aug. 2013 DANE PDF."""
from __future__ import annotations
import hashlib
import re
import unicodedata
from . import panela_article_aug2013_exact as MODULE

SOURCE_SHA = MODULE.ORIGINAL_SHA
SOURCE_URL = MODULE.SOURCE_URL
ARTICLE_SERIES = "dane-panela-article"
ARTICLE_BASIS = "Precio por kilo publicado en artículo"
ARTICLE_STATISTIC = "published_single_price"

def _slug(value: str) -> str:
    return re.sub("[^a-z0-9]+", "-", unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()).strip("-")

def official_rows(body: bytes, url: str):
    if url != SOURCE_URL or hashlib.sha256(body).hexdigest() != SOURCE_SHA:
        raise ValueError("Exact Aug 2013 panela article original changed")
    cells = MODULE.extract(body, url)
    if len(cells) != 60 or len({c["source_locator"] for c in cells}) != 60:
        raise ValueError("Incomplete or duplicated exact Aug 2013 article grid")
    rows = []
    for cell in cells:
        product = cell["product_literal"]
        rows.append({
            "product_id": _slug(product), "product_name": product, "category": "Panela",
            "publisher": "DANE · SIPSA", "series": ARTICLE_SERIES, "basis": ARTICLE_BASIS,
            "identity_dimensions": {"published_statistic": ARTICLE_STATISTIC}, "currency": "COP", "unit": "kg",
            "market": cell["market_literal"], "date": cell["period_end"], "period_start": cell["period_start"],
            "price": cell["price_cop_per_kg"], "min": None, "max": None,
            "source_locator": cell["source_locator"], "source_page": cell["source_page"],
            "details": {"period_type": "weekly", "period_start": cell["period_start"], "period_end": cell["period_end"],
                "price_statistic": ARTICLE_STATISTIC,
                "statistic": "Precio único publicado en tabla del artículo; no es media ni rango del Cuadro",
                "source_product": product, "original_price": cell["price_literal"],
                "source_note": "Precios de la panela, tabla del artículo; COP por kilo. Fuente distinta del Cuadro 8 semanal.",
                "source_table": cell["source_table"], "source_row": cell["source_row"], "source_column": cell["source_column"]}})
    if [sum(r["details"]["source_table"] == n for r in rows) for n in (1,2,3)] != [25,30,5]:
        raise ValueError("Aug 2013 article table distribution changed")
    return rows

"""DANE weekly wholesale quotations, distinct from daily and monthly prices."""

import io
import json
from hashlib import sha256
import math
import re
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urldefrag, urljoin, urlsplit

VERSION = "dane-weekly-v24"

AUG2014_PAGE43_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_11ago_15ago_2014.pdf"
AUG2014_PAGE43_SHA = "b6558d09580b038bbc077dc02475eb0d6a22ef32bb5979ba5b5a271e22148442"
AUG2014_PAGE43_HEADER = "2014 (9 al 15 de agosto)"
AUG2014_PAGE43_SUFFIX = ":aug2014-page43-caption-grid-v1:aug2014-panela-article-single-price-v1"
AUG2013_PAGE43_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_20ago_23ago_2013.pdf"
AUG2013_PAGE43_SHA = "5a8af3b10894d3241907e149a39451d09488bf827d79b52d3789e5a8cfa60f4d"
AUG2013_PAGE43_HEADER = "2013 (17 al 23 de agosto)"
AUG2013_PAGE43_ARTICLE_PERIOD = "2013 (20 de julio al 23 de agosto)"
AUG2013_PAGE43_SUFFIX = ":aug2013-page43-grid-article-period-v1"
SEP2013_PAGE43_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana23_sep_27sep_2013.pdf"
SEP2013_PAGE43_SHA = "ca2205284936795f03167c310ca401bb2beda72732c9db4d15a878134b378603"
SEP2013_PAGE43_HEADER = "2013 (21 al 27 de septiembre)"
SEP2013_PAGE43_SUFFIX = ":sep2013-page43-boundary-native-price-v1:sep2013-page43-vinagre-kg-v1"
AUGUST_2015_WRAP_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_08ago_14ago_2015.pdf"
AUGUST_2015_WRAP_SHA = "3660829203a4608502a1f0656cc7fdd7fe0ac6ad7ecf3fed8cd1ffa7d4e7e777"
AUGUST_2015_WRAP_ROWS_SHA = "9df36532f94506f59f411c4a3841b84c1ef20cc313cf91288d703045f8d796f0"

# Both source originals print periods that the ordinary weekly grammar must
# continue to reject. The 2017 bulletin explicitly reports nine inclusive
# calendar dates across an eight-day span. The 2014/2015 bulletin spaces its
# two printed years around a dash.
# Only exact archived bytes and all monetary-table captions may use these
# source-specific readings. Companion XLS rows are not covered by this review.
APRIL_2017_EXTENDED_PERIOD_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_13abr_21abr_2017.pdf"
APRIL_2017_EXTENDED_PERIOD_SHA = "e5f6ba1960b8da66108edabe4549cf7cffd70831df08108d6175eea4a65e33c6"
APRIL_2017_EXTENDED_PERIOD_PERIOD = (date(2017, 4, 13), date(2017, 4, 21))
JANUARY_2015_SPACED_YEARS_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_27dic_02ne_2015.pdf"
JANUARY_2015_SPACED_YEARS_SHA = "0655a1e671c22fe1e00adfe892737086d5ee0910993a183a079ee3213cb184d5"
JANUARY_2015_SPACED_YEARS_PERIOD = (date(2014, 12, 27), date(2015, 1, 2))
REVIEWED_PDF_PERIODS = {
    APRIL_2017_EXTENDED_PERIOD_URL: (
        APRIL_2017_EXTENDED_PERIOD_SHA, APRIL_2017_EXTENDED_PERIOD_PERIOD,
        re.compile(r"2017\s*\(13 al 21 de abril\)", re.I), 40,
        re.compile(r"semana del 13 al 21 de abril", re.I),
    ),
    JANUARY_2015_SPACED_YEARS_URL: (
        JANUARY_2015_SPACED_YEARS_SHA, JANUARY_2015_SPACED_YEARS_PERIOD,
        re.compile(r"2014\s*-\s*2015\s*\(27 de diciembre al 2 de enero\)", re.I), 37,
        re.compile(r"semana del 27 de diciembre\s+de 2014 al 2 de enero de 2015", re.I),
    ),
}

# One exact 2019 archived PDF prints this typo as a continuation annotation.
NOV2019_COTINUACION_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Sem_02nov_2019__08nov_2019.pdf"
)
NOV2019_COTINUACION_SHA = "4f038cbc3d2e2c55d1b3cbf09f22782ef451225c73dded1f7e987e3a0eca2134"
NOV2019_COTINUACION_PERIOD = (date(2019, 11, 2), date(2019, 11, 8))
NOV2019_COTINUACION_MARKER = re.compile(r"\s*\(cotinuación\)\s*$", re.IGNORECASE)
MAY2013_WHITE_CORN_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_18may_24may_2013.pdf"
MAY2013_WHITE_CORN_SHA = "d7bbfdb46fcba969ebcdbad7f17960b8fdc7ba1df8e376cd89883f692330cd04"
MAY2013_WHITE_CORN_SIZE = 1683428

# Exact retained July 2012 bulletin: table dates and dated filename differ by a
# day, while page 23 also contains an unrelated multiweek chart caption. This
# route retains literal rows for review only; it does not choose a date or price.
JULY2012_CONFLICT_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana14_19julio_2012.pdf"
JULY2012_CONFLICT_SHA = "fd66a34201085c864a2953e2e8ae56e593f2c12d897fdcb95e14bb1589c70856"
JULY2012_TABLE_HEADING = "2012 (julio 14 a 20)"
JULY2012_GRAPH_HEADING = "2012 (junio 23 a julio 19)"
JULY2012_TABLE_COUNT = 27
JULY2012_REVIEW_REASON = (
    "El boletín tiene fechas discrepantes: el archivo/portada indica 19 de julio, "
    "mientras las tablas impresas abarcan del 14 al 20 de julio; se conserva "
    "la fila literal sin fecha de observación ni precio publicado para revisión."
)


def _reviewed_cotinuacion_source(url, body_sha, page_no, table_no, side, category, period):
    """Only the physically reviewed left fruit table on this immutable PDF."""
    return (
        url == NOV2019_COTINUACION_URL
        and body_sha == NOV2019_COTINUACION_SHA
        and page_no == 34 and table_no == 1 and side == 1
        and category == "frutas frescas"
        and period == NOV2019_COTINUACION_PERIOD
    )

# Two product headings in this exact 2012 original change font for their final
# letter without printing a space. pdfplumber's font-aware word extraction
# separates the glyphs, although their native boxes overlap on one baseline.
JUNE_2012_FONT_RUN_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Semana4_junio_2012.pdf"
)
JUNE_2012_FONT_RUN_SHA = (
    "dd059a09eecb1fa01cadb24a4f21a7768d97d9e31684dee6a57222c536faf6a8"
)
JUNE_2012_FONT_RUNS = {
    19: ("hues", "o", 133.11, 150.23, 668.11),
    22: ("anillo", "s", 70.11, 89.05, 458.87),
}
JUNE_2012_MARKET_FONT_RUN_COUNTS = {19: 29, 20: 29, 21: 13}
JUNE_2012_MARKET_NAMES = {
    "Bogotá, D. C. Frigorífico Guadalupe",
    "Bogotá, D. C. Frigorífico San Martín",
}
JUNE_2012_REPAIRED_ROWS = {
    **{
        f"PDF page 19,table 1,column 1,line {line}":
        ("Carne de cerdo, pernil con hueso", ["Carne", "de", "cerdo,", "pernil", "con", "hues", "o"])
        for line in range(49, 53)
    },
    "PDF page 22,table 1,column 1,line 24":
        ("Calamar anillos", ["Calamar", "anillo", "s"]),
}

# The archived January 2017 bulletin prints these Medellín markets on two
# separate native lines. The unpriced first line is vertically as close to the
# preceding quote as to its own monetary line; nearest-row binding moves both
# the preceding market and the Medellín price to false identities. This binding
# is limited to the original whose complete two-column layout was audited.
JANUARY_2017_MARKET_WRAP_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Sem_21ene_27ene_2017.pdf"
)
JANUARY_2017_MARKET_WRAP_SHA = (
    "95072bb4d5c98fbb2b2635c8aa3dd50c22b4e3ab9c40abcb441662868b5f062e"
)
JANUARY_2017_JAN13_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Sem_7ene_2017_13ene_2017.pdf"
)
JANUARY_2017_JAN13_SHA = (
    "2075ff73d374815709ea72927d5981c81823c066a01a6dc9557cefa409902440"
)
JANUARY_2017_JAN13_ROWS_SHA = (
    "d18305dd89958247a50b9c6b875cc1013d31ef35a4a4949cdc1fec1766194728"
)
JANUARY_2017_MARKET_WRAP_ORIGINALS = {
    JANUARY_2017_MARKET_WRAP_URL: JANUARY_2017_MARKET_WRAP_SHA,
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_14ene_2017_20ene_2017.pdf":
        "3769781b1cd01919e6ad815b703094ff37efcbf9f3579f03ad7bef5858febfd3",
    JANUARY_2017_JAN13_URL: JANUARY_2017_JAN13_SHA,
}
JANUARY_2017_MARKET_LEADS = {
    "Medellín, Central": "Mayorista de Antioquia",
    "Medellín, Plaza": "Minorista “José María Villa”",
}
NOVEMBER_2016_MARKET_LEADS = {
    "Medellín, Central": "Mayorista de Antioquia",
    "Medellín, Plaza": "Minorista José María Villa",
}
DECEMBER_2022_POPAYAN_WRAP_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "bol_3dic_al_9dic_2022.pdf"
)
DECEMBER_2022_POPAYAN_WRAP_SHA = (
    "bc1793504b595c2fb17957330c5698e2fd848252b4b11b2af5fe61c268e49e83"
)
NOVEMBER_2016_MEDELLIN_WRAP_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Sem_29oct_04nov_2016.pdf"
)
NOVEMBER_2016_MEDELLIN_WRAP_SHA = (
    "1a6d6a31c9beda79688b41bf72443c1ec28dcd42ab724c49673736703b82c177"
)
NOVEMBER_2016_MEDELLIN_WRAP_ROWS_SHA = (
    "de02ebc54faff5d6e7ecb11bf388f653f6f5e57d1258789dc7386640ef7c3f66"
)

# Exact monthly rice tables embedded in two weekly-cover XLS originals.
RICE_MONTHLY_CONFLICTS = {
    'e958792dd692da3254e3c258e0e91bbc163770a2929d2e845e009eaf9053c947': dict(url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_01may_2021_07may_2021.xls', pdf_sha256='17a11d39b28de7f99fcd61e2e5c1958d72a99e33e396fff396a85e31ac892d34', table_month='2021-04', cover_end='2021-05-07', first=(2480000, 2720000, 2624000)),
    'fea945714854ad2f1dd0b96b6a9ab4a2fbec096e3758b65415a17c95433ac944': dict(url='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_03abr_2021_09abr_2021.xls', pdf_sha256='2cacb959a36249fa65a84bb67ed22517ac9dff3f1a448bbc33f317f43fea00cc', table_month='2021-03', cover_end='2021-04-09', first=(2640000, 2800000, 2704000)),
}
RICE_MONTHLY_CONFLICT_URLS = frozenset(c["url"] for c in RICE_MONTHLY_CONFLICTS.values())


def _rice_revision_binding(sheets, url, body_sha):
    """Fail closed when a new original cannot bind every row of the rice table."""
    if url not in RICE_MONTHLY_CONFLICT_URLS:
        return None
    from .worker import SourceRevisionNeedsReview

    native_sheets = [rows for name, rows in sheets if name == "1.9"]
    if len(native_sheets) != 1:
        raise SourceRevisionNeedsReview("Audited rice sheet 1.9 is absent or duplicated in changed original")
    native = native_sheets[0]
    if (len(native) < 12
        or not native[5]
        or not any(label in folded(clean(native[5][0]))
                   for label in ("arroz y subproductos en molino", "arroz en molino"))
        or len(native[9]) < 5
        or [folded(clean(v)) for v in native[9][:3]] != ["producto", "mercado mayorista", "pesos por kilogramo"]
        or len(native[10]) < 5
        or [folded(clean(v)) for v in native[10][2:5]] != ["precio minimo", "precio maximo", "precio medio"]):
        raise SourceRevisionNeedsReview("Audited rice sheet caption or monetary columns changed")
    numeric = [row for row in native[11:]
               if len(row) >= 5 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                        for v in row[2:5])]
    if len(numeric) != 111 or any(not clean(row[0]) or not clean(row[1]) for row in numeric):
        raise SourceRevisionNeedsReview("Audited rice sheet numeric rows cannot all be bound")
    # A moved/renamed copy must not escape through an ordinary kg sheet.
    if any(name != "1.9" and any(
        any(label in folded(clean(v)) for label in ("arroz y subproductos en molino", "arroz en molino"))
        for row in rows[:12] for v in row if isinstance(v, str)
    ) for name, rows in sheets):
        raise SourceRevisionNeedsReview("Audited rice table appears on another sheet")
    return native
UNIT_REVIEW_MARKER = "DANE weekly 2018 native unit undeclared; exact archived workbook reviewed"
UNIT_REVIEW_LOCATOR = "XLSX document-level native unit review"
UNIT_REVIEW_MANIFEST = json.loads(
    (Path(__file__).parent / "weekly_2018_unit_reviews.json").read_text()
)
UNIT_REVIEW_ORIGINALS = {
    entry["sha256"]: entry for entry in UNIT_REVIEW_MANIFEST["documents"]
}


def _audited_unit_review(body, url, body_sha, sheets, declared_kg):
    """Classify only the 31 retained, independently audited native originals."""
    manifest = UNIT_REVIEW_MANIFEST
    entry = UNIT_REVIEW_ORIGINALS.get(body_sha)
    if entry is None:
        return None
    if declared_kg or url != entry["url"] or len(body) != entry["bytes"]:
        raise ValueError("Audited weekly workbook identity or monetary unit changed")
    if source_date(url).isoformat() != entry["source_date"]:
        raise ValueError("Audited weekly workbook source date changed")
    shift = 1 if entry["layout"] == "flat-group-columns" else 0
    expected = (["grupo", "producto", "mercado mayorista", "precio minimo", "precio maximo", "precio medio"]
                if shift else ["producto", "mercado mayorista", "precio minimo", "precio maximo", "precio medio"])
    numeric_rows = 0
    data_sheets = 0
    for _, rows in sheets[1:]:
        header_row = 0 if shift else 9
        if len(rows) <= header_row or [folded(clean(v)) for v in rows[header_row][:len(expected)]] != expected:
            raise ValueError("Audited weekly workbook native column layout changed")
        data_sheets += 1
        for row in rows:
            if len(row) < shift + 5:
                continue
            if isinstance(row[shift], str) and isinstance(row[shift + 1], str) and all(
                isinstance(v, (int, float)) and not isinstance(v, bool)
                for v in row[shift + 2:shift + 5]
            ):
                numeric_rows += 1
    if not data_sheets or numeric_rows != entry["native_numeric_rows"]:
        raise ValueError("Audited weekly workbook native numeric row count changed")
    return [{
        "source_locator": UNIT_REVIEW_LOCATOR,
        "price": None,
        "details": {
            "quality_issue": UNIT_REVIEW_MARKER,
            "original_sha256": body_sha,
            "source_url": url,
            "source_date": entry["source_date"],
            "native_layout": entry["layout"],
            "native_numeric_rows_untyped": numeric_rows,
            "paired_pdf_sha256": entry["paired_pdf_sha256"],
            "paired_pdf_status": entry["paired_pdf_status"],
            "paired_pdf_date_conflict": entry["paired_pdf_date_conflict"],
            "paired_pdf_date_note": entry.get("paired_pdf_date_note"),
            "strict_pdf_matches_diagnostic_only": entry["strict_pdf_matches"],
            "folded_matches_diagnostic_only": entry["folded_diagnostic_only"],
            "unmatched_pdf_identity": entry["unmatched_pdf_identity"],
            "same_identity_different_amount": entry["same_identity_different_amount"],
            "audit_date_consistent_unmatched": manifest["audit"]["date_consistent_unmatched"],
            "audit_amount_conflicts": manifest["audit"]["amount_conflicts"],
            "prior_error": entry["prior_error"],
            "unit_basis": "No monetary unit declared in the archived XLSX; paired PDF identity is not a workbook-wide unit proof.",
        },
    }]
WEEKLY = "https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/mayoristas-boletin-semanal-1"
ROOTS = ((WEEKLY, "dane-weekly-index"),)
MARCH_2024_ANNEX_URL = (
    "https://www.dane.gov.co/files/operaciones/SIPSA/"
    "anex-SIPSASemanal-09mar-16mar-2024.xlsx"
)
MARCH_2024_ANNEX_SHA = "a1d2992f6bee7ce29c12ed1cee92feb31a9204ffe5546cd3276bab0cc09436e6"
MARCH_2024_PRINTED_PERIOD = (date(2024, 3, 9), date(2024, 3, 15))
JULY_2023_BULLETIN_URL = (
    "https://www.dane.gov.co/files/operaciones/SIPSA/"
    "bol-SIPSASemanal-22jul-28jul-2023.pdf"
)
JULY_2023_BULLETIN_SHA = "7bd0545a892e3a95cbaa9333510161ed14b7753949ac0fae3c24aa419729d088"
JULY_2023_PRINTED_TABLE_PERIOD = (date(2023, 7, 15), date(2023, 7, 21))
JULY_2023_OFFICIAL_PERIOD = (date(2023, 7, 22), date(2023, 7, 28))
JULY_2023_MATCHING_ANNEX_SHA = "8c816da5924dce084db73edd8bd05f501afa9aa3ffb0cdb756371c196f95080a"
NOVEMBER_2022_BULLETIN_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "bol_12nov_al_18nov_2022.pdf"
)
NOVEMBER_2022_BULLETIN_SHA = "fc7e88b6cc7d6b413ed9af697c8d7388bc4c02a2e43de031be4facba0a57fd44"
NOVEMBER_2022_MATCHING_ANNEX_SHA = "e6bda6d3172e0dfa87cde29fd9a8151ee438d265c8b8cf8a3fbeb72b6ae5d25f"
NOVEMBER_2022_PRINTED_TABLE_PERIOD = (date(2022, 10, 22), date(2022, 11, 18))
NOVEMBER_2022_OFFICIAL_PERIOD = (date(2022, 11, 12), date(2022, 11, 18))
INDEX_KINDS = {"dane-weekly-index"}
PUBLISHERS = {
    kind: "DANE · SIPSA"
    for kind in ("dane-weekly-index", "dane-weekly-xlsx", "dane-weekly-pdf")
}
MONTHS = [
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
MONTH_NUM = {v: i for i, m in enumerate(MONTHS, 1) for v in (m, m[:3])}
MONTH_NUM["setiembre"] = 9
MONTH = "(?:" + "|".join(sorted(MONTH_NUM, key=len, reverse=True)) + ")"
NUMBER = re.compile(r"(?:\d{1,3}(?:\.\d{3})+|\d{1,3}(?:,\d{3})+|\d+(?:,\d{1,2})?)")
# Only suffixes printed in the archived DANE weekly PDFs are annotations.
# Keep this finite: a broad edit-distance match could erase a real product name.
PRODUCT_CONTINUATION_MARKERS = (
    "(continuación)",
    "(contoinuación)",
    "(continuacion)",
    "(continución)",
    "(continucion)",
    "(comntinuación)",
    "(comtinuación)",
    "(comntinuacion)",
    "(conclusión)",
    "(conclusion)",
    "(continuaciòn)",
    "(continuacón)",
    "(continuaciópn)",
    "(continación)",
    "(continaución)",
    "(continiación)",
    "(continiuación)",
    "(contiunuación)",
    "(continuaión)",
    "(continuiación)",
    "(continujación)",
    "(contiuación)",
    "(contnuación)",
    "(contrinuación)",
    "(contunuación)",
    "(continuaci{on)",
    "(continuacion )",
    "(continuación",
    "(continuación9",
    "(continu",
    "continuación)",
)
PRODUCT_CONTINUATION = re.compile(
    r"\s*(?:"
    + "|".join(
        re.escape(marker)
        for marker in sorted(PRODUCT_CONTINUATION_MARKERS, key=len, reverse=True)
    )
    + r")\s*$",
    re.IGNORECASE,
)


def _product_heading(label, *, reviewed_cotinuacion=False):
    """Separate a printed continuation marker from the product identity."""
    label = clean(label)
    marker = PRODUCT_CONTINUATION.search(label)
    if marker is None and reviewed_cotinuacion:
        marker = NOV2019_COTINUACION_MARKER.search(label)
    return (clean(label[: marker.start()]), True) if marker else (label, False)


def _pdf_number(token):
    # SIPSA weekly PDFs print whole-peso prices with either grouping mark.
    # A comma followed by one or two digits remains a decimal comma.
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", token):
        return float(token.replace(".", "").replace(",", ""))
    return float(token.replace(".", "").replace(",", "."))


def folded(value):
    return "".join(
        c
        for c in unicodedata.normalize("NFD", str(value))
        if not unicodedata.combining(c)
    ).lower()


def clean(value):
    return " ".join(str(value or "").replace("\xad", "").split())


class NormalExtractionFailed(ValueError):
    def __init__(self, required_pages):
        self.required_pages = tuple(sorted(set(required_pages)))
        super().__init__(
            f"Weekly native price extraction failed on pages {self.required_pages}"
        )


def _period(text):
    """Only explicit weekly ranges; neither publication days nor graph dates."""
    text = folded(text).replace("_", " ")
    parenthesized_years = re.search(
        rf"\b(20\d{{2}})\s*\(\s*(\d{{1,2}})\s+de\s+({MONTH})\s*\)\s*[-–]\s*"
        rf"(20\d{{2}})\s*\(\s*(\d{{1,2}})\s+de\s+({MONTH})\s*\)",
        text,
    )
    if parenthesized_years:
        y1, d1, m1, y2, d2, m2 = parenthesized_years.groups()
        first = date(int(y1), MONTH_NUM[m1], int(d1))
        last = date(int(y2), MONTH_NUM[m2], int(d2))
        if not 1 <= (last - first).days <= 7:
            raise ValueError("Weekly printed range is not a supported weekly period")
        return first, last
    prefix = re.search(
        rf"(20\d{{2}})[-–](20\d{{2}})\s*\(\s*(\d{{1,2}})\s+de\s+({MONTH})\s+al\s+(\d{{1,2}})\s+de\s+({MONTH})\s*\)",
        text,
    )
    if prefix:
        y1, y2, d1, m1, d2, m2 = prefix.groups()
        first, last = (
            date(int(y1), MONTH_NUM[m1], int(d1)),
            date(int(y2), MONTH_NUM[m2], int(d2)),
        )
        if not 1 <= (last - first).days <= 7:
            raise ValueError("Weekly printed range is not a supported weekly period")
        return first, last
    # A single printed year applies to both months of an ordinary cross-month
    # week: 2021 (27 de febrero al 5 de marzo). A December/January range needs
    # explicit two-year evidence handled above, not an inferred year change.
    year_first = re.search(
        rf"\b(20\d{{2}})\s*\(\s*(\d{{1,2}})\s+(?:de\s+)?({MONTH})\s+(?:al|a)\s+(\d{{1,2}})\s+de\s+({MONTH})\s*\)",
        text,
    )
    if year_first:
        year, first, m1, last, m2 = year_first.groups()
        result = (
            date(int(year), MONTH_NUM[m1], int(first)),
            date(int(year), MONTH_NUM[m2], int(last)),
        )
        if not 1 <= (result[1] - result[0]).days <= 7:
            raise ValueError("Weekly printed range is not a supported weekly period")
        return result
    # Native DANE captions also place the first month before its day, and
    # the ending month after its day: 2023 (octubre 28 al 3 de noviembre).
    # The printed year applies to both dates; no filename/date inference.
    month_first = re.search(
        rf"\b(20\d{{2}})\s*\(\s*({MONTH})\s+(\d{{1,2}})\s+(?:al|a)\s+"
        rf"(\d{{1,2}})\s+(?:de\s+)?({MONTH})\s*\)",
        text,
    )
    if month_first:
        year, m1, first, last, m2 = month_first.groups()
        result = (
            date(int(year), MONTH_NUM[m1], int(first)),
            date(int(year), MONTH_NUM[m2], int(last)),
        )
        if not 1 <= (result[1] - result[0]).days <= 7:
            raise ValueError("Weekly printed range is not a supported weekly period")
        return result
    # Explicit years on both sides of a New Year week.
    cross = re.search(
        rf"\b(\d{{1,2}})\s*(?:de\s*)?({MONTH})\s*(?:de\s*)?(20\d{{2}})\s*(?:al|a|-)\s*(\d{{1,2}})\s*(?:de\s*)?({MONTH})\s*(?:de\s*)?(20\d{{2}})\b",
        text,
    )
    if cross:
        d1, m1, y1, d2, m2, y2 = cross.groups()
        start, end = (
            date(int(y1), MONTH_NUM[m1], int(d1)),
            date(int(y2), MONTH_NUM[m2], int(d2)),
        )
        if not 1 <= (end - start).days <= 7:
            raise ValueError("Weekly printed range is not a supported weekly period")
        return start, end
    # Modern caption: 19 al 25 de septiembre de 2026; cross-month ranges too.
    match = re.search(
        rf"\b(\d{{1,2}})\s*(?:de\s*)?({MONTH})?\s*(?:al|a|-)\s*(\d{{1,2}})\s*(?:de\s*)?({MONTH})\s*(?:de\s*)?(20\d{{2}})\b",
        text,
    )
    if match:
        first, m1, last, m2, year = match.groups()
        month2 = MONTH_NUM[m2]
        month1 = MONTH_NUM[m1] if m1 else month2
        y = int(year)
        result = (
            date(y - int(month1 > month2), month1, int(first)),
            date(y, month2, int(last)),
        )
    else:
        # Original 2012 monetary caption: 2012 (agosto 4 a 10).
        match = re.search(
            rf"\b(20\d{{2}})\s*\(\s*({MONTH})\s+(\d{{1,2}})\s*(?:a|al|-)\s*(?:({MONTH})\s*)?(\d{{1,2}})\s*\)",
            text,
        )
        if not match:
            reverse = re.search(
                rf"\b(20\d{{2}})\s*\(\s*(\d{{1,2}})\s*(?:a|al|-)\s*(\d{{1,2}})\s+(?:de\s+)?({MONTH})\s*\)",
                text,
            )
            if not reverse:
                return None
            year, first, last, month = reverse.groups()
            end_year = int(year)
            end_month = MONTH_NUM[month]
            # DANE also prints cross-month weeks as "2026 (31 al 6 de
            # febrero)". A larger start day must be in the preceding month;
            # the printed year belongs to the end of the range.
            start_month = end_month - int(int(first) > int(last))
            start_year = end_year
            if start_month == 0:
                start_month = 12
                start_year -= 1
            result = (
                date(start_year, start_month, int(first)),
                date(end_year, end_month, int(last)),
            )
            if not 1 <= (result[1] - result[0]).days <= 7:
                raise ValueError(
                    "Weekly printed range is not a supported weekly period"
                )
            return result
        year, m1, first, m2, last = match.groups()
        month1 = MONTH_NUM[m1]
        month2 = MONTH_NUM[m2] if m2 else month1
        result = (
            date(int(year), month1, int(first)),
            date(int(year) + int(month2 < month1), month2, int(last)),
        )
    if not 1 <= (result[1] - result[0]).days <= 7:
        raise ValueError("Weekly printed range is not a supported weekly period")
    return result


def _url_period(url):
    text = folded(unquote(urlsplit(url).path.rsplit("/", 1)[-1]))
    explicit = re.search(
        rf"(\d{{1,2}})({MONTH})[_-]?(20\d{{2}})[_-]*(\d{{1,2}})({MONTH})[_-]?(20\d{{2}})",
        text,
    )
    if explicit:
        first = date(int(explicit[3]), MONTH_NUM[explicit[2]], int(explicit[1]))
        last = date(int(explicit[6]), MONTH_NUM[explicit[5]], int(explicit[4]))
    else:
        years = re.findall(r"20\d{2}", text)
        if len(years) != 1:
            return None
        pairs = re.findall(rf"(\d{{1,2}})({MONTH})", text)
        if len(pairs) == 2:
            (d1, m1), (d2, m2) = pairs
        else:
            match = re.search(
                rf"semana[_-]?(\d{{1,2}})[_-](\d{{1,2}})({MONTH})[_-](20\d{{2}})", text
            )
            if not match:
                return None
            d1, d2, m2, _ = match.groups()
            m1 = m2
        last = date(int(years[0]), MONTH_NUM[m2], int(d2))
        first = date(
            last.year - int(MONTH_NUM[m1] > last.month), MONTH_NUM[m1], int(d1)
        )
    return (first, last) if 1 <= (last - first).days <= 7 else None


def source_date(url):
    if url in REVIEWED_PDF_PERIODS:
        # The corresponding parse_pdf path still checks exact content SHA,
        # 44 pages, printed cover and every monetary-table caption.
        return REVIEWED_PDF_PERIODS[url][1][1]
    # The official archive and all nine native sheets say March 9–15. The
    # annex path alone has an erroneous 16; parse_workbook still requires the
    # exact audited content SHA before publication.
    if url == MARCH_2024_ANNEX_URL:
        return MARCH_2024_PRINTED_PERIOD[1]
    period = _url_period(url)
    return period[1] if period else None


def discover(body=None, url=None, kind=None):
    if body is None:
        return list(ROOTS)
    if kind != "dane-weekly-index":
        return []
    from bs4 import BeautifulSoup

    found = []
    for a in BeautifulSoup(body, "html.parser").select("a[href]"):
        child = urldefrag(urljoin(url, a["href"]))[0]
        parts = urlsplit(child)
        if (
            parts.scheme != "https"
            or parts.hostname not in {"www.dane.gov.co", "dane.gov.co"}
            or parts.username
            or parts.password
        ):
            continue
        path = unquote(parts.path).lower()
        if "/mayoristas-boletin-semanal-" in path and not path.startswith("/files/"):
            child_kind = "dane-weekly-index"
        elif path.startswith("/files/") and re.search(
            r"(?:semanal|semana|sem[_-]|(?:anexo|anex|bol)[_-]\d)[^/]*\.(?:pdf|xlsx?)$",
            path,
        ):
            child_kind = (
                "dane-weekly-pdf" if path.endswith(".pdf") else "dane-weekly-xlsx"
            )
        else:
            continue
        if child != urldefrag(url)[0]:
            found.append((child, child_kind))
    return list(dict.fromkeys(found))


def _exceptions(text):
    text = folded(clean(text))
    return {
        "eggs": bool(
            re.search(
                r"\bhuevos?\b.{0,160}(?:\$\s*/\s*unidad|pesos\s*(?:/|por)\s*unidad|por\s+unidad)",
                text,
            )
        ),
        "liquids": bool(
            re.search(
                r"aceite vegetal mezcla.{0,100}jugo de frutas.{0,100}vinagre.{0,100}(?:\$\s*/\s*litro|pesos\s*(?:/|por)\s*litro|por\s+litro)",
                text,
            )
        ),
    }


def _unit(name, exceptions):
    name = folded(name)
    if name in exceptions.get("exact_kilogram_products", ()):
        return "kg"
    if name.startswith("huevo"):
        return "unit" if exceptions.get("eggs") else None
    if name in {"aceite vegetal mezcla", "jugo de frutas", "vinagre"}:
        return "litre" if exceptions.get("liquids") else None
    return "kg"


def _row(
    name,
    market,
    low,
    high,
    mean,
    trend,
    category,
    period,
    locator,
    *,
    page=None,
    exceptions=None,
    allow_missing_identity=False,
    allow_missing_min=False,
    allow_unpriced_zero=False,
    allow_unavailable=False,
    allow_published_range_conflict=False,
):
    from .worker import slug, today

    start, end = period
    if end > today():
        raise ValueError("Weekly monetary table period is in the future")
    numbers = [float(v) if v is not None else None for v in (low, high, mean)]
    if allow_unpriced_zero and numbers != [None, None, 0.0]:
        raise ValueError("Native unpriced-zero review requires literal missing min/max and printed zero mean")
    if allow_unavailable and numbers != [None, None, None]:
        raise ValueError("Native unavailable review requires three literal dash cells")
    invalid_number = (
        (numbers[0] is None and not allow_missing_min)
        or any(v is None or not math.isfinite(v) or v <= 0 for v in numbers[1:])
        or (numbers[0] is not None and (not math.isfinite(numbers[0]) or numbers[0] <= 0))
    )
    if allow_unpriced_zero or allow_unavailable:
        invalid_number = False
    range_conflict = not invalid_number and not (allow_unpriced_zero or allow_unavailable) and (
        numbers[2] > numbers[1]
        or (numbers[0] is not None and numbers[0] > numbers[2])
    )
    printed_zero = (
        allow_published_range_conflict
        and any(v == 0 for v in numbers)
        and all(v is not None and math.isfinite(v) and v >= 0 for v in numbers)
    )
    if (invalid_number and not printed_zero) or (range_conflict and not allow_published_range_conflict):
        raise ValueError(f"Weekly mean is outside the printed min/max at {locator}")
    name, market = clean(name), clean(market)
    product_id = slug(name)
    missing_identity = not product_id or not market
    if missing_identity and not allow_missing_identity:
        raise ValueError("Weekly price lacks a literal product or market")
    unit = _unit(name, exceptions or {}) if name else None
    row = {
        "product_id": product_id,
        "product_name": name,
        "category": clean(category),
        "publisher": "DANE · SIPSA",
        "series": "dane-weekly",
        "basis": "Precio mayorista semanal",
        "identity_dimensions": {"source_product": name},
        "currency": "COP",
        "unit": unit or "unverified",
        "market": market,
        "date": end.isoformat(),
        "period_start": start.isoformat(),
        "price": numbers[2],
        "min": numbers[0],
        "max": numbers[1],
        "source_locator": locator,
        "source_page": page,
        "details": {
            "period_type": "weekly",
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "price_statistic": "published_mean",
            "trend": clean(trend),
            "source_note": "Media semanal publicada por DANE; mínimo y máximo de la misma semana. La tendencia es el símbolo literal de la fuente.",
            "unit_basis": "Pesos por kilogramo; excepciones de huevos/líquidos solo según nota explícita de la publicación.",
        },
    }
    if folded(name) in (exceptions or {}).get("exact_kilogram_products", ()):
        row["details"]["literal_unit_heading"] = "Pesos por kilogramo"
        row["details"]["exact_unit_evidence"] = (
            "Exact page-43 Cuadro 8 header: Pesos por kilogramo"
        )
    if unit is None:
        row["price"] = None
        row["details"].update(
            {
                "quality_issue": "La tabla no declara la excepción de unidad para huevos/líquidos; se conserva el precio literal sin asignar kg, unidad o litro.",
                "literal_min": numbers[0],
                "literal_max": numbers[1],
                "literal_mean": numbers[2],
                "literal_unit_heading": "Pesos por kilogramo",
            }
        )
    if missing_identity:
        row["price"] = None
        row["details"].update(
            {
                "quality_issue": "La fila monetaria tiene una celda de producto o mercado vacía; no se arrastra una identidad de filas vecinas.",
                "literal_product_name": name or None,
                "literal_market_name": market or None,
                "literal_min": numbers[0],
                "literal_max": numbers[1],
                "literal_mean": numbers[2],
            }
        )
    if allow_missing_min:
        row["price"] = None
        row["details"].update(
            {
                "quality_issue": "La fuente deja vacía la celda de precio mínimo; se conservan máximo y medio literales para revisión sin inferir el mínimo.",
                "literal_min": None,
                "literal_max": numbers[1],
                "literal_mean": numbers[2],
                "literal_missing_columns": ["Mínimo"],
            }
        )
    if allow_unpriced_zero:
        row["price"] = None
        row["details"].update({
            "quality_issue": "La fuente imprime puntos sin precio mínimo/máximo y cero como medio; se conserva la fila literal sin publicar un precio.",
            "literal_min": ".", "literal_max": ".", "literal_mean": 0.0,
            "literal_missing_columns": ["Mínimo", "Máximo"],
        })
    if allow_unavailable:
        row["price"] = None
        row["details"].update({
            "quality_issue": "La fuente identifica el mercado pero imprime guiones en las tres columnas de precio; se conserva la fila literal sin cotización.",
            "literal_min": "-", "literal_max": "-", "literal_mean": "-",
            "literal_missing_columns": ["Mínimo", "Máximo", "Medio"],
        })
    if range_conflict or printed_zero:
        row["price"] = None
        row["details"].update(
            {
                "quality_issue": (
                    "La fuente imprime cero en una celda monetaria; se conservan las tres cifras literales para revisión sin publicar un precio nulo."
                    if printed_zero else
                    "La media publicada está fuera del rango mínimo/máximo impreso; se conservan las tres cifras literales para revisión."
                ),
                "literal_min": numbers[0],
                "literal_max": numbers[1],
                "literal_mean": numbers[2],
            }
        )
    return row


def _review_workbook_conflicts(rows):
    """A named workbook row is independent; withhold only conflicting keys."""
    groups = {}
    for row in rows:
        if row.get("price") is None:
            continue
        key = (
            row["product_id"],
            row["product_name"],
            row["market"],
            row["currency"],
            row["unit"],
            row["basis"],
            row["date"],
        )
        groups.setdefault(key, []).append(row)
    for group in groups.values():
        if len({(r["min"], r["max"], r["price"]) for r in group}) <= 1:
            continue
        locators = [r["source_locator"] for r in group]
        for row in group:
            row["details"].update(
                {
                    "quality_issue": "El anexo publica precios distintos para el mismo producto, mercado, unidad y semana; todas las filas en conflicto se conservan para revisión.",
                    "literal_min": row["min"],
                    "literal_max": row["max"],
                    "literal_mean": row["price"],
                    "conflicting_source_locators": locators,
                }
            )
            row["price"] = None
    return rows


def _verify_url(period, url, body_sha=None):
    filename = _url_period(url)
    if filename is not None and period[1] != filename[1]:
        if (url == MARCH_2024_ANNEX_URL
            and body_sha == MARCH_2024_ANNEX_SHA
            and period == MARCH_2024_PRINTED_PERIOD):
            return
        from .worker import SourceDateMismatch

        raise SourceDateMismatch(
            "Weekly printed period conflicts with the dated source URL: "
            f"printed {period[0]}–{period[1]}; filename {filename[0]}–{filename[1]}"
        )


class WeeklyNativeContextIncomplete(ValueError):
    """Readable grouped source whose own cells and URL do not date the prices."""


def parse_workbook(body, url):
    from .worker import workbooks

    body_sha = sha256(body).hexdigest()
    sheets = [(name, list(rows)) for name, rows in workbooks(body)]
    rice_native = _rice_revision_binding(sheets, url, body_sha)
    notes = "\n".join(
        clean(value)
        for _, rows in sheets
        for row in rows
        for value in row
        if isinstance(value, str)
    )
    exceptions = _exceptions(notes)
    declared_kg = "pesos por kilogramo" in folded(notes)
    result = []
    # Read one publication heading at a time. Ancillary supply sheets can
    # print their own longer reporting range after the weekly price caption.
    global_period = next(
        (
            period
            for _, rows in sheets
            for row in rows[:10]
            for value in row
            if isinstance(value, str)
            and (period := _period(clean(value))) is not None
        ),
        None,
    )
    for name, rows in sheets:
        grouped = any(
            len(row) >= 4
            and folded(clean(row[0])) == "productos y mercados"
            and [folded(clean(v)) for v in row[1:4]]
            == ["precio minimo", "precio maximo", "precio medio"]
            for row in rows
        )
        if grouped:
            period = global_period or _url_period(url)
            if period is None:
                raise WeeklyNativeContextIncomplete(
                    "Weekly grouped workbook has no explicit period in cells or URL"
                )
            _verify_url(period, url, body_sha)
            product = ""
            category = ""
            active = False
            for row_no, row in enumerate(rows, 1):
                label = clean(row[0]) if row else ""
                if re.match(
                    r"Cuadro \d+\. Mercados mayoristas\. Precios de venta de ", label
                ):
                    category = re.sub(r"^.*?Precios de venta de ", "", label).strip()
                    active = False
                    product = ""
                    continue
                if len(row) >= 4 and folded(label) == "productos y mercados":
                    if [folded(clean(v)) for v in row[1:4]] != [
                        "precio minimo",
                        "precio maximo",
                        "precio medio",
                    ]:
                        raise ValueError(
                            "Weekly grouped monetary column meanings changed"
                        )
                    active = True
                    continue
                if not active or not label:
                    continue
                # Two audited originals repeat monetary column titles as a
                # schematic row below the verified header. It is not a market;
                # every other incomplete numeric row still fails.
                if (
                    (url, body_sha) in {
                        (
                            "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Anexo_21feb_27feb_2015.xls",
                            "30d900d3c1d2ee3ca4f32bd09649b682b16f9bd23a177c7200de518b8dc2bcbd",
                        ),
                        (
                            "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_29oct_04nov_2016.xls",
                            "abce8f1ee2cd3211e6bb20b8dd6a2849aea9266a19b76a5c293ef89b77a1e23e",
                        ),
                    }
                    and name == "Información Boletin"
                    and row_no == 3
                    and list(row[:5]) == ["Producto", "Min(1)", "Max(1)", "P(1)", "Tend"]
                ):
                    continue
                prices = row[1:4]
                if not any(v not in (None, "") for v in prices):
                    product = label
                    continue
                if not all(
                    isinstance(v, (int, float)) and not isinstance(v, bool)
                    for v in prices
                ):
                    raise ValueError(
                        "Weekly grouped workbook has incomplete monetary cells"
                    )
                record = _row(
                    product,
                    label,
                    *prices,
                    row[4] if len(row) > 4 else "",
                    category,
                    period,
                    f"{name}!row {row_no},cols B:D",
                    exceptions=exceptions,
                    allow_published_range_conflict=True,
                )
                if not declared_kg:
                    record["price"] = None
                    record["unit"] = "unverified"
                    record["details"].update(
                        {
                            "quality_issue": "El anexo conserva cifras monetarias pero no declara la unidad; consultar el PDF compañero de la misma semana.",
                            "literal_min": float(prices[0]),
                            "literal_max": float(prices[1]),
                            "literal_mean": float(prices[2]),
                            "literal_unit_heading": None,
                            "unit_basis": "No se declara la unidad en las celdas ni encabezados de impresión del anexo.",
                            "period_evidence": "workbook cells"
                            if global_period
                            else "explicit publisher filename range",
                        }
                    )
                result.append(record)
            continue
        header = next(
            (
                i
                for i, row in enumerate(rows)
                if len(row) >= 5
                and clean(row[0]) == "Producto"
                and "mercado" in folded(row[1])
                and "pesos por kilogramo" in folded(row[2])
            ),
            None,
        )
        if header is None:
            continue  # Index, supply tonnes and narrative are not monetary tables.
        subheader = [folded(clean(v)) for v in rows[header + 1]]
        if subheader[2:5] != ["precio minimo", "precio maximo", "precio medio"]:
            raise ValueError("Weekly workbook monetary column meanings changed")
        heading = "\n".join(clean(v) for row in rows[:header] for v in row if v)
        period = _period(heading)
        if period is None:
            raise ValueError("Weekly workbook has no explicit table period")
        _verify_url(period, url, body_sha)
        category = next(
            (
                re.sub(r"^\d+\.\d+\.\s*", "", clean(row[0])).rstrip("*")
                for row in rows[:header]
                if row and re.match(r"^\d+\.\d+\.\s", clean(row[0]))
            ),
            "Productos mayoristas",
        )
        for row_no, row in enumerate(rows[header + 2 :], header + 3):
            if len(row) < 5 or not any(isinstance(v, (int, float)) for v in row[2:5]):
                continue
            if not all(
                isinstance(v, (int, float)) and not isinstance(v, bool)
                for v in row[2:5]
            ):
                raise ValueError("Weekly workbook has incomplete numeric price cells")
            result.append(
                _row(
                    row[0],
                    row[1],
                    *row[2:5],
                    row[5] if len(row) > 5 else "",
                    category,
                    period,
                    f"{name}!row {row_no},cols C:E",
                    exceptions=exceptions,
                    allow_missing_identity=True,
                    allow_published_range_conflict=True,
                )
            )
    if not result:
        audited = _audited_unit_review(body, url, body_sha, sheets, declared_kg)
        if audited is not None:
            return audited
        raise ValueError(
            "Weekly workbook native extraction failed: no supported monetary tables; original requires layout/OCR review"
        )
    if url == MARCH_2024_ANNEX_URL and body_sha == MARCH_2024_ANNEX_SHA:
        for row in result:
            row["details"].update({
                "source_filename_period_end": "2024-03-16",
                "literal_printed_period_end": "2024-03-15",
                "source_period_resolution": "official archive and all native worksheet captions: March 9–15; exact annex SHA",
            })
    rice = next((case for sha, case in RICE_MONTHLY_CONFLICTS.items() if case["url"] == url), None)
    if rice_native is not None:
        from .worker import SourceRevisionNeedsReview

        native = rice_native
        exact = RICE_MONTHLY_CONFLICTS.get(body_sha) is rice
        if exact and (clean(native[11][0]) != "Arroz blanco empacado"
                      or clean(native[11][1]) != "Aguazul (Casanare)"
                      or tuple(native[11][2:5]) != rice["first"]):
            raise SourceRevisionNeedsReview("Audited rice original first row changed")
        target = [row for row in result if row["source_locator"].startswith("1.9!")]
        if (len(target) != 111 or any(row["date"] != rice["cover_end"] or row["unit"] != "kg" for row in target)
            or any(any(label in folded(row.get("category", ""))
                       for label in ("arroz y subproductos en molino", "arroz en molino"))
                   for row in result if not row["source_locator"].startswith("1.9!"))):
            raise SourceRevisionNeedsReview("Audited rice rows cannot all be bound to sheet 1.9")
        for row in target:
            row["details"].update({
                "quality_issue": "DANE rice mill native kg heading conflicts with published tonne chart and reporting period; literal price withheld pending verified unit/date resolution.",
                "literal_min": row["min"], "literal_max": row["max"],
                "literal_mean": row["price"],
                "literal_table_unit_heading": "Pesos por kilogramo",
                "literal_weekly_cover_end": rice["cover_end"],
                "conflict_kind": "publisher_unit_and_period",
                "original_sha256": body_sha,
            })
            if exact:
                row["details"].update({"companion_pdf_sha256": rice["pdf_sha256"],
                                       "literal_pdf_table_month": rice["table_month"]})
            row["price"] = None
    return _review_workbook_conflicts(result)


def _lines(words):
    lines = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        line = next(
            (line for line in lines[-3:] if abs(line[0]["top"] - word["top"]) <= 2),
            None,
        )
        if line is None:
            lines.append([word])
        else:
            line.append(word)
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _split_joined_price_words(words, columns, *, sep2013_page43=False):
    """Separate only literal glyph runs aligned with adjacent price headers.

    Some DANE PDFs have distinct, positioned glyphs but no extractable space
    between two printed cells. The characters, not an inferred price, provide
    both the split and its exact coordinates.
    """
    def piece(word, chars):
        return {
            **word,
            "text": "".join(char["text"] for char in chars),
            "x0": min(char["x0"] for char in chars),
            "x1": max(char["x1"] for char in chars),
            "chars": chars,
        }

    def aligned(word, header):
        center = (word["x0"] + word["x1"]) / 2
        return header["x0"] - 12 <= center <= header["x1"] + 12

    result = []
    if sep2013_page43:
        if len(columns) != 2 or any(len(headers) < 3 for headers in columns):
            raise ValueError("Exact September 2013 page-43 price columns changed")
        headers = columns[1]
        candidates = []
        for index in range(len(words) - 1):
            label, amount = words[index:index + 2]
            label_chars, amount_chars = label.get("chars"), amount.get("chars")
            if not label_chars or not amount_chars:
                continue
            text, suffix = label.get("text", ""), amount.get("text", "")
            if (not text.endswith("4") or suffix != ".527"
                    or len(label_chars) != len(text) or len(amount_chars) != len(suffix)):
                continue
            if text != "Antioquia4":
                continue
            prior = []
            cursor = index - 1
            while cursor >= 0 and abs(words[cursor]["top"] - label["top"]) <= 0.25 and len(prior) < 4:
                prior.insert(0, words[cursor]["text"])
                cursor -= 1
            if prior != ["Medellín,", "Central", "Mayorista", "de"]:
                continue
            gap = amount["x0"] - label["x1"]
            overlap = label_chars[-1]["x1"] - amount_chars[0]["x0"]
            value_chars = [label_chars[-1], *amount_chars]
            x0, x1 = min(c["x0"] for c in value_chars), max(c["x1"] for c in value_chars)
            center = (x0 + x1) / 2
            aligned = headers[0]["x0"] - 2 <= center <= headers[0]["x1"] + 2
            if (abs(label["top"] - amount["top"]) <= 0.25
                    and -0.25 <= gap <= 0.25 and overlap >= 0 and aligned):
                candidates.append((index, label, amount, value_chars))
        if len(candidates) != 1:
            raise ValueError("Exact September 2013 Antioquia glyph partition is ambiguous")
        index, label, amount, value_chars = candidates[0]
        prefix_chars = label["chars"][:-1]
        prefix_piece = {**label, "text": "".join(c["text"] for c in prefix_chars),
                        "x0": min(c["x0"] for c in prefix_chars),
                        "x1": max(c["x1"] for c in prefix_chars), "chars": prefix_chars}
        amount_piece = {**amount, "text": "4.527", "x0": min(c["x0"] for c in value_chars),
                        "x1": max(c["x1"] for c in value_chars), "chars": value_chars}
        words = [*words[:index], prefix_piece, amount_piece, *words[index + 2:]]
    for word in words:
        chars = word.get("chars")
        if (
            not chars
            or len(chars) != len(word["text"])
            or NUMBER.fullmatch(word["text"])
            or not any(char.isdigit() for char in word["text"])
        ):
            result.append(word)
            continue
        candidates = []
        for split in range(1, len(chars)):
            left_text, right_text = word["text"][:split], word["text"][split:]
            two_prices = NUMBER.fullmatch(left_text) and NUMBER.fullmatch(right_text)
            price_trend = NUMBER.fullmatch(left_text) and right_text in {
                "+", "++", "+++", "-", "--", "---", "=", "n.d."
            }
            label_price = (
                re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", left_text)
                and not left_text[-1].isdigit()
                and left_text[-1] != "."
                and NUMBER.fullmatch(right_text)
            )
            if not (two_prices or price_trend or label_price):
                continue
            left, right = piece(word, chars[:split]), piece(word, chars[split:])
            for headers in columns:
                for column in (0, 1):
                    if (
                        two_prices
                        and aligned(left, headers[column])
                        and aligned(right, headers[column + 1])
                    ):
                        candidates.append((left, right))
                if (
                    price_trend
                    and aligned(left, headers[2])
                    and (
                        right_text != "n.d."
                        or right["x0"] > headers[2]["x1"] + 5
                    )
                ):
                    candidates.append((left, right))
                if (
                    label_price
                    and left["x0"] < headers[0]["x0"] - 6
                    and aligned(right, headers[0])
                ):
                    candidates.append((left, right))
        # Ambiguous glyph partitioning stays unresolved for source review.
        result.extend(candidates[0] if len(candidates) == 1 else (word,))
    return result


def _audited_june_2012_font_runs(words, url, body_sha, page_no, width):
    """Join audited heading and market glyph runs in one immutable original.

    A different file, column, baseline, font or actual inter-word gap never
    inherits a corrected product identity from the audited PDF.
    """
    if url != JUNE_2012_FONT_RUN_URL or body_sha != JUNE_2012_FONT_RUN_SHA:
        return words
    expected_markets = JUNE_2012_MARKET_FONT_RUN_COUNTS.get(page_no)
    if expected_markets is not None:
        market_pairs = []
        for i, left_word in enumerate(words):
            if left_word["text"] != "Frigorífi":
                continue
            right_word = words[i + 1] if i + 1 < len(words) else None
            expected_x = (84.83, 358.07 if page_no == 21 else 358.16)
            if (
                right_word is None or right_word["text"] != "co"
                or not any(abs(left_word["x0"] - x) <= 0.12 for x in expected_x)
                or left_word["x0"] >= width or right_word["x1"] >= width
                or left_word["fontname"] != "ArialMT"
                or right_word["fontname"] != "ArialMT"
                or abs(left_word["size"] - 7.6) > 0.01
                or abs(right_word["size"] - 7.6) > 0.01
                or abs(left_word["top"] - right_word["top"]) > 0.12
                or not -0.17 <= right_word["x0"] - left_word["x1"] <= -0.13
                or not left_word.get("chars") or left_word["chars"][-1]["text"] != "ﬁ"
                or not right_word.get("chars")
                or [char["text"] for char in right_word["chars"]] != ["c", "o"]
            ):
                raise ValueError(f"Audited 2012 market glyph geometry changed on PDF page {page_no}")
            market_pairs.append((i, left_word, right_word))
        if len(market_pairs) != expected_markets:
            raise ValueError(f"Audited 2012 market glyph count changed on PDF page {page_no}")
        replacements = {
            i: {**left_word, "text": "Frigorífico", "x1": right_word["x1"],
                "chars": left_word["chars"] + right_word["chars"]}
            for i, left_word, right_word in market_pairs
        }
        removed = {i + 1 for i, _, _ in market_pairs}
        words = [replacements.get(i, word) for i, word in enumerate(words) if i not in removed]
    specification = JUNE_2012_FONT_RUNS.get(page_no)
    if specification is None:
        return words
    left_text, right_text, left_x, right_x, top = specification
    left = [
        (i, word) for i, word in enumerate(words)
        if word["text"] == left_text
        and abs(word["x0"] - left_x) <= 0.12
        and abs(word["top"] - top) <= 0.12
        and word["fontname"] == "Arial-BoldMT"
    ]
    right = [
        (i, word) for i, word in enumerate(words)
        if word["text"] == right_text
        and abs(word["x0"] - right_x) <= 0.12
        and abs(word["top"] - top) <= 0.12
        and word["fontname"] == "ArialMT"
    ]
    if len(left) != 1 or len(right) != 1:
        raise ValueError(f"Audited 2012 heading font runs changed on PDF page {page_no}")
    li, lw = left[0]
    ri, rw = right[0]
    if (
        li == ri or li > ri
        or lw["x0"] >= width / 2 or rw["x1"] >= width / 2
        or abs(lw["top"] - rw["top"]) > 0.12
        or not -0.3 <= rw["x0"] - lw["x1"] <= 0.3
        or len(rw["text"]) != 1
        or not lw.get("chars") or not rw.get("chars")
    ):
        raise ValueError(f"Audited 2012 heading glyph geometry changed on PDF page {page_no}")
    merged = {
        **lw,
        "text": lw["text"] + rw["text"],
        "x1": rw["x1"],
        "chars": lw["chars"] + rw["chars"],
    }
    return [merged if i == li else word for i, word in enumerate(words) if i != ri]


def _native_column(
    lines, headers, category, period, page_no, table_no, side, exceptions,
    legacy_wrapping=False, january_2017_market_wrap=False,
    december_2022_popayan_wrap=False,
    november_2016_medellin_wrap=False,
    august_2015_medellin_wrap=False,
    reviewed_cotinuacion=False,
    may2013_white_corn_heading=False,
):
    result = []
    boundary = headers[0]["x0"] - 6
    product = ""
    block = []
    continuation = False
    recovered_heading = None

    def flush():
        if not block:
            return
        anchors = []
        labels = []
        for number, line in block:
            label = clean(" ".join(w["text"] for w in line if w["x0"] < boundary))
            def cell(word, header):
                center = (word["x0"] + word["x1"]) / 2
                return header["x0"] - 12 <= center <= header["x1"] + 12
            # Three native dash cells report no monetary observation. Retain
            # the named market for review without borrowing a neighboring quote.
            cells = [w for w in line if w["x0"] >= boundary]
            unavailable = (
                bool(label) and len(cells) == 4
                and [w["text"] for w in cells[:3]] == ["-", "-", "-"]
                and cells[3]["text"] in {"n.d.", "+", "++", "+++", "-", "--", "---", "="}
                and all(cell(cells[i], headers[i]) for i in (0, 1, 2))
                and cells[3]["x0"] > headers[2]["x1"] + 5
            )
            if unavailable:
                if labels and labels[-1][0] == number - 1 and not labels[-1][3]:
                    raise ValueError(
                        f"Weekly PDF unresolved unavailable market wrap at page {page_no}: "
                        f"{labels[-1]} / {label}"
                    )
                result.append(_row(
                    product, label, None, None, None, cells[3]["text"], category, period,
                    f"PDF page {page_no},table {table_no},column {side},line {number}",
                    page=page_no, exceptions=exceptions,
                    allow_missing_identity=not re.search(r"\w", product),
                    allow_unavailable=True,
                ))
                continue
            values = [
                w for w in line if w["x0"] >= boundary and NUMBER.fullmatch(w["text"])
            ]
            if values:
                # The publisher prints two dot-only cells and a literal zero
                # mean for some unavailable markets. This is review, not COP 0.
                unpriced_zero = (
                    len(values) == 1 and values[0]["text"] == "0"
                    and len(cells) == 4
                    and [w["text"] for w in cells] == [".", ".", "0", "n.d."]
                    and cell(values[0], headers[2])
                    and all(cell(cells[i], headers[i]) for i in (0, 1))
                    and cells[3]["x0"] > headers[2]["x1"] + 5
                )
                missing_min = (
                    len(values) == 2
                    and headers[1]["x0"] <= values[0]["x0"] <= headers[1]["x1"]
                    and headers[2]["x0"] <= values[1]["x0"] <= headers[2]["x1"]
                )
                if len(values) != 3 and not missing_min and not unpriced_zero:
                    raise ValueError(
                        f"Weekly PDF unbound/incomplete monetary row at page {page_no}, column {side}, line {number}: {product!r} / {label!r} / {[v['text'] for v in values]}"
                    )
                anchors.append(
                    {
                        "number": number,
                        "top": values[0]["top"],
                        "values": values,
                        "missing_min": missing_min,
                        "unpriced_zero": unpriced_zero,
                        "labels": [],
                        "trend": clean(
                            " ".join(
                                w["text"] for w in line if w["x0"] > values[-1]["x1"]
                            )
                        ),
                    }
                )
            if label:
                labels.append((number, line[0]["top"], label, bool(values)))
        if not anchors and labels:
            raise ValueError(
                f"Weekly PDF named product has no prices at page {page_no}: {product!r} / {labels!r}"
            )
        market_leads = (
            NOVEMBER_2016_MARKET_LEADS
            if november_2016_medellin_wrap else JANUARY_2017_MARKET_LEADS
        )
        for label_index, (line_number, top, label, has_prices) in enumerate(labels):
            if august_2015_medellin_wrap and label == "Medellín, Central" and not has_prices:
                prior = [a for a in anchors if a["top"] < top]
                if prior and 0 < top - prior[-1]["top"] <= 7:
                    nxt = labels[label_index + 1] if label_index + 1 < len(labels) else None
                    if (nxt is None or nxt[0] != line_number + 1
                        or nxt[2] != "Mayorista de Antioquia" or not nxt[3]
                        or not 8.2 <= nxt[1] - top <= 8.5):
                        raise ValueError("Exact August 2015 market wrap changed")
                    matching = [a for a in anchors if abs(a["top"] - nxt[1]) <= 2.5]
                    if len(matching) != 1:
                        raise ValueError("Exact August 2015 monetary anchor changed")
                    matching[0]["labels"].append(label)
                    matching[0]["aug_exact_wrap"] = True
                    continue
            if (january_2017_market_wrap or november_2016_medellin_wrap) and label in market_leads and not has_prices:
                # Require the *next native line in this same product block and
                # physical column* to name the corresponding priced market.
                # Never borrow a quote across a column, heading, or intervening
                # market line when an archived layout differs from this one.
                next_line = labels[label_index + 1] if label_index + 1 < len(labels) else None
                if (
                    next_line is None
                    or next_line[0] != line_number + 1
                    or next_line[2] != market_leads[label]
                    or not next_line[3]
                    or not 6.5 <= next_line[1] - top <= (
                        7.3 if november_2016_medellin_wrap else 7.2
                    )
                ):
                    raise ValueError(
                        f"Weekly PDF unresolved Medellín market wrap at page {page_no}, "
                        f"column {side}: {product!r} / {label!r}"
                    )
                matching = [a for a in anchors if abs(a["top"] - next_line[1]) <= 2.5]
                if len(matching) != 1:
                    raise ValueError(
                        f"Weekly PDF ambiguous Medellín monetary anchor at page {page_no}, "
                        f"column {side}: {product!r} / {label!r}"
                    )
                matching[0]["labels"].append(label)
                continue
            # Historical prices align with the last line of a wrapped market;
            # newer layouts center them between its two lines. A nearest-row
            # heuristic would attach the first line to the preceding market.
            prior = [a for a in anchors if a["top"] < top]
            following = [a for a in anchors if a["top"] >= top - 2]
            aligned = [a for a in anchors if abs(a["top"] - top) <= 2.5]
            if aligned:
                anchor = min(aligned, key=lambda a: abs(a["top"] - top))
            elif prior and top - prior[-1]["top"] <= (14 if legacy_wrapping else 7):
                anchor = prior[-1]
            elif following:
                anchor = following[0]
            elif prior and 0 < top - prior[-1]["top"] <= 28:
                # Readable text can contain an orphan heading at a page end.
                # Keep its literal evidence and withhold the adjacent quote;
                # neither a guessed product nor repeated OCR resolves it.
                prior[-1].setdefault("unbound_tail_labels", []).append(label)
                continue
            else:
                raise ValueError(
                    f"Weekly PDF unresolved final market line at page {page_no}: {label}"
                )
            if abs(anchor["top"] - top) > 28:
                raise ValueError(
                    f"Weekly PDF unbound wrapped market at page {page_no}: {label}"
                )
            anchor["labels"].append(label)
        for anchor in anchors:
            values = ([None, None, 0.0] if anchor["unpriced_zero"] else
                      [_pdf_number(w["text"]) for w in anchor["values"]])
            missing_min = anchor["missing_min"]
            market_lines = anchor["labels"]
            market = " ".join(market_lines)
            if market_lines == ["Bogotá, D.C., Frigorífico Gua-", "dalupe"]:
                # The archived 2019 meat pages visibly split Guadalupe at the
                # line end. Preserve both printed lines for source review.
                market = "Bogotá, D.C., Frigorífico Guadalupe"
            elif december_2022_popayan_wrap and market_lines == [
                "Popayán, Plaza de mercado del barrio Bo-", "lívar"
            ]:
                # The source prints one market across two native lines. This
                # applies only to the audited, byte-identical 9 Dec original.
                market = "Popayán, Plaza de mercado del barrio Bolívar"
            record = _row(
                product,
                market,
                None if missing_min else values[0],
                values[0] if missing_min else values[1],
                values[1] if missing_min else values[2],
                anchor["trend"],
                category,
                period,
                f"PDF page {page_no},table {table_no},column {side},line {anchor['number']}",
                page=page_no,
                exceptions=exceptions,
                # A fully printed quote can have an empty market cell (DANE
                # 7–13 March 2020, printed page 37). Only a named product with
                # three literal prices reaches this review-only path; _row
                # withholds its price rather than borrowing a nearby market.
                # Page-start continuations may have complete printed prices
                # before their product heading; retain them without guessing it.
                allow_missing_identity=not re.search(r"\w", product) or not anchor["labels"],
                allow_missing_min=missing_min,
                allow_unpriced_zero=anchor["unpriced_zero"],
                allow_published_range_conflict=True,
            )
            if (
                may2013_white_corn_heading
                and page_no == 29 and table_no == 1 and side == 2
                and anchor["number"] in {27, 28}
                and product == "Maíz blanco cáscara"
                and market in {
                    "Medellín, Central Mayorista de Antioquia",
                    "San Vicente (Antioquia)",
                }
            ):
                record["source_locator"] += ":may2013-white-corn-heading-v1"
                record["details"].update({
                    "literal_product_heading": "Maíz blanco cáscara",
                    "native_heading_recovery": "exact_may2013_page29_column2_heading_before_wrapped_market_v1",
                })
            if market != " ".join(market_lines):
                record["details"]["literal_market_lines"] = market_lines
                record["details"]["native_market_join"] = (
                    "december_2022_popayan_line_wrap"
                    if december_2022_popayan_wrap and market.startswith("Popayán,")
                    else "explicit_guadalupe_line_wrap"
                )
            elif (january_2017_market_wrap or november_2016_medellin_wrap or (august_2015_medellin_wrap and anchor.get("aug_exact_wrap"))) and len(market_lines) == 2 and (
                market_lines[0] in market_leads
                and market_lines[1] == market_leads[market_lines[0]]
            ):
                record["details"]["literal_market_lines"] = market_lines
                record["details"]["native_market_join"] = (
                    "august_2015_same_column_leading_market_line"
                    if august_2015_medellin_wrap else (
                    "november_2016_same_column_leading_market_line"
                    if november_2016_medellin_wrap
                    else "january_2017_same_column_leading_market_line")
                )
            if recovered_heading:
                record["details"]["literal_product_heading"] = recovered_heading
                if re.search(r"\(comntinuaci[oó]n\)$", recovered_heading, re.IGNORECASE):
                    record["details"]["native_heading_recovery"] = (
                        "explicit_comntinuacion_annotation"
                    )
                elif recovered_heading == "Carne de cerdo, tocino ba- rriga":
                    record["details"]["native_heading_recovery"] = (
                        "printed_tocino_barriga_line_wrap"
                    )
                elif recovered_heading.startswith(('"', '“')) and recovered_heading.endswith(('"', '”')):
                    record["details"]["native_heading_recovery"] = (
                        "printed_wrapped_product_quotation"
                    )
            if anchor.get("unbound_tail_labels"):
                record["details"].update(
                    {
                        "quality_issue": "El final del bloque contiene texto sin una fila monetaria vinculable; se conserva el texto literal y la cotización adyacente para revisión.",
                        "literal_unbound_tail_labels": anchor["unbound_tail_labels"],
                        "literal_min": values[0],
                        "literal_max": values[1],
                        "literal_mean": values[2],
                    }
                )
                record["price"] = None
            result.append(record)

    column_left = min(
        (w["x0"] for line in lines for w in line if w["x0"] < boundary), default=0
    )
    for number, line in enumerate(lines, 1):
        literal = clean(" ".join(w["text"] for w in line))
        if literal == str(page_no):
            continue
        if ("variacion" in folded(literal) and "%" in literal) or folded(
            literal
        ).startswith(("tendencias", "fuente:", "nota:", "*")):
            break
        label_words = [w for w in line if w["x0"] < boundary]
        label = clean(" ".join(w["text"] for w in label_words))
        # DANE's older Futura tables use the Heavy face for product headings.
        bold = label and any(
            any(weight in w["fontname"].lower() for weight in ("bold", "heavy"))
            for w in label_words
        )
        numeric = any(w["x0"] >= boundary and NUMBER.fullmatch(w["text"]) for w in line)
        # Original reports occasionally forgot bold on a standalone product
        # heading. A short left-aligned label followed by a complete, separately
        # named market row has a different geometry from a wrapped market.
        following = lines[number] if number < len(lines) else []
        after_following = lines[number + 1] if number + 1 < len(lines) else []
        next_label = clean(" ".join(w["text"] for w in following if w["x0"] < boundary))
        next_values = [
            w for w in following if w["x0"] >= boundary and NUMBER.fullmatch(w["text"])
        ]
        previous_prices = [
            w
            for prior in lines[max(0, number - 3) : number - 1]
            for w in prior
            if w["x0"] >= boundary and NUMBER.fullmatch(w["text"])
        ]
        follows_centered_price = any(
            0 < line[0]["top"] - w["top"] <= (14 if legacy_wrapping else 7)
            for w in previous_prices
        )
        second_label = clean(
            " ".join(w["text"] for w in after_following if w["x0"] < boundary)
        )
        after_values = [
            w for w in after_following
            if w["x0"] >= boundary and NUMBER.fullmatch(w["text"])
        ]
        two_line_heading = bool(
            legacy_wrapping
            and
            next_label
            and 0 < following[0]["top"] - line[0]["top"] <= 10
            and not next_values
            and not re.search(r"[,.(]", next_label)
            and len(after_values) == 3
            and re.search(r"[,.(]", second_label)
        )
        # The 24–30 Dec 2022 original, page 36, prints a Book-face
        # '"Papa R-12 negra' heading with its closing quote on a separate line.
        # Require that exact quote geometry followed by a named monetary row;
        # an isolated punctuation mark cannot supply a product identity.
        wrapped_quotation = bool(
            label.startswith(('"', '“'))
            and re.search(r"\w", label)
            and next_label == ('"' if label.startswith('"') else '”')
            and not next_values
            and 0 < following[0]["top"] - line[0]["top"] <= 14
            and len(after_values) == 3
            and re.search(r"[,.(]", second_label)
        )
        meat_heading = (
            legacy_wrapping
            and category == "carnes"
            and label.startswith("Carne de ")
        )
        plain_heading = bool(
            label
            and re.search(r"\w", label)
            and (not follows_centered_price or meat_heading)
            and not numeric
            and not bold
            and (
                meat_heading
                or not re.search(
                    r"[,.(]",
                    re.sub(r"\((?:bolsita|caja)\)", "", label, flags=re.IGNORECASE),
                )
            )
            and label_words[0]["x0"] <= column_left + 3
            and max(w["x1"] for w in label_words)
            < column_left + (boundary - column_left) * (0.98 if legacy_wrapping else 0.85)
            and (
                two_line_heading
                or wrapped_quotation
                or (
                    len(next_values) == 3
                    and re.search(r"[,.(]", next_label)
                    and abs(following[0]["top"] - next_values[0]["top"]) <= 2
                )
            )
        )
        may2013_native_heading = False
        if may2013_white_corn_heading and label == "Maíz blanco cáscara":
            second_following = lines[number + 2] if number + 2 < len(lines) else []
            second_label = clean(" ".join(w["text"] for w in after_following if w["x0"] < boundary))
            third_label = clean(" ".join(w["text"] for w in second_following if w["x0"] < boundary))
            third_values = [w for w in second_following if w["x0"] >= boundary and NUMBER.fullmatch(w["text"])]
            second_values = [w for w in after_following if w["x0"] >= boundary and NUMBER.fullmatch(w["text"])]
            heading_geometry = (
                bool(label_words)
                and abs(label_words[0]["x0"] - 320.7874) < 0.05
                and abs(label_words[0]["top"] - 342.8563) < 0.05
                and [w["text"] for w in label_words] == ["Maíz", "blanco", "cáscara"]
                and all(w["fontname"] == "OKQNWG+ArialMT" for w in label_words)
                and next_label == "Medellín, Central"
                and second_label == "Mayorista de Antioquia"
                and not next_values
                and len(second_values) == 3
                and [w["text"] for w in second_values] == ["905", "905", "905"]
                and clean(" ".join(w["text"] for w in after_following if w["x0"] > second_values[-1]["x1"])) == "="
                and abs(following[0]["top"] - label_words[0]["top"] - 7.8) < 0.05
                and abs(after_following[0]["top"] - following[0]["top"] - 7.8) < 0.05
                and third_label == "San Vicente (Antioquia)"
                and [w["text"] for w in third_values] == ["1.000", "1.000", "1.000"]
                and clean(" ".join(w["text"] for w in second_following if third_values and w["x0"] > third_values[-1]["x1"])) == "++"
            )
            if not heading_geometry:
                raise ValueError("Audited May 2013 page-29 native heading geometry changed")
            may2013_native_heading = True
        if (
            label in ('"', '”')
            and not numeric
            and len(next_values) == 3
            and re.search(r"[,.(]", next_label)
        ):
            if (
                continuation
                and not block
                and product.startswith(('"', '“'))
                and label == ('"' if product.startswith('"') else '”')
            ):
                recovered_heading = clean(product + " " + label)
                product = clean(product[1:])
            else:
                # Preserve the following literal prices for review when the
                # opening title is absent, instead of borrowing an old title.
                flush()
                block = []
                product = ""
                recovered_heading = label
            continuation = False
            continue
        repeated_heading, repeated_continuation = _product_heading(
            label, reviewed_cotinuacion=reviewed_cotinuacion
        )
        if (
            label
            and not bold
            and not numeric
            and product
            and repeated_continuation
            and folded(repeated_heading) == folded(product)
            and len(next_values) == 3
        ):
            # DANE occasionally reprints the current product's continuation
            # heading in Book type on its own line. It labels the following
            # quotes, rather than forming part of the next market name.
            flush()
            block = []
            recovered_heading = label
            continuation = False
            continue
        if (
            label
            and not numeric
            and PRODUCT_CONTINUATION.fullmatch(label)
            and product
            and not block
        ):
            # The 2019 meat tables print this annotation on a separate line
            # beneath a complete product heading. It is not a new product.
            recovered_heading = clean(product + " " + label)
            continuation = False
            continue
        if bold and label_words[0]["x0"] > column_left + 25 and not numeric:
            # Centered section captions (e.g. Carne de cerdo) are not the
            # following left-aligned product's first line.
            flush()
            block = []
            product = ""
            continuation = False
            recovered_heading = None
            continue
        if bold or plain_heading or may2013_native_heading:
            flush()
            block = []
            heading, marked_continuation = _product_heading(
                label, reviewed_cotinuacion=reviewed_cotinuacion
            )
            wrapped_tocino = (
                continuation
                and product == "Carne de cerdo, tocino ba-"
                and label == "rriga"
                and bold
            )
            if marked_continuation:
                recovered_heading = clean(
                    (product + " " if continuation else "") + label
                )
            elif wrapped_tocino:
                # DANE 16–22 Feb 2019, PDF page 53, prints the final syllable
                # on a separate bold line. The hyphen is a line-break mark.
                recovered_heading = product + " " + label
            elif not continuation:
                recovered_heading = (
                    "Maíz blanco cáscara" if may2013_native_heading else None
                )
            if wrapped_tocino:
                product = "Carne de cerdo, tocino barriga"
            else:
                product = clean(product + " " + heading) if continuation else heading
            # A marked carryover can be followed immediately by a different
            # product with no intervening quote (DANE 31 Jan–6 Feb 2026,
            # PDF page 64). Only an unmarked heading may wrap onto the next.
            continuation = not marked_continuation
        else:
            block.append((number, line))
            continuation = False
    flush()
    return result


def _column_headers(words, width):
    minima = sorted(
        (word for word in words if folded(word["text"]) == "minimo"),
        key=lambda word: word["x0"],
    )
    if len(minima) not in (1, 2):
        return None
    columns = []
    for side, minimum in enumerate(minima):
        if len(minima) == 1 and minimum["x0"] >= width / 2:
            return None
        lo, hi = (0, width / 2) if side == 0 else (width / 2, width)
        headers = sorted(
            (
                word
                for word in words
                if lo < word["x0"] < hi
                and abs(word["top"] - minimum["top"]) < 3
                and folded(word["text"]) in {"minimo", "maximo", "medio"}
            ),
            key=lambda word: word["x0"],
        )
        if [folded(word["text"]) for word in headers] != ["minimo", "maximo", "medio"]:
            return None
        columns.append(headers)
    return columns


def _overprint_column_headers(page, top, bottom):
    """Recover exact overprinted headers; never repair monetary body text."""
    deduped = page.dedupe_chars(
        tolerance=0, extra_attrs=("fontname", "size", "x1", "bottom")
    )
    if len(deduped.chars) == len(page.chars):
        return None
    words = deduped.extract_words(extra_attrs=["fontname", "size"])
    columns = _column_headers(
        [word for word in words if top <= word["top"] < bottom], page.width
    )
    if columns is None:
        return None
    attrs = ("upright", "text", "fontname", "size", "doctop", "x0", "x1", "bottom")
    remaining = Counter(tuple(char[attr] for attr in attrs) for char in deduped.chars)
    repaired_header = False
    for char in page.chars:
        key = tuple(char[attr] for attr in attrs)
        if remaining[key]:
            remaining[key] -= 1
            continue
        for side, headers in enumerate(columns):
            lo, hi = (0, page.width / 2) if side == 0 else (page.width / 2, page.width)
            if not lo < char["x0"] < hi:
                continue
            if char["top"] > max(header["bottom"] for header in headers) + 2 and char[
                "bottom"
            ] < min(bottom, page.height - 22):
                # Duplicated body digits/names need separate validation. Their
                # existence must not turn a header repair into a guessed price.
                return None
            if any(
                header["x0"] <= char["x0"] < header["x1"]
                and header["top"] <= char["top"] < header["bottom"]
                for header in headers
            ):
                repaired_header = True
    return columns if repaired_header else None


def _printed_monetary_period_headings(table_text):
    """Keep price-table dates; exclude only a separate, finished-grid graph month.

    Early bulletins put a monthly graph below the weekly price table on the
    same page. Its explicit graph caption and month are context, while any
    unclassified later date or contradictory monetary heading stays reviewable.
    """
    lines = table_text.splitlines()
    grid_line = next(
        (i for i, line in enumerate(lines) if "productos y mercados" in folded(line)),
        None,
    )
    headings = []
    for i, line in enumerate(lines):
        if not re.match(r"^\s*20\d{2}\s*\(", line):
            continue
        # Require the actual monthly graph caption immediately above this
        # month-only label, after the table's literal Tendencias terminator.
        # A weekly range, another price grid or an unidentified date is never
        # discarded merely because an earlier graph exists somewhere on page.
        adjacent_graph = any(
            re.match(r"^\s*gr[aá]fico\s+\d+", before, re.I)
            for before in lines[max(0, i - 3):i]
        )
        month_only = re.fullmatch(rf"\s*20\d{{2}}\s*\(\s*(?:{MONTH})\s*\)\s*", folded(line))
        finished_grid = grid_line is not None and any(
            re.match(r"^\s*tendencias\s*:", earlier, re.I)
            for earlier in lines[grid_line + 1:i]
        )
        later_grid = any(
            "productos y mercados" in folded(later)
            or "pesos por kilogramo" in folded(later)
            for later in lines[i + 1:]
        )
        if adjacent_graph and month_only and finished_grid and not later_grid:
            continue
        headings.extend(clean(match[0]) for match in re.finditer(r"20\d{2}\s*\([^)]+\)", line))
    return headings


def _aug2014_page43_table_period_override(url, body_sha, page_no, table_no, table_text, words):
    """Bind only the pinned Aug 2014 Cuadro 8 period before its printed grid."""
    if url != AUG2014_PAGE43_URL or page_no != 43 or table_no != 1:
        return None
    if body_sha != AUG2014_PAGE43_SHA:
        raise ValueError("Exact August 2014 page-43 source bytes changed")
    if not re.search(
        r"Cuadro\s+8\.\s*Mercados mayoristas\.\s*Precios de venta de productos procesados",
        table_text, re.IGNORECASE,
    ):
        raise ValueError("Exact August 2014 page-43 Cuadro 8 caption changed")
    labeled = [(
        " ".join(word["text"] for word in line),
        min(word["top"] for word in line),
        max(word["bottom"] for word in line),
    ) for line in _lines(words)]
    grid = [(text, top, bottom) for text, top, bottom in labeled
            if "productos y mercados" in folded(text)]
    trends = [(text, top, bottom) for text, top, bottom in labeled
              if re.search(r"\btendencias\s*:", folded(text))]
    article = [(text, top, bottom) for text, top, bottom in labeled
               if re.search(r"precios\s+de\s+la\s+panela", folded(text))]
    chart = [(text, top, bottom) for text, top, bottom in labeled
             if re.search(r"gr[aá]fico\s+8\b", folded(text))]
    tabla2 = [(text, top, bottom) for text, top, bottom in labeled
              if re.search(r"tabla\s+2\.\s*precios por kilo de la panela cuadrada blanca", folded(text))]
    if len(grid) != 1 or len(trends) != 1 or len(article) != 1 or len(chart) != 1 or len(tabla2) != 1:
        raise ValueError("Exact August 2014 page-43 grid/article boundary changed")
    grid_top = grid[0][1]
    trends_top, trends_bottom = trends[0][1], trends[0][2]
    article_top = article[0][1]
    if not (0 < grid_top < trends_top < trends_bottom < article_top):
        raise ValueError("Exact August 2014 page-43 table/article order changed")
    chart_top, chart_bottom = chart[0][1], chart[0][2]
    tabla2_top, tabla2_bottom = tabla2[0][1], tabla2[0][2]
    chart_dates = [(text, top, bottom) for text, top, bottom in labeled
                   if chart_bottom < top < tabla2_top
                   and re.search(r"2014\s*\(\s*12 de julio al 15 de agosto\s*\)", folded(text))]
    tabla2_dates = [(text, top, bottom) for text, top, bottom in labeled
                    if top > tabla2_bottom
                    and re.search(r"2014\s*\(\s*12 de julio al 15 de agosto\s*\)", folded(text))]
    if not (article_top < chart_top < chart_bottom < tabla2_top < tabla2_bottom
            and len(chart_dates) == 1 and len(tabla2_dates) == 1
            and chart_dates[0][1] < tabla2_top and tabla2_dates[0][1] > tabla2_bottom):
        raise ValueError("Exact August 2014 chart and later Tabla 2 boundary changed")

    # The only accepted period and unit are printed in the Cuadro 8 header,
    # above its own product/market grid and before the Trends terminator.
    header_lines = [(text, top, bottom) for text, top, bottom in labeled
                    if top < grid_top]
    header_text = "\n".join(text for text, _, _ in header_lines)
    headings = _printed_monetary_period_headings(header_text)
    if headings != [AUG2014_PAGE43_HEADER]:
        raise ValueError("Exact August 2014 page-43 printed table header changed")
    if not any("pesos por kilogramo" in folded(text)
               for text, _, _ in header_lines):
        raise ValueError("Exact August 2014 page-43 unit header changed")
    return headings


def _aug2013_page43_table_period_override(url, body_sha, page_no, table_no, table_text, words):
    """Keep the weekly Cuadro 8 heading separate from the panela article below it."""
    if url != AUG2013_PAGE43_URL or page_no != 43 or table_no != 1:
        return None
    if body_sha != AUG2013_PAGE43_SHA:
        raise ValueError("Exact August 2013 page-43 source bytes changed")
    if not re.search(
        r"Cuadro\s+8\.\s*Mercados mayoristas\.\s*Precios de venta de "
        r"productos procesados\s*\(conclusi[oó]n\)",
        table_text,
        re.IGNORECASE,
    ):
        raise ValueError("Exact August 2013 page-43 Cuadro 8 caption changed")

    labeled = [(
        " ".join(word["text"] for word in line),
        min(word["top"] for word in line),
        max(word["bottom"] for word in line),
    ) for line in _lines(words)]
    grid = [row for row in labeled if "productos y mercados" in folded(row[0])]
    trends = [row for row in labeled if re.search(r"\btendencias\s*:", folded(row[0]))]
    article = [row for row in labeled if re.search(r"precios\s+de\s+la\s+panela", folded(row[0]))]
    chart = [row for row in labeled if re.search(r"gr[aá]fico\s+8\b", folded(row[0]))]
    article_table = [row for row in labeled if re.search(
        r"tabla\s+1\.\s*precios por kilo de la panela cuadrada morena", folded(row[0])
    )]
    if any(len(rows) != 1 for rows in (grid, trends, article, chart, article_table)):
        raise ValueError("Exact August 2013 page-43 grid/article anchors changed")

    grid_top = grid[0][1]
    trends_top, trends_bottom = trends[0][1], trends[0][2]
    article_top, chart_top, table_top = article[0][1], chart[0][1], article_table[0][1]
    if not (0 < grid_top < trends_top < trends_bottom < article_top < chart_top < table_top):
        raise ValueError("Exact August 2013 page-43 grid/article order changed")

    header_text = "\n".join(text for text, top, _ in labeled if top < grid_top)
    headings = _printed_monetary_period_headings(header_text)
    if headings != [AUG2013_PAGE43_HEADER]:
        raise ValueError("Exact August 2013 page-43 printed table header changed")
    if "pesos por kilogramo" not in folded(header_text):
        raise ValueError("Exact August 2013 page-43 unit header changed")

    article_text = "\n".join(text for text, top, _ in labeled if top >= article_top)
    if (article_text.count(AUG2013_PAGE43_ARTICLE_PERIOD) < 2
            or "grafico 8" not in folded(article_text)
            or "tabla 1." not in folded(article_text)):
        raise ValueError("Exact August 2013 historical panela article changed")
    # This longer period is printed only in the separate graph and historical
    # article table below the finished wholesale-price grid.
    return headings


def _sep2013_page43_table_period_override(url, body_sha, page_no, table_no, table_text, words):
    """Exact-source table/article separation for the September 2013 page."""
    if url != SEP2013_PAGE43_URL or page_no != 43 or table_no != 1:
        return None
    if body_sha != SEP2013_PAGE43_SHA:
        raise ValueError("Exact September 2013 page-43 source bytes changed")
    if not re.search(r"Cuadro\s+8\.\s*Mercados mayoristas\.\s*Precios de venta de\s*productos procesados\s*\(conclusi[oó]n\)", table_text, re.I):
        raise ValueError("Exact September 2013 page-43 Cuadro caption changed")
    labeled = [(" ".join(w["text"] for w in line), min(w["top"] for w in line),
                max(w["bottom"] for w in line)) for line in _lines(words)]
    grid = [r for r in labeled if "productos y mercados" in folded(r[0])]
    trends = [r for r in labeled if re.search(r"\btendencias\s*:", folded(r[0]))]
    article = [r for r in labeled if re.fullmatch(r"precios\s+de\s+la\s+panela", folded(r[0]))]
    chart = [r for r in labeled if re.search(r"gr[aá]fico\s+9\.\s*comportamiento del precio", folded(r[0]))]
    article_table = [r for r in labeled if re.search(r"tabla\s+1\.\s*precios por kilo de la panela cuadrada blanca", folded(r[0]))]
    if any(len(rows) != 1 for rows in (grid, trends, article, chart, article_table)):
        raise ValueError("Exact September 2013 page-43 grid/article anchors changed")
    if not (grid[0][1] < trends[0][1] < trends[0][2] < article[0][1] < chart[0][1] < article_table[0][1]):
        raise ValueError("Exact September 2013 page-43 grid/article order changed")
    header_text = "\n".join(text for text, top, _ in labeled if top < grid[0][1])
    headings = _printed_monetary_period_headings(header_text)
    if headings != [SEP2013_PAGE43_HEADER]:
        raise ValueError("Exact September 2013 page-43 table date header changed")
    if folded(header_text).count("pesos por kilogramo") != 2:
        raise ValueError("Exact September 2013 page-43 kilogram headings changed")
    article_text = "\n".join(text for text, top, _ in labeled if top >= article[0][1])
    if (article_text.count("2013 (24 de agosto al 27 de septiembre)") < 2
            or "grafico 9" not in folded(article_text) or "tabla 1." not in folded(article_text)):
        raise ValueError("Exact September 2013 historical panela article changed")
    return headings


def parse_pdf(body, url, readings_by_page=None):
    import pdfplumber
    from .weekly_boundary_review import reviewed_article_bottom

    body_sha = sha256(body).hexdigest()
    if url == AUG2014_PAGE43_URL and body_sha != AUG2014_PAGE43_SHA:
        raise ValueError("Exact August 2014 weekly PDF bytes changed")
    if url == AUG2013_PAGE43_URL and body_sha != AUG2013_PAGE43_SHA:
        raise ValueError("Exact August 2013 weekly PDF bytes changed")
    reviewed_period = REVIEWED_PDF_PERIODS.get(url)
    if reviewed_period is not None and body_sha != reviewed_period[0]:
        raise ValueError("Reviewed weekly PDF period source bytes changed")
    if url == MAY2013_WHITE_CORN_URL and body_sha != MAY2013_WHITE_CORN_SHA:
        raise ValueError("Exact May 2013 weekly PDF bytes changed")
    if url == AUGUST_2015_WRAP_URL and body_sha != AUGUST_2015_WRAP_SHA:
        raise ValueError("Exact August 2015 PDF bytes changed")
    if url == JANUARY_2017_JAN13_URL and body_sha != JANUARY_2017_JAN13_SHA:
        raise ValueError("Audited January 13 2017 weekly PDF bytes changed")
    if (url == NOVEMBER_2016_MEDELLIN_WRAP_URL
            and body_sha != NOVEMBER_2016_MEDELLIN_WRAP_SHA):
        raise ValueError("Audited November 4 2016 weekly PDF bytes changed")
    def monetary_period(context):
        if reviewed_period is not None and reviewed_period[2].search(context):
            return reviewed_period[1]
        # One retained bulletin repeats a four-week caption on its monetary
        # tables. Its cover and same-week XLSX independently corroborate every
        # eligible PDF tuple except the separately quarantined row below.
        # Preserve the printed span; do not relax the ordinary weekly parser.
        if (url == NOVEMBER_2022_BULLETIN_URL
            and body_sha == NOVEMBER_2022_BULLETIN_SHA
            and "2022 (22 de octubre al 18 de noviembre)" in clean(context)):
            return NOVEMBER_2022_PRINTED_TABLE_PERIOD
        return _period(context)
    result = []
    failed = []
    legacy_pages = set()
    filename_period = _url_period(url)
    matching_filename_end_seen = False
    conflicting_filename_end_seen = False
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        texts = [page.extract_text() or "" for page in pdf.pages]
        july2012_review = url == JULY2012_CONFLICT_URL and body_sha == JULY2012_CONFLICT_SHA
        if url == JULY2012_CONFLICT_URL and body_sha != JULY2012_CONFLICT_SHA:
            raise ValueError("Exact July 2012 review source bytes changed")
        if july2012_review:
            if len(pdf.pages) != 34 or "19 de julio de 2012" not in texts[0]:
                raise ValueError("Exact July 2012 cover or page count changed")
            captions = []
            for pageno, page_text in enumerate(texts, 1):
                lines = [line.strip() for line in page_text.splitlines() if line.strip()]
                for index, line in enumerate(lines):
                    if re.match(r"Cuadro\s+\d+\.\s*Mercados mayoristas\.\s*Precios de venta de", line, re.I):
                        following = lines[index + 1] if index + 1 < len(lines) else ""
                        if following != JULY2012_TABLE_HEADING:
                            raise ValueError("Exact July 2012 monetary caption changed")
                        captions.append((pageno, line))
            if len(captions) != JULY2012_TABLE_COUNT:
                raise ValueError("Exact July 2012 monetary table count changed")
            page23 = folded(texts[22])
            if ("grafico 6. comportamiento del precio mayorista" not in page23
                or "2012 (junio 23 a julio 19)" not in page23
                or "2012 (julio 14 a 20)" not in page23):
                raise ValueError("Exact July 2012 page-23 graph/table context changed")
        if reviewed_period is not None:
            cover = pdf.pages[0].crop((0, 0, pdf.pages[0].width * .5,
                                       pdf.pages[0].height)).extract_text() or ""
            if (len(pdf.pages) != 44
                or not reviewed_period[4].search(cover)
                or len(reviewed_period[2].findall("\n".join(texts))) != reviewed_period[3]):
                raise ValueError("Reviewed weekly PDF cover or monetary captions changed")
        exceptions = _exceptions("\n".join(texts))
        # Some originals literally print a five-digit year on one continuation
        # page. The dated URL alone cannot validate that page. A separate native
        # monetary caption must corroborate the full range before retaining its
        # rows as unpriced review evidence; never repair or publish the bad year.
        verified_document_period = False
        if filename_period:
            for text in texts:
                for caption in re.finditer(
                    r"Cuadro\s+\d+\.\s*Mercados mayoristas\.\s*Precios de venta de\s+[^\n]+",
                    text, re.IGNORECASE,
                ):
                    try:
                        candidate = _period(text[caption.start():caption.start() + 550])
                    except ValueError:
                        continue
                    if candidate == filename_period:
                        verified_document_period = True
        for page_no, (page, text) in enumerate(zip(pdf.pages, texts), 1):
            if readings_by_page and page_no in readings_by_page:
                result.extend(
                    _ocr_page(readings_by_page[page_no], url, page_no, exceptions)
                )
                continue
            if len(re.sub(r"\W", "", text)) < 25:
                from .pdf_sources import has_table_sized_image

                if has_table_sized_image(page):
                    failed.append(page_no)
                continue
            # A readable DANE title does not make an image-only price table
            # readable. Require a large image and explicit publication context;
            # normal photographs/logos and fully readable monetary pages stay
            # on the native path.
            if len(re.sub(r"\W", "", text)) < 250 and re.search(
                r"sipsa|precios mayoristas", folded(text)
            ):
                from .pdf_sources import has_table_sized_image

                if has_table_sized_image(page):
                    failed.append(page_no)
                    continue
            # Multiple independent monetary tables can share one old PDF page.
            words = page.extract_words(extra_attrs=["fontname", "size"], return_chars=True)
            words = _audited_june_2012_font_runs(
                words, url, body_sha, page_no, page.width
            )
            starts = sorted(
                {
                    w["top"]
                    for w in words
                    if w["text"] == "Cuadro" and w["x0"] < page.width * 0.20
                }
            )
            for table_no, top in enumerate(starts, 1):
                bottom = starts[table_no] if table_no < len(starts) else page.height
                source_bottom = bottom
                bottom = reviewed_article_bottom(
                    url, body_sha, page_no, words, max(0, top - 1), bottom
                )
                section = page.crop((0, max(0, top - 1), page.width, bottom))
                table_text = section.extract_text() or ""
                caption = re.search(
                    r"Cuadro\s+\d+\.\s*Mercados mayoristas\.\s*Precios de venta de\s+([^\n]+)",
                    table_text,
                    re.IGNORECASE,
                )
                if not caption:
                    continue
                context = table_text[:550]
                printed_headings = _printed_monetary_period_headings(table_text)
                if july2012_review and page_no == 23:
                    if JULY2012_TABLE_HEADING not in printed_headings or JULY2012_GRAPH_HEADING not in printed_headings:
                        raise ValueError("Exact July 2012 page-23 monetary/graph headings changed")
                    printed_headings = [JULY2012_TABLE_HEADING]
                # The exact-source period guard also validates the distinct
                # historical article anchors below the Cuadro cutoff. Keep
                # those page words for its structural check while parsing only
                # the cropped table body above.
                period_local = [w for w in words if top <= w["top"] < source_bottom]
                exact_period_headings = _aug2014_page43_table_period_override(
                    url, body_sha, page_no, table_no, table_text, period_local
                )
                if exact_period_headings is None:
                    exact_period_headings = _aug2013_page43_table_period_override(
                        url, body_sha, page_no, table_no, table_text, period_local
                    )
                if exact_period_headings is None:
                    exact_period_headings = _sep2013_page43_table_period_override(
                        url, body_sha, page_no, table_no, table_text, period_local
                    )
                if exact_period_headings is not None:
                    printed_headings = exact_period_headings
                conflicting_printed_headings = (
                    len(set(printed_headings)) > 1
                    and not re.search(
                        r"20\d{2}\s*\([^)]+\)\s*[-–]\s*20\d{2}\s*\([^)]+\)",
                        context,
                    )
                )
                if conflicting_printed_headings:
                    # A 2019 Cuadro 6 page prints a month-long range next to
                    # the actual week. Only an explicitly printed weekly range
                    # agreeing with the dated URL may identify its rows; keep
                    # the contradictory caption for review below.
                    candidates = []
                    for heading in printed_headings:
                        try:
                            candidate = _period(heading)
                        except ValueError:
                            continue
                        if candidate == filename_period:
                            candidates.append(candidate)
                    if len(candidates) != 1:
                        raise ValueError(
                            f"Weekly PDF page {page_no} has conflicting printed periods"
                        )
                    period = candidates[0]
                else:
                    # Old two-column bulletins can place a separate chart
                    # before the Cuadro in text-stream order. Its four-week
                    # range may fall inside context[:550], while the actual
                    # monetary heading is the single anchored year/range line
                    # directly above the price grid. Keep multi-heading cases
                    # in the conflict path above.
                    before_grid = folded(table_text).split("productos y mercados", 1)[0]
                    period = (
                        monetary_period(printed_headings[0])
                        if len(printed_headings) == 1
                        and folded(printed_headings[0]) in before_grid
                        else monetary_period(context)
                    )
                unverified_printed_period = period is None
                if unverified_printed_period:
                    if not verified_document_period:
                        raise ValueError(
                            f"Weekly PDF page {page_no} has no verified monetary-table period"
                        )
                    # Date fields identify the corroborated document's review
                    # record, not a verified observation on this malformed page.
                    period = filename_period
                # DANE's July 28 bulletin cover and archive identify July
                # 22–28, and every eligible native price tuple agrees with
                # its same-week XLSX annex. All 52 monetary captions repeat
                # the preceding week. This exception is bound to both exact
                # original bytes and URL; retain the printed dates per row.
                july_caption_correction = (
                    url == JULY_2023_BULLETIN_URL
                    and body_sha == JULY_2023_BULLETIN_SHA
                    and filename_period == JULY_2023_OFFICIAL_PERIOD
                    and period == JULY_2023_PRINTED_TABLE_PERIOD
                )
                november_caption_correction = (
                    url == NOVEMBER_2022_BULLETIN_URL
                    and body_sha == NOVEMBER_2022_BULLETIN_SHA
                    and filename_period == NOVEMBER_2022_OFFICIAL_PERIOD
                    and period == NOVEMBER_2022_PRINTED_TABLE_PERIOD
                )
                audited_caption_correction = july_caption_correction or november_caption_correction
                period_conflict = (
                    filename_period is not None and period[1] != filename_period[1]
                    and not audited_caption_correction
                )
                if filename_period is not None and not unverified_printed_period:
                    matching_filename_end_seen |= not period_conflict
                    conflicting_filename_end_seen |= period_conflict
                printed_period_heading = next(
                    (
                        clean(line) for line in table_text.splitlines()
                        if re.match(r"^\s*20\d{2}\s*\(", line)
                    ),
                    None,
                ) if period_conflict else None
                category = re.sub(
                    r"\s*\((?:continuaci[oó]n|conclusi[oó]n)\)",
                    "",
                    caption[1],
                    flags=re.IGNORECASE,
                ).strip()
                local = [w for w in words if top <= w["top"] < bottom]
                columns = _column_headers(local, page.width)
                recovered_headers = False
                inherited_headers = False
                if columns is None or (
                    len(columns) == 1
                    and folded(context).count("pesos por kilogramo") != 1
                ):
                    repaired = _overprint_column_headers(page, top, bottom)
                    if repaired is not None:
                        columns = repaired
                        recovered_headers = True
                if (
                    columns is None
                    and page_no > 1
                    and table_no == 1
                    and len(starts) == 1
                    and "(continuacion)" in folded(caption[0])
                    and "pesos por kilogramo" not in folded(context)
                ):
                    # Some final continuation pages omit the repeated column
                    # headings and unit. The immediately preceding page can
                    # supply them only when it prints the same table and week.
                    prior_text = texts[page_no - 2]
                    prior_page = pdf.pages[page_no - 2]
                    prior_caption = re.search(
                        r"Cuadro\s+\d+\.\s*Mercados mayoristas\.\s*Precios de venta de\s+([^\n]+)",
                        prior_text,
                        re.IGNORECASE,
                    )
                    year_word = next(
                        (
                            w for w in local
                            if re.fullmatch(r"20\d{2}", w["text"])
                            and top < w["top"] < top + 30
                        ),
                        None,
                    )
                    if (
                        prior_caption
                        and prior_page.width == page.width
                        and len(re.findall(r"\bCuadro\s+\d+\.", prior_text)) == 1
                        and folded(prior_caption[0]) == folded(caption[0])
                        and monetary_period(prior_text[prior_caption.start():prior_caption.start()+550]) == period
                        and "pesos por kilogramo" in folded(prior_text[prior_caption.start():prior_caption.start()+550])
                        and year_word
                    ):
                        prior_columns = _column_headers(
                            prior_page.extract_words(extra_attrs=["fontname", "size"]),
                            prior_page.width,
                        )
                        if prior_columns and len(prior_columns) == 2:
                            line_bottom = max(
                                w["bottom"] for w in local
                                if abs(w["top"] - year_word["top"]) < 2
                            )
                            columns = [
                                [
                                    {**header, "top": line_bottom - 8, "bottom": line_bottom}
                                    for header in side_headers
                                ]
                                for side_headers in prior_columns
                            ]
                            inherited_headers = True
                # Text-stream order can interleave a chart printed below the
                # price table ahead of its caption. Currency/unit evidence
                # belongs to the Cuadro's geometric header, not context[:550].
                header_context = ""
                if columns:
                    header_bottom = max(h["bottom"] for side_headers in columns for h in side_headers)
                    header_context = folded(page.crop((
                        0, max(0, top - 1), page.width,
                        min(page.height, header_bottom + 2),
                    )).extract_text() or "")
                if columns is None or (
                    "pesos por kilogramo" not in header_context
                    and not inherited_headers
                ):
                    failed.append(page_no)
                    continue
                if len(columns) == 1 and (
                    header_context.count("pesos por kilogramo") != 1
                ):
                    failed.append(page_no)
                    continue
                table_exceptions = exceptions
                if (url == AUG2013_PAGE43_URL and body_sha == AUG2013_PAGE43_SHA
                        and page_no == 43 and table_no == 1):
                    if header_context.count("pesos por kilogramo") != 2:
                        raise ValueError("Exact August 2013 page-43 kilogram headings changed")
                    table_exceptions = {**exceptions, "exact_kilogram_products": {"vinagre"}}
                sep2013_page43 = (url == SEP2013_PAGE43_URL and body_sha == SEP2013_PAGE43_SHA
                                  and page_no == 43 and table_no == 1)
                if sep2013_page43:
                    if header_context.count("pesos por kilogramo") != 2:
                        raise ValueError("Exact September 2013 page-43 kilogram headings changed")
                    table_exceptions = {**exceptions, "exact_kilogram_products": {"vinagre"}}
                local = _split_joined_price_words(local, columns, sep2013_page43=sep2013_page43)
                legacy_wrapping = any(
                    folded(word["text"]) == "precio"
                    and word["top"] < columns[0][0]["top"]
                    and columns[0][0]["top"] - word["top"] < 30
                    for word in local
                )
                if legacy_wrapping:
                    legacy_pages.add(page_no)
                for side, headers in enumerate(columns, 1):
                    lo, hi = (
                        (0, page.width / 2)
                        if side == 1
                        else (page.width / 2, page.width)
                    )
                    body_words = [
                        w
                        for w in local
                        if w.get("upright", True)
                        and lo + (page.width * 0.04 if side == 1 else 1)
                        < w["x0"]
                        < hi - 7
                        and w["top"] > max(h["bottom"] for h in headers) + 2
                        and w["bottom"] < min(bottom, page.height - 22)
                    ]
                    try:
                        column_rows = _native_column(
                            _lines(body_words),
                            headers,
                            category,
                            period,
                            page_no,
                            table_no,
                            side,
                            table_exceptions,
                            legacy_wrapping=legacy_wrapping,
                            january_2017_market_wrap=(
                                JANUARY_2017_MARKET_WRAP_ORIGINALS.get(url) == body_sha
                            ),
                            december_2022_popayan_wrap=(
                                url == DECEMBER_2022_POPAYAN_WRAP_URL
                                and body_sha == DECEMBER_2022_POPAYAN_WRAP_SHA
                            ),
                            august_2015_medellin_wrap=(
                                url == AUGUST_2015_WRAP_URL and body_sha == AUGUST_2015_WRAP_SHA
                            ),
                            november_2016_medellin_wrap=(
                                url == NOVEMBER_2016_MEDELLIN_WRAP_URL
                                and body_sha == NOVEMBER_2016_MEDELLIN_WRAP_SHA
                                and 30 <= page_no <= 36
                            ),
                            reviewed_cotinuacion=_reviewed_cotinuacion_source(
                                url, body_sha, page_no, table_no, side, category, period
                            ),
                            may2013_white_corn_heading=(
                                url == MAY2013_WHITE_CORN_URL and body_sha == MAY2013_WHITE_CORN_SHA
                                and page_no == 29 and table_no == 1 and side == 2
                            ),
                        )
                        if (url == JUNE_2012_FONT_RUN_URL
                            and body_sha == JUNE_2012_FONT_RUN_SHA):
                            for row in column_rows:
                                if (page_no in JUNE_2012_MARKET_FONT_RUN_COUNTS
                                    and row["market"] in JUNE_2012_MARKET_NAMES):
                                    if row["price"] is None:
                                        raise ValueError("Audited 2012 market quote became unpriced")
                                    row["details"].update({
                                        "literal_market_font_runs": ["Frigoríﬁ", "co"],
                                        "native_market_recovery": "exact_2012_adjacent_ligature_run",
                                    })
                                audited = JUNE_2012_REPAIRED_ROWS.get(row["source_locator"])
                                if audited is None:
                                    continue
                                name, literal_runs = audited
                                if row["product_name"] != name or row["price"] is None:
                                    raise ValueError(
                                        "Audited 2012 font-run quote identity changed at "
                                        + row["source_locator"]
                                    )
                                row["details"].update({
                                    "literal_product_heading": name,
                                    "literal_heading_font_runs": literal_runs,
                                    "native_heading_recovery": "exact_2012_adjacent_font_run",
                                })
                        if july2012_review:
                            for row in column_rows:
                                literal_mean = row["price"]
                                details = row["details"]
                                details.update({
                                    "quality_issue": JULY2012_REVIEW_REASON,
                                    "literal_min": row["min"],
                                    "literal_max": row["max"],
                                    "literal_mean": literal_mean,
                                    "literal_printed_period_heading": JULY2012_TABLE_HEADING,
                                    "literal_filename_period_start": filename_period[0].isoformat(),
                                    "literal_filename_period_end": filename_period[1].isoformat(),
                                    "literal_document_reference_day": "2012-07-19",
                                    "source_period_resolution": "unresolved_source_conflict_review_only",
                                })
                                row["price"] = None
                                row["date"] = None
                                row["period_start"] = None
                        if audited_caption_correction:
                            for row in column_rows:
                                row["date"] = filename_period[1].isoformat()
                                row["period_start"] = filename_period[0].isoformat()
                                row["details"].update({
                                    "period_start": filename_period[0].isoformat(),
                                    "period_end": filename_period[1].isoformat(),
                                    "literal_printed_period_start": period[0].isoformat(),
                                    "literal_printed_period_end": period[1].isoformat(),
                                    "source_period_resolution": (
                                        "November 12–18 official archive, cover, and exact same-week annex monetary tuple parity; exact PDF SHA"
                                        if november_caption_correction else
                                        "July 22–28 official archive, cover, and exact same-week annex monetary tuple parity; exact PDF SHA"
                                    ),
                                    "corroborating_annex_sha256": (
                                        NOVEMBER_2022_MATCHING_ANNEX_SHA if november_caption_correction
                                        else JULY_2023_MATCHING_ANNEX_SHA
                                    ),
                                })
                                row["details"]["source_note"] += (
                                    " La tabla imprime 22 de octubre–18 de noviembre; la portada "
                                    "y el anexo oficial verifican la semana del 12–18 de noviembre."
                                    if november_caption_correction else
                                    " El encabezado de la tabla imprime 15–21 de julio por error; "
                                    "la portada, el índice y el anexo oficial corresponden al 22–28 de julio."
                                )
                                if (november_caption_correction
                                    and row["source_locator"] == "PDF page 55,table 1,column 2,line 44"
                                    and row["product_id"] == "rabadillas-de-pollo"
                                    and row["market"] == "Villavicencio, CAV"):
                                    row["details"].update({
                                        "quality_issue": "El anexo que verifica la semana no incluye esta fila; su precio literal se conserva para revisión de fecha.",
                                        "literal_min": row["min"], "literal_max": row["max"],
                                        "literal_mean": row["price"],
                                        "unverified_weekly_date": True,
                                    })
                                    row["price"] = None
                        if recovered_headers:
                            for row in column_rows:
                                row["details"]["native_header_recovery"] = (
                                    "exact_overprinted_glyphs"
                                )
                        if inherited_headers:
                            for row in column_rows:
                                row["details"]["native_header_recovery"] = (
                                    "same_table_previous_page"
                                )
                                row["details"]["native_unit_evidence_page"] = page_no - 1
                        if unverified_printed_period:
                            for row in column_rows:
                                details = row["details"]
                                issue = (
                                    "El encabezado de esta tabla no contiene un periodo "
                                    "semanal verificable; la fecha del documento está "
                                    "corroborada en otra tabla, pero estas cifras "
                                    "literales se conservan sin publicar para revisión."
                                )
                                details["quality_issue"] = (
                                    f"{details['quality_issue']} {issue}"
                                    if details.get("quality_issue") else issue
                                )
                                details.update({
                                    "literal_min": row["min"],
                                    "literal_max": row["max"],
                                    "literal_mean": details.get("literal_mean", row["price"]),
                                    "literal_printed_table_context": context,
                                    "period_evidence": "corroborated document range; this page unverified",
                                    "source_filename_period_start": filename_period[0].isoformat(),
                                    "source_filename_period_end": filename_period[1].isoformat(),
                                })
                                row["price"] = None
                        if period_conflict and not july2012_review:
                            for row in column_rows:
                                details = row["details"]
                                issue = (
                                    "El periodo impreso de esta tabla contradice el "
                                    "rango explícito del archivo publicado; se conserva "
                                    "la fecha y el precio literales para revisión."
                                )
                                details["quality_issue"] = (
                                    f"{details['quality_issue']} {issue}"
                                    if details.get("quality_issue") else issue
                                )
                                details.update({
                                    "literal_min": row["min"],
                                    "literal_max": row["max"],
                                    "literal_mean": details.get("literal_mean", row["price"]),
                                    "literal_printed_period_heading": printed_period_heading,
                                    "source_filename_period_start": filename_period[0].isoformat(),
                                    "source_filename_period_end": filename_period[1].isoformat(),
                                })
                                row["price"] = None
                        if conflicting_printed_headings:
                            for row in column_rows:
                                details = row["details"]
                                issue = (
                                    "El encabezado impreso contiene periodos "
                                    "contradictorios; se conserva la cotización "
                                    "literal para revisión."
                                )
                                details["quality_issue"] = (
                                    f"{details['quality_issue']} {issue}"
                                    if details.get("quality_issue") else issue
                                )
                                details.update({
                                    "literal_min": row["min"],
                                    "literal_max": row["max"],
                                    "literal_mean": details.get("literal_mean", row["price"]),
                                    "literal_printed_period_headings": printed_headings,
                                    "source_filename_period_start": filename_period[0].isoformat(),
                                    "source_filename_period_end": filename_period[1].isoformat(),
                                })
                                row["price"] = None
                        result.extend(column_rows)
                    except ValueError as error:
                        if str(error).startswith(
                            (
                                "Weekly PDF unbound",
                                "Weekly PDF unresolved",
                                "Weekly PDF named product has no prices",
                            )
                        ):
                            failed.append(page_no)
                        else:
                            raise
    if conflicting_filename_end_seen and not matching_filename_end_seen:
        if not july2012_review or not result or any(row["price"] is not None or row["date"] is not None for row in result):
            from .worker import SourceDateMismatch

            raise SourceDateMismatch("Weekly printed period conflicts with the dated source URL")
    if failed:
        raise NormalExtractionFailed(failed)
    if not result:
        raise ValueError(
            "Weekly PDF native extraction failed: no supported monetary tables; original requires layout/OCR review"
        )
    # The first 2012 reports sometimes omit a product heading altogether. Two
    # different values for the same literal product/market reveal an ambiguous
    # block. Preserve every row as review; never invent the absent heading.
    seen = {}
    ambiguous = set()
    orphaned_products = {
        row["product_name"]
        for row in result
        if row["details"].get("literal_unbound_tail_labels")
    }
    for row in result:
        identity = (row["product_name"], row["market"], row["date"], row["unit"])
        values = (
            row["min"],
            row["max"],
            row["price"] or row["details"].get("literal_mean"),
        )
        if identity in seen and seen[identity] != values:
            ambiguous.add(row["product_name"])
        seen[identity] = values
    for row in result:
        if row["product_name"] in ambiguous or row["product_name"] in orphaned_products:
            issue = (
                "El bloque contiene un encabezado final sin filas vinculables; las cotizaciones con ese producto, incluidas sus continuaciones, se conservan para revisión."
                if row["product_name"] in orphaned_products
                else "El bloque repite mercados con precios distintos y no permite verificar un encabezado de producto único; se conservan las cifras literales para revisión."
            )
            row["details"].update(
                {
                    "quality_issue": issue,
                    "literal_min": row["min"],
                    "literal_max": row["max"],
                    "literal_mean": row["price"] or row["details"].get("literal_mean"),
                }
            )
            row["price"] = None
    by_page = {}
    for row in result:
        by_page.setdefault(row["source_page"], []).append(row)
    unreadable_pages = [
        page for page, rows in by_page.items()
        if page in legacy_pages
        and len(rows) >= 10
        and all(row["price"] is None for row in rows)
    ]
    if len(unreadable_pages) >= 2:
        # Multiple entirely unresolved monetary pages indicate a document
        # layout the native parser has not safely recovered.
        raise NormalExtractionFailed(unreadable_pages)
    if url == JUNE_2012_FONT_RUN_URL and body_sha == JUNE_2012_FONT_RUN_SHA:
        market_counts = Counter(
            row["source_page"] for row in result
            if row["details"].get("native_market_recovery") == "exact_2012_adjacent_ligature_run"
        )
        if market_counts != JUNE_2012_MARKET_FONT_RUN_COUNTS:
            raise ValueError("Audited 2012 market quote bindings changed")
        if any("Frigorífi co" in row["market"] for row in result):
            raise ValueError("Audited 2012 market glyphs remain unbound")
    if url == AUGUST_2015_WRAP_URL:
        if (len(result) != 4472
            or sum(row["price"] is not None for row in result) != 4335
            or len({row["source_locator"] for row in result}) != 4472
            or sha256(json.dumps(
                result, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), default=str,
            ).encode("utf-8")).hexdigest() != AUGUST_2015_WRAP_ROWS_SHA):
            raise ValueError("Exact August 2015 whole weekly grid changed")
    if url == JANUARY_2017_JAN13_URL:
        if (len(result) != 4674
            or sum(row["price"] is not None for row in result) != 4523
            or len({row["source_locator"] for row in result}) != 4674
            or sha256(json.dumps(
                result, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), default=str,
            ).encode("utf-8")).hexdigest() != JANUARY_2017_JAN13_ROWS_SHA):
            raise ValueError("Audited January 13 2017 whole weekly grid changed")
    if url == NOVEMBER_2016_MEDELLIN_WRAP_URL:
        if (len(result) != 4709
            or sum(row["price"] is not None for row in result) != 4560
            or len({row["source_locator"] for row in result}) != 4709
            or sha256(json.dumps(
                result, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), default=str,
            ).encode("utf-8")).hexdigest() != NOVEMBER_2016_MEDELLIN_WRAP_ROWS_SHA):
            raise ValueError("Audited November 4 2016 whole weekly grid changed")
    return result


def parse(body, url, kind):
    if kind in INDEX_KINDS:
        return []
    if kind == "dane-weekly-xlsx":
        return parse_workbook(body, url)
    if kind == "dane-weekly-pdf":
        rows = parse_pdf(body, url)
        if url == "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_16jun_20jun_2014.pdf":
            from .panela_article_official import official_rows
            rows = list(rows) + official_rows(body, url)
        elif url == AUG2014_PAGE43_URL:
            # Separate printed article single prices from this PDF's Cuadro 8 quotes.
            from .panela_article_aug2014_official import official_rows
            rows = list(rows) + official_rows(body, url)
        elif url == AUG2013_PAGE43_URL:
            # Two exact Huevo rojo extra prices are stated as per-unit in the
            # same immutable original's page-27 narrative; constrain that
            # correction to the two native review rows before appending the
            # separate 60-cell article series.
            from .aug2013_huevo_extra_unit import apply as apply_huevo_extra_unit
            rows = apply_huevo_extra_unit(body, url, rows)
            # Article tables are a distinct series; weekly Cuadro 8 rows remain intact.
            from .panela_article_aug2013_official import official_rows
            rows = list(rows) + official_rows(body, url)
        return rows
    raise ValueError("Unsupported weekly source kind")


def _ocr_page(reading, url, page_no, document_exceptions):
    """Only agreed literal OCR tables with explicit weekly monetary headings."""
    text = clean(reading.get("text", ""))
    if not re.search(r"mercados mayoristas.*precios de venta", folded(text)):
        # Fully scanned narrative pages may have been required to find tables.
        if not reading.get("tables"):
            return []
        raise ValueError(f"Weekly OCR page {page_no} lacks a monetary-table caption")
    monetary_caption = re.search(
        r"mercados mayoristas.*?precios de venta", folded(text)
    )
    period = _period(text[monetary_caption.start() : monetary_caption.start() + 550])
    if period is None or "pesos por kilogramo" not in folded(text):
        raise ValueError(f"Weekly OCR page {page_no} lacks explicit period/unit")
    _verify_url(period, url)
    category_match = re.search(
        r"precios de venta de (.*?)(?:\b20\d{2}|\d{1,2} al|\(continuaci|\(conclusi)",
        text,
        re.IGNORECASE,
    )
    category = clean(category_match[1]) if category_match else "Productos mayoristas"
    exceptions = {
        key: value or _exceptions(text)[key]
        for key, value in document_exceptions.items()
    }
    result = []
    for table_no, table in enumerate(reading.get("tables", []), 1):
        if isinstance(table, dict):
            table = [table.get("headers", []), *table.get("rows", [])]
        header = next(
            (
                i
                for i, row in enumerate(table)
                if all(
                    any(word in folded(clean(cell)) for cell in row)
                    for word in ["minimo", "maximo", "medio"]
                )
            ),
            None,
        )
        if header is None:
            if any(NUMBER.fullmatch(clean(cell)) for row in table for cell in row):
                raise ValueError(
                    "Weekly OCR contains numeric table cells without explicit monetary columns"
                )
            continue
        headings = [folded(clean(cell)) for cell in table[header]]
        indices = [
            next(i for i, h in enumerate(headings) if word in h)
            for word in ["minimo", "maximo", "medio"]
        ]
        if indices != list(range(indices[0], indices[0] + 3)) or indices[0] not in (
            1,
            2,
        ):
            raise ValueError("Weekly OCR price columns are ambiguous")
        explicit_product_column = indices[0] == 2
        product = ""
        for row_no, row in enumerate(table[header + 1 :], header + 2):
            cells = [clean(v) for v in row]
            if not any(cells):
                continue
            tokens = [cells[i] if i < len(cells) else "" for i in indices]
            if not any(tokens):
                if cells[0]:
                    product, _ = _product_heading(cells[0])
                continue
            if not all(NUMBER.fullmatch(token) for token in tokens):
                raise ValueError("Weekly OCR has incomplete literal monetary cells")
            values = [_pdf_number(token) for token in tokens]
            if explicit_product_column:
                product = cells[0]
            result.append(
                _row(
                    product,
                    cells[1] if explicit_product_column else cells[0],
                    *values,
                    cells[indices[-1] + 1] if len(cells) > indices[-1] + 1 else "",
                    category,
                    period,
                    f"PDF page {page_no},OCR table {table_no},row {row_no}",
                    page=page_no,
                    exceptions=exceptions,
                )
            )
    if not result:
        raise ValueError(
            f"Weekly OCR page {page_no} contains no supported monetary rows"
        )
    return result


def parse_with_ocr(body, url, kind, readings_by_page):
    if kind != "dane-weekly-pdf":
        raise ValueError("Weekly workbook OCR requires a typed workbook review")
    return parse_pdf(body, url, readings_by_page)

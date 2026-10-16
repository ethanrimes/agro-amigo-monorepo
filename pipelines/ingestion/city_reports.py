"""City-report ZIPs: individual dated PDFs, package sizes, and both price rounds."""

import io
import json
import re
import time
import zipfile
from datetime import date
from decimal import Decimal
from hashlib import sha256

import pdfplumber
from pdfminer.pdfexceptions import PDFException
from pdfminer.psparser import PSEOF
from pdfplumber.utils.exceptions import PdfminerException
from pypdf.errors import PdfReadError

VERSION = "city-v8"

# DANE's 5 November ZIP contains this separately dated, native 6 November
# Medellín PDF. Preserve the actual parent and PDF hashes: the 6 November ZIP
# contains a different revision with the same basename. Only this exact pair
# may use the PDF's printed date for publication; the parent stays in review.
_CARRYOVER_PARENT_URL = (
    "https://www.dane.gov.co/files/operaciones/SIPSA/"
    "bol-SIPSADiario-regionales-05nov2025.zip"
)
_CARRYOVER_PARENT_SHA = "a5e09dc5d3a759199d514813293d8e06ce10255c8e787a71a000cffd5a8abbae"
_CARRYOVER_MEMBER_NAME = "Medellín, Central Mayorista de Antioquia-06-11-2025.pdf"
_CARRYOVER_MEMBER_SHA = "79760ce3816cd8424c04a00b602fee46be073a7c797065fe791cafd9c76e2a4c"
_CARRYOVER_DAY = date(2025, 11, 6)
_CARRYOVER_PARENT_DAY = date(2025, 11, 5)

def _carryover_review():
    return {
        "filename": _CARRYOVER_MEMBER_NAME,
        "document_id": _CARRYOVER_MEMBER_SHA,
        "error": "40 native price ranges published at printed 6 November 2025; parent ZIP link is dated 5 November 2025",
        "error_type": "SourceDateMismatch",
    }


def _is_carryover_parent(data, zip_id, url, day):
    return (
        url == _CARRYOVER_PARENT_URL
        and day == _CARRYOVER_PARENT_DAY
        and zip_id == _CARRYOVER_PARENT_SHA
        and sha256(data).hexdigest() == _CARRYOVER_PARENT_SHA
    )


class CityZipPartialReview(ValueError):
    """Valid members were published; identified members still need review."""

    def __init__(self, count, failures):
        self.count = count
        self.failures = failures
        details = "; ".join(f"{item['filename']}: {item['error']}" for item in failures)
        super().__init__(
            f"{len(failures)} city PDF members retained for review: {details[:1500]}"
        )


def _is_structural_pdfminer_member_error(exc):
    """Recognize a typed PDF failure without traversing operational wrappers.

    Only pdfplumber's PdfminerException is unwrapped. An explicit cause takes
    precedence over implicit context; unknown exceptions are fatal even when
    their own cause/context happens to contain a PDF parser exception.
    """
    structural = (PSEOF, PDFException)
    if isinstance(exc, structural):
        return True
    seen = set()
    current = exc
    while isinstance(current, PdfminerException):
        if id(current) in seen:
            return False
        seen.add(id(current))

        cause = getattr(current, "__cause__", None)
        if cause is not None:
            if isinstance(cause, structural):
                return True
            if isinstance(cause, PdfminerException):
                current = cause
                continue
            return False

        first_arg = current.args[0] if current.args else None
        if isinstance(first_arg, structural):
            return True
        if isinstance(first_arg, PdfminerException):
            current = first_arg
            continue
        if isinstance(first_arg, BaseException):
            return False

        context = getattr(current, "__context__", None)
        if isinstance(context, structural):
            return True
        if isinstance(context, PdfminerException):
            current = context
            continue
        return False
    return False


def _review_step(failure):
    # `step` belongs to a B-tree primary key. Bound UTF-8 bytes as well as
    # characters so a long Unicode ZIP filename/error remains insertable.
    details = dict(failure)
    for key, limit in (("filename", 500), ("error", 1000), ("error_type", 80)):
        details[key] = details[key].encode("utf-8")[:limit].decode("utf-8", "ignore")
    step = "review:" + json.dumps(details, ensure_ascii=False, sort_keys=True)
    while len(step.encode("utf-8")) > 2000:
        key = max(("filename", "error"), key=lambda key: len(details[key]))
        details[key] = details[key][: len(details[key]) // 2]
        step = "review:" + json.dumps(details, ensure_ascii=False, sort_keys=True)
    return step


_NOV2021_CATEGORY_SOURCE_IDS = frozenset({
    "1d8258d2fa8f22a4c7bee56e03513fa6fc80e81f7c3149caa896c89deeebfcae",
    "7872936c55b88d539388b2f27865f5866dedb97a362f2223095629d811e3930c",
    "b262c47141d6b44d1e37b0a526405f79374ce017999fe1f36facd818d7816c57",
    "4ced8283b62ced0ffbf1cdb91e545a810fa2da4b13af52b2287594f547565078",
    "298f734fe2b12f4ed4ee8c9cc35541916a30d76926a36c22e83dcbf377d16c0c",
})
_NOV2021_UNIT_SOURCE_IDS = frozenset({
    "4ced8283b62ced0ffbf1cdb91e545a810fa2da4b13af52b2287594f547565078",
    "298f734fe2b12f4ed4ee8c9cc35541916a30d76926a36c22e83dcbf377d16c0c",
})
_NOV2021_REPLAY_VERSION = "city-v8:nov2021-unit-category-exact-v1"


def parse_city_pdf(data, archive_day=None):
    source_document_id = sha256(data).hexdigest()
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        yield from parse_city_pages(
            pdf.pages, archive_day, source_document_id=source_document_id
        )


def _market_heading(heading):
    """Read the literal market from either verified native title order."""
    from .worker import clean

    match = re.search(
        r"PRECIOS DE VENTA MAYORISTA\s*\n(.+?)\nPRODUCTOS", heading, re.IGNORECASE
    )
    if not match:
        # Two Bogotá originals place the quality subtitle before the market.
        # Bound the market between that subtitle and the explicit printed date;
        # never select an arbitrary later product/table/narrative line.
        match = re.search(
            r"PRECIOS DE VENTA MAYORISTA\s*\n"
            r"PRODUCTOS(?: DE)? PRIMERA CALIDAD[^\n]*\n"
            r"([^\n]+)\n\s*\d{1,2} de [A-Za-zÀ-ÿ]+ de \d{4}(?:\s|$)",
            heading, re.IGNORECASE,
        )
    return clean(match[1]) if match else None


def parse_archived_city_pdf(db, data, did, archive_day):
    """Combine readable native pages with independently verified OCR pages.

    A scanned first page must not prevent readable later pages from eventually
    being published, and one OCR page must not mark the entire PDF complete.
    """
    from .ocr import needs_ocr
    from .pdf_sources import has_table_sized_image, verified_page
    from .worker import SourceDateMismatch, date_from_text, today

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = []
        pending = []
        for number, page in enumerate(pdf.pages, 1):
            if needs_ocr(page, page.extract_text() or ""):
                verified = verified_page(db, page, did, "city-pdf", number)
                pages.append(verified or page)
                if verified is None:
                    pending.append(number)
            else:
                pages.append(page)
        # Native headings are not successful price extraction. Probe only pages
        # containing a substantial image, using the document's dated heading for
        # continuation pages. Semantic/date errors still fail normally.
        heading = pages[0].extract_text() or ""
        for number, page in enumerate(pages, 1):
            if number in pending or not has_table_sized_image(page):
                continue
            if 1 in pending:
                # The first page's identity must be verified before parsing peers.
                continue
            text = page.extract_text() or ""
            if not re.search(
                r"PRECIOS DE VENTA MAYORISTA|\bDANE\b|\bSIPSA\b|Producto.*Presentaci[oó]n",
                text,
                re.IGNORECASE | re.DOTALL,
            ):
                continue
            heading_day = date_from_text(heading)
            if heading_day and (
                heading_day > today() or (archive_day and heading_day > archive_day)
            ):
                raise SourceDateMismatch(
                    "City PDF has unverifiable or future internal date"
                )
            complete_heading = heading_day and _market_heading(heading)
            if complete_heading and list(
                parse_city_pages([page], archive_day, heading=heading, allow_empty=True, source_document_id=did)
            ):
                continue
            verified = verified_page(db, page, did, "city-pdf", number)
            if verified is None:
                pending.append(number)
            else:
                pages[number - 1] = verified
                if number == 1:
                    heading = verified.extract_text() or ""
        if pending:
            raise ValueError(f"City PDF pages {pending} await agreeing OCR readings")
        yield from parse_city_pages(pages, archive_day, source_document_id=did)


def _verified_empty_native_grid(page, tables):
    """Recognize a printed, header-only SIPSA grid without excusing unread prices.

    This deliberately accepts only the observed one-page native layout. A
    missing/malformed table, a continuation page, or an image-sized price grid
    still needs review (or OCR), even when no prices were parsed.
    """
    from .pdf_sources import has_table_sized_image
    from .worker import clean

    if not isinstance(page, pdfplumber.page.Page) or has_table_sized_image(page):
        return False
    if len(tables) != 1 or len(tables[0]) != 4:
        return False
    title, heading, columns, ranges = tables[0]
    if any(len(row) != 7 for row in (title, heading, columns, ranges)):
        return False
    if any(clean(cell) for cell in title):
        return False
    if any(clean(cell) for cell in heading[1:]):
        return False
    if not (heading[0] or "").startswith("PRECIOS DE VENTA MAYORISTA\n"):
        return False
    if [clean(cell) for cell in columns[:3]] != [
        "Producto", "Presentación", "Unidades"
    ]:
        return False
    if any(clean(cell) for cell in (columns[4], columns[6])):
        return False
    if not clean(columns[3]).startswith("Ronda 1") or clean(columns[5]) != "Ronda 2":
        return False
    if [clean(cell) for cell in ranges] != [
        "", "", "", "Mínimo", "Máximo", "Mínimo", "Máximo"
    ]:
        return False
    # A row omitted by table detection can still leave native text on the
    # page. Require the complete printed header and page-count text only.
    lines = [line.strip() for line in (page.extract_text() or "").splitlines() if line.strip()]
    return (
        len(lines) == 9
        and lines[0] == "PRECIOS DE VENTA MAYORISTA"
        and lines[2].startswith("PRODUCTOS PRIMERA CALIDAD")
        and re.fullmatch(r"\d{1,2} de [A-Za-zÀ-ÿ]+ de \d{4}", lines[3], re.IGNORECASE)
        and lines[4:] == [
            "Ronda 1", "Ronda 2", "Producto Presentación Unidades -",
            "Mínimo Máximo Mínimo Máximo", "Pagina 1 de 1",
        ]
    )


def _city_tables(page, *, repair_prices=True):
    """Read verified native word gaps and, optionally, numeric padding glyphs."""
    from .worker import clean

    tables = page.extract_tables()
    if not isinstance(page, pdfplumber.page.Page):
        return tables
    # DANE word gaps around two points are swallowed by pdfplumber's default
    # three-point tolerance. A second extraction at one point restores them.
    # Only the product cell is eligible, and only when both passes have the
    # same native glyph sequence and identical table/cell structure.
    separated = page.extract_tables(table_settings={"text_x_tolerance": 1})
    if len(separated) != len(tables) or any(
        len(other) != len(original)
        or any(len(a) != len(b) for a, b in zip(original, other))
        for original, other in zip(tables, separated)
    ):
        raise ValueError("City product spacing cannot be verified in native table")
    for original, other in zip(tables, separated):
        for row, spaced in zip(original, other):
            if not row or not row[0] or not spaced[0]:
                continue
            old, new = clean(row[0]), clean(spaced[0])
            if (
                new != old
                and len(new.split()) > len(old.split())
                and "".join(new.split()) == "".join(old.split())
            ):
                row[0] = spaced[0]
    if not repair_prices:
        # The additive product-name correction audit has a narrower contract:
        # every non-name cell must remain literally unchanged in its two reads.
        return tables
    from .city_unit_overflow import verified_city_unit_overflow

    tables = verified_city_unit_overflow(page, tables)
    # A January2024 source has padding-space glyphs overlapping a price's
    # leading digit. Table extraction inserts "1 50,000" although the numeric
    # glyphs form one contiguous, visible "150,000". Recover that glyph run only
    # inside the exact monetary cell; separated/duplicated runs stay invalid.
    geometry = None
    for table_no, table in enumerate(tables):
        for row_no, row in enumerate(table):
            for col in range(3, min(7, len(row))):
                token = clean(row[col])
                if not re.fullmatch(r"[\d.,]+(?:\s+[\d.,]+)+", token):
                    continue
                if geometry is None:
                    geometry = page.find_tables()
                box = geometry[table_no].rows[row_no].cells[col]
                if box is None:
                    continue
                chars = sorted((char for char in page.chars
                    if char["text"].strip()
                    and box[0] <= (char["x0"] + char["x1"]) / 2 <= box[2]
                    and box[1] <= (char["top"] + char["bottom"]) / 2 <= box[3]),
                    key=lambda char: char["x0"])
                candidate = "".join(char["text"] for char in chars)
                if (
                    not chars
                    or candidate != re.sub(r"\s+", "", token)
                    or max(char["top"] for char in chars) - min(char["top"] for char in chars) > 1
                    or any(not re.fullmatch(r"[\d.,]", char["text"]) for char in chars)
                    or any(
                        not -0.25 * min(a["x1"] - a["x0"], b["x1"] - b["x0"])
                        <= b["x0"] - a["x1"]
                        <= 0.75 * max(a["x1"] - a["x0"], b["x1"] - b["x0"])
                        for a, b in zip(chars, chars[1:])
                    )
                ):
                    continue
                row[col] = candidate
    return tables


def _city_number(token):
    # These are literal whole-peso bounds. Some native city originals use comma
    # grouping rather than dot grouping; one/two decimal-comma digits retain
    # their decimal meaning. Neither spacing nor punctuation invents a digit.
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", token):
        return Decimal(token.replace(",", ""))
    return Decimal(token.replace(".", "").replace(",", "."))


def parse_city_pages(
    pages, archive_day=None, *, heading=None, allow_empty=False, source_document_id=None
):
    from .worker import SourceDateMismatch, clean, date_from_text, slug, today

    heading = heading if heading is not None else pages[0].extract_text() or ""
    day = date_from_text(heading)
    if not day or day > today() or (archive_day and day > archive_day):
        raise SourceDateMismatch("City PDF has unverifiable or future internal date")
    market = _market_heading(heading)
    scoped_category_repair = source_document_id in _NOV2021_CATEGORY_SOURCE_IDS
    scoped_unit_repair = source_document_id in _NOV2021_UNIT_SOURCE_IDS
    if not market:
        raise ValueError("City PDF market heading not found")
    found = 0
    verified_empty = False
    category = "Productos agropecuarios"
    group = ""
    main_groups = {
        "frutas",
        "tuberculos-raices-y-platanos",
        "verduras-y-hortalizas",
        "procesados",
        "granos-y-cereales",
        "lacteos-y-huevos",
        "pescados",
        "carnes",
    }
    for page_no, page in enumerate(pages, 1):
        tables = _city_tables(page)
        if len(pages) == 1 and _verified_empty_native_grid(page, tables):
            verified_empty = True
        for table_no, table in enumerate(tables, 1):
            headers = next(
                (
                    i
                    for i, r in enumerate(table)
                    if len(r) >= 7
                    and clean(r[0]) == "Producto"
                    and clean(r[1]) == "Presentación"
                ),
                None,
            )
            if headers is None:
                continue
            rounds = {1: clean(table[headers][3]), 2: clean(table[headers][5])}
            for row_no, row in enumerate(table[headers + 2 :], headers + 3):
                if len(row) < 7:
                    continue
                name, presentation, units = map(clean, row[:3])
                if not presentation and not units:
                    if scoped_category_repair:
                        unavailable = ("", "0", "-", "n.d.")
                        price_cells = [clean(v) for v in row[3:7]]
                        if any(value not in unavailable for value in price_cells):
                            raise ValueError(
                                f"Unquantified city row has price data on page {page_no}, row {row_no}"
                            )
                        group_aliases = main_groups | {
                            "tuberculos-raices-platanos",
                            "verduras-y-hortailizas",
                            "huevos",
                        }
                        if name and slug(name) in group_aliases:
                            group = name.capitalize()
                            category = group
                        elif name and not name.startswith(("*", "Fuente", "Nota")):
                            raise ValueError(
                                f"Unrecognized city section heading on page {page_no}, row {row_no}: {name}"
                            )
                    elif name and sum(bool(clean(v)) for v in row) == 1:
                        if slug(name) in main_groups:
                            group = name.capitalize()
                            category = group
                        elif not name.startswith(("*", "Fuente", "Nota")):
                            category = (
                                group + " > " if group else ""
                            ) + name.capitalize()
                    continue
                # Some native PDFs omit the space between quantity and unit.
                # Require a letter at the unit boundary so a numeric quantity
                # cannot backtrack into a bogus suffix (e.g. bare "12.5").
                # Compound units remain literal and receive no base conversion.
                qty = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*([A-Za-zÀ-ÿ].*)", units)
                if qty:
                    quantity = Decimal(qty[1].replace(",", "."))
                    source_unit = qty[2]
                elif (
                    scoped_unit_repair
                    and presentation
                    and units
                    and slug(presentation) == slug(units)
                    and slug(units) in {"kilogramo", "arroba"}
                ):
                    quantity = Decimal(1)
                    source_unit = units
                else:
                    raise ValueError(
                        f"Unknown city quantity on page {page_no}: {units}"
                    )
                if not name:
                    raise ValueError(f"Missing city product name on page {page_no}, row {row_no}")
                key = slug(source_unit)
                base = {
                    "kilogramo": ("kg", Decimal(1)),
                    "gramo": ("kg", Decimal(".001")),
                    "litro": ("litre", Decimal(1)),
                    "mililitro": ("litre", Decimal(".001")),
                    "unidad": ("unit", Decimal(1)),
                    "unidades": ("unit", Decimal(1)),
                }.get(key)
                normalized_unit, factor = base if base else (source_unit, Decimal(1))
                if quantity <= 0:
                    raise ValueError("Nonpositive city package quantity")
                for rnd, col in [(1, 3), (2, 5)]:
                    tokens = [clean(row[col]), clean(row[col + 1])]
                    if all(v in ("", "0", "-", "n.d.") for v in tokens):
                        continue
                    if not all(
                        re.fullmatch(r"(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d{3})*(?:,\d+)?)", v) for v in tokens
                    ):
                        raise ValueError(
                            f"Unknown price range: page {page_no}, row {row_no}: {tokens}"
                        )
                    low, high = (_city_number(v) for v in tokens)
                    if not 0 < low <= high:
                        raise ValueError("Invalid city min/max range")
                    found += 1
                    yield (
                        f"PDF page {page_no},table {table_no},row {row_no},round {rnd}",
                        day,
                        slug(name),
                        name,
                        market,
                        category,
                        presentation,
                        quantity,
                        source_unit,
                        rnd,
                        rounds[rnd],
                        low,
                        high,
                        normalized_unit,
                        low / (quantity * factor) if base else None,
                        high / (quantity * factor) if base else None,
                        page_no,
                    )
        page.close()
    if not found and not allow_empty and not verified_empty:
        raise ValueError("No city price ranges parsed")


_BULK_TABLES = {
    "regional_price": (
        (
            "document_id,source_locator,observed_on,product_id,product_name,market_name,category,"
            "presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,"
            "min_unit_price,max_unit_price,source_page"
        ),
        ("document_id", "source_locator"),
    ),
    "product": ("id,name,category", ("id",)),
    "market": ("id,name,city,region,municipality_id", ("id",)),
    "regional_classification": (
        "document_id,source_locator,category_path",
        ("document_id", "source_locator"),
    ),
}


def _bulk_insert(db, table, rows):
    """COPY one PDF's rows, then publish in a single bounded SQL statement.

    The caller owns the transaction. Identifiers come only from this fixed map;
    source text is sent through COPY parameters. Existing immutable rows never
    reach insertion/retention triggers when a PDF is replayed after an upgrade.
    """
    columns, keys = _BULK_TABLES[table]
    stage = "city_stage_" + table
    db.execute(
        f"CREATE TEMP TABLE IF NOT EXISTS {stage} ON COMMIT DROP AS "
        f"SELECT {columns} FROM {table} WITH NO DATA"
    )
    db.execute(f"TRUNCATE pg_temp.{stage}")
    with (
        db.cursor() as cur,
        cur.copy(f"COPY pg_temp.{stage} ({columns}) FROM STDIN") as copy,
    ):
        for row in rows:
            copy.write_row(row)
    selected = ",".join("s." + column for column in columns.split(","))
    matches = " AND ".join(f"existing.{key}=s.{key}" for key in keys)
    db.execute(
        f"INSERT INTO {table} ({columns}) SELECT {selected} FROM pg_temp.{stage} s "
        f"WHERE NOT EXISTS (SELECT 1 FROM {table} existing WHERE {matches}) "
        "ON CONFLICT DO NOTHING"
    )


_PRICE_FIELDS = _BULK_TABLES["regional_price"][0].split(",")[2:]


def _evidence_value(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return value


def _publication_parity(db, did, rows, *, require_all=False, verified_categories=None):
    """Compare a whole parsed PDF with every immutable row already retained.

    New locators are legitimate during a partial resume. An old locator that
    disappeared, or any changed typed value/path, requires manual review.
    """
    verified_categories = verified_categories or {}
    native = {}
    for row in rows:
        locator = row[0]
        if locator in native:
            raise ValueError(f"Duplicate city PDF source locator: {locator[:200]}")
        native[locator] = (row[1:], row[5].split(" > "))
    stored = {
        record[0]: record[1:]
        for record in db.execute(
            f"SELECT source_locator,{','.join(_PRICE_FIELDS)} FROM regional_price "
            "WHERE document_id=%s ORDER BY source_locator", (did,),
        ).fetchall()
    }
    classifications = dict(db.execute(
        "SELECT source_locator,category_path FROM regional_classification "
        "WHERE document_id=%s ORDER BY source_locator", (did,),
    ).fetchall())
    corrected_identities = {
        locator: (product_id, product_name)
        for locator, product_id, product_name in db.execute(
            "SELECT source_locator,corrected_product_id,corrected_product_name "
            "FROM regional_price_product_correction WHERE document_id=%s",
            (did,),
        ).fetchall()
    }
    discrepancies = []
    for locator, values in stored.items():
        current = native.get(locator)
        if current is None:
            discrepancies.append({"locator": locator, "field": "source_locator", "stored": "present", "native": "absent"})
            continue
        correction = corrected_identities.get(locator)
        for field, old, new in zip(_PRICE_FIELDS, values, current[0]):
            verified = verified_categories.get(locator)
            if field == "category" and verified is not None:
                verified_old, verified_new = (
                    (verified["old_category"], verified["corrected_category"])
                    if isinstance(verified, dict)
                    else verified
                )
                if verified_old == old and verified_new == new:
                    # An exact current-parser proof may project this category only.
                    continue
            if field in ("product_id", "product_name") and correction is not None:
                corrected = correction[0 if field == "product_id" else 1]
                if new == corrected:
                    continue
            if old != new:
                discrepancies.append({"locator": locator, "field": field,
                    "stored": _evidence_value(old), "native": _evidence_value(new)})
    for locator, path in classifications.items():
        current = native.get(locator)
        if current is None:
            discrepancies.append({"locator": locator, "field": "category_path", "stored": path, "native": "absent"})
        elif path != current[1]:
            verified = verified_categories.get(locator)
            if not (
                isinstance(verified, dict)
                and verified["rule"] == "literal-top-level-heading"
                and path == verified["old_category"].split(" > ")
                and current[1] == verified["category_path"]
            ):
                discrepancies.append({"locator": locator, "field": "category_path", "stored": path, "native": current[1]})
    if require_all:
        for locator in native.keys() - stored.keys():
            discrepancies.append({"locator": locator, "field": "source_locator", "stored": "absent", "native": "present"})
        for locator in native.keys() - classifications.keys():
            discrepancies.append({"locator": locator, "field": "category_path", "stored": "absent", "native": native[locator][1]})
    def fingerprint(records):
        return sha256(json.dumps(records, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), default=_evidence_value).encode()).hexdigest()
    native_digest = fingerprint([
        (locator, *(_evidence_value(value) for value in native[locator][0]), native[locator][1])
        for locator in sorted(native)
    ])
    stored_digest = fingerprint([
        (locator, *(_evidence_value(value) for value in stored[locator]), classifications.get(locator))
        for locator in sorted(stored)
    ] + [(locator, classifications[locator]) for locator in sorted(classifications.keys() - stored.keys())]
      + [(locator, corrected_identities[locator]) for locator in sorted(corrected_identities)])
    return native_digest, stored_digest, {
        "native_count": len(native), "stored_count": len(stored),
        "classification_count": len(classifications),
        "difference_count": len(discrepancies), "differences": discrepancies[:20],
        "difference_fields": sorted({item["field"] for item in discrepancies}),
    }


def _publication_conflict(db, did, rows, version, archive_id=None, entry_name=None, *, require_all=False, native_source=None):
    from psycopg.pq import TransactionStatus

    if db.info.transaction_status == TransactionStatus.IDLE:
        raise RuntimeError("City PDF parity requires a publication transaction")
    # Advisory transaction lock needs no UPDATE privilege on immutable source
    # rows. It serializes this child's compare/insert/checkpoint attempts.
    db.execute("SELECT pg_advisory_xact_lock(hashtextextended('city-pdf-publication:' || %s,0))", (did,))
    if not db.execute("SELECT id FROM source_document WHERE id=%s", (did,)).fetchone():
        raise ValueError("Archived city PDF source is missing")
    native_hash, stored_hash, details = _publication_parity(db, did, rows, require_all=require_all)
    if (
        native_source is not None
        and details["native_count"] == details["stored_count"] == details["classification_count"]
        and (
            (version == VERSION and details["difference_fields"] == ["category"])
            or (
                version == _NOV2021_REPLAY_VERSION
                and did in _NOV2021_CATEGORY_SOURCE_IDS
                and details["difference_fields"] == ["category", "category_path"]
            )
        )
    ):
        from .city_category_overlay import (
            Ineligible, apply_category_overlay, load_verified_category_overlay,
        )

        try:
            # Revalidate an immutable prior-parser leaf attestation against the
            # complete retained originals before attempting a new parser proof.
            # This preserves older valid proof rows and prevents a false conflict.
            from .city_category_overlay import load_verified_prior_leaf_overlay
            with db.transaction():
                parent_zip, child_pdf, source_url = native_source
                prior_verified = load_verified_prior_leaf_overlay(
                    db, did, rows, native_source,
                    archive_id=archive_id, entry_name=entry_name,
                )
                if prior_verified:
                    checked_native, checked_stored, checked_details = _publication_parity(
                        db, did, rows, require_all=True, verified_categories=prior_verified,
                    )
                    if not checked_details["difference_count"]:
                        native_hash, stored_hash, details = checked_native, checked_stored, checked_details
                    else:
                        prior_verified = None
            if prior_verified and not details["difference_count"]:
                pass
            else:
                # An ineligible proposal must roll back every tentative overlay.
                # It cannot leave an orphan behind or change immutable raw rows.
                with db.transaction():
                    parent_zip, child_pdf, source_url = native_source
                    proposal = apply_category_overlay(
                        db, parent_zip=parent_zip, archive_id=archive_id,
                        entry_name=entry_name, child_pdf=child_pdf, document_id=did,
                        source_url=source_url, native_rows=rows,
                    )
                    verified = load_verified_category_overlay(db, did, rows, proposal)
                    checked_native, checked_stored, checked_details = _publication_parity(
                        db, did, rows, require_all=True, verified_categories=verified,
                    )
                    if checked_details["difference_count"] or not verified:
                        raise Ineligible("Whole-source category projection did not restore exact parity")
                    checked_details["category_overlay_proof_id"] = proposal["proof"]["proof_id"]
                    native_hash, stored_hash, details = checked_native, checked_stored, checked_details
        except Ineligible:
            # Preserve the original discrepancy evidence and normal conflict
            # gate when exact bytes, locators, headings or fields differ.
            pass
    if details["difference_count"]:
        from psycopg.types.json import Jsonb

        db.execute(
            "INSERT INTO city_pdf_publication_conflict"
            "(document_id,archive_id,entry_name,processor_version,native_sha256,stored_sha256,details) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (did, archive_id, entry_name, version, native_hash, stored_hash, Jsonb(details)),
        )
        return f"City PDF publication conflict: {details['difference_count']} native/stored differences"
    if db.execute(
        "SELECT 1 FROM city_pdf_publication_conflict WHERE document_id=%s LIMIT 1", (did,),
    ).fetchone():
        return "City PDF has an unresolved publication conflict"
    return None


def _member_step(member, day):
    # Archive hash + member identity + supplied date context uniquely identify
    # the work. Hashing keeps long Unicode entry names out of B-tree keys.
    identity = [
        member.filename,
        member.header_offset,
        member.CRC,
        member.file_size,
        str(day),
    ]
    return "city-member:" + sha256(json.dumps(identity).encode()).hexdigest()


def publish_city_zip(db, data, zip_id, url, day, *, processor_version=VERSION):
    from .pdf_sources import extract_pages
    from .reviewed_city_dates import (
        reviewed_member, reviewed_parent, source_review, validate_rows,
    )
    from .resumable_inputs import WorkDeferred
    from .worker import RUN_DEADLINE, archive

    total = 0
    failures = []
    carryover_parent = _is_carryover_parent(data, zip_id, url, day)
    date_review_parent = reviewed_parent(data, zip_id, url, day)
    with zipfile.ZipFile(io.BytesIO(data)) as bundle:
        members = [
            m
            for m in bundle.infolist()
            if not m.is_dir() and m.filename.lower().endswith(".pdf")
        ]
        if (
            not members
            or len(members) > 500
            or sum(m.file_size for m in members) > 512 * 1024 * 1024
        ):
            raise ValueError("Unexpected city archive contents or size")
        completed = dict(
            db.execute(
                "SELECT step,records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step LIKE 'city-member:%%'",
                (zip_id, processor_version),
            ).fetchall()
        )
        for member in members:
            step = _member_step(member, day)
            carryover_name = carryover_parent and member.filename == _CARRYOVER_MEMBER_NAME
            date_review_member = reviewed_member(date_review_parent, member.filename)
            blocked_child = step in completed and db.execute(
                "SELECT 1 FROM source_archive_member member "
                "JOIN unresolved_city_pdf_publication_conflict conflict "
                "ON conflict.document_id=member.document_id "
                "WHERE member.archive_id=%s AND member.entry_name=%s LIMIT 1",
                (zip_id, member.filename),
            ).fetchone()
            if step in completed and not blocked_child:
                total += completed[step]
                if carryover_name:
                    failures.append(_carryover_review())
                if date_review_member is not None:
                    if completed[step] != date_review_member["rows"]:
                        raise ValueError("Reviewed city date checkpoint count changed")
                    failures.append(source_review(date_review_parent, date_review_member))
                continue
            deadline = RUN_DEADLINE.get()
            if deadline is not None and time.monotonic() >= deadline:
                raise WorkDeferred(
                    f"City ZIP deferred before {member.filename[:200]}; {total} committed price rows will resume"
                )
            # Read bytes without extracting paths supplied by the ZIP to disk.
            content = bundle.read(member)
            carryover = carryover_name and sha256(content).hexdigest() == _CARRYOVER_MEMBER_SHA
            date_review_member = reviewed_member(date_review_parent, member.filename, content)
            did = archive(
                db,
                url,
                content,
                "city-pdf",
                None,
                filename=member.filename,
                parents=[zip_id],
            )
            db.execute(
                "INSERT INTO source_archive_member VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                (zip_id, member.filename, did),
            )
            try:
                if carryover and did != _CARRYOVER_MEMBER_SHA:
                    raise ValueError("Verified Medellín carryover document ID changed")
                if content.lstrip()[:32].lower().startswith(
                    (b"<!doctype html", b"<html")
                ):
                    raise ValueError("City PDF member contains HTML, not a PDF")
                with db.transaction():
                    extract_pages(db, content, did)
                rows = list(
                    parse_archived_city_pdf(
                        db, content, did,
                        date.fromisoformat(date_review_member["printed_day"])
                        if date_review_member is not None
                        else _CARRYOVER_DAY if carryover else day,
                    )
                )
                if date_review_member is not None:
                    validate_rows(date_review_member, rows)
                if carryover and (
                    len(rows) != 40
                    or any(
                        row[1] != _CARRYOVER_DAY
                        or row[4] != "Medellín, Central Mayorista de Antioquia"
                        for row in rows
                    )
                ):
                    raise ValueError("Verified Medellín carryover price grid changed")
                with db.transaction():
                    conflict = _publication_conflict(
                        db, did, rows, processor_version, zip_id, member.filename,
                        native_source=(data, content, url),
                    )
                    if conflict is None:
                        save_classifications(db, did, rows)
                        _bulk_insert(db, "regional_price", ((did, *r) for r in rows))
                        conflict = _publication_conflict(
                            db, did, rows, processor_version, zip_id,
                            member.filename, require_all=True,
                            native_source=(data, content, url),
                        )
                    if conflict is None:
                        # Completion and native/stored parity commit together.
                        db.execute(
                            "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (zip_id, processor_version, step, len(rows)),
                        )
                        if carryover:
                            db.execute(
                                "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) VALUES(%s,%s,%s,0) ON CONFLICT DO NOTHING",
                                (zip_id, processor_version, _review_step(_carryover_review())),
                            )
                        if date_review_member is not None:
                            db.execute(
                                "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) VALUES(%s,%s,%s,0) ON CONFLICT DO NOTHING",
                                (zip_id, processor_version, _review_step(source_review(date_review_parent, date_review_member))),
                            )
                if conflict is not None:
                    raise ValueError(conflict)
                total += len(rows)
                if carryover:
                    failures.append(_carryover_review())
                if date_review_member is not None:
                    failures.append(source_review(date_review_parent, date_review_member))
            except (ValueError, PdfReadError, PSEOF, PDFException, PdfminerException) as exc:
                if isinstance(exc, PdfminerException) and not _is_structural_pdfminer_member_error(exc):
                    # Known structural PDF failures such as pdfminer.psparser.PSEOF
                    # are isolated to this retained ZIP member. Other failures
                    # remain fatal and are not converted to source review.
                    raise
                failure = {
                    "filename": member.filename[:500],
                    "document_id": did,
                    "error": str(exc)[:1500],
                    "error_type": (
                        type(exc.args[0]).__name__
                        if isinstance(exc, PdfminerException) else type(exc).__name__
                    ),
                }
                # The ZIP/date context matters: the same original may be valid
                # in another archive. Keep this review evidence additive and
                # separate from immutable original document metadata.
                db.execute(
                    """INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records)
                    VALUES(%s,%s,%s,0) ON CONFLICT DO NOTHING""",
                    (
                        zip_id,
                        processor_version,
                        _review_step(failure),
                    ),
                )
                failures.append(failure)
    if failures:
        raise CityZipPartialReview(total, failures)
    return total


def publish_ocr_page(db, did, page, result):
    archive_day = db.execute(
        "SELECT max(a.observed_on) FROM ingestion_asset a JOIN source_archive_member m ON m.archive_id=a.document_id WHERE m.document_id=%s",
        (did,),
    ).fetchone()[0]
    data = db.execute(
        "SELECT content FROM source_document WHERE id=%s", (did,)
    ).fetchone()[0]
    # Reconstruct all pages so continuation tables inherit the real document
    # date, market and classification. Stable locators also avoid duplicate
    # native rows when a later OCR page becomes available.
    rows = [
        (did, *row)
        for row in parse_archived_city_pdf(db, bytes(data), did, archive_day)
    ]
    parsed = [r[1:] for r in rows]
    with db.transaction():
        conflict = _publication_conflict(db, did, parsed, VERSION + ":ocr")
        if conflict is None:
            save_classifications(db, did, parsed)
            _bulk_insert(db, "regional_price", rows)
            conflict = _publication_conflict(
                db, did, parsed, VERSION + ":ocr", require_all=True,
            )
        if conflict is None:
            db.execute(
                "UPDATE source_ocr_task SET status='published',checked_at=now(),error=NULL WHERE document_id=%s AND source_kind='city-pdf'",
                (did,),
            )
    if conflict is not None:
        raise ValueError(conflict)
    return len(rows)


def save_classifications(db, did, rows):
    from .worker import slug

    # Every newly discovered city market must be reachable by the price API.
    # Coordinates are attached only when the municipality name is unambiguous.
    names = {r[4] for r in rows}
    existing_rows = db.execute(
        "SELECT id,name,city,region,municipality_id FROM market"
    ).fetchall()
    existing = {}
    for market_row in existing_rows:
        existing.setdefault(market_row[1], []).append(market_row)
    missing = names - existing.keys()
    markets = []
    enrichments = []
    if missing or any(
        any(row[4] is None for row in existing.get(name, ())) for name in names
    ):
        places = db.execute("SELECT id,name,department FROM municipality").fetchall()
        for name in names:
            city = name.split(",")[0].strip()
            # DANE's older Bogotá city heading omits the D.C. suffix. This is
            # the same official municipality 11001, not an approximate match.
            city_key = "bogota-d-c" if slug(city) == "bogota" else slug(city)
            matches = [p for p in places if slug(p[1]) == city_key]
            place = matches[0] if len(matches) == 1 else None
            department = (
                "Bogotá, D.C." if place and place[0] == "11001"
                else place[2] if place else ""
            )
            if name in missing:
                markets.append(
                    ("dane-city-" + slug(name), name, city, department,
                     place[0] if place else None)
                )
                continue

            # A prior city market may have been created before its official
            # municipality could be joined. Enrich only the exact generated
            # city-market identity, only when the maintained municipality
            # directory has one exact normalized city-name match, and only
            # when existing location fields are blank/country placeholders.
            # Existing direct mappings and conflicting/non-city identities
            # are never rewritten.
            prior = existing.get(name, ())
            if len(prior) != 1 or place is None:
                continue
            market_id, literal_name, old_city, old_region, old_municipality = prior[0]
            if old_municipality is not None:
                continue
            if market_id not in {"dane-city-" + slug(name), "sipsa-" + slug(name)}:
                continue
            allowed_city = {"", "colombia", slug(city)}
            allowed_region = {"", "colombia"}
            if (
                slug(old_city or "") not in allowed_city
                or slug(old_region or "") not in allowed_region
            ):
                continue
            enrichments.append(
                (city, department, place[0], market_id, literal_name,
                 old_city, old_region)
            )
    with db.transaction():
        if markets:
            _bulk_insert(db, "market", markets)
        for city, department, municipality_id, market_id, literal_name, old_city, old_region in enrichments:
            db.execute(
                "UPDATE market SET city=%s,region=%s,municipality_id=%s "
                "WHERE id=%s AND name=%s AND municipality_id IS NULL "
                "AND city IS NOT DISTINCT FROM %s AND region IS NOT DISTINCT FROM %s",
                (city, department, municipality_id, market_id, literal_name,
                 old_city, old_region),
            )
        products = {r[2]: (r[2], r[3], r[5].split(" > ")[0]) for r in rows}
        _bulk_insert(db, "product", products.values())
        _bulk_insert(
            db,
            "regional_classification",
            ((did, r[0], r[5].split(" > ")) for r in rows),
        )

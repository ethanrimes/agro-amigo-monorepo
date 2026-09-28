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

VERSION = "city-v5"

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


def parse_city_pdf(data, archive_day=None):

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        yield from parse_city_pages(pdf.pages, archive_day)


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
            complete_heading = heading_day and re.search(
                r"PRECIOS DE VENTA MAYORISTA\s*\n(.+?)\nPRODUCTOS",
                heading,
                re.IGNORECASE,
            )
            if complete_heading and list(
                parse_city_pages([page], archive_day, heading=heading, allow_empty=True)
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
        yield from parse_city_pages(pages, archive_day)


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


def parse_city_pages(pages, archive_day=None, *, heading=None, allow_empty=False):
    from .worker import SourceDateMismatch, clean, date_from_text, slug, today

    heading = heading if heading is not None else pages[0].extract_text() or ""
    day = date_from_text(heading)
    if not day or day > today() or (archive_day and day > archive_day):
        raise SourceDateMismatch("City PDF has unverifiable or future internal date")
    market_match = re.search(
        r"PRECIOS DE VENTA MAYORISTA\s*\n(.+?)\nPRODUCTOS", heading, re.IGNORECASE
    )
    if not market_match:
        raise ValueError("City PDF market heading not found")
    market = clean(market_match[1])
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
        tables = page.extract_tables()
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
                    if name and sum(bool(clean(v)) for v in row) == 1:
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
                if not name or not qty:
                    raise ValueError(
                        f"Unknown city quantity on page {page_no}: {units}"
                    )
                quantity = Decimal(qty[1].replace(",", "."))
                source_unit = qty[2]
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
                        re.fullmatch(r"\d+(?:\.\d{3})*(?:,\d+)?", v) for v in tokens
                    ):
                        raise ValueError(
                            f"Unknown price range: page {page_no}, row {row_no}: {tokens}"
                        )
                    low, high = (
                        Decimal(v.replace(".", "").replace(",", ".")) for v in tokens
                    )
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
    from .resumable_inputs import WorkDeferred
    from .worker import RUN_DEADLINE, archive

    total = 0
    failures = []
    carryover_parent = _is_carryover_parent(data, zip_id, url, day)
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
            if step in completed:
                total += completed[step]
                if carryover_name:
                    failures.append(_carryover_review())
                continue
            deadline = RUN_DEADLINE.get()
            if deadline is not None and time.monotonic() >= deadline:
                raise WorkDeferred(
                    f"City ZIP deferred before {member.filename[:200]}; {total} committed price rows will resume"
                )
            # Read bytes without extracting paths supplied by the ZIP to disk.
            content = bundle.read(member)
            carryover = carryover_name and sha256(content).hexdigest() == _CARRYOVER_MEMBER_SHA
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
                with db.transaction():
                    extract_pages(db, content, did)
                rows = list(
                    parse_archived_city_pdf(
                        db, content, did, _CARRYOVER_DAY if carryover else day
                    )
                )
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
                    save_classifications(db, did, rows)
                    _bulk_insert(db, "regional_price", ((did, *r) for r in rows))
                    # Completion is committed with all prices and categories.
                    # A crash can leave archived evidence but never a false
                    # success marker that skips an unpublished member.
                    db.execute(
                        "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (zip_id, processor_version, step, len(rows)),
                    )
                    if carryover:
                        db.execute(
                            "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) VALUES(%s,%s,%s,0) ON CONFLICT DO NOTHING",
                            (zip_id, processor_version, _review_step(_carryover_review())),
                        )
                total += len(rows)
                if carryover:
                    failures.append(_carryover_review())
            except ValueError as exc:
                failure = {
                    "filename": member.filename[:500],
                    "document_id": did,
                    "error": str(exc)[:1500],
                    "error_type": type(exc).__name__,
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
    with db.transaction():
        save_classifications(db, did, [r[1:] for r in rows])
        _bulk_insert(db, "regional_price", rows)
        db.execute(
            "UPDATE source_ocr_task SET status='published',checked_at=now(),error=NULL WHERE document_id=%s AND source_kind='city-pdf'",
            (did,),
        )
    return len(rows)


def save_classifications(db, did, rows):
    from .worker import slug

    # Every newly discovered city market must be reachable by the price API.
    # Coordinates are attached only when the municipality name is unambiguous.
    names = {r[4] for r in rows}
    existing = {r[0] for r in db.execute("SELECT name FROM market").fetchall()}
    missing = names - existing
    markets = []
    if missing:
        places = db.execute("SELECT id,name,department FROM municipality").fetchall()
        for name in missing:
            city = name.split(",")[0].strip()
            matches = [p for p in places if slug(p[1]) == slug(city)]
            place = matches[0] if len(matches) == 1 else None
            markets.append(
                (
                    "dane-city-" + slug(name),
                    name,
                    city,
                    place[2] if place else "",
                    place[0] if place else None,
                ),
            )
    with db.transaction():
        if markets:
            _bulk_insert(db, "market", markets)
        products = {r[2]: (r[2], r[3], r[5].split(" > ")[0]) for r in rows}
        _bulk_insert(db, "product", products.values())
        _bulk_insert(
            db,
            "regional_classification",
            ((did, r[0], r[5].split(" > ")) for r in rows),
        )

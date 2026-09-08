"""City-report ZIPs: individual dated PDFs, package sizes, and both price rounds."""

import io
import re
import zipfile
from decimal import Decimal

import pdfplumber


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
        for table_no, table in enumerate(page.extract_tables(), 1):
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
                qty = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s+(.+)", units)
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
    if not found and not allow_empty:
        raise ValueError("No city price ranges parsed")


def publish_city_zip(db, data, zip_id, url, day):
    from .pdf_sources import extract_pages
    from .worker import archive

    total = 0
    failures = []
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
        for member in members:
            # Read bytes without extracting paths supplied by the ZIP to disk.
            content = bundle.read(member)
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
                with db.transaction():
                    extract_pages(db, content, did)
                rows = list(parse_archived_city_pdf(db, content, did, day))
                save_classifications(db, did, rows)
                with db.transaction():
                    with db.cursor() as cur:
                        cur.executemany(
                            """INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,
                            presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                            [(did, *r) for r in rows],
                        )
                total += len(rows)
            except ValueError as exc:
                failures.append(member.filename + ": " + str(exc))
    if failures:
        raise ValueError(
            "City PDF members retained for review: " + "; ".join(failures)[:1500]
        )
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
    save_classifications(db, did, [r[1:] for r in rows])
    with db.transaction():
        with db.cursor() as cur:
            cur.executemany(
                """INSERT INTO regional_price(document_id,source_locator,observed_on,product_id,product_name,market_name,category,
                presentation,quantity,source_unit,round,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                rows,
            )
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
    if missing:
        places = db.execute("SELECT id,name,department FROM municipality").fetchall()
        for name in missing:
            city = name.split(",")[0].strip()
            matches = [p for p in places if slug(p[1]) == slug(city)]
            place = matches[0] if len(matches) == 1 else None
            db.execute(
                "INSERT INTO market(id,name,city,region,municipality_id) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (
                    "dane-city-" + slug(name),
                    name,
                    city,
                    place[2] if place else "",
                    place[0] if place else None,
                ),
            )
    with db.cursor() as cur:
        products = {r[2]: (r[2], r[3], r[5].split(" > ")[0]) for r in rows}
        cur.executemany(
            "INSERT INTO product(id,name,category) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
            products.values(),
        )
        cur.executemany(
            "INSERT INTO regional_classification(document_id,source_locator,category_path) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
            [(did, r[0], r[5].split(" > ")) for r in rows],
        )

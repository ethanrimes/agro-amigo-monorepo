"""Process every PDF independently; keep text/tables and exact page provenance."""

import io
import re

import pdfplumber
from psycopg.types.json import Jsonb

VERSION = "pdf-text-tables-v1"


def has_table_sized_image(page):
    """Exclude banners/logos when a supported price page has no parsed cells."""
    return any(
        (image["x1"] - image["x0"]) >= page.width * 0.35
        and (image["bottom"] - image["top"]) >= page.height * 0.20
        and (image["x1"] - image["x0"]) * (image["bottom"] - image["top"])
        >= page.width * page.height * 0.12
        for image in page.images
    )


class VerifiedPDFPage:
    """Literal, agreeing OCR cells presented to the ordinary table parser."""

    def __init__(self, result):
        self.result = result
        self.images = []

    def extract_text(self):
        return self.result["text"]

    def extract_tables(self):
        return self.result["tables"]

    def close(self):
        pass


def verified_page(db, page, did, kind, number):
    """Use cached independent readings or queue this failed page, not its peers."""
    from .ocr import VERSION as OCR_VERSION
    from .ocr import compare_readings, enqueue_image

    readings = db.execute(
        """SELECT r.result FROM source_ocr_task t JOIN source_ocr_result r ON r.image_id=t.image_id
        WHERE t.document_id=%s AND t.source_page=%s AND r.version=%s ORDER BY r.reading""",
        (did, number, OCR_VERSION),
    ).fetchall()
    if len(readings) == 2 and compare_readings(readings[0][0], readings[1][0]):
        return VerifiedPDFPage(readings[0][0])
    enqueue_image(
        db,
        did,
        f"PDF page {number}",
        page.to_image(resolution=200).original,
        kind,
        number,
    )
    return None


class PDFOCRPending(ValueError):
    """Originals and failed pages are retained while independent OCR is pending."""


def parse_archived_price_pdf(db, data, did, day, kind):
    """Native-first extraction for supported DANE daily/monthly price matrices."""
    from .ocr import needs_ocr
    from .worker import parse_pdf_pages

    monthly = kind == "monthly-pdf"
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = list(pdf.pages)
        pending = []
        for number, page in enumerate(pages, 1):
            text = page.extract_text() or ""
            failed = needs_ocr(page, text)
            if not failed and has_table_sized_image(page):
                price_heading = re.search(r"precios?", text, re.IGNORECASE) and (
                    re.search(r"kilogramo|mayorista", text, re.IGNORECASE)
                    or sum(
                        city in text
                        for city in ("Bogotá", "Medellín", "Cali", "Armenia", "Pereira")
                    )
                    >= 3
                )
                failed = bool(price_heading) and not list(
                    parse_pdf_pages([page], day, monthly, allow_empty=True)
                )
            if not failed:
                continue
            verified = verified_page(db, page, did, kind, number)
            if verified is None:
                pending.append(number)
            else:
                pages[number - 1] = verified
        if pending:
            raise PDFOCRPending(
                f"Price PDF pages {pending} await agreeing OCR readings"
            )
        yield from parse_pdf_pages(pages, day, monthly)


def publish_price_ocr(db, did, kind):
    from .worker import project, save_rows

    source = db.execute(
        "SELECT d.content,a.url,a.observed_on FROM source_document d JOIN ingestion_asset a ON a.document_id=d.id WHERE d.id=%s AND a.kind=%s LIMIT 1",
        (did, kind),
    ).fetchone()
    if not source:
        raise ValueError("PDF OCR has no original dated ingestion asset")
    data, url, day = source
    if day is None:
        raise ValueError("PDF OCR has no verified reference period")
    rows = list(parse_archived_price_pdf(db, bytes(data), did, day, kind))
    with db.transaction():
        count = save_rows(db, did, rows)
        conflicts = project(db, did, url, kind)
        db.execute(
            "UPDATE ingestion_asset SET status='complete',records=%s,checked_at=now(),error=%s WHERE document_id=%s AND kind=%s",
            (
                count,
                f"Conflicting source keys retained but excluded from app: {conflicts}"
                if conflicts
                else None,
                did,
                kind,
            ),
        )
        db.execute(
            "UPDATE source_ocr_task SET status='published',checked_at=now(),error=NULL WHERE document_id=%s AND source_kind=%s",
            (did, kind),
        )
    return count


def extract_pages(db, data, did):
    count = 0
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            db.execute(
                """INSERT INTO source_pdf_page(document_id,page,text_content,tables,extraction_version)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (
                    did,
                    number,
                    page.extract_text() or "",
                    Jsonb(page.extract_tables()),
                    VERSION,
                ),
            )
            count += 1
            page.close()
    from .ocr import scan_document

    kind = db.execute(
        "SELECT metadata->>'ingestion_kind' FROM source_document WHERE id=%s", (did,)
    ).fetchone()[0]
    scan_document(db, data, did, kind)
    return count


def input_category(title):
    from .inputs import CATEGORIES
    from .worker import clean

    text = re.sub(
        r"\s*\((?:continuaci[oó]n|conclusi[oó]n)\)", "", title, flags=re.IGNORECASE
    )
    text = re.sub(r"^.*?Precios de\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"^Insumos (?:agrícolas|pecuarios)\.\s*", "", text, flags=re.IGNORECASE
    )
    text = clean(text).strip(" .").capitalize()
    prefixes = {
        "alimentos balanceados": "2.1",
        "antibióticos": "2.2",
        "antisépticos": "2.3",
        "vitaminas": "2.7",
        "sales y minerales": "2.7",
        "antinflamatorios": "2.6",
        "fertilizantes": "1.3",
        "coadyudantes": "1.2",
        "coadyuvantes": "1.2",
        "especie productiva": "3.4",
        "material de propagación": "3.6",
        "empaques": "3.3",
        "jornales": "3.5",
        "elementos pecuarios": "3.2",
    }
    return next(
        (
            CATEGORIES[key]
            for prefix, key in prefixes.items()
            if text.lower().startswith(prefix)
        ),
        text,
    )


def parse_input_pdf(data, day):
    """Read each dated two-column table, including layouts without variation.

    Table-local titles/date stamps avoid borrowing the date of an unrelated chart
    or electricity table above. Price rows require explicit geographic identity.
    """
    from .worker import MONTH_NUM, SourceDateMismatch, clean, record

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if "mercados" not in text or "Precio medio" not in text:
                page.close()
                continue
            all_words = [
                w for w in page.extract_words(extra_attrs=["fontname"]) if w["upright"]
            ]
            heading = ""
            previous_category = None
            for col, (left, right) in enumerate(
                [(0, page.width / 2), (page.width / 2, page.width)], 1
            ):
                words = [w for w in all_words if left <= w["x0"] < right]
                headers = [w for w in words if w["text"] == "mercados"]
                for header in headers:
                    nearby = [w for w in words if abs(w["top"] - header["top"]) < 24]
                    price_headers = [w for w in nearby if w["text"] == "Precio"]
                    if not price_headers:
                        continue
                    price_left = min(w["x0"] for w in price_headers)
                    location_headers = [
                        w
                        for w in nearby
                        if abs(w["top"] - header["top"]) < 3 and w["x0"] < price_left
                    ]
                    table_left = min(w["x0"] for w in location_headers) - 8
                    percentage_headers = [
                        w for w in nearby if w["text"] == "porcentual"
                    ]
                    month_headers = [
                        w
                        for w in nearby
                        if w["text"].lower() in MONTH_NUM and w["x0"] >= price_left
                    ]
                    header_bottom = max(
                        w["bottom"]
                        for w in [header, *percentage_headers, *month_headers]
                    )
                    end = min(
                        [h["top"] for h in headers if h["top"] > header_bottom]
                        or [page.height - 18]
                    )
                    prefix = " ".join(
                        w["text"]
                        for w in sorted(
                            all_words, key=lambda w: (round(w["top"], 1), w["x0"])
                        )
                        if w["top"] < header["top"] - 8
                    )
                    stamps = list(
                        re.finditer(
                            r"(20\d{2})\s*\(([a-záéíóú]+)\)", prefix, re.IGNORECASE
                        )
                    )
                    if not stamps:
                        raise SourceDateMismatch(
                            f"Input PDF table has no month: page {page_no}"
                        )
                    stamp = stamps[-1]
                    if (int(stamp[1]), MONTH_NUM.get(stamp[2].lower())) != (
                        day.year,
                        day.month,
                    ):
                        raise SourceDateMismatch(
                            f"Input PDF table month differs from archive link: page {page_no}, {stamp[0]}"
                        )
                    # Use the last table title, not an earlier table on the same page.
                    title = re.split(r"Cuadro\s+\d+\.\s+", prefix[: stamp.start()])[-1]
                    category = input_category(title)
                    if category != previous_category:
                        heading = ""
                    previous_category = category
                    table_right = (
                        max(w["x1"] for w in percentage_headers) + 10
                        if percentage_headers
                        else right - 12
                    )
                    lines = []
                    body = [
                        w
                        for w in words
                        if w["x0"] >= table_left
                        and w["x1"] <= table_right
                        and w["top"] > header_bottom
                        and w["bottom"] < end
                    ]
                    for w in sorted(body, key=lambda w: (round(w["top"], 1), w["x0"])):
                        if not lines or abs(lines[-1][0] - w["top"]) > 2:
                            lines.append((w["top"], [w]))
                        else:
                            lines[-1][1].append(w)
                    previous_heading = False
                    unresolved = False
                    for line_no, (top, ws) in enumerate(lines, 1):
                        ws.sort(key=lambda w: w["x0"])
                        line = clean(" ".join(w["text"] for w in ws))
                        if len(line) == 1 and line.isalpha():
                            continue  # Decorative vertical margin lettering.
                        # Preserve overprinted product identities for review;
                        # never borrow the preceding product's name.
                        if line.startswith("Cuadro"):
                            heading = ""
                            unresolved = True
                            previous_heading = False
                            continue
                        line = re.sub(
                            r"^20\d{2}\s*\([a-záéíóú]+\)\s*",
                            "",
                            line,
                            flags=re.IGNORECASE,
                        )
                        pattern = (
                            r"^(.+?)\s+(\d[\d.,]*)"
                            + (
                                r"\s+(n\.d\.|[-+]?\d[\d.,]*)"
                                if percentage_headers
                                else ""
                            )
                            + r"\s*$"
                        )
                        numeric = re.match(pattern, line, re.IGNORECASE)
                        if numeric and (
                            re.match(r"^(.*?)\s*\(([^)]+)\)\s*\*?$", numeric[1])
                            or re.fullmatch(
                                r"Bogot[aá],?\s*D\.?\s*C\.?\s*\*?", numeric[1]
                            )
                        ):
                            location, price = numeric.group(1, 2)
                            variation = numeric[3] if percentage_headers else "n.d."
                            place = re.match(r"^(.*?)\s*\(([^)]+)\)\s*\*?$", location)
                            if place:
                                municipality, department = map(clean, place.groups())
                            elif re.fullmatch(
                                r"Bogot[aá],?\s*D\.?\s*C\.?\s*\*?", location
                            ):
                                municipality = department = "Bogotá, D.C."
                            else:
                                continue
                            if not heading and not unresolved:
                                raise ValueError(
                                    f"Input PDF price without product/presentation: page {page_no}, col {col}, line {line_no}"
                                )
                            if unresolved:
                                name, presentation = (
                                    "Identidad ilegible en el original",
                                    "Sin presentación verificable",
                                )
                            elif ", " in heading:
                                name, presentation = heading.rsplit(", ", 1)
                            elif category == "Jornales":
                                name, presentation = heading, "Jornal"
                            elif any(
                                term in category.lower()
                                for term in ("arrendamiento", "servicios", "riego")
                            ):
                                name, presentation = (
                                    heading,
                                    "Según descripción del servicio",
                                )
                            else:
                                raise ValueError(
                                    f"Missing input presentation on page {page_no}: {heading}"
                                )
                            value = float(price.replace(".", "").replace(",", "."))
                            if value <= 0:
                                continue
                            change = (
                                None
                                if variation.lower() == "n.d."
                                else float(variation.replace(".", "").replace(",", "."))
                            )
                            yield record(
                                "dane-inputs-pdf-unresolved"
                                if unresolved
                                else "dane-inputs-pdf",
                                day,
                                name,
                                municipality,
                                presentation,
                                value,
                                f"PDF page {page_no},col {col},y {top:.1f}; inputs-pdf-v4",
                                change,
                                {
                                    "sheet": "pdf",
                                    "parser_version": "inputs-pdf-v4",
                                    "printed_category": clean(title),
                                    "category": category,
                                    "presentation": presentation,
                                    "brand": "",
                                    "ica": "",
                                    "department": department,
                                    "municipality": municipality,
                                    "page": page_no,
                                    "printed_heading": heading,
                                    "quality_issue": "Publisher overprinted the product heading with a duplicate table title"
                                    if unresolved
                                    else None,
                                },
                            )
                            previous_heading = False
                        elif (
                            all("Bold" in w["fontname"] for w in ws)
                            or (
                                max(w["x1"] for w in ws) < price_left
                                and re.search(
                                    r",\s*(?:[\d.,]+\s+)?(?:kilo|gram|litro|cent|mili|unidad|metro|bolsa|dosis|gal[oó]n)",
                                    line,
                                    re.IGNORECASE,
                                )
                            )
                        ) and not line.startswith(
                            ("Fuente:", "Nota:", "Cuadro", "Precios")
                        ):
                            line = re.sub(
                                r"\s*\((?:continuaci[oó]n|conclusi[oó]n)\)",
                                "",
                                line,
                                flags=re.IGNORECASE,
                            ).strip()
                            heading = heading + " " + line if previous_heading else line
                            unresolved = False
                            previous_heading = True
                        else:
                            previous_heading = False
            page.close()

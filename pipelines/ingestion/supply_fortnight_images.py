"""Two-page image-only DANE Cuadro 1 with complete paired OCR evidence.

The exact original supplies the native reporting period. Neither page alone
publishes cells: both independently read halves must match, cover every literal
market, and reconcile with the printed TOTAL.
"""
import io
import re
from hashlib import sha256

import pdfplumber

DOCUMENT_ID = "274c6e10d3039f14d5aa1615d3bdfc39993d317c9841594179c0073ca88a151c"
SOURCE_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/bol_abas_1quincena_jun20.pdf"
PAGES = (2, 3)
BBOXES = {2: (70, 425, 535, 715), 3: (70, 115, 535, 331)}
TASK_SUFFIX = "; printed-row transcription-v2"
# Independently checked against this exact original's page 2: the table prints
# "Saper", while its prose prints "Samper". These two retained provider comments
# describe that literal spelling, not an unreadable cell. All other notes block.
VERIFIED_PRINTED_SPELLING_COMMENTS = frozenset({
    "The name 'Plaza Saper Mendoza' is transcribed exactly as printed, although 'Samper' is the standard spelling.",
    "Plaza Saper Mendoza is transcribed exactly as printed, which may be a typo for Plaza Samper Mendoza.",
})


def task_locator(number):
    return f"PDF page {number}; supply market table native extraction failed" + TASK_SUFFIX

# Independent literal enumeration of the two physical pages, including TOTAL.
MARKETS = {
    2: (
        ("Armenia", "Mercar"), ("Barranquilla", "Barranquillita"),
        ("Barranquilla", "Granabastos"), ("Bogotá, D.C.", "Corabastos"),
        ("Bogotá, D.C.", "Paloquemao"), ("Bogotá, D.C.", "Plaza Las Flores"),
        ("Bogotá, D.C.", "Plaza Saper Mendoza"), ("Bucaramanga", "Centroabastos"),
        ("Cali", "Cavasa"), ("Cali", "Santa Helena"), ("Cartagena", "Bazurto"),
        ("Cúcuta", "Cenabastos"), ("Cúcuta", "La Nueva Sexta"),
        ("Ibagué", "Plaza La 21"), ("Ipiales", "Centro de acopio"),
    ),
    3: (
        ("Manizales", "Centro Galerías"), ("Medellín", "Central Mayorista de Antioquia"),
        ("Medellín", 'Plaza Minorista "José María Villa"'), ("Montería", "Mercado del Sur"),
        ("Neiva", "Surabastos"), ("Pasto", "El Potrerillo"), ("Pereira", "Mercasa"),
        ("Popayán", "Plaza de mercado del barrio Bolívar"),
        ("Santa Marta", "Santa Marta (Magdalena)"), ("Sincelejo", "Nuevo Mercado"),
        ("Tunja", "Complejo de Servicios del Sur"), ("Valledupar", "Mercabastos"),
        ("Valledupar", "Mercado Nuevo"), ("Villavicencio", "CAV"), ("TOTAL", ""),
    ),
}


def normalized(value):
    from .worker import clean
    return clean(value).casefold().replace("“", '"').replace("”", '"')


def validate_original(original, document_id):
    if document_id != DOCUMENT_ID or sha256(original).hexdigest() != DOCUMENT_ID:
        raise ValueError("Unsupported two-page supply image original")
    with pdfplumber.open(io.BytesIO(original)) as pdf:
        if len(pdf.pages) < 3:
            raise ValueError("Supply image continuation page is missing")
        first, second = pdf.pages[1], pdf.pages[2]
        a, b = first.extract_text() or "", second.extract_text() or ""
        if not (
            "Primera quincena de junio de 2020" in a
            and "Cuadro 1. Variación en el abastecimiento" in a
            and "primera quincena de mayo y la primera quincena de junio de 2020" in a
            and "Fuente: DANE-Sipsa" in b and "Cuadro 2." in b
            and len(first.images) >= 50 and len(second.images) >= 50
            and not re.search(r"\b(?:5\.620|238\.744|241\.047)\b", a + b)
        ):
            raise ValueError("Supply image pages no longer match the failed native frame")


def queue(db, original, document_id):
    if document_id != DOCUMENT_ID:
        return []
    validate_original(original, document_id)
    from .ocr import enqueue_image
    queued = []
    with pdfplumber.open(io.BytesIO(original)) as pdf:
        for number in PAGES:
            # Cuadro 2 on the continuation must not be mistaken for Cuadro 1.
            image = pdf.pages[number - 1].crop(BBOXES[number]).to_image(resolution=240).original
            if enqueue_image(db, document_id,
                task_locator(number),
                image, "supply-reference-pdf", number):
                queued.append(number)
    return queued


def page_rows(original, document_id, page_number, reading):
    from .supply_period_summaries import _pdf_number, _row, periods
    from .worker import clean
    validate_original(original, document_id)
    notes = reading.get("review_notes")
    if (page_number not in PAGES or not isinstance(notes, list)
        or any(not isinstance(note, str) for note in notes)
        or (notes and (page_number != 2 or not set(notes) <= VERIFIED_PRINTED_SPELLING_COMMENTS))):
        raise ValueError("Supply image page or reading is uncertain")
    tables = reading.get("tables")
    if not isinstance(tables, list) or len(tables) != 1:
        raise ValueError("Supply OCR needs exactly the cropped Cuadro 1 table")
    cells = tables[0]
    if not isinstance(cells, list):
        raise ValueError("Supply OCR table rows are missing")
    if page_number == 2:
        if len(cells) != 16 or not isinstance(cells[0], list) or len(cells[0]) != 5:
            raise ValueError("First supply image needs its printed header and fifteen markets")
        header = [normalized(v) for v in cells[0]]
        if not (header[:2] == ["ciudad", "central"] and "mayo" in header[2]
            and "junio" in header[3] and "quincena" in header[2] and "quincena" in header[3]
            and "(t)" in header[2] and "(t)" in header[3] and "variaci" in header[4]
            and "%" in header[4]):
            raise ValueError("Supply image header lacks literal periods and tonne/percent units")
        cells = cells[1:]
    # The continuation has no printed header. Its date/unit binding comes from
    # page 2 and the exact native caption; an invented OCR header is rejected.
    if len(cells) != 15:
        raise ValueError("Supply continuation needs fourteen markets and its TOTAL")
    dates = periods("primera quincena de junio de 2020", "mayo", "junio")
    result = []
    for index, (cell, expected_market) in enumerate(zip(cells, MARKETS[page_number]), 1):
        if not isinstance(cell, list) or len(cell) != 5 or any(not isinstance(v, str) for v in cell):
            raise ValueError("Supply OCR needs five literal string cells per row")
        if tuple(map(normalized, cell[:2])) != tuple(map(normalized, expected_market)):
            raise ValueError("Supply OCR literal market order/identity mismatch")
        if any("?" in v for v in cell) or not re.fullmatch(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}%", cell[4]):
            raise ValueError("Supply OCR percentage is not certain and literal")
        if any(not re.fullmatch(r"(?:\d{1,3}(?:\.\d{3})+|\d+)", v) for v in cell[2:4]):
            raise ValueError("Supply OCR tonnes are not literal nonnegative integers")
        name = "TOTAL" if expected_market[0] == "TOTAL" else clean(cell[0]) + ", " + clean(cell[1])
        for column, (value, statistic, unit, period_index) in enumerate(zip(
            map(_pdf_number, cell[2:]), ("market_arrivals", "market_arrivals", "period_change"),
            ("t", "t", "percentage_points"), (0, 1, 1)), 2):
            result.append(_row(
                f"PDF page {page_number}, OCR table 1, row {index + (page_number == 2)}, column {column}",
                value, unit, name, dates[period_index], statistic,
                "reported_markets_total" if name == "TOTAL" else "market_total",
                source_page=page_number, literal_value=cell[column],
                table_caption="Cuadro 1. Primera quincena de mayo y junio de 2020",
                extraction_method="two-agreeing-image-OCR-readings",
                precision="printed_pdf_value", image_bbox=list(BBOXES[page_number]),
                period_heading_source_page=2,
                compared_period_start=dates[0][0].isoformat() if column == 4 else None,
                source_note=("La tabla imprime «Plaza Saper Mendoza» y el texto del boletín dice «Samper Mendoza»; se conserva el nombre literal de la tabla."
                    if expected_market[1] == "Plaza Saper Mendoza" else None),
            ))
    return result


def paired_page(original, document_id, page_number, readings):
    if len(readings) != 2:
        raise ValueError("Two independent supply image readings are required")
    first, second = (page_rows(original, document_id, page_number, r) for r in readings)
    identity = lambda rows: [(normalized(r["name"]), r["source_locator"], r["details"]["value"]) for r in rows]
    if identity(first) != identity(second):
        raise ValueError("Independent supply image readings disagree")
    return first


def cached_rows(db, original, document_id, expected_day=None):
    if document_id != DOCUMENT_ID:
        return []
    validate_original(original, document_id)
    if expected_day and (expected_day.year, expected_day.month, expected_day.day) != (2020, 6, 15):
        raise ValueError("Supply image source does not match the expected fortnight")
    from .ocr import VERSION
    result = []
    for page in PAGES:
        tasks = db.execute("SELECT image_id FROM source_ocr_task WHERE document_id=%s "
            "AND source_kind='supply-reference-pdf' AND source_page=%s AND source_locator=%s",
            (document_id, page, task_locator(page))).fetchall()
        if len(tasks) != 1:
            return []
        readings = db.execute("SELECT reading,result FROM source_ocr_result WHERE image_id=%s "
            "AND version=%s AND reading IN(0,1) ORDER BY reading", (tasks[0][0], VERSION)).fetchall()
        if len(readings) != 2 or [r[0] for r in readings] != [0, 1]:
            return []
        result.extend(paired_page(original, document_id, page, [r[1] for r in readings]))
    if len(result) != 90 or len({normalized(r["name"]) for r in result}) != 30:
        raise ValueError("Supply image Cuadro 1 lacks all twenty-nine markets and TOTAL")
    for offset in (0, 1):
        total = sum(r["details"]["value"] for r in result[:-3] if r["details"]["unit"] == "t"
                    and r["observed_on"] == result[-3 + offset]["observed_on"])
        if abs(total - result[-3 + offset]["details"]["value"]) > 29:
            raise ValueError("Supply image quantities conflict with printed TOTAL")
    return result


def publish_verified(db, original, document_id, page_number, readings):
    # Check this page immediately, including when the other half is pending.
    paired_page(original, document_id, page_number, readings)
    rows = cached_rows(db, original, document_id)
    if not rows:
        return 0
    from .supply_summaries import publish_rows
    with db.transaction():
        count = publish_rows(db, rows, document_id)
        db.execute("UPDATE ingestion_asset SET status='complete',records=%s,error=NULL,checked_at=now() "
            "WHERE document_id=%s AND kind='supply-reference-pdf' AND status='review'", (count, document_id))
        db.execute("UPDATE source_ocr_task SET status='published',checked_at=now(),error=NULL "
            "WHERE document_id=%s AND source_kind='supply-reference-pdf' AND source_locator=ANY(%s)",
            (document_id, [task_locator(p) for p in PAGES]))
    return count

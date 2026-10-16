"""Exact-source, complete Cuadro 1 recovery for three image-only DANE bulletins.

The native PDF frame establishes the period, units and page. Market identities
were read from those originals; numerical values enter only through two matching
OCR readings of the cropped printed table. No partial table is published.
"""

import io
import re
from dataclasses import dataclass
from datetime import date
from hashlib import sha256

import pdfplumber


@dataclass(frozen=True)
class Source:
    url: str
    page: int
    bbox: tuple[int, int, int, int]
    cover: str
    heading: str
    prior_header: str
    current_header: str
    caption: str
    period: str
    left: str
    right: str
    expected_day: date
    santa: str
    popayan: str


SOURCES = {
    "05abc2c0ccfce9a42f11805c1500fc81c8b8e10bdf025b4469569b06d98a5121": Source(
        "https://www.dane.gov.co/files/investigaciones/agropecuario/bol_abas_sep21.pdf",
        4, (70, 120, 525, 635), "Septiembre de 2021",
        "Agosto y septiembre de 2021", "Agosto 2021 (t)", "Septiembre 2021 (t)",
        "Cuadro 1. Agosto y septiembre de 2021, 29 mercados mayoristas",
        "septiembre de 2021", "agosto", "septiembre", date(2021, 9, 30),
        "Santa Elena", "Popayán*",
    ),
    "a978f0dcc210e831c2e3676b214448c121b846fd9152fdd88da5d1db5bd4a006": Source(
        "https://www.dane.gov.co/files/investigaciones/agropecuario/bol_abas_dic20.pdf",
        3, (50, 120, 575, 645), "Diciembre de 2020",
        "Noviembre y diciembre de 2020", "Noviembre 2020 (t)", "Diciembre 2020 (t)",
        "Cuadro 1. Noviembre y diciembre de 2020, 29 mercados mayoristas",
        "diciembre de 2020", "noviembre", "diciembre", date(2020, 12, 31),
        "Santa Helena", "Popayán",
    ),
    "2c298078437323885a5104ae6c902ea84e597bf4c65449b00da3e2961cea530d": Source(
        "https://www.dane.gov.co/files/investigaciones/agropecuario/bol_abas_1quincena_ene21.pdf",
        3, (50, 120, 575, 653), "Primera quincena de enero de 2021",
        "1 al 15 de diciembre de 2020 y 1 al 15 de enero de 2021",
        "Diciembre 2020 (t)", "Enero 2021 (t)",
        "Cuadro 1. Primera quincena de diciembre de 2020 y enero de 2021, 29 mercados mayoristas",
        "primera quincena de enero de 2021", "diciembre", "enero", date(2021, 1, 15),
        "Santa Helena", "Popayán",
    ),
}

SEPTEMBER_2021 = "05abc2c0ccfce9a42f11805c1500fc81c8b8e10bdf025b4469569b06d98a5121"
# These are the two retained provider notes from the exact cropped original.
# They concern only the footnote below the complete printed table. No general
# uncertainty, missing cells or different source is waived by this exception.
SEPTEMBER_FOOTNOTE_CROP_NOTES = frozenset((
    "The footnote at the bottom of the page is cropped and incomplete.",
    "The footnote at the bottom of the page is cropped: '* Para el día 27 de septiembre no hubo recolección de información en el mercado de Popayán, lo que afectó la información...'",
))
SEPTEMBER_POPAYAN_IMPUTATION = (
    "Para el día 27 de septiembre no hubo recolección de información en el mercado de Popayán, "
    "lo que afectó la información mensual, por lo cual se hizo necesario imputar estos datos, "
    "asumiendo que el dato faltante tiene un comportamiento igual al dato similar más próximo "
    "en el tiempo, es decir el 20 de septiembre."
)

# Identities only, taken from visual originals. Numeric test oracles stay outside runtime.
BASE_MARKETS = (
    ("Armenia", "Mercar"), ("Barranquilla", "Barranquillita"),
    ("Barranquilla", "Granabastos"), ("Bogotá, D.C.", "Corabastos"),
    ("Bogotá, D.C.", "Paloquemao"), ("Bogotá, D.C.", "Plaza Las Flores"),
    ("Bogotá, D.C.", "Plaza Samper Mendoza"), ("Bucaramanga", "Centroabastos"),
    ("Cali", "Cavasa"), ("Cali", None), ("Cartagena", "Bazurto"),
    ("Cúcuta", "Cenabastos"), ("Cúcuta", "La Nueva Sexta"),
    ("Ibagué", "Plaza La 21"), ("Ipiales", "Centro de acopio"),
    ("Manizales", "Centro Galerías"),
    ("Medellín", "Central Mayorista de Antioquia"),
    ("Medellín", 'Plaza Minorista "José María Villa"'),
    ("Montería", "Mercado del Sur"), ("Neiva", "Surabastos"),
    ("Pasto", "El Potrerillo"), ("Pereira", "Mercasa"),
    (None, "Plaza de mercado del barrio Bolívar"),
    ("Santa Marta", "Santa Marta (Magdalena)"),
    ("Sincelejo", "Nuevo Mercado"), ("Tunja", "Complejo de Servicios del Sur"),
    ("Valledupar", "Mercabastos"), ("Valledupar", "Mercado Nuevo"),
    ("Villavicencio", "CAV"), ("TOTAL", ""),
)


def _normal(value):
    from .worker import clean
    return clean(value).casefold().replace("“", '"').replace("”", '"')


def _markets(source):
    return tuple((source.popayan if city is None else city,
                  source.santa if market is None else market)
                 for city, market in BASE_MARKETS)


def task_locator(document_id):
    source = SOURCES[document_id]
    return f"PDF page {source.page}; supply market table native extraction failed; printed-row-v2"


def validate_original(original, document_id):
    if document_id not in SOURCES or sha256(original).hexdigest() != document_id:
        raise ValueError("Unsupported single-page supply image original")
    source = SOURCES[document_id]
    with pdfplumber.open(io.BytesIO(original)) as pdf:
        if len(pdf.pages) < source.page:
            raise ValueError("Supply image table page is missing")
        cover = pdf.pages[0].extract_text() or ""
        page = pdf.pages[source.page - 1]
        frame = page.extract_text() or ""
        if not (
            source.cover in cover and source.heading in frame
            and "Cuadro 1. Variación en el abastecimiento" in frame
            and "29 mercados mayoristas" in frame
            and "Fuente: DANE" in frame
            and len(page.images) >= 100
            and not re.search(r"(?<!\d)\d{1,3}\.\d{3}(?!\d)", frame)
        ):
            raise ValueError("Supply image native period/table frame changed")
    return source


def queue(db, original, document_id):
    if document_id not in SOURCES:
        return []
    source = validate_original(original, document_id)
    from .ocr import enqueue_image
    with pdfplumber.open(io.BytesIO(original)) as pdf:
        cropped = pdf.pages[source.page - 1].crop(source.bbox).to_image(resolution=240).original
    return [source.page] if enqueue_image(db, document_id, task_locator(document_id),
        cropped, "supply-reference-pdf", source.page) else []


def page_rows(original, document_id, page_number, reading):
    from .supply_period_summaries import _pdf_number, _row, periods
    from .worker import clean
    source = validate_original(original, document_id)
    notes = reading.get("review_notes") or []
    footnote_only = (document_id == SEPTEMBER_2021 and isinstance(notes, list)
                     and len(notes) == 1 and notes[0] in SEPTEMBER_FOOTNOTE_CROP_NOTES)
    if page_number != source.page or (notes and not footnote_only):
        raise ValueError("Supply image page or reading is uncertain")
    tables = reading.get("tables")
    if not isinstance(tables, list) or len(tables) != 1 or not isinstance(tables[0], list) or len(tables[0]) != 31:
        raise ValueError("Supply image requires one header, 29 markets, and TOTAL")
    header = tables[0][0]
    if not isinstance(header, list) or len(header) != 5 or any(not isinstance(v, str) for v in header):
        raise ValueError("Supply image requires five literal heading cells")
    words = list(map(_normal, header))
    if not (words[:2] == ["ciudad", "central"]
        and words[2:] == list(map(_normal, (source.prior_header, source.current_header, "Variación (%)")))):
        raise ValueError("Supply image headings conflict with the printed period/units")
    dates = periods(source.period, source.left, source.right)
    rows, totals, seen = [], [0.0, 0.0], set()
    for index, (cells, identity) in enumerate(zip(tables[0][1:], _markets(source)), 2):
        if not isinstance(cells, list) or len(cells) != 5 or any(not isinstance(v, str) for v in cells):
            raise ValueError("Supply OCR needs five literal strings per row")
        if any("?" in v for v in cells) or tuple(map(_normal, cells[:2])) != tuple(map(_normal, identity)):
            raise ValueError("Supply OCR literal market identity/order mismatch")
        if any(not re.fullmatch(r"(?:\d{1,3}(?:\.\d{3})+|\d+)", v) for v in cells[2:4]):
            raise ValueError("Supply OCR tonnes are not literal nonnegative integers")
        if not re.fullmatch(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}%", cells[4]):
            raise ValueError("Supply OCR percentage is not certain and literal")
        values = list(map(_pdf_number, cells[2:5]))
        if values[0] <= 0 or abs((values[1] - values[0]) / values[0] * 100 - values[2]) > 0.12:
            raise ValueError("Supply OCR percentage conflicts with printed rounded tonnes")
        total = index == 31
        name = "TOTAL" if total else clean(cells[0]) + ", " + clean(cells[1])
        if name in seen:
            raise ValueError("Supply OCR duplicate market")
        seen.add(name)
        if not total:
            totals[0] += values[0]
            totals[1] += values[1]
        for column, (value, statistic, unit, period_index) in enumerate(zip(
            values, ("market_arrivals", "market_arrivals", "period_change"),
            ("t", "t", "percentage_points"), (0, 1, 1)), 2):
            rows.append(_row(
                f"PDF page {source.page}, OCR table 1, row {index}, column {column}; printed-row-v2",
                value, unit, name, dates[period_index], statistic,
                "reported_markets_total" if total else "market_total",
                source_page=source.page, literal_value=cells[column],
                table_caption=source.caption,
                extraction_method="two-agreeing-image-OCR-readings",
                precision="printed_pdf_value", image_bbox=list(source.bbox),
                period_heading_source_page=source.page,
                compared_period_start=dates[0][0].isoformat() if column == 4 else None,
                source_note=(SEPTEMBER_POPAYAN_IMPUTATION
                    if document_id == SEPTEMBER_2021 and index == 24 else None),
            ))
    if len(seen) != 30 or len(rows) != 90:
        raise ValueError("Supply image Cuadro 1 market coverage incomplete")
    if any(abs(totals[i] - rows[-3 + i]["details"]["value"]) > 29 for i in (0, 1)):
        raise ValueError("Supply image market quantities conflict with printed TOTAL")
    return rows


def paired(original, document_id, page_number, readings):
    if len(readings) != 2:
        raise ValueError("Two independent supply image readings required")
    first, second = [page_rows(original, document_id, page_number, item) for item in readings]
    def identity(rows):
        return [(r["name"], r["source_locator"], r["details"]["literal_value"])
                for r in rows]
    if identity(first) != identity(second):
        raise ValueError("Independent supply image readings disagree")
    return first


def cached_rows(db, original, document_id, expected_day=None):
    if document_id not in SOURCES:
        return []
    source = validate_original(original, document_id)
    if expected_day and expected_day != source.expected_day:
        raise ValueError("Supply image source conflicts with expected report day")
    from .ocr import VERSION
    tasks = db.execute("SELECT image_id FROM source_ocr_task WHERE document_id=%s "
        "AND source_kind='supply-reference-pdf' AND source_page=%s AND source_locator=%s",
        (document_id, source.page, task_locator(document_id))).fetchall()
    if len(tasks) != 1:
        return []
    readings = db.execute("SELECT reading,result FROM source_ocr_result WHERE image_id=%s "
        "AND version=%s AND reading IN(0,1) ORDER BY reading", (tasks[0][0], VERSION)).fetchall()
    if len(readings) != 2 or [r[0] for r in readings] != [0, 1]:
        return []
    return paired(original, document_id, source.page, [r[1] for r in readings])


def publish_verified(db, original, document_id, page_number, readings):
    paired(original, document_id, page_number, readings)
    rows = cached_rows(db, original, document_id)
    if not rows:
        return 0
    from .supply_summaries import publish_rows
    with db.transaction():
        count = publish_rows(db, rows, document_id)
        db.execute("UPDATE ingestion_asset SET status='complete',records=%s,error=NULL,checked_at=now() "
            "WHERE document_id=%s AND kind='supply-reference-pdf' AND status='review'", (count, document_id))
        db.execute("UPDATE source_ocr_task SET status='published',checked_at=now(),error=NULL "
            "WHERE document_id=%s AND source_kind='supply-reference-pdf' AND source_locator=%s",
            (document_id, task_locator(document_id)))
    return count

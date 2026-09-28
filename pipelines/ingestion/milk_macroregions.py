"""Printed DANE milk macroregion means, separate from municipal observations.

Only explicit labels are prices: never infer values from bar height. Native
tables bypass OCR. Labelled raster charts require two complete agreeing readings.
"""

import calendar
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import pairwise

import pdfplumber

VERSION = "milk-macroregions-v2"
KIND = "milk-macroregion-pdf"
SERIES = "dane-milk-macroregion"
MONTHS = dict(
    zip(
        [
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
        ],
        range(1, 13),
    )
)
MONTH_PATTERN = "(?:" + "|".join(MONTHS) + ")"
REGIONS = (
    "Costa Caribe",
    "Antioquia y Eje Cafetero",
    "Boyacá y Cundinamarca",
    "Cauca, Nariño y Valle del Cauca",
    "Resto del país",
)
OCR_INSTRUCTION = """
This is a labelled DANE milk-price chart, not a price table. Transcribe exactly
ONE table with header [Macrorregión, <first full printed month and year>,
<second full printed month and year>], followed by all FIVE named regions.
Each price cell must contain the literal numeric label printed over its bar,
attached to the correct named region and month using the actual legend colors.
Do not estimate bar heights, transcribe axis tick values as prices, calculate
averages, infer absent labels, or reorder months. Preserve printed thousands
separators. Include the complete caption, unit-axis label and legend in text.
If any month, region, bar-label attachment, unit or digit is uncertain, record
that uncertainty in review_notes; never fill a missing value by similarity.
"""


def _norm(value):
    return " ".join(
        "".join(
            c
            for c in unicodedata.normalize("NFKD", str(value))
            if not unicodedata.combining(c)
        )
        .casefold()
        .replace("_", "-")
        .split()
    )


def _month_end(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])


@dataclass(frozen=True)
class Chart:
    page: int
    report_month: date
    months: tuple[date, date]
    caption: str
    basis_evidence: str
    bbox: tuple[float, float, float, float] | None
    native_rows: tuple = ()

    @property
    def locator(self):
        return f"PDF page {self.page}, milk macroregion chart 1; {VERSION}"


def _caption_months(text):
    pattern = rf"({MONTH_PATTERN})(?:\s+de)?(?:\s+(20\d{{2}}))?\s+y\s+({MONTH_PATTERN})\s+(?:de\s+)?(20\d{{2}})"
    found = re.search(pattern, _norm(text))
    if not found:
        raise ValueError("Milk macroregion chart lacks two explicit caption months")
    first, first_year, second, second_year = found.groups()
    year2 = int(second_year)
    year1 = int(first_year) if first_year else year2
    months = (_month_end(year1, MONTHS[first]), _month_end(year2, MONTHS[second]))
    if (months[1].year * 12 + months[1].month) - (
        months[0].year * 12 + months[0].month
    ) != 1:
        raise ValueError(
            "Milk macroregion caption months are not explicit consecutive months"
        )
    return months, found[0]


def _native_chart_reading(page, chart):
    """Bind literal vector labels to bars, legend colors, and named regions.

    Geometry only associates printed labels; bar height never produces a value.
    """
    colors = {}
    legend_tops = []
    month_names = {value: key for key, value in MONTHS.items()}
    for month in chart.months:
        matches = page.search(rf"{month_names[month.month]}\s+{month.year}", case=False)
        if len(matches) != 1:
            return None
        legend = matches[0]
        squares = [
            r
            for r in page.rects
            if r.get("fill")
            and 3 < r["x1"] - r["x0"] < 12
            and 3 < r["bottom"] - r["top"] < 12
            and 0 <= legend["x0"] - r["x1"] < 12
            and abs((r["top"] + r["bottom"] - legend["top"] - legend["bottom"]) / 2) < 3
        ]
        if len(squares) != 1:
            raise ValueError("Native milk chart month legend color is ambiguous")
        color = squares[0]["non_stroking_color"]
        if not isinstance(color, tuple) or color in colors:
            raise ValueError("Native milk chart month legend colors are not distinct")
        colors[color] = month
        legend_tops.append(legend["top"])
    bars = sorted(
        [
            r
            for r in page.rects
            if r.get("fill")
            and r.get("non_stroking_color") in colors
            and r["bottom"] - r["top"] > 40
            and r["x1"] - r["x0"] > 5
        ],
        key=lambda r: r["x0"],
    )
    if (
        len(bars) != 10
        or max(r["bottom"] for r in bars) - min(r["bottom"] for r in bars) > 0.5
    ):
        raise ValueError("Native milk chart does not have ten uniquely labelled bars")
    pairs = [bars[i : i + 2] for i in range(0, 10, 2)]
    if any(
        abs(a["x1"] - b["x0"]) > 0.5
        or a["non_stroking_color"] == b["non_stroking_color"]
        for a, b in pairs
    ):
        raise ValueError("Native milk chart bar grouping is ambiguous")
    centers = [(a["x0"] + b["x1"]) / 2 for a, b in pairs]
    boundaries = (
        [bars[0]["x0"] - 30]
        + [(a + b) / 2 for a, b in pairwise(centers)]
        + [bars[-1]["x1"] + 30]
    )
    words = page.extract_words()
    table = [
        ["Macrorregión", *[f"{month_names[m.month]} {m.year}" for m in chart.months]]
    ]
    bindings = {}
    for i, pair in enumerate(pairs):
        label_words = [
            w
            for w in words
            if boundaries[i] < (w["x0"] + w["x1"]) / 2 < boundaries[i + 1]
            and pair[0]["bottom"] + 2 < w["top"] < min(legend_tops) - 4
        ]
        region = " ".join(
            w["text"] for w in sorted(label_words, key=lambda w: (w["top"], w["x0"]))
        )
        if _norm(region) not in {_norm(r) for r in REGIONS}:
            raise ValueError(
                "Native milk chart region label could not be bound to its bars"
            )
        values = {}
        for bar in pair:
            candidates = [
                w
                for w in words
                if re.fullmatch(r"\d[\d.,]*", w["text"])
                and abs((w["x0"] + w["x1"] - bar["x0"] - bar["x1"]) / 2)
                < (bar["x1"] - bar["x0"]) * 0.25
                and 0 < bar["top"] - w["bottom"] < 16
            ]
            if len(candidates) != 1:
                raise ValueError(
                    "Native milk chart bar has no unique printed numeric label"
                )
            month = colors[bar["non_stroking_color"]]
            values[month] = candidates[0]["text"]
            bindings[f"{_norm(region)}|{month}"] = {
                "bar_bbox": [bar[k] for k in ("x0", "top", "x1", "bottom")],
                "label_bbox": [candidates[0][k] for k in ("x0", "top", "x1", "bottom")],
                "legend_color": list(bar["non_stroking_color"]),
            }
        table.append([region, *[values[m] for m in chart.months]])
    # Content-stream order preserves the rotated native axis label which the
    # usual horizontal extract_text order splits into individual letters.
    native_text = (
        (page.extract_text() or "") + "\n" + "".join(c["text"] for c in page.chars)
    )
    return {
        "text": native_text,
        "tables": [table],
        "review_notes": [],
        "native_bindings": bindings,
    }


def inspect(data, expected_day=None):
    """Recognize this bounded cover-chart layout and prove native failure.

    Unsupported other figures are not sent to OCR just because they are images.
    """
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        page = pdf.pages[0]
        text = page.extract_text() or ""
        normalized = _norm(text)
        if not re.search(
            r"grafico\s+1[.\s].*precio.*leche cruda en finca", normalized
        ) or not re.search(r"5\s+macror?regiones lecheras", normalized):
            return None
        stamp = re.search(
            rf"sipsa[- ]l\)\s+({MONTH_PATTERN})\s+de\s+(20\d{{2}})", normalized
        )
        if not stamp:
            raise ValueError("Milk macroregion report month is not explicit")
        report_month = _month_end(int(stamp[2]), MONTHS[stamp[1]])
        from .worker import SourceDateMismatch, today

        if report_month > today() or (expected_day and expected_day != report_month):
            raise SourceDateMismatch(
                "Milk macroregion report month differs from archive date or is future"
            )
        months, caption = _caption_months(normalized.split("grafico", 1)[1])
        if months[1] != report_month:
            raise SourceDateMismatch(
                "Milk macroregion chart month differs from report month"
            )
        # Earlier covers omit 'promedio' in the caption; the native methodology
        # explicitly identifies this report's prices as published monthly means.
        basis_text = text
        if (
            not re.search(r"precio(?:s)?\s+(?:de venta\s+)?promedio", _norm(basis_text))
            and len(pdf.pages) > 1
        ):
            basis_text += "\n" + (pdf.pages[1].extract_text() or "")
        mean = re.search(
            r"precio(?:s)?\s+(?:de venta\s+)?promedio[^.\n]{0,130}",
            basis_text,
            re.IGNORECASE,
        )
        if not mean:
            raise ValueError(
                "Milk macroregion mean basis is not explicit in native caption or methodology"
            )
        chart = Chart(1, report_month, months, caption, mean[0], None)
        # Explicit native tables, if present, take precedence over image OCR.
        tables = [
            t
            for t in page.extract_tables()
            if t
            and len(t[0]) == 3
            and _norm(t[0][0] or "") in {"macrorregion", "macroregion", "region"}
        ]
        if tables:
            rows = parse_reading(
                chart,
                {"text": text, "tables": tables, "review_notes": []},
                method="native-pdf-table",
            )
            return Chart(1, report_month, months, caption, mean[0], None, tuple(rows))
        native_chart = _native_chart_reading(page, chart)
        if native_chart:
            rows = parse_reading(
                chart, native_chart, method="native-pdf-chart-label-geometry"
            )
            return Chart(1, report_month, months, caption, mean[0], None, tuple(rows))
        headings = [
            w
            for w in page.extract_words()
            if _norm(w["text"]) in {"grafico", "gráfico"}
        ]
        if not headings:
            raise ValueError("Milk macroregion caption geometry is missing")
        heading_top = min(w["top"] for w in headings)
        images = [
            im
            for im in page.images
            if im["top"] > heading_top
            and im["x1"] - im["x0"] > page.width * 0.45
            and im["bottom"] - im["top"] > 100
        ]
        if len(images) != 1:
            raise ValueError("Milk macroregion chart image cannot be isolated uniquely")
        im = images[0]
        native_labels = [
            c
            for c in page.chars
            if im["x0"] <= c["x0"] <= im["x1"]
            and im["top"] <= c["top"] <= im["bottom"]
            and c["text"].strip()
        ]
        if native_labels:
            raise ValueError(
                "Milk macroregion chart has native labels but no supported native binding; not an OCR failure"
            )
        bbox = (
            0,
            max(0, heading_top - 3),
            page.width,
            min(page.height, im["bottom"] + 8),
        )
        return Chart(1, report_month, months, caption, mean[0], bbox)


def _reading_month(value):
    match = re.fullmatch(rf"({MONTH_PATTERN})\s+(?:de\s+)?(20\d{{2}})", _norm(value))
    if not match:
        raise ValueError("Milk chart reading lacks a full month/year legend")
    return _month_end(int(match[2]), MONTHS[match[1]])


def parse_reading(chart, reading, *, method="paired-image-ocr"):
    """Validate all ten literal labels; missing/ambiguous values fail closed."""
    if reading.get("review_notes") or "?" in str(reading):
        raise ValueError("Milk chart reading contains uncertainty")
    if not re.search(
        r"precio(?:s)?\s+(?:de venta\s+)?promedio", _norm(chart.basis_evidence)
    ):
        raise ValueError("Milk chart lacks verified published mean basis")
    text = _norm(reading.get("text", ""))
    if not re.search(r"(?:precio|pesos)\s+por\s+litro", text):
        raise ValueError("Milk chart reading lacks the printed litre price unit")
    if not re.search(r"5\s+macror?regiones", text):
        raise ValueError(
            "Milk chart reading lacks the explicit five-macroregion caption"
        )
    caption_months, _ = _caption_months(text)
    if caption_months != chart.months:
        raise ValueError("Milk chart reading caption disagrees with native months")
    tables = reading.get("tables", [])
    if (
        len(tables) != 1
        or len(tables[0]) != 6
        or any(len(row) != 3 for row in tables[0])
    ):
        raise ValueError(
            "Milk chart needs exactly five named regions and ten printed labels"
        )
    header, *values = tables[0]
    if _norm(header[0]) not in {"macrorregion", "macroregion", "region"}:
        raise ValueError("Milk chart region heading is missing")
    if tuple(_reading_month(v) for v in header[1:]) != chart.months:
        raise ValueError(
            "Milk chart legend columns do not match the printed caption months"
        )
    # October 2025 prints comma thousands throughout the chart. Accept that
    # alternate format only when every one of the ten labels uses complete
    # three-digit groups. A lone comma cell or mixed conventions remain review.
    comma_thousands = all(
        re.fullmatch(r"[1-9]\d{0,2}(?:,\d{3})+", str(v).strip())
        for row in values
        for v in row[1:]
    )
    aliases = {_norm(region): region for region in REGIONS}
    seen = set()
    rows = []
    for region, *prices in values:
        key = _norm(region)
        if key not in aliases or key in seen:
            raise ValueError("Milk chart region is missing, repeated, or unrecognized")
        seen.add(key)
        canonical = aliases[key]
        for day, literal in zip(chart.months, prices):
            literal = str(literal).strip()
            if not comma_thousands and not re.fullmatch(
                r"(?:[1-9]\d*|[1-9]\d{0,2}(?:\.\d{3})+)(?:,\d{1,2})?", literal
            ):
                raise ValueError("Milk chart price is not a literal Colombian number")
            price = Decimal(
                literal.replace(",", "")
                if comma_thousands
                else literal.replace(".", "").replace(",", ".")
            )
            if not 0 < price < 100000:
                raise ValueError(
                    "Milk chart price is outside the supported literal range"
                )
            rows.append(
                {
                    "product_id": "leche-cruda-en-finca-macrorregional",
                    "product_name": "Leche cruda en finca · promedio macrorregional",
                    "category": "Leche cruda en finca",
                    "publisher": "DANE",
                    "series": SERIES,
                    "basis": "Promedio mensual publicado en finca por macrorregión",
                    "currency": "COP",
                    "unit": "litro",
                    "market": canonical,
                    "date": day,
                    "period_start": day.replace(day=1),
                    "price": float(price),
                    "source_page": chart.page,
                    "source_locator": f"PDF page {chart.page}, chart 1, region {canonical}, month {day:%Y-%m}",
                    "identity_dimensions": {
                        "geographic_level": "macroregion",
                        "statistic": "published_mean",
                    },
                    "details": {
                        "extraction_method": method,
                        "source_page": chart.page,
                        "geographic_level": "macroregion",
                        "statistic": "published_mean",
                        "price_statistic": "published_mean",
                        "period": "monthly",
                        "period_type": "monthly",
                        "bulletin_period": chart.report_month.isoformat(),
                        "period_end": day.isoformat(),
                        "original_unit": "Precio por litro",
                        "literal_price": literal,
                        "literal_region": region,
                        "literal_month": header[1 + chart.months.index(day)],
                        "native_caption": chart.caption,
                        "native_basis_evidence": chart.basis_evidence,
                        "native_label_binding": reading.get("native_bindings", {}).get(
                            f"{key}|{day}"
                        ),
                        "not_municipal": True,
                        "not_derived_from_bar_height": True,
                    },
                }
            )
    if seen != set(aliases):
        raise ValueError("Milk chart does not cover all five explicitly named regions")
    if comma_thousands:
        for row in rows:
            row["details"]["literal_number_format"] = "whole-chart-comma-thousands"
    return rows


def _cosmetic_note_categories(chart, reading):
    """Finite observed annotations, not a sentiment/uncertainty classifier.

    Exact whole-note matching prevents an accepted prefix from masking another
    concern. Context must corroborate the quoted spelling/legend/footer too.
    The caller still validates both complete readings and their agreement.
    """
    notes = reading.get("review_notes", [])
    if not isinstance(notes, list) or any(not isinstance(n, str) for n in notes):
        raise ValueError("Milk chart review notes have an unsupported shape")
    text = _norm(reading.get("text", ""))
    categories = []
    footers = {
        "The source line 'Fuente: DANE, SIPSA' is partially cropped at the bottom of the image.",
        "The source line at the bottom is partially cropped but legible as 'Fuente: DANE, SIPSA.'",
        "The source line at the bottom is partially cropped but clearly reads 'Fuente: DANE, SIPSA'.",
        "The footnote 'Fuente: DANE, SIPSA.' is slightly cropped at the bottom of the image but remains legible.",
        "The bottom source text 'Fuente: DANE, SIPSA' is partially cropped but legible.",
        "The source line at the bottom is partially cropped but readable as 'Fuente: DANE, SIPSA'.",
    }
    spacing = {
        "The legend label for February is printed as 'Febrero2025' without a space.",
        "The legend label 'Febrero2025' is printed without a space between the month and the year.",
    }
    for note in notes:
        if (
            note
            == "The subtitle in the image contains the spelling 'macroregiones' with a single 'r'."
            and re.search(r"\b5 macroregiones lecheras\b", text)
        ):
            categories.append("subtitle-spelling")
        elif (
            note in spacing
            and date(2025, 2, 28) in chart.months
            and re.search(r"\bfebrero2025\b", text)
        ):
            categories.append("legend-spacing")
        elif note in footers and "fuente: dane, sipsa" in text:
            categories.append("publisher-footer-crop")
        else:
            raise ValueError("Milk chart reading contains an unrecognized review note")
    return categories


def paired_rows(chart, readings):
    if len(readings) != 2:
        raise ValueError("Milk chart requires two independent readings")
    categories = [_cosmetic_note_categories(chart, r) for r in readings]
    # New top-level dictionaries only: retain the cached originals unchanged.
    # Standalone parse_reading remains strict; no annotated single reading can
    # become a publication by bypassing the paired contract.
    pairs = [parse_reading(chart, {**r, "review_notes": []}) for r in readings]
    signature = lambda rows: sorted(
        (r["market"], r["date"], r["price"], r["unit"], r["basis"]) for r in rows
    )
    if signature(pairs[0]) != signature(pairs[1]):
        raise ValueError(
            "Independent milk chart readings disagree; no prices published"
        )
    if any(categories):
        for row in pairs[0]:
            row["details"].update(
                original_review_notes=[
                    list(r.get("review_notes", [])) for r in readings
                ],
                accepted_cosmetic_note_categories=[list(c) for c in categories],
            )
    return pairs[0]


def enqueue(db, data, document_id, expected_day=None):
    """Queue only the isolated image-price chart after native extraction fails."""
    chart = inspect(data, expected_day)
    if chart is None or chart.native_rows:
        return chart
    from .ocr import enqueue_image

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        image = (
            pdf.pages[chart.page - 1].crop(chart.bbox).to_image(resolution=220).original
        )
    if not enqueue_image(db, document_id, chart.locator, image, KIND, chart.page):
        raise ValueError("Milk macroregion chart image was too small to retain")
    return chart


def eligible_task(db, document_id, locator):
    original = db.execute(
        "SELECT content FROM source_document WHERE id=%s", (document_id,)
    ).fetchone()
    if not original:
        raise ValueError("Milk macroregion original is missing")
    assets = db.execute(
        "SELECT observed_on,status,error FROM ingestion_asset WHERE document_id=%s AND kind='milk-pdf'",
        (document_id,),
    ).fetchall()
    if not assets:
        raise ValueError(
            "Milk macroregion original has no current validated source asset"
        )
    if any(row[1] in {"review", "failed"} for row in assets):
        raise ValueError(
            "Milk macroregion source is under document review; chart prices remain unpublished"
        )
    chart = inspect(bytes(original[0]))
    if (
        chart is None
        or chart.native_rows
        or chart.locator != locator
        or chart.bbox is None
    ):
        raise ValueError(
            "Milk macroregion task no longer has a verified native extraction failure"
        )
    if any(row[0] and row[0] != chart.report_month for row in assets):
        raise ValueError(
            "Milk macroregion source archive date differs from the verified report month"
        )
    from .worker import parser_version

    if not db.execute(
        "SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='milk:municipal'",
        (document_id, parser_version("milk-pdf")),
    ).fetchone():
        raise ValueError(
            "Milk macroregion source has no current strict native/date validation checkpoint"
        )
    return chart


def publish_readings(db, document_id, locator, image_id, readings):
    from .ocr import VERSION as OCR_VERSION
    from .official_sources import publish_rows

    chart = eligible_task(db, document_id, locator)
    rows = paired_rows(chart, readings)
    for row in rows:
        row["details"].update(
            source_image_id=image_id, ocr_version=OCR_VERSION, agreeing_readings=2
        )
    return publish_rows(db, rows, document_id, KIND)

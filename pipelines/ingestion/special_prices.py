"""Farm-gate raw milk and mill rice series, distinct from wholesale prices."""

import calendar
import re
from datetime import date, datetime
from decimal import Decimal

DEPARTMENTS = "Amazonas|Antioquia|Arauca|Atlántico|Bogotá D.C.|Bolívar|Boyacá|Caldas|Caquetá|Casanare|Cauca|Cesar|Chocó|Córdoba|Cundinamarca|Guainía|Guaviare|Huila|La Guajira|Magdalena|Meta|Nariño|Norte de Santander|Putumayo|Quindío|Risaralda|San Andrés|Santander|Sucre|Tolima|Valle del Cauca|Vaupés|Vichada".split(
    "|"
)


def parse_special(data, kind, publication_day=None):
    from .worker import (
        MONTH_NUM,
        SourceDateMismatch,
        clean,
        positive,
        publication_month,
        record,
        slug,
        today,
        workbooks,
    )

    found = 0
    for sheet, rows in workbooks(data):
        header = {}
        printed_period = publication_month(sheet, "")
        grouped_header = None
        grouped_department = ""
        litre_unit = False
        departments = {slug(d): d for d in DEPARTMENTS}
        for row_no, row in enumerate(rows, 1):
            if not any(v is not None and v != "" for v in row):
                continue
            names = [clean(v) for v in row]
            if not header:
                printed_period = (
                    publication_month(" ".join(names), "") or printed_period
                )
            if kind == "milk":
                litre_unit = litre_unit or any(
                    "pesos-por-litro" in slug(v) for v in names
                )
                grouped_names = {slug(v): i for i, v in enumerate(names) if v}
                required = (
                    "departamentos-y-municipios",
                    "precio-minimo",
                    "precio-maximo",
                    "precio-promedio",
                )
                if all(key in grouped_names for key in required):
                    grouped_header = {key: grouped_names[key] for key in required}
                    continue
                if grouped_header:
                    place, low, high, value = [
                        row[grouped_header[key]] for key in required
                    ]
                    if all(v is None or v == "" for v in (low, high, value)):
                        if clean(place):
                            grouped_department = departments.get(slug(place), "")
                        continue
                    if not positive(value):
                        continue
                    if not litre_unit or not grouped_department or not clean(place):
                        raise ValueError(
                            "Grouped milk table has unverified unit or location"
                        )
                    # Excel cached floating means can differ from an exact
                    # endpoint by a few 1e-13 pesos; preserve that original
                    # value, allowing only numerical representation tolerance.
                    if (
                        not positive(low)
                        or not positive(high)
                        or not low - 1e-9 <= value <= high + 1e-9
                    ):
                        raise ValueError(
                            "Grouped milk price is outside its reported minimum/maximum"
                        )
                    if (
                        printed_period
                        and publication_day
                        and printed_period != publication_day
                    ):
                        raise SourceDateMismatch(
                            "Special-series table month differs from archive link"
                        )
                    day = printed_period or publication_day
                    if day is None:
                        raise ValueError("Grouped milk table has no verified month")
                    if day > today():
                        raise SourceDateMismatch(
                            "Grouped milk table month is in the future"
                        )
                    found += 1
                    yield record(
                        "dane-milk-farm",
                        day,
                        "Leche cruda en finca",
                        clean(place),
                        "litre",
                        value,
                        f"{sheet}!row {row_no}",
                        details={
                            "department": grouped_department,
                            "municipality": clean(place),
                            "price_basis": "farmgate",
                            "min_price": low,
                            "max_price": high,
                            "quality_issue": None,
                        },
                    )
                    continue
            if any(
                v in names
                for v in (
                    "Precio por tonelada",
                    "Precio promedio por litro",
                    "Pesos por litro",
                )
            ):
                header = {v: i for i, v in enumerate(names) if v}
                continue
            if header and any(v in names for v in ("Nombre municipio", "Precio medio")):
                header.update({v: i for i, v in enumerate(names) if v})
                continue
            if not header:
                continue

            def get(*names):
                return next(
                    (
                        row[header[n]]
                        for n in names
                        if n in header and header[n] < len(row)
                    ),
                    None,
                )

            value = get(
                "Precio por tonelada", "Precio promedio por litro", "Precio medio"
            )
            if not positive(value):
                continue
            d = get("Fecha", "Mes y año")
            if isinstance(d, (date, datetime)):
                year, month = d.year, d.month
            elif get("Año"):
                year = int(get("Año"))
                m = clean(get("Mes")).lower()
                month = int(m) if m.isdigit() else MONTH_NUM.get(m)
                if not month:
                    raise ValueError("Unknown special-series month: " + m)
            elif publication_day:
                if printed_period and printed_period != publication_day:
                    raise SourceDateMismatch(
                        "Special-series table month differs from archive link"
                    )
                year, month = publication_day.year, publication_day.month
            else:
                raise ValueError("Missing special-series observation month")
            day = date(year, month, calendar.monthrange(year, month)[1])
            if day > today():
                continue
            rice = kind == "rice"
            name = clean(get("Producto")) if rice else "Leche cruda en finca"
            town = clean(get("Municipio", "Nombre municipio"))
            department = clean(get("Departamento", "Nombre departamento"))
            if not name:
                raise ValueError("Missing special-series product")
            found += 1
            yield record(
                "dane-rice-mill" if rice else "dane-milk-farm",
                day,
                name,
                town,
                "tonne" if rice else "litre",
                value,
                f"{sheet}!row {row_no}",
                details={
                    "department": department,
                    "municipality": town,
                    "municipality_code": clean(
                        get("Código Municipio", "Código municipio")
                    ),
                    "price_basis": "mill" if rice else "farmgate",
                    "min_price": get("Precio mínimo"),
                    "max_price": get("Precio máximo"),
                    "quality_issue": "Publisher omitted location"
                    if not town or not department
                    else None,
                },
            )
    if not found:
        raise ValueError("No " + kind + " price observations parsed")


def project_special(db, did, url):
    from .worker import slug

    places = {
        (slug(d), slug(n)): (n, d)
        for n, d in db.execute("SELECT name,department FROM municipality").fetchall()
    }
    products = {}
    markets = {}
    values = {}
    conflicts = set()
    for loc, series, day, name, town, unit, price, meta in db.execute(
        "SELECT source_locator,series,observed_on,product_name,market_name,unit,price,details FROM historical_price WHERE document_id=%s",
        (did,),
    ).fetchall():
        if not town or not meta.get("department"):
            conflicts.add(("missing-location", loc))
            continue
        rice = series == "dane-rice-mill"
        pid = ("molino-" if rice else "") + slug(name)
        town, department = places.get(
            (slug(meta["department"]), slug(town)), (town, meta["department"])
        )
        mid = ("molino-" if rice else "finca-") + slug(department + "-" + town)
        products[pid] = (
            pid,
            name + " · en molino" if rice else name,
            "Arroz y subproductos en molino" if rice else "Leche cruda en finca",
        )
        markets[mid] = (
            mid,
            town + (" · molinos" if rice else " · leche en finca"),
            town,
            department,
        )
        key = (pid, mid, day)
        # The application compares COP/kg; retain original COP/tonne in raw history.
        converted = price / 1000 if rice else price
        bounds = tuple(
            Decimal(str(meta[field])) / 1000
            if rice and meta.get(field) is not None
            else meta.get(field)
            for field in ("min_price", "max_price")
        )
        if key in values and values[key][6:9] != (converted, *bounds):
            conflicts.add(key)
        values[key] = (
            pid,
            mid,
            series,
            day,
            "monthly",
            "kg" if rice else "litre",
            converted,
            *bounds,
            url,
            did,
            loc
            + (
                "; COP/tonelada dividido entre 1000 = COP/kg"
                if rice
                else "; precio en finca, COP/litro"
            ),
        )
    with db.transaction(), db.cursor() as cur:
        cur.executemany(
            "INSERT INTO product(id,name,category) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
            products.values(),
        )
        cur.executemany(
            "INSERT INTO market(id,name,city,region) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            markets.values(),
        )
        columns = "product_id,market_id,source_id,observed_on,period,unit,price,min_price,max_price,source_url,document_id,source_locator"
        cur.execute(
            f"CREATE TEMP TABLE IF NOT EXISTS special_price_stage ON COMMIT DROP AS SELECT {columns} FROM price_observation WITH NO DATA"
        )
        cur.execute("TRUNCATE pg_temp.special_price_stage")
        with cur.copy(
            f"COPY pg_temp.special_price_stage ({columns}) FROM STDIN"
        ) as copy:
            for key, row in values.items():
                if key not in conflicts:
                    copy.write_row(row)
        cur.execute(
            f"""INSERT INTO price_observation({columns})
            SELECT {columns} FROM pg_temp.special_price_stage WHERE true
            ON CONFLICT(product_id,market_id,source_id,observed_on,period,unit)
            DO UPDATE SET price=excluded.price,min_price=excluded.min_price,max_price=excluded.max_price,source_url=excluded.source_url,document_id=excluded.document_id,source_locator=excluded.source_locator
            WHERE (price_observation.price,price_observation.min_price,price_observation.max_price,price_observation.document_id,price_observation.source_locator)
              IS DISTINCT FROM (excluded.price,excluded.min_price,excluded.max_price,excluded.document_id,excluded.source_locator)
            AND (SELECT retrieved_at FROM source_document WHERE id=excluded.document_id)
              >=coalesce((SELECT retrieved_at FROM source_document WHERE id=price_observation.document_id),'-infinity'::timestamptz)
            AND ((SELECT media_type FROM source_document WHERE id=excluded.document_id)<>'application/pdf'
             OR (SELECT media_type FROM source_document WHERE id=price_observation.document_id)='application/pdf'
             OR EXISTS(SELECT 1 FROM ingestion_asset WHERE document_id=price_observation.document_id AND status='review'))""",
        )
    return len(conflicts)


class MilkNarrativeOnly(ValueError):
    """Readable modern bulletin with labelled figures, without a price table."""


def _milk_full_width_table(page):
    """Identify one monetary grid crossing the page midpoint from its headers.

    September 2021 uses one wide table rather than the historical two-column
    layout. Requiring all four aligned native labels keeps a narrative, scan or
    two independent narrow tables out of this fallback.
    """
    if not hasattr(page, "extract_words"):
        return False
    words = page.extract_words()
    headers = {}
    for label in ("Departamentos", "Mínimo", "Máximo", "Promedio"):
        matches = [word for word in words if word["text"] == label]
        if len(matches) != 1:
            return False
        headers[label] = matches[0]
    department, low, high, mean = (headers[label] for label in headers)
    return (
        department["x0"] < low["x0"] < page.width / 2 < high["x0"] < mean["x0"]
        and max(word["top"] for word in headers.values())
        - min(word["top"] for word in headers.values())
        < 30
        and len(
            [
                word
                for word in words
                if word["text"] == "Precio"
                and abs(word["top"] - low["top"]) < 30
            ]
        )
        == 3
    )


def _milk_narrative_month(texts, native_pages):
    """Recognize the explicit modern report structure, never an unreadable grid."""
    from .worker import MONTH_NUM

    if not texts or not native_pages:
        return None
    text = "\n".join(texts)
    if not all(
        marker in text.casefold()
        for marker in ("boletín técnico", "introducción", "ficha metodológica")
    ):
        return None
    if re.search(
        r"\b(?:cuadro|tabla)\s+\d|departamentos\s+y\s+municipios"
        r"|m[ií]nimo\s+m[aá]ximo\s+(?:medio|promedio)",
        text,
        re.IGNORECASE,
    ):
        return None
    stamp = re.search(
        r"Precios?\s+de\s+Leche\s+Cruda\s+en\s+Finca\s*\(SIPSA-L\)"
        r"\s+([a-záéíóú]+)\s+de\s+(20\d{2})",
        texts[0],
        re.IGNORECASE,
    )
    if not stamp or stamp[1].lower() not in MONTH_NUM:
        return None
    month, year = MONTH_NUM[stamp[1].lower()], int(stamp[2])
    return date(year, month, calendar.monthrange(year, month)[1])


def parse_milk_pdf(data, day):
    """Read the two newspaper-style columns in historical milk bulletins."""
    import io

    import pdfplumber

    from .pdf_sources import has_table_sized_image
    from .worker import MONTH_NUM, SourceDateMismatch, clean, record, slug, today

    if day is not None and day > today():
        raise SourceDateMismatch("Milk PDF table month is in the future")
    lookup = {slug(d): d for d in DEPARTMENTS}
    compact_departments = {key.replace("-", ""): value for key, value in lookup.items()}
    found = 0
    department = ""
    texts = []
    native_pages = True
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            texts.append(text)
            # Do not turn a scan or an unlabelled substantial image into a
            # successful zero-row report. Modern bulletins label each large
            # illustration as a graph or map in readable native text.
            native_pages = (
                native_pages
                and len(text.strip()) >= 100
                and (
                    not getattr(page, "images", [])
                    or not has_table_sized_image(page)
                    or bool(
                        re.search(
                            r"Gr[aá]fico\s+\d+|siguiente\s+mapa", text, re.IGNORECASE
                        )
                    )
                )
            )
            if not (
                "Departamentos" in text
                and "municipios" in text
                and ("Medio" in text or "Promedio" in text)
            ):
                page.close()
                continue
            full_width = _milk_full_width_table(page)
            # A bulletin's publication date can be months after its observations.
            # Historical tables state their observation month after the caption.
            # Do not substitute the publication date or an unrelated chart date.
            stamps = re.finditer(
                r"Precios\s+de\s+leche\s+cruda\s+en\s+finca"
                r"(?:\s+\((?:continuaci[oó]n|conclusi[oó]n)\))?"
                r"\s+(20\d{2})\s*\(([a-záéíóú]+)\)",
                text,
                re.IGNORECASE,
            )
            for stamp in stamps:
                month = MONTH_NUM.get(stamp[2].lower())
                if month is None:
                    raise ValueError("Milk PDF table has an unknown observation month")
                year = int(stamp[1])
                printed_day = date(year, month, calendar.monthrange(year, month)[1])
                if printed_day > today():
                    raise SourceDateMismatch("Milk PDF table month is in the future")
                if day is not None and printed_day != day:
                    raise SourceDateMismatch(
                        "Milk PDF table month differs from archive link or another table"
                    )
                day = printed_day
            if full_width:
                # This layout prints its observation month in the repeated
                # report heading above every table. The cover's separate
                # publication date and unrelated narrative dates are excluded.
                heading = text.split("Departamentos", 1)[0]
                stamp = re.search(
                    r"(?:^|\n)Leche\s+Cruda\s+en\s+Finca\s*\n"
                    r"([a-záéíóú]+)\s+de\s+(20\d{2})(?:\s*\n|$)",
                    heading,
                    re.IGNORECASE,
                )
                if not stamp or stamp[1].lower() not in MONTH_NUM:
                    raise ValueError("Milk wide table has no verifiable report month")
                month, year = MONTH_NUM[stamp[1].lower()], int(stamp[2])
                printed_day = date(year, month, calendar.monthrange(year, month)[1])
                if printed_day > today() or (day is not None and day != printed_day):
                    raise SourceDateMismatch(
                        "Milk PDF report month differs from archive link or another table"
                    )
                day = printed_day
            if day is None:
                raise ValueError("Milk bulletin has no verifiable publication month")
            columns = (
                [(0, page.width)]
                if full_width
                else [(0, page.width / 2), (page.width / 2, page.width)]
            )
            for column, (left, right) in enumerate(columns, 1):
                lines = (
                    page.crop((left, 0, right, page.height)).extract_text() or ""
                ).splitlines()
                enabled = False
                town_prefix = ""
                pending_price = ""
                for line_no, line in enumerate(lines, 1):
                    line = clean(line)
                    if pending_price:
                        if not re.fullmatch(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'-]{1,79}", line):
                            raise ValueError(
                                "Milk PDF wrapped municipality could not be resolved"
                            )
                        line = town_prefix + " " + line + " " + pending_price
                        town_prefix = pending_price = ""
                    if (
                        "Mínimo" in line
                        and "Máximo" in line
                        and ("Medio" in line or "Promedio" in line)
                    ):
                        enabled = True
                        continue
                    if not enabled:
                        continue
                    key = slug(
                        re.sub(r"\s*\(continuaci[oó]n\)", "", line, flags=re.IGNORECASE)
                    )
                    # Native PDF glyph spacing can split a department word
                    # ("Santa nder"). Accept only the exact letters of a known
                    # department, never a fuzzy name or an inherited guess.
                    printed_department = lookup.get(key) or (
                        compact_departments.get(key.replace("-", ""))
                        if full_width
                        else None
                    )
                    if printed_department:
                        department = printed_department
                        town_prefix = ""
                        continue
                    if line.startswith(("TENDENCIAS", "Fuente:")):
                        break
                    match = re.fullmatch(
                        r"(.+?)\s+(\d[\d.,]*)\s+(\d[\d.,]*)\s+(\d[\d.,]*)(?:\s+(.*))?",
                        line,
                    )
                    if not match:
                        if town_prefix and re.fullmatch(
                            r"\d[\d.,]*\s+\d[\d.,]*\s+\d[\d.,]*(?:\s+.*)?", line
                        ):
                            pending_price = line
                            continue
                        if re.fullmatch(
                            r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'-]{1,79}", line
                        ) and not line.startswith(("Pesos", "Precios", "Tendencia")):
                            town_prefix = (town_prefix + " " + line).strip()
                        continue
                    if not department:
                        raise ValueError(
                            f"Milk PDF page {number} has prices without a department"
                        )
                    town, low, high, mean, trend = match.groups()
                    town = (town_prefix + " " + town).strip()
                    town_prefix = ""
                    low, high, mean = (
                        float(x.replace(".", "").replace(",", "."))
                        for x in (low, high, mean)
                    )
                    if not 0 < low <= mean <= high:
                        raise ValueError("Milk PDF min/mean/max out of order")
                    found += 1
                    yield record(
                        "dane-milk-farm",
                        day,
                        "Leche cruda en finca",
                        town,
                        "litre",
                        mean,
                        f"PDF page {number},col {column},line {line_no}",
                        details={
                            "department": department,
                            "municipality": town,
                            "price_basis": "farmgate",
                            "min_price": low,
                            "max_price": high,
                            "trend": trend or "",
                            "page": number,
                        },
                    )
            page.close()
    if not found:
        narrative_month = _milk_narrative_month(texts, native_pages)
        if narrative_month:
            if narrative_month > today() or (day and day != narrative_month):
                raise SourceDateMismatch(
                    "Milk PDF report month differs from archive link or is future"
                )
            raise MilkNarrativeOnly(
                "Native milk bulletin contains narrative and labelled figures, no municipal price table"
            )
        raise ValueError("No milk PDF price rows parsed")

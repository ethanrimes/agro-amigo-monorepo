"""Farm-gate raw milk and mill rice series, distinct from wholesale prices."""

import calendar
import re
from datetime import date, datetime

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
        if key in values and values[key][6] != converted:
            conflicts.add(key)
        values[key] = (
            pid,
            mid,
            series,
            day,
            "monthly",
            "kg" if rice else "litre",
            converted,
            meta.get("min_price"),
            meta.get("max_price"),
            url,
            did,
            loc
            + (
                "; COP/tonelada dividido entre 1000 = COP/kg"
                if rice
                else "; precio en finca, COP/litro"
            ),
        )
    with db.cursor() as cur:
        cur.executemany(
            "INSERT INTO product(id,name,category) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
            products.values(),
        )
        cur.executemany(
            "INSERT INTO market(id,name,city,region) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            markets.values(),
        )
        cur.executemany(
            """INSERT INTO price_observation(product_id,market_id,source_id,observed_on,period,unit,price,min_price,max_price,source_url,document_id,source_locator)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(product_id,market_id,source_id,observed_on,period,unit)
            DO UPDATE SET price=excluded.price,min_price=excluded.min_price,max_price=excluded.max_price,source_url=excluded.source_url,document_id=excluded.document_id,source_locator=excluded.source_locator
            WHERE (price_observation.price,price_observation.document_id) IS DISTINCT FROM (excluded.price,excluded.document_id)
            AND ((SELECT media_type FROM source_document WHERE id=excluded.document_id)<>'application/pdf'
             OR (SELECT media_type FROM source_document WHERE id=price_observation.document_id)='application/pdf'
             OR EXISTS(SELECT 1 FROM ingestion_asset WHERE document_id=price_observation.document_id AND status='review'))""",
            [r for k, r in values.items() if k not in conflicts],
        )
    return len(conflicts)


def parse_milk_pdf(data, day):
    """Read the two newspaper-style columns in historical milk bulletins."""
    import io

    import pdfplumber

    from .worker import MONTH_NUM, SourceDateMismatch, clean, record, slug, today

    if day is not None and day > today():
        raise SourceDateMismatch("Milk PDF table month is in the future")
    lookup = {slug(d): d for d in DEPARTMENTS}
    found = 0
    department = ""
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if not (
                "Departamentos" in text
                and "municipios" in text
                and ("Medio" in text or "Promedio" in text)
            ):
                page.close()
                continue
            # A bulletin's publication date can be months after its observations.
            # Use only a date immediately following the price-table caption, never
            # the masthead, narrative, unrelated chart or a two-digit filename year.
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
            if day is None:
                raise ValueError("Milk bulletin has no verifiable publication month")
            for column, (left, right) in enumerate(
                [(0, page.width / 2), (page.width / 2, page.width)], 1
            ):
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
                    if key in lookup:
                        department = lookup[key]
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
        raise ValueError("No milk PDF price rows parsed")

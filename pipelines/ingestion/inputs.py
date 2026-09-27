"""All SIPSA input groups, retaining geographic level and commercial identity."""

import calendar
import re
from datetime import date

CATEGORIES = {
    "1.1": "Bioinsumos",
    "1.2": "Coadyuvantes, molusquicidas, reguladores fisiológicos y otros",
    "1.3": "Fertilizantes y enmiendas",
    "1.4": "Fungicidas",
    "1.5": "Herbicidas",
    "1.6": "Insecticidas, acaricidas y nematicidas",
    "2.1": "Alimentos balanceados, suplementos, coadyuvantes, adsorbentes, enzimas y aditivos",
    "2.2": "Antibióticos, antimicóticos y antiparasitarios",
    "2.3": "Antisépticos, desinfectantes e higiene",
    "2.4": "Hormonales",
    "2.5": "Insecticidas, plaguicidas y repelentes",
    "2.6": "Medicamentos",
    "2.7": "Vitaminas, sales y minerales",
    "3.1": "Arrendamiento de tierras",
    "3.2": "Elementos agropecuarios",
    "3.3": "Empaques agropecuarios",
    "3.4": "Especies productivas",
    "3.5": "Jornales",
    "3.6": "Material de propagación",
    "3.7": "Servicios agrícolas",
}


def parse_inputs(data):
    from .worker import (
        MONTH_NUM,
        SourceDateMismatch,
        clean,
        positive,
        record,
        slug,
        today,
        workbooks,
    )

    found = 0
    monthly_annex_period = None
    for sheet, rows in workbooks(data):
        header = None
        fixed_period = None
        category = CATEGORIES.get(sheet)
        legacy = None
        legacy_product = None
        for rownum, row in enumerate(rows, 1):
            normalized = [clean(v) for v in row]
            if "Productos y mercados" in normalized:
                prices = [
                    (i, re.fullmatch(r"Precio medio (\w+)", value, re.IGNORECASE))
                    for i, value in enumerate(normalized)
                ]
                prices = [(i, match) for i, match in prices if match]
                if prices:
                    # These original XLS sheets print e.g. FERTILIZANTES FEB15.
                    # The independently printed column month must agree; never
                    # use the preceding comparison column as the current price.
                    stamp = re.search(
                        r"\b([A-ZÁÉÍÓÚ]+)\s?(\d{2}|20\d{2})$", sheet, re.IGNORECASE
                    )
                    if len(prices) != 1 or not stamp:
                        raise ValueError(f"Unverified legacy input period: {sheet}")
                    month = MONTH_NUM.get(stamp[1].lower())
                    year = int(stamp[2]) + (2000 if len(stamp[2]) == 2 else 0)
                    if (
                        not month
                        or month != MONTH_NUM.get(prices[0][1][1].lower())
                        or not 2012 <= year <= today().year
                    ):
                        raise SourceDateMismatch(
                            f"Conflicting legacy input sheet/header period: {sheet}"
                        )
                    day = date(year, month, calendar.monthrange(year, month)[1])
                    category_key = {
                        "fertilizantes": "1.3",
                        "fungicidas": "1.4",
                        "insecticidas-agricolas": "1.6",
                        "herbicidas": "1.5",
                        "coadyudantes-agricolas": "1.2",
                        "coadyuvantes-agricolas": "1.2",
                        "alimentos": "2.1",
                        "medicamentos": "2.6",
                        "antibioticos": "2.2",
                        "vitaminas": "2.7",
                        "hormonales": "2.4",
                        "antisepticos": "2.3",
                        "insecticidas-pecuarios": "2.5",
                        "servicios-agricolas": "3.7",
                        "arriendos": "3.1",
                        "material-propagacion": "3.6",
                    }.get(slug(sheet[: stamp.start()]))
                    if category_key is None:
                        raise ValueError(f"Unmapped legacy input category: {sheet}")
                    category = CATEGORIES[category_key]
                    legacy = (
                        prices[0][0],
                        day,
                        normalized.index("Productos y mercados"),
                        normalized[prices[0][0]],
                    )
                    legacy_product = None
                    continue
            if legacy:
                from .special_prices import DEPARTMENTS

                col, day, place_col, printed_price_header = legacy
                price = row[col] if col < len(row) else None
                place = normalized[place_col]
                if not positive(price):
                    if place and not any(positive(v) for v in row[1:]):
                        legacy_product = place
                    continue
                match = re.fullmatch(r"(.+?)\s*\(([^()]+)\)", place)
                departments = {slug(d): d for d in DEPARTMENTS}
                if match:
                    municipality, department = (
                        clean(match[1]),
                        departments.get(slug(match[2])),
                    )
                elif slug(place) in {"bogota", "bogota-d-c"}:
                    municipality, department = "Bogotá, D.C.", "Bogotá D.C."
                else:
                    municipality, department = "", None
                if not legacy_product or not department or not municipality:
                    raise ValueError(
                        f"Unmapped legacy input identity/location: {sheet}, row {rownum}"
                    )
                if category == CATEGORIES["3.1"]:
                    name, presentation = legacy_product, legacy_product
                elif "," in legacy_product:
                    name, presentation = map(clean, legacy_product.rsplit(",", 1))
                else:
                    raise ValueError(
                        f"Missing legacy input presentation: {sheet}, row {rownum}"
                    )
                if day > today():
                    continue
                found += 1
                yield record(
                    "dane-inputs-municipal",
                    day,
                    name,
                    municipality,
                    presentation,
                    price,
                    f"{sheet}!row {rownum},col {col + 1}; legacy-inputs-v1",
                    details={
                        "sheet": sheet,
                        "category": category,
                        "presentation": presentation,
                        "department": department,
                        "municipality": municipality,
                        "printed_heading": legacy_product,
                        "printed_price_header": printed_price_header,
                        "parser_version": "legacy-inputs-v1",
                        "brand": "",
                        "ica": "",
                    },
                )
                continue
            if header is None:
                for v in normalized:
                    annex_heading = re.fullmatch(
                        r"Insumos y factores asociados a la producción agropecuaria"
                        r"(?:: precio promedio)? por departamento - (\w+) (20\d{2})",
                        v,
                        re.IGNORECASE,
                    )
                    period = annex_heading or re.search(r"\((\w+) (20\d{2})\)", v)
                    if period and period[1].lower() in MONTH_NUM:
                        year = int(period[2])
                        month = MONTH_NUM[period[1].lower()]
                        candidate = date(
                            year, month, calendar.monthrange(year, month)[1]
                        )
                        if annex_heading:
                            if (
                                monthly_annex_period
                                and monthly_annex_period != candidate
                            ):
                                raise SourceDateMismatch(
                                    f"Conflicting native department annex periods: {sheet}, row {rownum}; "
                                    f"{candidate} disagrees with {monthly_annex_period}"
                                )
                            monthly_annex_period = candidate
                        if fixed_period and fixed_period != candidate:
                            raise SourceDateMismatch(
                                f"Conflicting native input periods: {sheet}, row {rownum}"
                            )
                        fixed_period = candidate
                title = next(
                    (
                        re.match(r"^\d+\.\d+\.\s+(.+)", v)
                        for v in normalized
                        if re.match(r"^\d+\.\d+\.\s+(.+)", v)
                    ),
                    None,
                )
                if title:
                    category = title[1]
                    if category.startswith("Fertilizantes,"):
                        category = "Fertilizantes y enmiendas"
                    if category == "Especies Productivas":
                        category = "Especies productivas"
            if any("Precio promedio" in v for v in normalized) and (
                "Año" in normalized or "Nombre departamento" in normalized
            ):
                header = {v: i for i, v in enumerate(normalized) if v}
                continue
            if header is None:
                continue

            def get(*names):
                return next(
                    (
                        row[header[name]]
                        for name in names
                        if name in header and header[name] < len(row)
                    ),
                    None,
                )

            municipal = "Nombre municipio" in header
            periods = []
            for h in header:
                match = re.fullmatch(r"Precio promedio de (\w+) de (20\d{2})", h)
                if match and match[1].lower() in MONTH_NUM:
                    y = int(match[2])
                    m = MONTH_NUM[match[1].lower()]
                    periods.append(
                        (
                            date(y, m, calendar.monthrange(y, m)[1]),
                            get(h),
                            "; column " + str(header[h] + 1),
                        )
                    )
            if not periods:
                year, month = get("Año"), MONTH_NUM.get(clean(get("Mes")).lower())
                if isinstance(year, str) and re.fullmatch(r"20\d{2}", year.strip()):
                    year = int(year)
                if positive(year) and month:
                    day = date(
                        int(year), month, calendar.monthrange(int(year), month)[1]
                    )
                elif fixed_period:
                    day = fixed_period
                else:
                    continue
                periods = [
                    (
                        day,
                        get("Precio promedio municipio", "Precio promedio")
                        if municipal
                        else get("Precio promedio departamento"),
                        "",
                    )
                ]
            if not any(positive(price) and day <= today() for day, price, _ in periods):
                continue
            name = clean(
                get("Nombre del producto", "Artículo")
                if category == "Elementos agropecuarios"
                else get(
                    "Artículo",
                    "Nombre del producto",
                    "Nombre del insumo",
                    "Nombre de la especie productiva",
                    "Especie productiva",
                    "Tipo de jornal",
                    "Tipo de arriendo",
                    "Distrito de riego",
                    "Nombre del servicio agrícola",
                    "Nombre del servicio",
                )
            )
            presentation = (
                clean(
                    get(
                        "Presentación del producto",
                        "Presentación",
                        "Tipo de pago",
                        "Tipo de servicio",
                    )
                )
                or name
            )
            department = clean(get("Nombre departamento"))
            municipality = clean(get("Nombre municipio")) if municipal else ""
            if (
                not name
                or not department
                or (municipal and not municipality)
                or not category
            ):
                raise ValueError(
                    f"Unmapped input header/category/location: {sheet}, row {rownum}"
                )
            for day, price, column in periods:
                if not positive(price) or day > today():
                    continue
                found += 1
                locator = f"{sheet}!row {rownum}" + (
                    "; full product identity"
                    if not municipal and sheet == "3.2"
                    else ""
                )
                yield record(
                    "dane-inputs-municipal" if municipal else "dane-inputs",
                    day,
                    name,
                    municipality or department,
                    presentation,
                    price,
                    locator + column,
                    details={
                        "sheet": sheet,
                        "category": category,
                        "presentation": presentation,
                        "article": clean(get("Artículo")),
                        "brand": clean(get("Casa Comercial")),
                        "ica": clean(get("Registro ICA")),
                        "line": clean(get("Línea")),
                        "department": department,
                        "municipality": municipality,
                        "municipality_code": clean(get("Código municipio")),
                    },
                )
    if not found:
        raise ValueError("No input price rows parsed")


def identity(name, meta):
    from .worker import slug

    # Existing links for the first two groups remain valid. Full product names
    # distinguish e.g. material gauge and width that share the same Article.
    base = slug(
        name
        + "-"
        + meta["presentation"]
        + "-"
        + meta.get("brand", "")
        + "-"
        + meta.get("ica", "")
    )
    return base


def project_inputs(db, did, observed_on=None):
    """Stream into COPY staging: avoid holding millions of municipal rows in RAM."""

    columns = "id,department,observed_on,name,category,presentation,price,document_id,source_locator,brand,registration,product_line,municipality"
    with db.cursor() as cur:
        cur.execute(
            "CREATE TEMP TABLE input_stage (LIKE input_municipal_price INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        with db.cursor(name="input_source_rows") as source:
            source.itersize = 2000
            source.execute(
                "SELECT source_locator,series,observed_on,product_name,market_name,unit,price,details FROM historical_price WHERE document_id=%s AND (%s::date IS NULL OR observed_on=%s) AND series IN ('dane-inputs','dane-inputs-municipal','dane-inputs-pdf') AND (series<>'dane-inputs-pdf' OR details->>'parser_version'='inputs-pdf-v4' OR NOT EXISTS(SELECT 1 FROM historical_price newer WHERE newer.document_id=%s AND newer.details->>'parser_version'='inputs-pdf-v4')) AND NOT (series='dane-inputs' AND details->>'sheet'='3.2' AND NOT details ? 'category')",
                (did, observed_on, observed_on, did),
            )
            while batch := source.fetchmany(2000):
                with cur.copy(f"COPY input_stage({columns}) FROM STDIN") as cp:
                    for loc, series, day, name, market, unit, price, meta in batch:
                        cp.write_row(
                            (
                                identity(name, meta),
                                meta.get("department") or market,
                                day,
                                name,
                                meta.get("category") or CATEGORIES[meta["sheet"]],
                                unit,
                                price,
                                did,
                                loc,
                                meta.get("brand", ""),
                                meta.get("ica", ""),
                                meta.get("line", ""),
                                meta.get("municipality", "")
                                if series != "dane-inputs"
                                else "",
                            )
                        )
        cur.execute(
            "CREATE INDEX ON input_stage(id,department,municipality,observed_on)"
        )
        cur.execute("ANALYZE input_stage")
        conflicts = cur.execute(
            "SELECT count(*) FROM (SELECT 1 FROM input_stage GROUP BY id,department,municipality,observed_on HAVING min(price)<>max(price)) c"
        ).fetchone()[0]
        # Advance a narrow per-key watermark even if the value is unchanged.
        # Keeping original attribution for an equal value must not let an
        # intermediate older revision overwrite the latest validated value.
        # Ambiguous staged keys never publish or advance their watermark.
        cur.execute(
            """INSERT INTO input_revision(id,department,municipality,observed_on,retrieved_at)
            SELECT id,department,municipality,observed_on,
                (SELECT retrieved_at FROM source_document WHERE id=%s)
            FROM input_stage GROUP BY id,department,municipality,observed_on
            HAVING min(price)=max(price)
            ON CONFLICT(id,department,municipality,observed_on) DO UPDATE
            SET retrieved_at=excluded.retrieved_at
            WHERE input_revision.retrieved_at<excluded.retrieved_at""",
            (did,),
        )
        for table, municipal in [
            ("input_price", False),
            ("input_municipal_price", True),
        ]:
            cols = columns if municipal else columns.removesuffix(",municipality")
            keys = (
                "id,department,municipality,observed_on"
                if municipal
                else "id,department,observed_on"
            )
            # Existing rows may predate watermarks, so also check their original
            # timestamp. Equal business values retain their source attribution.
            # Retrieval order does not infer different sources' publication dates.
            cur.execute(
                f"""INSERT INTO {table}({cols})
                SELECT {cols} FROM (SELECT s.*,row_number() OVER(PARTITION BY id,department,municipality,observed_on ORDER BY source_locator) rn,
                min(price) OVER(PARTITION BY id,department,municipality,observed_on) low,max(price) OVER(PARTITION BY id,department,municipality,observed_on) high
                FROM input_stage s WHERE municipality {"<>" if municipal else "="} '') x WHERE rn=1 AND low=high
                ON CONFLICT({keys}) DO UPDATE SET name=excluded.name,category=excluded.category,price=excluded.price,document_id=excluded.document_id,
                source_locator=excluded.source_locator,brand=excluded.brand,registration=excluded.registration,product_line=excluded.product_line
                WHERE ({table}.price,{table}.name,{table}.category,{table}.brand,{table}.registration,{table}.product_line)
                IS DISTINCT FROM (excluded.price,excluded.name,excluded.category,excluded.brand,excluded.registration,excluded.product_line)
                AND (SELECT retrieved_at FROM source_document WHERE id=%s)
                    >= (SELECT retrieved_at FROM source_document WHERE id={table}.document_id)
                AND (SELECT retrieved_at FROM source_document WHERE id=%s)
                    >= (SELECT retrieved_at FROM input_revision r WHERE r.id=excluded.id
                        AND r.department=excluded.department AND r.observed_on=excluded.observed_on
                        AND r.municipality={"excluded.municipality" if municipal else "''"})""",
                (did, did),
            )
    return conflicts

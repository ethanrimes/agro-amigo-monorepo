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

# Literal sheet families observed in DANE's 2015–2018 native XLS annexes.
# Keep agricultural insecticides separate from the explicitly pecuary family.
LEGACY_CATEGORIES = {
    "fertilizantes": "1.3",
    "fungicidas": "1.4",
    "insecticidas": "1.6",
    "insecticidas-agricolas": "1.6",
    "herbicidas": "1.5",
    "coadyudantes-agricolas": "1.2",
    "coadyuvantes-agricolas": "1.2",
    "coadyudantes": "1.2",
    "alimentos": "2.1",
    "alimentos-pecuarios": "2.1",
    "medicamentos": "2.6",
    "antibioticos": "2.2",
    "vitaminas": "2.7",
    "hormonales": "2.4",
    "antisepticos": "2.3",
    "insecticidas-pecuarios": "2.5",
    "insecticida-pecuario": "2.5",
    "servicios-agricolas": "3.7",
    "distritos-de-riego": "3.7",
    "arriendos": "3.1",
    "material-propagacion": "3.6",
    "material-de-propagacion": "3.6",
    "empaques": "3.3",
    "elementos-pecuarios": "3.2",
    "especie-productiva": "3.4",
    "jornales": "3.5",
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
            legacy_heading = next(
                (
                    value
                    for value in normalized
                    if value
                    in (
                        "Productos y mercados",
                        "Tipo de jornal y mercados",
                        "Tipo de pago, mercado",
                    )
                ),
                None,
            )
            if not legacy_heading and any(
                re.fullmatch(r"Precio medio \w+", value, re.IGNORECASE)
                for value in normalized
            ):
                raise ValueError(f"Unmapped legacy input table header: {sheet}")
            if legacy_heading:
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
                    if not stamp:
                        raise ValueError(f"Unverified legacy input period: {sheet}")
                    month = MONTH_NUM.get(stamp[1].lower())
                    year = int(stamp[2]) + (2000 if len(stamp[2]) == 2 else 0)
                    current_prices = [
                        (i, match)
                        for i, match in prices
                        if MONTH_NUM.get(match[1].lower()) == month
                    ]
                    if (
                        not month
                        or not current_prices
                        or not 2012 <= year <= today().year
                    ):
                        raise SourceDateMismatch(
                            f"Conflicting legacy input sheet/header period: {sheet}"
                        )
                    if len(current_prices) != 1:
                        raise ValueError(
                            f"Ambiguous legacy input price columns: {sheet}"
                        )
                    day = date(year, month, calendar.monthrange(year, month)[1])
                    category_key = LEGACY_CATEGORIES.get(slug(sheet[: stamp.start()]))
                    if category_key is None:
                        raise ValueError(f"Unmapped legacy input category: {sheet}")
                    if legacy_heading == "Tipo de pago, mercado" and (
                        slug(sheet[: stamp.start()]) != "distritos-de-riego"
                        or "Distrito de riego" not in normalized
                    ):
                        raise ValueError(f"Unmapped legacy irrigation header: {sheet}")
                    category = CATEGORIES[category_key]
                    legacy = (
                        current_prices[0][0],
                        day,
                        normalized.index(legacy_heading),
                        normalized[current_prices[0][0]],
                        normalized.index("Distrito de riego")
                        if legacy_heading == "Tipo de pago, mercado"
                        else None,
                    )
                    legacy_product = None
                    continue
                raise ValueError(f"Unverified legacy input price header: {sheet}")
            if legacy:
                from .special_prices import DEPARTMENTS

                col, day, place_col, printed_price_header, district_col = legacy
                price = row[col] if col < len(row) else None
                place = normalized[place_col] if place_col < len(normalized) else ""
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
                if district_col is not None:
                    name = (
                        normalized[district_col]
                        if district_col < len(normalized)
                        else ""
                    )
                    presentation = legacy_product
                    if not name:
                        raise ValueError(
                            f"Missing legacy irrigation district: {sheet}, row {rownum}"
                        )
                elif category == CATEGORIES["3.1"]:
                    name, presentation = legacy_product, legacy_product
                elif "," in legacy_product:
                    name, presentation = map(clean, legacy_product.rsplit(",", 1))
                else:
                    raise ValueError(
                        f"Missing legacy input presentation: {sheet}, row {rownum}"
                    )
                if not name or not presentation:
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

            def get(*names, current_row=row, current_header=header):
                return next(
                    (
                        current_row[current_header[name]]
                        for name in names
                        if name in current_header
                        and current_header[name] < len(current_row)
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


def prepare_input_stage(db, did, observed_on=None, *, preserve=False):
    """Stage a complete immutable period before grouping its publication work."""

    from .pdf_sources import INPUT_PDF_VERSION

    columns = "id,department,observed_on,name,category,presentation,price,document_id,source_locator,brand,registration,product_line,municipality"
    with db.cursor() as cur:
        cur.execute(
            "CREATE TEMP TABLE input_stage (LIKE input_municipal_price INCLUDING DEFAULTS) "
            + ("ON COMMIT PRESERVE ROWS" if preserve else "ON COMMIT DROP")
        )
        with db.cursor(name="input_source_rows") as source:
            source.itersize = 2000
            source.execute(
                "SELECT source_locator,series,observed_on,product_name,market_name,unit,price,details FROM historical_price WHERE document_id=%s AND (%s::date IS NULL OR observed_on=%s) AND series IN ('dane-inputs','dane-inputs-municipal','dane-inputs-pdf') AND (series<>'dane-inputs-pdf' OR details->>'parser_version'=%s OR (NOT EXISTS(SELECT 1 FROM historical_price newer WHERE newer.document_id=%s AND newer.details->>'parser_version'=%s) AND (details->>'parser_version'='inputs-pdf-v4' OR NOT EXISTS(SELECT 1 FROM historical_price newer WHERE newer.document_id=%s AND newer.details->>'parser_version'='inputs-pdf-v4')))) AND NOT (series='dane-inputs' AND details->>'sheet'='3.2' AND NOT details ? 'category')",
                (
                    did,
                    observed_on,
                    observed_on,
                    INPUT_PDF_VERSION,
                    did,
                    INPUT_PDF_VERSION,
                    did,
                ),
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


def project_inputs(db, did, observed_on=None, *, staged=False, bounds=None):
    """Publish complete exact identities; a caller owns this transaction."""
    if not staged:
        prepare_input_stage(db, did, observed_on)
    columns = "id,department,observed_on,name,category,presentation,price,document_id,source_locator,brand,registration,product_line,municipality"
    stage = "input_stage"
    with db.cursor() as cur:
        if bounds is not None:
            stage = "input_publication_stage"
            cur.execute(
                "CREATE TEMP TABLE IF NOT EXISTS input_publication_stage (LIKE input_stage INCLUDING DEFAULTS) ON COMMIT DROP"
            )
            cur.execute("TRUNCATE pg_temp.input_publication_stage")
            cur.execute(
                """INSERT INTO input_publication_stage SELECT * FROM input_stage
                WHERE (id,department,municipality,observed_on)>=(%s,%s,%s,%s)
                  AND (id,department,municipality,observed_on)<=(%s,%s,%s,%s)""",
                (*bounds[0], *bounds[1]),
            )
            cur.execute("ANALYZE input_publication_stage")
        conflicts = cur.execute(
            f"SELECT count(*) FROM (SELECT 1 FROM {stage} GROUP BY id,department,municipality,observed_on HAVING min(price)<>max(price)) c"
        ).fetchone()[0]
        # Advance a narrow per-key watermark even if the value is unchanged.
        # Keeping original attribution for an equal value must not let an
        # intermediate older revision overwrite the latest validated value.
        # Ambiguous staged keys never publish or advance their watermark.
        cur.execute(
            f"""INSERT INTO input_revision(id,department,municipality,observed_on,retrieved_at)
            SELECT id,department,municipality,observed_on,
                (SELECT retrieved_at FROM source_document WHERE id=%s)
            FROM {stage} GROUP BY id,department,municipality,observed_on
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
                FROM {stage} s WHERE municipality {"<>" if municipal else "="} '') x WHERE rn=1 AND low=high
                AND NOT EXISTS(SELECT 1 FROM {table} current
                  WHERE current.id=x.id AND current.department=x.department AND current.observed_on=x.observed_on
                    {"AND current.municipality=x.municipality" if municipal else ""}
                    AND ((current.price,current.name,current.category,current.brand,current.registration,current.product_line)
                      IS NOT DISTINCT FROM (x.price,x.name,x.category,x.brand,x.registration,x.product_line)
                      OR (SELECT retrieved_at FROM source_document WHERE id=x.document_id)
                        < (SELECT retrieved_at FROM source_document WHERE id=current.document_id)
                      OR (SELECT retrieved_at FROM source_document WHERE id=x.document_id)
                        < (SELECT retrieved_at FROM input_revision r WHERE r.id=x.id
                          AND r.department=x.department AND r.municipality=x.municipality AND r.observed_on=x.observed_on)))
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

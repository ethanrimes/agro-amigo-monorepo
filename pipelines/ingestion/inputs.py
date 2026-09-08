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
    from .worker import MONTH_NUM, clean, positive, record, today, workbooks

    found = 0
    for sheet, rows in workbooks(data):
        header = None
        fixed_period = None
        category = CATEGORIES.get(sheet)
        for rownum, row in enumerate(rows, 1):
            normalized = [clean(v) for v in row]
            if header is None:
                for v in normalized:
                    period = re.search(r"\((\w+) (20\d{2})\)", v)
                    if period and period[1].lower() in MONTH_NUM:
                        year = int(period[2])
                        month = MONTH_NUM[period[1].lower()]
                        fixed_period = date(
                            year, month, calendar.monthrange(year, month)[1]
                        )
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


def project_inputs(db, did):
    """Stream into COPY staging: avoid holding millions of municipal rows in RAM."""

    columns = "id,department,observed_on,name,category,presentation,price,document_id,source_locator,brand,registration,product_line,municipality"
    with db.cursor() as cur:
        cur.execute(
            "CREATE TEMP TABLE input_stage (LIKE input_municipal_price INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        with db.cursor(name="input_source_rows") as source:
            source.itersize = 2000
            source.execute(
                "SELECT source_locator,series,observed_on,product_name,market_name,unit,price,details FROM historical_price WHERE document_id=%s AND series IN ('dane-inputs','dane-inputs-municipal','dane-inputs-pdf') AND (series<>'dane-inputs-pdf' OR details->>'parser_version'='inputs-pdf-v4' OR NOT EXISTS(SELECT 1 FROM historical_price newer WHERE newer.document_id=%s AND newer.details->>'parser_version'='inputs-pdf-v4')) AND NOT (series='dane-inputs' AND details->>'sheet'='3.2' AND NOT details ? 'category')",
                (did,did),
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
        conflicts = cur.execute(
            "SELECT count(*) FROM (SELECT 1 FROM input_stage GROUP BY id,department,municipality,observed_on HAVING min(price)<>max(price)) c"
        ).fetchone()[0]
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
            cur.execute(f"""INSERT INTO {table}({cols})
                SELECT {cols} FROM (SELECT s.*,row_number() OVER(PARTITION BY id,department,municipality,observed_on ORDER BY source_locator) rn,
                min(price) OVER(PARTITION BY id,department,municipality,observed_on) low,max(price) OVER(PARTITION BY id,department,municipality,observed_on) high
                FROM input_stage s WHERE municipality {"<>" if municipal else "="} '') x WHERE rn=1 AND low=high
                ON CONFLICT({keys}) DO UPDATE SET name=excluded.name,category=excluded.category,price=excluded.price,document_id=excluded.document_id,
                source_locator=excluded.source_locator,brand=excluded.brand,registration=excluded.registration,product_line=excluded.product_line
                WHERE ({table}.price,{table}.document_id,{table}.name,{table}.category,{table}.brand,{table}.registration,{table}.product_line,{table}.source_locator)
                IS DISTINCT FROM (excluded.price,excluded.document_id,excluded.name,excluded.category,excluded.brand,excluded.registration,excluded.product_line,excluded.source_locator)""")
    return conflicts

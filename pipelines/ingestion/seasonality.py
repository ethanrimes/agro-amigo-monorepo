"""Comparable COP/kg seasonal years with evidence for every individual month."""

from collections import defaultdict

from psycopg.types.json import Jsonb

VERSION = "seasonality-kg-v2"


def derive(monthly, coffee):
    """Return complete comparable years and reasons for excluding other years.

    Monthly tuples: product, market, year, month, price, document, locator, unit.
    Coffee tuples: observed date, COP/125kg price, original document.
    """
    grouped = defaultdict(lambda: defaultdict(list))
    candidates = set()
    for pid, mid, year, month, price, did, locator, unit in monthly:
        key = (pid, mid, year)
        candidates.add(key)
        if unit == "kg":
            grouped[key][month].append((float(price), did, locator))
    valid, excluded = [], {}
    for key in sorted(candidates):
        months = grouped[key]
        if set(months) != set(range(1, 13)):
            excluded[key] = "Fewer than twelve verified monthly COP/kg prices"
            continue
        if any(len({r[0] for r in values}) != 1 for values in months.values()):
            excluded[key] = "Conflicting COP/kg observations within a month"
            continue
        if any(not r[1] or not r[2] for values in months.values() for r in values):
            excluded[key] = "Missing original document or exact source locator"
            continue
        documents = [sorted({r[1] for r in months[m]}) for m in range(1, 13)]
        valid.append(
            (
                *key,
                [months[m][0][0] for m in range(1, 13)],
                documents[11][0],
                [
                    "; ".join(sorted({r[1] + " · " + r[2] for r in months[m]}))
                    for m in range(1, 13)
                ],
                documents,
            )
        )
    coffee_years = defaultdict(lambda: defaultdict(list))
    for day, price, did in coffee:
        coffee_years[day.year][day.month].append((float(price) / 125, did, day))
    for year, months in sorted(coffee_years.items()):
        key = ("cafe-pergamino-seco", "fnc-national", year)
        if set(months) != set(range(1, 13)):
            excluded[key] = "Fewer than twelve months with published FNC observations"
            continue
        if any(not r[1] for values in months.values() for r in values):
            excluded[key] = "Missing original FNC document"
            continue
        documents = [sorted({r[1] for r in months[m]}) for m in range(1, 13)]
        valid.append(
            (
                *key,
                [sum(r[0] for r in months[m]) / len(months[m]) for m in range(1, 13)],
                documents[11][0],
                [
                    f"FNC {year}-{m:02d}: mean of {len(months[m])} published daily references; COP/125kg divided by 125; "
                    + "; ".join(f"{r[2].isoformat()} · {r[1]}" for r in months[m])
                    for m in range(1, 13)
                ],
                documents,
            )
        )
    return valid, excluded


def refresh(db, current_year):
    monthly = db.execute(
        """SELECT product_id,market_id,extract(year from observed_on)::int,
        extract(month from observed_on)::int,price,document_id,source_locator,unit
        FROM published_price_observation WHERE source_id='dane-sipsa'
        AND period='monthly' AND observed_on<make_date(%s,1,1)
        ORDER BY product_id,market_id,observed_on,unit""",
        (current_year,),
    ).fetchall()
    coffee = db.execute(
        "SELECT observed_on,price,document_id FROM coffee_reference WHERE observed_on<make_date(%s,1,1) ORDER BY observed_on",
        (current_year,),
    ).fetchall()
    valid, excluded = derive(monthly, coffee)
    columns = "product_id,market_id,reference_year,monthly_prices,document_id,source_rows,source_documents,validation_version"
    with db.transaction():
        db.execute(
            "CREATE TEMP TABLE seasonal_stage (LIKE seasonal_year INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        with db.cursor().copy(f"COPY seasonal_stage({columns}) FROM STDIN") as copy:
            for pid, mid, year, prices, anchor, locators, documents in valid:
                copy.write_row(
                    (
                        pid,
                        mid,
                        year,
                        Jsonb(prices),
                        anchor,
                        Jsonb(locators),
                        Jsonb(documents),
                        VERSION,
                    )
                )
        db.execute(f"""INSERT INTO seasonal_year({columns}) SELECT {columns} FROM seasonal_stage
        ON CONFLICT(product_id,market_id,reference_year) DO UPDATE SET
          monthly_prices=excluded.monthly_prices,document_id=excluded.document_id,
          source_rows=excluded.source_rows,source_documents=excluded.source_documents,
          validation_version=excluded.validation_version,review_reason=NULL
        WHERE (seasonal_year.monthly_prices,seasonal_year.document_id,seasonal_year.source_rows,
               seasonal_year.source_documents,seasonal_year.validation_version,seasonal_year.review_reason)
          IS DISTINCT FROM (excluded.monthly_prices,excluded.document_id,excluded.source_rows,
                            excluded.source_documents,excluded.validation_version,NULL::text)""")
        db.execute(
            "CREATE TEMP TABLE seasonal_review_stage(product_id text,market_id text,reference_year integer,reason text) ON COMMIT DROP"
        )
        with db.cursor().copy("COPY seasonal_review_stage FROM STDIN") as copy:
            for key, reason in excluded.items():
                copy.write_row((*key, reason))
        db.execute(
            """UPDATE seasonal_year y SET validation_version=%s,review_reason=r.reason
        FROM seasonal_review_stage r WHERE (y.product_id,y.market_id,y.reference_year)=
          (r.product_id,r.market_id,r.reference_year)
          AND (y.validation_version,y.review_reason) IS DISTINCT FROM (%s,r.reason)""",
            (VERSION, VERSION),
        )
    return {"complete_years": len(valid), "reviewed_years": len(excluded)}

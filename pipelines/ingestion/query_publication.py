"""Archive and publish official daily-query alternatives with distinct semantics."""

import time

from . import dane_daily_query


def official_rows(rows):
    from .worker import slug

    for locator, series, day, name, market, unit, mean, _, details in rows:
        yield {
            "product_id": slug(name),
            "product_name": name,
            "category": "Productos agrícolas",
            "publisher": "DANE · SIPSA",
            "series": series,
            "basis": "Precio mayorista diario · promedio publicado",
            "currency": "COP",
            "unit": unit,
            "market": market,
            "date": day.isoformat(),
            "period_start": day.isoformat(),
            "price": mean,
            "min": details["price_min"],
            "max": details["price_max"],
            "source_locator": locator,
            "identity_dimensions": {
                "source_product": name,
                "statistic": "published_mean",
            },
            "details": {
                **{
                    key: value for key, value in details.items() if key != "source_page"
                },
                "source_page_url": details.get("source_page"),
                "period_type": "daily",
                "source_note": "Promedio diario publicado por DANE en su consulta histórica; el mínimo y máximo corresponden al mismo día y mercado.",
            },
        }


def recover(
    db,
    url,
    status,
    day,
    *,
    original_data=None,
    original_id=None,
    preserve_original_status=False,
):
    """Keep contradictory workbooks reviewed; alternatives have their own identity."""
    from . import official_sources, worker
    from .daily_publication import retain_resolution
    from .resumable_inputs import WorkDeferred

    received = []

    def check_budget():
        remaining = (worker.RUN_DEADLINE.get() or float("inf")) - time.monotonic()
        if remaining < 15:
            raise WorkDeferred(
                "Official daily query will resume with sufficient request time"
            )
        return remaining

    def fetch(target, parameters):
        remaining = check_budget()
        request = worker.SESSION.get if parameters is None else worker.SESSION.post
        kwargs = {} if parameters is None else {"data": parameters}
        response = request(target, timeout=(10, min(60, remaining - 12)), **kwargs)
        response.raise_for_status()
        body = response.content
        role = {
            "qryFuente": "sources",
            "qryGrupo": "groups",
            "qryArticulo": "products",
            "qryTabla": "daily-prices",
        }.get(parameters.get("dataAccessId") if parameters else None, "unit-evidence")
        did = worker.archive(
            db,
            dane_daily_query.EXPLORER_URL,
            body,
            "dane-daily-query",
            day,
            filename=f"sipsa-{day}-{role}." + ("json" if parameters else "html"),
            parents=([original_id] if original_id else [])
            + [r["document_id"] for r in received]
            or None,
        )
        evidence = {
            "document_id": did,
            "role": role,
            "request_url": target,
            "request_method": "POST" if parameters else "GET",
            "request_parameters": parameters,
            "requested_day": day.isoformat(),
            "original_url": url,
            "original_document_id": original_id,
        }
        retain_resolution(db, "official_query_response", evidence)
        received.append(evidence)
        return body

    result = dane_daily_query.recover_daily(
        url,
        status,
        day,
        fetch,
        check_budget=check_budget,
        original_data=original_data,
    )
    if result is None:
        return None
    # Responses are archived before validation, including malformed responses
    # and successful earlier requests when a later request fails.
    documents = received
    did = documents[-1]["document_id"]
    with db.transaction():
        worker.save_rows(db, did, result.rows)
        count = official_sources.publish_rows(
            db, official_rows(result.rows), did, "dane-daily-query"
        )
        retain_resolution(
            db,
            "official_daily_query_resolution",
            {
                "document_id": did,
                "original_document_id": original_id,
                "documents": documents,
                **result.evidence,
            },
        )
        if original_id and preserve_original_status:
            # Supplemental means do not change the city archive's identity,
            # package-price count, review state or explicit coverage diagnostic.
            pass
        elif original_id:
            # Retaining this review also prevents invalid older projections of
            # the contradictory workbook from becoming visible again.
            db.execute(
                """UPDATE ingestion_asset SET status='review',checked_at=now(),
                error=%s WHERE url=%s AND document_id=%s""",
                (
                    f"Publisher date conflict retained; {count} independently dated DANE daily means for {day} published from archived query {did}",
                    url,
                    original_id,
                ),
            )
        else:
            db.execute(
                """UPDATE ingestion_asset SET document_id=%s,status='complete',records=%s,
                checked_at=now(),attempts=attempts+1,error=%s WHERE url=%s""",
                (
                    did,
                    count,
                    "Excel link unavailable; recovered official daily query with explicit published mean, min, max and source units",
                    url,
                ),
            )
    return count

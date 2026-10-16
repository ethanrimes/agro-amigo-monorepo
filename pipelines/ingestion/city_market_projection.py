"""Bounded location-only repair for source-backed city markets.

The worker runs this small projection during unattended daily/backfill/all
cycles. It updates only market.city, market.region, and market.municipality_id
for an exact generated city-market identity with a published quote witness.
"""

from __future__ import annotations

import time


MAX_BATCH = 100
CURSOR_MAX_LENGTH = 200


def load_completed_projection_cursor(db, current_run_id):
    """Read the last completed projection checkpoint, even from a partial run.

    The projection phase is deliberately persisted independently of overall
    run status: unrelated source failures must not pin the keyset at its first
    page forever. The current run is excluded so its in-progress summary can
    never feed itself.
    """
    row = db.execute(
        """
        SELECT summary #>> '{city_market_location_projection,cursor_after}'
        FROM ingestion_run
        WHERE id <> %s
          AND summary #>> '{city_market_location_projection,phase_completed}' = 'true'
          AND summary #>> '{city_market_location_projection,cursor_after}' IS NOT NULL
        ORDER BY started_at DESC, id DESC
        LIMIT 1
        """,
        (current_run_id,),
    ).fetchone()
    if not row:
        return "", False
    cursor = row[0]
    if not isinstance(cursor, str) or len(cursor) > CURSOR_MAX_LENGTH:
        return "", True
    return cursor, False


def _slug(value):
    # Keep the same normalization contract as city_reports.save_classifications
    # without copying its implementation or introducing a fuzzy alias rule.
    from pipelines.ingestion.worker import slug

    return slug(value)


def _municipality_for_market_name(name, municipalities):
    if not isinstance(name, str) or not name.strip():
        return None
    city = name.split(",", 1)[0].strip()
    key = "bogota-d-c" if _slug(city) == "bogota" else _slug(city)
    matches = [row for row in municipalities if _slug(row[1]) == key]
    if len(matches) != 1:
        return None
    municipality_id, _name, department = matches[0]
    if municipality_id == "11001":
        department = "Bogotá, D.C."
    return city, department, municipality_id


def repair_published_city_market_locations(
    db,
    *,
    after_id="",
    limit=MAX_BATCH,
    deadline=None,
):
    """Repair one keyset page of strictly identified published city markets.

    `after_id` is a durable caller-owned cursor. Persist the returned cursor in
    the existing ingestion_run summary and resume from it on the next run;
    wrap to the beginning only after the end is reached. Failed/manual rows
    therefore cannot permanently occupy the first batch.
    """
    if not isinstance(after_id, str):
        raise ValueError("after_id must be a string market ID")
    if len(after_id) > CURSOR_MAX_LENGTH:
        raise ValueError("after_id exceeds the bounded cursor length")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")
    limit = min(limit, MAX_BATCH)
    if deadline is None:
        deadline = time.monotonic() + 5.0

    scanned = 0
    updated = 0
    skipped = 0
    cursor = after_id
    if deadline - time.monotonic() <= 0.05:
        return {
            "scanned": 0, "updated": 0, "skipped": 0,
            "cursor_after": after_id, "batch_limit": limit,
            "deadline_reached": True, "wrap_required": False,
        }
    with db.transaction():
        statement_ms = max(50, int((deadline - time.monotonic()) * 1000))
        db.execute("SELECT set_config('statement_timeout', %s, true)", (f"{statement_ms}ms",))
        db.execute("SELECT set_config('lock_timeout', '1000ms', true)")
        rows = db.execute(
            """
            WITH bounded_market_page AS (
              SELECT m.id,m.name,m.city,m.region,m.municipality_id
              FROM market m
              WHERE m.id > %s
                AND (m.id LIKE 'dane-city-%%' OR m.id LIKE 'sipsa-%%')
                AND m.municipality_id IS NULL
              ORDER BY m.id
              LIMIT %s
            )
            SELECT m.id,m.name,m.city,m.region,m.municipality_id,
              EXISTS (SELECT 1 FROM published_regional_price p WHERE p.market_name=m.name) AS has_published_witness,
              (SELECT count(*) FROM market same_name WHERE same_name.name=m.name)=1 AS unique_literal_name
            FROM bounded_market_page m
            ORDER BY m.id
            """,
            (after_id, limit),
        ).fetchall()
        municipalities = db.execute(
            "SELECT id,name,department FROM municipality ORDER BY id"
        ).fetchall()

        for market_id, literal_name, old_city, old_region, old_municipality, has_witness, unique_literal_name in rows:
            if time.monotonic() >= deadline:
                break
            scanned += 1
            cursor = market_id
            if not has_witness or not unique_literal_name:
                skipped += 1
                continue
            expected_ids = {
                "dane-city-" + _slug(literal_name),
                "sipsa-" + _slug(literal_name),
            }
            if market_id not in expected_ids or old_municipality is not None:
                skipped += 1
                continue
            match = _municipality_for_market_name(literal_name, municipalities)
            if match is None:
                skipped += 1
                continue
            city, department, municipality_id = match
            allowed_city = {"", "colombia", _slug(city)}
            allowed_region = {"", "colombia"}
            if (
                _slug(old_city or "") not in allowed_city
                or _slug(old_region or "") not in allowed_region
            ):
                skipped += 1
                continue

            # Compare all old values in the UPDATE so concurrent edits/manual
            # mappings win. No price, source, or classification table is touched.
            result = db.execute(
                """
                UPDATE market AS target
                SET city=%s,region=%s,municipality_id=%s
                WHERE target.id=%s AND target.name=%s AND target.municipality_id IS NULL
                  AND target.city IS NOT DISTINCT FROM %s
                  AND target.region IS NOT DISTINCT FROM %s
                  AND (SELECT count(*) FROM market same_name WHERE same_name.name=target.name)=1
                  AND EXISTS (
                    SELECT 1 FROM published_regional_price p
                    WHERE p.market_name=target.name
                  )
                RETURNING id
                """,
                (city, department, municipality_id, market_id, literal_name,
                 old_city, old_region),
            ).fetchone()
            if result:
                updated += 1
            else:
                skipped += 1

    return {
        "scanned": scanned,
        "updated": updated,
        "skipped": skipped,
        "cursor_after": cursor,
        "batch_limit": limit,
        "deadline_reached": time.monotonic() >= deadline,
        "wrap_required": len(rows) < limit and not (time.monotonic() >= deadline),
    }

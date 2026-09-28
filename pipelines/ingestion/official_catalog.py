"""Persistent latest official quotes; ingestion computes, frontend reads.

Only derived cache rows are mutable. Original quotes, reviews and checkpoints
remain append-only. Every persisted batch was validated source-wide before
publication; a derived refresh never claims the original import completed.
"""

from .resumable_inputs import WorkDeferred

VERSION = "official-catalog-v1"
LATEST_FOR_KEYS_SQL = """WITH identities(quote_key) AS (SELECT unnest(%s::text[]))
  SELECT p.*,previous.price AS previous_price FROM identities i CROSS JOIN LATERAL (
    SELECT q.observed_on FROM official_price_quote q
    WHERE q.quote_key=i.quote_key
      AND q.observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
      AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id
        AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
      AND NOT EXISTS(SELECT 1 FROM official_source_review r WHERE r.document_id=q.document_id
        AND r.source_locator=q.source_locator AND r.created_at>=q.parsed_at)
    ORDER BY q.observed_on DESC LIMIT 1
  ) latest_day CROSS JOIN LATERAL (
    SELECT q.*,d.source_url FROM official_price_quote q
    JOIN source_document d ON d.id=q.document_id
    WHERE q.quote_key=i.quote_key AND q.observed_on=latest_day.observed_on
      AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id
        AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
      AND NOT EXISTS(SELECT 1 FROM official_source_review r WHERE r.document_id=q.document_id
        AND r.source_locator=q.source_locator AND r.created_at>=q.parsed_at)
    ORDER BY CASE WHEN q.series='dane-milk-macroregion'
      AND q.observed_on=(date_trunc('month',q.observed_on)+interval '1 month - 1 day')::date
      AND COALESCE(NULLIF(q.details->>'bulletin_period',''),d.reference_period) IN (
        to_char(q.observed_on,'YYYY-MM-DD'),
        to_char(date_trunc('month',q.observed_on)+interval '2 months - 1 day','YYYY-MM-DD'))
    THEN COALESCE(NULLIF(q.details->>'bulletin_period',''),d.reference_period)
    END DESC NULLS LAST,d.retrieved_at DESC,q.parsed_at DESC,q.source_locator LIMIT 1
  ) p LEFT JOIN LATERAL (
    SELECT prior.price FROM (
      SELECT q.observed_on FROM official_price_quote q
      WHERE q.quote_key=p.quote_key AND q.observed_on<p.observed_on
        AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id
          AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
        AND NOT EXISTS(SELECT 1 FROM official_source_review r WHERE r.document_id=q.document_id
          AND r.source_locator=q.source_locator AND r.created_at>=q.parsed_at)
      ORDER BY q.observed_on DESC LIMIT 1
    ) previous_day CROSS JOIN LATERAL (
      SELECT q.price FROM official_price_quote q JOIN source_document d ON d.id=q.document_id
      WHERE q.quote_key=p.quote_key AND q.observed_on=previous_day.observed_on
        AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id
          AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
        AND NOT EXISTS(SELECT 1 FROM official_source_review r WHERE r.document_id=q.document_id
          AND r.source_locator=q.source_locator AND r.created_at>=q.parsed_at)
      ORDER BY CASE WHEN q.series='dane-milk-macroregion'
      AND q.observed_on=(date_trunc('month',q.observed_on)+interval '1 month - 1 day')::date
      AND COALESCE(NULLIF(q.details->>'bulletin_period',''),d.reference_period) IN (
        to_char(q.observed_on,'YYYY-MM-DD'),
        to_char(date_trunc('month',q.observed_on)+interval '2 months - 1 day','YYYY-MM-DD'))
    THEN COALESCE(NULLIF(q.details->>'bulletin_period',''),d.reference_period)
    END DESC NULLS LAST,d.retrieved_at DESC,q.parsed_at DESC,q.source_locator LIMIT 1
    ) prior
  ) previous ON true"""


def refresh_document(db, document_id):
    """Refresh all original identities, including quotes withdrawn by reviews."""
    keys = [
        row[0]
        for row in db.execute(
            "SELECT DISTINCT quote_key FROM official_price_quote WHERE document_id=%s",
            (document_id,),
        ).fetchall()
    ]
    return refresh_keys(db, keys)


def refresh_keys(db, keys):
    """Replace affected cache rows atomically, including NULL tombstones.

    Lock cache keys before reading quotes in the following READ COMMITTED
    statement. Concurrent quote/review triggers must wait, then mark this result
    dirty; a blocked refresh instead reads the committed newer source snapshot.
    """
    keys = sorted(set(keys))
    if not keys:
        return 0
    with db.transaction():
        db.execute(
            "INSERT INTO official_catalog_current(quote_key) SELECT unnest(%s::text[]) ORDER BY 1 ON CONFLICT DO NOTHING",
            (keys,),
        )
        db.execute(
            "SELECT quote_key FROM official_catalog_current WHERE quote_key=ANY(%s::text[]) ORDER BY quote_key FOR UPDATE",
            (keys,),
        ).fetchall()
        db.execute(
            """WITH latest AS MATERIALIZED ("""
            + LATEST_FOR_KEYS_SQL
            + """),
            requested(quote_key) AS (SELECT unnest(%s::text[]))
            INSERT INTO official_catalog_current(quote_key,payload,dirty,version,refreshed_at)
            SELECT requested.quote_key,CASE WHEN latest.quote_key IS NULL THEN NULL ELSE to_jsonb(latest) END,
              false,%s,now()
            FROM requested LEFT JOIN latest USING(quote_key)
            ON CONFLICT(quote_key) DO UPDATE SET payload=excluded.payload,dirty=false,
              version=excluded.version,refreshed_at=excluded.refreshed_at""",
            (keys, keys, VERSION),
        )
    return len(keys)


def refresh_dirty(db, limit=100):
    """Bounded recovery for reviews/status changes or interrupted cache refresh."""
    if not 1 <= limit <= 2000:
        raise ValueError("Official catalog refresh limit must be 1..2000")
    keys = [
        row[0]
        for row in db.execute(
            "SELECT quote_key FROM official_catalog_current WHERE dirty OR version<>%s ORDER BY refreshed_at NULLS FIRST,quote_key LIMIT %s",
            (VERSION, limit),
        ).fetchall()
    ]
    return refresh_keys(db, keys)


def bootstrap(db, batch_size=100, *, after=None, deadline=None):
    """Initial/recovery seek, bounded per transaction and resumable by last key.

    Each committed batch is safe to repeat. No history/catalog rows are deleted.
    Existing cache tombstones remain if all raw quotes become reviewed.
    """
    import time

    if not 1 <= batch_size <= 2000:
        raise ValueError("Official catalog bootstrap batch size must be 1..2000")
    total = 0
    cursor = after or ""
    while True:
        if deadline is not None and time.monotonic() >= deadline:
            raise WorkDeferred(
                f"Official catalog bootstrap deferred after key {cursor}; {total} keys refreshed"
            )
        keys = [
            row[0]
            for row in db.execute(
                """WITH RECURSIVE identities(quote_key,n) AS (
              (SELECT quote_key,1 FROM official_price_quote WHERE quote_key>%s ORDER BY quote_key LIMIT 1)
              UNION ALL
              SELECT next.quote_key,i.n+1 FROM identities i CROSS JOIN LATERAL (
                SELECT quote_key FROM official_price_quote WHERE quote_key>i.quote_key ORDER BY quote_key LIMIT 1
              ) next WHERE i.n<%s
            ) SELECT quote_key FROM identities ORDER BY quote_key""",
                (cursor, batch_size),
            ).fetchall()
        ]
        if not keys:
            return {"keys": total, "last_key": cursor}
        total += refresh_keys(db, keys)
        cursor = keys[-1]

"""Persistent latest official quotes; ingestion computes, frontend reads.

Only derived cache rows are mutable. Original quotes, reviews and checkpoints
remain append-only. Every persisted batch was validated source-wide before
publication; a derived refresh never claims the original import completed.
"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from psycopg.pq import TransactionStatus

from . import write_pacing
from .catalog_stage import catalog_stage
from .resumable_inputs import WorkDeferred

VERSION = "official-catalog-v1"
DOCUMENT_BATCH_SIZE = 64
DOCUMENT_PACE_MIN_SECONDS = 0.25
DOCUMENT_PACE_MAX_SECONDS = 5.0


def _clock():
    return time.monotonic()


def _sleep(seconds):
    time.sleep(seconds)


def _bogota_day():
    return datetime.now(ZoneInfo("America/Bogota")).date()


def _refresh_phase():
    """A phase belongs to one immutable parse and one publication day."""
    return f"official:catalog-start:{VERSION}:{_bogota_day().isoformat()}"


def _phase_started(db, document_id, revision, phase=None):
    return bool(db.execute(
        "SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s "
        "AND processor_version=%s AND step=%s",
        (document_id, revision, phase or _refresh_phase()),
    ).fetchone())


LATEST_FOR_KEYS_SQL = """WITH identities(quote_key) AS (SELECT unnest(%s::text[]))
  SELECT p.*,previous.price AS previous_price FROM identities i CROSS JOIN LATERAL (
    SELECT q.observed_on FROM official_price_quote q
    WHERE q.quote_key=i.quote_key
      AND q.observed_on<=(statement_timestamp() AT TIME ZONE 'America/Bogota')::date
      AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id
        AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
      AND NOT EXISTS(SELECT 1 FROM official_source_review r WHERE r.document_id=q.document_id
        AND r.source_locator=q.source_locator AND r.created_at>=q.parsed_at)
      AND NOT EXISTS(SELECT 1 FROM official_price_quote newer WHERE newer.document_id=q.document_id
        AND newer.source_locator=q.source_locator AND newer.parsed_at>q.parsed_at)
    ORDER BY q.observed_on DESC LIMIT 1
  ) latest_day CROSS JOIN LATERAL (
    SELECT q.*,d.source_url FROM official_price_quote q
    JOIN source_document d ON d.id=q.document_id
    WHERE q.quote_key=i.quote_key AND q.observed_on=latest_day.observed_on
      AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id
        AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
      AND NOT EXISTS(SELECT 1 FROM official_source_review r WHERE r.document_id=q.document_id
        AND r.source_locator=q.source_locator AND r.created_at>=q.parsed_at)
      AND NOT EXISTS(SELECT 1 FROM official_price_quote newer WHERE newer.document_id=q.document_id
        AND newer.source_locator=q.source_locator AND newer.parsed_at>q.parsed_at)
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
        AND NOT EXISTS(SELECT 1 FROM official_price_quote newer WHERE newer.document_id=q.document_id
          AND newer.source_locator=q.source_locator AND newer.parsed_at>q.parsed_at)
      ORDER BY q.observed_on DESC LIMIT 1
    ) previous_day CROSS JOIN LATERAL (
      SELECT q.price FROM official_price_quote q JOIN source_document d ON d.id=q.document_id
      WHERE q.quote_key=p.quote_key AND q.observed_on=previous_day.observed_on
        AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id
          AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
        AND NOT EXISTS(SELECT 1 FROM official_source_review r WHERE r.document_id=q.document_id
          AND r.source_locator=q.source_locator AND r.created_at>=q.parsed_at)
        AND NOT EXISTS(SELECT 1 FROM official_price_quote newer WHERE newer.document_id=q.document_id
          AND newer.source_locator=q.source_locator AND newer.parsed_at>q.parsed_at)
      ORDER BY CASE WHEN q.series='dane-milk-macroregion'
      AND q.observed_on=(date_trunc('month',q.observed_on)+interval '1 month - 1 day')::date
      AND COALESCE(NULLIF(q.details->>'bulletin_period',''),d.reference_period) IN (
        to_char(q.observed_on,'YYYY-MM-DD'),
        to_char(date_trunc('month',q.observed_on)+interval '2 months - 1 day','YYYY-MM-DD'))
    THEN COALESCE(NULLIF(q.details->>'bulletin_period',''),d.reference_period)
    END DESC NULLS LAST,d.retrieved_at DESC,q.parsed_at DESC,q.source_locator LIMIT 1
    ) prior
  ) previous ON true"""

# The internal dates come from the same two eligible winner seeks as the public
# payload. Keep LATEST_FOR_KEYS_SQL's row shape unchanged for existing readers.
_LATEST_WITH_DATES_SQL = LATEST_FOR_KEYS_SQL.replace(
    "SELECT p.*,previous.price AS previous_price FROM identities",
    "SELECT p.*,previous.price AS previous_price,previous.observed_on AS previous_observed_on FROM identities",
).replace(
    "SELECT prior.price FROM (",
    "SELECT prior.price,previous_day.observed_on FROM (",
)
assert _LATEST_WITH_DATES_SQL != LATEST_FOR_KEYS_SQL


def document_keys(db, document_id):
    """Return every quote identity ever retained for this original."""
    return [
        row[0]
        for row in db.execute(
            "SELECT DISTINCT quote_key FROM official_price_quote WHERE document_id=%s",
            (document_id,),
        ).fetchall()
    ]


def mark_keys_dirty(db, keys):
    """Invalidate original identities before quote batches can become visible."""
    if not keys:
        return
    pending = sorted(set(keys))
    # A revised source locator may replace an old quote_key with a new one.
    # The insert trigger dirties the new key only, so invalidate every original
    # identity before refreshing any batch. If work is deferred, untouched old
    # keys stay visibly dirty for bounded recovery rather than serving stale
    # clean payloads.
    with db.transaction():
        db.execute(
            "INSERT INTO official_catalog_current(quote_key) "
            "SELECT unnest(%s::text[]) ORDER BY 1 "
            "ON CONFLICT(quote_key) DO UPDATE SET dirty=true "
            "WHERE NOT official_catalog_current.dirty",
            (pending,),
        )


def _mark_older_document_keys_dirty(db, document_id, keys):
    """Keep a clean card only when this entire original predates its prior day.

    The caller has validated the whole replacement source, including any
    source-bound reviews or locator retirements. New quotes, reviews, and asset
    status transitions retain independent per-key invalidation triggers.
    """
    pending = sorted(set(keys))
    if not pending:
        return
    with db.transaction():
        db.execute(
            "INSERT INTO official_catalog_current(quote_key) "
            "SELECT unnest(%s::text[]) ORDER BY 1 ON CONFLICT DO NOTHING",
            (pending,),
        )
        # Match refresh_keys and quote-trigger lock order. The day is sampled
        # after any wait, so a cache refreshed before midnight fails closed.
        db.execute(
            "SELECT quote_key FROM official_catalog_current "
            "WHERE quote_key=ANY(%s::text[]) ORDER BY quote_key FOR UPDATE",
            (pending,),
        ).fetchall()
        day = db.execute(
            "SELECT (clock_timestamp() AT TIME ZONE 'America/Bogota')::date"
        ).fetchone()[0]
        db.execute(
            "WITH source_max AS MATERIALIZED ("
            " SELECT quote_key,max(observed_on) AS newest,"
            " count(*)=count(observed_on) AS all_dated"
            " FROM official_price_quote WHERE document_id=%s GROUP BY quote_key"
            ") UPDATE official_catalog_current c SET dirty=true"
            " FROM source_max s WHERE c.quote_key=s.quote_key AND NOT c.dirty"
            " AND ("
            " c.version=%s AND c.payload IS NOT NULL AND c.refreshed_at IS NOT NULL"
            " AND (c.refreshed_at AT TIME ZONE 'America/Bogota')::date=%s"
            " AND c.winner_observed_on IS NOT NULL"
            " AND c.previous_observed_on IS NOT NULL"
            " AND c.previous_observed_on<c.winner_observed_on"
            " AND c.winner_observed_on<=%s"
            " AND c.payload->>'observed_on'=to_char(c.winner_observed_on,'YYYY-MM-DD')"
            " AND s.all_dated AND s.newest<c.previous_observed_on) IS NOT TRUE",
            (document_id, VERSION, day, day),
        )


def mark_document_dirty(db, document_id, revision=None, *, older_only=False):
    """Keep prior identities out of readers during a revised source replay."""
    # A marker is written only after *all* quote/review batches are retained.
    # A retry of that same immutable revision on the same Bogotá day must not
    # invalidate already committed catalog batches. New revisions or days have
    # no marker and invalidate every old identity before the first quote write.
    if revision is not None and _phase_started(db, document_id, revision):
        return
    keys = document_keys(db, document_id)
    if older_only and revision is not None:
        _mark_older_document_keys_dirty(db, document_id, keys)
    else:
        mark_keys_dirty(db, keys)


def refresh_document(db, document_id, revision=None, *, older_only=False):
    """Refresh affected identities in bounded transactions, including withdrawals.

    Every original identity is included: a new parser revision can supersede a
    different quote key at the same source locator, and the Bogotá day can make
    an unchanged future-dated quote eligible. Each completed batch is durable
    even if the worker must defer the remaining keys.
    """
    # Existing caller transactions (such as retained PDF replay) keep row locks
    # until their outer commit. Never pause while that transaction is open.
    pace = db.autocommit and db.info.transaction_status == TransactionStatus.IDLE
    pending = sorted(set(document_keys(db, document_id)))
    if not pending:
        return 0
    phase = _refresh_phase() if revision is not None else None
    resumed = revision is not None and _phase_started(db, document_id, revision, phase)
    if not resumed:
        # Covers direct refresh callers as well as newly inserted identities;
        # the publication path also invalidates old identities before insert.
        if older_only and revision is not None:
            _mark_older_document_keys_dirty(db, document_id, pending)
        else:
            mark_keys_dirty(db, pending)
    if revision is not None:
        # This is reached only after the caller retained every quote/review and
        # source-locator retirement. The marker is durable even if no cache
        # batch fits before the deadline. It cannot imply source completion.
        with db.transaction():
            db.execute(
                "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
                "VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (document_id, revision, phase, len(pending)),
            )
    if resumed or (older_only and revision is not None):
        # The prior run committed clean 64-key batches. Triggers independently
        # dirty any quote/review/status change; cache-version changes also need
        # refresh. Keep clean batches visible and spend work only on the rest.
        pending = [
            row[0] for row in db.execute(
                "SELECT quote_key FROM official_catalog_current "
                "WHERE quote_key=ANY(%s::text[]) AND (dirty OR version<>%s) "
                "ORDER BY quote_key",
                (pending, VERSION),
            ).fetchall()
        ]
    from .worker import RUN_DEADLINE

    refreshed = 0
    for start in range(0, len(pending), DOCUMENT_BATCH_SIZE):
        deadline = RUN_DEADLINE.get()
        begun = _clock()
        if deadline is not None and begun >= deadline:
            raise WorkDeferred(
                f"Official catalog refresh deferred after {refreshed} of {len(pending)} identities"
            )
        refreshed += refresh_keys(db, pending[start : start + DOCUMENT_BATCH_SIZE])
        finished = _clock()
        if deadline is not None and finished >= deadline:
            raise WorkDeferred(
                f"Official catalog refresh deferred after {refreshed} of {len(pending)} identities"
            )
        if not pace:
            continue
        if start + DOCUMENT_BATCH_SIZE < len(pending):
            # Match each write/lookup burst with a bounded quiet interval so
            # app reads have a chance to use the small database's disk budget.
            delay = min(
                DOCUMENT_PACE_MAX_SECONDS,
                max(DOCUMENT_PACE_MIN_SECONDS, finished - begun),
            )
            if deadline is not None and finished + delay >= deadline:
                raise WorkDeferred(
                    f"Official catalog refresh deferred after {refreshed} of {len(pending)} identities"
                )
            if db.info.transaction_status == TransactionStatus.IDLE:
                _sleep(delay)
        write_pacing.yield_to_active_readers(db, deadline)
    return refreshed


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
        with catalog_stage("cache_lock", len(keys)):
            db.execute(
                "INSERT INTO official_catalog_current(quote_key) SELECT unnest(%s::text[]) ORDER BY 1 ON CONFLICT DO NOTHING",
                (keys,),
            )
            db.execute(
                "SELECT quote_key FROM official_catalog_current WHERE quote_key=ANY(%s::text[]) ORDER BY quote_key FOR UPDATE",
                (keys,),
            ).fetchall()
        with catalog_stage("winner_upsert", len(keys)):
            db.execute(
            """WITH latest AS MATERIALIZED ("""
            + _LATEST_WITH_DATES_SQL
            + """),
            requested(quote_key) AS (SELECT unnest(%s::text[]))
            INSERT INTO official_catalog_current(quote_key,payload,dirty,version,refreshed_at,
              winner_observed_on,previous_observed_on)
            SELECT requested.quote_key,CASE WHEN latest.quote_key IS NULL THEN NULL
                ELSE to_jsonb(latest)-'previous_observed_on' END,
              false,%s,statement_timestamp(),latest.observed_on,latest.previous_observed_on
            FROM requested LEFT JOIN latest USING(quote_key)
            ON CONFLICT(quote_key) DO UPDATE SET payload=excluded.payload,dirty=false,
              version=excluded.version,refreshed_at=excluded.refreshed_at,
              winner_observed_on=excluded.winner_observed_on,
              previous_observed_on=excluded.previous_observed_on""",
                (keys, keys, VERSION),
            )
    return len(keys)


def refresh_dirty(db, limit=100, *, priority_keys=()):
    """Bounded recovery: at most four explicit keys, then first-dirtied FIFO.

    The caller supplies exact source-backed identities; this function never
    scans raw quotes or lets a priority bypass dirty/version eligibility.
    """
    if not 1 <= limit <= 2000:
        raise ValueError("Official catalog refresh limit must be 1..2000")
    priority_keys = tuple(dict.fromkeys(priority_keys))
    if len(priority_keys) > 4 or any(
        not isinstance(key, str) or len(key) != 64 or
        any(ch not in "0123456789abcdef" for ch in key)
        for key in priority_keys
    ):
        raise ValueError("At most four exact official quote keys are allowed")
    with catalog_stage("dirty_selection", len(priority_keys)):
        selected = [
            row[0] for row in db.execute(
                "SELECT quote_key FROM official_catalog_current "
                "WHERE quote_key=ANY(%s::text[]) AND (dirty OR version<>%s)",
                (list(priority_keys), VERSION),
            ).fetchall()
        ] if priority_keys else []
        selected.sort(key=priority_keys.index)
        selected = selected[:limit]
        remaining = limit - len(selected)
        ordinary = [
            row[0]
            for row in db.execute(
                "SELECT quote_key FROM official_catalog_current WHERE (dirty OR version<>%s) "
                "AND NOT (quote_key=ANY(%s::text[])) "
                "ORDER BY CASE WHEN dirty THEN dirty_since ELSE refreshed_at END NULLS FIRST,"
                "quote_key LIMIT %s",
                (VERSION, selected, remaining),
            ).fetchall()
        ] if remaining else []
    from .worker import RUN_DEADLINE
    # Preserve the existing ordinary FIFO refresh behavior. The new two-batch
    # priority path alone needs a deadline check between its committed batches.
    deadline = RUN_DEADLINE.get() if priority_keys else None
    if deadline is not None and _clock() >= deadline:
        raise WorkDeferred("Official catalog dirty refresh deferred before priority keys")
    refreshed = refresh_keys(db, selected) if selected else 0
    if deadline is not None and _clock() >= deadline:
        raise WorkDeferred(f"Official catalog dirty refresh deferred after {refreshed} priority identities")
    return refreshed + (refresh_keys(db, ordinary) if ordinary else 0)


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

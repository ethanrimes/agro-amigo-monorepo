"""Coalesce input read-model refreshes without changing source publication."""

import time

from psycopg.errors import LockNotAvailable, QueryCanceled
from psycopg.pq import TransactionStatus


def refresh(db, *, deadline=None):
    result = {"refreshed": [], "deferred": [], "available": False}
    if not db.execute("SELECT to_regclass('input_latest_projection_state')").fetchone()[0]:
        return result
    result["available"] = True
    states = db.execute(
        "SELECT scope,(projection_epoch=source_epoch OR delta_complete) AND "
        "asof_bogota=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date AS ready "
        "FROM input_latest_projection_state ORDER BY scope"
    ).fetchall()
    for scope, ready in states:
        if ready:
            continue
        remaining = deadline - time.monotonic() if deadline is not None else 125
        if remaining < 30 or not db.autocommit or db.info.transaction_status != TransactionStatus.IDLE:
            result["deferred"].append(scope)
            continue
        started = time.monotonic()
        try:
            # Restore the caller's timeout automatically after either commit or
            # rollback. A failed refresh leaves its epoch invalid and readers
            # continue using the exact published raw path.
            with db.transaction():
                db.execute("SELECT set_config('statement_timeout',%s,true)",
                           (str(int(min(120, remaining - 5) * 1000)),))
                db.execute("SET LOCAL lock_timeout='3s'")
                fresh = db.execute("SELECT refresh_input_latest_projection(%s)", (scope,)).fetchone()[0]
            if fresh:
                result["refreshed"].append({"scope": scope, "seconds": round(time.monotonic()-started, 3)})
            else:
                result["deferred"].append(scope)
        except (LockNotAvailable, QueryCanceled):
            result["deferred"].append(scope)
    return result

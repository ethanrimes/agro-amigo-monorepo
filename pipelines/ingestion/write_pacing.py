"""Yield the database between committed historical publication batches."""

import time

from psycopg.pq import TransactionStatus

from .resumable_inputs import WorkDeferred


def clock():
    return time.monotonic()


READER_YIELD_LIMIT_SECONDS = 30.0
READER_YIELD_POLL_SECONDS = 1.0


def yield_to_active_readers(db, deadline):
    """Offer active app SQL a bounded quiet interval after a durable commit.

    The database helper returns only a boolean. A missing helper is an error:
    silently treating invisible reader state as idle would defeat this guard.
    """
    if not db.autocommit or db.info.transaction_status != TransactionStatus.IDLE:
        return
    started = clock()
    while True:
        now = clock()
        if deadline is not None and now >= deadline:
            raise WorkDeferred("Committed official batches retained; next work deferred")
        if not db.execute("SELECT public.agro_readers_active()").fetchone()[0]:
            return
        remaining = READER_YIELD_LIMIT_SECONDS - (clock() - started)
        if remaining <= 0:
            return
        delay = min(READER_YIELD_POLL_SECONDS, remaining)
        if deadline is not None and clock() + delay >= deadline:
            raise WorkDeferred("Committed official batches retained; next work deferred")
        time.sleep(delay)


def pause_between_batches(db, started, deadline, *, remaining):
    # A caller's transaction must retain its atomicity, without idle sleeps or
    # deferral that would undo a supposedly committed checkpoint.
    if not db.autocommit or db.info.transaction_status != TransactionStatus.IDLE:
        return
    if remaining:
        now = clock()
        # Give reads two quiet seconds for each second spent writing, bounded to
        # avoid either a tight loop on fast batches or an unbounded worker sleep.
        delay = min(5.0, max(0.25, 2 * max(0, now - started)))
        if deadline is not None and now + delay >= deadline:
            raise WorkDeferred("Committed official quote batches retained; next batch deferred")
        time.sleep(delay)
    # Include the final quote batch before the catalog refresh. A resumed
    # publication can repeat immutable quote inserts safely after deferral.
    yield_to_active_readers(db, deadline)

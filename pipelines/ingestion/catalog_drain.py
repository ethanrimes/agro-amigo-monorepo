"""Bounded, reader-aware drain for the derived official catalog cache."""

from dataclasses import asdict, dataclass
import time

from . import official_catalog, write_pacing
from .resumable_inputs import WorkDeferred


DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_BATCHES = 12
DEFAULT_WINDOW_SECONDS = 20.0
MIN_PAUSE_SECONDS = 0.25


@dataclass(frozen=True)
class CatalogDrainResult:
    status: str
    batches: int
    refreshed: int
    elapsed_seconds: float
    budget_seconds: float
    batch_limit: int
    more_may_remain: bool
    stop_reason: str

    def as_record(self):
        return asdict(self)


def _has_pending(db):
    # The current production backlog is overwhelmingly dirty, so consult the
    # FIFO partial index first. Scan for stale versions only after it is empty.
    if db.execute(
        "SELECT EXISTS(SELECT 1 FROM official_catalog_current WHERE dirty)"
    ).fetchone()[0]:
        return True
    return db.execute(
        "SELECT EXISTS(SELECT 1 FROM official_catalog_current WHERE version<>%s)",
        (official_catalog.VERSION,),
    ).fetchone()[0]


def _pause_between_batches(db, batch_started, deadline):
    try:
        write_pacing.pause_between_batches(
            db, batch_started, deadline, remaining=True,
        )
    except WorkDeferred:
        return False
    return True


def _drain_window(
    db,
    *,
    refresh_dirty,
    priority_keys,
    run_deadline,
    has_pending,
    pause_between_batches,
    time_budget_seconds=DEFAULT_WINDOW_SECONDS,
    batch_size=DEFAULT_BATCH_SIZE,
    max_batches=DEFAULT_MAX_BATCHES,
    clock=time.monotonic,
):
    if time_budget_seconds <= 0:
        raise ValueError("Catalog drain time budget must be positive")
    if not 1 <= batch_size <= DEFAULT_BATCH_SIZE:
        raise ValueError("Catalog drain batch size must be 1..100")
    if not 1 <= max_batches <= DEFAULT_MAX_BATCHES:
        raise ValueError("Catalog drain batch cap must be 1..12")
    priority_keys = tuple(dict.fromkeys(priority_keys))
    if len(priority_keys) > 4:
        raise ValueError("At most four official catalog repair keys are allowed")

    started = clock()
    window_deadline = started + float(time_budget_seconds)
    deadline = min(window_deadline, run_deadline) if run_deadline is not None else window_deadline
    total = batches = 0
    stop_reason = "queue_exhausted"
    more_may_remain = False

    while batches < max_batches:
        now = clock()
        if now >= deadline:
            stop_reason = "run_deadline" if run_deadline is not None and now >= run_deadline else "time_budget"
            more_may_remain = True
            break
        batch_started = now
        refreshed = refresh_dirty(
            db, limit=batch_size,
            priority_keys=priority_keys if batches == 0 else (),
        )
        if not isinstance(refreshed, int) or not 0 <= refreshed <= batch_size:
            raise RuntimeError("Official catalog refresh returned an invalid batch count")
        batches += 1
        total += refreshed
        if refreshed < batch_size:
            stop_reason = "queue_exhausted"
            more_may_remain = False
            break
        now = clock()
        if batches >= max_batches:
            stop_reason = "batch_cap"
            more_may_remain = True
            break
        if now >= deadline:
            stop_reason = "run_deadline" if run_deadline is not None and now >= run_deadline else "time_budget"
            more_may_remain = True
            break
        more_may_remain = bool(has_pending(db))
        if not more_may_remain:
            stop_reason = "queue_exhausted"
            break
        now = clock()
        if now >= deadline:
            stop_reason = "run_deadline" if run_deadline is not None and now >= run_deadline else "time_budget"
            more_may_remain = True
            break
        if deadline - now <= MIN_PAUSE_SECONDS:
            stop_reason = "run_deadline" if run_deadline is not None and run_deadline <= window_deadline else "time_budget"
            more_may_remain = True
            break
        if pause_between_batches(db, batch_started, deadline) is False:
            now = clock()
            stop_reason = "run_deadline" if run_deadline is not None and now >= run_deadline else "time_budget"
            more_may_remain = True
            break
    else:
        stop_reason = "batch_cap"
        more_may_remain = True

    elapsed = max(0.0, clock() - started)
    return CatalogDrainResult(
        status="bounded" if more_may_remain else "drained",
        batches=batches,
        refreshed=total,
        elapsed_seconds=elapsed,
        budget_seconds=float(time_budget_seconds),
        batch_limit=batch_size * max_batches,
        more_may_remain=more_may_remain,
        stop_reason=stop_reason,
    )


def drain_official_catalog(db, *, priority_keys=(), run_deadline=None):
    """Refresh the derived cache within one bounded, reader-aware window."""
    return _drain_window(
        db,
        refresh_dirty=official_catalog.refresh_dirty,
        priority_keys=priority_keys,
        run_deadline=run_deadline,
        has_pending=_has_pending,
        pause_between_batches=_pause_between_batches,
    )

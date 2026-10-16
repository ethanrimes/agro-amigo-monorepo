"""Bounded, non-sensitive official catalog stage failures.

This module never logs SQL, keys,
connection strings, or exception messages.  The original exception remains
available only as Python context, which the worker does not serialize.
"""

from contextlib import contextmanager
import re
import time

from .resumable_inputs import WorkDeferred


STAGES = frozenset((
    "input_projection", "repair_priority", "dirty_selection",
    "cache_lock", "winner_upsert", "dirty_refresh", "unattributed",
))


class CatalogStageFailure(RuntimeError):
    def __init__(self, stage, elapsed_ms, key_count, sqlstate):
        if stage not in STAGES:
            raise ValueError("Unknown catalog stage")
        self.stage = stage
        self.elapsed_ms = min(999999, max(0, int(elapsed_ms)))
        self.key_count = min(2000, max(0, int(key_count)))
        self.sqlstate = sqlstate if isinstance(sqlstate, str) and re.fullmatch(r"[A-Z0-9]{5}", sqlstate) else "UNKNOWN"
        super().__init__(
            f"stage={self.stage} elapsed_ms={self.elapsed_ms} "
            f"key_count={self.key_count} sqlstate={self.sqlstate}"
        )


@contextmanager
def catalog_stage(stage, key_count=0):
    if stage not in STAGES:
        raise ValueError("Unknown catalog stage")
    started = time.monotonic()
    try:
        yield
    except (CatalogStageFailure, WorkDeferred):
        raise
    except Exception as exc:
        raise CatalogStageFailure(
            stage, (time.monotonic() - started) * 1000, key_count,
            getattr(exc, "sqlstate", None),
        ) from None


def catalog_error_record(exc):
    """The worker summary contains only the reviewed bounded fields."""
    if isinstance(exc, CatalogStageFailure):
        return {"source": "official_catalog", "error": str(exc)}
    # WorkDeferred and unexpected validation failures still reach the existing
    # worker error path. Never claim a stage that was not actually observed.
    return {"source": "official_catalog", "error":
            "stage=unattributed elapsed_ms=0 key_count=0 sqlstate=UNKNOWN"}

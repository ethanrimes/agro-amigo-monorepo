"""Commit validated input originals once, then publish bounded calendar months.

All native rows must parse before the native checkpoint commits. Each subsequent
month and checkpoint commit together; a timeout cannot expose half a month or
make the next invocation repeat an entire multi-million-row workbook.
"""

import time
from itertools import islice

BATCH_SIZE = 25000


class WorkDeferred(Exception):
    """Safe checkpoint reached; the next invocation resumes remaining work."""


def publish(db, data, did, kind, day, *, deadline=None):
    from . import worker
    from .input_references import extract_reference_rows
    from .inputs import parse_inputs, project_inputs

    version = worker.parser_version(kind)
    steps = dict(
        db.execute(
            "SELECT step,records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s",
            (did, version),
        ).fetchall()
    )

    def checkpoint(step, records):
        db.execute(
            "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (did, version, step, records),
        )

    def check_budget(message):
        if deadline is not None and time.monotonic() >= deadline:
            raise WorkDeferred(message)

    if "native" not in steps:
        # Validate the complete literal workbook before any source rows are
        # committed. Then use bounded COPY transactions instead of one enormous
        # statement whose rollback used to erase hours of work.
        if "validated" not in steps:
            check_budget("Native input validation deferred before starting")
            validation = iter(parse_inputs(data))
            count = 0
            try:
                for _ in validation:
                    count += 1
                    if count % 1000 == 0:
                        check_budget(
                            "Native input validation exceeded this run's budget"
                        )
            finally:
                if hasattr(validation, "close"):
                    validation.close()
            with db.transaction():
                checkpoint("validated", count)
            steps["validated"] = count
        rows = iter(parse_inputs(data))
        count = batch_number = 0
        try:
            while batch := list(islice(rows, BATCH_SIZE)):
                batch_number += 1
                count += len(batch)
                step = f"native-batch:{batch_number:06d}"
                check_budget(
                    "Validated input batches checkpointed; source rows will resume"
                )
                if step in steps:
                    continue
                with db.transaction():
                    copied = worker.save_rows(db, did, batch)
                    checkpoint(step, copied)
        finally:
            if hasattr(rows, "close"):
                rows.close()
        if count != steps["validated"]:
            raise ValueError(
                "Input row count changed between native validation and persistence"
            )
        with db.transaction():
            checkpoint("native", count)
        steps["native"] = count
    periods = db.execute(
        "SELECT DISTINCT observed_on FROM historical_price WHERE document_id=%s ORDER BY observed_on DESC",
        (did,),
    ).fetchall()
    conflicts = 0
    for (period,) in periods:
        step = "published:" + period.isoformat()
        if step in steps:
            conflicts += steps[step]
            continue
        if deadline is not None and time.monotonic() >= deadline:
            raise WorkDeferred(
                "Input months checkpointed; remaining months will resume"
            )
        with db.transaction():
            count = project_inputs(db, did, period)
            checkpoint(step, count)
        conflicts += count
    if "references" not in steps:
        if deadline is not None and time.monotonic() >= deadline:
            raise WorkDeferred("Input prices published; reference tables will resume")
        with db.transaction():
            count = extract_reference_rows(db, data, did, day)
            checkpoint("references", count)
    # Older header adapters mistakenly queued readable workbooks' logos. Once
    # native validation and all monthly publication steps succeed, no pending
    # OCR request should be spent on those already-extracted originals. Keep
    # prior readings/review decisions and every original unchanged.
    db.execute(
        """UPDATE source_ocr_task SET status='native-complete',checked_at=now(),
        error='Native workbook extraction and monthly publication completed'
        WHERE document_id=%s AND source_kind=%s AND status IN ('pending','deferred')""",
        (did, kind),
    )
    return steps["native"], conflicts

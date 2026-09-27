"""Replay superseded official originals without refetching mutable publisher URLs.

The normal asset queue has one pointer per URL. Its older immutable documents
need their own versioned completion/review markers so parser upgrades can recover
missed weeks. This module never changes that current pointer or invents a URL.
"""

import logging
import time

from psycopg.types.json import Jsonb

LOG = logging.getLogger(__name__)
COMPLETE = "retained:complete"
REVIEW = "retained:review"
ATTEMPT_PREFIX = "retained:attempt:"
COOLDOWN_SECONDS = 3600
MAX_PER_RUN = 2


def leaf_versions():
    from . import colombia_sources, international_sources, worker

    excluded = colombia_sources.INDEX_KINDS | {"colombia-evidence"}
    kinds = sorted(
        kind
        for module in (colombia_sources, international_sources)
        for kind in module.PUBLISHERS
        if kind not in excluded and not kind.endswith("-index")
    )
    return [(kind, worker.parser_version(kind)) for kind in kinds]


def candidate_query(versions, limit, cooldown_seconds):
    """Metadata-only selection; the indexed document bytes are loaded after LIMIT.

    source_document(source_url,retrieved_at) narrows each registered URL to its
    retained versions. Quote/checkpoint probes use their document-prefixed PKs.
    There is no historical_price scan, aggregate, or content read in this query.
    """
    values = ",".join("(%s,%s)" for _ in versions)
    sql = f"""
        WITH versions(kind,processor_version) AS (VALUES {values})
        SELECT d.id,d.source_url,a.kind,v.processor_version
        FROM ingestion_asset a
        JOIN versions v ON v.kind=a.kind
        JOIN source_document current ON current.id=a.document_id
        JOIN source_document d ON d.source_url=a.url
        WHERE d.id<>a.document_id AND d.retrieved_at<current.retrieved_at
          AND d.kind='original' AND d.metadata->>'ingestion_kind'=a.kind
          AND NOT EXISTS (
              SELECT 1 FROM official_price_quote q
              WHERE q.document_id=d.id AND q.parser_version=v.processor_version
          )
          AND NOT EXISTS (
              SELECT 1 FROM ingestion_checkpoint c
              WHERE c.document_id=d.id AND c.processor_version=v.processor_version
                AND (c.step IN (%s,%s) OR (
                    c.step LIKE %s
                    AND c.completed_at>now()-(%s * interval '1 second')
                ))
          )
        ORDER BY d.retrieved_at DESC,d.id
        LIMIT %s
    """
    params = [part for pair in versions for part in pair]
    params.extend([COMPLETE, REVIEW, ATTEMPT_PREFIX + "%", cooldown_seconds, limit])
    return sql, tuple(params)


def _checkpoint(db, did, version, step, records=0):
    db.execute(
        "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
        "VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        (did, version, step, records),
    )


def _attempt(db, did, version, cooldown_seconds):
    # Append-only checkpoints only grant INSERT, not UPDATE. One fixed-size
    # marker per cooldown bucket avoids uncontrolled rows and index-key growth.
    bucket = int(time.time() // cooldown_seconds)
    _checkpoint(db, did, version, ATTEMPT_PREFIX + str(bucket))


def _timeout(db, deadline, maximum_ms):
    remaining = maximum_ms
    if deadline is not None:
        remaining = min(remaining, max(1, int((deadline - time.monotonic()) * 1000)))
    db.execute("SELECT set_config('statement_timeout',%s,true)", (str(remaining),))


def drain(db, *, limit=MAX_PER_RUN, deadline=None, cooldown_seconds=COOLDOWN_SECONDS):
    """Publish at most two older official documents in independent transactions.

    `deadline` is monotonic and is checked before selection, each document, and
    native parsing. SQL also receives the remaining budget. A parser already in
    progress cannot be interrupted safely; these bounded official leaf parsers
    should finish before the caller proceeds to its next auxiliary phase.

    A successful return of 0 is complete (possibly all rows went to review).
    None means OCR is pending: keep tasks/results and a cooldown marker, never a
    completion marker. Deterministic ValueError gets a version-specific review;
    transport/database/runtime failures stay retryable after the cooldown.
    """
    from . import official_sources

    limit = max(0, min(int(limit), MAX_PER_RUN))
    cooldown_seconds = max(60, int(cooldown_seconds))
    summary = {
        "selected": 0,
        "completed": 0,
        "review": 0,
        "awaiting_ocr": 0,
        "failed": 0,
        "rows": 0,
        "deferred": 0,
        "errors": [],
    }
    if not limit or (deadline is not None and time.monotonic() >= deadline):
        return summary
    versions = leaf_versions()
    if not versions:
        return summary
    try:
        with db.transaction():
            _timeout(db, deadline, 5000)
            candidates = db.execute(
                *candidate_query(versions, limit, cooldown_seconds)
            ).fetchall()
    except Exception as exc:  # noqa: BLE001 - auxiliary selection must not abort the ingestion run.
        summary["errors"].append({"phase": "selection", "error": str(exc)[:1000]})
        LOG.warning("Retained official selection failed: %s", str(exc)[:1000])
        return summary
    summary["selected"] = len(candidates)
    for did, url, kind, version in candidates:
        if deadline is not None and time.monotonic() >= deadline:
            summary["deferred"] += 1
            continue
        try:
            with db.transaction():
                _timeout(db, deadline, 30000)
                # Normal runs already hold the ingestion lock; the per-document
                # lock also makes a standalone/manual drain safe to overlap.
                if not db.execute(
                    "SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0))",
                    ("retained:" + did + ":" + version,),
                ).fetchone()[0]:
                    summary["deferred"] += 1
                    continue
                if db.execute(
                    "SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s "
                    "AND processor_version=%s AND step IN (%s,%s) LIMIT 1",
                    (did, version, COMPLETE, REVIEW),
                ).fetchone():
                    continue
                original = db.execute(
                    "SELECT content FROM source_document WHERE id=%s", (did,)
                ).fetchone()
                if not original:
                    raise RuntimeError("Retained original bytes are unavailable")
                if deadline is not None and time.monotonic() >= deadline:
                    summary["deferred"] += 1
                    continue
                count = official_sources.process(db, bytes(original[0]), did, url, kind)
                if count is None:
                    _attempt(db, did, version, cooldown_seconds)
                else:
                    if (
                        not isinstance(count, int)
                        or isinstance(count, bool)
                        or count < 0
                    ):
                        raise RuntimeError("Official parser returned an invalid count")
                    _checkpoint(db, did, version, COMPLETE, count)
            if count is None:
                summary["awaiting_ocr"] += 1
            else:
                summary["completed"] += 1
                summary["rows"] += count
        except Exception as exc:  # noqa: BLE001 - isolate each archived document's parser/database failure.
            deterministic = isinstance(exc, ValueError)
            summary["review" if deterministic else "failed"] += 1
            summary["errors"].append({"document_id": did, "error": str(exc)[:1000]})
            LOG.warning("Retained official document %s: %s", did, str(exc)[:1000])
            # The failed publication transaction rolled back. Its review or
            # retry marker commits independently and cannot poison other docs.
            try:
                with db.transaction():
                    _timeout(db, deadline, 5000)
                    if deterministic:
                        db.execute(
                            "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) "
                            "VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (
                                did,
                                "retained-document:review",
                                version,
                                Jsonb({"source_url": url, "ingestion_kind": kind}),
                                str(exc)[:2000],
                            ),
                        )
                        _checkpoint(db, did, version, REVIEW)
                    else:
                        _attempt(db, did, version, cooldown_seconds)
            except Exception as marker_error:  # noqa: BLE001 - preserve progress if the checkpoint connection fails.
                summary["errors"].append(
                    {
                        "document_id": did,
                        "phase": "checkpoint",
                        "error": str(marker_error)[:1000],
                    }
                )
                LOG.warning(
                    "Retained replay checkpoint %s failed: %s",
                    did,
                    str(marker_error)[:1000],
                )
    return summary

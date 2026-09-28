"""Publish validated daily matrices while retaining literal review evidence."""

import hashlib
import json
from decimal import Decimal

from psycopg.types.json import Jsonb


def retain_resolution(db, kind, evidence):
    """Append idempotent source-resolution evidence without changing originals."""
    encoded = json.dumps(evidence, sort_keys=True, ensure_ascii=False, default=str)
    db.execute(
        """INSERT INTO retained_record(table_name,fingerprint,record)
        VALUES(%s,%s,%s) ON CONFLICT DO NOTHING""",
        (kind, hashlib.sha256(encoded.encode()).hexdigest(), Jsonb(evidence)),
    )


VARIATION_REVISION = "daily-variation-v1"


def _identity(row):
    return (*row[1:6], Decimal(str(row[6])))


def _change(value):
    return None if value is None else Decimal(str(value))


def _legacy_percentage_error(previous, current):
    """Only the proven numeric-times100 bug may create a variation revision."""
    from .daily_recovery import percentage_change

    details = current[-1]
    raw, fmt = details.get("raw_change"), details.get("change_number_format")
    if fmt is None or details.get("change_percent_encoding") != "percentage_points":
        return False
    corrected, proof = percentage_change(raw, fmt)
    if corrected is None or proof.get("change_scale") != 1:
        return False
    return (
        current[7] is not None
        and previous[7] is not None
        and Decimal(str(current[7])) == Decimal(str(corrected))
        and Decimal(str(previous[7])) == Decimal(str(float(raw) * 100))
    )


def current_daily_rows(rows):
    """Select explicit validated correction rows; preserve every raw revision."""
    from .worker import SourceDateMismatch

    by_locator = {r[0]: r for r in rows}
    superseded = set()
    for row in rows:
        base = row[-1].get("supersedes_source_locator")
        if not base:
            continue
        prior = by_locator.get(base)
        if (
            row[0] != base + "; " + VARIATION_REVISION
            or row[-1].get("variation_revision") != VARIATION_REVISION
            or prior is None
            or _identity(prior) != _identity(row)
            or not _legacy_percentage_error(prior, row)
        ):
            raise SourceDateMismatch("Invalid daily variation revision at " + row[0])
        superseded.add(base)
    return [r for r in rows if r[0] not in superseded]


def _publication_rows(rows, existing):
    """Allow exact replay or an additive proven percentage correction only."""
    from .worker import SourceDateMismatch

    incoming = {r[0]: r for r in rows}
    revisions = {}
    for previous in existing:
        base = previous[-1].get("supersedes_source_locator", previous[0])
        current = incoming.get(base)
        if current is None or _identity(previous) != _identity(current):
            raise SourceDateMismatch(
                "Daily recovery conflicts with immutable evidence at " + previous[0]
            )
        if previous[0] != base:
            if (
                previous[0] != base + "; " + VARIATION_REVISION
                or previous[-1].get("variation_revision") != VARIATION_REVISION
            ):
                raise SourceDateMismatch(
                    "Unknown daily variation revision at " + previous[0]
                )
            if _change(previous[7]) != _change(current[7]):
                raise SourceDateMismatch(
                    "Daily recovery conflicts with immutable evidence at " + previous[0]
                )
            revisions[base] = previous[0]
        elif _change(previous[7]) != _change(current[7]):
            if not _legacy_percentage_error(previous, current):
                raise SourceDateMismatch(
                    "Daily recovery conflicts with immutable evidence at " + previous[0]
                )
            revisions[base] = base + "; " + VARIATION_REVISION
    result = []
    for row in rows:
        if row[0] in revisions:
            row = (
                revisions[row[0]],
                *row[1:-1],
                {
                    **row[-1],
                    "supersedes_source_locator": row[0],
                    "variation_revision": VARIATION_REVISION,
                },
            )
        result.append(row)
    # Validate already retained correction provenance too, regardless of row order.
    current_daily_rows(existing)
    return result


def publish(db, data, did, url, expected_day, *, update_asset=True, parsed_result=None):
    from . import daily_recovery, worker

    result = (
        parsed_result
        if parsed_result is not None
        else daily_recovery.parse_daily(data, expected_day)
    )
    rows, reviews = result["rows"], result["reviews"]
    # A variation correction appends a versioned locator only after every
    # date, identity, unit and price agrees with the immutable original rows.
    with db.transaction():
        existing = db.execute(
            """SELECT source_locator,series,observed_on,product_name,market_name,
            unit,price,change_percent,details FROM historical_price WHERE document_id=%s""",
            (did,),
        ).fetchall()
        rows = _publication_rows(rows, existing)
        count = worker.save_rows(db, did, rows) if rows else 0
        if reviews:
            with db.cursor() as cur:
                cur.executemany(
                    """INSERT INTO official_source_review
                    (document_id,source_locator,parser_version,record,reason)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    [
                        (
                            did,
                            r["source_locator"],
                            daily_recovery.VERSION,
                            Jsonb(r["record"]),
                            r["reason"],
                        )
                        for r in reviews
                    ],
                )
        for evidence in result["date_resolutions"]:
            retain_resolution(
                db,
                "source_date_resolution",
                {
                    "document_id": did,
                    "source_url": url,
                    **evidence,
                },
            )
        if count:
            worker.project(db, did, url, "daily", source_rows=rows)
        misplaced = [
            r
            for r in result["date_resolutions"]
            if r["archive_date"] != r["observation_date"]
        ]
        notes = []
        if reviews:
            notes.append(
                f"{len(reviews)} price cells retained for review; {count} explicit quotes published"
            )
        if misplaced:
            actual = ", ".join(sorted({r["observation_date"] for r in misplaced}))
            notes.append(
                f"Publisher archive mislink: verified observations belong to {actual}, not {expected_day}; requested-day coverage remains unresolved"
            )
        elif result["date_resolutions"]:
            notes.append(
                "Native date header corrected using exact original hash and independent official evidence"
            )
        status = "review" if misplaced or (reviews and not count) else "complete"
        if update_asset:
            db.execute(
                """UPDATE ingestion_asset SET document_id=%s,status=%s,records=%s,
                checked_at=now(),attempts=attempts+1,error=%s WHERE url=%s""",
                (did, status, count, "; ".join(notes) or None, url),
            )
    return count

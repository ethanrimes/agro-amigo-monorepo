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


def publish(db, data, did, url, expected_day):
    from . import daily_recovery, worker

    result = daily_recovery.parse_daily(data, expected_day)
    rows, reviews = result["rows"], result["reviews"]
    identities = {
        row[0]: (
            *row[1:6],
            Decimal(str(row[6])),
            Decimal(str(row[7])) if row[7] is not None else None,
        )
        for row in rows
    }
    # Existing immutable rows cannot be silently reinterpreted during a replay.
    # A changed date/identity requires an explicit migration, never republishing
    # the old rows merely because this version parsed the original successfully.
    with db.transaction():
        existing = db.execute(
            """SELECT source_locator,series,observed_on,product_name,market_name,
            unit,price,change_percent FROM historical_price WHERE document_id=%s""",
            (did,),
        ).fetchall()
        for row in existing:
            if identities.get(row[0]) != row[1:]:
                raise worker.SourceDateMismatch(
                    "Daily recovery conflicts with immutable evidence at " + row[0]
                )
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
            worker.project(db, did, url, "daily")
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
        db.execute(
            """UPDATE ingestion_asset SET document_id=%s,status=%s,records=%s,
            checked_at=now(),attempts=attempts+1,error=%s WHERE url=%s""",
            (did, status, count, "; ".join(notes) or None, url),
        )
    return count

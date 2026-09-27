"""Read-only operational audit; never prints credentials or source bytes."""

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from psycopg.rows import dict_row

from .worker import connect

QUERIES = {
    "runs": "SELECT id,mode,started_at,finished_at,status,summary FROM ingestion_run WHERE started_at>=%s ORDER BY started_at DESC",
    "queue": "SELECT kind,status,count(*) assets,sum(records) records,min(checked_at) oldest_check,max(checked_at) newest_check FROM ingestion_asset GROUP BY kind,status ORDER BY kind,status",
    "assets": "SELECT url,kind,observed_on,discovered_at,checked_at,status,records,error,attempts,processor_version,document_id FROM ingestion_asset ORDER BY kind,url",
    "size": "SELECT pg_size_pretty(pg_database_size(current_database())) size",
    "active": "SELECT pid,usename,state,wait_event_type,wait_event,query_start,left(query,400) query FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND (state='active' OR wait_event_type='Lock')",
    "locks": "SELECT pid,mode,granted FROM pg_locks WHERE locktype='advisory'",
    "ocr": "SELECT status,count(*) FROM source_ocr_task GROUP BY status",
    "failed": "SELECT kind,error,count(*) assets FROM ingestion_asset WHERE status IN ('failed','review','awaiting-ocr') GROUP BY kind,error ORDER BY count(*) DESC",
}


def audit(output, since=None):
    since = since or (datetime.now(timezone.utc).date() - timedelta(days=30))
    report = {"at": datetime.now(timezone.utc).isoformat()}
    with connect() as db:
        db.row_factory = dict_row
        db.execute("SET default_transaction_read_only=on")
        db.execute("SET statement_timeout='30s'")
        for name, query in QUERIES.items():
            try:
                with db.transaction():
                    report[name] = db.execute(
                        query, (since,) if name == "runs" else None
                    ).fetchall()
            except Exception as exc:  # noqa: BLE001 - preserve other audit sections after a query fails.
                report[name] = {"error": type(exc).__name__}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, default=str, indent=2) + "\n")
    from collections import Counter

    print(
        json.dumps(
            {
                "output": str(output),
                "at": report["at"],
                "size": report["size"],
                "run_statuses": dict(
                    Counter(
                        r["mode"] + ":" + r["status"]
                        for r in report["runs"]
                        if isinstance(r, dict)
                    )
                ),
                "queue_statuses": dict(
                    Counter(
                        r["status"] for r in report["assets"] if isinstance(r, dict)
                    )
                ),
                "recent_runs": report["runs"][:3]
                if isinstance(report["runs"], list)
                else report["runs"],
                "active": report["active"],
            },
            default=str,
            indent=2,
        )
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--since", type=date.fromisoformat)
    args = parser.parse_args()
    audit(args.output, args.since)

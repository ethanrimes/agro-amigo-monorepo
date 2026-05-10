"""
Helpers for detecting stale cumulative downloads at static URLs.

SIPSA's cumulative files (rice/insumos/abastecimiento current-year, etc.) are
served at a static URL and overwritten in place when DANE publishes new data.
The plain "is this URL already in download_entries?" check causes us to skip
fresh data forever after the first download.

`check_url_freshness` issues a HEAD request and compares the server's
Last-Modified header against the existing entry's download_date. If the server
copy is newer, the caller is expected to clean up child rows
(via `cleanup_stale_entry`) and proceed with a fresh download.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import psycopg2
import requests
from email.utils import parsedate_to_datetime


@dataclass
class FreshnessResult:
    status: str          # "missing" (no entry) | "fresh" (entry up to date) | "stale" (server newer)
    existing_entry: Optional[dict] = None
    server_last_modified: Optional[datetime] = None


def check_url_freshness(database, session: requests.Session, url: str,
                        timeout: int = 30) -> FreshnessResult:
    """Check whether the URL has been updated on the server since we last downloaded it."""
    existing = database.get_download_entry_by_link(url)
    if not existing:
        return FreshnessResult("missing")

    try:
        resp = session.head(url, allow_redirects=True, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException:
        # If HEAD fails, treat as fresh — we don't want to re-download just because the
        # network blipped. The next run will retry.
        return FreshnessResult("fresh", existing_entry=existing)

    last_mod = resp.headers.get("Last-Modified")
    if not last_mod:
        return FreshnessResult("fresh", existing_entry=existing)

    try:
        server_dt = parsedate_to_datetime(last_mod)
    except (TypeError, ValueError):
        return FreshnessResult("fresh", existing_entry=existing)

    if server_dt.tzinfo is None:
        server_dt = server_dt.replace(tzinfo=timezone.utc)

    download_date = existing.get("download_date")
    if isinstance(download_date, str):
        try:
            download_dt = datetime.fromisoformat(download_date.replace("Z", "+00:00"))
        except ValueError:
            return FreshnessResult("stale", existing_entry=existing,
                                   server_last_modified=server_dt)
    elif isinstance(download_date, datetime):
        download_dt = download_date
    else:
        return FreshnessResult("stale", existing_entry=existing,
                               server_last_modified=server_dt)

    if download_dt.tzinfo is None:
        download_dt = download_dt.replace(tzinfo=timezone.utc)

    if server_dt > download_dt:
        return FreshnessResult("stale", existing_entry=existing,
                               server_last_modified=server_dt)
    return FreshnessResult("fresh", existing_entry=existing)


def cleanup_stale_entry(entry: dict, dest_tables: Iterable[str], also_clear_observations: bool = False) -> None:
    """Delete child rows and the download_entry row for a stale entry.

    Local files are left in place; callers downloading a fresh copy will overwrite them.
    Storage objects are deleted only on demand because reuploading touches the bucket anyway.
    """
    eid = entry["id"]
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise RuntimeError("SUPABASE_DB_URL not set")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '900s'")

        if also_clear_observations:
            _batched_delete(conn, "price_observations", "download_entry_id", eid)
        for tbl in dest_tables:
            _batched_delete(conn, tbl, "download_entry_id", eid)

        with conn.cursor() as cur:
            cur.execute("DELETE FROM download_entries WHERE id = %s", (eid,))
    finally:
        conn.close()

    # Best-effort local file removal so the scraper actually re-downloads instead of [LOCAL]-reusing.
    storage_path = entry.get("storage_path") or ""
    if storage_path.startswith("local:"):
        local = Path(storage_path[len("local:"):])
        if local.exists():
            try:
                local.unlink()
            except OSError:
                pass


def _batched_delete(conn, table: str, col: str, value, batch: int = 50000) -> None:
    while True:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {table} WHERE id IN ("
                f"  SELECT id FROM {table} WHERE {col} = %s LIMIT {batch}"
                f")",
                (value,),
            )
            n = cur.rowcount
        if n == 0:
            return

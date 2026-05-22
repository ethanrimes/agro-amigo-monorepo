"""
Supabase client initialization and connection management.
"""

import os
import socket
from pathlib import Path
from typing import Optional, List, Tuple
from dotenv import load_dotenv
from supabase import create_client, Client
import psycopg2
from psycopg2.extras import RealDictCursor

# Load environment variables from data-pipeline/.env
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

# Singleton instances
_supabase_client: Optional[Client] = None
_db_connection = None
_chosen_db_url: Optional[str] = None  # Cached after first successful connect


def get_supabase_client() -> Client:
    """
    Get or create a Supabase client instance.
    Uses singleton pattern for connection reuse.
    """
    global _supabase_client

    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SECRET_KEY")  # Use secret key for full access

        if not url:
            raise ValueError("SUPABASE_URL environment variable not set")
        if not key:
            raise ValueError("SUPABASE_SECRET_KEY environment variable not set")

        _supabase_client = create_client(url, key)

    return _supabase_client


def _candidate_db_urls() -> List[Tuple[str, str]]:
    """
    Return DB connection candidates in priority order:
      1. SUPABASE_DB_URL_DIRECT      — port 5432 to db.<ref>.supabase.co (best throughput)
      2. SUPABASE_DB_URL_TXN_POOLER  — port 6543 to db.<ref>.supabase.co (transaction pooler)
      3. SUPABASE_DB_URL_SESSION_POOLER — port 5432 to aws-*.pooler.supabase.com (most permissive networks)
      4. SUPABASE_DB_URL             — single-URL legacy fallback
    """
    candidates = []
    for name in (
        "SUPABASE_DB_URL_DIRECT",
        "SUPABASE_DB_URL_TXN_POOLER",
        "SUPABASE_DB_URL_SESSION_POOLER",
        "SUPABASE_DB_URL",
    ):
        url = os.getenv(name)
        if url:
            candidates.append((name, url))
    if not candidates:
        raise ValueError(
            "No Supabase DB URL configured. Set SUPABASE_DB_URL_DIRECT (or "
            "SUPABASE_DB_URL) in your .env file."
        )
    return candidates


def _try_connect(url: str, connect_timeout: int = 8):
    """Open a psycopg2 connection, raising on failure.

    Aggressive TCP keepalives so the OS detects dropped server→client packets
    quickly (within ~15s) instead of hanging forever. The Supabase session
    pooler in us-east-1 has been observed dropping response packets after a
    successful query → backend sits in ClientRead while client blocks in
    execute(). With these keepalives, the socket dies cleanly and the
    application can reconnect.
    """
    return psycopg2.connect(
        url,
        cursor_factory=RealDictCursor,
        connect_timeout=connect_timeout,
        keepalives=1,
        keepalives_idle=5,
        keepalives_interval=3,
        keepalives_count=3,
        # socket-level read timeout via libpq's tcp_user_timeout (Linux only,
        # ignored on Windows but harmless)
        tcp_user_timeout=20000,
    )


def get_db_connection(new_connection: bool = False):
    """
    Get a direct PostgreSQL connection for bulk operations.

    Tries DB URLs in priority order (direct → txn pooler → session pooler → legacy).
    The first URL that connects successfully is cached for subsequent calls so we
    don't re-probe on every connection.

    Args:
        new_connection: If True, create a new connection instead of reusing
    """
    global _db_connection, _chosen_db_url

    if not new_connection and _db_connection is not None and not _db_connection.closed:
        return _db_connection

    # If we've previously found a working URL, use it directly.
    if _chosen_db_url:
        try:
            conn = _try_connect(_chosen_db_url)
            conn.autocommit = False
            _db_connection = conn
            return conn
        except Exception:
            # Cached URL stopped working — fall through to re-probe.
            _chosen_db_url = None

    last_error: Optional[Exception] = None
    for name, url in _candidate_db_urls():
        try:
            conn = _try_connect(url)
            conn.autocommit = False
            _db_connection = conn
            _chosen_db_url = url
            # Log selection on stderr only on first probe to keep CLI output clean
            try:
                host = url.split("@", 1)[1].split("/", 1)[0]
                print(f"[supabase] Using DB connection: {name} ({host})", flush=True)
            except Exception:
                pass
            return conn
        except (psycopg2.OperationalError, socket.gaierror, OSError) as e:
            last_error = e
            print(f"[supabase] {name} unavailable: {e}", flush=True)
            continue

    raise ConnectionError(
        f"Unable to connect to Supabase Postgres via any configured URL. Last error: {last_error}"
    )


def close_connections():
    """Close all open connections."""
    global _supabase_client, _db_connection

    if _db_connection is not None and not _db_connection.closed:
        _db_connection.close()
        _db_connection = None

    _supabase_client = None

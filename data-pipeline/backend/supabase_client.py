"""
Supabase client initialization and connection management.
"""

import os
from pathlib import Path
from typing import Optional
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


def get_db_connection(new_connection: bool = False):
    """
    Get a direct PostgreSQL connection for bulk operations.

    Args:
        new_connection: If True, create a new connection instead of reusing

    Returns:
        psycopg2 connection object
    """
    global _db_connection

    if new_connection or _db_connection is None or _db_connection.closed:
        db_url = os.getenv("SUPABASE_DB_URL")

        if not db_url:
            raise ValueError("SUPABASE_DB_URL environment variable not set")

        _db_connection = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        _db_connection.autocommit = False

    return _db_connection


def close_connections():
    """Close all open connections."""
    global _supabase_client, _db_connection

    if _db_connection is not None and not _db_connection.closed:
        _db_connection.close()
        _db_connection = None

    _supabase_client = None

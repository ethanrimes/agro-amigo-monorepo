#!/usr/bin/env python3
"""
Migration runner for AgroAmigo data pipeline.

Executes SQL migration files in order and tracks which have been applied.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.supabase_client import get_db_connection


MIGRATIONS_DIR = Path(__file__).parent


def get_applied_migrations(cursor) -> set:
    """Get set of already applied migration names."""
    try:
        cursor.execute("""
            SELECT name FROM schema_migrations
        """)
        return {row['name'] for row in cursor.fetchall()}
    except Exception:
        # Table doesn't exist yet
        return set()


def create_migrations_table(cursor):
    """Create the schema_migrations tracking table if it doesn't exist."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) UNIQUE NOT NULL,
            executed_at TIMESTAMP DEFAULT NOW()
        )
    """)


def run_migration(cursor, migration_path: Path) -> bool:
    """
    Run a single migration file.

    Returns:
        True if successful, False otherwise
    """
    migration_name = migration_path.name

    print(f"  Running: {migration_name}")

    try:
        with open(migration_path, 'r') as f:
            sql = f.read()

        cursor.execute(sql)

        # Record migration as applied
        cursor.execute(
            "INSERT INTO schema_migrations (name) VALUES (%s)",
            (migration_name,)
        )

        print(f"  ✓ Completed: {migration_name}")
        return True

    except Exception as e:
        print(f"  ✗ Failed: {migration_name}")
        print(f"    Error: {e}")
        return False


def run_all_migrations():
    """Run all pending migrations."""
    print("=" * 60)
    print("AgroAmigo Data Pipeline - Migration Runner")
    print("=" * 60)

    # Get database connection
    try:
        conn = get_db_connection(new_connection=True)
        cursor = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        sys.exit(1)

    try:
        # Create migrations table
        create_migrations_table(cursor)
        conn.commit()

        # Get already applied migrations
        applied = get_applied_migrations(cursor)
        print(f"\nAlready applied: {len(applied)} migrations")

        # Find all migration files
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        print(f"Found: {len(migration_files)} migration files")

        # Filter pending migrations
        pending = [f for f in migration_files if f.name not in applied]
        print(f"Pending: {len(pending)} migrations\n")

        if not pending:
            print("No pending migrations.")
            return 0

        # Run pending migrations
        success_count = 0
        error_count = 0

        for migration_path in pending:
            if run_migration(cursor, migration_path):
                conn.commit()
                success_count += 1
            else:
                conn.rollback()
                error_count += 1
                # Stop on first error
                print("\nStopping due to migration error.")
                break

        print("\n" + "=" * 60)
        print(f"Migration Summary")
        print("=" * 60)
        print(f"  Successful: {success_count}")
        print(f"  Failed: {error_count}")

        return 0 if error_count == 0 else 1

    finally:
        cursor.close()
        conn.close()


def rollback_migration(migration_name: str):
    """
    Remove a migration from the tracking table.
    Note: This does NOT undo the SQL changes.
    """
    conn = get_db_connection(new_connection=True)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "DELETE FROM schema_migrations WHERE name = %s",
            (migration_name,)
        )
        conn.commit()
        print(f"Removed migration record: {migration_name}")
    finally:
        cursor.close()
        conn.close()


def list_migrations():
    """List all migrations and their status."""
    conn = get_db_connection(new_connection=True)
    cursor = conn.cursor()

    try:
        # Create table if needed
        create_migrations_table(cursor)
        conn.commit()

        # Get applied migrations
        cursor.execute("""
            SELECT name, executed_at FROM schema_migrations
            ORDER BY executed_at
        """)
        applied = {row['name']: row['executed_at'] for row in cursor.fetchall()}

        # List all migration files
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

        print("\nMigration Status:")
        print("-" * 60)

        for f in migration_files:
            if f.name in applied:
                executed = applied[f.name].strftime("%Y-%m-%d %H:%M:%S")
                print(f"  [✓] {f.name}")
                print(f"      Applied: {executed}")
            else:
                print(f"  [ ] {f.name}")
                print(f"      Pending")

        print("-" * 60)
        print(f"Total: {len(migration_files)}, Applied: {len(applied)}, Pending: {len(migration_files) - len(applied)}")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument('--list', action='store_true', help="List all migrations")
    parser.add_argument('--rollback', type=str, help="Remove migration from tracking (doesn't undo SQL)")

    args = parser.parse_args()

    if args.list:
        list_migrations()
    elif args.rollback:
        rollback_migration(args.rollback)
    else:
        sys.exit(run_all_migrations())

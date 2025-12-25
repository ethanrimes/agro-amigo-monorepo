#!/bin/bash
# dump_schema.sh - Dump database schema to CSV for Claude context
#
# Usage:
#   ./scripts/dump_schema.sh                    # Uses SUPABASE_DB_URL env var
#   ./scripts/dump_schema.sh <connection_url>   # Use custom connection URL
#
# Output: data-pipeline/schema_columns.csv

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE_DIR="$(dirname "$SCRIPT_DIR")"

# Get database URL
DB_URL="${1:-$SUPABASE_DB_URL}"

if [ -z "$DB_URL" ]; then
    echo "Error: No database URL provided."
    echo "Either set SUPABASE_DB_URL environment variable or pass URL as argument."
    echo ""
    echo "Usage:"
    echo "  export SUPABASE_DB_URL='postgresql://...'"
    echo "  ./scripts/dump_schema.sh"
    echo ""
    echo "  # Or pass directly:"
    echo "  ./scripts/dump_schema.sh 'postgresql://...'"
    exit 1
fi

OUTPUT_FILE="$PIPELINE_DIR/schema_columns.csv"

echo "=============================================="
echo "Dumping Database Schema"
echo "=============================================="
echo "Output: $OUTPUT_FILE"
echo ""

cd "$PIPELINE_DIR"

# Run the SQL script
psql "$DB_URL" -f "$SCRIPT_DIR/dump_schema.sql"

echo ""
echo "=============================================="
echo "Schema dumped to: $OUTPUT_FILE"
echo "=============================================="

# Show preview
if [ -f "$OUTPUT_FILE" ]; then
    echo ""
    echo "Preview (first 20 lines):"
    head -20 "$OUTPUT_FILE"
fi

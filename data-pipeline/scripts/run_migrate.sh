#!/bin/bash
# run_migrate.sh - Run database migrations with logging
#
# Usage:
#   ./scripts/run_migrate.sh          # Run all pending migrations
#   ./scripts/run_migrate.sh --list   # List migration status

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE_DIR="$(dirname "$SCRIPT_DIR")"
RUN_DIR="$PIPELINE_DIR/runs"

# Create timestamped run directory
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RUN_NAME="migrate_${TIMESTAMP}"
RUN_PATH="$RUN_DIR/$RUN_NAME"

mkdir -p "$RUN_PATH"

LOG_FILE="$RUN_PATH/migrate.log"

echo "=============================================="
echo "AgroAmigo Database Migration"
echo "=============================================="
echo "Run directory: $RUN_PATH"
echo "Log file: $LOG_FILE"
echo "Arguments: $@"
echo "=============================================="

# Save run metadata
cat > "$RUN_PATH/metadata.json" << EOF
{
  "run_name": "$RUN_NAME",
  "timestamp": "$TIMESTAMP",
  "command": "migrate",
  "arguments": "$@",
  "started_at": "$(date -Iseconds)"
}
EOF

cd "$PIPELINE_DIR"

# Run migrations
python -u -m cli.main migrate "$@" 2>&1 | tee "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

# Update metadata
python3 << EOF
import json
from datetime import datetime

with open("$RUN_PATH/metadata.json", "r") as f:
    meta = json.load(f)

meta["completed_at"] = datetime.now().isoformat()
meta["exit_code"] = $EXIT_CODE
meta["status"] = "success" if $EXIT_CODE == 0 else "failed"

with open("$RUN_PATH/metadata.json", "w") as f:
    json.dump(meta, f, indent=2)
EOF

echo ""
echo "=============================================="
echo "Migration completed with exit code: $EXIT_CODE"
echo "Logs saved to: $RUN_PATH"
echo "=============================================="

exit $EXIT_CODE

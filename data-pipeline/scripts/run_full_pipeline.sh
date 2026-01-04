#!/bin/bash
# run_full_pipeline.sh - Run full historical pipeline with logging
#
# Usage:
#   ./scripts/run_full_pipeline.sh --year 2024
#   ./scripts/run_full_pipeline.sh --start-date 2024-01-01 --end-date 2024-06-30
#   ./scripts/run_full_pipeline.sh --year 2024 --anexo-only

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE_DIR="$(dirname "$SCRIPT_DIR")"
RUN_DIR="$PIPELINE_DIR/runs"

# Create timestamped run directory
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RUN_NAME="full_pipeline_${TIMESTAMP}"
RUN_PATH="$RUN_DIR/$RUN_NAME"

mkdir -p "$RUN_PATH"

LOG_FILE="$RUN_PATH/pipeline.log"
ERROR_LOG="$RUN_PATH/errors.log"

echo "=============================================="
echo "AgroAmigo Full Pipeline Run"
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
  "command": "run-historical",
  "arguments": "$@",
  "started_at": "$(date -Iseconds)"
}
EOF

cd "$PIPELINE_DIR"

# Run the pipeline, tee output to both console and log
python -u -m cli.main run-historical "$@" 2>&1 | tee "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

# Extract errors to separate file
grep -i "error\|exception\|failed\|traceback" "$LOG_FILE" > "$ERROR_LOG" 2>/dev/null || true

# Update metadata with completion status
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
echo "Pipeline completed with exit code: $EXIT_CODE"
echo "Logs saved to: $RUN_PATH"
echo "=============================================="

exit $EXIT_CODE

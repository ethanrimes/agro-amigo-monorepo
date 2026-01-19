#!/bin/bash
# pipeline.sh - Unified pipeline runner with logging
#
# This single script replaces:
#   - run_scrape.sh
#   - run_full_pipeline.sh
#   - run_current.sh
#   - run_process.sh
#   - retry_errors.sh
#
# Usage:
#   ./scripts/pipeline.sh scrape-current                    # Scrape current month only
#   ./scripts/pipeline.sh scrape-historical --year 2024     # Scrape historical year
#   ./scripts/pipeline.sh scrape-all                        # Scrape all data
#   ./scripts/pipeline.sh run-current                       # Scrape + process current month
#   ./scripts/pipeline.sh run-historical --year 2024        # Scrape + process historical
#   ./scripts/pipeline.sh process                           # Process all pending
#   ./scripts/pipeline.sh retry-errors                      # Retry failed processing
#   ./scripts/pipeline.sh migrate                           # Run database migrations
#   ./scripts/pipeline.sh <any-cli-command> [options]       # Run any CLI command
#
# All commands support standard CLI options like --dry-run, --anexo-only, etc.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE_DIR="$(dirname "$SCRIPT_DIR")"
RUN_DIR="$PIPELINE_DIR/runs"

# Display usage if no arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  scrape-current      Scrape current month only"
    echo "  scrape-historical   Scrape historical data (use --year or --start-date/--end-date)"
    echo "  scrape-all          Scrape all data (current + historical from 2012)"
    echo "  run-current         Scrape + process current month"
    echo "  run-historical      Scrape + process historical data"
    echo "  process             Process all pending download entries"
    echo "  retry-errors        Retry failed processing"
    echo "  migrate             Run database migrations"
    echo ""
    echo "Options are passed through to the CLI command."
    echo "Run 'python -m cli.main <command> --help' for command-specific options."
    exit 1
fi

# Parse command
COMMAND="${1}"
shift

# Create command-specific run name
COMMAND_SHORT="${COMMAND//scrape-/s_}"  # Shorten scrape- to s_
COMMAND_SHORT="${COMMAND_SHORT//run-/r_}"  # Shorten run- to r_
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RUN_NAME="${COMMAND_SHORT}_${TIMESTAMP}"
RUN_PATH="$RUN_DIR/$RUN_NAME"

mkdir -p "$RUN_PATH"

LOG_FILE="$RUN_PATH/output.log"
ERROR_LOG="$RUN_PATH/errors.log"

echo "=============================================="
echo "AgroAmigo Pipeline: $COMMAND"
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
  "command": "$COMMAND",
  "arguments": "$@",
  "started_at": "$(date -Iseconds)"
}
EOF

cd "$PIPELINE_DIR"

# Run the CLI command
python -u -m cli.main "$COMMAND" "$@" 2>&1 | tee "$LOG_FILE"
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
echo "Completed with exit code: $EXIT_CODE"
echo "Logs saved to: $RUN_PATH"
echo "=============================================="

exit $EXIT_CODE

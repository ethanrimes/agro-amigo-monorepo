#!/usr/bin/env bash
# start-dev.sh — Kill any running Next.js dev servers, then launch a fresh one
#                and print the port it binds to.
#  & "C:\Program Files\Git\bin\bash.exe" .\agroamigo-web\start-dev.sh      

set -euo pipefail

cd "$(dirname "$0")"

# Kill any existing next-server / next dev processes.
# "taskkill" for Windows (Git Bash / MSYS2), "pkill" fallback for Unix.
echo "Stopping existing dev servers..."
if command -v taskkill &>/dev/null; then
  # Windows: kill node processes whose command line contains "next dev" or "next-server"
  tasklist //FI "IMAGENAME eq node.exe" //FO CSV 2>/dev/null \
    | tail -n +2 \
    | while IFS=, read -r name pid _rest; do
        pid=$(echo "$pid" | tr -d '"')
        # Check if this node process is a next dev server
        if wmic process where "ProcessId=$pid" get CommandLine 2>/dev/null \
             | grep -qiE 'next dev|next-server'; then
          echo "  Killing PID $pid"
          taskkill //PID "$pid" //F //T &>/dev/null || true
        fi
      done || true
else
  # Unix
  pkill -f 'next dev' 2>/dev/null || true
  pkill -f 'next-server' 2>/dev/null || true
fi

# Brief pause to let ports free up.
sleep 1
echo "Starting dev server..."
echo ""

# Start the dev server, parsing output to detect the port.
npx next dev 2>&1 | while IFS= read -r line; do
  echo "$line"
  # Next.js prints:  - Local:  http://localhost:<port>
  if echo "$line" | grep -qE 'Local:\s+http'; then
    port=$(echo "$line" | grep -oE ':[0-9]+' | tail -1 | tr -d ':')
    echo ""
    echo "================================================"
    echo "  Dev server is running on port: $port"
    echo "  URL: http://localhost:$port"
    echo "================================================"
  fi
done

#!/usr/bin/env bash
# start-tunnel-dev.sh — Launch a Cloudflare tunnel + Expo dev server for
#                      agroamigo-app in a single shell. Used for phones on
#                      a different network.
#
# The script always starts a FRESH Metro/Expo process on an unused port so it
# won't attach to another project's dev server you already have running
# (e.g. Minga Expeditions). It also clears Metro's project cache each run.
#
# Run in PowerShell:
#   & "C:\Program Files\Git\bin\bash.exe" .\agroamigo-app\start-tunnel-dev.sh
#   & "C:\Program Files\Git\bin\bash.exe" .\agroamigo-app\start-tunnel-dev.sh 8090
#
# Run in Git Bash:
#   ./agroamigo-app/start-tunnel-dev.sh             # auto-pick free port
#   ./agroamigo-app/start-tunnel-dev.sh 8090        # specific port
#   PORT=8090 ./agroamigo-app/start-tunnel-dev.sh   # env-var form

set -euo pipefail

cd "$(dirname "$0")"

# ---------- port selection --------------------------------------------------
is_port_free() {
  local p=$1
  if command -v ss >/dev/null 2>&1; then
    ! ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":$p$"
  elif command -v netstat >/dev/null 2>&1; then
    # Git Bash netstat lists ports as "0.0.0.0:8085" — match trailing :port.
    ! netstat -an 2>/dev/null | grep -E "LISTENING|LISTEN" | grep -q ":$p "
  else
    return 0
  fi
}

pick_free_port() {
  for p in $(seq 8085 8199); do
    if is_port_free "$p"; then
      echo "$p"
      return 0
    fi
  done
  echo "ERROR: no free port found in 8085..8199. Pass one explicitly." >&2
  exit 1
}

REQUESTED_PORT="${1:-${PORT:-}}"
if [[ -n "$REQUESTED_PORT" ]]; then
  if ! is_port_free "$REQUESTED_PORT"; then
    echo "ERROR: port $REQUESTED_PORT is already in use. Pick another or run without args to auto-pick." >&2
    exit 1
  fi
  PORT="$REQUESTED_PORT"
else
  PORT=$(pick_free_port)
fi

TUNNEL_LOG=$(mktemp -t cloudflared.XXXXXX)
TUNNEL_PID=""

cleanup() {
  echo ""
  echo "Shutting down tunnel (port $PORT)..."
  if [[ -n "$TUNNEL_PID" ]] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
    kill "$TUNNEL_PID" 2>/dev/null || true
    if command -v taskkill &>/dev/null; then
      taskkill //F //T //PID "$TUNNEL_PID" &>/dev/null || true
    fi
  fi
  rm -f "$TUNNEL_LOG"
}
trap cleanup EXIT INT TERM

# ---------- cloudflare tunnel ----------------------------------------------
echo "Starting Cloudflare tunnel on http://localhost:$PORT ..."
npx -y cloudflared tunnel --url "http://localhost:$PORT" >"$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

TUNNEL_URL=""
for _ in $(seq 1 60); do
  TUNNEL_URL=$(grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | head -1 || true)
  if [[ -n "$TUNNEL_URL" ]]; then
    break
  fi
  if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    echo "ERROR: cloudflared exited before a URL was produced." >&2
    cat "$TUNNEL_LOG" >&2
    exit 1
  fi
  sleep 0.5
done

if [[ -z "$TUNNEL_URL" ]]; then
  echo "ERROR: Tunnel URL not found after 30s. cloudflared log:" >&2
  cat "$TUNNEL_LOG" >&2
  exit 1
fi

echo ""
echo "================================================"
echo "  Project:      agroamigo-app"
echo "  Local port:   $PORT"
echo "  Tunnel URL:   $TUNNEL_URL"
echo "  Phone (Expo): exp://${TUNNEL_URL#https://}:443"
echo "================================================"
echo ""
echo "If Expo Go opens the wrong project, force-quit Expo Go and paste the"
echo "exp:// URL above from your phone's clipboard, or scan the QR code below."
echo ""

# ---------- expo start ------------------------------------------------------
# EXPO_PACKAGER_PROXY_URL makes Metro advertise the tunnel URL in its manifest
# so the phone loads the bundle through the tunnel instead of localhost.
export EXPO_PACKAGER_PROXY_URL="$TUNNEL_URL"
export EXPO_NO_DEV_CLIENT=1

# Flags:
#   --port  Metro listens here; matches the tunnel.
#   --clear wipe Metro cache (fixes "Unable to deserialize cloned data"
#           when cache was written by a different metro version).
#   --go    force the bundle to target Expo Go.
exec npx expo start --port "$PORT" --clear --go

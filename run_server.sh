#!/usr/bin/env bash
# SPEC-INFRA-001 REQ-INFRA-002 — idempotent first-run / restart path.
#
# Brings the Argus stack up in detached mode and blocks until
# `GET /health` returns 200 (model resident). Re-running on a healthy
# stack is a no-op: `docker compose up -d` reconciles state, then the
# /health poll returns immediately.
#
# Lives at project root (per CLAUDE.md "Planned architecture").
#
# Exit codes:
#   0  stack is healthy
#   1  Docker daemon unavailable
#   2  configured port already in use on the host
#   3  /health did not return 200 within ARGUS_HEALTH_TIMEOUT seconds

set -euo pipefail

# Resolve project root regardless of caller CWD. Script lives at project root,
# so dirname of BASH_SOURCE is already the project root.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Pre-flight: Docker daemon reachable.
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon not running or 'docker' CLI not available." >&2
  echo "Start Docker Desktop (macOS/Windows) or 'sudo systemctl start docker' (Linux), then retry." >&2
  exit 1
fi

API_PORT="${API_PORT:-8000}"
HEALTH_URL="http://127.0.0.1:${API_PORT}/health"
TIMEOUT_SECONDS="${ARGUS_HEALTH_TIMEOUT:-600}"

# Pre-flight: host port available (best-effort; lsof may not be installed).
if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:"${API_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "ERROR: Port ${API_PORT} is already in use on this host." >&2
    echo "Either free the port, or override with API_PORT=<other>: API_PORT=8001 ./run_server.sh" >&2
    exit 2
  fi
fi

echo "Starting Argus stack (model + api) via docker compose..."
docker compose up -d

echo "Polling ${HEALTH_URL} (timeout ${TIMEOUT_SECONDS}s)..."
ELAPSED=0
STEP=2
LAST_PROGRESS=0
while [ "${ELAPSED}" -lt "${TIMEOUT_SECONDS}" ]; do
  if curl -sf -o /dev/null "${HEALTH_URL}" 2>/dev/null; then
    echo "Stack ready. /health returned 200 after ${ELAPSED}s."
    exit 0
  fi
  if [ $((ELAPSED - LAST_PROGRESS)) -ge 30 ]; then
    echo "  ... still waiting (${ELAPSED}s elapsed; model may still be downloading)"
    LAST_PROGRESS=${ELAPSED}
  fi
  sleep ${STEP}
  ELAPSED=$((ELAPSED + STEP))
done

echo "ERROR: /health did not return 200 within ${TIMEOUT_SECONDS}s." >&2
echo "Inspect logs: docker compose logs" >&2
exit 3

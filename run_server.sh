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

# Pre-flight: Docker daemon reachable (auto-start if installed; instruct if absent).
# Logic lives in _docker_preflight.sh (sourced) so run_server.sh and run_debug.sh
# share the same policy. See CHANGELOG.md for design rationale.
# shellcheck source=_docker_preflight.sh
source "$PROJECT_ROOT/_docker_preflight.sh"
ensure_docker_ready

API_PORT="${API_PORT:-8000}"
HEALTH_URL="http://127.0.0.1:${API_PORT}/health"
TIMEOUT_SECONDS="${ARGUS_HEALTH_TIMEOUT:-600}"

# Stale-container detection (REQ-INFRA-002 Scenario 5 idempotency preserved):
# If Argus containers are running but /health is unreachable, the stack is
# stale — tear it down (named volume preserved, no model re-pull) so the
# subsequent `docker compose up -d` succeeds without name conflicts. If
# /health already responds 200, the stack is healthy — we skip the down
# entirely so the up below is a no-op and the /health poll exits
# immediately (Scenario 5: containers not recreated unnecessarily).
RUNNING_CONTAINERS="$(docker compose ps --status running --quiet 2>/dev/null | wc -l | tr -d ' ')"
if [ "${RUNNING_CONTAINERS}" -gt 0 ]; then
  if curl -sf -o /dev/null --max-time 3 "${HEALTH_URL}" 2>/dev/null; then
    echo "Argus stack is already healthy at ${HEALTH_URL}; skipping recreate."
  else
    echo "Detected ${RUNNING_CONTAINERS} stale Argus container(s); tearing down before fresh start."
    docker compose down --remove-orphans 2>/dev/null || true
  fi
fi

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

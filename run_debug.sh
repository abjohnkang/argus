#!/usr/bin/env bash
# SPEC-INFRA-001 REQ-INFRA-002 — foreground debug variant.
#
# Brings the Argus stack up in the foreground with verbose logging from
# both Ollama (OLLAMA_DEBUG=1) and uvicorn (LOG_LEVEL=debug) so logs
# stream to stdout. Ctrl+C tears the stack down. Use this for cold-start
# debugging, model-pull progress watching, and middleware trace work.
#
# Lives at project root (per CLAUDE.md "Planned architecture").
#
# Debug-mode quality-of-life additions (post-SPEC, documented in CHANGELOG):
#   1. Unconditional `docker compose down --remove-orphans` before `up` —
#      debug mode is "give me a predictable fresh stack each run". The
#      named volume argus_ollama_models is preserved (no --volumes flag),
#      so no model re-pull occurs. This intentionally departs from the
#      idempotency contract of run_server.sh (REQ-INFRA-002 Scenario 5),
#      because debug runs are short-lived and want clean container state.
#   2. Background browser-launcher: once `/health` returns 200, opens the
#      future-UI URL (http://127.0.0.1:${UI_PORT:-3000}/). The UI service
#      is NOT in v1's docker-compose.yml — that URL won't respond until
#      the follow-up React UI SPEC ships. Set NO_BROWSER=1 to skip.
#      Cross-platform: macOS `open`, Linux `xdg-open`, WSL `cmd.exe`.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon not running." >&2
  exit 1
fi

API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-3000}"
HEALTH_URL="http://127.0.0.1:${API_PORT}/health"
UI_URL="http://127.0.0.1:${UI_PORT}/"

# Tear down any previous Argus stack (debug mode = always fresh).
# --remove-orphans clears stale containers from earlier service definitions.
# Named volume argus_ollama_models is preserved (no --volumes flag) so the
# 32-67 GB model pull is NOT redone.
echo "Tearing down any previous Argus stack..."
docker compose down --remove-orphans 2>/dev/null || true

# Background browser-launcher: waits for /health = 200, then opens UI_URL.
# Self-terminates after ARGUS_HEALTH_TIMEOUT seconds (default 600). Runs
# in a subshell that survives the exec below; it will exit on its own
# once it opens the browser or hits the timeout.
launch_browser_when_ready() {
  if [ "${NO_BROWSER:-0}" = "1" ]; then
    return 0
  fi
  local timeout="${ARGUS_HEALTH_TIMEOUT:-600}"
  local elapsed=0
  while [ "${elapsed}" -lt "${timeout}" ]; do
    if curl -sf -o /dev/null "${HEALTH_URL}" 2>/dev/null; then
      echo "[browser] API ready at ${HEALTH_URL}; opening ${UI_URL}"
      echo "[browser] Note: UI service is deferred to a follow-up SPEC; URL may not yet respond."
      if command -v open >/dev/null 2>&1; then
        open "${UI_URL}" 2>/dev/null || true
      elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "${UI_URL}" >/dev/null 2>&1 || true
      elif command -v cmd.exe >/dev/null 2>&1; then
        cmd.exe /C start "" "${UI_URL}" 2>/dev/null || true
      else
        echo "[browser] No browser launcher detected on PATH. Open ${UI_URL} manually." >&2
      fi
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  echo "[browser] /health did not return 200 within ${timeout}s; browser open skipped." >&2
}

(launch_browser_when_ready) &

export OLLAMA_DEBUG=1
export LOG_LEVEL=debug

echo "Starting Argus stack in foreground (debug mode). Ctrl+C to stop."
exec docker compose up

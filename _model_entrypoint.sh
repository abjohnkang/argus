#!/bin/sh
# SPEC-INFRA-001 — model service entrypoint.
#
# Runs INSIDE the `model` container (bind-mounted via docker-compose.yml).
# Wraps the upstream ollama/ollama image so that the configured MODEL is
# pulled into the volume on first run, then `ollama serve` takes over.
#
# Why this exists: the stock ollama/ollama image runs `ollama serve` only.
# It does NOT auto-pull models. Without this wrapper, /api/tags returns
# an empty list forever, OllamaAdapter.is_ready() never flips true, and
# the api service's /health stays at 503 indefinitely.
#
# Idempotency: re-runs skip the pull if the model is already present in
# the argus_ollama_models named volume.
#
# Env vars:
#   MODEL                  - Ollama model tag to pull (default: llama4:scout)
#   ARGUS_OLLAMA_BOOT_WAIT - seconds to wait for `ollama serve` ready (default: 60)
#
# This script is `sh`-compatible (not bash-only): the upstream ollama
# image is debian-slim and has /bin/sh.

set -eu

MODEL_TAG="${MODEL:-llama4:scout}"
BOOT_WAIT="${ARGUS_OLLAMA_BOOT_WAIT:-60}"

echo "[model-entrypoint] Starting ollama serve in background..."
ollama serve &
SERVE_PID=$!

# Wait for the daemon to accept connections. `ollama list` is cheap and
# exits 0 once the daemon is ready.
ELAPSED=0
while ! ollama list >/dev/null 2>&1; do
  if [ "$ELAPSED" -ge "$BOOT_WAIT" ]; then
    echo "[model-entrypoint] ERROR: ollama serve did not respond within ${BOOT_WAIT}s." >&2
    kill "$SERVE_PID" 2>/dev/null || true
    exit 1
  fi
  sleep 1
  ELAPSED=$((ELAPSED + 1))
done
echo "[model-entrypoint] ollama serve ready (${ELAPSED}s)."

# Pull the configured model if not already cached in the volume.
# `ollama list` output format (skip header row):
#   NAME                  ID              SIZE      MODIFIED
#   llama3.2:1b           abc123def456    1.3 GB    2 hours ago
if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$MODEL_TAG"; then
  echo "[model-entrypoint] Model '$MODEL_TAG' already present in volume cache; skipping pull."
else
  echo "[model-entrypoint] Pulling model: $MODEL_TAG"
  echo "[model-entrypoint] (first-run for this tag; subsequent invocations will skip this)"
  if ! ollama pull "$MODEL_TAG"; then
    echo "[model-entrypoint] ERROR: ollama pull '$MODEL_TAG' failed." >&2
    echo "[model-entrypoint] Common causes: tag does not exist, network unreachable," >&2
    echo "[model-entrypoint] insufficient disk space in the argus_ollama_models volume." >&2
    kill "$SERVE_PID" 2>/dev/null || true
    exit 1
  fi
  echo "[model-entrypoint] Pull complete. Model '$MODEL_TAG' is now resident."
fi

# Hand foreground control back to ollama serve. The api service will now
# see the model in /api/tags and /health will flip to 200 {"status":"ready"}.
echo "[model-entrypoint] Handing control to ollama serve (PID $SERVE_PID)..."
wait "$SERVE_PID"

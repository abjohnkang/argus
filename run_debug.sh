#!/usr/bin/env bash
# SPEC-INFRA-001 REQ-INFRA-002 — foreground debug variant.
#
# Brings the Argus stack up in the foreground with verbose logging from
# both Ollama (OLLAMA_DEBUG=1) and uvicorn (LOG_LEVEL=debug) so logs
# stream to stdout. Ctrl+C tears the stack down. Use this for cold-start
# debugging, model-pull progress watching, and middleware trace work.
#
# Lives at project root (per CLAUDE.md "Planned architecture").

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon not running." >&2
  exit 1
fi

export OLLAMA_DEBUG=1
export LOG_LEVEL=debug

echo "Starting Argus stack in foreground (debug mode). Ctrl+C to stop."
exec docker compose up

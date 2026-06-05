# Argus — Project Structure

This document describes the directory layout for Argus as it exists after SPEC-INFRA-001 (runtime foundation).

---

## Current Repository Contents

```
argus/
├── README.md               Public project summary (quick start, API, security model)
├── CONCEPT.md              Vision, non-goals, open questions
├── CHANGELOG.md            Keep-a-Changelog format (created in SPEC-INFRA-001 sync)
├── CLAUDE.md               MoAI execution directives and project rules
├── LICENSE                 Apache-2.0
├── pyproject.toml          Python project config (build, deps, test, lint tooling)
├── docker-compose.yml      Two-service Compose stack (model + api)
├── run_server.sh           Idempotent first-run + health-gated startup [project root]
├── run_debug.sh            Foreground variant with debug logging [project root]
├── .env.example            MODEL, API_PORT, OLLAMA_HOST documented
├── .dockerignore           Excludes .moai/, .claude/, *.md, .venv/ etc. from build context
├── .gitignore
├── .mcp.json               MCP server configuration
├── api/                    FastAPI service (see below)
├── tests/integration/      Docker-dependent integration tests (see below)
├── .moai/                  MoAI scaffolding (config, specs, project docs)
└── .claude/                Claude Code agent definitions, rules, and skills
```

---

## `api/` — FastAPI Service

Python 3.12 backend. The only service exposed to the host. Talks to the Ollama
`model` container over the internal Docker network.

```
api/
├── __init__.py
├── main.py             App factory, middleware registration, lifespan readiness poller
├── inference.py        OllamaAdapter — @MX:ANCHOR runtime swap boundary
├── security.py         LocalhostOnlyMiddleware (pure header-validation functions)
├── state.py            ReadinessTracker (async-lock-protected LOADING → READY state machine)
├── requirements.txt    Pinned runtime deps (fastapi, uvicorn, httpx, pydantic)
├── Dockerfile          Python 3.12-slim image; runs uvicorn bound to 127.0.0.1:8000
└── tests/              Unit tests (hermetic via respx; no Docker required)
    ├── __init__.py
    ├── test_main.py
    ├── test_inference.py
    ├── test_security.py
    └── test_state.py
```

### Architectural pattern: API-in-front-of-runtime

`api/inference.py::OllamaAdapter` is the **single invariant contract** between Argus and the
model runtime. The `@MX:ANCHOR` tag marks it as a high-fan_in boundary that must not be changed
without updating all callers. Future runtime swaps (llama.cpp, vLLM) become configuration changes
inside `inference.py`, not rewrites of every downstream consumer. The React UI (future SPEC) will
only ever talk to the FastAPI routes — never to Ollama directly.

### State machine: `/health` endpoint

Three internal states tracked by `ReadinessTracker`:
- `LOADING` — initial state; `/health` returns `503 {"status":"loading"}`
- `READY` — background poller confirmed Ollama has the model resident; `/health` returns `200 {"status":"ready"}`

Transitions are idempotent and protected by an async lock. The `@MX:NOTE` tag on the state machine
in `main.py` documents the `loading → ready` contract so future contributors do not collapse it into
a simpler boolean check.

### Defense in depth: localhost-only

Two independent layers enforce the localhost-only constraint:

1. **Docker port mapping** — `docker-compose.yml` uses `127.0.0.1:${API_PORT:-8000}:8000`.
   The kernel never accepts a non-loopback TCP connection to this port.
2. **`LocalhostOnlyMiddleware`** — reads `Host` and `Origin` headers on every request and rejects
   anything not matching `127.0.0.1`, `localhost`, or `[::1]` with `403 Forbidden`.
   Defends against DNS rebinding and misconfigured reverse proxies even if the bind is bypassed.

---

## `tests/integration/` — Docker-Dependent Integration Tests

```
tests/
└── integration/
    ├── __init__.py
    ├── conftest.py         Docker availability check; skips all tests without running Docker
    ├── test_docker_stack.py  Stack bring-up, health transition, Edge Case 2 (port in use)
    └── test_api_endpoints.py  End-to-end endpoint assertions against real Ollama
```

Tests in this directory are marked `@pytest.mark.integration`. They require Docker + a running
Ollama instance. On CI without Docker they collect cleanly and skip. The test fixture pulls
`llama3.2:1b` (~1 GB) to avoid the 32–67 GB Scout download in CI.

---

## Project Root Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Two-service stack: `model` (Ollama, internal only) + `api` (FastAPI, 127.0.0.1 host bind) |
| `run_server.sh` | `docker compose up -d`, then poll `/health` until `200` or timeout. Idempotent re-runs are no-ops. |
| `run_debug.sh` | `docker compose up` (foreground, no `-d`) with `OLLAMA_DEBUG=1` and API `debug` log level |
| `.env.example` | Documented env vars: `MODEL` (default `llama4:scout`), `API_PORT` (default `8000`), `OLLAMA_HOST` (internal) |
| `.dockerignore` | Keeps image build fast: excludes `.git/`, `.moai/`, `.claude/`, `*.md`, `__pycache__/`, `.venv/`, `run_*.sh` |
| `pyproject.toml` | Build system, deps, pytest config, coverage gate (≥85%), ruff/black/isort settings |

---

## Named Docker Volume

`argus_ollama_models` — mounted at `/root/.ollama` in the `model` service. Preserves the
32–67 GB Llama 4 Scout weights across `docker compose down`. Only deleted by explicit
`docker volume rm argus_ollama_models` or `docker compose down --volumes`.

---

## Planned Directories (not yet created)

| Directory | Status | Notes |
|---|---|---|
| `web/` | Planned | React frontend (separate SPEC) |
| `docs/` | Optional | User-facing docs beyond README; may stay README-only |

---

## `.moai/` — MoAI Scaffolding

Contains:
- `config/` — Project configuration (quality, language, user, design settings)
- `specs/` — SPEC documents (SPEC-INFRA-001 complete; future SPECs TBD)
- `project/` — Living project documentation (`product.md`, `structure.md`, `tech.md`)
- `backups/` — Pre-modification snapshots created during `/moai sync`
- `reports/` — Sync reports created during `/moai sync`

## `.claude/` — Claude Code Configuration

Agent definitions, rules, skills, and hooks used by MoAI-ADK during development.

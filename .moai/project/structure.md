# Argus — Project Structure

This document describes the directory layout for Argus as it exists after SPEC-UI-001 (React chat UI, completing the first-milestone vertical slice).

---

## Current Repository Contents

```
argus/
├── README.md               Public project summary (quick start, browser UI, API, security model)
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
├── web/                    React SPA source (see below)
├── api/                    FastAPI service (see below)
├── tests/integration/      Docker-dependent integration tests (see below)
├── .moai/                  MoAI scaffolding (config, specs, project docs)
└── .claude/                Claude Code agent definitions, rules, and skills
```

---

## `web/` — React SPA

TypeScript single-page application built with Vite 5. Source lives in `web/`; the Vite build
produces `web/dist/`, which is folded into the `api` Docker image at build time and served
via `StaticFiles` at `/`. No Node runtime is present in production.

```
web/
├── package.json            React 18, Vite 5, TypeScript, Tailwind 3.4, react-markdown, Vitest
├── tsconfig.json           TypeScript config
├── vite.config.ts          base: '/'; dev-proxy: /v1 + /health → http://127.0.0.1:8000
├── tailwind.config.ts      Neutral ChatGPT-like theme; semantic CSS-variable brand seam
├── postcss.config.js       Tailwind + autoprefixer pipeline
├── index.html              SPA entry; CSP meta default-src 'self'
└── src/
    ├── main.tsx            React root mount
    ├── App.tsx             Top-level single-column chat layout
    ├── index.css           Tailwind directives + self-hosted fonts + highlight.js theme
    ├── lib/
    │   ├── sseClient.ts    @MX:ANCHOR — SSE over fetch+ReadableStream; chunk-boundary buffering; AbortController
    │   ├── health.ts       /health readiness polling (503 loading → 200 ready)
    │   └── useChat.ts      React hook wiring sseClient + health + state
    └── components/
        ├── ChatView.tsx
        ├── MessageList.tsx
        ├── MessageBubble.tsx
        ├── Composer.tsx
        ├── StopButton.tsx
        ├── LoadingState.tsx
        └── ModelBadge.tsx
```

### Key architectural decisions

- **Same-origin serving:** The SPA is served from the `api` origin (`127.0.0.1:8000`) via
  `StaticFiles`. Same-origin requests carry `Host: 127.0.0.1:8000`, which passes
  `LocalhostOnlyMiddleware` cleanly — no CORS configuration needed and no weakening of the
  localhost-only threat model.
- **`fetch()` + `ReadableStream` over `EventSource`:** The browser's native `EventSource` cannot
  POST a JSON body. The SSE stream is consumed via `fetch()` with `response.body.getReader()`,
  manual `\n\n`-delimited frame splitting, and `AbortController`-based Stop support.
- **Ollama-native frame shape:** Token text is at `message.content` (not OpenAI
  `choices[].delta`). The `@MX:ANCHOR` on `sseClient.ts` marks this as the single point
  where the wire format is parsed.
- **Multi-stage Dockerfile:** `api/Dockerfile` has a `node:20-slim` build stage that runs
  `npm ci && npm run build`; the resulting `web/dist` is copied into the `python:3.12-slim`
  runtime stage. No Node runtime is present in the final image.

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
├── Dockerfile          Multi-stage: node:20-slim builds web/dist; python:3.12-slim serves API + static assets
└── tests/              Unit tests (hermetic via respx; no Docker required)
    ├── __init__.py
    ├── test_main.py
    ├── test_inference.py
    ├── test_security.py
    ├── test_state.py
    └── test_static_spa.py  SPA mount, API precedence, graceful-absence-of-web-dist (14 tests, SPEC-UI-001)
```

### Static SPA serving (added in SPEC-UI-001)

`api/main.py` mounts `StaticFiles(directory="web/dist", html=True)` at `/`, registered AFTER
the `/health`, `/v1/models`, and `/v1/chat/completions` routes. Mount ordering ensures API routes
take precedence; the SPA catch-all serves everything else. The mount is guarded to be a no-op
when `web/dist` is absent (development without a built bundle). The `@MX:NOTE` on the mount
documents the ordering invariant — do not reorder, do not add CORS.

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

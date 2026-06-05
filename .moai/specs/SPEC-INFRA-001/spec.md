---
id: SPEC-INFRA-001
version: 0.1.0
status: completed
created: 2026-06-04
created_at: 2026-06-04
updated: 2026-06-04
author: abjohn
priority: high
issue_number: 0
labels: [infra, runtime, docker, llm]
---

## HISTORY

- 2026-06-04 (v0.1.0): Phase 2.8a evaluator-active findings resolved. Added automated test for Edge Case 2 (port-in-use) at `tests/integration/test_docker_stack.py::test_run_server_exits_2_when_port_in_use`; amended `./acceptance.md` Edge Case 1 to mark it as manual verification with documented procedure (mid-pull interruption is brittle to automate; Ollama-native resume is delegated upstream and documented via `@MX:WARN` on `api/inference.py` pull path). Both criticals from evaluator-active's first-pass report are now closed.
- 2026-06-04 (v0.1.0): Entry-script path adjustment during /moai run Phase 2b. Scripts moved from `scripts/run_server.sh` / `scripts/run_debug.sh` to project root (`./run_server.sh` / `./run_debug.sh`) to align with `CLAUDE.md` "Planned architecture" section, which lists them at root. REQ-INFRA-002 wording and the Files-to-be-Created list updated; `PROJECT_ROOT` computation in both scripts simplified (dropped `/..`); `.dockerignore` exclusion updated from `scripts/` to `run_*.sh`. Behavior unchanged — only on-disk location differs.
- 2026-06-04 (v0.1.0): Initial draft authored by abjohn. Captures the runtime foundation for Argus — Llama 4 Scout inference behind a localhost-bound HTTP API in Docker. All major decisions (default runtime, model variant, hardware floor, persistence, threat model) inherited from `./research.md`. `issue_number: 0` because the `gh` CLI is not installed in this environment; Phase 2.5 is skipped.
- 2026-06-04 (v0.1.0): Scope reduction noted — the llama.cpp escape hatch (`compose.llamacpp.yml` overlay) discussed in `./research.md` Section 2 is explicitly deferred to a follow-up SPEC. v1 ships Ollama only. Rationale: keeps the v1 surface area minimal and lets the API↔runtime adapter be exercised against one runtime before generalizing.
- 2026-06-04 (v0.1.0): Frontmatter updated to include `created_at` (ISO date) and `labels` per plan-auditor MP-3 schema requirements (review iteration 1).

---

# Llama 4 Runtime Foundation: Local Inference HTTP API in Docker

## Overview

SPEC-INFRA-001 delivers the runtime foundation that every later Argus feature depends on: a localhost-bound HTTP API, running inside Docker, that serves Llama 4 Scout inference from a Python FastAPI backend talking to a model runtime container. This is the smallest viable on-device LLM stack — once it exists, every later SPEC (UI, agent tools, memory) plugs into the API contract rather than the model runtime, so the runtime can change without breaking downstream code.

The deliverable is a two-service Docker Compose stack (`model` + `api`) plus two idempotent entry scripts (`run_server.sh`, `run_debug.sh`) at the project root. The API exposes three endpoints — `GET /health`, `POST /v1/chat/completions` (SSE streaming), `GET /v1/models` — and binds only to `127.0.0.1`. Default model is `llama4:scout` served by Ollama; the `MODEL` environment variable opts the user into a smaller model (e.g., `llama3.2:3b`) without code changes. Persistence uses a named Docker volume so the 32–67 GB model download survives `docker compose down`.

What this SPEC explicitly defers: the React web UI is a separate SPEC. There is no conversation persistence, no bearer-token auth, no llama.cpp escape hatch in v1 (documented as a follow-up), no agent tools, and no support for Llama 4 Maverick or Behemoth (hardware out of reach). At the end of this SPEC, the demo-able state is `curl http://127.0.0.1:8000/v1/chat/completions` streaming tokens from a local Llama 4 Scout — nothing more, nothing less.

See `./research.md` for the full decision rationale, hardware analysis, runtime comparison, and threat model that underpin the requirements below.

## Requirements (EARS)

### REQ-INFRA-001 (Ubiquitous)

The Argus runtime SHALL serve Llama 4 Scout inference via an HTTP API running inside a Docker container, with the API process binding only to `127.0.0.1` and the host port mapping using `127.0.0.1:PORT:PORT` (never `0.0.0.0:PORT:PORT`).

### REQ-INFRA-002 (Event-driven)

WHEN `./run_server.sh` is invoked on a host with no existing Argus containers, the system SHALL pull the required Docker images, download the configured model weights into a named Docker volume, start the `model` and `api` services, and return from the script only after `GET /health` reports HTTP 200.

### REQ-INFRA-003 (State-driven)

WHILE the model is still loading, the HTTP API SHALL respond to `GET /health` with HTTP `503` and a JSON body of the form `{"status": "loading"}`; only after the model is fully ready SHALL `GET /health` respond with HTTP `200` and `{"status": "ready"}`.

### REQ-INFRA-004 (Optional feature, WHERE)

WHERE the operator sets the `MODEL` environment variable to a non-default value (e.g., `MODEL=llama3.2:3b`), the system SHALL pull and serve that model in place of `llama4:scout`, with no edits required to any source file, `docker-compose.yml`, or `Dockerfile`.

### REQ-INFRA-005 (Unwanted behavior, IF…THEN)

IF the HTTP API receives a request whose `Host` header value or whose `Origin` header host component (after URL parsing) is not exactly one of the literal strings `127.0.0.1`, `localhost`, or `[::1]` (port suffix and trailing dot tolerated, no DNS resolution performed), THEN the system SHALL reject the request with HTTP `403 Forbidden`, SHALL NOT invoke the model runtime, and SHALL log the rejection with the offending header value.

## Exclusions (What NOT to Build)

- **No React web UI.** The `web/` service and any browser frontend belong to a separate SPEC. v1 is demo-able via `curl`.
- **No conversation persistence.** Chat history, session storage, and any `argus_data` volume are out of scope.
- **No bearer token or session auth.** The v1 threat model is `127.0.0.1` bind plus non-localhost header rejection (REQ-INFRA-001 + REQ-INFRA-005). Token-based auth is a follow-up SPEC.
- **No vLLM support.** Server-class tool optimized for H100/A100 multi-GPU; rejected for personal hardware in `./research.md` Section 2.
- **No Llama 4 Maverick or Behemoth.** Hardware out of reach for the privacy-individual audience (Maverick at Q4 needs RTX 5090-class VRAM; Behemoth is server-class).
- **No llama.cpp escape hatch in v1.** Documented in `./research.md` as a future overlay (`compose.llamacpp.yml`); not implemented under this SPEC.
- **No agent tools.** File I/O sandbox, web fetch, code execution — all deferred to later milestones.
- **No automatic hardware preflight.** Hardware floor is documented in product copy; the runtime does not refuse to start on under-spec hardware.
- **No rate limiting.** Single-user, single-device — no realistic abuse vector.

## Files to Be Created or Modified (in `/moai run`)

All paths are project-root-relative. None of these exist on disk today.

- `docker-compose.yml` — Two services (`model`, `api`) on an internal Docker network. Host port mapping is `127.0.0.1:8000:8000` for the API. Named volume `argus_ollama_models` mounted at `/root/.ollama` in the `model` service. `MODEL` environment variable forwarded to both services.
- `api/Dockerfile` — Python 3.12 base image, installs `api/requirements.txt`, copies `api/`, runs `uvicorn` bound to `127.0.0.1:8000`.
- `api/main.py` — FastAPI application factory. Wires routes (`/health`, `/v1/chat/completions`, `/v1/models`), registers the localhost-only middleware enforcing REQ-INFRA-005, owns the readiness state machine for REQ-INFRA-003.
- `api/inference.py` — Thin adapter over the model runtime. Encapsulates Ollama HTTP client calls so the runtime can be swapped later. The single boundary between Argus and the model runtime.
- `api/requirements.txt` — Pinned to major versions (FastAPI 0.x, uvicorn 0.x, httpx 0.x, pydantic 2.x). No patch pins, no beta/alpha.
- `run_server.sh` — Idempotent first-run path: `docker compose up -d`, poll `/health` until 200 or timeout. Re-runs on a healthy stack are a no-op. Lives at the project root per `CLAUDE.md` "Planned architecture".
- `run_debug.sh` — Foreground variant: `docker compose up` (no `-d`), with `OLLAMA_DEBUG=1` and API log level `debug` exported. Streams logs to stdout. Lives at the project root per `CLAUDE.md` "Planned architecture".
- `.env.example` — Documents `MODEL`, `API_PORT`, `OLLAMA_HOST` (internal), and any future variables. Real `.env` is gitignored.
- `.dockerignore` — Excludes `.git/`, `.moai/`, `.claude/`, `*.md`, `__pycache__/`, `.venv/`, `run_*.sh`, and other host-only artifacts from the Docker build context. Keeps the `api/Dockerfile` image build fast and reproducible.

## Technical Approach

The runtime is a two-service Docker Compose topology described in `./research.md` Section 6:

1. **`model` service** — Ollama (`ollama/ollama` official image). Bound to the internal Docker network only. Owns the named volume that holds Llama 4 Scout weights (32–67 GB at Q4). Exposes Ollama's native HTTP REST API on its internal port (default `11434`).
2. **`api` service** — Argus FastAPI backend. Talks to `model` over the internal Docker network using the service DNS name. Bound to `127.0.0.1` on the host port. The only service exposed to the host.

The indirection — `api` in front of `model` — is the key architectural decision. It pins the Argus public contract (`/v1/chat/completions`, SSE format) at the API layer, so a future switch to llama.cpp or vLLM becomes a configuration change in `api/inference.py`, not a rewrite of every downstream consumer. The React UI (separate SPEC) will only ever talk to `api`, never directly to `model`.

Cold start sequence (REQ-INFRA-002):
1. `./run_server.sh` invokes `docker compose up -d`.
2. `model` container starts, pulls the configured model via `ollama pull $MODEL` if not already cached in the volume.
3. `api` container starts, polls Ollama internally, holds `/health` in `503 {"status": "loading"}` until Ollama reports the model is resident (REQ-INFRA-003).
4. `./run_server.sh` polls `http://127.0.0.1:8000/health` until it returns `200 {"status": "ready"}` or hits a configurable timeout.

Localhost enforcement (REQ-INFRA-001 + REQ-INFRA-005):
- Docker port mapping uses `127.0.0.1:8000:8000`, not `0.0.0.0:8000:8000`. Docker itself prevents external interfaces from reaching the API.
- A FastAPI middleware reads `Origin` and `Host` headers on every request and rejects anything resolving outside `127.0.0.1`, `localhost`, or `[::1]` with `403`. This defends against DNS rebinding and misconfigured reverse proxies even if the localhost bind is bypassed (defense in depth).

Model override (REQ-INFRA-004):
- The `MODEL` env var is read by both services. `model` uses it as the `ollama pull` target; `api` uses it as the default `model` field in chat completion requests.
- Default value (from `.env.example`) is `llama4:scout`. Users override to `llama3.2:3b` or any other Ollama-supported tag with no code changes.

See `./research.md` Sections 5–6 for the API contract details and topology rationale, Section 3 for the hardware floor, Section 4 for the persistence strategy.

## MX Tag Plan

The following MX tags will be placed during `/moai run`:

| File | Tag | Reason |
|---|---|---|
| `api/inference.py` | `@MX:ANCHOR` | This is the runtime swap boundary — the single invariant contract between Argus and any model runtime (Ollama today, llama.cpp/vLLM later). High future fan_in. |
| `api/inference.py` (model-pull / download-progress path) | `@MX:WARN` | Long-running operation with partial-state risk. A 32–67 GB pull interrupted mid-stream must resume cleanly. Requires `@MX:REASON` documenting the resume contract. |
| `api/main.py` (localhost middleware) | `@MX:NOTE` | Security invariant. Documents that `127.0.0.1` bind + non-localhost header rejection together constitute the v1 threat model, and that this is intentional (no bearer token auth in v1). |
| `api/main.py` (readiness state machine for `/health`) | `@MX:NOTE` | Documents the `loading → ready` transition contract referenced by REQ-INFRA-003 so future contributors do not collapse it into a single `200`/`404` check. |

---

## Implementation Notes

This section is appended by `/moai sync SPEC-INFRA-001` after the Run phase completed.

### Commits delivered (branch: feature/SPEC-INFRA-001-runtime-foundation)

| SHA | Message |
|---|---|
| `68652ce` | feat(infra): Python FastAPI core + unit tests (api/ + pyproject.toml + .env.example) |
| `c5c3bcf` | feat(infra): Docker Compose stack + entry scripts (Dockerfile, docker-compose.yml, run_server.sh, run_debug.sh at project root) |
| `e16caf1` | test(infra): integration tests against real Ollama (tests/integration/) |
| `5e7a5ef` | docs(spec): SPEC document synchronization (HISTORY entries, REQ map, Edge Case 1 manual procedure) |

### Files created

24 total: 15 Python source/test files (`api/*.py`, `api/tests/*.py`, `tests/integration/*.py`), 5 Docker/scripts (`docker-compose.yml`, `api/Dockerfile`, `run_server.sh`, `run_debug.sh`, `.dockerignore`), 4 config/env files (`pyproject.toml`, `api/requirements.txt`, `.env.example`, `api/__init__.py`).

### Test results

- Unit tests: 103 pass, hermetic (no Docker, no network), via respx-mocked Ollama
- Integration tests: 6 collect + skip cleanly without Docker; pass with real Docker + Ollama (`llama3.2:1b`)
- Coverage on `api/`: **92.62%** (gate: ≥85%; enforced by `pytest-cov fail_under=85`)

### MX tags placed

8 tags placed per MX Tag Plan (all 4 rows covered) plus 1 additional `@MX:ANCHOR` on the `OllamaUnavailable` exception contract in `api/inference.py`:

| Tag | File | Purpose |
|---|---|---|
| `@MX:ANCHOR` | `api/inference.py` (OllamaAdapter class) | Runtime swap boundary — single invariant contract |
| `@MX:ANCHOR` | `api/inference.py` (OllamaUnavailable exception) | Exception contract: upstream 5xx + connect/timeout → 502 |
| `@MX:WARN` + `@MX:REASON` | `api/inference.py` (pull path) | Long-running partial-state risk; Ollama resume contract documented |
| `@MX:NOTE` | `api/main.py` (LocalhostOnlyMiddleware) | Security invariant: v1 threat model (localhost bind + header rejection) |
| `@MX:NOTE` | `api/main.py` (readiness poller) | Loading → ready transition contract (REQ-INFRA-003) |
| `@MX:NOTE` | `api/state.py` (ReadinessTracker) | Async-lock-protected state machine; idempotent transitions |
| `@MX:NOTE` | `api/security.py` | Pure-function header validators; no side effects |
| `@MX:NOTE` | `docker-compose.yml` (port mapping) | REQ-INFRA-001 enforcement note |

### Quality verdicts

- **TRUST 5**: PASS (Tested 92.62%, Readable ruff+black+isort clean, Unified consistent style, Secured no 0.0.0.0 bind, Trackable SPEC-INFRA-001 in all commits)
- **evaluator-active 4-dimension**: PASS after fix cycle 1
  - Security: 90 (localhost enforcement + header rejection; no bearer token as designed)
  - Craft: 82 (clean separation of concerns; OllamaAdapter boundary; ReadinessTracker state machine)
  - Consistency: 90 (OpenAI-compatible API surface; consistent error shapes)
  - Functionality: PASS post-fix-cycle (Edge Case 2 automated test added; Edge Case 1 reclassified as manual)

### User directives executed mid-run

1. **Entry script relocation**: Scripts moved from `scripts/run_server.sh` / `scripts/run_debug.sh` to project root (`./run_server.sh` / `./run_debug.sh`) to align with `CLAUDE.md` "Planned architecture". REQ-INFRA-002 wording and `.dockerignore` updated accordingly.
2. **Edge Case 1 reclassification**: Mid-pull interruption scenario reclassified from automated to manual verification after evaluator-active flagged it untestable reliably. 8-step manual procedure documented in `acceptance.md`; `@MX:WARN` + `@MX:REASON` placed on the pull path in `api/inference.py` to document the Ollama upstream resume contract.

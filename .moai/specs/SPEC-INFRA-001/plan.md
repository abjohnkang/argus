# Implementation Plan — SPEC-INFRA-001

Implementation plan for the Llama 4 runtime foundation. All major architectural decisions are already settled in `./research.md` and `./spec.md`; this document sequences the work and identifies the risks. Do not re-decide runtime, model variant, hardware floor, or persistence strategy here — those are inputs.

---

## 1. Task Decomposition

Tasks are ordered for sequential execution. Each task produces a single file or one focused change. Targets are deliberately small so a stagnation in any one task does not cascade.

| # | Task | Output | Depends on |
|---|---|---|---|
| 1 | Author `.env.example` with `MODEL`, `API_PORT`, `OLLAMA_HOST` (internal service name), and inline comments. | `.env.example` | — |
| 2 | Write `docker-compose.yml` with two services (`model`, `api`), internal Docker network, named volume `argus_ollama_models` mounted at `/root/.ollama`, host port mapping `127.0.0.1:8000:8000`. | `docker-compose.yml` | Task 1 |
| 3 | Author `api/requirements.txt` pinning FastAPI (0.x), uvicorn (0.x), httpx (0.x), pydantic (2.x). Major-version pins only. | `api/requirements.txt` | — |
| 4 | Write `api/Dockerfile` using `python:3.12-slim`, install deps, copy `api/`, run `uvicorn` bound to `127.0.0.1:8000`. | `api/Dockerfile` | Task 3 |
| 5 | Implement `api/inference.py` adapter: Ollama HTTP client wrapper exposing `chat_completion_stream()`, `list_models()`, `is_ready()`. This is the `@MX:ANCHOR` boundary. | `api/inference.py` | Task 3 |
| 6 | Implement `api/main.py`: FastAPI app factory, register `/health` (state-driven per REQ-INFRA-003), `/v1/chat/completions` (SSE streaming), `/v1/models`. Wire localhost middleware (REQ-INFRA-005). Wire model-readiness state machine. | `api/main.py` | Tasks 4, 5 |
| 7 | Write `scripts/run_server.sh`: `docker compose up -d`, poll `http://127.0.0.1:8000/health` until 200 or timeout. Idempotent on healthy stack. | `scripts/run_server.sh` | Task 2 |
| 8 | Write `scripts/run_debug.sh`: `docker compose up` (foreground), export `OLLAMA_DEBUG=1` and `LOG_LEVEL=debug`. | `scripts/run_debug.sh` | Task 2 |
| 9 | Add `.dockerignore` covering `__pycache__`, `.venv`, `.moai`, `.claude`, `node_modules`, etc., to keep build context lean. | `.dockerignore` | — |
| 10 | Acceptance harness: cold start, loading-state, streaming, localhost rejection, idempotent restart, model override (per `./acceptance.md`). | `tests/` or shell-based check, scope determined in `/moai run` | All above |

Ten discrete tasks. Each is small enough to complete inside a single iteration; none requires more than one file write.

---

## 2. Technology Stack

All pins are major-version only — no patch pins, no beta/alpha.

| Layer | Choice | Version pin | Reason |
|---|---|---|---|
| Backend language | Python | `>=3.12,<3.13` | Modern asyncio, native HTTP/2 in stdlib helpers, broad ecosystem support. |
| Web framework | FastAPI | `0.x` | First-class SSE support, OpenAPI generation, asyncio-native. `./research.md` §5. |
| ASGI server | uvicorn | `0.x` | Standard FastAPI runner; supports `--host 127.0.0.1` bind. |
| HTTP client | httpx | `0.x` | Async-friendly, used by `api/inference.py` to talk to Ollama over the internal Docker network. |
| Validation | pydantic | `2.x` | Standard for FastAPI request/response models. |
| Model runtime | Ollama (image: `ollama/ollama`) | Official latest stable | Default runtime per `./research.md` §2. OpenAI-compatible API surface. |
| Container runtime | Docker + Docker Compose | Compose v2 | Per `tech.md` and `CONCEPT.md` — host stays untouched. |

llama.cpp and vLLM are explicitly NOT in the v1 stack. Documented as deferred overlays in `./research.md` §2.

---

## 3. Risk Analysis

Pulled from `./research.md` Section 7. Three primary risks plus two operational ones.

### Risk 1: Hardware floor excludes users

- **Source:** `./research.md` §7 hard risk #1.
- **Impact:** A 16 GB MacBook user runs `scripts/run_server.sh`, the model download finishes (or fails mid-stream), and inference is unusably slow or OOM-killed.
- **Mitigation:** REQ-INFRA-004 explicitly supports `MODEL=llama3.2:3b` as the documented fallback. Product copy (separate from this SPEC) surfaces the 64 GB recommended floor prominently. The runtime does not preflight hardware (out of scope per `./spec.md` exclusions); failures surface as Ollama OOM or slow tokens/sec.

### Risk 2: Model download UX on first run

- **Source:** `./research.md` §7 hard risk #2.
- **Impact:** 32–67 GB pull is a long-running operation. Network interruption mid-pull leaves the volume in a partial state.
- **Mitigation:** Ollama handles resume natively for `ollama pull`. `scripts/run_server.sh` invokes Compose, which restarts the model service if it exits; Ollama then picks up where it left off. `api/inference.py` model-pull path carries an `@MX:WARN` tag documenting the partial-state contract. Acceptance scenario "partial model download interrupted" verifies this.

### Risk 3: Architecture lock-in if API contract is loose

- **Source:** `./research.md` §7 hard risk #3.
- **Impact:** If `api/main.py` forwards directly to Ollama-shaped requests, every downstream consumer (UI, agent tools) couples to Ollama. Swapping to llama.cpp later becomes a rewrite.
- **Mitigation:** All Ollama-specific calls live behind the `api/inference.py` adapter (the `@MX:ANCHOR`). Routes in `api/main.py` consume only the adapter interface, not Ollama types. The adapter is the single swap point.

### Risk 4: Localhost middleware false positives

- **Impact:** A FastAPI test client or local healthcheck tool sends a request with an unexpected `Host` header (e.g., container DNS name) and gets a 403.
- **Mitigation:** The allowlist in REQ-INFRA-005 covers `127.0.0.1`, `localhost`, and `[::1]`. Docker internal service-to-service traffic (api → model) is host-side egress, not host-side ingress to api — the middleware applies only to inbound `api` requests on `127.0.0.1:8000`. Acceptance scenarios validate both the rejection path and the legitimate path.

### Risk 5: Host port already in use

- **Impact:** Another process holds port 8000; Compose fails partway through `up -d`. User sees a confusing half-started state.
- **Mitigation:** `scripts/run_server.sh` detects Compose failure and exits with a clear error. `API_PORT` env var allows override. Acceptance edge case "host port already in use" verifies the error path.

---

## 4. Reference Implementations

The following established patterns should guide implementation. No new invention is required for any layer.

- **Ollama's official `docker-compose.yml` examples.** The canonical reference for an Ollama service in Compose, including the volume mount at `/root/.ollama` and the internal network pattern. Argus adds the `api` sidecar.
- **FastAPI's SSE streaming patterns.** The standard pattern for `StreamingResponse` with `media_type="text/event-stream"`, including `data: {...}\n\n` framing and the `data: [DONE]` sentinel. Used by `api/main.py` for `POST /v1/chat/completions`.
- **Ollama OpenAI-compatibility surface (`/v1/chat/completions`).** Argus matches this shape so the adapter is a thin pass-through in v1, but the adapter encapsulates the call so future runtimes (llama.cpp's server, vLLM's OpenAI server) drop in without changing routes.
- **FastAPI middleware for header validation.** Standard pattern: a subclass of `BaseHTTPMiddleware` reads request headers before the route handler runs and returns a `JSONResponse(status_code=403, ...)` on rejection.

`manager-spec` does not need to fetch these — they are well-known patterns. `/moai run` agents (expert-backend, manager-tdd) will consult them via Context7 or library docs if needed.

---

## 5. Test Strategy Outline

Detailed Given/When/Then scenarios live in `./acceptance.md`. This is the scope summary.

### Test scope

- **Cold-start integration test** (`./acceptance.md` scenario 1): full `docker compose up` from clean state, verify `/health` reaches `200` and the named volume is populated.
- **Loading-state unit test** (`./acceptance.md` scenario 2): `api/main.py` `/health` returns `503 {"status": "loading"}` while the adapter reports model not ready.
- **Streaming integration test** (`./acceptance.md` scenario 3): `POST /v1/chat/completions` with `stream: true` returns SSE-framed chunks ending with `data: [DONE]`.
- **Localhost rejection unit test** (`./acceptance.md` scenario 4): middleware returns 403 for non-localhost `Host`/`Origin` headers and never invokes the adapter.
- **Idempotent restart shell test** (`./acceptance.md` scenario 5): running `scripts/run_server.sh` twice in succession leaves the stack healthy and produces no error.
- **Model override integration test** (`./acceptance.md` scenario 6): `MODEL=llama3.2:3b` produces a `llama3.2:3b` pull and `/v1/models` reflects this.

### Test placement

- Unit tests against `api/main.py` and `api/inference.py` use FastAPI's `TestClient` and httpx mocking. Live under `api/tests/` (created in `/moai run`).
- Integration tests that need real Docker exercise the cold-start path via shell scripts and `curl`. Live under `tests/integration/`.

### What this SPEC does NOT test

- Llama 4 output quality. The runtime serves whatever Llama 4 Scout returns; correctness of generation is Meta's problem, not Argus's.
- Performance regressions across model runtimes. v1 has only one runtime (Ollama); benchmark suite is deferred.
- React UI integration. Separate SPEC.

### Coverage target

`api/` Python code: ≥ 85% per the TRUST 5 baseline. Shell scripts: behavior-tested via the acceptance scenarios, no coverage instrumentation.

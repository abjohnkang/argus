# Argus — Technology

---

## Primary Languages

| Layer | Language |
|-------|----------|
| Backend | Python |
| Frontend | TypeScript (via React) |
| Orchestration | Shell (entry scripts) |
| Container config | YAML (Docker Compose) |

---

## Frameworks and Tools

### Backend: Python + FastAPI

**Rationale:** Python has the strongest ecosystem for Llama 4 integration. Key libraries (`transformers`, `llama-cpp-python`, Ollama client SDKs) are Python-first. FastAPI is the natural choice for the backend because it has first-class support for Server-Sent Events and WebSocket streaming, which are both candidates for the token-streaming transport. FastAPI also provides automatic OpenAPI schema generation, which is useful for frontend integration.

### Frontend: React (TypeScript)

**Rationale:** Locked in by the project's technology choices from the interview. React is the de facto standard for interactive chat UIs and has strong ecosystem support for streaming response rendering. TypeScript is used to keep the frontend type-safe as the project grows.

### Orchestration: Docker + Docker Compose

**Rationale:** The core constraint is that the host environment must stay untouched. Docker Compose is the simplest tool that satisfies this: one `docker-compose.yml` defines all services (backend API, frontend, model runtime), and the user needs only Docker installed on their machine. All dependencies — Python packages, Node modules, model runtime binaries — live inside containers.

---

## Dev Environment Requirements

To run Argus, the user needs:

- **Docker** and **Docker Compose** — required, no exceptions. All services run in containers.
- **Internet connection** — required on first run only, to pull Docker images and download model weights. Subsequent runs are fully offline.

To develop outside containers (optional):

- **Python 3.11+** — only if developing the API outside the container
- **Node.js 20+** — only if developing the UI outside the container (e.g., for hot reload)

No Python or Node.js installation is required to run Argus as an end user.

---

## Build and Deployment

Deployment model: single-machine, local Docker Compose stack. There is no cloud deployment target.

**Entry scripts (planned, not yet written):**

- `scripts/run_server.sh` — Starts the full stack. Idempotent behavior: on first run, pulls Docker images, builds local images, and downloads model weights. On subsequent runs, all steps are no-ops if already complete. This is the standard user entry point.
- `scripts/run_debug.sh` — Identical to `run_server.sh` but surfaces debug-level logs. Used during development and troubleshooting.

Both scripts require only `docker` and `docker compose` to be present in the host `PATH`.

**No-network stance:** After initial setup, the runtime makes no outbound network calls. This is a constitutional constraint, not a configuration option. There is no cloud inference fallback, no telemetry endpoint, and no remote configuration fetch. See [product.md](product.md) for the full non-goals list.

---

## Dependencies

Specific library versions and pinned dependencies are to be defined in the runtime foundation SPEC. The following categories will be resolved then:

**Backend (`api/requirements.txt` or `pyproject.toml`, planned):**
- FastAPI and ASGI server (e.g., uvicorn)
- Model runtime client (depends on open decision: Ollama client, llama-cpp-python, or vLLM client)
- Pydantic for request/response validation
- Streaming transport library (depends on SSE vs WebSocket decision)

**Frontend (`web/package.json`, planned):**
- React and ReactDOM
- TypeScript
- Build tooling (depends on open decision: Vite or Next.js)
- HTTP/streaming client library

**Docker images (planned):**
- Python base image for the API container
- Node.js base image for the frontend container (or static build served by the API)
- Model runtime image (depends on open decision: Ollama, llama.cpp server, or vLLM)

---

## Open Decisions

The following six decisions are unresolved and deferred to the runtime foundation SPEC. Agents working on Argus must not silently pick a side — these require explicit resolution.

### 1. Model runtime: Ollama vs llama.cpp server vs vLLM

**Why deferred:** Each option has different hardware requirements, API surface, and quantization support. Ollama is the easiest to operate but least flexible. llama.cpp server is the most hardware-efficient. vLLM targets GPU-heavy setups and is optimized for throughput. The minimum hardware target (open decision 3) must be known before this can be decided.

### 2. Llama 4 variant and quantization

**Why deferred:** Llama 4 has multiple variants (Scout, Maverick) and multiple quantization levels (Q4, Q5, Q8, FP16). The right choice depends on the minimum hardware target (open decision 3) and the model runtime (open decision 1). Picking a variant before hardware is specified risks targeting the wrong memory footprint.

### 3. Minimum hardware target (RAM, GPU, CPU baseline)

**Why deferred:** This sets the floor for all hardware-dependent decisions. Argus targets personal hardware, but "personal hardware" spans 8 GB unified memory MacBooks to workstations with 32 GB+ dedicated VRAM. The minimum spec determines which Llama 4 variant is viable and which model runtime is appropriate.

### 4. Persistence story (model weights cache and future chat history)

**Why deferred:** Model weights need a stable host path to survive container restarts. Chat history storage (SQLite, JSON files, or in-memory only) is out of scope for v1 but the directory layout must anticipate it. Docker volume strategy needs to be defined in the runtime foundation SPEC.

### 5. Local web UI auth model

**Why deferred:** Options range from no auth (bind to `127.0.0.1` only, trust the OS user boundary) to a simple bearer token to full session-based auth. The right choice depends on the threat model for a single-user local app. This is a security decision, not just a UX one.

### 6. React framework wrapper (bare Vite vs Next.js) and streaming transport (SSE vs WebSocket)

**Why deferred:** These two decisions are coupled. Next.js App Router has opinions about streaming that interact with SSE vs WebSocket choice. Bare Vite is simpler but has no built-in SSR. The decision affects the `web/` directory structure, the `Dockerfile` for the frontend container, and the API endpoint design. Both must be decided together in the runtime foundation SPEC.

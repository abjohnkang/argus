# Argus — Technology

---

## Primary Languages

| Layer | Language |
|-------|----------|
| Backend | Python 3.12 |
| Frontend | TypeScript (via React) — planned, follow-up SPEC |
| Orchestration | Shell (entry scripts) |
| Container config | YAML (Docker Compose) |

---

## Frameworks and Tools

### Backend: Python + FastAPI

**Rationale:** Python has the strongest ecosystem for Llama 4 integration. Key libraries (`transformers`, `llama-cpp-python`, Ollama client SDKs) are Python-first. FastAPI is the natural choice for the backend because it has first-class support for Server-Sent Events and asyncio-native streaming. FastAPI also provides automatic OpenAPI schema generation, which is useful for frontend integration.

### Frontend: React (TypeScript)

**Rationale (planned):** Locked in by the project's technology choices from the interview. React is the de facto standard for interactive chat UIs and has strong ecosystem support for streaming response rendering. TypeScript is used to keep the frontend type-safe as the project grows. Framework choice (bare Vite vs Next.js) is deferred to the UI SPEC.

### Orchestration: Docker + Docker Compose

**Rationale:** The core constraint is that the host environment must stay untouched. Docker Compose is the simplest tool that satisfies this: one `docker-compose.yml` defines all services, and the user needs only Docker installed. All dependencies live inside containers.

---

## SPEC-INFRA-001 Stack (Runtime Foundation)

### Runtime Dependencies

| Package | Version constraint | Role |
|---|---|---|
| Python | `>=3.12,<3.13` | Language runtime (pinned in pyproject.toml) |
| FastAPI | `>=0.115,<0.200` | ASGI web framework; SSE streaming, OpenAPI auto-gen, asyncio-native |
| uvicorn[standard] | `>=0.30,<0.40` | ASGI server (includes `websockets`, `httptools`, `uvloop`) |
| httpx | `>=0.27,<0.30` | Async HTTP client used by `OllamaAdapter` to talk to the model runtime |
| pydantic | `>=2.7,<3.0` | Request/response validation and serialization |

### Model Runtime

**Default: Ollama** (`ollama/ollama:latest` Docker image)

- Provides OpenAI-compatible `/v1/chat/completions` SSE endpoint natively
- First-class Llama 4 Scout support: `ollama run llama4:scout` is one command
- Named Docker volume `argus_ollama_models` persists model weights across container restarts
- Internal-only: no host port mapping; only the `api` service talks to it over the Compose network

**Why Ollama over llama.cpp or vLLM** (see `research.md` Section 2):
- Lowest operational friction for the privacy-individual audience
- Official Docker image with stable API surface
- Handles quantization, model pull, and resume natively

**llama.cpp escape hatch:** Deferred to a follow-up SPEC. A `compose.llamacpp.yml` overlay is planned for power users who need finer quantization control or smaller memory footprints. The `OllamaAdapter` in `api/inference.py` is the single boundary that would change.

**vLLM:** Rejected. Production GPU framework optimized for H100/A100 multi-GPU. Irrelevant on personal hardware (see `research.md` Section 2).

### Model: Llama 4 Scout

**Why Scout** (see `research.md` Section 1):
- Only Llama 4 variant that fits non-server personal hardware at Q4 quantization (~32–67 GB)
- Maverick (400B) needs RTX 5090-class VRAM; Behemoth is server-class — both rejected
- MoE architecture means inference speed is closer to a dense 17B than a 109B model

Default `MODEL=llama4:scout`. Override via environment variable for smaller hardware (e.g., `MODEL=llama3.2:3b`).

### Container Runtime

Docker + Docker Compose v2 (no `version:` key in `docker-compose.yml` per Compose Spec).

**Why two-service topology** (see `research.md` Section 6):
- Separation of concerns: API restart does not require model reload
- Future-proof: agent tool services (file I/O sandbox, retrieval) become additional containers
- Clear failure boundary: API crash does not take down the model runtime

### Test Stack

| Package | Version constraint | Role |
|---|---|---|
| pytest | `>=8,<9` | Test runner |
| pytest-asyncio | `>=0.23,<1` | Async test support (`asyncio_mode = "auto"`) |
| pytest-cov | `>=5,<7` | Coverage reporting and gate enforcement |
| respx | `>=0.21,<1` | HTTP mock for hermetic unit tests (intercepts `httpx` calls to Ollama) |

### Linting, Formatting, Coverage

| Tool | Config | Notes |
|---|---|---|
| ruff | `line-length=100`, `target-version=py312` | Lint rules: E, F, W, I, B, UP |
| black | `line-length=100`, `target-version=["py312"]` | Code formatter |
| isort | `profile=black`, `line_length=100` | Import sorter |
| pytest-cov | `fail_under=85` | Gate enforced in CI and locally; current coverage: 92.62% |

Coverage source is `api/`; `api/tests/*` is excluded from measurement.

---

## Dev Environment Requirements

To run Argus (end user):
- **Docker** and **Docker Compose** — required. All services run in containers.
- **Internet connection** — required on first run only (model pull). Subsequent runs are fully offline.

To develop outside containers (optional):
- **Python 3.12** — only if developing the API outside the container
- **Node.js 20+** — only if developing the UI outside the container (planned)

No Python or Node.js installation is required to run Argus as an end user.

---

## Build and Deployment

Deployment model: single-machine, local Docker Compose stack. No cloud deployment target.

**Entry scripts (project root):**
- `run_server.sh` — `docker compose up -d`, then poll `/health` until `200 {"status":"ready"}` or timeout. Idempotent: re-runs on a healthy stack are no-ops.
- `run_debug.sh` — `docker compose up` (foreground) with `OLLAMA_DEBUG=1` and API `debug` log level. Streams logs to stdout for development and troubleshooting.

Both scripts require only `docker` and `docker compose` in the host `PATH`.

**No-network stance:** After initial setup, the runtime makes no outbound network calls. Constitutional constraint; not a configuration option. See [product.md](product.md) for the full non-goals list.

---

## Open Decisions (carry-forward from pre-SPEC-INFRA-001)

The following decisions remain unresolved and are deferred to follow-up SPECs:

1. **React framework wrapper** (bare Vite vs Next.js) — belongs to the UI SPEC
2. **Streaming transport on the UI side** — backend uses SSE; UI SPEC decides how React consumes it
3. **Smaller-model fallback UX** — how users opt into Llama 3.2 in a UI context

Decisions resolved by SPEC-INFRA-001 (no longer open):
- Model runtime: Ollama (default)
- Llama 4 variant: Scout
- Hardware floor: 64 GB unified memory or 64 GB RAM + 24 GB VRAM
- Persistence: named Docker volume for model weights
- Auth model (v1): localhost bind + non-localhost header rejection

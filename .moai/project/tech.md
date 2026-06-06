# Argus — Technology

---

## Primary Languages

| Layer | Language |
|-------|----------|
| Backend | Python 3.12 |
| Frontend | TypeScript 5 (React 18) — delivered in SPEC-UI-001 |
| Orchestration | Shell (entry scripts) |
| Container config | YAML (Docker Compose) |

---

## Frameworks and Tools

### Backend: Python + FastAPI

**Rationale:** Python has the strongest ecosystem for Llama 4 integration. Key libraries (`transformers`, `llama-cpp-python`, Ollama client SDKs) are Python-first. FastAPI is the natural choice for the backend because it has first-class support for Server-Sent Events and asyncio-native streaming. FastAPI also provides automatic OpenAPI schema generation, which is useful for frontend integration.

### Frontend: React (TypeScript)

**Rationale:** Locked in by the project's technology choices from the interview. React 18 is the de facto standard for interactive chat UIs and has strong ecosystem support for streaming response rendering. TypeScript 5 keeps the frontend type-safe as the project grows. Vite 5 was chosen over Next.js because the UI is a static SPA with no server-side rendering needs — Vite produces a lean static bundle that the FastAPI `StaticFiles` mount serves directly, keeping the single-entry-point architecture intact.

### Orchestration: Docker + Docker Compose

**Rationale:** The core constraint is that the host environment must stay untouched. Docker Compose is the simplest tool that satisfies this: one `docker-compose.yml` defines all services, and the user needs only Docker installed. All dependencies live inside containers.

---

## SPEC-UI-001 Stack (React Chat UI)

### Frontend Runtime Dependencies

| Package | Version constraint | Role |
|---|---|---|
| React | `^18.3` | UI library; `useReducer`-based chat state |
| TypeScript | `^5` | Static typing for the SPA |
| Vite | `^5` | Build tool (dev server with API proxy + static bundle for production) |
| Tailwind CSS | `^3.4` | Utility-first styling; neutral ChatGPT-like theme backed by CSS-variable brand-seam tokens |
| react-markdown | `^9` | Markdown rendering for assistant messages |
| remark-gfm | `^4` | GitHub Flavored Markdown tables, strikethrough, task lists |
| rehype-highlight | `^7` | Syntax highlighting for fenced code blocks; highlight.js theme self-hosted (no CDN) |

### Frontend Test Stack

| Package | Role |
|---|---|
| Vitest | Test runner (co-located with Vite; zero config overhead) |
| @testing-library/react | React component testing (render + user-event) |

37 tests; lib branch coverage >85%.

### Key frontend decisions

**`fetch()` + `ReadableStream` over `EventSource`:** The browser's native `EventSource` API is
read-only GET — it cannot POST a JSON body. The SSE stream from `POST /v1/chat/completions` is
consumed via `fetch()` with `response.body.getReader()`, a manual `TextDecoder` + `\n\n`-frame
splitter, and `AbortController`-based abort for the Stop button. See `web/src/lib/sseClient.ts`
`@MX:ANCHOR` for the frame-parsing contract.

**Same-origin serving over a separate dev server:** The SPA is served from the api origin at
runtime (`StaticFiles` in `api/main.py`). This means `Host` and `Origin` headers on every
`fetch()` call are `127.0.0.1:8000`, which `LocalhostOnlyMiddleware` passes cleanly — no CORS
headers needed, no weakening of the v1 threat model. In development, `vite dev` uses a proxy
(`/v1` and `/health` → `http://127.0.0.1:8000`) to mirror the same-origin behavior.

**Multi-stage Dockerfile:** `api/Dockerfile` added a `node:20-slim` first stage that runs
`npm ci && npm run build` against `web/`; the output `web/dist/` is copied into the
`python:3.12-slim` runtime stage. Node is never present at runtime, honoring the
"host environment untouched" and "minimal runtime surface" stances. `.dockerignore` excludes
`web/node_modules/` and `web/dist/` so host artifacts do not pollute the build context.

**Neutral brand defaults with CSS-variable seam:** Tailwind tokens (`--color-bg`,
`--color-surface`, `--color-accent`, `--color-text`, `--font-sans`, `--font-mono`) are defined
as semantic CSS variables. The brand interview (`_TBD_` in `web/research.md`) can be applied
later by editing variable values only — no component changes needed.

**Content Security Policy:** `index.html` carries `<meta http-equiv="Content-Security-Policy"
content="default-src 'self'">` as defense-in-depth for the no-external-call rule. Self-hosted
fonts and highlight.js themes satisfy the `'self'` constraint.

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

## Open Decisions (carry-forward)

The following decisions remain unresolved and are deferred to follow-up SPECs:

1. **Smaller-model fallback UX** — how users opt into Llama 3.2 in a UI context (currently `MODEL=llama3.2:3b` env var only)
2. **Brand adoption** — the `_TBD_` brand files in `web/research.md`; CSS-variable seam is in place but no brand values committed

Decisions resolved by SPEC-UI-001 (no longer open):
- React framework wrapper: bare Vite (no SSR needed; static bundle served by FastAPI `StaticFiles`)
- Streaming transport on the UI side: `fetch()` + `ReadableStream` (EventSource cannot POST)
- Serving strategy: same-origin from api origin (no separate web container, no nginx, no CORS)

Decisions resolved by SPEC-INFRA-001 (no longer open):
- Model runtime: Ollama (default)
- Llama 4 variant: Scout
- Hardware floor: 64 GB unified memory or 64 GB RAM + 24 GB VRAM
- Persistence: named Docker volume for model weights
- Auth model (v1): localhost bind + non-localhost header rejection

# Argus — Product

Argus is an on-device AI agent built on Llama 4. All inference runs locally inside Docker containers on the user's own hardware. The runtime makes no outbound network calls after the initial model download, and no data is ever transmitted to cloud services, analytics providers, or remote configuration endpoints. See [CONCEPT.md](../../CONCEPT.md) for the full vision statement and non-goals. Technical choices are covered in [tech.md](tech.md).

---

## Target Audience

Privacy-focused individuals running offline AI on personal Mac or Linux hardware. The defining promise is that no data leaves the device. UX, defaults, and scope all derive from this single audience: simple Docker-based installation, no account creation, no cloud dependency, conversation history stored only on the local device.

This is a single-user product. Enterprise deployment, team sharing, and multi-user scenarios are out of scope.

**Hardware profile for v1:** Privacy-individual with serious-but-attainable personal hardware — 64 GB unified memory Mac (M-Pro/M-Max or Mac Studio) or 64 GB RAM + 24 GB VRAM x86 workstation. Users below this floor can use `MODEL=llama3.2:3b` as a documented downgrade that preserves the on-device promise.

---

## Core Value Propositions

**Privacy by architecture, not by policy.** The runtime is network-isolated after setup. There is no code path that sends data to a remote server. Privacy is enforced structurally, not through configuration switches.

**Zero subscription fees.** All compute runs on hardware the user already owns. There are no API credits, no monthly tiers, no usage caps.

**Host environment untouched.** Every service runs inside Docker via `docker-compose`. The user's host system is not modified. Uninstall is `docker-compose down`.

**Offline-first by default.** Once model weights are downloaded, Argus operates with no internet connection. This is not a degraded mode — it is the primary operating mode.

---

## SPEC-INFRA-001 Delivery (Runtime Foundation, v1)

SPEC-INFRA-001 is the first implementation milestone. It delivers the minimal on-device LLM stack that every later feature depends on.

### What v1 ships

- **Localhost-bound HTTP API in Docker** — FastAPI service (`api/`) serving Llama 4 Scout inference behind three OpenAI-compatible endpoints.
- **`GET /health`** — `503 {"status":"loading"}` during cold start; `200 {"status":"ready"}` once the model is resident. State machine prevents requests from reaching the model while it is still loading.
- **`GET /v1/models`** — lists models known to the configured Ollama runtime.
- **`POST /v1/chat/completions`** — SSE streaming chat with token-by-token delivery.
- **MODEL env var override** — `MODEL=llama3.2:3b ./run_server.sh` uses a smaller model with no source file modifications.
- **Named Docker volume `argus_ollama_models`** — preserves the 32–67 GB Llama 4 Scout weights across `docker compose down`. One-time pull; subsequent runs are instant.
- **Idempotent entry scripts at project root** — `run_server.sh` (health-gated cold start) and `run_debug.sh` (foreground with debug logging). Re-runs on a healthy stack are no-ops.
- **Defense-in-depth localhost enforcement** — Docker port mapping binds host side to `127.0.0.1`; `LocalhostOnlyMiddleware` rejects forged Host/Origin headers with `403`.

### Demo state at end of SPEC-INFRA-001

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"llama4:scout","messages":[{"role":"user","content":"hi"}],"stream":true}'
```

Streaming tokens from a local Llama 4 Scout — nothing more, nothing less.

### What v1 explicitly does NOT ship

Per SPEC-INFRA-001 Exclusions (not in scope, not to be implemented until corresponding SPECs):

- No React web UI (separate SPEC)
- No conversation persistence or chat history
- No bearer token or session auth
- No vLLM support
- No Llama 4 Maverick or Behemoth (hardware out of reach)
- No llama.cpp escape hatch in v1 (deferred follow-up SPEC; `compose.llamacpp.yml` overlay planned)
- No agent tools (file I/O, web fetch, code execution)
- No automatic hardware preflight check
- No rate limiting

---

## SPEC-UI-001 Delivery (Chat UI, v1)

SPEC-UI-001 delivers the browser-based React chat front end that completes the first-milestone vertical slice. The demo-able state is: open a browser at `http://127.0.0.1:8000`, type a message, and watch a local Llama model stream a response — all on-device.

### What shipped

- **Browser chat UI at `http://127.0.0.1:8000/`** — React 18 SPA built with Vite 5, served directly from the `api` service via `StaticFiles`. No new container, no nginx, no Node runtime in production.
- **Token-by-token streaming** — `fetch()` + `ReadableStream` SSE client (`web/src/lib/sseClient.ts`) consumes the Ollama-native stream; markdown and fenced code blocks rendered via react-markdown + remark-gfm + rehype-highlight.
- **Stop button** — aborts the in-flight stream via `AbortController`; partial output is retained and the composer resets without surfacing an error.
- **Loading state** — polls `GET /health`; disables the composer while the model is still loading (`503`); enables input on `200 {"status":"ready"}`.
- **Error handling** — pre-stream non-OK HTTP status and mid-stream `{"error"}` frames both surface human-readable messages; typed input is never discarded.
- **Same-origin, no external calls** — SPA served from the api origin keeps `LocalhostOnlyMiddleware` clean; no CORS config added; `Content-Security-Policy: default-src 'self'` enforced; all fonts and highlight themes self-hosted.
- **Single conversation, no persistence** — honors the project no-persistence rule; reloading the page starts a fresh empty conversation.

### Demo state at end of SPEC-UI-001

Open `http://127.0.0.1:8000/` in a browser after `./run_server.sh`. The first-milestone vertical slice — open browser, type, watch Llama stream — is complete.

### What v1 explicitly does NOT ship

Per SPEC-UI-001 Exclusions:

- No conversation persistence or chat history (honors project no-persistence rule)
- No multi-session or multiple conversations
- No settings panel or model-picker dropdown
- No authentication or access control (inherits SPEC-INFRA-001 localhost threat model)
- No mobile-specific layout
- No telemetry, analytics, or remote config
- No agent tools

---

## First-Milestone Feature Scope

The first milestone — a working chat UI backed by local Llama 4 streaming inference — is now COMPLETE. Both SPECs that compose the vertical slice have been delivered.

**In scope for the full first milestone (across multiple SPECs):**

- Chat UI (React, browser-based) — **delivered in SPEC-UI-001**
- Local Llama 4 inference via the Python backend — delivered in SPEC-INFRA-001
- Streaming response output (token-by-token) — delivered in SPEC-INFRA-001
- Docker Compose orchestration of all services — delivered in SPEC-INFRA-001
- `run_server.sh` and `run_debug.sh` entry scripts — delivered in SPEC-INFRA-001

**Explicit non-goals for the full first milestone:**

- No cloud inference or hosted model fallback
- No telemetry or usage analytics
- No remote configuration
- No conversation persistence or chat history
- No user authentication or access control
- No agent tools (file I/O, web fetch, code execution)
- No multi-user support
- No mobile interface

Agent capabilities (tools, memory, scheduling) are planned for later milestones.

---

## Use Cases

**Confidential document drafting.** A user working with sensitive personal or professional documents asks Argus to draft, summarize, or rewrite text. The content never leaves the local machine.

**Private research assistant.** A user researches a sensitive topic — medical, legal, financial — and wants AI-assisted synthesis without their queries being logged by a cloud provider.

**Offline productivity.** A user works in an air-gapped or network-restricted environment (airplane, secure facility, off-grid location) and needs AI assistance that does not depend on internet connectivity.

**Local code assistance.** A developer wants LLM-powered code suggestions for proprietary code they are unwilling to send to an external API.

**Experimentation with local LLMs.** A user wants to run and interact with Llama 4 without setting up raw model tooling, using Argus as a clean, ready-to-run interface.

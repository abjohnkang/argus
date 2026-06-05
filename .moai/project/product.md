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

## First-Milestone Feature Scope (pre-SPEC-INFRA-001, preserved)

The first milestone is a working chat UI backed by local Llama 4 streaming inference. It is the smallest demo-worthy vertical slice: open a browser, type a message, see Llama 4 stream a response from the local container.

**In scope for the full first milestone (across multiple SPECs):**

- Chat UI (React, browser-based) — follow-up SPEC
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

Agent capabilities (tools, memory, scheduling) are planned for later milestones and are not in scope until the runtime foundation SPEC is complete.

---

## Use Cases

**Confidential document drafting.** A user working with sensitive personal or professional documents asks Argus to draft, summarize, or rewrite text. The content never leaves the local machine.

**Private research assistant.** A user researches a sensitive topic — medical, legal, financial — and wants AI-assisted synthesis without their queries being logged by a cloud provider.

**Offline productivity.** A user works in an air-gapped or network-restricted environment (airplane, secure facility, off-grid location) and needs AI assistance that does not depend on internet connectivity.

**Local code assistance.** A developer wants LLM-powered code suggestions for proprietary code they are unwilling to send to an external API.

**Experimentation with local LLMs.** A user wants to run and interact with Llama 4 without setting up raw model tooling, using Argus as a clean, ready-to-run interface.

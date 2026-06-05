# Argus — On-device Llama 4 agent

All inference, memory, and tools run locally on your hardware. No data ever leaves the device.

---

## Status

**v1 (SPEC-INFRA-001) — Runtime foundation complete.**
This release delivers a localhost-bound HTTP API in Docker serving Llama 4 Scout inference.
The React web UI, agent tools, and memory are deferred to follow-up SPECs.

---

## System requirements

### Recommended

| Platform | Spec |
|---|---|
| Apple Silicon | M-Pro or M-Max with 64 GB unified memory (Mac Studio M2 Ultra ideal) |
| Linux / Windows x86 | 64 GB RAM + discrete GPU with 24 GB VRAM (RTX 3090, 4090, A6000) |

### Hard floor (degraded performance, Scout may be slow or require heavy quantization)

- 32 GB unified memory, or 32 GB RAM + 12 GB VRAM
- At this level, use `MODEL=llama3.2:3b` (see Model override below)

### Software

- Docker Desktop (macOS / Windows) or Docker Engine + Compose v2 (Linux)
- Internet connection on first run only (model pull is ~32–67 GB for default `llama4:scout`)

---

## Quick start

```bash
git clone <repo> && cd argus
./run_server.sh
# First run: pulls Docker images + downloads model weights (~32–67 GB for llama4:scout)
# This takes 5–15 minutes on a fast connection. Subsequent runs are instant.
curl http://127.0.0.1:8000/health
# {"status":"ready"} — model is loaded and serving
```

Send a streaming chat request:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"llama4:scout","messages":[{"role":"user","content":"hi"}],"stream":true}'
```

---

## Model override for smaller hardware

```bash
MODEL=llama3.2:3b ./run_server.sh   # ~2 GB pull, runs on 16 GB systems
```

Any Ollama-supported model tag works. No source files or config files need editing.

---

## API endpoints

All endpoints are bound to `127.0.0.1` only and are not reachable from other machines.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | `503 {"status":"loading"}` during cold start; `200 {"status":"ready"}` when model is loaded |
| `GET` | `/v1/models` | List models available in the configured Ollama runtime |
| `POST` | `/v1/chat/completions` | OpenAI-compatible SSE streaming chat (`model` + `messages` + `stream: true`) |

### Example: streaming completions

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama4:scout",
    "messages": [{"role": "user", "content": "Explain Docker volumes in one paragraph."}],
    "stream": true
  }'
```

The response is a sequence of `data: {...}` SSE frames followed by `data: [DONE]`.

---

## Security model (v1)

- Docker port mapping binds the host side to `127.0.0.1` only — no LAN exposure (REQ-INFRA-001).
- `LocalhostOnlyMiddleware` rejects requests with non-localhost `Host` or `Origin` headers with `403 Forbidden` — defense against DNS rebinding even if the bind is bypassed (REQ-INFRA-005).
- No bearer token auth in v1. The threat model is single-user, single-device: OS user boundary plus localhost bind.
- See `.moai/specs/SPEC-INFRA-001/spec.md` and `research.md` for the full threat model rationale.

---

## Development

### Setup

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### Tests

```bash
# Unit tests — hermetic, no Docker required (103 tests, 92.62% coverage)
.venv/bin/pytest api/tests/ --cov=api -v

# Integration tests — requires Docker + Ollama (~1 GB pull of llama3.2:1b on first run)
.venv/bin/pytest -m integration tests/integration/ -v
```

### Lint and format

```bash
.venv/bin/ruff check api/
.venv/bin/black --check api/
.venv/bin/isort --check api/
```

---

## Project layout

```
argus/
├── api/                    # FastAPI service
│   ├── main.py             # App factory, middleware, lifespan readiness poller
│   ├── inference.py        # OllamaAdapter — @MX:ANCHOR runtime swap boundary
│   ├── security.py         # LocalhostOnlyMiddleware (pure functions)
│   ├── state.py            # ReadinessTracker (async-lock-protected state machine)
│   ├── requirements.txt    # Pinned runtime deps
│   ├── Dockerfile          # Python 3.12-slim API image
│   └── tests/              # Unit tests (hermetic, respx-mocked Ollama)
├── tests/integration/      # Integration tests (real Docker + Ollama)
├── docker-compose.yml      # Two-service stack: model (Ollama) + api (FastAPI)
├── run_server.sh           # Idempotent first-run + health-gated startup (project root)
├── run_debug.sh            # Foreground variant with debug logging
├── .env.example            # MODEL, API_PORT, OLLAMA_HOST documented
├── pyproject.toml          # Python project config + test/lint tooling
├── CONCEPT.md              # Project vision and non-goals
└── .moai/specs/            # SPEC documents (SPEC-INFRA-001 and future SPECs)
```

---

## Manual test: Edge Case 1 (partial model pull resume)

Ollama resumes interrupted model downloads natively. The 8-step manual test procedure
(mid-pull container kill, partial-blob verification, resume confirmation) is documented in
`.moai/specs/SPEC-INFRA-001/acceptance.md` under "Edge case 1".

---

## License / contributing

License: Apache-2.0 (see `pyproject.toml`). Contributing guidelines are TBD.

---

## References

- [CONCEPT.md](CONCEPT.md) — Vision, non-goals, open questions
- [.moai/specs/SPEC-INFRA-001/](\.moai/specs/SPEC-INFRA-001/) — Full SPEC, research, acceptance criteria, and design rationale

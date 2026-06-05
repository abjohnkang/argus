# Changelog

All notable changes to Argus are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **SPEC-INFRA-001: Llama 4 runtime foundation** — localhost-bound HTTP API in Docker serving Llama 4 Scout inference via Ollama.
- FastAPI service (`api/`) with three OpenAI-compatible endpoints:
  - `GET /health` — loading/ready state machine (`503 {"status":"loading"}` → `200 {"status":"ready"}`)
  - `GET /v1/models` — list models known to the configured runtime
  - `POST /v1/chat/completions` — SSE streaming chat with token-by-token delivery
- `LocalhostOnlyMiddleware` — rejects requests with non-localhost `Host` or `Origin` headers with `403 Forbidden`; defense in depth alongside Docker port-mapping (`127.0.0.1:PORT:PORT`)
- `OllamaAdapter` — thin runtime-swap boundary (`@MX:ANCHOR`) with `OllamaUnavailable` exception mapping upstream 5xx and connect/timeout errors to `502 Bad Gateway`
- `ReadinessTracker` — async-lock-protected `LOADING → READY` state machine; prevents inference requests from reaching the model during cold start
- Docker Compose two-service stack (`model` + `api`) with named volume `argus_ollama_models` preserving the ~32–67 GB Llama 4 Scout download across `docker compose down`
- Idempotent entry scripts at project root:
  - `run_server.sh` — `docker compose up -d` + health-gated polling until `200 {"status":"ready"}`
  - `run_debug.sh` — foreground variant with `OLLAMA_DEBUG=1` and API `debug` log level
- `MODEL` env var override — `MODEL=llama3.2:3b ./run_server.sh` uses an alternative model with no source file modifications
- `.env.example` documenting `MODEL` (default `llama4:scout`), `API_PORT` (default `8000`), `OLLAMA_HOST` (internal Compose DNS)
- 103 unit tests (pytest + pytest-asyncio + respx) — hermetic, no Docker required; 92.62% coverage on `api/`
- 6 integration tests (`@pytest.mark.integration`) against real Ollama with `llama3.2:1b`; skip cleanly without Docker
- Manual test procedure for Edge Case 1 (partial model pull resume) documented in `.moai/specs/SPEC-INFRA-001/acceptance.md`
- Automated test for Edge Case 2 (host port already in use) at `tests/integration/test_docker_stack.py::test_run_server_exits_2_when_port_in_use`

### Tooling

- Python 3.12 project (`pyproject.toml` with setuptools build backend)
- ruff (lint, `line-length=100`, `target-version=py312`), black (format), isort (`profile=black`)
- pytest-cov coverage gate at 85% (`fail_under=85`); current coverage 92.62%
- `.dockerignore` excludes `.moai/`, `.claude/`, `*.md`, `.venv/`, `run_*.sh` for fast image builds

### Documentation

- `README.md` — quick start, system requirements, API contract, security model, development workflow, project layout
- `.moai/project/product.md` — SPEC-INFRA-001 delivery summary added (v1 ships / does not ship, demo state)
- `.moai/project/structure.md` — updated to reflect actual directory layout post-implementation
- `.moai/project/tech.md` — SPEC-INFRA-001 technology stack documented (versions, rationale, architecture decisions)
- `.moai/specs/SPEC-INFRA-001/` — status updated to `completed`; Implementation Notes section appended

---

[Unreleased]: https://github.com/abjohnkang/argus/compare/main...feature/SPEC-INFRA-001-runtime-foundation

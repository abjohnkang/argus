# SPEC-INFRA-001 Task Decomposition

**SPEC**: SPEC-INFRA-001 — Llama 4 Runtime Foundation
**Methodology**: TDD (RED-GREEN-REFACTOR) per `.moai/config/sections/quality.yaml`
**Branch**: `feature/SPEC-INFRA-001-runtime-foundation` (stay on; no auto-branch)
**Total tasks**: 17
**Generated**: 2026-06-04 (Phase 1.5)

## User decisions baked into plan

1. **Test strategy**: Real Ollama with tiny model (`llama3.2:1b`) for integration tests; pure-logic unit tests stay hermetic via `respx`.
2. **Slicing**: Full SPEC in one pass; per-task atomic commits at Phase 3.
3. **REQ-INFRA-001 interpretation**: uvicorn inside container binds `0.0.0.0`; Docker port mapping `127.0.0.1:8000:8000` enforces host-side localhost; `LocalhostOnlyMiddleware` enforces header-level rejection (defense in depth). SPEC text accepted as-is without amendment.

## Tasks

| ID | Description | REQ(s) | Depends | Planned Files | Acceptance | Position | Status |
|---|---|---|---|---|---|---|---|
| TASK-001 | Scaffold `pyproject.toml`, `api/requirements.txt`, `api/tests/conftest.py` stub | foundation | — | `pyproject.toml`, `api/requirements.txt`, `api/__init__.py`, `api/tests/__init__.py`, `api/tests/conftest.py` | `pytest --collect-only` exits 0; `ruff check api/` passes | SETUP | pending |
| TASK-002 | Create `api/security.py` stub with `is_localhost_header` raising `NotImplementedError` | 005 | T-001 | `api/security.py` | Import works; function exists | SETUP | pending |
| TASK-003 | RED: parametrized `test_security.py` for allowed and rejected headers | 005 | T-002 | `api/tests/test_security.py` | All tests fail with `NotImplementedError` (proves RED) | RED | pending |
| TASK-004 | GREEN: implement `is_localhost_header` + `extract_origin_host` (no DNS) | 005 | T-003 | `api/security.py` | `test_security.py` green; 100% coverage on file | GREEN | pending |
| TASK-005 | RED+GREEN: `api/state.py` — `ReadinessState` enum + `ReadinessTracker` (asyncio.Lock) | 003 | T-001 | `api/state.py`, `api/tests/test_state.py` | `test_state.py` green; 100% coverage | RED→GREEN | pending |
| TASK-006 | Write `.env.example` documenting `MODEL`, `API_PORT`, `OLLAMA_HOST` | 004 | — | `.env.example` | File exists with documented keys + comments | INFRA | pending |
| TASK-007 | Stub `api/inference.py` `OllamaAdapter` class | 003, 004 | T-001 | `api/inference.py` | Import works; class signature stable | SETUP | pending |
| TASK-008 | RED: `respx`-mocked `test_inference.py` for `is_ready` / `list_models` / `chat_completion_stream` | 003, 004 | T-007 | `api/tests/test_inference.py` | All tests fail (RED) | RED | pending |
| TASK-009 | GREEN: implement `OllamaAdapter` with `httpx.AsyncClient`; add `@MX:ANCHOR` + `@MX:WARN` on pull path | 003, 004 | T-008 | `api/inference.py` | `test_inference.py` green; coverage >=85% on file | GREEN | pending |
| TASK-010 | RED+GREEN: `api/main.py` FastAPI app + `/health`, `/v1/models`, `/v1/chat/completions`; `@MX:NOTE` on state machine | 001, 003 | T-005, T-009 | `api/main.py`, `api/tests/test_main_routes.py` | `test_main_routes.py` green | RED→GREEN | pending |
| TASK-011 | RED+GREEN: `LocalhostOnlyMiddleware` in `api/main.py`; `@MX:NOTE` on middleware | 005 | T-004, T-010 | `api/main.py`, `api/tests/test_middleware.py` | `test_middleware.py` green; mock adapter `assert_not_called()` for rejections | RED→GREEN | pending |
| TASK-012 | REFACTOR: extract fixtures, run `ruff`/`black`/`isort`, verify coverage >=85% | all | T-011 | `api/tests/conftest.py`, `pyproject.toml` | `pytest --cov=api --cov-fail-under=85` exits 0 | REFACTOR | pending |
| TASK-013 | Write `api/Dockerfile` (`python:3.12-slim`, uvicorn) | 001 | T-012 | `api/Dockerfile` | `docker build` succeeds in integration fixture | INFRA | pending |
| TASK-014 | Write `.dockerignore` | — | T-013 | `.dockerignore` | Build context shrinks; verified in `docker build` output | INFRA | pending |
| TASK-015 | Write `docker-compose.yml` (model + api services, internal network, named volume `argus_ollama_models`) | 001, 004 | T-013 | `docker-compose.yml` | `docker compose config` validates; port mapping `127.0.0.1:8000:8000` present | INFRA | pending |
| TASK-016 | Write `./run_server.sh` (project root, idempotent) and `./run_debug.sh` (project root, foreground) | 002 | T-015 | `run_server.sh`, `run_debug.sh` | `shellcheck run_*.sh` clean; `chmod +x` applied | INFRA | pending |
| TASK-017 | Write `tests/integration/test_docker_stack.py` — real Docker fixture, pulls `llama3.2:1b`, exercises cold-start + override + forged-Host rejection | 001, 002, 004, 005 | T-016 | `tests/integration/__init__.py`, `tests/integration/conftest.py`, `tests/integration/test_docker_stack.py` | `pytest tests/integration -m integration` passes with Docker; skips gracefully without | INTEGRATION | pending |

## REQ Coverage Map

| REQ | Tasks fulfilling | Test files |
|---|---|---|
| REQ-INFRA-001 (localhost bind) | T-013, T-015, T-017 | docker-compose contract + `test_docker_stack::test_port_bound_to_loopback_only` |
| REQ-INFRA-002 (cold-start health-gated) | T-016, T-017 | `test_docker_stack::test_health_eventually_200` (cold-start: session fixture invokes `./run_server.sh` and blocks until /health=200), `::test_idempotent_restart` |
| REQ-INFRA-003 (503 loading → 200 ready) | T-005, T-007, T-008, T-009, T-010 | `test_state.py`, `test_main_routes.py::test_health_returns_503_while_loading`, `::test_health_returns_200_when_ready`, `test_docker_stack::test_health_eventually_200` (live stack confirms 200 after ready) |
| REQ-INFRA-004 (`MODEL` override) | T-006, T-007, T-008, T-009, T-015, T-017 | `test_inference.py::test_adapter_respects_model_env`, `test_docker_stack::test_model_override_lists_llama32` |
| REQ-INFRA-005 (403 header rejection) | T-002, T-003, T-004, T-011, T-017 | `test_security.py` (12+ parametrized), `test_middleware.py::test_forged_host_returns_403_without_invoking_adapter`, `test_docker_stack::test_forged_host_rejected` |

## Success Criteria

- All 5 EARS REQs covered by at least one unit test AND at least one integration test (where Docker is involved).
- Coverage >=85% on `api/` enforced by `pytest --cov=api --cov-fail-under=85` at TASK-012.
- All TDD cycles closed; no orphaned RED.
- Integration test (TASK-017) successfully starts Docker stack, pulls `llama3.2:1b`, and verifies `/health` returns 200.
- Localhost middleware (TASK-011) rejects forged `Host` header with 403 and asserts mock adapter `assert_not_called()`.

## MX Tag Plan (from SPEC, honored by tasks)

| File | Tag type | Placed in task | Purpose |
|---|---|---|---|
| `api/inference.py` | `@MX:ANCHOR` | TASK-009 | Runtime swap boundary (Ollama → future llama.cpp/vLLM); high future fan_in |
| `api/inference.py` (pull/download path) | `@MX:WARN` + `@MX:REASON` | TASK-009 | Long-running 32-67 GB pull; partial-state risk; resume contract |
| `api/main.py` (LocalhostOnlyMiddleware) | `@MX:NOTE` | TASK-011 | v1 threat model documentation: 127.0.0.1 bind + header rejection = no bearer auth in v1 |
| `api/main.py` (readiness state machine) | `@MX:NOTE` | TASK-010 | Documents 503-loading -> 200-ready transition contract (REQ-INFRA-003) |

## Test Infrastructure (TASK-001 outputs)

`pyproject.toml`:
- Python 3.12 requires-python pin
- pytest 8 with `asyncio_mode = "auto"`, markers `unit` and `integration`, `--strict-markers`
- coverage scope = `api/`, fail_under = 85
- ruff (line-length 100, target py312), black, isort

`api/requirements.txt`:
- fastapi >=0.115,<0.200
- uvicorn[standard] >=0.30,<0.40
- httpx >=0.27,<0.30
- pydantic >=2.7,<3.0

Test-only deps (in `[project.optional-dependencies.dev]`):
- pytest >=8.0,<9.0
- pytest-asyncio >=0.23,<1.0
- pytest-cov >=5.0,<7.0
- respx >=0.21,<1.0

# Changelog

All notable changes to Argus are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **SPEC-UI-001: React chat UI** — browser-based streaming chat front end that completes the first-milestone vertical slice.
- React 18 SPA (`web/`) built with Vite 5, TypeScript 5, and Tailwind CSS 3.4; served by the existing FastAPI `api` service at `http://127.0.0.1:8000/` via `StaticFiles` — no new container, no nginx, no Node runtime in production.
- `web/src/lib/sseClient.ts` (`@MX:ANCHOR`) — SSE stream consumer over `fetch()` + `ReadableStream` with cross-chunk frame buffering, `[DONE]` sentinel detection, Ollama-native `message.content` extraction, in-band `{"error"}` frame handling, and `AbortController`-based stop.
- `web/src/lib/health.ts` — `/health` readiness polling; disables the composer while the backend is `503 loading`.
- Token-by-token streaming render with `react-markdown` + `remark-gfm` + `rehype-highlight`; all assets self-hosted (no CDN at runtime).
- Stop button: aborts the in-flight stream via `AbortController`; retains partial output; resets composer without surfacing an error.
- Loading state: indeterminate "model is loading" state while `/health` returns `503`; no timeout — first-run model pull can take minutes.
- Error handling: pre-stream non-OK HTTP status (e.g. `502`) and mid-stream `{"error"}` SSE frames both surface human-readable messages; typed input is never discarded; UI stays usable for retry.
- `Content-Security-Policy: default-src 'self'` meta tag in `index.html` — defense-in-depth for the no-external-call rule.
- Neutral ChatGPT-like theme with semantic CSS-variable brand seam (`--color-bg`, `--color-surface`, `--color-accent`, etc.) — brand values deferred to a future brand interview.
- 37 Vitest unit tests (`web/src/lib/`); lib branch coverage >85%.
- `api/tests/test_static_spa.py` — 14 new pytest tests covering `StaticFiles` mount, API route precedence, and graceful absence of `web/dist`; backend total 117 tests, `api/` coverage 93%.

### Changed (SPEC-UI-001)

- `api/main.py` — mounts `StaticFiles(directory="web/dist", html=True)` at `/`, registered AFTER the API routes so API route precedence is preserved; mount is a no-op when `web/dist` is absent. `@MX:NOTE` documents the ordering invariant.
- `api/Dockerfile` — converted to multi-stage: a `node:20-slim` build stage runs `npm ci && npm run build` against `web/`; the resulting `web/dist` is copied into the `python:3.12-slim` runtime stage via `COPY --from=web-build`. Node is present at build time only.
- `.dockerignore` — added `web/node_modules/` and `web/dist/` exclusions so stale host artifacts are not copied into the build context.
- `run_debug.sh` — browser-launcher `UI_PORT` default repointed from the obsolete port `3000` to `API_PORT` (`:8000`); obsolete "deferred UI service" comments removed.
- `run_server.sh` — prints "Chat UI available at http://127.0.0.1:${API_PORT:-8000}/" on ready.

---

### Added (SPEC-INFRA-001)

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

### Fixed

- **Model service never pulled the configured model** (regression from Phase 2b — `docker-compose.yml` had no model-pull step, and `MODEL` env var was not even forwarded to the `model` service). Stock `ollama/ollama:latest` only runs `ollama serve`; it does NOT auto-pull models on startup. Symptom: `/health` looped at `503 {"status":"loading"}` indefinitely because `OllamaAdapter.is_ready()` polled `/api/tags`, saw an empty model list, and never flipped `READY`. Repro: `./run_debug.sh` or `./run_server.sh` with default MODEL on a fresh `argus_ollama_models` volume. Fix:
  - `_model_entrypoint.sh` (new file at project root) — small `sh` wrapper bind-mounted into the `model` container as `/usr/local/bin/_model_entrypoint.sh`. Starts `ollama serve` in the background, polls for daemon ready (60s timeout, configurable via `ARGUS_OLLAMA_BOOT_WAIT`), pulls `$MODEL` if not already cached in the volume, then hands control to `ollama serve`. Idempotent — re-runs skip the pull when the model is already present.
  - `docker-compose.yml` — adds `MODEL: ${MODEL:-llama4:scout}` to the `model` service environment (was previously only on the `api` service), bind-mounts `_model_entrypoint.sh` read-only into the model container, and overrides the image's default entrypoint with the wrapper.
  - `.dockerignore` — excludes `_model_entrypoint.sh` from the api image build context (it's only used by the model container at runtime).
- **Unit and integration tests did not catch this** because unit tests mock the Ollama HTTP boundary (no real `/api/tags` call) and integration tests were never executed against a real Docker stack during the /moai run pipeline. Manual verification (Edge Case 1 procedure) would have caught it but was deferred to release-time.

### Changed

- `run_debug.sh`:
  - Unconditional `docker compose down --remove-orphans` before `docker compose up` so each debug invocation starts from a known-fresh container state. Named volume `argus_ollama_models` is preserved (no `--volumes` flag), so no model re-pull occurs. This intentionally departs from `run_server.sh`'s idempotency contract (REQ-INFRA-002 Scenario 5 applies to `run_server.sh` only).
  - Background browser-launcher: once `/health` returns 200, opens `http://127.0.0.1:${UI_PORT:-3000}/` in the default browser. Cross-platform: `open` (macOS), `xdg-open` (Linux), `cmd.exe /C start` (WSL/Windows). The UI service is deferred to a follow-up SPEC; the URL will not respond until that SPEC ships and adds a `web` service to `docker-compose.yml`. Set `NO_BROWSER=1` to skip the launch (headless / CI / remote-SSH runs).
- `run_server.sh`:
  - Stale-container detection added: probes `docker compose ps --status running` + `curl /health`. If containers exist but `/health` is unreachable within 3 s, runs `docker compose down --remove-orphans` (named volume preserved, no model re-pull) to recover before the existing `docker compose up -d`. If `/health` already responds 200, the existing idempotent fast-path is unchanged (Scenario 5 preserved).
- `.env.example` documents two new variables: `UI_PORT` (default `3000`, used by `run_debug.sh` browser-launch target) and `NO_BROWSER` (default `0`, set to `1` to skip the launch).
- `_docker_preflight.sh` (new file at project root) — sourced by both `run_server.sh` and `run_debug.sh`. Replaces the existing 4-line `if ! docker info` check with `ensure_docker_ready`, which:
  - **Auto-starts** Docker if installed but daemon is unreachable. macOS: launches Docker Desktop (`/Applications/Docker.app`), falls back to Colima (`colima start`), then OrbStack (`/Applications/OrbStack.app`). Linux-systemd: `sudo systemctl start docker`. WSL: cannot auto-start (daemon is on Windows host) — prints clear pointer.
  - **Force-installs** Docker if not present on supported platforms. macOS: prefers `brew install --cask docker` when brew is available, otherwise downloads `Docker.dmg` directly via `curl` + `hdiutil` + `sudo cp -R` to `/Applications`. Linux-systemd: detects `apt-get` / `dnf` / `pacman` and runs `sudo {pkg-mgr} install ...` followed by `sudo systemctl enable --now docker`. No confirmation prompt — invoking `./run_server.sh` is the consent; OS-level admin / sudo prompts still appear naturally during install. **Unsupported platforms** (`linux-other` without systemd, WSL) fall back to printing manual install instructions and `exit 1` — auto-install across the WSL/Windows boundary or non-systemd inits cannot be done reliably.
  - **Post-install wait** uses a longer default timeout (`ARGUS_DOCKER_WAIT_INSTALL`, default 180s) to accommodate Docker Desktop first-launch license/kernel-extension prompts on macOS.
  - Polls `docker info` for up to 60s after start attempt (configurable via `ARGUS_DOCKER_WAIT` env var).
  - Manual-install instructions cover Debian/Ubuntu (`apt-get`), Fedora/RHEL (`dnf`), Arch (`pacman`), macOS (Docker Desktop / Colima / OrbStack), and WSL (Docker Desktop on Windows host).
- `.dockerignore` extended: now excludes `_docker_preflight.sh` alongside `run_*.sh` (sourced helper, not needed inside the image).

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

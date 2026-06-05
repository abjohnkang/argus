# Acceptance Criteria — SPEC-INFRA-001

Given-When-Then acceptance scenarios for the Llama 4 runtime foundation. Each scenario maps to one or more REQ-INFRA-* requirements in `./spec.md`. A SPEC-INFRA-001 implementation is complete when every scenario below passes and the quality gates at the bottom are satisfied.

---

## Primary Scenarios

### Scenario 1: Cold start from clean Docker environment

Maps to: REQ-INFRA-002, REQ-INFRA-001

- **Given** a host with Docker and Docker Compose installed, no Argus containers running, no `argus_ollama_models` volume present, and the configured `MODEL` is the default `llama4:scout`,
- **When** the operator runs `scripts/run_server.sh`,
- **Then** Docker images for the `model` and `api` services are pulled,
- **And** the `llama4:scout` weights are downloaded into the named Docker volume `argus_ollama_models`,
- **And** both services reach a running state,
- **And** `curl http://127.0.0.1:8000/health` returns HTTP `200` with body `{"status": "ready"}`,
- **And** the named volume `argus_ollama_models` is non-empty (verifiable via `docker volume inspect`),
- **And** the script exits with code 0,
- **And** port 8000 is NOT bound on any non-loopback interface (verifiable via `lsof -iTCP:8000` or `ss -tlnp`).

### Scenario 2: Loading-state health response

Maps to: REQ-INFRA-003

- **Given** the `api` service is running but the `model` service has not yet finished loading `llama4:scout`,
- **When** a client issues `GET http://127.0.0.1:8000/health`,
- **Then** the response status code is `503`,
- **And** the response body is JSON of the form `{"status": "loading"}`,
- **And** no request is forwarded to the model runtime.

### Scenario 3: Streaming chat completions

Maps to: REQ-INFRA-001 (API surface), aligns with `./research.md` §5

- **Given** the API is in the `ready` state (Scenario 1 has completed),
- **When** a client issues `POST http://127.0.0.1:8000/v1/chat/completions` with `Content-Type: application/json` and body `{"model": "llama4:scout", "messages": [{"role": "user", "content": "ping"}], "stream": true}`,
- **Then** the response `Content-Type` is `text/event-stream`,
- **And** the response body is a sequence of SSE frames each prefixed `data: ` containing JSON chunks with token deltas,
- **And** the stream terminates with a final frame `data: [DONE]\n\n`,
- **And** at least one token chunk is delivered before the stream closes.

### Scenario 4: Non-localhost request rejection

Maps to: REQ-INFRA-005

- **Given** the API is running and ready,
- **When** a request arrives at `http://127.0.0.1:8000/v1/chat/completions` with a forged `Host: evil.example.com` header (or `Origin: http://evil.example.com`),
- **Then** the API responds with HTTP `403 Forbidden`,
- **And** the response body indicates the rejection reason,
- **And** no call is made to `api/inference.py` (verifiable via mock or log absence),
- **And** the rejection is logged with the offending header value.

### Scenario 5: Idempotent restart

Maps to: REQ-INFRA-002 (idempotency clause from `CONCEPT.md`)

- **Given** a healthy Argus stack started by a previous `scripts/run_server.sh` invocation (Scenario 1 outcome),
- **When** the operator runs `scripts/run_server.sh` a second time,
- **Then** the script exits with code 0,
- **And** no error is printed,
- **And** the stack remains healthy (`/health` still returns `200 {"status": "ready"}`),
- **And** the model weights are not re-downloaded (volume contents unchanged),
- **And** running containers are not recreated unnecessarily.

### Scenario 6: Model override via environment variable

Maps to: REQ-INFRA-004

- **Given** a clean Docker environment (no existing `argus_ollama_models` volume, no running containers) and `MODEL=llama3.2:3b` exported in the environment (or set in `.env`),
- **When** the operator runs `scripts/run_server.sh`,
- **Then** the `model` service pulls `llama3.2:3b` (verifiable in container logs),
- **And** `llama4:scout` is NOT pulled,
- **And** after the script returns, `curl http://127.0.0.1:8000/v1/models` lists `llama3.2:3b`,
- **And** `/v1/models` does NOT list `llama4:scout`,
- **And** no code, `Dockerfile`, or `docker-compose.yml` file was modified to achieve this.

---

## Edge Case Scenarios

### Edge case 1: Partial model download interrupted

Maps to: REQ-INFRA-002 (failure path), REQ-INFRA-003. Risk reference: Risk 2 in `./plan.md` §3.

- **Given** a model pull was interrupted mid-download (e.g., the `model` container was killed at 40% progress, leaving partial blobs in the volume),
- **When** the operator re-invokes `scripts/run_server.sh`,
- **Then** the model service resumes the pull from where it stopped (Ollama native resume behavior),
- **And** does NOT restart the download from zero,
- **And** eventually reaches the ready state,
- **And** `/health` transitions from `503 {"status": "loading"}` to `200 {"status": "ready"}` once the pull completes and the model loads.

### Edge case 2: Host port already in use

Maps to: REQ-INFRA-002 (failure path). Risk reference: Risk 5 in `./plan.md` §3.

- **Given** another process on the host is already bound to `127.0.0.1:8000`,
- **When** the operator runs `scripts/run_server.sh`,
- **Then** the script detects the Compose `up` failure,
- **And** exits with a non-zero exit code,
- **And** prints a clear error message identifying port 8000 as the cause,
- **And** does NOT leave the `model` service running while `api` is broken (no half-started state — either both come up or `model` is also torn down),
- **And** the user is told how to override the port via `API_PORT` env var.

---

## Quality Gate Criteria

### Performance targets

- **First-token latency** (POST `/v1/chat/completions` with `stream: true`, ready API, recommended-floor hardware per `./research.md` §3): ≤ 5 seconds for a 32-token prompt against a warm model. PASS if the median of 10 consecutive measurements is at or below the threshold; FAIL otherwise. The measured value is also recorded in the test report as the regression baseline. This is an initial threshold based on Llama 4 Scout token-rate reports in `./research.md` §1 (~20 tokens/sec on a 24 GB VRAM card with offload) and will be revised in a follow-up SPEC if hardware-class data warrants it.
- **Streaming throughput** on recommended-floor hardware: target ≥ 10 tokens/sec sustained. To be measured and recorded.
- **Cold-start time** (Scenario 1, excluding the model download itself): script returns within 60 seconds of the model finishing load. Model download time itself is unbounded — depends on network speed and model size — and is not a hard gate.

### Resource ceilings

- **`model` service memory**: documented per Llama variant (Scout Q4 baseline: ~32–67 GB resident per `./research.md` §1). No hard ceiling enforced in v1; Docker memory limits are not set.
- **`api` service memory**: ≤ 512 MB RSS under normal load. Verifiable via `docker stats`. If this is exceeded, the FastAPI app is leaking — investigate before merging.

### Code quality (TRUST 5)

- **Tested**: ≥ 85% coverage on `api/` Python code. All six primary scenarios and both edge cases pass.
- **Readable**: `ruff` clean on `api/`. ShellCheck clean on `scripts/`.
- **Unified**: `black` and `isort` applied to `api/`. Consistent shell style in `scripts/`.
- **Secured**: No bind to `0.0.0.0` anywhere. No secrets in `.env.example`. `.env` is gitignored. Header-validation middleware exercised by Scenario 4 — no bypass paths.
- **Trackable**: All commits reference `SPEC-INFRA-001`. MX tags placed per `./spec.md` MX Tag Plan.

### Definition of Done

A `/moai run SPEC-INFRA-001` execution is complete when all of the following are true:

- [ ] All six primary scenarios pass against a real `docker compose up` stack.
- [ ] Both edge case scenarios pass.
- [ ] All five REQ-INFRA-* requirements have at least one passing test or scenario covering them.
- [ ] `api/` test coverage ≥ 85%.
- [ ] Localhost bind verified: `lsof`/`ss` shows port 8000 bound only on the loopback interface.
- [ ] Named volume `argus_ollama_models` survives `docker compose down` and is reused on the next `up`.
- [ ] `scripts/run_server.sh` exits 0 on a clean run AND on a re-run against a healthy stack.
- [ ] `MODEL=llama3.2:3b` override works end-to-end with zero source-file modifications.
- [ ] `@MX:ANCHOR`, `@MX:WARN`, and `@MX:NOTE` tags placed per `./spec.md` MX Tag Plan.
- [ ] No item from the `./spec.md` Exclusions list was implemented.

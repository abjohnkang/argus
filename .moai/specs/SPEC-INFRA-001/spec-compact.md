# SPEC-INFRA-001 — Compact

Auto-generated companion to `./spec.md`. Contains only EARS requirements, acceptance criteria, files to modify, and exclusions. For overview, technical approach, MX plan, and research context, see `./spec.md` and `./research.md`.

---

## Requirements (EARS)

### REQ-INFRA-001 (Ubiquitous)

The Argus runtime SHALL serve Llama 4 Scout inference via an HTTP API running inside a Docker container, with the API process binding only to `127.0.0.1` and the host port mapping using `127.0.0.1:PORT:PORT` (never `0.0.0.0:PORT:PORT`).

### REQ-INFRA-002 (Event-driven)

WHEN `scripts/run_server.sh` is invoked on a host with no existing Argus containers, the system SHALL pull the required Docker images, download the configured model weights into a named Docker volume, start the `model` and `api` services, and return from the script only after `GET /health` reports HTTP 200.

### REQ-INFRA-003 (State-driven)

WHILE the model is still loading, the HTTP API SHALL respond to `GET /health` with HTTP `503` and a JSON body of the form `{"status": "loading"}`; only after the model is fully ready SHALL `GET /health` respond with HTTP `200` and `{"status": "ready"}`.

### REQ-INFRA-004 (Optional feature, WHERE)

WHERE the operator sets the `MODEL` environment variable to a non-default value (e.g., `MODEL=llama3.2:3b`), the system SHALL pull and serve that model in place of `llama4:scout`, with no edits required to any source file, `docker-compose.yml`, or `Dockerfile`.

### REQ-INFRA-005 (Unwanted behavior, IF…THEN)

IF the HTTP API receives a request whose `Host` header value or whose `Origin` header host component (after URL parsing) is not exactly one of the literal strings `127.0.0.1`, `localhost`, or `[::1]` (port suffix and trailing dot tolerated, no DNS resolution performed), THEN the system SHALL reject the request with HTTP `403 Forbidden`, SHALL NOT invoke the model runtime, and SHALL log the rejection with the offending header value.

---

## Acceptance Criteria

### Scenario 1: Cold start from clean Docker environment

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

- **Given** the `api` service is running but the `model` service has not yet finished loading `llama4:scout`,
- **When** a client issues `GET http://127.0.0.1:8000/health`,
- **Then** the response status code is `503`,
- **And** the response body is JSON of the form `{"status": "loading"}`,
- **And** no request is forwarded to the model runtime.

### Scenario 3: Streaming chat completions

- **Given** the API is in the `ready` state (Scenario 1 has completed),
- **When** a client issues `POST http://127.0.0.1:8000/v1/chat/completions` with `Content-Type: application/json` and body `{"model": "llama4:scout", "messages": [{"role": "user", "content": "ping"}], "stream": true}`,
- **Then** the response `Content-Type` is `text/event-stream`,
- **And** the response body is a sequence of SSE frames each prefixed `data: ` containing JSON chunks with token deltas,
- **And** the stream terminates with a final frame `data: [DONE]\n\n`,
- **And** at least one token chunk is delivered before the stream closes.

### Scenario 4: Non-localhost request rejection

- **Given** the API is running and ready,
- **When** a request arrives at `http://127.0.0.1:8000/v1/chat/completions` with a forged `Host: evil.example.com` header (or `Origin: http://evil.example.com`),
- **Then** the API responds with HTTP `403 Forbidden`,
- **And** the response body indicates the rejection reason,
- **And** no call is made to `api/inference.py` (verifiable via mock or log absence),
- **And** the rejection is logged with the offending header value.

### Scenario 5: Idempotent restart

- **Given** a healthy Argus stack started by a previous `scripts/run_server.sh` invocation (Scenario 1 outcome),
- **When** the operator runs `scripts/run_server.sh` a second time,
- **Then** the script exits with code 0,
- **And** no error is printed,
- **And** the stack remains healthy (`/health` still returns `200 {"status": "ready"}`),
- **And** the model weights are not re-downloaded (volume contents unchanged),
- **And** running containers are not recreated unnecessarily.

### Scenario 6: Model override via environment variable

- **Given** a clean Docker environment (no existing `argus_ollama_models` volume, no running containers) and `MODEL=llama3.2:3b` exported in the environment (or set in `.env`),
- **When** the operator runs `scripts/run_server.sh`,
- **Then** the `model` service pulls `llama3.2:3b` (verifiable in container logs),
- **And** `llama4:scout` is NOT pulled,
- **And** after the script returns, `curl http://127.0.0.1:8000/v1/models` lists `llama3.2:3b`,
- **And** `/v1/models` does NOT list `llama4:scout`,
- **And** no code, `Dockerfile`, or `docker-compose.yml` file was modified to achieve this.

### Edge case 1: Partial model download interrupted

- **Given** a model pull was interrupted mid-download (e.g., the `model` container was killed at 40% progress, leaving partial blobs in the volume),
- **When** the operator re-invokes `scripts/run_server.sh`,
- **Then** the model service resumes the pull from where it stopped (Ollama native resume behavior),
- **And** does NOT restart the download from zero,
- **And** eventually reaches the ready state,
- **And** `/health` transitions from `503 {"status": "loading"}` to `200 {"status": "ready"}` once the pull completes and the model loads.

### Edge case 2: Host port already in use

- **Given** another process on the host is already bound to `127.0.0.1:8000`,
- **When** the operator runs `scripts/run_server.sh`,
- **Then** the script detects the Compose `up` failure,
- **And** exits with a non-zero exit code,
- **And** prints a clear error message identifying port 8000 as the cause,
- **And** does NOT leave the `model` service running while `api` is broken (no half-started state — either both come up or `model` is also torn down),
- **And** the user is told how to override the port via `API_PORT` env var.

---

## Files to Be Created or Modified

- `docker-compose.yml`
- `api/Dockerfile`
- `api/main.py`
- `api/inference.py`
- `api/requirements.txt`
- `scripts/run_server.sh`
- `scripts/run_debug.sh`
- `.env.example`
- `.dockerignore`

---

## Exclusions (What NOT to Build)

- No React web UI (separate SPEC).
- No conversation persistence — no chat history, no session storage.
- No bearer token or session auth (v1 threat model is `127.0.0.1` bind + non-localhost header rejection).
- No vLLM support (server-class tool, rejected for personal hardware).
- No Llama 4 Maverick or Behemoth support (hardware out of reach).
- No llama.cpp escape hatch in v1 (documented as future overlay).
- No agent tools (file I/O sandbox, web fetch, code execution).
- No automatic hardware preflight.
- No rate limiting.

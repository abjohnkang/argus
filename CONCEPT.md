# Argus — Concept

## Vision

On-device AI agent built on Llama 4. All inference, memory, and tools run
locally; the runtime makes no outbound network calls after initial setup.

## Non-goals

- No cloud inference, no hosted model fallback.
- No telemetry, no usage analytics.
- No remote configuration.

## Runtime

- All services run inside Docker via `docker-compose.yml` so the host
  environment stays untouched.
- Model runtime: _decision pending — candidates: Ollama, llama.cpp server, vLLM_.
- Model: Llama 4, _variant pending_.
- Target hardware: _minimum spec pending_.

## Entry scripts

- `run_server.sh` — start the full stack.
- `run_debug.sh` — same, with debug logging surfaced.
- Both must be idempotent: pull/build images and download model weights on
  first run, no-op on subsequent runs.

## First milestone

A local web chat UI (ChatGPT-style) backed by the local model. The web UI
is built with React. Agent capabilities (tools, memory, scheduling) follow
in later milestones.

## Open questions

1. Model runtime and Llama 4 variant.
2. Minimum hardware target.
3. Where model weights and chat history are persisted.
4. Auth model for the local web UI (bind to `127.0.0.1` only? token auth?).
5. React framework choice (bare Vite vs Next.js) and streaming transport
   (SSE vs WebSocket).

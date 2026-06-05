# Project Interview

## Round 0: Project Classification

Question: Project type confirmation (no source code detected).
Answer: New Project. Repository contains only docs (README.md, CONCEPT.md, LICENSE) and MoAI scaffolding. Documentation will be generated from interview answers and CONCEPT.md.

## Round 1: Vision

Question: Who is Argus primarily for?
Answer: Privacy-focused individuals running offline AI on personal hardware. Argus is a single-user product whose defining promise is that no data leaves the device. UX, defaults, and scope all derive from this audience: simple Docker install, Mac/Linux desktop targets, no auth complexity, conversation history stored only on the local device.

## Round 2: Technology

Question: Primary backend technology stack? (React frontend already locked in.)
Answer: Python (FastAPI) + React + Docker. Chosen for the strongest Llama 4 ecosystem (transformers, llama-cpp-python, Ollama clients) and clean SSE/WebSocket streaming via FastAPI. Backend in Python, UI in React, all services orchestrated via docker-compose so the host environment stays untouched.

## Round 3: Scope

Question: First milestone scope?
Answer: Chat UI + local Llama 4 streaming inference. Smallest demo-worthy vertical slice — open a browser, type a message, see Llama 4 stream a response from the local container. Out of scope for the first milestone: persistence, authentication, agent tools (file I/O, web fetch), multi-user.

## Source Context

- CONCEPT.md: Argus project concept (vision, non-goals, runtime, entry scripts, first milestone, open questions).
- README.md: "On-Device AI agent... 24/7 vigilance... without ever sending a single byte of data to the cloud."

## Open Questions Carried Forward

These were enumerated in CONCEPT.md and remain unresolved. They will be addressed in the next SPEC (runtime foundation):

1. Model runtime: Ollama vs llama.cpp server vs vLLM.
2. Llama 4 variant (Scout / Maverick / specific quantization).
3. Minimum hardware target (RAM, GPU, CPU baseline).
4. Persistence story for model weights cache and (future) chat history.
5. Local web UI auth model (bind to 127.0.0.1 only, token, etc.).
6. React framework wrapper (bare Vite vs Next.js) and streaming transport (SSE vs WebSocket).

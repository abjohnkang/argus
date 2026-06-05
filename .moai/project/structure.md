# Argus — Project Structure

This document describes the intended directory layout for Argus. The project has no source code yet. All paths marked **[planned]** do not exist on disk. Paths marked **[exists]** are present in the current repository.

---

## Current Repository Contents

The repository currently contains only scaffolding and concept documents:

```
argus/
├── README.md           [exists]  Public project summary
├── CONCEPT.md          [exists]  Vision, non-goals, runtime decisions, open questions
├── CLAUDE.md           [exists]  MoAI execution directives and project rules
├── LICENSE             [exists]  License file
├── .gitignore          [exists]
├── .mcp.json           [exists]  MCP server configuration
├── .moai/              [exists]  MoAI scaffolding (config, specs, project docs)
└── .claude/            [exists]  Claude Code agent definitions, rules, and skills
```

No source code directories (`api/`, `web/`, `scripts/`) exist yet. They will be created during the runtime foundation SPEC implementation.

---

## Planned Directory Layout

```
argus/
├── api/                [planned]  Python FastAPI backend
├── web/                [planned]  React frontend
├── scripts/            [planned]  Entry and utility shell scripts
├── compose/            [planned]  Docker Compose and container configuration (alt: root-level)
├── docs/               [planned]  User-facing documentation (optional, may skip if README suffices)
├── .moai/              [exists]   MoAI scaffolding
├── .claude/            [exists]   Claude Code configuration
├── README.md           [exists]
├── CONCEPT.md          [exists]
├── CLAUDE.md           [exists]
├── LICENSE             [exists]
├── .gitignore          [exists]
└── .mcp.json           [exists]
```

Note: `docker-compose.yml` may live at the repository root or inside `compose/`. This is an open decision to be resolved in the runtime foundation SPEC.

---

## Planned Directory Purposes

### `api/` [planned]

Python FastAPI backend. Responsible for:

- Receiving chat requests from the React frontend
- Forwarding prompts to the local model runtime
- Streaming responses back to the client (SSE or WebSocket — transport TBD)
- Health check and readiness endpoints

Expected internal structure (subject to SPEC):

```
api/
├── app/
│   ├── main.py         Entry point, FastAPI application factory
│   ├── routers/        Route definitions (chat, health)
│   ├── services/       Model client and inference logic
│   └── models/         Pydantic request/response schemas
├── Dockerfile
└── requirements.txt    (or pyproject.toml)
```

### `web/` [planned]

React frontend. Responsible for:

- Chat UI (message input, streaming response display)
- Connecting to the FastAPI backend for inference
- Serving as the only user-facing interface

React framework choice (bare Vite vs Next.js) is an open decision. Expected internal structure depends on that choice and will be defined in the runtime foundation SPEC.

```
web/
├── src/
│   ├── components/     React components (chat window, message bubble, input)
│   ├── hooks/          Custom React hooks (streaming, state)
│   └── main.tsx        Application entry point
├── public/
├── Dockerfile
├── package.json
└── tsconfig.json
```

### `scripts/` [planned]

Shell scripts for operating the stack:

- `run_server.sh` — Start the full stack. Idempotent: pulls and builds Docker images, downloads model weights on first run; no-op on subsequent runs.
- `run_debug.sh` — Same as `run_server.sh` with debug logging surfaced.

Both scripts are the primary entry points for users. They require only Docker and Docker Compose to be installed on the host.

### `compose/` or root `docker-compose.yml` [planned]

Docker Compose configuration orchestrating all services (`api`, `web`, model runtime container). Placement (root vs `compose/` subdirectory) is an open decision to be resolved in the runtime foundation SPEC.

### `docs/` [planned, optional]

User-facing documentation beyond the README. May include installation guides, hardware requirements, and usage instructions. This directory will only be created if README.md proves insufficient.

### `.moai/` [exists]

MoAI-ADK scaffolding. Contains:

- `config/` — Project configuration (quality, language, user, design settings)
- `specs/` — SPEC documents (requirements, acceptance criteria)
- `project/` — Living project documentation (`product.md`, `structure.md`, `tech.md`)

### `.claude/` [exists]

Claude Code configuration. Contains agent definitions, rules, skills, and hooks used by MoAI-ADK during development.

---

## Notes on Layout Decisions

- The `api/` and `web/` split reflects the clear backend/frontend separation and allows each service to have its own `Dockerfile`.
- All services are containerized. The host filesystem is not modified by running Argus.
- The planned structure is conservative: directories are created when their SPEC is implemented, not speculatively.
- Exact internal structures within `api/` and `web/` will be defined in the runtime foundation SPEC.

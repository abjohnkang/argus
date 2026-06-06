# Research — SPEC-UI-001 (Argus React Chat UI)

Deep codebase analysis underpinning SPEC-UI-001. This document is the decision
record: every requirement, exclusion, and plan task in the sibling files traces
back to a finding here. SPEC-UI-001 consumes the API contract delivered by
SPEC-INFRA-001 and adds a browser-based chat front end that completes the
first-milestone vertical slice. No backend behavior changes beyond mounting
static-file serving in the existing `api` service.

All file:line references are against the tree as it exists on the
`feature/SPEC-INFRA-001-runtime-foundation` branch at the time of writing.

---

## 1. The SSE Streaming Format the UI Must Parse (central contract)

The UI's hardest technical job is parsing the streaming response. The exact
wire format is fixed by SPEC-INFRA-001 and must not be guessed.

### 1.1 Where the format is produced

`api/inference.py::OllamaAdapter.chat_completion_stream` (`api/inference.py:114-210`)
streams the response. The framing is established at `api/inference.py:199`:

```python
yield f"data: {line}\n\n".encode()
```

where `line` is a single raw NDJSON line from Ollama's `POST /api/chat`
(`stream: true`) response (`api/inference.py:193`). The adapter deliberately
does **not** reshape the JSON (`api/inference.py:196-198`: "Pass the raw Ollama
JSON through ... we deliberately don't reshape it here").

The stream always terminates with a sentinel frame at `api/inference.py:210`:

```python
yield b"data: [DONE]\n\n"
```

### 1.2 The exact JSON shape inside each `data:` frame

Because the adapter passes Ollama's `/api/chat` NDJSON through untouched, each
non-sentinel frame's payload is an Ollama chat-streaming object, **not** the
OpenAI `choices[].delta` shape. The token text lives at `message.content`:

```
data: {"model":"llama4:scout","created_at":"...","message":{"role":"assistant","content":"Hel"},"done":false}

data: {"model":"llama4:scout","created_at":"...","message":{"role":"assistant","content":"lo"},"done":false}

data: {"model":"...","created_at":"...","message":{"role":"assistant","content":""},"done":true,"total_duration":...}

data: [DONE]
```

[CRITICAL FINDING] The token text the UI must accumulate is at
`frame.message.content`, NOT `frame.choices[0].delta.content`. The README and
`product.md` describe the endpoint as "OpenAI-compatible", but the SSE frames
that actually flow through Argus's `api` service are Ollama-native because of
the pass-through at `api/inference.py:199`. The UI's stream parser MUST read
`message.content`. Acceptance criteria are written against this real shape.

The model name is available on every frame at `frame.model` — this is the
source for the "current model name" UI display (REQ-UI-005 supporting detail).

### 1.3 Error frames in-band

Mid-stream failures are signalled in-band, not by HTTP status. At
`api/inference.py:202`:

```python
yield b'data: {"error": "upstream stream broken"}\n\n'
```

So a frame may carry `{"error": "..."}` instead of `{"message": {...}}`. The UI
parser MUST treat a frame containing an `error` key as a stream failure: stop
accumulating, surface the error, retain partial output. The empty-stream case
(`api/main.py:222-227`) sends only `data: [DONE]` with no content frames.

Pre-stream failures DO use HTTP status: `api/main.py:197-234` drives the
generator past its first chunk before returning `StreamingResponse`, so an
`OllamaUnavailable` raised pre-stream becomes `HTTP 502` with a JSON body
(`api/main.py:214-220`). The UI must therefore handle two failure modes:
(a) non-OK HTTP status on the initial response (e.g. 502, 503), and
(b) an in-band `{"error": ...}` SSE frame after a 200 response began.

### 1.4 Decision: how the UI consumes the SSE stream

[DECISION POINT 1 — central technical risk]

The endpoint is `POST /v1/chat/completions` (`api/main.py:197`). The browser's
native `EventSource` API **cannot** be used: `EventSource` only issues GET
requests and exposes no way to send a JSON request body. This is the single
most important UI-side technical constraint.

Options considered:

| Option | Verdict |
|---|---|
| Native `EventSource` | REJECTED — GET-only, cannot POST a body. Disqualified by the endpoint shape. |
| `fetch()` + `ReadableStream` reader, manual SSE frame parsing | RECOMMENDED — `fetch` supports POST + body, returns `response.body` as a `ReadableStream<Uint8Array>`; an `AbortController` cleanly cancels the in-flight stream (REQ-UI-004). |
| Third-party SSE-over-POST library (e.g. `@microsoft/fetch-event-source`) | VIABLE but adds a dependency for ~60 lines of parsing logic. Deferred — keep the demo slice dependency-light; revisit only if manual parsing proves fragile. |

**Recommendation:** `fetch()` + `response.body.getReader()` with a manual SSE
frame splitter. The parser reads `Uint8Array` chunks, decodes via `TextDecoder`,
buffers across chunk boundaries, splits on the SSE frame delimiter `\n\n`, strips
the `data: ` prefix, recognises the `[DONE]` sentinel, and `JSON.parse`s each
remaining payload to extract `message.content`. An `AbortController` passed to
`fetch` is aborted by the Stop button (REQ-UI-004) and on component unmount.

[RISK] Chunk boundaries do not align with SSE frame boundaries. A single TCP
read may deliver half a frame or several frames at once. The parser MUST keep a
residual buffer and only consume complete `\n\n`-terminated frames, carrying the
remainder forward. This is the most likely source of subtle bugs and is called
out as a named risk in `plan.md` §3.

### 1.5 Token-rate expectations

`product.md:13` and `tech.md` set the hardware floor at 64 GB unified memory.
SPEC-INFRA-001 `acceptance.md` records a first-token-latency target of <=5s and
a streaming-throughput target of >=10 tokens/sec on recommended-floor hardware.
The UI must render incrementally fast enough to keep up with ~10-20 tokens/sec
without jank — i.e. append-and-repaint per frame is acceptable; no need for
virtualisation at demo scale (single conversation, bounded length).

---

## 2. The Readiness / Loading State Contract

[DECISION POINT 2]

`GET /health` (`api/main.py:168-173`) returns:
- `503 {"status": "loading"}` while the background poller has not yet confirmed
  the model is resident (`api/main.py:172-173`),
- `200 {"status": "ready"}` once ready (`api/main.py:171-172`).

The transition is driven by `ReadinessTracker` (`api/state.py`) flipped by the
background poller `_readiness_poller` (`api/main.py:110-124`), which calls
`OllamaAdapter.is_ready()` (`api/inference.py:62-92`). On a cold first run this
can take from seconds (model cached) to an hour (32-67 GB Scout pull over a slow
link, per `api/inference.py:71-77` `@MX:WARN`).

**Recommendation:** the UI polls `GET /health` on load and on an interval
(e.g. every 2s) until it observes `200 {"status":"ready"}`. WHILE the response
is `503`, the UI shows a clear "Model is loading…" state and **disables the
message input and send control** (REQ-UI-003). Once `200` is observed, the UI
enables input and may stop or slow polling. The UI MUST degrade gracefully for
the full possible duration of a multi-GB pull — i.e. no spinner-timeout that
gives up; "loading" is a legitimate long-lived state, not an error.

[FINDING] There is no progress percentage exposed by `/health` — it is binary
(loading/ready). The pull progress lives only in `docker compose logs model`
(`run_server.sh:74`). The UI therefore cannot show a download percentage; it can
only show an indeterminate "loading" state. This is a deliberate scope boundary,
not a gap to fix in this SPEC.

---

## 3. Abort / Stop-Generation Handling

[DECISION POINT 3]

REQ-UI-004 requires a Stop button that aborts the in-flight stream and retains
partial output. With the `fetch` + `ReadableStream` approach (§1.4), this is a
clean `AbortController`:

1. Before `fetch`, create `const controller = new AbortController()` and pass
   `signal: controller.signal`.
2. The Stop button calls `controller.abort()`.
3. The reader loop catches the resulting `AbortError`, stops accumulating, and
   leaves the already-rendered partial assistant message in place (do NOT clear
   it — REQ-UI-004 explicitly retains partial output).
4. The same controller is aborted on component unmount to avoid a leaked stream.

[RISK — stop-button race] `controller.abort()` may land between two reads. The
loop must distinguish an intentional abort (`AbortError` / `signal.aborted`)
from a genuine network failure so it does not render a spurious error banner on
a user-initiated stop. This is a named risk in `plan.md` §3. Treatment: branch
on `signal.aborted` in the catch — if aborted, finalise the partial message
silently; otherwise surface the error (REQ-UI-005).

No backend change is needed for Stop: aborting the `fetch` closes the client
side of the HTTP connection; the server-side generator's `finally` blocks
(`api/inference.py:203-209`) clean up the upstream Ollama connection.

---

## 4. Static-Serving Build Integration (how the bundle reaches the api image)

[DECISION POINT 4 — the real backend-touching decision]

The confirmed architecture: Vite builds the React app to a static bundle, and
the **existing** FastAPI `api` service serves it via `StaticFiles`. No new
container, no nginx, no Node runtime in production. Two sub-decisions:

### 4.1 How the built assets get INTO the api image

The `api` image is built from `api/Dockerfile` (`api/Dockerfile:20-42`), a
single-stage `python:3.12-slim` build. The build context is the project root
(`docker-compose.yml:42-43`: `context: .`, `dockerfile: api/Dockerfile`). The
`.dockerignore` currently excludes `*.md`, `.moai/`, `.claude/`, `.venv/`,
`run_*.sh` (per `structure.md:109`).

Options:

| Option | Description | Trade-off |
|---|---|---|
| **A. Multi-stage Dockerfile** (RECOMMENDED) | Add a first `node:20-slim` build stage to `api/Dockerfile` that runs `npm ci && npm run build` against `web/`, then `COPY --from=build /web/dist /app/web/dist` into the python stage. | Self-contained: `docker compose build` produces a working image with zero host Node install. Honors "host untouched" (`product.md:23`). Cost: larger build context (`web/` source is included; add `web/node_modules/` to `.dockerignore`), longer cold build, Node pulled at build time only (not runtime). |
| B. Pre-build on host, COPY dist | Developer runs `vite build` on the host, commits/stages `web/dist`, Dockerfile copies it. | Simpler Dockerfile, but REQUIRES host Node — violates the "no Node to run Argus" stance (`tech.md:104-112`). Rejected for the default path. |
| C. Bind-mount dist at runtime | Mount `web/dist` into the running container. | Couples runtime to a host build artifact; brittle; rejected. |

**Recommendation: Option A (multi-stage Dockerfile).** It keeps the single
`docker compose build` / `./run_server.sh` flow intact (`run_server.sh:62`
`docker compose up -d` triggers the build) and requires no host Node, matching
the "host environment untouched" constitutional value (`product.md:23`). The
trade-off (longer first build, larger context) is surfaced in `plan.md` §3.

`.dockerignore` must be amended to stop ignoring `web/` source while still
ignoring `web/node_modules` and `web/dist` from the *python-stage* context (the
node stage produces dist internally). This is a [MODIFY] delta on `.dockerignore`.

### 4.2 How FastAPI serves the bundle

[FINDING — middleware interaction] Mounting `StaticFiles` at `/` in
`api/main.py` means the SPA is served from the **same origin** as the API
(`http://127.0.0.1:8000`). This is significant for `LocalhostOnlyMiddleware`
(`api/main.py:67-102`): browser requests for the page and for `fetch('/v1/...')`
both carry `Host: 127.0.0.1:8000`, and same-origin `fetch` carries
`Origin: http://127.0.0.1:8000` — both pass `is_localhost_header`
(`api/security.py:44-60`) cleanly. Serving the SPA from the api origin therefore
keeps the entire app same-origin and middleware-clean, with no CORS config and
no middleware weakening. This is a strong argument FOR the chosen architecture
and is recorded as such — REQ-UI-001 must NOT relax the middleware.

Implementation: `app.mount("/", StaticFiles(directory="web/dist", html=True), name="spa")`
registered AFTER the `/health`, `/v1/models`, `/v1/chat/completions` routes so
API routes take precedence and the catch-all SPA mount handles everything else
(serving `index.html` for the root and client-side routes). `html=True` makes
`/` serve `index.html`. This is the only change to `api/main.py` and the only
new runtime dependency is `StaticFiles` (already bundled in Starlette via
FastAPI — no new pip requirement). [MODIFY] delta on `api/main.py`.

[RISK] Mount ordering: if `StaticFiles` is mounted before the API routes, it
would shadow them. The mount MUST come last. Named in `plan.md` §3.

---

## 5. Brand Tokens for Tailwind

[DECISION POINT 5]

`.moai/project/brand/visual-identity.md` and `brand-voice.md` are both `_TBD_`
placeholders (`visual-identity.md:3`, `brand-voice.md:3`) — the brand interview
(`/moai design`) has not been run. Every color, font, and layout field is `_TBD_`.

[FINDING] There are no concrete brand tokens to map. Rather than block this SPEC
on the brand interview (out of scope here), the recommendation is:

- Define a **neutral, ChatGPT-like default token set** in `web/tailwind.config`
  using Tailwind's built-in neutral/zinc grays, a single restrained accent for
  the send button and focus rings, system-ui / a self-hosted sans for body, and
  a self-hosted mono for code blocks.
- Structure the Tailwind theme so brand tokens slot in later: expose semantic
  CSS-variable-backed tokens (`--color-bg`, `--color-surface`, `--color-accent`,
  `--color-text`, `--font-sans`, `--font-mono`) so that WHEN the brand interview
  populates `visual-identity.md`, a follow-up change only edits the variable
  values, not every component.
- Honor `font_source` once defined; until then, fonts MUST be **self-hosted /
  bundled** (no Google Fonts CDN) to satisfy the no-external-call rule (§6).

This keeps the demo unblocked while leaving a clean seam for brand adoption. The
"map brand tokens" requirement is satisfied structurally (the seam exists);
concrete values await the brand interview and are noted as such in `spec.md`.

---

## 6. The No-External-Call Constraint (privacy by architecture)

`product.md:19` ("Privacy by architecture, not by policy") and `CLAUDE.md`
("no data ever leaves the device") make zero outbound runtime network calls a
hard requirement, not a setting. For the UI this means:

[FINDING] Every asset must be bundled and served locally. Concretely:
- **No CDN fonts** (no `fonts.googleapis.com`, no `fonts.bunny.net` at runtime).
  Fonts are self-hosted in `web/` and bundled by Vite, or pure `system-ui`.
- **No CDN scripts / no external CSS.** All JS/CSS is bundled by Vite into the
  static output served by `api`.
- **No analytics, no telemetry, no remote config, no error-reporting SaaS.**
- The only network destination the running UI may contact is the local Argus
  `api` on the same origin (`http://127.0.0.1:8000`) — same-origin `fetch` to
  `/health`, `/v1/chat/completions`, and optionally `/v1/models`.

Verification approach (feeds `acceptance.md`): a build-time / review check that
the bundled output contains no absolute `http(s)://` references to non-localhost
hosts, plus a runtime check (DevTools Network panel or a `connect-src 'self'`
Content-Security-Policy meta) showing no off-origin requests. A strict CSP
(`default-src 'self'`) is recommended as defense-in-depth and is cheap to add.

---

## 7. Markdown + Code-Block Rendering Library Choice

[DECISION POINT 6]

REQ-UI requires markdown rendering of assistant messages including code blocks.

| Option | Verdict |
|---|---|
| **`react-markdown` (`/remarkjs/react-markdown`)** + `remark-gfm` | RECOMMENDED — high source reputation, large install base, React-native (renders to React elements, not `dangerouslySetInnerHTML`), plugin model for GFM (tables, fenced code). Pin major version `^9` (current production-stable v9.x). |
| `markdown-to-jsx` | Lighter, but smaller ecosystem for our code-highlighting needs; deferred. |
| Hand-rolled regex markdown | Rejected — fragile, reinvents a solved problem. |

Code-block syntax highlighting: pair `react-markdown` with a code component that
uses a highlighter. Two sub-options:
- `react-syntax-highlighter` (Prism-backed) — mature, but ships large language
  packs; must use the light build + import only needed languages to keep bundle
  small (relevant to the offline-bundle-size risk in `plan.md` §3).
- `rehype-highlight` (highlight.js via rehype plugin) — simpler integration with
  `react-markdown`, single bundled stylesheet. RECOMMENDED for the demo slice
  for its smaller footprint and clean plugin wiring.

**Recommendation:** `react-markdown@^9` + `remark-gfm@^4` + `rehype-highlight@^7`,
all bundled (highlight.js theme CSS imported locally, not from CDN — §6). Pin
major versions only, production-stable, no alpha/beta. Streaming-safe: re-render
the markdown of the accumulating assistant text on each frame; react-markdown
handles incremental/incomplete markdown (e.g. an unclosed code fence) gracefully
by rendering best-effort, which is acceptable mid-stream and resolves when the
final frame arrives.

[RISK] Re-parsing the full markdown string on every token frame is O(n) per
frame, O(n^2) over a message. At demo message sizes (hundreds to low-thousands
of tokens) this is fine; if it janks, debounce markdown re-render to animation
frames. Noted in `plan.md` §3, not pre-optimised.

---

## 8. Frontend Stack & Version Pins

[DECISION POINT 7]

| Layer | Choice | Pin | Rationale |
|---|---|---|---|
| Framework | React | `^18.3` | Most production-stable React line; conservative for a demo slice. `tech.md:23-24` locks React + TypeScript; framework wrapper deferred to this SPEC, and bare Vite (not Next.js) is chosen — no SSR need, static bundle only. |
| Language | TypeScript | `^5` | Type-safe per `tech.md:24`. |
| Build tool | Vite | `^5` | Static-bundle build, fast, first-class React + TS. v5 chosen as the proven stable line (v7 exists but v5 is the safe default for a demo); `base` config lets the bundle be served from `/`. |
| Styling | Tailwind CSS | `^3.4` | Confirmed in scope. v3.4 is the production-proven line (v4 is newer; 3.4 chosen for stability). |
| Markdown | react-markdown | `^9` | §7. |
| Markdown GFM | remark-gfm | `^4` | §7. |
| Code highlight | rehype-highlight | `^7` | §7. |

All pins are major-version (`^`) only — no alpha/beta, no exact patch pins —
matching the SPEC-INFRA-001 house rule (`api/requirements.txt`,
`plan.md:30-31` "Major-version pins only").

Vite config notes: `base: '/'` so assets resolve from the api-served root; a dev
proxy (`server.proxy`) forwards `/v1` and `/health` to `http://127.0.0.1:8000`
during `vite dev` so the dev experience matches production same-origin behavior
without tripping the localhost middleware. The dev proxy is a dev-only
convenience and ships nothing to production.

---

## 9. Files Touched Summary (feeds spec.md "Files to Be Created or Modified")

New (`web/` source + config) — all [NEW]:
- `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`,
  `web/tailwind.config.ts`, `web/postcss.config.js`, `web/index.html`,
  `web/src/main.tsx`, `web/src/App.tsx`, `web/src/index.css`,
  `web/src/lib/sseClient.ts` (the fetch+ReadableStream SSE parser — the central
  module), `web/src/lib/health.ts` (readiness polling),
  `web/src/components/*` (ChatView, MessageList, MessageBubble, Composer,
  StopButton, LoadingState, ModelBadge — exact split decided in `/moai run`).

Modified (existing `api` service) — [MODIFY] deltas against SPEC-INFRA-001:
- `api/main.py` — mount `StaticFiles(directory="web/dist", html=True)` at `/`
  AFTER the API routes (§4.2).
- `api/Dockerfile` — add `node:20-slim` build stage running `vite build`, then
  `COPY --from=build` the dist into the python stage (§4.1, Option A).
- `.dockerignore` — `web/` source has no existing exclusion (already in the
  build context); ADD `web/node_modules/` (optionally `web/dist/`) exclusions so a
  stale host build artifact is not copied into the context (§4.1).

No change to `docker-compose.yml` is required (same `api` service, same single
host port mapping `127.0.0.1:8000` — `docker-compose.yml:46-47`). No change to
`api/inference.py`, `api/security.py`, `api/state.py`, `run_server.sh`,
`run_debug.sh`.

---

## 10. Open Items Deferred (NOT decided here, NOT in this SPEC)

- Concrete brand color/font tokens — await `/moai design` brand interview (§5).
- Model picker / multi-model UX — explicitly excluded (single conversation,
  no picker). `/v1/models` may be read only to display the active model name.
- Conversation persistence / history — excluded by the project no-persistence
  rule (`product.md`, `CONCEPT.md`).
- Mobile-specific layout, settings panel, auth — all excluded.
- Performance hardening (markdown debounce, stream virtualisation) — only if
  measured jank appears; not pre-optimised.

---

## Decision Summary

| # | Decision | Recommendation |
|---|---|---|
| 1 | SSE consumption | `fetch()` + `ReadableStream` reader + manual frame parser (EventSource cannot POST). Parse `message.content`, handle in-band `{"error"}` frames + `[DONE]`. |
| 2 | Loading state | Poll `/health`; WHILE 503 disable input, show indeterminate "loading"; no give-up timeout. |
| 3 | Stop generation | `AbortController.abort()`; branch on `signal.aborted` to avoid spurious error on user stop; retain partial output. |
| 4 | Static-serving build | Multi-stage `api/Dockerfile` (node build stage → python serve stage) + FastAPI `StaticFiles` mounted last; no host Node, no new container. |
| 5 | Brand tokens | Brand files are `_TBD_`; ship neutral ChatGPT-like defaults behind CSS-variable seams for later brand adoption; self-host all fonts. |
| 6 | Markdown rendering | `react-markdown@^9` + `remark-gfm@^4` + `rehype-highlight@^7`, all bundled locally. |
| 7 | Frontend stack | React `^18.3` + TypeScript `^5` + Vite `^5` + Tailwind `^3.4`, major-version pins only. |

---
id: SPEC-UI-001
version: 0.1.0
status: draft
created: 2026-06-05
created_at: 2026-06-05
updated: 2026-06-05
author: abjohn
priority: high
issue_number: 0
labels: [ui, frontend, react, vite, tailwind, streaming]
---

## HISTORY

- 2026-06-05 (v0.1.0): Initial draft authored by abjohn. Named follow-up to SPEC-INFRA-001 (runtime foundation, completed). Delivers the browser-based React chat UI that completes the first-milestone vertical slice — open a browser, type a message, watch Llama 4 Scout stream a response. All decisions (SSE-over-POST via fetch+ReadableStream, multi-stage Dockerfile static serving, neutral brand defaults pending the brand interview, react-markdown rendering, React 18 + Vite + Tailwind stack) inherited from `./research.md`. `issue_number: 0` because the `gh` CLI is not installed in this environment; Phase 2.5 GitHub Issue creation is skipped, following the same convention SPEC-INFRA-001 used.
- 2026-06-05 (v0.1.0): Scope locked to the minimal demo slice. Single conversation only; no persistence (honors the project no-persistence rule), no multi-session, no settings panel, no model-picker dropdown, no auth, no mobile-specific layout, no telemetry. Confirmed with the user during planning — see `## Exclusions`.
- 2026-06-05 (v0.1.0): Backend delta scoped to the single permitted modification — mounting static-file serving in the existing `api` service plus the Dockerfile build step to produce the bundle. No other backend change. `api/inference.py`, `api/security.py`, `api/state.py`, `docker-compose.yml`, and the entry scripts are untouched. See `## Files to Be Created or Modified`.
- 2026-06-05 (v0.1.0): plan-auditor review iteration 1 — passed (0.93) with 5 Minor defects, all fixed (user-approved). D1: corrected the `.dockerignore` delta wording — `web/` has no existing exclusion to "un-ignore"; the accurate change is to ADD `web/node_modules/` (optionally `web/dist/`) exclusions (verified against on-disk `.dockerignore`). D2: reclassified REQ-UI-004 from Optional/WHERE to Event-driven for the Stop behavior (a triggered event, not optional config), and added an Optional/WHERE clause for the genuinely-optional active-model-name display so all five EARS types remain represented across the set. D3: removed the `AbortController` implementation class name from the REQ-UI-004 normative statement (it now says "abort the in-flight streaming request"; the class name remains only in research.md/plan.md/Technical Approach as the chosen mechanism). D4: corrected REQ-UI-005's failure-status example — `POST /v1/chat/completions` returns `502` (upstream unavailable) pre-stream, not `503` (503 is the `/health` loading signal); verified against `api/main.py`. D5: closed the model-name-display traceability gap by marking it a non-acceptance-gated optional nicety in REQ-UI-004 and adding a corresponding note in `./acceptance.md`. Exclusions and frontmatter unchanged; `spec-compact.md` regenerated to match.
- 2026-06-05 (v0.1.0): Implemented via `/moai run` (TDD). Frontend `web/` React SPA (37 Vitest tests, lib branch coverage >85%) + backend serving delta (`api/main.py` guarded `StaticFiles` mount registered after the API routes, multi-stage `api/Dockerfile` node-build→python-serve, `.dockerignore` `web/node_modules/` exclusion; 14 new pytest, 117 total, `api/` coverage 93%). Independent reviews: plan-auditor PASS (0.93) on the SPEC; evaluator-active PASS on the implementation (Functionality 93 / Security 96 / Craft 89 / Consistency 94). Live end-to-end validated against a running stack (`run_debug.sh`, `MODEL=llama3.2:3b`): the multi-stage image built cleanly (npm ci + vite build in Docker), the SPA is served on the api origin `:8000`, API routes retain precedence (`/v1/models` returns JSON not the SPA), `LocalhostOnlyMiddleware` still rejects forged `Host` with 403, and streaming chat was confirmed arriving in the Ollama-native `message.content` wire shape.
- 2026-06-05 (v0.1.0): SCOPE AMENDMENT (user-approved during run). This SPEC's Exclusions originally listed `run_debug.sh`/`run_server.sh` as untouched. Live testing revealed `run_debug.sh`'s auto-open browser-launcher still targeted the obsolete separate-UI port `3000`; since SPEC-UI-001 serves the SPA from the api origin, `run_debug.sh` `UI_PORT` was repointed to `API_PORT` (`:8000`) and the obsolete "deferred UI service" comments removed, and `run_server.sh` gained a one-line "open the chat UI at ..." hint on ready. No behavioral change to the stack itself — only the browser-launcher target and operator-facing messaging.

---

# Argus React Chat UI: Browser-Based Streaming Chat over the Local Llama 4 API

## Overview

SPEC-UI-001 delivers the browser-based chat front end that completes the
Argus first-milestone vertical slice. SPEC-INFRA-001 made
`curl http://127.0.0.1:8000/v1/chat/completions` stream tokens from a local
Llama 4 Scout. This SPEC turns that into the intended user experience: open a
browser at `http://127.0.0.1:8000`, type a message, press Enter, and watch the
assistant response stream in token-by-token with markdown and code-block
rendering — all on-device, with zero data leaving the machine.

The UI is a React single-page application built with Vite into a static bundle.
There is **no new container, no nginx, and no Node runtime in production**: the
existing FastAPI `api` service serves the pre-built static assets via
`StaticFiles` mounted at `/`. Serving the SPA from the api origin keeps the
entire app same-origin, so the SPEC-INFRA-001 `LocalhostOnlyMiddleware` passes
cleanly with no CORS config and no weakening of the localhost-only threat model.
Source lives in a new top-level `web/` directory; the Vite build is folded into
the `api` image via a multi-stage Dockerfile build step, so `./run_server.sh`
remains the single entry point.

The feature scope is a deliberate minimal demo slice: one conversation, a
message composer (Enter to send, Shift+Enter for newline), token-by-token
streaming render consuming the existing SSE endpoint, markdown + code rendering,
a Stop button that aborts the in-flight stream while retaining partial output, a
graceful loading state while the backend is still `503 loading`, and a display
of the active model name. Everything else — persistence, multi-session, settings,
model picker, auth, mobile layout, telemetry — is explicitly excluded.

The central technical decision: the browser's native `EventSource` cannot issue
a POST with a JSON body, so the UI consumes the SSE stream via `fetch()` +
`ReadableStream` with a manual frame parser, and aborts via `AbortController`.
The frames are Ollama-native (token text at `message.content`, not OpenAI
`choices[].delta`), per the pass-through in `api/inference.py`. See
`./research.md` for the full decision rationale, the exact wire format with
file:line references, the static-serving build trade-off, and the markdown
library choice.

## Requirements (EARS)

Five REQ modules. Each maps to acceptance scenarios in `./acceptance.md`.

### REQ-UI-001 (Ubiquitous)

The Argus chat UI SHALL be a static single-page application served by the
existing FastAPI `api` service at `http://127.0.0.1:8000`, and at runtime SHALL
make no outbound network request to any host other than the local Argus `api`
on the same origin — no CDN-loaded fonts or scripts, no analytics, no telemetry,
no remote configuration, no cloud calls; all assets SHALL be bundled and served
locally, and the UI SHALL NOT weaken or bypass the `LocalhostOnlyMiddleware`.

### REQ-UI-002 (Event-driven)

WHEN the user submits a message (presses Enter in the composer, or activates the
send control), the UI SHALL issue `POST /v1/chat/completions` with
`stream: true`, SHALL read the response body as a stream, SHALL incrementally
render assistant token text (accumulated from each SSE frame's
`message.content`) into the conversation as it arrives, and SHALL render the
completed assistant message as markdown including fenced code blocks; Shift+Enter
SHALL insert a newline instead of submitting.

### REQ-UI-003 (State-driven)

WHILE `GET /health` reports the not-ready state (`HTTP 503 {"status":"loading"}`),
the UI SHALL display a clear, indeterminate "model is loading" state, SHALL
disable the message composer and send control so no message can be submitted,
and SHALL continue polling `/health` until it observes `HTTP 200
{"status":"ready"}`, at which point it SHALL enable the composer; the loading
state SHALL NOT time out or surface as an error, because a first-run model pull
is a legitimately long-lived operation.

### REQ-UI-004 (Event-driven + Optional/WHERE)

This module carries two clauses, an event-driven Stop behavior and an optional
WHERE behavior, keeping all five EARS types represented across the set.

- **(Event-driven)** WHEN the user activates the Stop control during an in-flight
  generation, the UI SHALL abort the in-flight streaming request, SHALL stop
  accumulating further tokens, SHALL retain and keep displaying the partial
  assistant output already received, and SHALL return the composer to a ready
  state so the user can send another message — without surfacing the
  user-initiated stop as an error.
- **(Optional, WHERE)** WHERE the active model name is available (from the
  streaming response frames or `GET /v1/models`), the UI SHALL display it; this
  display is an optional nicety and is NOT acceptance-gated (see `./acceptance.md`
  Quality Gate — model-name display).

### REQ-UI-005 (Unwanted behavior, IF…THEN)

IF a chat request fails before streaming begins (a non-OK HTTP status — for
`POST /v1/chat/completions` this is `502` when the upstream model service is
unavailable, the only non-2xx the chat endpoint returns pre-stream), OR the
stream errors mid-flight (an in-band SSE frame containing an `error` key, or a
dropped connection), THEN the UI SHALL surface a clear,
human-readable error message, SHALL retain any partial assistant output already
rendered, SHALL preserve the user's typed input (never silently discard an
unsent or in-progress message), and SHALL remain usable for a retry — the UI
SHALL NOT crash, hang, or lose data on any failure path.

## Exclusions (What NOT to Build)

- **No conversation persistence or chat history.** No localStorage of messages,
  no server-side history, no `argus_data` volume. Honors the project
  no-persistence rule (`product.md`, `CONCEPT.md`). Reloading the page starts a
  fresh empty conversation.
- **No multi-session / multiple conversations / tabs.** Exactly one in-memory
  conversation per page load.
- **No settings panel.** No theme toggle, no temperature/parameter controls, no
  configuration UI.
- **No model-picker dropdown.** The UI shows the active model name (read from
  the stream/response or a known default) but offers no way to switch models.
  `GET /v1/models` MAY be read only to display the active model name; it is
  optional and not required for the slice.
- **No authentication or access control.** Rides on the SPEC-INFRA-001 localhost
  threat model (`127.0.0.1` bind + header rejection). No login, no tokens.
- **No mobile-specific layout.** A clean single-column desktop-browser layout
  only. It need not break on small screens, but no dedicated mobile design work.
- **No telemetry, analytics, error-reporting SaaS, or remote config.** Forbidden
  by REQ-UI-001 and the privacy-by-architecture promise.
- **No outbound/cloud calls of any kind.** No CDN fonts or scripts at runtime.
- **No backend changes beyond static-file serving.** The only permitted backend
  modification is mounting `StaticFiles` in `api/main.py` and the Dockerfile
  build step. No new endpoints, no changes to `api/inference.py`,
  `api/security.py`, `api/state.py`, the SSE shape, or `docker-compose.yml`.
- **No new production container, no nginx, no production Node runtime.** Vite is
  a build-time step only.
- **No streaming performance hardening** (markdown re-render debounce, message
  virtualisation) unless measured jank appears — not pre-optimised at demo scale.
- **No concrete brand color/font values committed in this SPEC.** The brand files
  are `_TBD_` (`./research.md` §5); the UI ships neutral ChatGPT-like defaults
  behind CSS-variable seams for later brand adoption. Running the brand interview
  is a separate effort.

## Files to Be Created or Modified (in `/moai run`)

All paths are project-root-relative. `[NEW]` files do not exist on disk today;
`[MODIFY]` deltas amend files delivered by SPEC-INFRA-001.

### New — `web/` SPA source and config (all [NEW])

- `[NEW] web/package.json` — pins React `^18.3`, TypeScript `^5`, Vite `^5`,
  Tailwind `^3.4`, react-markdown `^9`, remark-gfm `^4`, rehype-highlight `^7`.
  Major-version pins only (matches the SPEC-INFRA-001 pinning rule).
- `[NEW] web/tsconfig.json` — TypeScript config for the React app.
- `[NEW] web/vite.config.ts` — `base: '/'`; dev-only `server.proxy` forwarding
  `/v1` and `/health` to `http://127.0.0.1:8000` so `vite dev` matches the
  production same-origin behavior.
- `[NEW] web/tailwind.config.ts` — neutral ChatGPT-like theme with semantic,
  CSS-variable-backed tokens (`--color-bg`, `--color-surface`, `--color-accent`,
  `--color-text`, `--font-sans`, `--font-mono`) as the brand-adoption seam.
- `[NEW] web/postcss.config.js` — Tailwind + autoprefixer pipeline.
- `[NEW] web/index.html` — SPA entry document; references only bundled assets;
  recommended `Content-Security-Policy` meta (`default-src 'self'`) as
  defense-in-depth for the no-external-call rule.
- `[NEW] web/src/main.tsx` — React root mount.
- `[NEW] web/src/App.tsx` — top-level chat layout (single column).
- `[NEW] web/src/index.css` — Tailwind directives + self-hosted font faces +
  highlight.js theme imported locally (no CDN).
- `[NEW] web/src/lib/sseClient.ts` — the central module: `fetch()` +
  `ReadableStream` reader, cross-chunk SSE frame buffering, `data: ` prefix
  strip, `[DONE]` sentinel detection, `message.content` extraction, in-band
  `{"error"}` frame handling, `AbortController` wiring.
- `[NEW] web/src/lib/health.ts` — `/health` readiness polling (loading → ready).
- `[NEW] web/src/components/*` — ChatView, MessageList, MessageBubble, Composer,
  StopButton, LoadingState, ModelBadge. Exact component split decided in
  `/moai run`.

### Modified — existing `api` service ([MODIFY] deltas against SPEC-INFRA-001)

- `[MODIFY] api/main.py` — mount `StaticFiles(directory="web/dist", html=True)`
  at `/`, registered AFTER the `/health`, `/v1/models`, `/v1/chat/completions`
  routes so API routes take precedence and the SPA catch-all serves everything
  else. No new pip dependency (`StaticFiles` ships with Starlette/FastAPI). This
  is the only behavioral change to `main.py`; the middleware, readiness state
  machine, and routes are otherwise untouched.
- `[MODIFY] api/Dockerfile` — add a first `node:20-slim` build stage that runs
  `npm ci && npm run build` against `web/`, then `COPY --from=build` the produced
  `web/dist` into the existing `python:3.12-slim` stage at `/app/web/dist`. The
  python runtime stage gains no Node; Node is used at build time only.
- `[MODIFY] .dockerignore` — the current `.dockerignore` has NO `web/` exclusion,
  so `web/` source is already reachable by the build context; there is nothing to
  "un-ignore". The accurate change is to ADD an exclusion for `web/node_modules/`
  (and optionally `web/dist/`) so a stale host `node_modules`/build artifact is
  not copied into the build context — the node build stage installs deps fresh
  inside the image via `npm ci`. Note the existing `*.md` exclusion already
  covers any `web/**/*.md`; no change is needed there.

No change to `api/inference.py`, `api/security.py`, `api/state.py`,
`docker-compose.yml`, `run_server.sh`, `run_debug.sh`, `.env.example`.

## Technical Approach

The architecture and the API contract are fixed by `./research.md`. Summary:

1. **Same-origin static SPA (REQ-UI-001).** Vite builds `web/` to a static
   bundle. `api/main.py` serves it via `StaticFiles` mounted at `/`, so the page
   and all `fetch` calls share the `http://127.0.0.1:8000` origin. Same-origin
   requests carry `Host: 127.0.0.1:8000` and `Origin: http://127.0.0.1:8000`,
   both of which pass `is_localhost_header` (`api/security.py`) — the localhost
   middleware needs no change and is not weakened. All assets are bundled; no
   CDN, no telemetry, no off-origin requests.

2. **Streaming render (REQ-UI-002).** On submit, the UI calls
   `POST /v1/chat/completions` with `{messages, stream: true}` via `fetch`.
   It reads `response.body.getReader()`, decodes chunks with `TextDecoder`,
   buffers across chunk boundaries, splits complete `\n\n`-delimited SSE frames,
   strips `data: `, treats `[DONE]` as end-of-stream, and `JSON.parse`s each
   frame to append `message.content` to the in-progress assistant message. The
   accumulated text is rendered through `react-markdown` + `remark-gfm` +
   `rehype-highlight` (code blocks highlighted, all assets local). Frames are
   Ollama-native — token text is at `message.content`, NOT OpenAI
   `choices[].delta` (`./research.md` §1.2).

3. **Loading state (REQ-UI-003).** The UI polls `GET /health`. WHILE `503`, it
   shows an indeterminate "loading" state and disables the composer; on `200
   {"status":"ready"}` it enables input. No give-up timeout — a first-run pull
   can legitimately take a long time (`./research.md` §2).

4. **Stop generation (REQ-UI-004).** Each request uses an `AbortController`; the
   Stop button calls `abort()`. The reader loop branches on `signal.aborted` to
   finalise the partial message silently (no error banner on user stop) and
   reset the composer. The same controller is aborted on unmount. No backend
   change — aborting the `fetch` closes the client connection and the server
   generator's `finally` blocks clean up upstream (`api/inference.py:203-209`).

5. **Error handling (REQ-UI-005).** Two failure modes are handled distinctly:
   pre-stream non-OK HTTP status (e.g. 502 from `OllamaUnavailable`,
   `api/main.py:214-220`) surfaces an error before any tokens render; an in-band
   `{"error": ...}` SSE frame (`api/inference.py:202`) or dropped connection
   mid-stream finalises the partial output and surfaces an error. In all cases
   the typed input is preserved and the UI stays usable.

6. **Build integration (static serving).** A multi-stage `api/Dockerfile`
   (`./research.md` §4.1, Option A) runs `vite build` in a `node:20-slim` stage
   and copies the dist into the python serve stage. This preserves the single
   `./run_server.sh` → `docker compose up -d` → build flow and requires no host
   Node, honoring "host environment untouched". Trade-off (longer first build,
   larger context) is documented in `plan.md` §3.

7. **Brand seam (REQ-UI-001 styling).** Tailwind tokens are defined as semantic
   CSS variables so the `_TBD_` brand files (`./research.md` §5) can be adopted
   later by editing variable values only. Fonts are self-hosted/bundled. The
   layout targets a clean single-column ChatGPT-like view and WCAG 2.1 AA basics
   (contrast, visible focus states, keyboard nav for composer/send/stop).

## MX Tag Plan

The following MX tags will be placed during `/moai run`:

| File | Tag | Reason |
|---|---|---|
| `web/src/lib/sseClient.ts` (SSE frame parser) | `@MX:ANCHOR` | The single boundary where the Ollama-native SSE wire format (`message.content`, `[DONE]` sentinel, in-band `{"error"}` frames) is parsed. Every streaming feature depends on it; the format contract is pinned here so a backend SSE-shape change is a single-file edit. Requires `@MX:REASON`. |
| `web/src/lib/sseClient.ts` (chunk-boundary buffering) | `@MX:WARN` | TCP chunk boundaries do not align with SSE frame boundaries; the residual-buffer logic is the most likely source of subtle truncation bugs. Requires `@MX:REASON` documenting the carry-forward contract. |
| `web/src/lib/sseClient.ts` (abort/stop branch) | `@MX:WARN` | Stop-button race: `abort()` can land between reads; the catch MUST distinguish `signal.aborted` (silent finalise) from a real error (surface it). Requires `@MX:REASON`. |
| `api/main.py` (StaticFiles mount) | `@MX:NOTE` | Documents that the SPA mount MUST be registered AFTER the API routes (mount ordering invariant) and that same-origin serving is what keeps `LocalhostOnlyMiddleware` clean — do not reorder, do not add CORS. |
| `api/Dockerfile` (node build stage) | `@MX:NOTE` | Documents that Node appears in the build stage only and never in the runtime image, preserving the no-Node-at-runtime stance. |

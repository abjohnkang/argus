# Implementation Plan — SPEC-UI-001

Implementation plan for the Argus React chat UI. All major architectural
decisions are already settled in `./research.md` and `./spec.md`; this document
sequences the work, pins the stack, decides the static-serving build
integration, and names the risks. Do not re-decide the SSE-consumption approach,
the build-integration option, the markdown library, or the stack pins here —
those are inputs from `./research.md`.

---

## 1. Task Decomposition

Tasks are ordered for sequential execution. Each produces a focused change.
Targets are kept small so a stagnation in any one task does not cascade. The
backend-touching tasks (8-10) come last so the SPA exists before it is wired in.

| # | Task | Output | Depends on |
|---|---|---|---|
| 1 | Scaffold `web/` project: `package.json` (pinned deps), `tsconfig.json`, `vite.config.ts` (`base: '/'` + dev proxy for `/v1` and `/health`), `postcss.config.js`. | `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`, `web/postcss.config.js` | — |
| 2 | Tailwind setup: `tailwind.config.ts` with semantic CSS-variable tokens (brand seam); `web/src/index.css` with Tailwind directives, self-hosted font faces, local highlight.js theme. | `web/tailwind.config.ts`, `web/src/index.css` | Task 1 |
| 3 | Implement `web/src/lib/sseClient.ts` — the `@MX:ANCHOR` SSE parser: `fetch` + `ReadableStream` reader, cross-chunk frame buffering, `data: ` strip, `[DONE]` detection, `message.content` extraction, in-band `{"error"}` handling, `AbortController` wiring. | `web/src/lib/sseClient.ts` | Task 1 |
| 4 | Implement `web/src/lib/health.ts` — `/health` polling, loading → ready detection. | `web/src/lib/health.ts` | Task 1 |
| 5 | Build presentational components: MessageBubble (markdown via react-markdown + remark-gfm + rehype-highlight), MessageList, ModelBadge, LoadingState. | `web/src/components/*` | Tasks 2, 3 |
| 6 | Build interactive components: Composer (Enter to send, Shift+Enter newline, disabled WHILE loading) and StopButton (abort in-flight, retain partial). | `web/src/components/*` | Tasks 3, 5 |
| 7 | Compose `web/src/App.tsx` + `web/src/main.tsx` + `web/index.html` (CSP meta `default-src 'self'`): single-column chat layout wiring health gate, composer, streaming render, stop, error surface, model badge. | `web/src/App.tsx`, `web/src/main.tsx`, `web/index.html` | Tasks 4, 5, 6 |
| 8 | `[MODIFY] .dockerignore`: `web/` source is already in the build context (no existing exclusion); ADD `web/node_modules/` (optionally `web/dist/`) exclusions so a stale host build artifact is not copied into the context. | `.dockerignore` | — |
| 9 | `[MODIFY] api/Dockerfile`: add `node:20-slim` build stage running `npm ci && npm run build` on `web/`; `COPY --from=build` dist into the python stage. | `api/Dockerfile` | Tasks 7, 8 |
| 10 | `[MODIFY] api/main.py`: mount `StaticFiles(directory="web/dist", html=True)` at `/` AFTER the API routes; place `@MX:NOTE` on mount ordering. | `api/main.py` | Task 9 |
| 11 | Acceptance harness: streaming render, stop mid-stream, 503 loading gate, markdown/code render, error path, no-external-call verification (per `./acceptance.md`). | `web/` tests + manual/check scripts; scope finalized in `/moai run` | All above |

Eleven discrete tasks. Each is small enough for a single iteration. The central
risk concentrates in Task 3 (`sseClient.ts`); it is sequenced early so the rest
of the UI builds on a proven parser.

---

## 2. Technology Stack

All pins are major-version (`^`) only — no patch pins, no beta/alpha — matching
the SPEC-INFRA-001 house rule (`api/requirements.txt`).

| Layer | Choice | Version pin | Reason |
|---|---|---|---|
| Framework | React | `^18.3` | Most production-stable React line; conservative for a demo slice. `tech.md` locks React + TypeScript. |
| Language | TypeScript | `^5` | Type-safe front end per `tech.md`. |
| Build tool | Vite | `^5` | Static-bundle build, fast, first-class React + TS. v5 is the proven stable line (v7 exists; v5 chosen for stability). `base: '/'` so assets serve from the api root. Bare Vite, not Next.js — no SSR need. |
| Styling | Tailwind CSS | `^3.4` | Confirmed in scope. v3.4 is the production-proven line (v4 is newer; 3.4 chosen for stability). |
| Markdown | react-markdown | `^9` | High source reputation, React-native (no `dangerouslySetInnerHTML`), plugin model. `./research.md` §7. |
| Markdown GFM | remark-gfm | `^4` | Tables, fenced code, task lists. |
| Code highlight | rehype-highlight | `^7` | highlight.js via rehype plugin; smaller footprint than `react-syntax-highlighter` language packs; theme CSS bundled locally (no CDN). |
| Runtime serving | FastAPI `StaticFiles` (existing) | inherited from SPEC-INFRA-001 | No new pip dependency; ships with Starlette/FastAPI. |
| Build-time only | Node | `20-slim` (Docker build stage) | Runs `vite build` inside `api/Dockerfile`; absent from the runtime image. |

Next.js, nginx, and any production Node runtime are explicitly NOT in the stack.
No new production container. No new pip dependency on the backend.

---

## 3. Risk Analysis

### Risk 1: SSE-over-POST parsing (central technical risk)

- **Source:** `./research.md` §1.4.
- **Impact:** Native `EventSource` cannot POST a body, so the UI must hand-roll
  `fetch` + `ReadableStream` parsing. TCP chunk boundaries do not align with SSE
  frame boundaries — a read may deliver half a frame or several frames. Naive
  splitting drops or corrupts tokens.
- **Mitigation:** `sseClient.ts` keeps a residual buffer, only consumes complete
  `\n\n`-terminated frames, and carries the remainder forward. The frame parser
  reads `message.content` (Ollama-native shape, NOT `choices[].delta`), detects
  the `[DONE]` sentinel, and treats any frame with an `error` key as a failure.
  `@MX:ANCHOR` + `@MX:WARN` tags document the contract. Acceptance Scenario 1
  asserts tokens arrive incrementally and render in order.

### Risk 2: Stop-button race condition

- **Source:** `./research.md` §3.
- **Impact:** `controller.abort()` can land between two reads; the loop may
  raise `AbortError` that looks like a network failure, producing a spurious
  error banner on a user-initiated stop, or leaking a half-read stream.
- **Mitigation:** the reader catch branches on `signal.aborted` — if aborted,
  finalise the partial message silently and reset the composer; otherwise
  surface the error. The same controller is aborted on component unmount.
  `@MX:WARN` on the abort branch. Acceptance Scenario 2 asserts partial output
  is retained and no error banner appears on stop.

### Risk 3: Static-bundle build cost and `.dockerignore` correctness

- **Source:** `./research.md` §4.1.
- **Impact:** The multi-stage Dockerfile (Option A) adds a `node:20-slim` build
  stage; the first `docker compose build` is slower and the build context grows
  because `web/` source is now included. `web/` is already reachable (no existing
  `.dockerignore` exclusion), but a stale host `web/node_modules` or `web/dist`
  copied into the context would bloat the build and risk a stale artifact.
- **Mitigation:** ADD `web/node_modules/` (optionally `web/dist/`) to
  `.dockerignore` so deps install fresh inside the node stage via `npm ci` and
  the node stage produces `dist` internally (`COPY --from=build` transfers it to
  the python stage). Document the trade-off;
  the cost is build-time only and Node never enters the runtime image. The
  alternative (host `vite build`) was rejected because it requires host Node,
  violating "host untouched" (`product.md`). Acceptance verifies the served
  bundle works end-to-end after `./run_server.sh`.

### Risk 4: StaticFiles mount ordering shadows API routes

- **Source:** `./research.md` §4.2.
- **Impact:** If `StaticFiles` is mounted at `/` BEFORE the API routes, the
  catch-all SPA mount shadows `/health`, `/v1/models`, `/v1/chat/completions` —
  the UI loads but every API call returns the SPA `index.html`.
- **Mitigation:** mount `StaticFiles` LAST, after all API routes are registered.
  `@MX:NOTE` on the mount documents the ordering invariant. Acceptance verifies
  both that the page loads AND that `/health` / chat still return JSON/SSE.

### Risk 5: Large bundle / offline-font handling breaks the no-external-call rule

- **Source:** `./research.md` §6.
- **Impact:** A careless font or highlight-theme import from a CDN
  (`fonts.googleapis.com`, a jsDelivr highlight.js theme) would silently violate
  the privacy-by-architecture promise (REQ-UI-001) — the page would make an
  off-origin request at runtime.
- **Mitigation:** self-host all fonts (bundled by Vite) or use pure `system-ui`;
  import the highlight.js theme CSS locally. Add a `Content-Security-Policy` meta
  (`default-src 'self'`) as defense-in-depth. Acceptance includes a no-external-
  call check (bundle scan for non-localhost `http(s)://` references + DevTools
  Network-panel verification that only same-origin requests fire).

### Risk 6: Middleware false-positive on `Origin` for same-origin fetch

- **Source:** `./research.md` §4.2.
- **Impact:** If the SPA were served from a different origin (e.g. a separate dev
  server in production), same-origin assumptions break and `Origin` could fail
  `is_localhost_header`, yielding 403s.
- **Mitigation:** production serves the SPA from the api origin (same-origin),
  which the middleware already passes. The dev proxy in `vite.config.ts` makes
  `vite dev` forward `/v1` and `/health` to `127.0.0.1:8000` so even in dev the
  requests are localhost-origin. No middleware change. Low residual risk.

### Risk 7: Markdown re-render performance on every token frame

- **Source:** `./research.md` §7.
- **Impact:** Re-parsing the full markdown string per frame is O(n^2) over a
  message; very long responses could jank.
- **Mitigation:** acceptable at demo message sizes (hundreds to low-thousands of
  tokens). If measured jank appears, debounce markdown re-render to animation
  frames. NOT pre-optimised (Exclusions). Listed so `/moai run` does not gold-
  plate prematurely.

---

## 4. Reference Implementations

Established patterns to guide implementation; no new invention required.

- **`fetch` + `ReadableStream` SSE parsing.** The canonical pattern for
  consuming a POST SSE stream in the browser: `getReader()`, `TextDecoder`,
  buffer-and-split on `\n\n`, `data: ` prefix handling, `[DONE]` sentinel. The
  central module `sseClient.ts` implements it against the Ollama-native frame
  shape documented in `./research.md` §1.2.
- **`AbortController` for fetch cancellation.** Standard pattern: pass
  `signal` to `fetch`, call `abort()` from the Stop button, branch on
  `signal.aborted` in the catch.
- **`react-markdown` with rehype/remark plugins.** Standard wiring of
  `remark-gfm` + `rehype-highlight` and a custom `code` component override; the
  highlight theme CSS imported locally.
- **FastAPI `StaticFiles` SPA serving.** Standard `app.mount("/",
  StaticFiles(directory=..., html=True))` registered after API routes.
- **Multi-stage Docker (node build → slim runtime).** Standard front-end-in-
  backend pattern: a `node` builder stage produces `dist`, a slim runtime stage
  `COPY --from=build` the static output and serves it.

`/moai run` agents (expert-frontend, expert-backend) may consult Context7 or
library docs for exact API surfaces (react-markdown v9 component props, Vite v5
`base`/`server.proxy` config, Tailwind v3.4 theme extension).

---

## 5. Test Strategy Outline

Detailed Given/When/Then scenarios live in `./acceptance.md`. Scope summary:

### Test scope

- **Streaming render (happy path)** — submit a message, assert tokens accumulate
  incrementally from `message.content` and the final message renders as markdown.
- **Stop mid-stream** — abort during generation; assert partial output retained,
  composer reset, no error banner.
- **Loading gate (503)** — WHILE `/health` is 503, assert composer disabled and a
  loading state shown; on 200 assert composer enabled.
- **Markdown + code rendering** — assert fenced code blocks render highlighted
  and GFM (tables, lists) renders.
- **Error path** — pre-stream 502 and in-band `{"error"}` frame each surface an
  error while preserving typed input and partial output.
- **No external call** — bundle scan + runtime Network-panel check show only
  same-origin requests; no CDN font/script.

### Test placement and method

- Component/unit tests for `sseClient.ts` (frame buffering across synthetic
  chunk splits, `[DONE]`, `{"error"}` frames, abort) and `health.ts` (503→200)
  run hermetically against a mocked `fetch` / mocked `ReadableStream` — no real
  backend, no Docker. Vitest is the natural runner for a Vite project (selected
  in `/moai run`).
- Component tests for Composer (Enter vs Shift+Enter, disabled-when-loading) and
  the error surface use React Testing Library.
- The no-external-call check is a build-output grep plus a documented manual
  DevTools verification (and/or the CSP meta acting as an enforced backstop).
- End-to-end streaming against the real `api` service is verified manually via
  `./run_server.sh` + browser, mirroring the SPEC-INFRA-001 integration approach
  (Docker-dependent paths are manual/integration, not unit).

### What this SPEC does NOT test

- Llama 4 output quality — Meta's concern, not Argus's (same stance as
  SPEC-INFRA-001 `plan.md` §5).
- Backend SSE production correctness — owned and tested by SPEC-INFRA-001.
- Cross-browser matrix beyond a current evergreen desktop browser.
- Mobile layout — excluded.

### Coverage target

`web/src/lib/` (the logic-bearing modules, especially `sseClient.ts`): aim for
the TRUST 5 baseline (>= 85%). Presentational components are covered by behavior
tests rather than line-coverage targets. Final thresholds confirmed in
`/moai run` against `quality.yaml`.

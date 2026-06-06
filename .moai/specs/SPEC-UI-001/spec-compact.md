# SPEC-UI-001 (Compact)

> Auto-generated compact form of `./spec.md`. REQs + acceptance + files +
> exclusions only. For full context, rationale, and file:line references see
> `./spec.md`, `./plan.md`, `./acceptance.md`, and `./research.md`.
> Regenerated after plan-auditor review iteration 1 (D1–D5 fixes).

- **id:** SPEC-UI-001
- **title:** Argus React Chat UI — Browser-Based Streaming Chat over the Local Llama 4 API
- **status:** draft · **priority:** high · **author:** abjohn · **issue:** 0
- **follows:** SPEC-INFRA-001 (runtime foundation, completed)

---

## Requirements (EARS)

- **REQ-UI-001 (Ubiquitous):** The chat UI SHALL be a static SPA served by the
  existing FastAPI `api` service at `http://127.0.0.1:8000`, and at runtime SHALL
  make no outbound call to any host other than the local Argus `api` on the same
  origin (no CDN fonts/scripts, no analytics, no telemetry, no remote config, no
  cloud calls); all assets bundled and served locally; the `LocalhostOnlyMiddleware`
  SHALL NOT be weakened or bypassed.
- **REQ-UI-002 (Event-driven):** WHEN the user submits a message (Enter or send),
  the UI SHALL `POST /v1/chat/completions` with `stream: true`, read the response
  as a stream, incrementally render assistant token text accumulated from each SSE
  frame's `message.content`, and render the completed message as markdown including
  fenced code blocks; Shift+Enter SHALL insert a newline instead of submitting.
- **REQ-UI-003 (State-driven):** WHILE `GET /health` reports `503
  {"status":"loading"}`, the UI SHALL show an indeterminate loading state, disable
  the composer/send control, and keep polling until `200 {"status":"ready"}`, then
  enable the composer; the loading state SHALL NOT time out or become an error.
- **REQ-UI-004 (Event-driven + Optional/WHERE):** Two clauses —
  (Event-driven) WHEN the user activates Stop during generation, the UI SHALL
  abort the in-flight streaming request, stop accumulating tokens, retain the
  partial output, and reset the composer — without surfacing the user stop as an
  error; (Optional, WHERE) WHERE the active model name is available (response
  frames or `GET /v1/models`), the UI SHALL display it — an optional nicety that
  is NOT acceptance-gated.
- **REQ-UI-005 (Unwanted, IF…THEN):** IF a chat request fails pre-stream (a non-OK
  status — for `POST /v1/chat/completions` this is `502` when the upstream model
  service is unavailable, the only non-2xx it returns pre-stream) OR the stream
  errors mid-flight (in-band `{"error"}` frame or dropped connection), THEN the UI
  SHALL surface a clear error, retain partial output, preserve the user's typed
  input, and stay usable — no crash, no hang, no data loss.

EARS-type coverage across the set: Ubiquitous (001), Event-driven (002 + 004
clause 1), State-driven (003), Optional/WHERE (004 clause 2), Unwanted/IF-THEN
(005) — all five types represented.

---

## Acceptance (Given/When/Then summary)

Primary:
1. **Streaming render happy path** (REQ-UI-002/001) — Enter sends; tokens render
   token-by-token from `message.content`; clean `[DONE]`; markdown render;
   same-origin only.
2. **Stop mid-stream** (REQ-UI-004) — abort retains partial output, resets
   composer, shows no error.
3. **Backend loading 503** (REQ-UI-003) — composer disabled + loading state while
   503; enabled on 200; no timeout/error.
4. **Markdown + code rendering** (REQ-UI-002) — fenced code highlighted, GFM
   rendered, assets local-only.
5. **Request/stream error** (REQ-UI-005) — error surfaced (pre-stream 502 or
   in-band `{"error"}` frame), partial output + typed input preserved, UI stays
   usable.
6. **No off-origin call** (REQ-UI-001) — Network panel shows only
   `127.0.0.1:8000`; bundle scan clean; CSP `default-src 'self'`.

Edge cases:
1. Shift+Enter newline vs Enter send.
2. Stop after completion is a no-op.
3. Empty/whitespace submission ignored.
4. Empty stream (only `[DONE]`) terminates cleanly, no hang.
5. SSE frame split across chunk boundaries — buffered, no token loss (unit test).
6. Page reload starts a fresh conversation (no persistence).

Not acceptance-gated: model-name display (REQ-UI-004 Optional/WHERE clause) — an
optional nicety with no scenario; omitting it still PASSES.

Must-pass firewall: any off-origin runtime request FAILS the SPEC regardless of
other quality. Backend regression guard: SPEC-INFRA-001 `/health`, `/v1/models`,
`/v1/chat/completions` still work (no route shadowing); final `api` image has no
Node.

---

## Files

New (all `[NEW]`, `web/` SPA source + config):
- `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`,
  `web/tailwind.config.ts`, `web/postcss.config.js`, `web/index.html`,
  `web/src/main.tsx`, `web/src/App.tsx`, `web/src/index.css`,
  `web/src/lib/sseClient.ts` (central SSE parser), `web/src/lib/health.ts`,
  `web/src/components/*` (ChatView, MessageList, MessageBubble, Composer,
  StopButton, LoadingState, ModelBadge).

Modified ([MODIFY] deltas vs SPEC-INFRA-001):
- `api/main.py` — mount `StaticFiles(directory="web/dist", html=True)` at `/`
  AFTER the API routes.
- `api/Dockerfile` — add `node:20-slim` build stage running `vite build`;
  `COPY --from=build` dist into the python stage (Node build-time only).
- `.dockerignore` — `web/` source is already in the context (no existing
  exclusion); ADD `web/node_modules/` (optionally `web/dist/`) exclusions so a
  stale host build artifact is not copied in.

Untouched: `api/inference.py`, `api/security.py`, `api/state.py`,
`docker-compose.yml`, `run_server.sh`, `run_debug.sh`, `.env.example`.

---

## Stack (major-version pins only)

React `^18.3` · TypeScript `^5` · Vite `^5` · Tailwind CSS `^3.4` ·
react-markdown `^9` · remark-gfm `^4` · rehype-highlight `^7` · FastAPI
`StaticFiles` (inherited, no new pip dep) · Node `20-slim` (Docker build stage
only). No Next.js, no nginx, no production Node runtime, no new container.

---

## Exclusions (What NOT to Build)

- No conversation persistence / chat history (honors project no-persistence rule).
- No multi-session / multiple conversations / tabs.
- No settings panel.
- No model-picker dropdown (active model name shown; `/v1/models` optional, read
  only for the name).
- No authentication / access control.
- No mobile-specific layout.
- No telemetry, analytics, error-reporting SaaS, or remote config.
- No outbound/cloud calls; no CDN fonts/scripts at runtime.
- No backend changes beyond static-file serving + the Dockerfile build step.
- No new production container, no nginx, no production Node runtime.
- No streaming performance hardening unless measured jank appears.
- No concrete brand color/font values committed (brand files are `_TBD_`; ship
  neutral ChatGPT-like defaults behind CSS-variable seams).

---

## MX Tag Plan

- `@MX:ANCHOR` — `web/src/lib/sseClient.ts` (SSE frame parser, the wire-format
  boundary).
- `@MX:WARN` — `web/src/lib/sseClient.ts` (cross-chunk frame buffering;
  carry-forward contract).
- `@MX:WARN` — `web/src/lib/sseClient.ts` (abort/stop branch; distinguish
  user-initiated stop from a real error).
- `@MX:NOTE` — `api/main.py` (StaticFiles mount ordering: mount LAST, keep
  same-origin, no CORS).
- `@MX:NOTE` — `api/Dockerfile` (Node in build stage only, never in runtime).

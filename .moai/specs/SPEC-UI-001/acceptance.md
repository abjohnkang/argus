# Acceptance Criteria — SPEC-UI-001

Given-When-Then acceptance scenarios for the Argus React chat UI. Each scenario
maps to one or more REQ-UI-* requirements in `./spec.md`. A SPEC-UI-001
implementation is complete when every scenario below passes and the quality
gates at the bottom are satisfied.

The wire format asserted below is the real Ollama-native SSE shape produced by
`api/inference.py` (token text at `message.content`, `[DONE]` sentinel, in-band
`{"error"}` frames), confirmed in `./research.md` §1.

---

## Primary Scenarios

### Scenario 1: Streaming render happy path

Maps to: REQ-UI-002, REQ-UI-001

- **Given** the API is in the `ready` state (`GET /health` returns `200
  {"status":"ready"}`) and the SPA is loaded in a browser at
  `http://127.0.0.1:8000`,
- **When** the user types "Write a haiku about the sea" into the composer and
  presses Enter,
- **Then** the UI issues `POST /v1/chat/completions` with `stream: true` and the
  user message body,
- **And** the user's message appears immediately in the conversation,
- **And** assistant token text accumulated from each SSE frame's
  `message.content` is rendered incrementally into a new assistant message as
  frames arrive (visible token-by-token growth, not a single post-completion
  dump),
- **And** the stream terminates cleanly on the `data: [DONE]` sentinel,
- **And** the completed assistant message is rendered as markdown,
- **And** all of this happens against the same origin only — no request to any
  host other than `http://127.0.0.1:8000` is made (verifiable in the DevTools
  Network panel).

### Scenario 2: Stop generation mid-stream

Maps to: REQ-UI-004

- **Given** an assistant response is actively streaming (some tokens already
  rendered, `[DONE]` not yet received),
- **When** the user activates the Stop control,
- **Then** the in-flight `fetch` is aborted via `AbortController`,
- **And** no further tokens are appended after the abort,
- **And** the partial assistant text already rendered is retained and remains
  visible (it is NOT cleared),
- **And** the composer returns to a ready, enabled state so the user can send
  another message,
- **And** NO error message or error banner is shown (a user-initiated stop is
  not an error).

### Scenario 3: Backend still loading (503 graceful state)

Maps to: REQ-UI-003

- **Given** the `api` service is up but the model is still loading (`GET /health`
  returns `503 {"status":"loading"}` — e.g. during a first-run model pull),
- **When** the user opens or is viewing the SPA,
- **Then** the UI displays a clear, indeterminate "model is loading" state,
- **And** the message composer and send control are disabled so no message can
  be submitted,
- **And** the UI keeps polling `GET /health` on an interval,
- **And** the loading state does NOT time out or convert into an error, however
  long the model takes,
- **And** WHEN `/health` subsequently returns `200 {"status":"ready"}`, the
  composer becomes enabled and the loading state clears.

### Scenario 4: Markdown and code-block rendering

Maps to: REQ-UI-002

- **Given** the API is ready and the user has sent a message,
- **When** the assistant response contains markdown — at minimum a fenced code
  block (e.g. a ```python block), a list, and inline emphasis,
- **Then** the fenced code block renders as a distinct, syntax-highlighted code
  block (monospace, highlight applied via the locally bundled highlight theme),
- **And** the list and emphasis render as formatted markdown (not raw `*` / `-`
  characters),
- **And** the syntax-highlight theme CSS and any fonts are loaded from the local
  bundle only — no CDN request fires for fonts or highlight assets (verifiable in
  the DevTools Network panel).

### Scenario 5: Request/stream error keeps the UI usable (no data loss)

Maps to: REQ-UI-005

- **Given** the API is reachable and the user submits a message,
- **When** the request fails before streaming begins (the initial response is a
  non-OK status such as `502` from `OllamaUnavailable`), OR the stream errors
  mid-flight (an SSE frame containing an `error` key arrives, or the connection
  drops),
- **Then** the UI surfaces a clear, human-readable error message,
- **And** any partial assistant output already rendered is retained,
- **And** the user's typed input is preserved (an unsent message is not silently
  discarded; an in-progress message remains recoverable),
- **And** the UI does NOT crash, hang, or enter an unrecoverable state,
- **And** the user can send another message after the error.

### Scenario 6: No outbound / off-origin network call (privacy by architecture)

Maps to: REQ-UI-001

- **Given** the SPA is served by the `api` service and loaded in a browser,
- **When** the user loads the page and conducts a full chat exchange (load,
  send, stream, stop),
- **Then** every network request observed in the DevTools Network panel targets
  the same origin `http://127.0.0.1:8000` and no other host,
- **And** a static scan of the built bundle (`web/dist`) finds no absolute
  `http(s)://` reference to any non-localhost host (no `fonts.googleapis.com`,
  no CDN script/style, no analytics/telemetry endpoint),
- **And** the `index.html` carries a `Content-Security-Policy` meta of at least
  `default-src 'self'` (defense-in-depth backstop),
- **And** no analytics, telemetry, or remote-config request is made at any point.

---

## Edge Case Scenarios

### Edge case 1: Shift+Enter inserts a newline instead of sending

Maps to: REQ-UI-002

- **Given** the composer is focused and enabled (API ready),
- **When** the user presses Shift+Enter,
- **Then** a newline is inserted into the composer text,
- **And** NO message is submitted,
- **And** pressing Enter alone (without Shift) on a non-empty composer DOES
  submit the message.

### Edge case 2: Stop pressed after stream already completed

Maps to: REQ-UI-004

- **Given** an assistant response has fully completed (`[DONE]` received, Stop
  control no longer active or hidden),
- **When** the user attempts to activate Stop (or Stop is shown only during
  active generation),
- **Then** no error occurs and the completed message is unaffected (aborting an
  already-finished controller is a no-op),
- **And** the composer remains ready for the next message.

### Edge case 3: Empty / whitespace-only submission is ignored

Maps to: REQ-UI-002

- **Given** the composer is empty or contains only whitespace,
- **When** the user presses Enter,
- **Then** no `POST /v1/chat/completions` request is made,
- **And** no empty user message is added to the conversation.

### Edge case 4: Empty assistant stream (only `[DONE]`)

Maps to: REQ-UI-002, REQ-UI-005

- **Given** the API is ready and the user sends a message,
- **When** the backend returns a stream containing only the `data: [DONE]`
  sentinel and no content frames (the empty-stream path in `api/main.py`),
- **Then** the UI terminates the stream cleanly,
- **And** the assistant message is either empty or a benign placeholder,
- **And** the UI does NOT hang waiting for tokens and the composer returns to a
  ready state.

### Edge case 5: SSE frame split across chunk boundaries

Maps to: REQ-UI-002 (Risk 1 in `./plan.md` §3)

- **Given** the streaming response delivers a single SSE frame split across two
  network reads (the `\n\n` delimiter arrives in a later chunk),
- **When** `sseClient.ts` processes the partial chunks,
- **Then** the parser buffers the incomplete frame and only emits the token once
  the complete `\n\n`-terminated frame is assembled,
- **And** no token text is dropped, duplicated, or corrupted,
- **And** this is verified by a unit test feeding deliberately split chunk
  sequences to the parser.

### Edge case 6: Page reload starts a fresh conversation (no persistence)

Maps to: REQ-UI-001 Exclusions (no persistence)

- **Given** a conversation with several messages exists in the UI,
- **When** the user reloads the page,
- **Then** the conversation is empty (no messages are restored),
- **And** no message history was written to localStorage, IndexedDB, or any
  server-side store (verifiable: storage inspectors are empty of chat data).

---

## Quality Gate Criteria

### Functional targets

- All six primary scenarios pass.
- All six edge-case scenarios pass.
- Each REQ-UI-001 … REQ-UI-005 has at least one passing scenario or test
  covering it.
- The SSE parser (`sseClient.ts`) has unit tests for: incremental
  `message.content` accumulation, cross-chunk frame buffering (Edge case 5),
  `[DONE]` termination, in-band `{"error"}` frame handling, empty stream
  (Edge case 4), and abort.

### Model-name display (optional, NOT acceptance-gated)

The active-model-name display (REQ-UI-004 Optional/WHERE clause) is an optional
nicety. It has deliberately NO Given/When/Then scenario and is NOT a gating
criterion: a build that omits the model-name badge, or shows a default/unknown
name when the model name is unavailable, still PASSES the SPEC. Traceability is
satisfied by this explicit non-gated marking. If implemented, the displayed name
should be sourced from the streaming response frames (`frame.model`) or
`GET /v1/models`, with a sensible fallback when neither is available.

### Accessibility (WCAG 2.1 AA basics)

- Text/background contrast meets AA for body and assistant/user message text.
- The composer, send control, and Stop control are keyboard-operable and show a
  visible focus state.
- The loading state and error message are perceivable to assistive tech (not
  conveyed by color alone).

### Privacy / no-external-call (must-pass, cannot be compensated)

- DevTools Network panel during a full load+chat+stop exchange shows requests to
  `http://127.0.0.1:8000` only.
- Static scan of `web/dist` finds no non-localhost `http(s)://` asset reference.
- No analytics/telemetry/remote-config request at any point.
- `index.html` carries a `default-src 'self'` (or stricter) CSP meta.
This criterion is a firewall: a UI that is otherwise perfect but makes any
off-origin request FAILS.

### Code quality (TRUST 5)

- **Tested**: `web/src/lib/` (esp. `sseClient.ts`) >= 85% coverage. All primary
  and edge scenarios pass.
- **Readable**: lint clean (ESLint for `web/`); clear component and module names.
- **Unified**: consistent formatting (Prettier/ESLint) across `web/`; consistent
  with the existing repo's English-comment convention.
- **Secured**: no off-origin runtime calls; CSP present; `LocalhostOnlyMiddleware`
  not weakened; no secrets in `web/` source; `StaticFiles` mounted AFTER API
  routes (no route shadowing).
- **Trackable**: all commits reference `SPEC-UI-001`. MX tags placed per
  `./spec.md` MX Tag Plan.

### Backend-delta safety (regression guard)

- The SPEC-INFRA-001 acceptance scenarios still pass after the `api/main.py`,
  `api/Dockerfile`, and `.dockerignore` deltas — specifically `/health`,
  `/v1/models`, and `/v1/chat/completions` still return their expected
  JSON/SSE responses and are NOT shadowed by the SPA mount (Risk 4).
- No production Node runtime exists in the final `api` image (Node appears in the
  build stage only); verifiable via `docker run --rm <api-image> node --version`
  failing / `which node` empty in the runtime stage.

### Definition of Done

A `/moai run SPEC-UI-001` execution is complete when all of the following hold:

- [ ] All six primary scenarios pass (manual browser verification for the
      end-to-end streaming path; automated tests for parser/component logic).
- [ ] All six edge-case scenarios pass.
- [ ] All five REQ-UI-* requirements have at least one passing test or scenario.
- [ ] `web/src/lib/` coverage >= 85%.
- [ ] No off-origin network request fires at runtime; bundle scan clean; CSP meta
      present (the privacy must-pass firewall).
- [ ] The SPA loads at `http://127.0.0.1:8000` after `./run_server.sh`, AND
      `/health` + chat endpoints still return JSON/SSE (mount ordering correct).
- [ ] The composer is disabled WHILE `/health` is 503 and enabled on 200.
- [ ] Stop aborts mid-stream, retains partial output, surfaces no error.
- [ ] Markdown + fenced code blocks render with locally bundled assets only.
- [ ] Page reload yields an empty conversation (no persistence).
- [ ] The final `api` runtime image contains no Node.
- [ ] `@MX:ANCHOR`, `@MX:WARN`, and `@MX:NOTE` tags placed per `./spec.md` MX Tag
      Plan.
- [ ] No item from the `./spec.md` Exclusions list was implemented.

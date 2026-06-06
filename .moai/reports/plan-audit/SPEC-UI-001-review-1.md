# SPEC Review Report: SPEC-UI-001
Iteration: 1/3
Verdict: PASS
Overall Score: 0.93

> Reasoning context ignored per M1 Context Isolation — no author reasoning or
> conversation history was consulted. The SPEC bundle (`spec.md`, `plan.md`,
> `acceptance.md`, `spec-compact.md`) was judged against the SPEC-INFRA-001
> ground-truth source (`api/main.py`, `api/inference.py`, `api/state.py`,
> `api/security.py`, `api/Dockerfile`, `api/requirements.txt`, `.dockerignore`).

## Must-Pass Results

- **[PASS] MP-1 REQ number consistency** — REQ-UI-001 … REQ-UI-005, sequential,
  zero-padded, no gaps, no duplicates (`spec.md:65,74,84,94,103`). Identical
  numbering in `spec-compact.md:16-39`. No drift between the two documents.

- **[PASS] MP-2 EARS format compliance** — All five EARS patterns present and
  each REQ uses its keyword:
  - REQ-UI-001 Ubiquitous: "The Argus chat UI SHALL be a static single-page
    application…" (`spec.md:67`).
  - REQ-UI-002 Event-driven: "WHEN the user submits a message…, the UI SHALL
    issue `POST /v1/chat/completions`…" (`spec.md:76-78`).
  - REQ-UI-003 State-driven: "WHILE `GET /health` reports the not-ready state…,
    the UI SHALL display…" (`spec.md:86-87`).
  - REQ-UI-004 Optional/Where: "WHERE the user activates the Stop control…, the
    UI SHALL abort…" (`spec.md:96-97`). Grammatically conforms to the Where
    pattern; semantic fit is a minor stretch (see D2) but not a format failure.
  - REQ-UI-005 Unwanted/If-Then: "IF a chat request fails before streaming
    begins…, THEN the UI SHALL surface…" (`spec.md:105-107`).

- **[PASS] MP-3 YAML frontmatter validity** — All required fields present with
  correct types (`spec.md:1-12`): `id: SPEC-UI-001` (string, matches pattern),
  `version: 0.1.0` (string), `status: draft` (string), `created: 2026-06-05`,
  `created_at: 2026-06-05` (ISO date), `updated: 2026-06-05`, `author: abjohn`,
  `priority: high` (string), `issue_number: 0` (matches required value;
  explained in HISTORY — `gh` CLI absent, same convention as SPEC-INFRA-001),
  `labels: [ui, frontend, react, vite, tailwind, streaming]` (array).

- **[N/A] MP-4 Section 22 language neutrality** — N/A: single-project SPEC. This
  is a concrete React/TypeScript product UI consuming a fixed Python API, not
  multi-language LSP/template tooling. No 16-language enumeration requirement
  applies. Auto-pass.

## Category Scores (0.0-1.0, rubric-anchored)

| Dimension | Score | Rubric Band | Evidence |
|-----------|-------|-------------|----------|
| Clarity | 0.90 | 0.75–1.0 | Every REQ has a single interpretation; only REQ-UI-004's Where/When semantic stretch (`spec.md:96`) requires minor reader resolution. |
| Completeness | 0.95 | 1.0 | HISTORY (`spec.md:14-18`), Overview/WHY+WHAT (`24-59`), Requirements (`61-111`), Exclusions w/ 12 entries (`113-145`), Files (`147-198`), Technical Approach (`200-253`), MX plan (`255-265`); AC in `acceptance.md` per MoAI convention; frontmatter complete. |
| Testability | 0.92 | 1.0 | All 6 primary + 6 edge scenarios have binary-observable Then-clauses (`acceptance.md:16-186`); no prohibited weasel words ("appropriate/adequate/reasonable/good/proper" absent). |
| Traceability | 1.00 | 1.0 | Every REQ has ≥1 AC; every "Maps to:" line references a valid REQ-UI-001..005; no orphaned ACs, no uncovered REQs (`acceptance.md:18,40,56,72,88,104,123,135,146,155,167,180`). |

## Ground-Truth Verification (audit focus items)

**1. API contract accuracy — VERIFIED CORRECT (the central claim is accurate).**
The SPEC asserts tokens arrive at `frame.message.content` (Ollama-native), NOT
`frame.choices[0].delta.content`. Confirmed against source:
- `api/inference.py:196-199` passes the raw Ollama `/api/chat` NDJSON line
  through unchanged ("we deliberately don't reshape it here"), wrapped as
  `data: <json>\n\n`. Ollama's native chat stream places token text at
  `message.content`. The SPEC's claim (`spec.md:55-58`, `78-81`, `220-221`;
  `acceptance.md:8-10,28-30`) is **correct**. No CRITICAL defect — the
  acceptance criteria parse the right shape.
- `[DONE]` sentinel: `api/inference.py:210` yields `data: [DONE]\n\n` —
  matches SPEC (`spec.md:174`, `acceptance.md:32`).
- In-band error frame: `api/inference.py:202` yields
  `data: {"error": "upstream stream broken"}\n\n` — matches SPEC's
  `{"error"}`-frame handling claim and its cited line `inference.py:202`
  (`spec.md:238`).
- Pre-stream 502: `api/main.py:214-220` returns `502` on `OllamaUnavailable` —
  matches SPEC's cited `main.py:214-220` (`spec.md:238`).
- Empty-stream path: `api/main.py:221-227` yields only `[DONE]` — matches
  `acceptance.md:153-163` (Edge case 4).
- Cleanup-on-abort: `api/inference.py:203-209` `finally` blocks close the
  stream/client — matches SPEC's cited `inference.py:203-209` (`spec.md:233`).
  **All file:line citations in the SPEC are accurate.**

**2. `/health` 503/200 readiness — VERIFIED CORRECT.** `api/main.py:168-173`:
`200 {"status":"ready"}` when READY else `503 {"status":"loading"}`;
`api/state.py:18-23` is a two-state LOADING/READY machine. REQ-UI-003
(`spec.md:86-92`) and `acceptance.md:54-68` describe exactly this and correctly
honor SPEC-INFRA-001 REQ-INFRA-003. The no-timeout stance matches the
documented long-pull contract (`api/inference.py:69-78`).

**3. Same-origin / middleware claim — VERIFIED CORRECT.** Serving the SPA from
the api origin means same-origin requests carry `Host: 127.0.0.1:8000` and
`Origin: http://127.0.0.1:8000`, both of which pass `is_localhost_header`
(`api/security.py:44-60`) and `extract_origin_host` (`api/security.py:63-89`).
The middleware (`api/main.py:75-102`) needs no CORS change and is not weakened.
SPEC claim (`spec.md:37-39,204-210`) is accurate. The dev-proxy mitigation
(`plan.md` Risk 6) also holds — proxied requests stay localhost-origin.

**4. StaticFiles mount ordering — VERIFIED SOUND.** Starlette matches routes in
registration order; a `Mount("/")` catch-all registered AFTER `/health`,
`/v1/models`, `/v1/chat/completions` lets the API routes win and the SPA serve
everything else. SPEC's ordering invariant (`spec.md:184-188`, `plan.md` Risk 4)
is correct. `StaticFiles` ships with Starlette/FastAPI — no new pip dependency
required; confirmed `fastapi>=0.115` in `api/requirements.txt:1`. Claim
(`spec.md:187`) accurate.

**5. fetch()+ReadableStream POST SSE — VERIFIED SOUND.** Native `EventSource` is
GET-only and cannot send a JSON body, so `fetch()` + `response.body.getReader()`
is the correct approach for the POST SSE stream. The endpoint returns
`StreamingResponse(media_type="text/event-stream")` (`api/main.py:234`),
readable as a stream. No contradiction.

**6. Multi-stage Dockerfile — VERIFIED SOUND (as a delta).** The existing
`api/Dockerfile:20` is single-stage `python:3.12-slim`; the SPEC proposes ADDING
a `node:20-slim` build stage + `COPY --from=build` (`spec.md:189-192`). Standard
front-end-in-backend pattern, implementable, Node absent from runtime. Correctly
labeled `[MODIFY]`.

## Defects Found

D1. `spec.md:194-195` (also `plan.md` Task 8, `spec-compact.md:90-91`) — The
`.dockerignore` change is described as "un-ignore `web/` source," but the actual
`.dockerignore` (`.dockerignore:1-35`) contains **no rule excluding `web/`** —
only specific paths (`.git/`, `.moai/`, `.claude/`, `*.md`, `__pycache__/`,
`api/tests/`, `run_*.sh`, etc.). There is nothing to "un-ignore." The genuinely
needed change is to **add** exclusions for `web/node_modules` and `web/dist` from
the python-stage context (which the SPEC also states correctly in the second half
of each mention). The "un-ignore" framing rests on a false premise. — Severity:
**Minor** (non-blocking; the dominant correct action is stated, and `/moai run`
will reconcile the actual `.dockerignore` edit).

D2. `spec.md:94-97` — REQ-UI-004 uses the EARS "WHERE" (Optional-feature)
keyword for what is semantically a user **event** ("WHERE the user activates the
Stop control during an in-flight generation"). Canonical "Where" gates an
optional capability ("Where the system includes feature X"); a user action reads
more naturally as event-driven ("WHEN the user activates Stop"). Grammar
conforms to the Where pattern, so MP-2 still passes, but the semantic fit is a
stretch. — Severity: **Minor**.

D3. `spec.md:78,97` — REQ-UI-002 and REQ-UI-004 name the browser class
`AbortController` in normative requirement text. RQ-4 prefers no class names in
requirements (the WHAT is "abort the in-flight request"). Defensible for an
integration SPEC against a fixed streaming API (AbortController is the only
fetch-cancellation primitive, and naming it aids the Scenario 2 test hook), but
strictly an implementation-name leak into a REQ. — Severity: **Minor**.

D4. `spec.md:106` — REQ-UI-005 lists "503" as a pre-stream chat-request failure
example, but the real `/v1/chat/completions` handler (`api/main.py:197-234`)
returns only `502` (`OllamaUnavailable`) or `200` (StreamingResponse) — never
`503` (which is `/health`-only per `api/main.py:168-173`). Hedged with "such
as," and gracefully handling an unexpected 503 is defensive design, not a
contract error. — Severity: **Minor**.

D5. `spec.md:49,123-124,178` — "display of the active model name" (ModelBadge) is
an Overview-level in-scope feature, but it is not one of the five REQ-UI-*
requirements and has no dedicated acceptance scenario asserting the displayed
value. Not an uncovered REQ (it is explicitly optional — `GET /v1/models` "MAY"
be read), so traceability is intact, but the narrative feature lacks a test
hook. — Severity: **Minor** (observation).

## Chain-of-Verification Pass

Second-look findings, verified by re-reading the following sections:
- **REQ numbering end-to-end** (not spot-checked): re-read all of `spec.md:65-111`
  and cross-checked `spec-compact.md:16-39` — confirmed REQ-UI-001..005, no
  gaps/dups, consistent across both docs.
- **Traceability for EVERY REQ** (not sampled): walked all "Maps to:" lines in
  `acceptance.md` — REQ-UI-001 (Scn 1,6 + Edge 6), 002 (Scn 1,4 + Edge 1,3,4,5),
  003 (Scn 3), 004 (Scn 2 + Edge 2), 005 (Scn 5 + Edge 4). No orphans, no
  uncovered REQs.
- **Exclusions specificity** (not just presence): all 12 entries (`spec.md:115-145`)
  are concrete, not vague, and consistent with the minimal-demo intent.
- **Contradiction scan** (across requirements AND across docs): checked
  Exclusions-vs-Requirements ("No backend changes beyond static-file serving"
  vs the named `api/main.py` mount + Dockerfile delta — consistent, the
  Dockerfile build step is explicitly permitted at `spec.md:136`); "No
  model-picker / no remote config" vs the optional same-origin `/v1/models`
  read — no conflict. No contradictions found.
- **Weasel-word scan of every AC**: no prohibited terms; "clear/human-readable"
  recur but each is backed by a binary observable.
- **New defect surfaced in second pass**: D1 (`.dockerignore` "un-ignore"
  mischaracterization) was found ONLY by reading the actual `.dockerignore`
  file rather than trusting the SPEC's description — added above.

The four audit-critical dimensions (API contract shape, /health states, EARS,
scope integrity) and the frontmatter + technical-soundness checks all hold with
ground-truth evidence. No Major or Critical defect exists.

## Recommendation

**PASS.** Rationale, with evidence per must-pass criterion:
- MP-1: REQ-UI-001..005 sequential, no gaps/dups (`spec.md:65-103`).
- MP-2: All five EARS patterns present and keyword-correct (`spec.md:67,76,86,96,105`).
- MP-3: All required frontmatter fields present with correct types (`spec.md:1-12`),
  `issue_number: 0` as required.
- MP-4: N/A (single-project React/Python SPEC).

The defining adversarial test — whether the acceptance criteria parse the
correct SSE shape — was the highest-stakes check, and the author got it right:
tokens at `message.content`, verified against `api/inference.py:196-199`. Every
file:line citation in the SPEC was checked and is accurate. The five Minor
defects (D1–D5) are non-blocking `/moai run` refinements and do not warrant
another iteration.

Optional polish for `/moai run` (not required to proceed):
1. Reword the `.dockerignore` task (D1) from "un-ignore web/" to "exclude
   `web/node_modules` and `web/dist` from the python-stage build context."
2. Consider rephrasing REQ-UI-004 from "WHERE the user activates Stop" to
   "WHEN the user activates Stop" if event-driven semantics are intended (D2),
   or keep Where if Stop is framed as an optional capability.
3. If model-name display (D5) is a committed feature, add a small acceptance
   assertion for the ModelBadge value or move it firmly into Exclusions as
   "best-effort only."

Verdict: PASS

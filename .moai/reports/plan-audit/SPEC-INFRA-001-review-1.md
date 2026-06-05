# SPEC Review Report: SPEC-INFRA-001
Iteration: 1/3
Verdict: FAIL
Overall Score: 0.68

Reasoning context ignored per M1 Context Isolation. Audit conducted from spec.md, acceptance.md, plan.md, and research.md files only.

---

## Must-Pass Results

- [PASS] MP-1 REQ number consistency
  - Evidence: spec.md:L32, L36, L40, L44, L48 enumerate REQ-INFRA-001 through REQ-INFRA-005 sequentially. No gaps, no duplicates, consistent 3-digit zero padding.

- [PASS] MP-2 EARS format compliance (requirements layer)
  - Evidence: All five EARS requirements are syntactically conformant:
    - REQ-INFRA-001 spec.md:L34 — Ubiquitous ("The Argus runtime SHALL serve...")
    - REQ-INFRA-002 spec.md:L38 — Event-driven ("WHEN scripts/run_server.sh is invoked..., the system SHALL pull...")
    - REQ-INFRA-003 spec.md:L42 — State-driven ("WHILE the model is still loading, the HTTP API SHALL respond...")
    - REQ-INFRA-004 spec.md:L46 — Optional/Where ("WHERE the operator sets the MODEL environment variable..., the system SHALL pull...")
    - REQ-INFRA-005 spec.md:L50 — Unwanted/If-Then ("IF the HTTP API receives a request..., THEN the system SHALL reject...")
  - Note: The Given/When/Then scenarios in acceptance.md are intentionally test scenarios, not EARS-form ACs. The binding normative statements are the REQs in spec.md, which all comply. This is acceptable structural separation, not mislabeling.

- [FAIL] MP-3 YAML frontmatter validity
  - Evidence: spec.md:L1-L10 frontmatter contains:
    ```
    id: SPEC-INFRA-001
    version: 0.1.0
    status: draft
    created: 2026-06-04
    updated: 2026-06-04
    author: abjohn
    priority: high
    issue_number: 0
    ```
  - Required field `created_at` is MISSING. The frontmatter uses `created` (spec.md:L5) instead of the protocol-required `created_at`. Field-name mismatch = missing required field.
  - Required field `labels` is MISSING ENTIRELY. No `labels` key appears anywhere in the frontmatter block.
  - Two missing required fields = MP-3 automatic FAIL.

- [N/A] MP-4 Section 22 language neutrality
  - Evidence: SPEC-INFRA-001 is a single-project infrastructure SPEC for the Argus product (Python/FastAPI + Docker stack). It is not template-bound multi-language tooling. The 16-language enumeration requirement does not apply. Per MP-4 N/A clause, auto-passes.

---

## Category Scores (0.0-1.0, rubric-anchored)

| Dimension | Score | Rubric Band | Evidence |
|-----------|-------|-------------|----------|
| Clarity | 0.75 | 0.75 band — minor ambiguity | spec.md:L50 "Origin or Host header resolves to a non-localhost address" — HTTP Host headers contain literal text and are not DNS-resolved by the receiver; "resolves to" wording is misleading. Otherwise unambiguous. |
| Completeness | 0.50 | 0.50 band — multiple sections sparse or missing | spec.md HISTORY (L12-14) and Overview (L20-28) present, REQUIREMENTS (L30-50) complete, Exclusions (L52-62) thorough. However: YAML frontmatter missing two required fields (created_at, labels); spec.md does not contain its own ACCEPTANCE CRITERIA section (lives in acceptance.md — acceptable per protocol); spec.md:L64-76 file list omits `.dockerignore` that plan.md:L21 schedules for creation. |
| Testability | 0.75 | 0.75 band — one AC imprecisely measurable | acceptance.md:L112 "First-token latency... target to be measured during /moai run. No specific number is invented here" has no binary pass/fail criterion — it documents an intent to measure, not a threshold to meet. All other primary scenarios (L9-77) and edge cases (L83-104) are binary-testable with explicit observable conditions (HTTP status codes, JSON body shapes, exit codes, file/volume state). Streaming throughput (L114) and cold-start time (L115) have explicit thresholds. |
| Traceability | 0.75 | 0.75 band — minor traceability gaps | Every REQ-INFRA-001..005 maps to at least one scenario (Scenario 1→REQ-002/001, Scenario 2→REQ-003, Scenario 3→REQ-001, Scenario 4→REQ-005, Scenario 5→REQ-002, Scenario 6→REQ-004). However, acceptance.md:L83-104 edge cases trace only to plan.md risks ("Maps to: Risk 2 in ./plan.md §3", "Maps to: Risk 5 in ./plan.md §3") rather than to specific REQ-INFRA-* identifiers. The mapping is indirect for edge cases. |

---

## Defects Found

D1. spec.md:L5 — YAML frontmatter uses `created: 2026-06-04` but protocol requires field name `created_at`. Field-name mismatch counts as missing required field. — Severity: critical

D2. spec.md:L1-L10 — YAML frontmatter is missing required field `labels` (array or string). No `labels` key appears in the frontmatter block. — Severity: critical

D3. acceptance.md:L112 — Performance target "First-token latency... target to be measured during /moai run. No specific number is invented here; the test will record the observed value..." is not binary-testable. It is a measurement intention, not an acceptance threshold. A tester cannot determine PASS or FAIL from this criterion. — Severity: minor

D4. spec.md:L50 — REQ-INFRA-005 uses the phrase "Origin or Host header resolves to a non-localhost address". HTTP Host/Origin headers contain literal hostname strings; the receiver does not DNS-resolve them before authorization. The middleware must compare the literal header value (after parsing the Origin URL's host component and any Host header port suffix) against a string allowlist. "Resolves to" implies DNS lookup behavior that is not intended. Misleading wording in a security-critical requirement. — Severity: minor

D5. spec.md:L64-L76 vs plan.md:L21 — spec.md's "Files to Be Created or Modified" enumeration omits `.dockerignore`, but plan.md Task 9 (L21) explicitly schedules its creation. The two documents disagree on the file set. spec-compact.md:L113-L121 also omits `.dockerignore`. Either the file should be added to spec.md and spec-compact.md, or Task 9 should be removed from plan.md with rationale. — Severity: minor

D6. acceptance.md:L83-L104 — Both edge case scenarios reference only plan.md risk numbers ("Maps to: Risk 2 in ./plan.md §3", "Maps to: Risk 5 in ./plan.md §3") and not specific REQ-INFRA-* IDs. Edge case 1 (partial model download) implicitly tests REQ-INFRA-002 and REQ-INFRA-003; Edge case 2 (host port already in use) implicitly tests the failure path of REQ-INFRA-002. Direct REQ traceability would tighten the audit chain. — Severity: minor

D7. spec.md:L59 vs research.md:L77-L87 — research.md Section 2 Decision states "Default runtime is Ollama; SPEC includes an llama.cpp escape hatch" with three specific deliverables ("Ship Ollama as the default... Document an alternative compose.llamacpp.yml overlay... Define the API contract at the Argus API layer"). spec.md:L59 instead declares "No llama.cpp escape hatch in v1. Documented in ./research.md as a future overlay; not implemented under this SPEC." The deferral is explicit and transparent in spec.md (not a hidden contradiction), but research.md was not amended to reflect the scope reduction. The HISTORY entry (spec.md:L14) does not call out this decision change. — Severity: minor (informational)

---

## Chain-of-Verification Pass

Second-look findings: Re-read each section that was reviewed quickly in pass 1.

- Re-verified every REQ-INFRA-001..005 line-by-line for EARS pattern conformance: all five conform exactly.
- Re-verified REQ number sequencing end-to-end (not just spot-check): REQ-INFRA-001 spec.md:L32, REQ-INFRA-002 spec.md:L36, REQ-INFRA-003 spec.md:L40, REQ-INFRA-004 spec.md:L44, REQ-INFRA-005 spec.md:L48. No skip, no repeat, consistent format.
- Re-verified traceability for EVERY REQ (not sampled): all five appear in at least one "Maps to:" line in acceptance.md (L11, L25, L35, L46, L57, L69).
- Re-verified Exclusions section for specificity: spec.md:L54-L62 lists 8 specific exclusions, each with concrete rationale (not vague placeholders).
- Re-read research.md decision sections for cross-file contradictions: found the llama.cpp escape hatch divergence (D7) that was not noted in pass 1. Added as D7.
- Re-read acceptance.md Performance targets section: confirmed only the first-token latency target lacks a threshold (D3). Throughput target (≥10 tokens/sec) and cold-start time (60s) are testable.
- Re-checked YAML frontmatter twice to confirm `created_at` and `labels` absence — confirmed both times.

One new defect was discovered in the second pass (D7). First-pass scoring was retained because D7 is informational severity and does not change overall verdict.

---

## Regression Check

N/A — this is iteration 1. No prior iteration report exists.

---

## Recommendation

The SPEC FAILS audit due to MP-3 YAML frontmatter violation. Two required fields are missing or misnamed. This is a hard blocker independent of the other dimension scores (which are otherwise in the 0.50-0.75 range — workable but not exemplary).

manager-spec must address the following before the next audit iteration:

1. **Fix MP-3 frontmatter (D1, D2) — required to unblock**:
   - In spec.md:L5, rename the field `created` to `created_at`. Keep the value `2026-06-04`. Result: `created_at: 2026-06-04`.
   - In spec.md frontmatter (L1-L10 block), add a `labels` field. Example: `labels: [infrastructure, runtime, docker, llama4]` or a single-string form per project convention. Place it near `priority`.

2. **Make the latency target testable (D3)**:
   - Either declare a concrete threshold in acceptance.md:L112 (e.g., "first-token latency ≤ 2.0 seconds on recommended-floor hardware"), or move the latency line out of "Performance targets" into a separate "Baseline measurements (informational, no gate)" subsection so it is not mistaken for an acceptance gate.

3. **Tighten REQ-INFRA-005 wording (D4)**:
   - In spec.md:L50, replace "whose Origin or Host header resolves to a non-localhost address" with "whose Origin URL host component or Host header value is not in the allowlist {`127.0.0.1`, `localhost`, `[::1]`}". This removes the DNS-resolution implication.

4. **Reconcile file enumeration (D5)**:
   - Add `.dockerignore` to spec.md:L64-L76 "Files to Be Created or Modified" with a one-line purpose statement, and mirror in spec-compact.md:L113-L121. Alternatively, remove Task 9 from plan.md if `.dockerignore` is not actually required for v1.

5. **Strengthen edge case traceability (D6)**:
   - In acceptance.md:L85 and L96, expand the "Maps to:" lines to include REQ-INFRA-* identifiers in addition to plan.md risk numbers. Example for Edge case 1: "Maps to: REQ-INFRA-002 (resume contract), REQ-INFRA-003 (loading→ready transition), Risk 2 in ./plan.md §3."

6. **Document the llama.cpp scope reduction (D7) — informational, not blocking**:
   - Add a HISTORY entry to spec.md:L12-L14 explicitly noting the decision to defer the llama.cpp escape hatch from research.md §2's recommendation. Example: "Llama.cpp escape hatch deferred to a follow-up SPEC despite research.md §2 recommending v1 inclusion; rationale: v1 scope discipline."

Once D1 and D2 are fixed, the audit will re-evaluate. D3 and D4 should be addressed in the same revision because they affect Testability and Clarity scores meaningfully. D5, D6, D7 are minor polish.

Verdict: FAIL

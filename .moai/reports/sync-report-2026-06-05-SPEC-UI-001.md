---
spec: SPEC-UI-001
sync_date: 2026-06-05
status_transition: draft → completed
branch: feature/SPEC-INFRA-001-runtime-foundation
---

# Sync Report — SPEC-UI-001 (React Chat UI)

## Documents updated

| File | Change summary |
|---|---|
| `.moai/specs/SPEC-UI-001/spec.md` | Frontmatter `status: draft → completed`; "## Implementation Notes" section appended (commits table, files created, test results, MX tags, quality verdicts, scope amendment). |
| `.moai/project/product.md` | Added "## SPEC-UI-001 Delivery (Chat UI, v1)" section parallel to the SPEC-INFRA-001 section; updated "First-Milestone Feature Scope" list to mark Chat UI as delivered and note first milestone is COMPLETE. |
| `.moai/project/structure.md` | Added `web/` to repository tree and added a full "## `web/` — React SPA" section (directory tree, key architectural decisions). Updated `api/Dockerfile` description to reflect multi-stage build. Added static SPA serving note to `api/` section. Removed `web/` from "Planned Directories". |
| `.moai/project/tech.md` | Added "## SPEC-UI-001 Stack (React Chat UI)" section covering frontend runtime deps (React 18, Vite 5, TS 5, Tailwind 3.4, react-markdown/remark-gfm/rehype-highlight, Vitest), key frontend decisions (fetch+ReadableStream over EventSource, same-origin serving, multi-stage Dockerfile, brand seam, CSP). Updated Open Decisions to mark three UI decisions resolved, with one remaining (brand values). Updated primary languages table. |
| `README.md` | Updated status banner to "First milestone complete (SPEC-INFRA-001 + SPEC-UI-001)"; added browser UI paragraph to Quick start; updated project layout to include `web/`; updated test count (103 → 117, 92.62% → 93%). |
| `CHANGELOG.md` | Added SPEC-UI-001 Added and Changed entries above the existing SPEC-INFRA-001 entries; preserves Keep-a-Changelog format. |
| `.moai/reports/sync-report-2026-06-05-SPEC-UI-001.md` | This file. |

## Divergence documented

**New `web/` directory:** A new top-level `web/` directory was created containing the React SPA source. This was not present after SPEC-INFRA-001 and required additions to structure.md, tech.md, README.md, and CHANGELOG.md.

**Frontend technology stack:** React 18, Vite 5, TypeScript 5, Tailwind CSS 3.4, react-markdown/remark-gfm/rehype-highlight, Vitest are now in use. tech.md carried a "planned" note for these; they are now documented as delivered with rationale.

**Backend serving delta:** `api/main.py` now mounts `StaticFiles`; `api/Dockerfile` is multi-stage. These changes were reflected in structure.md (Dockerfile description, new static-serving subsection) and tech.md (multi-stage Dockerfile key decision).

**Scope amendment:** `run_debug.sh` browser-launcher was repointed from port 3000 to API_PORT (:8000), and `run_server.sh` gained a ready-URL hint. These were documented in the spec HISTORY, the Implementation Notes scope amendment subsection, and the CHANGELOG Changed section.

## SPEC status transition

SPEC-UI-001 transitions from `draft` to `completed`. This is a Level-1 spec-first SPEC delivering a self-contained feature (browser chat UI). There is no ongoing maintenance cadence; the spec is closed. The first-milestone vertical slice is complete across both SPEC-INFRA-001 and SPEC-UI-001.

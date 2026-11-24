> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: PLAN.HUMAN.md.
# Project: link-expiry
Status: IMPLEMENTING

## Problem statement
Short links live forever. Owners want links for time-limited campaigns to stop working after a set time.
`SPECIFIED` (request, 2026-10-12)

## Goals
- A link can be created with an optional time to live (TTL). `SPECIFIED`
- An expired link no longer resolves, and callers can tell "expired" apart from "unknown". `SPECIFIED`

## Non-goals
- Deleting expired links from storage (no clean-up job). `SPECIFIED` (P4 answer to G2)
- Changing an existing link's expiry. `SPECIFIED`
- An HTTP layer. The package is a library. `DERIVED` (repo has no web code: `git ls-files` shows only `src/shortener/*.py`)

## Success criteria
- Every acceptance criterion in slices 01–02 is covered by an automated test that fails if the criterion is broken.
- Existing behaviour is unchanged for links created without a TTL (`tests/test_shortener.py` still passes untouched).

## Scope
`src/shortener/` and `tests/`. One public API change: `Shortener.create(url, ttl_seconds=None)`, and a new
`LinkExpired` error from `resolve`.

## Delivery parameters
| ID | Parameter | Value | Label |
|----|-----------|-------|-------|
| C-1 | Slice budget | ≤ 150 changed lines of production code per slice | SPECIFIED |
| C-2 | New-project budget | No new packages or services | SPECIFIED |
| C-3 | Reuse posture | Reuse the existing store and clock injection | ASSUMED (default) |
| C-4 | Existing-code blast radius | `src/shortener/` only; no config files | SPECIFIED |
| C-5 | Tracking artifacts | None (no work items) | SPECIFIED |
| C-6 | Time and artifact budget | Default artifact caps; finish in one working session per slice | ASSUMED (default) |
| C-7 | Convention posture | Follow repo conventions (unittest style, dataclasses) | ASSUMED (default) |
| C-8 | Feature branch / base branch | `feature/link-expiry` from `main` | SPECIFIED |
| C-9 | Cost budget | Standard routing; no extra reviewers beyond triggers | ASSUMED (default) |
| C-10 | Formal rigour | none | ASSUMED (default) |
| — | Brainstorm breadth | 1 (technical, value, contrarian) | ASSUMED (default) |

## Stakeholders
Repo owner (the human). No external consumers found. `DERIVED` (no other package imports `shortener`)

## Constraints
- Python 3.9+ (`pyproject.toml` → `requires-python`). `DERIVED`
- Canonical test command: `python -m pytest -q` (runs in under 2 s). `DERIVED` (ran it at P1)

## Relevant repositories and services
This repository only.

## Known dependencies
Standard library only; pytest for tests.

## Key terminology
- **TTL**: time to live, in whole seconds, chosen at creation.
- **Expired**: `clock() >= expires_at`.

## Framework configuration
- Compute: registry defaults, no lowered minimums.
- Notes branch: `feature/link-expiry-shipyard`. `.ai/` stays off the work branches (`/.ai/` added to
  `.git/info/exclude` at P0; the project's `.gitignore` is unchanged) and is snapshotted to the notes branch at
  every checkpoint.

## Phase log
| Date | Phase | Produced |
|------|-------|----------|
| 2026-10-12 | P0 Intake | C-1..C-10, branch `feature/link-expiry` created from `main`, state.json |
| 2026-10-12 | P1–P3 Discover | planning/discovery.md, planning/concepts.md, draft ARCHITECTURE/INVARIANTS |
| 2026-10-12 | P4 Grill | Concept A chosen; G1–G3 answered in one round; frontier empty |
| 2026-10-13 | P5–P7 Plan | DELIVERY_PLAN.md, slices 01–02, readiness goldfish READY ×2 |
| 2026-10-13 | P8 Plan approval | Approved by the human; slices 01–02 APPROVED |
| 2026-10-14 | P9 Slice 01 | READY_FOR_HUMAN after 1 fix round |
| 2026-10-14 | P9.9 Merge 01 | Merged into `feature/link-expiry` (`--no-ff`), tests re-run PASS |
| 2026-10-14 | P10 Reconcile | Architect VALID, planner UNCHANGED |
| 2026-10-15 | P9 Slice 02 | Branch `feature/link-expiry-slice-02` created; TEST_PLAN.md DRAFT under review |

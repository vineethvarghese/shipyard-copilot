# Changelog

## 1.1.0 — 2026-11-08

- TEST_PLAN.md gains `## Seams under test` (copied from SLICE.md; every planned test sits at one), a `Seam` column,
  an `## Invariants exercised` table with a "would fail against a no-op stub?" column, and `## Test doubles`.
- Rules: doubles only at system boundaries; expected values from an independent source of truth; test names in
  glossary terms; prior art followed.
- VERIFY reports `formal` (tier, checked, notRun) when C-10 is above none.
- Seam, doubles and tautology discipline adapted from an MIT-licensed TDD skill (see NOTICE).

## 1.0.0 — 2026-10-15

Initial release.

---
applyTo: "**/test/**,**/tests/**,**/__tests__/**,**/*.test.*,**/*.spec.*,**/*_test.*,**/test_*.*,**/*Test.*,**/*Tests.*,**/spec/**"
---

# Test files in a Shipyard project

- **The verifier owns every test.** In a Shipyard slice only `shipyard-verifier` writes, changes or deletes test
  files, fixtures and test helpers, and only inside the active slice's test touch set. The implementer never
  edits a test; a test it believes is wrong goes in `testDisputes` with a citation, and the architect rules.
- **Derive from the acceptance criteria, never from the implementation.** The direction is
  `approved requirements -> invariants -> acceptance criteria -> tests -> implementation`. A test written by reading
  the code encodes the code's bugs and reports green. If an acceptance criterion is too vague to test without
  reading the implementation, say so; the criterion is the defect.
- **Only planned tests.** Every test traces to a row of the approved `.ai/slices/<id>/TEST_PLAN.md`: an acceptance
  criterion, a seam the slice declares under `## Seams under test`, a level, and the failure or edge case it covers.
  No test before the plan says `Status: APPROVED`. A test the plan does not name is a plan change: rewrite the plan
  as `DRAFT` first.
- **Seams, not internals.** Observe behaviour through the public interface the slice names (a module boundary, an
  endpoint, a command, a topic). Test doubles only at system boundaries, each named in the plan with the boundary
  it stands in for.
- **Keep the canonical command canonical.** Run the repository's recorded test command exactly as recorded, never
  a filtered or quieter variant, when producing evidence. Filtered runs are debugging, not evidence.
- **Invariants need a test that can fail.** Each row under `## Invariants exercised` names a faulty implementation that
  violates the invariant and would fail the test (a safety property may hold for a do-nothing stub; the AC tests
  reject that). At C-10 `properties` and above, property tests; at `model-checked`, a trace replay.
- **Necessity goes both ways.** The code-reviewer may file "tests to remove" and "tests to reshape" as well as
  "tests to add". A redundant or tautological test is a finding owned by the verifier.
- The method lives in the skills `test-design` (writing) and `test-quality` (reviewing) under `.github/skills/`,
  with per-language conventions in `lang-packs/references/<language>.md`.

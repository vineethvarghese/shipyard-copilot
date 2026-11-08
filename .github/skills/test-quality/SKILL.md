---
name: test-quality
description: >
  Test review method for Shipyard. The code-reviewer loads it in TEST_PLAN mode to decide APPROVE or REVISE on a
  slice's TEST_PLAN.md, and in SLICE and RECHECK mode to review the tests in a diff together with the code. Covers
  the coverage pass (map tests to acceptance criteria, failure, edge and boundary cases, mental mutation), the
  necessity pass (classify every test Essential, Defensible, Redundant, Over-engineered, Wrong test or Borderline),
  seven language-agnostic test anti-patterns, and symmetric tests-to-add, tests-to-remove and tests-to-reshape
  findings owned by the verifier. Not for writing tests (test-design) or production-code clarity (code-clarity).
---

# Test quality

Version 1.1.0 · used by code-review (`shipyard-code-reviewer`, TEST_PLAN, SLICE and RECHECK)

Tests are code. They cost as much to maintain as production code, and a test that guards nothing is a liability: it
slows every change and gives false confidence. Your job is to push the suite toward **just the right amount of
coverage**: every acceptance criterion guarded by a test that would notice a regression, and nothing else. Missing
tests and needless tests are equally real findings.

## Part 1 — Reviewing TEST_PLAN.md (TEST_PLAN mode)

Read `SLICE.md` first, then `TEST_PLAN.md`. Check each item; every failed item is a finding in
`.ai/slices/<id>/findings/code-reviewer.test-plan.md` with `Owner: verifier`.

| # | Check | Fails when |
|---|---|---|
| 1 | Every AC is in the AC → tests table. | An AC is missing, or mapped to "covered by existing tests" with no test named. |
| 2 | Each AC is covered at the right level. | Unit tests are planned for wiring that only an integration test can exercise, or an end-to-end test is planned for pure logic a unit test covers. |
| 3 | Failure cases are planned. | An AC with an error path, invalid input or a limit has only happy-path tests. |
| 4 | Edge and boundary cases are planned. | Empty, one, maximum, off-by-one, duplicate, unicode, time-zone or concurrency edges the AC implies are absent. |
| 5 | Performance ACs have benchmarks. | An AC states a latency, throughput or memory target and no benchmark with a pass line is planned. |
| 6 | Nothing the type system already guarantees. | A planned test only checks a field's declared type, that a function exists, or a constant's value. |
| 7 | Tests derive from ACs, not the implementation. | A planned test is described in terms of internal functions or private state rather than observable behaviour. |
| 8 | ACs not verifiable here are listed with what is checked instead. | An AC needs a SHARED tier or a human check and the plan silently drops it. |
| 9 | Tiers are ordered simplest first and justified. | A costly tier is planned where a cheaper one reaches the AC. |
| 10 | Every planned test sits at a seam `SLICE.md` declares. | A test reaches past `## Seams under test` into a private module or internal collaborator; the plan invents a seam the slice never named (that is a question for the planner, not a test). |
| 11 | Test doubles only at system boundaries. | A fake of the project's own module or an internal collaborator; a double that stands in for the code under test. |
| 12 | Every invariant test can fail. | The "violating implementation it fails against" column is empty or names nothing concrete; the named implementation does not actually violate the invariant; no faulty implementation could fail the property (a tautology). A safety property holding for a do-nothing implementation is not a failure of this check when the AC tests reject that implementation. At C-10 `properties` and above, an invariant with `Check: property` has no property-based or assertion test. |

**Verdict.** `APPROVE` when no item fails at `MINOR` or above. Then, and only then, flip the status line with the
Edit tool (`Status: DRAFT` → `Status: APPROVED`); that is the only edit you may make to TEST_PLAN.md. Otherwise
return `REVISE` with the findings.

## Part 2 — Reviewing tests in a diff (SLICE and RECHECK mode)

Order: requirement (`SLICE.md` ACs) → tests → implementation. Read the tests before the code so you see what was
verified before you see what was built.

### Coverage pass

1. **Map tests to ACs, one by one.** List each AC and the test that proves it. An AC with no test is a finding.
2. **Failure, edge and boundary cases.** For every happy-path test, ask what the matching failure, empty, limit and
   off-by-one cases are, and whether the AC implies them.
3. **Mental mutation.** Pick a plausible bug (flip a comparison, drop a branch, return early, skip a write, swap two
   arguments). Would any test fail? If not, the path is uncovered whatever line coverage says. Name the mutation in
   the finding; it is the best evidence you can give.
4. Each gap becomes a **test to add** finding with `Owner: verifier`.

### Necessity pass — classify every test

Give each test (or tightly grouped block) one label:

| Label | Meaning | Action |
|---|---|---|
| Essential | Guards a real contract behaviour; a regression a user or caller would see makes it fail. | Keep. |
| Defensible | Not strictly required, but cheap, real, or records a non-obvious decision. | Keep. |
| Redundant | Another test already covers the same observable behaviour. | Remove. |
| Over-engineered | Checks implementation details (private state, call order, that A calls B, a mocked internal collaborator) instead of behaviour at a declared seam; breaks on refactor. | Reshape against behaviour, or remove. |
| Wrong test | Passes by coincidence; would stay green when the behaviour it names breaks. | Reshape. |
| Borderline | Could go either way. | Say why, recommend one way. |

Only Redundant, Over-engineered, Wrong test and contested Borderline tests become findings.

### Seven anti-patterns (any language)

1. **Proving what the compiler already proves.** Asserting that a constant equals itself, that a declared function
   exists, or that a constructor returns its own type. If the bug that would fail the test would also fail type
   checking or compilation, the test is noise.
2. **Tests that need a test-only door in production code.** A reset hook, an "internal" export, a visibility hack
   added only so a test can reach in. Remove the door and the test together. Real seams that the design calls for
   (an injected clock, a factory parameter) are fine.
3. **The same edge case tested at every layer.** When one behaviour (say, empty input does nothing) is asserted in
   the adapter, the service and the integration test, only the layer that owns the behaviour keeps the test.
4. **Count-only or shape-only checks beside a full check.** "Has 3 items" adds nothing when another test asserts the
   exact 3 items. Remove the weaker one.
5. **Asserting on text that is there by accident.** The test claims to check behaviour X but matches a word that
   appears for an unrelated reason (boilerplate, a help string). It passes by coincidence and breaks on rewording.
6. **Tautologies and restated setup.** The assertion recomputes the expected value the way the code does (the same
   formula, the same call, the same helper), so the test can only disagree with the code if the code disagrees
   with itself; or it asserts what follows mechanically from how the test built its inputs: a value passed into a
   constructor reads back the same; two new objects are different references. Expected values must come from an
   independent source: a known-good literal, a worked example, the AC's own numbers.
7. **Smoke noise.** "Module loads" or "creates without crashing" when the build already fails in that case. Real
   smoke tests that touch an external system (database, network, model) are different and can be Essential.

### Symmetry

A review that adds five tests and ignores ten redundant ones is incomplete. Report three kinds of test finding, all
with `Owner: verifier`:

- **Test to add** — from the coverage pass. Name the AC and the behaviour or mutation it must catch.
- **Test to remove** — from the necessity pass. Give `file:line` and a one-sentence reason.
- **Test to reshape** — over-engineered or wrong tests. Say what observable behaviour to assert instead.

Production-code problems you find while reading tests go to the implementer (`Owner: implementer`) under the
relevant code-review ability.

## Severity calibration

- `BLOCKING`: an AC that protects correctness, security or an invariant has no test that would catch its
  regression; or a Wrong test is the only proof of such an AC (it gives false assurance).
- `MAJOR`: an AC's failure or boundary case is untested; a test plan misses a benchmark for a performance AC; a
  test-only production door exists.
- `MINOR`: Redundant, Over-engineered or tautological tests; a test at the wrong level when the right level is cheap.
- `NOTE`: naming, small duplication in fixtures, Borderline calls.

## Finding examples

GOOD (AC named, mutation given, owner verifier):

```text
ID: code-008
Severity: MAJOR
Category: tests/test-to-add
Location: tests/discount.test.ts:1-48
Finding: AC-3 says a discount code expires at the end of its valid-until day, but no test covers a code used on or
  after that day.
Why it matters: Mutation check: changing `now <= validUntil` to `now < validUntil + 1 day` in src/discount.ts:22
  leaves every test green, so an off-by-one expiry would ship.
Evidence: SLICE.md AC-3; discount.test.ts has only `applies a valid code` and `rejects an unknown code`.
Required resolution: Add two tests: a code used at 23:59 on its valid-until day applies; one used at 00:00 the next
  day is rejected with CODE_EXPIRED.
Confidence: HIGH
Owner: verifier
Status: OPEN
```

BAD (coverage percentage as the goal, no AC, no location):

```text
ID: code-014
Severity: BLOCKING
Category: tests
Location: whole slice
Finding: Coverage is only 72%; more tests are needed.
Why it matters: High coverage is best practice.
Evidence: Coverage report.
Required resolution: Add tests until coverage is above 90%.
Confidence: MEDIUM
Owner: verifier
Status: OPEN
```

What is wrong with it: no AC or behaviour is named, line coverage is not the goal, nothing says which mutation goes
unnoticed, and it invites exactly the needless tests the necessity pass removes.

## Out of jurisdiction

- How to write the plan and the tests → `test-design` (the verifier's skill).
- Readability, design and performance of production code → `code-clarity`, `performance`, `domain-design`.
- Whether the slice's ACs themselves are right → raise a `NOTE` for the planner; do not rewrite them.
- Running SHARED validation tiers: never.

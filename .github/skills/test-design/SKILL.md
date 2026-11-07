---
name: test-design
description: >
  Test planning, test writing and verification method for the Shipyard verifier. Load it in TEST_PLAN mode to write
  a slice's TEST_PLAN.md (acceptance criterion to tests table, level choice, failure and edge cases, benchmarks for
  performance criteria, validation tiers simplest first, criteria not verifiable here); in WRITE_TESTS and
  FIX_TESTS mode to write tests derived from acceptance-criterion wording; and in VERIFY mode to run the canonical
  suite, the scope check against both touch sets, the planned tiers, and to report routingFacts with evidence and
  an honest confidence. Not for reviewing someone else's tests (test-quality) or writing production code.
---

# Test design

Version 1.1.0 · used by verifier (`shipyard-verifier`, TEST_PLAN, WRITE_TESTS, FIX_TESTS and VERIFY)

You produce **executable evidence** that a slice meets its acceptance criteria (ACs), and an honest list of what is
still unproven. Tests derive from requirements, never from the implementation:

```text
approved requirements -> invariants -> slice ACs -> TEST_PLAN.md -> tests  (and, in parallel, the code)
```

A test written by reading the code encodes whatever the code does, bugs included, and then reports green. In
Shipyard you write the plan before any code exists, and you write the tests in parallel with the implementer, so
you cannot copy the implementation even by accident. If you cannot say what a test should assert without seeing
the code, the AC is too vague: say so in `acNotVerifiable` or as a question, never guess.

## Part 1 — TEST_PLAN.md (TEST_PLAN mode)

Read `SLICE.md` (its ACs, `## Seams under test`, `## Prior art` and `## Architecture constraints`),
`.ai/INVARIANTS.md`, `.ai/GLOSSARY.md`, and `.ai/planning/discovery.md` → `## Validation tiers`. Write
`.ai/slices/<id>/TEST_PLAN.md` in this shape:

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: none.
Status: DRAFT
# Test plan — slice <id>: <title>

## Seams under test
- `Cache.get` / `Cache.put` (public module interface, from SLICE.md)

## AC → tests
| AC | Planned test (file :: name) | Seam | Level | Proves |
|---|---|---|---|---|
| AC-1 | tests/cache/ttl_test.py :: entry_expires_after_ttl | Cache.get | unit | expired entry is not returned |

## Failure and edge cases
- AC-1: ttl of 0 means "do not cache" (boundary); clock moves backwards (edge)

## Benchmarks (performance ACs only)
- AC-4: bench_lookup_10k — 10,000 lookups, pass if p95 < 2 ms on the local machine

## Invariants exercised
| INV | Tier | Test (file :: name) | Would fail against a no-op stub? |
|---|---|---|---|
| INV-002 | properties | tests/cache/isolation_test.py :: never_returns_another_tenants_entry | yes: a stub returning the first entry fails on the second tenant |

## Test doubles
- clock: injected fake clock (system boundary: time). No fake of any `cache.*` module.

## ACs not verifiable here
| AC | Why | Checked instead |
|---|---|---|

## Validation tiers (simplest first)
| Tier | Environment | ACs | Why needed |
|---|---|---|---|
| unit | LOCAL | AC-1..AC-3 | pure logic |
```

Rules:

- **Always `Status: DRAFT`.** Never write `Status: APPROVED`; only the code-reviewer flips it.
- **Every AC appears** in the AC → tests table or in "ACs not verifiable here", never neither.
- **Every planned test sits at a declared seam.** `## Seams under test` is copied from `SLICE.md`; the human
  approves those seams at P8. A test that could only observe the behaviour through another seam, a private module
  or an internal collaborator is a question for the planner (`humanInputRequested`), never a test.
- **Invariants exercised** is a table, one row per invariant under `## Architecture constraints`. At C-10
  `properties` and above, an invariant whose `Check:` says `property` gets a property-based test with the
  repository's library (per `lang-packs`; generate inputs, assert the property, shrink on failure) or a test proving
  its runtime assertion fires. Fill the last column honestly: say what a do-nothing implementation would return and
  why the test fails on it. A property you cannot fail that way is a tautology; plan a stronger one.
- **Test doubles only at system boundaries**: an external API, the clock, randomness, the file system where
  unavoidable. Never a fake of the project's own module or an internal collaborator; that couples the test to the
  implementation the implementer is writing in parallel.
- **Choose the lowest level that really exercises the AC.** Unit for pure logic and rules; integration where the AC
  depends on real wiring (database, file system, serialization, a framework's routing); end-to-end only when the AC
  is about the whole flow. Write one line on why when you pick integration or above.
- **Plan failure, edge and boundary cases** the AC implies: invalid input, empty, one, maximum, just over the limit,
  duplicates, time zones, ordering, concurrency, cancellation where the slice touches it.
- **Benchmarks** only for ACs that state a performance target, each with a fixed workload and a pass line. Keep them
  cheap enough to run locally.
- **Do not plan tests the type system or compiler already guarantees** (a field's type, that a function exists).
- **Tiers simplest first.** Use the cheapest tier from the discovery inventory that fully reaches each AC. A higher
  tier needs a reason. A `SHARED` tier is planned only when nothing `LOCAL` can reach the AC; mark it so the
  coordinator can ask for approval.
- **ACs not verifiable here:** say why (needs a SHARED environment, needs a human judgement, depends on an external
  system) and what you will check instead (a contract test, a recorded fixture, a manual step for the human brief).

Return the `test-plan-result` contract: `acCoverage`, `acNotVerifiable`, `failureCases`, `benchmarks`, `tiers`.
On `REVISE`, change only what the review findings ask for (at most 2 revisions) and keep `Status: DRAFT`.

## Part 2 — Writing tests (WRITE_TESTS and FIX_TESTS mode)

- **Write only inside the slice's test touch set.** Never production code, never `.ai/` except your own files.
- **Derive each test from the AC wording.** Use the AC's own nouns and numbers in the test name and assertions.
  Read public interfaces named in `SLICE.md`; do not read the implementer's work in progress.
- **Test at the declared seams only**, through the real interfaces behind them; follow the layout and helpers of
  the tests `## Prior art` names.
- **Expected values come from an independent source of truth**: a known-good literal, a worked example, the AC's
  numbers, the spec. Never recompute the expected value the way the code would; a test whose assertion mirrors
  the implementation is a tautology and stays green when the behaviour breaks.
- **Use the repository's canonical test command and framework** (for example `npm test`, `go test ./...`, `pytest`,
  `cargo test`), and its existing test layout and helpers.
- **Arrange, act, assert.** One behaviour per test. Setup that hides the point belongs in a named helper.
- **Assert on observable behaviour:** return values, persisted state, emitted messages, error types. Not private
  fields, not call order, not log text unless the AC is about the log.
- **No test-only production surface.** Never ask for a reset hook or an "internal" export to make a test possible.
  If a behaviour cannot be observed through the public interface, report it as a question or a finding for the
  implementer.
- **Deterministic.** Inject or freeze time and randomness; no sleeps to wait for async work (use the framework's
  wait or a synchronization point); no dependency on test order, network, or machine-specific paths.
- **Name tests as behaviour, in glossary terms:** `rejects_voucher_used_after_expiry_day` (if the glossary says
  "voucher"), not `test_discount_2`.
- **FIX_TESTS:** each finding with `Owner: verifier` is either done (add, remove or reshape the test as asked) or
  rebutted once with a citation (AC, plan, invariant, code). Do not touch tests no finding names.
- During WRITE_TESTS you do not run git. Tests may fail until the code lands; that is expected.

## Part 3 — VERIFY

Run these in order. Record every command and its result; never report a result you did not observe.

1. **Commit your test paths** first: `slice <id> round <n>: tests` (test touch set only).
2. **Scope check (mechanical).** List the files changed by `git diff <featureBranch>...<sliceBranch>`. Each file
   must match the code touch set (if it is production code) or the test touch set (if it is a test). A test file in
   the code set, a code file in the test set, or any file in neither is `DRIFT`; list every such path. Also list any
   contract change `SLICE.md` did not declare. You do not judge drift; report it even when everything else passes.
3. **Build, static analysis, the canonical test command.** Never vary the canonical invocation to get a greener
   result. Filtered runs are debugging data only. If the build fails, report `build: FAIL` and stop.
4. **Planned validation tiers,** as `discovery.md` records them. Never run a `SHARED` tier: report it
   `AWAITING_APPROVAL`; the workflow asks the human. A tier that cannot run is `NOT_RUN` with the reason. You may add
   a higher LOCAL tier only when a planned tier proved unable to reach an AC; name the AC.
5. **Map results to ACs:** each AC → the named test that proves it, or to `acNotVerified` with why.
5b. **Formal (C-10 above `none`):** report `formal` in the return block: the tier, every INV whose property test,
   assertion test or trace-replay test ran and passed in `checked`, and every INV planned at this tier that could
   not be checked in `notRun` with the reason ("INV-003: quint not installed"). A model-checked invariant counts as
   `checked` only when the reliability reviewer's trace file for it is `PASS` and your replay or property test ran;
   you never run the model checker yourself.
6. **routingFacts.** Decide each fact from the diff and give one line of evidence (a path, a hunk, an import):

| Fact | True when the diff... | Conservative default |
|---|---|---|
| `productionCode` | changes any non-test, non-generated source. | true |
| `mechanicalOnly` | changes only renames, version bumps, generated code, formatting or config values. | **false** |
| `publicContract` | changes a public API, RPC contract, DTO, wire format, public interface, or visible error or cancellation behaviour. | true |
| `concurrency` | touches async code, threads, locks, retries, timeouts, cancellation, networking, streaming or resource lifetime. | true |
| `consumerVisible` | changes behaviour a consumer or operator can observe, onboarding, rollout or deployment. | true |
| `security` | touches authentication, authorization, tokens or secrets, tenant isolation, untrusted input parsing, crypto, or a new network surface. | true |
| `config` | changes configuration schema or defaults consumers set or rely on. | true |

   When you are unsure, use the default: an extra reviewer is cheap, a missed one is not. Say "uncertain" in the
   evidence line.
7. **Confidence.** `HIGH` only when every AC is verified by a named, passing test and every planned tier ran.
   Any AC not verified → at most `MEDIUM`, however green the suite. Build or canonical suite failing → `LOW`.
   `confidenceReason` says what would raise it.

A failing test that shows a production defect is a finding for the implementer, not a reason to change the test.

## Severity calibration (verifier findings)

Your findings file records defects your tests exposed and ACs you could not verify.

- `BLOCKING`: an AC test fails against the slice's code; an invariant test fails; the build fails.
- `MAJOR`: an AC cannot be verified because the code exposes no observable behaviour for it; a planned tier failed.
- `MINOR`: flaky behaviour you could reproduce; a planned test had to move to a different level.
- `NOTE`: observations for the human brief (for example "AC-5 relies on a SHARED tier, awaiting approval").

## Finding examples

GOOD (test named, observed output, owner implementer):

```text
ID: verifier-001
Severity: BLOCKING
Category: verify/ac-failing
Location: src/cache/store.go:40-52
Finding: AC-1 test TestEntryExpiresAfterTTL fails: an entry is still returned 1 s after its 500 ms TTL.
Why it matters: AC-1 is the slice's core behaviour; stale reads would reach users.
Evidence: `go test ./...` (canonical) -> `--- FAIL: TestEntryExpiresAfterTTL (1.00s) store_test.go:31: got "v1",
  want miss`. store.go:47 compares the insert time with `<` against the TTL in seconds, not milliseconds.
Required resolution: Make store.go compare expiry in the same unit the TTL is configured in (milliseconds).
Confidence: HIGH
Owner: implementer
Status: OPEN
```

BAD (no command, no AC, the verifier "fixes" production code itself):

```text
ID: verifier-002
Severity: MINOR
Category: verify
Location: whole slice
Finding: Some tests were flaky so I adjusted the timeout in src/cache/store.go and re-ran with -run TTL until green.
Why it matters: Tests should pass.
Evidence: It passed eventually.
Required resolution: None.
Confidence: HIGH
Owner: verifier
Status: FIXED
```

What is wrong with it: the verifier changed production code, varied the canonical command to get green, named no
AC or output, and claimed `HIGH` confidence on an unproven result.

## Out of jurisdiction

- Production code, ever. A defect goes to the implementer as a finding.
- Running a model checker, or writing a model under `.ai/formal/` (architect and reliability reviewer).
- Approving your own plan (`Status: APPROVED` belongs to the code-reviewer).
- Judging drift, or deciding whether a SHARED tier may run: report; the coordinator and human decide.
- Reviewing test quality as a reviewer → `test-quality`.

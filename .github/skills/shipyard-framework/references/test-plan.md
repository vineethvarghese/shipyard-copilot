# Test plan first

No production code and no test code for a slice until its `.ai/slices/<id>/TEST_PLAN.md` says `Status: APPROVED`
(hard rule 14).

## Why

- **Tests derive from the acceptance criteria, not from the implementation.** Tests written after the code tend to
  prove what the code does, not what the slice promised. Planning them first, from `SLICE.md` alone, makes them an
  independent check.
- **Cheap disagreement.** A gap in the ACs or a missing failure case is found while it costs one paragraph, not one
  fix round.
- **Parallel work.** Once the plan is approved, the implementer and the verifier build against the same contract at
  the same time, without reading each other's work.

## Who does what

| Step | Role and mode | Class | Output |
|---|---|---|---|
| 1 | verifier `TEST_PLAN` | DEEP | `TEST_PLAN.md` with `Status: DRAFT`; `contracts/test-plan-result` |
| 2 | code-reviewer `TEST_PLAN` | DEEP | `findings/code-reviewer.test-plan.md`; verdict `APPROVE` or `REVISE`; on `APPROVE`, the status flip |
| 3 | verifier `TEST_PLAN` again, with the findings | DEEP | revised `TEST_PLAN.md`, still `DRAFT` (at most 2 revisions) |
| 4 | implementer `IMPLEMENT` ‖ verifier `WRITE_TESTS` | STANDARD | code in the code touch set ‖ tests in the test touch set |

All four run inside the `shipyard-slice` workflow. Still not approved after 2 revisions → the workflow returns `ESCALATE`, the
slice stays `TEST_PLANNING`, and the coordinator brings the open test-plan findings to the human.

## What TEST_PLAN.md must contain

Template: `artifact-templates.md`. The verifier writes it from `SLICE.md`, `INVARIANTS.md`, `discovery.md`
(validation tiers, test conventions) and the code as it stands **before** the slice. It never reads or guesses the
implementation, which does not exist yet.

1. **The status line.** A line exactly `Status: DRAFT` within the first 10 lines. The verifier never writes
   `Status: APPROVED`.
2. **AC → planned tests.** Every acceptance criterion maps to one or more named tests (`file :: test name`), each
   with its level and what it proves. Test files lie inside the slice's test touch set.
3. **Seams under test**, copied from `SLICE.md`: every planned test observes behaviour through one of them. A test
   that would need another seam is a question for the planner (`humanInputRequested` or a `NOTE`), never a test.
4. **Levels** — `unit`, `integration`, `e2e`, `benchmark` or `tier` — and why each AC sits at its level. Use the
   lowest level that can actually observe the behaviour.
4. **Failure, edge and boundary cases**, each tied to an AC: empty, one, many, limits and limit+1, invalid input,
   time-outs, cancellation, partial failure, concurrent access where relevant.
6. **Benchmarks** for every performance AC: what is measured, the baseline, the threshold, the command.
7. **Invariants exercised**: a table `INV | Tier | Test (file :: name) | Would fail against a no-op stub?` for every
   invariant the slice names under `## Architecture constraints`. At C-10 `properties` and above, an invariant whose
   `Check:` says `property` gets a property-based test (the repository's library, per `lang-packs`) or a test that
   proves its runtime assertion fires. The last column must say how the test would fail against an implementation
   that does nothing: a property that passes against a no-op stub is a tautology.
8. **Test doubles**: each fake and the system boundary it stands in for (an external API, the clock, randomness,
   the file system where unavoidable). Never a fake of the project's own module or an internal collaborator.
9. **ACs not verifiable here**, each with why and what is checked instead.
10. **Validation tiers** from `discovery.md`: name, `LOCAL` or `SHARED`, which ACs, why the tier is needed.
11. **Deliberately not tested**, with the reason — for example a property the type system already guarantees.
12. **Commands**: the canonical suite command and the narrowest command per planned test file.

## What the code-reviewer checks in TEST_PLAN mode

The code-reviewer reads only the raw `SLICE.md` and `TEST_PLAN.md` (no diff — there is no code yet), loads its
`test-quality` capability skill, and checks:

| Check | A failure looks like |
|---|---|
| **Every AC covered at the right level** | An AC with no test; an integration behaviour tested only with mocks; an e2e test where a unit test would observe the same thing. |
| **Failure, edge and boundary cases** | Only the happy path; no limit or limit+1 case for a stated limit; no error-path test for a stated error. |
| **Mental mutation** | For each planned test, imagine a plausible bug in the code it covers (off-by-one, wrong comparison, swallowed error, missing call). If no planned test would fail, the plan is too weak there. |
| **Benchmarks for performance ACs** | A latency, throughput or memory AC with no measurement, no baseline or no threshold. |
| **No tests for what the type system guarantees** | Tests that a typed field has its type, that a non-nullable value is not null, or that a compiler-checked interface is implemented. Remove them; they cost time and prove nothing. |
| **Tests derive from ACs, not implementation** | Planned tests that name private helpers or internal call order the spec never mentions. |
| **Touch set and tiers** | A planned test file outside the test touch set; a `SHARED` tier presented as routine. |
| **ACs not verifiable here** | Silently missing ACs instead of a named entry with what is checked instead. |
| **Every test at a declared seam** | A planned test that reaches past `## Seams under test` into a private module or an internal collaborator; a seam the slice never declared. |
| **Doubles only at system boundaries** | A fake of the project's own module, a mocked internal collaborator, or an invariant property that would still pass against a no-op stub. |

Each gap is a finding in the standard schema (`finding-schema.md`) with `Owner: verifier`, written to
`.ai/slices/<id>/findings/code-reviewer.test-plan.md`. Verdict `REVISE` if any `BLOCKING`, `MAJOR` or `MINOR` finding
is open; else `APPROVE`.

## The approval flip: the only gate

Approval is one line in one file, changed by one agent:

- On verdict `APPROVE`, and only then, the code-reviewer uses the **Edit** tool on `TEST_PLAN.md` with
  `old_string` `Status: DRAFT` and `new_string` `Status: APPROVED`. Nothing else in the file changes.
- The write-scope hook allows the code-reviewer exactly that edit and blocks any other change it tries to make to
  `TEST_PLAN.md`. It blocks the verifier from ever writing `Status: APPROVED`, and blocks the coordinator from writing
  the status line at all.
- No other signal counts: not a verdict in a return block, not a chat message, not the coordinator's opinion. If the
  line does not say `APPROVED`, the plan is not approved.

The code-reviewer reads the line back after its edit and reports it in `extras.testPlanStatus`; a verdict of
`APPROVE` without `APPROVED` there stops the workflow (`BLOCKED`) before anything is built. Every `VERIFY` re-reads
the line independently (`testPlanStatus` in `verify-result`) and the workflow stops unless it is `APPROVED`, so a
resumed run cannot skip the gate either.

**An approved plan is frozen.** After approval the verifier may not edit `TEST_PLAN.md`: no planned test is dropped
or weakened during the build or the fix rounds (write-scope enforces this). The only allowed change is a full
rewrite with the Write tool that sets `Status: DRAFT` (for example after a human change to an AC), and the gate then
closes again until the code-reviewer re-approves.

## After approval: implementer and verifier in parallel

In the same working tree, at the same time:

- the implementer (`IMPLEMENT`) writes production code in the **code** touch set only, derived from `SLICE.md` and
  `TEST_PLAN.md`, and commits it (`slice <id> round <n>: code`);
- the verifier (`WRITE_TESTS`) writes the planned tests in the **test** touch set only, derived from `SLICE.md` and
  `TEST_PLAN.md`, and does not run git.

Neither reads the other's output. The disjoint touch sets make the parallel writes safe; the write-scope hook enforces
them. Tests written this way may fail at first against a half-written implementation; that is expected until
`VERIFY`, where the verifier commits its tests and runs the suite against both.

## The test-plan-gate hook

PreToolUse on `Edit|Write|MultiEdit|NotebookEdit|Bash`, for `shipyard-implementer` and `shipyard-verifier`. It reads `state.json` →
`activeSlice`, then that slice's `TEST_PLAN.md`:

- the status line is not `Status: APPROVED` (or the file or the state is missing) → deny any write to the code or
  test touch set, with a message naming the slice and the line it found;
- the verifier's own writes to `TEST_PLAN.md` are always allowed, so it can draft and revise the plan.

For Bash, the hook checks every project path the command visibly writes (redirects, `tee`, `sed -i`, `cp`, `mv`,
`rm`, `touch`, `git rm/mv/restore`). It cannot see a program that writes files itself (`python -c`, a build
script); the rule binds every agent regardless, and VERIFY's scope check lists every changed path.

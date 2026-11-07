# The slice loop

Each slice runs the same loop. The coordinator sets it up. In CLI mode the `shipyard-slice` dynamic workflow runs
it, with its order and caps fixed in code; in IDE and cloud modes the coordinator runs the same steps itself,
following `.github/prompts/shipyard.slice.prompt.md`, and the `shipyard-slice-check` pull-request check verifies the
touch sets and the test-plan order afterwards ([modes.md](modes.md)). You approve the result.

## The loop at a glance

```mermaid
flowchart TD
    start["Coordinator creates the slice branch"] --> tp["Verifier writes TEST_PLAN.md as DRAFT"]
    tp --> gate{"Code-reviewer: approve the test plan?"}
    gate -->|"REVISE, at most 2 revisions"| tp
    gate -->|"still not approved"| esc1["ESCALATE to you"]
    gate -->|"APPROVE"| build
    subgraph build["In parallel, same working tree"]
        impl["Implementer writes code"]
        wt["Verifier writes tests"]
    end
    build --> ver["Verifier VERIFY: commit tests, run suite, scope check, routing facts"]
    ver -->|"a SHARED tier is needed"| shared["NEEDS_SHARED_APPROVAL: you decide"]
    ver --> route["Routed reviewers in parallel; code review always"]
    route -->|"a reviewer fails twice"| blocked["BLOCKED_REVIEWER: fail closed"]
    route --> dedupe["Dedupe findings"]
    dedupe --> open{"Any open finding at MINOR or above?"}
    open -->|"yes, under 3 rounds so far"| fix["Fix round: implementer and verifier fix or rebut; architect rules on disputes"]
    fix --> ver
    open -->|"yes, 3 rounds used"| esc2["ESCALATE with the open findings"]
    open -->|"no"| brief["Coordinator writes EVIDENCE.md and REVIEW.HUMAN.md"]
    brief --> human{"You approve?"}
    human -->|"you request changes"| hfix["Change run: authors apply your requests, outside the round cap"]
    hfix --> ver
    human -->|"yes"| merge["git merge --no-ff into the feature branch"]
    merge --> rec["P10 Reconcile"]
    classDef human fill:#fde68a,stroke:#b45309,color:#000000
    class esc1,shared,esc2,human human
```

<sub>Source: [05-slice-loop.mmd](diagrams/05-slice-loop.mmd) · rendered: [05-slice-loop.svg](diagrams/05-slice-loop.svg)</sub>

Step by step:

1. **Slice branch.** The coordinator creates `<feature>-slice-<id>` from the tip of the feature branch, checks it
   out, and records it in `state.json`. Then it launches the workflow (CLI) or starts the prompt-file checklist (IDE, cloud).
2. **Test plan.** The verifier writes `.ai/slices/<id>/TEST_PLAN.md` with `Status: DRAFT`. It maps every
   acceptance criterion to planned tests at the seams the slice declares, lists failure cases, benchmarks for
   performance criteria, the invariants exercised (with a property test each at C-10 `properties` and above), the
   test doubles and their system boundaries, and what cannot be verified here.
3. **Test-plan gate.** The code-reviewer reviews the plan. On APPROVE it changes only the status line to
   `Status: APPROVED` and reads it back; if the change did not land, the workflow stops before anything is built.
   On REVISE the verifier revises. After 2 revisions without approval, the workflow returns `ESCALATE`. Once
   approved, the plan is frozen: changing it means rewriting it as `DRAFT` and approving it again.
4. **Build, in parallel.** The implementer writes code in the code touch set. The verifier writes tests in the
   test touch set. Both work from `SLICE.md` and `TEST_PLAN.md`, never from each other's work. In CLI mode a hook blocks
   both until the plan is approved, whether they write with the editor tools or the shell; elsewhere the
   pull-request check catches a violation. The implementer
   commits `slice <id> round <n>: code`. If an author says the approved design cannot be followed, or that a
   test is wrong, the architect rules on it and the ruling goes back to the right author in the same round.
5. **Verify.** The verifier confirms the test plan still says `APPROVED` (the workflow stops if not), commits
   `slice <id> round <n>: tests`, runs the full test suite, checks that every
   changed file is inside a touch set, runs the planned validation tiers, and reports routing facts. If a tier
   needs a shared environment, the workflow stops with `NEEDS_SHARED_APPROVAL`. The coordinator asks you, and
   re-launches only after an explicit yes.
6. **Routed review.** The reviewers that the facts call for run in parallel on the raw diff
   `git diff <featureBranch>...<sliceBranch>`, the raw `SLICE.md` and the raw `TEST_PLAN.md`. The code reviewer
   always runs, even for a slice that only adds tests. A finding filed with category `security` brings in the
   security reviewer if routing had not.
7. **Dedupe.** Findings from different reviewers at the same location in the same category become one finding.
   It keeps the highest severity and every reporter. Two findings from the same reviewer are never merged.
8. **Fix round.** If any finding at `MINOR` or above is open, the implementer (code findings) and the verifier
   (test findings) fix or rebut in parallel. A rebuttal goes to the reviewer that filed the finding, once. Then
   the loop goes back to step 5. In the next review, reviewers recheck their open findings, and the code reviewer
   also reviews everything changed since its last review, even if it had no findings of its own.
9. **Brief.** When nothing at `MINOR` or above is open and no author reports stubs or unmet acceptance criteria,
   the workflow returns `READY_FOR_HUMAN`. The coordinator
   writes `EVIDENCE.md` and `REVIEW.HUMAN.md`, snapshots `.ai/` to the notes branch (never the slice branch), and
   shows you the brief.
10. **Merge.** You approve (`APPROVE MERGE slice <id>`; in cloud mode, by approving and merging the slice pull
    request). The coordinator merges with `--no-ff` into the feature branch and runs reconcile (P10).
    If you ask for changes instead, the coordinator relaunches the workflow with your requests as `humanChanges`:
    the authors apply them (they cannot rebut you), then verification and every routed review run again in full.
    Your requests do not use up the 3 fix rounds. A change that alters the acceptance criteria goes back through
    `SLICE.md` and a fresh run, starting from the test plan.

## Slice states

```mermaid
stateDiagram-v2
    [*] --> PROPOSED
    PROPOSED --> APPROVED: you approve the plan at P8
    APPROVED --> TEST_PLANNING: slice branch created
    TEST_PLANNING --> IMPLEMENTING: test plan APPROVED
    IMPLEMENTING --> VERIFYING: code and tests written
    VERIFYING --> AGENT_REVIEW: suite and scope checks done
    AGENT_REVIEW --> CHANGES_REQUESTED: open findings
    CHANGES_REQUESTED --> IMPLEMENTING: fix round, at most 3
    AGENT_REVIEW --> READY_FOR_HUMAN: no open findings
    READY_FOR_HUMAN --> HUMAN_REVIEW: brief shown to you
    HUMAN_REVIEW --> IMPLEMENTING: you request changes
    HUMAN_REVIEW --> MERGED: you approve and the merge succeeds
    MERGED --> [*]
```

<sub>Source: [06-slice-states.mmd](diagrams/06-slice-states.mmd) · rendered: [06-slice-states.svg](diagrams/06-slice-states.svg)</sub>

| State | Meaning |
|---|---|
| `PROPOSED` | In the plan, not yet approved |
| `APPROVED` | You approved the plan at P8 |
| `TEST_PLANNING` | The test plan is being written and reviewed |
| `IMPLEMENTING` | Code and tests are being written, or fixed |
| `VERIFYING` | The suite, scope check and tiers are running |
| `AGENT_REVIEW` | Routed reviewers are reviewing |
| `CHANGES_REQUESTED` | Open findings; a fix round follows |
| `READY_FOR_HUMAN` | Clean; the brief is being written |
| `HUMAN_REVIEW` | You have the brief |
| `MERGED` | Merged into the feature branch. The only end state |

`HUMAN_REVIEW` is set when you are shown the brief. `MERGED` is set only after the merge succeeds.

## One slice in time order

```mermaid
sequenceDiagram
    participant Y as You
    participant C as Coordinator
    participant W as Slice workflow
    participant V as Verifier
    participant CR as CodeReviewer
    participant I as Implementer
    participant R as Reviewers
    C->>C: Create slice branch and update state.json
    C->>W: Launch the slice workflow for one slice
    W->>V: TEST_PLAN mode
    V-->>W: TEST_PLAN.md written as DRAFT
    W->>CR: TEST_PLAN review
    CR-->>W: APPROVE and flip the status line
    par Code
        W->>I: IMPLEMENT
        I-->>W: Code committed
    and Tests
        W->>V: WRITE_TESTS
        V-->>W: Tests written
    end
    W->>V: VERIFY
    V-->>W: Suite result and routing facts
    W->>R: SLICE review of the raw diff
    R-->>W: Findings
    loop Fix rounds while findings are open, at most 3
        W->>I: FIX code findings
        W->>V: FIX_TESTS test findings
        W->>V: VERIFY again
        W->>R: RECHECK
    end
    W-->>C: READY_FOR_HUMAN with evidence
    C->>Y: Show REVIEW.HUMAN.md in chat
    Y->>C: Approve the merge
    C->>C: Merge into the feature branch, no fast-forward
```

<sub>Source: [07-slice-sequence.mmd](diagrams/07-slice-sequence.mmd) · rendered: [07-slice-sequence.svg](diagrams/07-slice-sequence.svg)</sub>

## Routing: which reviewers run

The verifier reports routing facts as true or false, each with evidence. The registry turns facts into
reviewers.

| Reviewer | Runs when |
|---|---|
| code-reviewer | Any production code changed |
| simplicity-reviewer | Production code changed, unless the slice is mechanical only (renames, version bumps, generated code, formatting, config values) |
| security-reviewer | Auth, tokens or secrets, isolation, untrusted input, crypto, a new network surface |
| contract-reviewer | Public API, wire format, DTOs, externally visible errors; or config that consumers set |
| integration-reviewer | Behaviour a consumer or operator can see; a public contract or config change |
| reliability-reviewer | Concurrency, retries, timeouts, cancellation, networking, streaming, resource lifetime |

If a fact is uncertain, the reviewer runs. Reviewers not routed are listed in `EVIDENCE.md` with the reason.

A reviewer that returns nothing or invalid output is retried once. If it fails again, the workflow returns
`BLOCKED_REVIEWER`. Shipyard never treats a missing review as a clean one.

## Fix scope, rebuttals and caps

- **Fix scope:** every `BLOCKING`, `MAJOR` and `MINOR` finding must be fixed or rebutted before you see the
  slice. `NOTE` is optional.
- **Owner:** each finding names who acts. The implementer owns code paths and code actions. The verifier owns
  test paths and tests to add, remove or reshape.
- **Rebuttal:** the owner may rebut a finding once, with a citation, instead of fixing it. The reviewer who
  raised it answers `ACCEPT_REBUTTAL` or `MAINTAIN_FINDING`. A maintained architectural `BLOCKING` finding goes
  to the architect to adjudicate. If that does not settle it, it goes to you.
- **Re-review:** after a fix round, verification runs again, routing is redone on the new diff, and reviewers
  re-run for their open findings plus any newly triggered reviewer.

| Loop | Cap | On hitting the cap |
|---|---|---|
| Test-plan revisions | 2 | `ESCALATE` to you |
| Fix rounds | 3 | `ESCALATE` with the open findings, options and a recommendation |
| Reviewer retries | 1 | `BLOCKED_REVIEWER` |

Changes you request at the merge brief do not count toward the 3-round cap. Each one re-runs verification and
review in full.

Repeated failure to converge usually means the slice or its spec is wrong. The escalation will say so.

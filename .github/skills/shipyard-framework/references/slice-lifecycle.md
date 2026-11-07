# Slice lifecycle

A project is not one large autonomous implementation. It is a sequence of independently mergeable **slices**. Each
slice lives on its own branch, `<feature>-slice-<id>`, tells one coherent engineering story, and lands on the feature
branch as one `--no-ff` merge commit.

## State machine

```text
PROPOSED            planner drafted it; not yet approved
    |
    v
APPROVED            set by the coordinator for every slice in the plan when the human approves it at P8
    |
    v
TEST_PLANNING       slice branch created; verifier writes TEST_PLAN.md (DRAFT); code-reviewer reviews it
    |               (<= 2 revisions; still not approved -> ESCALATE, slice stays here)
    v
IMPLEMENTING        TEST_PLAN.md says APPROVED; implementer writes code, verifier writes tests, in parallel
    |
    v
VERIFYING           verifier commits tests, runs the suite, scope check, planned tiers, routing facts
    |               (a PENDING "Pending human approval" entry in SLICE.md means: waiting on the human)
    v
AGENT_REVIEW        routed reviewers run concurrently; findings deduped; rebuttals answered
    |
    +--> CHANGES_REQUESTED --> IMPLEMENTING   (an in-scope finding is open; max 3 rounds, then ESCALATE)
    |
    v                   (every routed review ran; every BLOCKING/MAJOR/MINOR fixed or rebutted)
READY_FOR_HUMAN     workflow returned READY_FOR_HUMAN; EVIDENCE.md and REVIEW.HUMAN.md written
    |
    v
HUMAN_REVIEW        set when the brief is shown to the human in chat
    |
    +--> CHANGES_REQUESTED --> IMPLEMENTING   (human change request; re-verify, re-review; not counted)
    |
    v
MERGED              terminal; set only after `git merge --no-ff` succeeded and the canonical tests passed
```

`MERGED` is the only terminal state. Agent approval is never terminal, and neither is human approval: a merge that
conflicts or breaks the tests leaves the slice in `HUMAN_REVIEW`.

The current state of every slice lives in `DELIVERY_PLAN.md` (slice table) and in its `SLICE.md` (`State:`). The
coordinator updates both on every transition it observes — that is how a new session learns where the project
stands. `state.json` → `activeSlice` and `sliceBranch` name the slice in flight.

### Who sets which state

A dynamic workflow cannot write files, so the coordinator records states around each the `shipyard-slice` workflow launch:

| When | Coordinator sets |
|---|---|
| P8 approval | every slice in the plan `PROPOSED → APPROVED` |
| Before launch, `TEST_PLAN.md` absent or `DRAFT` | `TEST_PLANNING` |
| Before launch, `TEST_PLAN.md` already `APPROVED` (re-run after a human change request or a resume) | `IMPLEMENTING` |
| Result `READY_FOR_HUMAN` | `READY_FOR_HUMAN`, then `HUMAN_REVIEW` in the same turn the brief is shown |
| Result `ESCALATE` | `TEST_PLANNING` if the test plan never got approved, else `AGENT_REVIEW`; `Revision round` from `rounds` |
| Result `NEEDS_SHARED_APPROVAL` | `VERIFYING`, with a `PENDING` entry under `## Pending human approval` |
| Result `BLOCKED_REVIEWER` | `AGENT_REVIEW` |
| Result `BLOCKED` | unchanged; project `Status: BLOCKED` with the reason |
| Human change request at the brief | `CHANGES_REQUESTED`, then `IMPLEMENTING` when the fix starts |
| Merge and post-merge tests succeeded | `MERGED`; `state.json` `activeSlice`/`sliceBranch` back to `null` |

The intermediate passes (`IMPLEMENTING → VERIFYING → AGENT_REVIEW → CHANGES_REQUESTED`) happen inside one workflow
run; the result's `rounds` and `EVIDENCE.md` record them.

### Transition rules that are easy to get wrong

- **P8 approval moves the whole plan.** Every slice in it moves `PROPOSED → APPROVED`, in `DELIVERY_PLAN.md` and in
  each `SLICE.md`. A replan that returns to P8 puts changed or new slices back to `PROPOSED` until the human approves
  again. Merged slices stay `MERGED`.
- **No code before the test plan.** `TEST_PLANNING → IMPLEMENTING` happens only when the code-reviewer has flipped
  `TEST_PLAN.md` to `Status: APPROVED`. The test-plan-gate hook enforces it (`test-plan.md`).
- **`AGENT_REVIEW` has three exits.** Every routed review ran (or the human explicitly skipped one that failed), and
  every `BLOCKING`, `MAJOR` and `MINOR` finding is fixed or rebutted → `READY_FOR_HUMAN`. An in-scope finding still
  open → `CHANGES_REQUESTED → IMPLEMENTING`. A disputed finding stays in `AGENT_REVIEW` through rebuttal, architect
  adjudication or human escalation, then takes one of the other two exits.
- **`HUMAN_REVIEW` starts when the human sees the brief**, not when the file is written.
- **A `VERIFYING` slice with a `## Pending human approval` entry whose outcome is `PENDING` is waiting on the
  human,** not on an agent. On resume, re-ask the human for that tier rather than re-running verification.
- **Human change requests do not count toward the 3-round cap.** The cap measures agent convergence; a human asking
  for something different is new input. Each request still re-runs verification and review in full.

## Slice quality criteria

A slice is well-formed when it is:

- coherent — one conceptual change, not a bundle;
- independently understandable, buildable, testable and mergeable;
- backward compatible where practical, and reasonably reversible;
- small enough that a human can meaningfully review it;
- tied to explicit acceptance criteria that a test plan can cover;
- explicit about consumer impact, prerequisites and both touch sets;
- named with its branch in `## Branch`.

## Human cognitive load

"Small enough for a human to review" is the criterion most often asserted and least often examined. A slice is a
**change a person has to hold in their head at once**, and review quality drops sharply with size long before review
*time* does — a reviewer does not read a 3,000-line diff three times more carefully than a 1,000-line one; they skim
it.

Treat these as **signals to look again at the boundary**, not thresholds to compute against:

| Signal | What it usually means |
|---|---|
| More than ~20 files touched | The slice is probably carrying more than one conceptual change. |
| Well into four-figure line counts | Either genuinely too big, or dominated by generated/mechanical content that should be separated from the reviewed logic. |
| More than ~7 acceptance criteria, or a test plan that needs several levels for most ACs | Several behaviours share one title. |
| The reviewer needs the whole diff in view to judge any part of it | Genuinely cohesive — this one may legitimately stay whole. Say why. |
| Its summary needs "and" more than once | It is a bundle wearing one title. |

When a slice trips a signal, the first question is *can this split along a seam that leaves both halves independently
mergeable?* Usually yes. Sometimes not — a single transactional workflow whose ordering invariants must be reviewable
in one place is a real exception. **State the exception and its reason** rather than letting a large slice pass
silently; a reviewer who knows why a change is large reviews it differently from one who assumes nobody noticed.

Prefer splitting over apologising. A slice budget (C-1) is a preference; a reviewer's attention is a hard limit.

Mechanical bulk — generated code, large fixtures, bulk renames, formatting — is worth isolating into its own slice
even when it is trivially correct, so the reviewed logic is not buried beneath it.

## Vertical, not horizontal

Do not slice by layer:

```text
BAD:  slice 1 all interfaces -> slice 2 all DTOs -> slice 3 all implementations -> slice 4 tests
```

Slice by capability, so every slice is independently meaningful, testable against its own ACs, and revertible:

```text
GOOD: slice 1 domain representation + validation the next path needs
      slice 2 new behaviour behind existing external semantics
      slice 3 enable the new path for one controlled case
      slice 4 configurable rollout
      slice 5 migrate consumer A
      slice 6 migrate consumer B
      slice 7 remove the legacy path once evidence shows zero use
```

Tests always travel with the behaviour they prove, in the same slice. "Tests later" is horizontal slicing.

## Stale evidence is invalid evidence

If **anyone** — human or agent — changes the slice branch after verification ran, the prior evidence no longer
describes the commit under review:

```text
change lands on the slice branch
    -> verifier re-runs (VERIFY)
    -> routing recomputed against the new diff; affected reviewers re-run
    -> EVIDENCE.md and REVIEW.HUMAN.md regenerated (new evidence commit)
    -> human approval
```

Never merge a commit whose evidence only applies to an earlier revision. The merge procedure enforces it: the slice
branch tip must be the evidence commit (`branch-policy.md`); nobody commits after VERIFY, and `.ai/` is never
committed. This applies equally to a one-line human tweak made during review — exactly the case where the
rule is most often skipped and most often matters.

A change to an acceptance criterion also invalidates the test plan: the planner updates `SLICE.md`, the verifier
rewrites `TEST_PLAN.md` as `DRAFT`, and the code-reviewer must approve it again before any further code or test.

## Convergence cap

At most **3** `CHANGES_REQUESTED → IMPLEMENTING` rounds per slice (`registry.limits.fixRounds`), and at most **2**
test-plan revisions (`registry.limits.testPlanRevisions`). Beyond either, the workflow returns `ESCALATE` and the
coordinator brings the open findings to the human. Repeated failure to converge is a signal that the slice boundary
or the acceptance criteria are wrong — not that the implementer needs another attempt.

## Dependent slices

Never begin a slice that depends on an unmerged predecessor unless the human explicitly approves proceeding against
unmerged assumptions. The predecessor may change materially during human review. When approval is given, record it
under `## Speculative dependencies` in `DELIVERY_PLAN.md` so reconciliation knows the dependency was speculative. Merge
the predecessor first; after it merges, the dependent slice's evidence is stale and is re-run before its own merge.

# Merge reconciliation (P10)

The delivery plan is a living document, not a contract signed at the start. After every merge, the feature branch is
a new reality and the remaining slices were written against the old one.

**Run this after every merge, before starting the next slice. No exceptions.**

The most common way a multi-slice agent workflow fails is that slice 05 proceeds against what slice 04 was
*expected* to merge, rather than what actually merged — including the human's edits.

## Where the truth is

The feature branch is **local**. Shipyard never pushes, so there is nothing to fetch: the coordinator's own
`git merge --no-ff` (`branch-policy.md`) produced the state to reconcile against. The coordinator owns P10; it runs
read-only git commands and calls two agents directly (architect `REVALIDATE`, planner `RECONCILE`).

## Procedure

### 1. Pin the states

Right after the merge, with the feature branch checked out:

```bash
git rev-parse HEAD                      # M: the merge commit
git rev-parse HEAD^1                    # B: the feature branch before the merge
git rev-parse HEAD^2                    # S: the slice branch tip that merged
```

If `HEAD` is not a two-parent merge commit whose message is `Merge slice <id>: <title>`, stop: the merge did not
happen the way the evidence says. Report in one line and do not start the next slice.

### 2. Compare planned against actual

```text
planned post-slice state                 vs   actual feature-branch state
(SLICE.md: touch sets, ACs, contract           (git diff --stat B M; git diff B M -- <paths>;
 changes, next-slice dependency;                git log --format='%h %an %s' B..S)
 DELIVERY_PLAN.md ordering)
```

### 3. Identify what actually changed

- **human edits on the slice branch before approval** — every commit on `B..S` whose message does not follow the
  Shipyard forms (`slice <id> round <n>: code|tests`), and every change made in answer to a
  human change request at the merge brief. Agents commit under the human's git identity, so the author field does
  not tell them apart; the message does;
- new conventions established by the merged code;
- changed APIs or signatures;
- changed or renamed abstractions;
- assumptions in `planning/assumptions.md` that are now confirmed or invalidated;
- new tests that encode behaviour later slices must preserve;
- changed dependencies;
- touch-set drift accepted during the slice (`EVIDENCE.md` → scope check).

**Human edits are the highest-signal changes in the diff.** They tell you what the human actually wanted and the plan
did not capture. Quote them in the brief to both agents.

### 4. Architect revalidates

Call `shipyard-architect` with `Mode: REVALIDATE`. `Read:` the merged diff command (`git diff B M`), `ARCHITECTURE.md`,
`INVARIANTS.md`, the slice's `SLICE.md` and `EVIDENCE.md`, and the human-edit list. It decides whether the target
architecture still holds and whether any invariant was weakened or superseded, and returns exactly one verdict:

| Verdict | Meaning | Effect |
|---|---|---|
| `VALID` | Target architecture and invariants still hold. | None. |
| `UPDATE` | A clarification that changes no approved decision: wording, a new invariant the merge established, a component renamed. The architect edits `ARCHITECTURE.md` / `INVARIANTS.md` itself. | Tell the human in one line. |
| `ARCHITECTURE_DECISION` | The merge invalidated an architectural assumption. The architect drafts an ADR as `PROPOSED`. | Back to P8 with the change. |

### 5. Planner reconciles

Call `shipyard-planner` with `Mode: RECONCILE`. `Read:` the same inputs plus the architect's verdict and
`DELIVERY_PLAN.md` and every remaining `SLICE.md`. It re-checks every remaining slice against the merged reality —
touch sets, prerequisites, ACs, verification commands — and returns exactly one verdict:

| Verdict | Meaning | Action |
|---|---|---|
| `UNCHANGED` | Remaining slices are still correct. | Continue to the next slice (P9). |
| `MINOR_UPDATE` | Slice text needs edits; approved scope, boundaries, ordering, dependencies and gates are unchanged. Touch-set globs may be corrected for renamed paths. | The planner updates the files; the coordinator tells the human in one line of chat and continues. |
| `REPLAN` | Slice boundaries, ordering or dependencies must change. | The planner rewrites the affected slices (state `PROPOSED`); back to P8 (regenerate `PLAN.HUMAN.md`). No slice starts until the human approves. |
| `ARCHITECTURE_DECISION` | The planner cannot replan without an architecture change. | Back to P8 with the architecture change and the replanned slices. |

Only `UNCHANGED` and `MINOR_UPDATE` continue without the human. Anything that would alter approved scope,
boundaries, ordering, dependencies or gates is not a `MINOR_UPDATE`. An architect `ARCHITECTURE_DECISION` overrides
a planner `UNCHANGED`.

Each direct call ends with one fenced ```json block. Save it to `.ai/returns/` and validate it
(`shipyard_validate.py architect-result` / `planner-result`) before acting on it. An invalid or missing block is a
fail-closed stop: retry once, then `BLOCKED`.

### 6. Record

Append one row to the reconciliation log in `DELIVERY_PLAN.md`: slice, architect verdict, planner verdict, what
changed (with the evidence: commit range, human edits), action taken. Add a phase-log row to `PROJECT.md`. A future
session must be able to see why the plan changed without re-deriving it.

### 7. Speculative dependencies

If a slice was started before this one merged (recorded under `## Speculative dependencies`), the planner checks it
explicitly. Any assumption it made about this slice that the merge broke makes the verdict at least `MINOR_UPDATE`
for that slice, and its evidence is stale (`slice-lifecycle.md`).

## Do not skip on a "clean" merge

A merge that looks clean still moves the baseline. `UNCHANGED` is a legitimate and common verdict — but it must be a
verdict reached by inspecting the merged state, not an assumption made to save a step.

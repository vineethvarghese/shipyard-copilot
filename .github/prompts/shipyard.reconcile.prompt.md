---
name: shipyard.reconcile
description: Shipyard P10, IDE mode. After every merge, architect REVALIDATE and planner RECONCILE; a replan or architecture decision goes back to the P8 gate.
agent: shipyard-coordinator
---

# Shipyard P10: reconcile after a merge

You are `shipyard-coordinator` in IDE mode. Run this after **every** merge, before the next slice, even when the
merge looked clean. The brief header, `set-active-role` before each call, and `.ai/returns/` validation are as
in `/shipyard.discover`.

## 0. Precondition

```bash
python3 shipyard/scripts/check.py --phase P8
git log -1 --format=%P HEAD
```

The first confirms the P8 gate (slices may run); the second must print two parents, which makes `HEAD` the
slice's merge commit on the feature branch. `DELIVERY_PLAN.md` must show that slice `MERGED` with no
reconciliation row yet. Otherwise stop. Read `references/merge-reconciliation.md` in full.

## 1. Pin the commits

`B = HEAD^1`, `S = HEAD^2`, `M = HEAD`; confirm `HEAD` is the slice's merge commit. List human edits: commits on
`B..S` whose message is not `slice <id> round <n>: code|tests`, and changes made for human change requests. These
are the highest-signal lines.

## 2. Architect

`shipyard-architect`, `Mode: REVALIDATE`, `Compute: DEEP`, `Budget: 25 turns`. `Read:` `git diff B M`,
`.ai/ARCHITECTURE.md`, `.ai/INVARIANTS.md`, the slice's `SLICE.md` and `EVIDENCE.md`, the human-edit list.
`Write:` `.ai/slices/<id>/findings/architect.revalidate.md`. Contract `architect-result`. Verdict
`VALID | UPDATE | ARCHITECTURE_DECISION`; on `UPDATE` it edits the two files itself.

## 3. Planner

`shipyard-planner`, `Mode: RECONCILE`, `Compute: DEEP`, `Budget: 25 turns`. `Read:` the same plus
`DELIVERY_PLAN.md`, every remaining `SLICE.md` and the architect's verdict. `Write:` `.ai/planning/planner.md`
(and edited `SLICE.md` text on `MINOR_UPDATE`). Contract `planner-result`. Verdict
`UNCHANGED | MINOR_UPDATE | REPLAN | ARCHITECTURE_DECISION`. `UNCHANGED` is a conclusion from inspecting the merged
state, never an assumption.

## 4. Record and route

Record both verdicts in the reconciliation log of `DELIVERY_PLAN.md`; phase-log row;
`snapshot -m "P10 slice <id>: <verdicts>"`. Then:

| Verdicts | Next |
|---|---|
| planner `UNCHANGED`, architect `VALID` or `UPDATE` | Next slice: `/shipyard.slice <next id>`. |
| planner `MINOR_UPDATE` | Tell the person in one line of chat, then the next slice. |
| `REPLAN` or `ARCHITECTURE_DECISION` from either | Back to the P8 gate: `shipyard-planner`, `Mode: REPLAN` as needed, regenerate `PLAN.HUMAN.md`, changed or new slices back to `PROPOSED`, and wait for `APPROVE PLAN <feature>` again (`/shipyard.plan`, P8 section). No slice starts before that. |

Out-of-scope notes the authors recorded in `EVIDENCE.md` go to the planner in this call. Reconciliation changes
stay in `.ai/` in the working tree; the snapshot above has already put them on the notes branch.

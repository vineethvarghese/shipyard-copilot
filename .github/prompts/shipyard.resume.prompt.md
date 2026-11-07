---
name: shipyard.resume
description: Resume a Shipyard project from .ai/state.json and PROJECT.md, in any mode. Finds the interrupted step and names the prompt to run next.
agent: shipyard-coordinator
---

# Shipyard: resume

You are `shipyard-coordinator`. Never reconstruct state from conversation history. Re-read the files.

## 0. Precondition

```bash
python3 shipyard/scripts/check.py --env
python3 shipyard/scripts/shipyard_state.py show
```

If `.ai/` is absent (a fresh clone), fetch the notes branch if it was pushed
(`git fetch <remote> <notes>:<notes>`) and run `python3 shipyard/scripts/shipyard_state.py restore --from <notes>`;
the last snapshot is where the project resumes, and work after it is lost: say so. If only `state.json` is
missing, rebuild it with `init` from `PROJECT.md` → C-8 and the protected set, then `set-status` and `set-slice`
from `DELIVERY_PLAN.md`. If neither `.ai/` nor a notes branch exists, stop: the merge commits' evidence summaries
record what was merged, and a new `/shipyard.intake` starts from there.

Load `.github/skills/shipyard-framework/SKILL.md`; read `references/coordinator-workflow.md` → Resume.

## 1. Reconcile the two state files

Read `state.json` (`status`, `activeSlice`, `sliceBranch`, `activeRole`, `gates`) and `PROJECT.md` (`Status`,
`## Phase log`), then `DELIVERY_PLAN.md`. If they disagree, stop and reconcile them from the artifacts and
`git branch --show-current`, `git log --oneline -5`, `git status --porcelain` before anything else. If
`activeRole` is not `none`, a delegation was cut off: `set-active-role none`, and treat that step as not done.

## 2. Find the interrupted step and continue

| Last recorded state | Resume by |
|---|---|
| `INTAKE`, P0 answers incomplete or no P0 gate | `/shipyard.intake`: re-ask only the missing items, in one turn. |
| `DISCOVERY` with no P1–P3 rows | `/shipyard.discover` (CLI: re-launch the `shipyard-discover` workflow). |
| `PLANNING` with P4 open | `/shipyard.plan` Part A: the last `P4 round <n>` row says which round was asked; re-present that round's unanswered questions, or run `GRILL` for the next frontier. Never restart from round 1. |
| `PLANNING` after the P4 gate | `/shipyard.plan` Part B (CLI: re-launch `shipyard-plan` with the same `cycle`). |
| `AWAITING_PLAN_APPROVAL` | Re-present `PLAN.HUMAN.md` in chat and end on the **Approve the plan** handoff. |
| `IMPLEMENTING`, slice `TEST_PLANNING` … `AGENT_REVIEW` | Check out the slice branch; `/shipyard.slice <id>` from the step the artifacts show (`TEST_PLAN.md` `APPROVED` and code commits present → from VERIFY; otherwise from the test plan, round 0). |
| slice `VERIFYING` with a `PENDING` shared tier | Re-ask the person for that tier; do not re-run verification. |
| slice `HUMAN_REVIEW` | Check the evidence commit still matches the slice branch tip (else `/shipyard.slice` from VERIFY), then re-show `REVIEW.HUMAN.md` and end on the merge handoffs. |
| a merge commit for the slice on the feature branch, slice not `MERGED` | Re-run the post-merge tests, then `/shipyard.merge` step 4 and `/shipyard.reconcile`. |
| slice `MERGED`, no reconciliation row | `/shipyard.reconcile`. |
| `BLOCKED` | Report the recorded reason and ask what the person wants. Never clear `BLOCKED` without fixing its cause. |
| `COMPLETE` | Remind the person to push the feature branch and raise the pull request. |

Never run the size check on a resume. Lead the first message with the state block (project, phase, mode, slice,
round, blocked on, next action).

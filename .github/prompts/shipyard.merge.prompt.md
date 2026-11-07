---
name: shipyard.merge
description: Shipyard P9.9, IDE mode. Record the human's merge approval, check the slice branch, merge with --no-ff into the feature branch, re-run the tests, snapshot. Then run P10.
agent: shipyard-coordinator
argument-hint: "<slice id> APPROVE MERGE"
---

# Shipyard P9.9: merge one approved slice

You are `shipyard-coordinator` in IDE mode. This prompt runs only after the person wrote the literal
`APPROVE MERGE slice <id>` (the handoff pre-fills it). Anything else is not approval: answer questions from the
artifacts, record change requests, and go back to `/shipyard.slice`.

## 0. Gate and precondition

```bash
python3 shipyard/scripts/shipyard_state.py gate MERGE approve --by <login> --slice <id>
python3 shipyard/scripts/check.py --phase MERGE
```

The check confirms the merge gate for this slice is recorded, the slice is `HUMAN_REVIEW`, `EVIDENCE.md` and
`REVIEW.HUMAN.md` exist, and every routed reviewer's findings file is present. A non-zero exit: stop and report.
Read `references/branch-policy.md` → the merge procedure. Quote the approval in the phase log.

## 1. Checks

1. `git status --porcelain` is empty (`.ai/` is ignored).
2. The slice branch tip is the evidence commit named in `EVIDENCE.md` (`git rev-parse <slice-branch>`). If the
   person edited the slice branch themselves, the evidence is stale: re-run `/shipyard.slice` from VERIFY with
   `round 0` instead of merging.
3. `git switch <feature>`; clean tree; `git merge-base --is-ancestor <feature> <slice-branch>`.

## 2. Merge

```bash
git merge --no-ff <feature>-slice-<id> -m "Merge slice <id>: <title>" -m "<evidence summary>"
```

The evidence summary is one short paragraph from `EVIDENCE.md`: ACs verified, test command and result, reviewers,
rounds, accepted risks. On a conflict: `git merge --abort`, report in one line, the slice stays `HUMAN_REVIEW`.

## 3. Post-merge tests

Re-run the canonical test command exactly as recorded in `PROJECT.md`; record command, result and duration. On
failure: `set-status BLOCKED`, report, recommend a revert commit or a fix-forward slice; act only on the person's
word.

## 4. Record

Set the slice `MERGED` with the merge sha in `SLICE.md` and `DELIVERY_PLAN.md`;
`python3 shipyard/scripts/shipyard_state.py set-slice --clear`; phase-log row;
`snapshot -m "P9.9 slice <id>: merged <short sha>"`. Keep the slice branch. Never push.

## 5. Next

Run `/shipyard.reconcile` now, before anything else. When every slice is merged or deliberately dropped:
`set-status COMPLETE`, phase-log row, `snapshot -m "complete"`, and remind the person to push the feature branch
and raise the pull request to the base branch themselves (and the notes branch if they want a copy).

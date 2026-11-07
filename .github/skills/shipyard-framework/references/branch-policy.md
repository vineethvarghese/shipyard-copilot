# Branch policy

Shipyard works on one local **feature branch**. Every slice is built on its own **slice branch**, cut from the
feature branch, and lands back on it as one `--no-ff` merge that only the coordinator makes, only after the human
approved that slice. Shipyard never pushes. The human pushes the feature branch and raises the pull request to the
base branch themselves.

```text
main ─────●──────────────────────────────────────────  (base; protected; never touched)
           \
feature/x   ●────────────M1────────────M2────────  (local; only --no-ff merges land here)
             \          /  \          /
feature/x-slice-01  c──t    \        /
                            feature/x-slice-02  c──t──c
c = slice <id> round <n>: code      t = slice <id> round <n>: tests      M = Merge slice <id>: <title>
```

**`.ai/` never enters your work branches; it is committed to a notes branch instead.** `.ai/` is Shipyard's working
state: plans, slice specs, test plans, evidence, briefs, `state.json`. Git ignores it in the working tree through the
repository's local exclude file (`.git/info/exclude`), so the project's own files, `.gitignore` included, are not
changed, and `.ai/` stays put while the coordinator switches between the feature and slice branches. The feature
branch, the slice branches and your pull request contain only code and tests.

At every checkpoint the coordinator runs `shipyard_state.py snapshot -m "<phase>: <what changed>"`. It commits the
whole `.ai/` folder to the **notes branch** (`state.json` → `notesBranch`, default `<feature>-shipyard`) with git
plumbing: a private index, `write-tree`, `commit-tree` and a checked `update-ref`. It never checks anything out and
never touches the working tree, the index or the current branch. The notes branch holds only `.ai/`, one commit per
checkpoint, so the full history of the project's notes is in git. It is never checked out, merged or pushed by
Shipyard; push it yourself if you want an off-machine copy. On another machine, `shipyard_state.py restore --from
<notes branch>` writes `.ai/` back into a fresh clone and the project resumes.

```text
feature/x-shipyard  ●──●──●──●──●──●   (notes: .ai/ only; one commit per checkpoint; never checked out or merged)
```

## P0: choosing and validating the feature branch (C-8)

The human gives two names in the P0 batched turn: the **feature branch** and the **base branch**. Recommend defaults:
base = the repository's default branch; feature = `feature/<project-slug>`.

Validate, in this order. Any failure is a fail-closed stop with a one-line reason and a corrected suggestion.

1. **Repository.** `git rev-parse --is-inside-work-tree` prints `true`, and `git rev-parse --verify HEAD` succeeds
   (there is at least one commit).
2. **Default branch.** `git symbolic-ref --quiet --short refs/remotes/origin/HEAD` (strip the `origin/` prefix). With
   no remote, use `git config --get init.defaultBranch`. If neither answers, record the default as `UNRESOLVED` and
   treat the base branch as the default.
3. **Protected set.** `main`, `master`, the default branch, the base branch, and any branch the human names as
   protected. This list becomes `state.json` → `protectedBranches`.
4. **Name is valid.** `git check-ref-format --branch "<feature>"` exits 0.
5. **Name is not protected.** Refuse a feature branch equal to any name in the protected set, or equal to the base
   branch. Do not offer to "just use main"; that is the case this policy exists to prevent.
6. **Base exists.** `git rev-parse --verify "<base>^{commit}"` succeeds.
7. **Clean tree.** `git status --porcelain` is empty. Never stash, reset or discard the human's work to get a clean
   tree; ask them.
8. **Create or reuse.**
   - Branch missing: `git switch -c "<feature>" "<base>"`. If git refuses because a ref like `<feature>/…` already
     exists (see below), report it and suggest another name.
   - Branch exists: confirm with the human that it is the intended branch, check
     `git merge-base --is-ancestor "<base>" "<feature>"` (it must descend from the base), then `git switch "<feature>"`.
9. **Ignore `.ai/` in the work tree, then record.** `python3 shipyard/scripts/shipyard_state.py init …`
   (it also records the notes branch, `<feature>-shipyard` unless the human names another) first runs `ignore-ai`: it adds `/.ai/` to `.git/info/exclude` (idempotently), then checks that git ignores `.ai/` and
   tracks nothing in it. Only then does it write `state.json`. If files under `.ai/` are already tracked (an earlier
   project committed them), it refuses: ask the human whether to run `git rm -r --cached .ai` themselves; never do
   it for them. C-8 goes in `PROJECT.md` → `## Delivery parameters`; the protected set, the notes branch and "`.ai/`
   ignored via `.git/info/exclude`" go under `## Framework configuration`. Then take the first snapshot.

Never write `.ai/` into the project's `.gitignore`: that file is the human's work, and changing it would put a
Shipyard line into their pull request. The local exclude does the same job without touching the project.

## Slice branch naming

The slice branch is `<feature>-slice-<id>`, using the slice ID from `DELIVERY_PLAN.md`: `feature/x-slice-03`. It is
written in the slice's `SLICE.md` under `## Branch` and in `state.json` → `sliceBranch`.

**Why not `<feature>/slice-<id>`.** Git stores a branch as a path under `refs/heads/`. `feature/x` is a ref *file*,
so `feature/x/slice-03` would need `feature/x` to be a *directory* at the same time. Git refuses with an error like
`cannot lock ref 'refs/heads/feature/x/slice-03': 'refs/heads/feature/x' exists`. The same conflict blocks creating
`feature/x` when any `feature/x/...` branch already exists. The `-slice-` suffix keeps both names valid.

## Cutting a slice branch (P9, coordinator)

1. The slice is `APPROVED`; every prerequisite is `MERGED` (or a speculative start is recorded).
2. The feature branch is checked out and `git status --porcelain` is empty. `.ai/` is ignored, so it stays in the
   working tree across the switch.
3. `git check-ref-format --branch "<feature>-slice-<id>"`, then `git switch -c "<feature>-slice-<id>" "<feature>"`.
   If the branch already exists (a resume or a re-run), switch to it instead and check
   `git merge-base --is-ancestor "<feature>" "<slice-branch>"`.
4. `shipyard_state.py set-slice …` sets `activeSlice` and `sliceBranch`. Only then launch the `shipyard-slice` workflow.

## Who may commit what, and when

| Who | Branch | Paths | Message | When |
|---|---|---|---|---|
| implementer | slice branch | code touch set only | `slice <id> round <n>: code` | at the end of `IMPLEMENT` and of each `FIX` |
| verifier | slice branch | test touch set only | `slice <id> round <n>: tests` | at the **start** of `VERIFY`, before running anything. Never during `WRITE_TESTS` or `FIX_TESTS`. |
| coordinator | feature branch | the merge (no other commit, ever) | `Merge slice <id>: <title>` plus a one-paragraph evidence summary | P9.9, after explicit human approval |
| coordinator | notes branch | `.ai/` only, through `shipyard_state.py snapshot` (never `git commit`) | `<phase>: <what changed>` | at every checkpoint: each phase transition, each slice result, each merge, each reconciliation, completion |
| everyone else | — | nothing | — | Discovery, goldfish, architect, planner and reviewers never change git state. |

Nobody `git add`s or `git commit`s `.ai/` onto a work branch. The protect-branches hook refuses a coordinator
`git commit`, any `git add` of a `.ai` path, any forced add (`git add -f`), and any checkout, reset, move, delete,
merge or worktree of the notes branch.

`<n>` is the `Round:` value from the brief: `0` for the first pass, `1`–`3` for fix rounds. A relaunch of
the `shipyard-slice` workflow after a human change request starts again at round 0 (human requests do not count toward the cap),
so round numbers can repeat on one slice branch; `EVIDENCE.md` records how many launches the slice took.

Rules for every committer:

- **Stage by explicit path.** `git add -- <paths in your touch set>`. Never `git add -A`, `git add .` or
  `git commit -a`: the working tree also holds other roles' uncommitted files.
- **New commits only.** No `--amend`, no rebase, no reset, no force, no history rewriting, no tags, no stash.
- **One commit per step.** If there is nothing to commit, say so and return `commit: null`.
- **Never push.** No `git push` in any form, to any remote.
- **The slice branch only.** Authors check `git branch --show-current` equals the `Slice-branch:` line in the brief
  before committing. A mismatch is a fail-closed stop.

The verifier's `VERIFY` result returns the slice branch `HEAD` after its tests commit as `commit`. That is the
**evidence commit**: the exact code and tests that were verified and reviewed. `.ai/` never appears in the diff.

## The merge procedure (P9.9, coordinator only)

Run every step; any failure stops the procedure with a one-line report, and the slice stays `HUMAN_REVIEW`.

1. **Approval.** The human approved *this* slice's brief explicitly in chat. Quote their words in the phase log.
   Silence, "looks good overall" or approval of a different slice is not approval.
2. **Slice branch is settled.** On the slice branch, `git status --porcelain` is empty (`.ai/` is ignored and never
   shows).
3. **Evidence matches HEAD.** `git rev-parse "<slice-branch>"` equals `Evidence commit:` in `EVIDENCE.md`. Nobody
   commits after VERIFY, so any difference means code or tests changed after verification: the evidence is stale. Stop and re-run the slice
   workflow (`slice-lifecycle.md` → stale evidence).
4. **Switch.** `git switch "<feature>"`; `git status --porcelain` must be empty.
5. **Feature branch has not moved.** `git merge-base --is-ancestor "<feature>" "<slice-branch>"` must succeed. If
   the feature branch gained commits after the slice was cut, stop and ask the human; never rebase to fix it.
6. **Merge.** `git merge --no-ff "<slice-branch>" -m "Merge slice <id>: <title>" -m "<evidence summary>"`. The
   second `-m` is one short paragraph from `EVIDENCE.md` (acceptance criteria verified, test command and result,
   reviewers that ran, fix rounds, accepted risks), so the feature branch's own history explains each merge.
7. **Conflict.** If the merge exits non-zero: `git merge --abort`, confirm `git status --porcelain` is empty, report
   in one line (`Merge of slice <id> conflicted in <paths>; aborted, nothing changed.`), and stop.
8. **Post-merge tests.** Run the canonical test command (`SLICE.md` → `## How this is verified`; else the one in
   `discovery.md`). Record command, result and duration in `DELIVERY_PLAN.md` and the phase log. On failure, do not
   undo anything yourself: set `BLOCKED`, report, and recommend `git revert -m 1 HEAD` (a new commit, which you run
   only on the human's explicit yes) or a fix-forward slice.
9. **Record.** Set the slice `MERGED` in `DELIVERY_PLAN.md` (with the merge commit sha) and `SLICE.md`; run
   `shipyard_state.py set-slice` to clear `activeSlice` and `sliceBranch`; add a phase-log row. **Keep the slice
   branch.** Never delete it.
10. **Reconcile.** Run P10 (`merge-reconciliation.md`) before anything else.

## Completion

When every slice is `MERGED` or deliberately dropped, set `COMPLETE` and tell the human, in this form:

```text
All slices are merged into <feature> (local). Nothing has been pushed.
Shipyard's notes are on the local branch <notes branch> (.ai/ only). Push it too if you want a copy:
  git push -u <remote> <notes branch>
To publish:  git push -u <remote> <feature>
Then raise a pull request from <feature> to <base> in your usual tool.
```

## What protect-branches blocks

The protect-branches hook (`preToolUse` on the shell tool) applies to every Shipyard agent, including the coordinator,
and to nothing else: it does nothing unless a Shipyard role is known, from `SHIPYARD_ROLE` (the CLI agent-scoped
hooks) or from `.ai/state.json` → `activeRole` (the repository hooks), so the human's own sessions are never
affected. The `main` ruleset on the remote is the stronger guarantee: never grant Copilot a bypass on it. For Shipyard agents it denies:

- `git push` in any form;
- `git commit`, `git merge`, `git rebase`, `git reset` and `git cherry-pick` while the current branch is in
  `state.json` → `protectedBranches` (or is `main` / `master`);
- any `git commit` by the coordinator (it only merges), any `git add` of a `.ai` path, and any forced add.

Hooks see commands, not intent. A command hidden inside a script can slip past a hook, so the rules above bind every
agent whether or not a hook catches the breach. The write-scope hook separately limits which paths each agent may
edit, and the readonly-bash hook stops planning and review roles from changing git state at all.

---
applyTo: "**"
---

# Working on a Shipyard slice branch

These rules apply whenever `.ai/state.json` exists and names an `activeSlice`. They are the same rules the
Shipyard hooks enforce in Copilot CLI and the `shipyard-slice-check` workflow enforces on the pull request.

1. **Touch sets are the boundary.** The active slice's `.ai/slices/<id>/SLICE.md` lists
   `## Expected touch set — code` and `## Expected touch set — tests`. The implementer writes only paths matching
   the code set; the verifier only paths matching the test set. Test files, fixtures and test helpers belong to
   the test set. A path outside both sets is scope drift: report it, do not write it.
2. **Test plan first.** Write no production code and no test code until `.ai/slices/<id>/TEST_PLAN.md` carries
   `Status: APPROVED` within its first ten lines. The verifier writes the plan as `Status: DRAFT`; the
   code-reviewer flips the line on an `APPROVE` verdict; nobody else touches it. After approval the plan is
   frozen: changing it means rewriting it as `DRAFT` and getting it approved again.
3. **Commit only on the slice branch**, named `<feature>-slice-<id>` and recorded in `state.json` →
   `sliceBranch`. Check with `git rev-parse --abbrev-ref HEAD` before the first write. Stage paths by name
   (`git add -- <path>`), never `git add -A` or `git add .`. Messages are exactly `slice <id> round <n>: code`
   (implementer, at the end of IMPLEMENT and each FIX) or `slice <id> round <n>: tests` (verifier, at the start
   of VERIFY). No amend, rebase, reset, cherry-pick, branch creation or branch switch.
4. **Never push.** The coordinator merges the slice branch into the feature branch with `git merge --no-ff` after
   a person approves the brief (in cloud mode, the person merges the slice pull request). The feature branch
   reaches the remote only when the person pushes it.
5. **Shell writes count.** A redirect, `tee`, `sed -i`, `cp`, `mv`, `rm` or `touch` into the repository is held
   to the same touch set and the same test-plan gate as an editor write. Send scratch output to the system temp
   folder.
6. **Do not read the other author's work in progress.** The implementer derives code from `SLICE.md` and
   `TEST_PLAN.md`, not from the tests being written in parallel; the verifier derives tests from the same two
   files, not from the code. In FIX and FIX_TESTS rounds, reading committed work from the other side is allowed;
   editing it never is.
7. **Report honestly.** `build: "FAIL"` or `"NOT_RUN"` when it did not run; every stub in `stubsRemaining`;
   every out-of-scope need in `outOfScopeNoticed`; an architecture conflict in `architectureConcerns`. Never
   describe unbuilt code as working.

---
name: shipyard.slice
description: Shipyard P9 for one approved slice, IDE mode. Test plan first, code and tests, verify, routed review, capped fix rounds. Ends with REVIEW.HUMAN.md and the merge gate.
agent: shipyard-coordinator
argument-hint: "<slice id, e.g. 02>"
---

# Shipyard P9: one slice

You are `shipyard-coordinator` in IDE mode, standing in for the `shipyard-slice` dynamic workflow. The brief
header, `set-active-role` before each call, and `.ai/returns/` validation are as in `/shipyard.discover`. Slice
briefs also carry `Slice:`, `Round:`, `Feature-branch:` and `Slice-branch:`; reviewer briefs carry
`Diff: git diff <feature>...<slice-branch>`.

## 0. Precondition

```bash
python3 shipyard/scripts/check.py --phase SLICE
```

It confirms the P8 gate is approved, the slice is `APPROVED`, and its prerequisites are `MERGED` (or a recorded
human exception). Read `references/coordinator-workflow.md` → P9, `references/test-plan.md`,
`references/review-routing.md`, `references/branch-policy.md` → cutting a slice branch.

## 1. Branch and state

Clean tree; `git check-ref-format --branch <feature>-slice-<id>`; `git switch -c <feature>-slice-<id> <feature>`
(or switch to it on a re-run). Then:

```bash
python3 shipyard/scripts/shipyard_state.py set-slice <id> <feature>-slice-<id>
```

Set the slice `TEST_PLANNING` in `SLICE.md` and `DELIVERY_PLAN.md`. Round `n` starts at 0.

## 2. Test plan (at most 2 revisions)

1. `shipyard-verifier`, `Mode: TEST_PLAN`, `Compute: DEEP`, `Budget: 25 turns`. `Read:` `SLICE.md`,
   `INVARIANTS.md`, `GLOSSARY.md`, `planning/discovery.md` → validation tiers. `Write:`
   `.ai/slices/<id>/TEST_PLAN.md` as `Status: DRAFT`. Contract `test-plan-result`.
2. `shipyard-code-reviewer`, `Mode: TEST_PLAN`, `Compute: DEEP`, `Budget: 20 turns`. `Read:` `SLICE.md`,
   `TEST_PLAN.md`, `INVARIANTS.md`, the tiers. `Write:` `findings/code-reviewer.test-plan.md`. Contract
   `reviewer-result`. On `APPROVE` it flips the status line and reports `extras.testPlanStatus`; confirm the file
   says `Status: APPROVED` yourself before step 3. On `REVISE`, step 1 again with the findings in `Read:`; after 2
   revisions still `REVISE` → `ESCALATE`: the slice stays `TEST_PLANNING`; bring the open findings to the person.

Slice `IMPLEMENTING`.

## 3. Build (both from `SLICE.md` + `TEST_PLAN.md`, never from each other)

3. `shipyard-implementer`, `Mode: IMPLEMENT`, `Round: 0`, `Compute: STANDARD`, `Budget: 60 turns`. Code touch set
   only; commits `slice <id> round 0: code`. Contract `author-result`.
4. `shipyard-verifier`, `Mode: WRITE_TESTS`, `Round: 0`, `Compute: STANDARD`, `Budget: 60 turns`. Test touch set
   only; no git. Contract `author-result`.

Run them in parallel when the client allows. (Write scope is unenforced in this mode: the `shipyard-slice-check`
pull-request check is the backstop.) `architectureConcerns` or `testDisputes` in either return → `shipyard-architect`,
`Mode: ADJUDICATE`, and the ruling goes back to the right author in the same round.

## 4. Verify

5. `shipyard-verifier`, `Mode: VERIFY`, `Round: n`, `Compute: STANDARD`, `Budget: 40 turns`. It reports
   `testPlanStatus` (stop unless `APPROVED`), commits `slice <id> round n: tests`, runs the scope check, the
   canonical suite, the planned tiers, and `routingFacts`. Contract `verify-result`.
   - `scopeCheck: DRIFT` → `shipyard-architect`, `Mode: CONFORMANCE`; `INCONSISTENT` is a `BLOCKING` finding.
   - A `SHARED` tier `AWAITING_APPROVAL` → slice `VERIFYING`, record it under `## Pending human approval`, ask the
     person live, continue only on an explicit yes (or record `NOT_RUN` on a no).
   - `build: FAIL` → fail closed.

## 5. Routed review (parallel when possible; code review always)

Compute the routing set from `routingFacts` and `registry.routing.slice`: `shipyard-code-reviewer` always;
`shipyard-simplicity-reviewer` when `productionCode` and not `mechanicalOnly`; `shipyard-security-reviewer` when
`security`; `shipyard-contract-reviewer` when `publicContract` or `config`; `shipyard-integration-reviewer` when
`consumerVisible`, `publicContract` or `config`; `shipyard-reliability-reviewer` when `concurrency`. Uncertain →
route. Each: `Mode: SLICE` (round 0) or `Mode: RECHECK` (later rounds), `Compute: DEEP`, `Budget: 30 turns`,
`Read:` raw `SLICE.md`, raw `TEST_PLAN.md`, the `Diff:` command; `Write:`
`.ai/slices/<id>/findings/<agent-name>.md`; contract `reviewer-result`. A missing or unparseable findings file is
an invalid return: re-brief once, then `BLOCKED_REVIEWER`. A finding with category `security` routes the security
reviewer if it had not run. Record reviewers not routed, with the reason, for `EVIDENCE.md`.

Dedupe: same location and category across reviewers → one finding, highest severity, every reporter kept.

## 6. Fix rounds (at most 3)

While any `OPEN` finding is `MINOR` or above and `n < 3`: `n += 1`;
`shipyard-implementer`, `Mode: FIX`, `Round: n` (code findings) and `shipyard-verifier`, `Mode: FIX_TESTS`,
`Round: n` (test findings), each with its findings pasted in the brief. A rebuttal goes to the filing reviewer,
`Mode: REBUTTAL` (contract `rebuttal-response`), once per finding. A maintained architectural `BLOCKING` goes to
`shipyard-architect`, `Mode: ADJUDICATE`. Then step 4 again, then step 5 in `RECHECK` mode for every reviewer with
open findings plus the code reviewer over everything changed since its last review. After round 3 with findings
still open → `ESCALATE` with the open findings, options and a recommendation.

## 7. Evidence and the gate

Slice `READY_FOR_HUMAN`. Write `.ai/slices/<id>/FINDINGS.json` (the deduplicated findings), `EVIDENCE.md`
(template in `references/artifact-templates.md`: evidence commit, test plan line, review table with reviewers not
routed and why, verification, formal line at C-10 above `none`, capability skill versions, rounds) and
`REVIEW.HUMAN.md` (at most 40 lines: recommendation first, at most three things to check, what changes, risks
including unverified ACs, `NOT_RUN` tiers and skipped reviewers, one line of evidence). Slice `HUMAN_REVIEW`.
`snapshot -m "P9 slice <id>: ready for review"`.

Show the brief in chat plus one line: `git diff <feature>...<feature>-slice-<id>` to see the code. End on the
handoffs **Approve the slice merge** / **Request slice changes**. Then wait: `/shipyard.merge` records the yes.
A change request is recorded verbatim under `## Human change requests` (H1, H2, …) and re-runs from step 6 as a
change run outside the round cap (or from step 2 when it changes an acceptance criterion, after
`shipyard-planner`, `Mode: REPLAN`).

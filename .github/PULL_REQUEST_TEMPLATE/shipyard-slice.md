<!-- Shipyard slice pull request: from <feature>-slice-NN (or copilot/<branch>) into the feature branch.
     Fill it from .ai/slices/NN/EVIDENCE.md and REVIEW.HUMAN.md. Keep it to one screen; the merge commit keeps it. -->

## Slice NN: <title>

**Recommendation:** <merge | merge with the risks below | do not merge yet>

**Feature branch:** `feature/<slug>` · **Evidence commit:** `<sha>` · **Rounds:** <n> of 3

### Acceptance criteria

| AC | Verified by | Result |
|---|---|---|
| AC-1 | `<test name>` | pass |
| AC-2 | not verifiable here: <why, what was checked instead> | — |

### Verification

- Test plan: `Status: APPROVED` on <date>, <n> revisions.
- Canonical command: `<command>` → <result>, <duration>.
- Tiers: <tier> (LOCAL) pass · <tier> (SHARED) NOT_RUN / APPROVED by <login>.
- Scope check: <CLEAN | DRIFT: paths> · Formal (C-10): <tier; invariants checked; NOT_RUN with reasons | n/a>.

### Reviewers

| Reviewer | Routed because | Verdict | Open |
|---|---|---|---|
| code-reviewer | always | PASS | 0 |
| simplicity-reviewer | productionCode | PASS | 0 |
| <reviewer> | <trigger> | <verdict> | <n> |
| <reviewer> | not routed: <reason> | — | — |

### Open findings and accepted risks

- <id> <severity>: <one line> — <ACCEPTED_BY_HUMAN | fix-forward slice NN | open>
- Unverified ACs, `NOT_RUN` tiers, skipped reviewers: <list or none>

### Things to check (at most three)

1. `<path or decision>`: <the question to ask about it>
2. …

### Human change requests

<!-- Review comments on this pull request are recorded verbatim as H1, H2, ... in .ai/slices/NN/SLICE.md.
     They cannot be rebutted and do not count toward the 3-round cap; verification and review re-run in full. -->

- [ ] Checks: `shipyard-slice-check`, `shipyard-notes-guard`, `shipyard-plan-gate` are green.
- [ ] This pull request contains code and tests only; `.ai/` is on the notes branch `<feature>-shipyard`.
- [ ] Merge with a **merge commit** (the feature-branch ruleset allows nothing else) so this summary is kept.

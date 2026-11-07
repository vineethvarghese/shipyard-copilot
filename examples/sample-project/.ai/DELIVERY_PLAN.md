> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: PLAN.HUMAN.md.
# Delivery plan: link-expiry

Feature branch: `feature/link-expiry` (from `main`). Slice branches: `feature/link-expiry-slice-<id>`.

## Rollout strategy
Two vertical slices, in order. Slice 01 records an expiry without changing resolve behaviour, so it is safe to
merge alone. Slice 02 enforces it. Nothing is deployed by this project; the human raises one PR to `main` at the end.

## Slices
| ID | Title | State | Depends on | Reviewers routed | Branch |
|----|-------|-------|------------|------------------|--------|
| 01 | Store an optional expiry on links | MERGED | — | code, simplicity, contract, integration | `feature/link-expiry-slice-01` |
| 02 | Expired links stop resolving | TEST_PLANNING | 01 | (decided after VERIFY) | `feature/link-expiry-slice-02` |

## Human gates
- P8 plan approval: approved 2026-10-13.
- Merge of each slice into `feature/link-expiry`: slice 01 approved 2026-10-14.

## Compatibility stages
1. Slice 01: additive. `Link.expires_at` defaults to `None`; `create()` gains an optional keyword.
2. Slice 02: behaviour change for links that have an expiry only. Links without a TTL behave as before.

## Consumer migration order
None. No consumers outside this repository. `DERIVED`

## Deprecation and removal sequence
None.

## Rollout observability
Not applicable (library, no deployment in scope).

## Rollback strategy
Revert the slice's merge commit on the feature branch (`git revert -m 1 <merge>`). Slice 01 can stay if slice 02
is reverted.

## Completion criteria
Both slices MERGED; full suite passes on `feature/link-expiry`; human reminded to push and raise the PR.

## Reconciliation log
| After slice | Verdict | What changed | Action taken |
|-------------|---------|--------------|--------------|
| 01 | Architect VALID · Planner UNCHANGED | `Link` gained `expires_at=None` as planned; `MAX_TTL_SECONDS` constant added in `service.py` (planned in AC-3) | None |

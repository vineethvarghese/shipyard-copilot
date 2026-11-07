> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: REVIEW.HUMAN.md.

# Evidence: Slice 01

Slice branch: `feature/link-expiry-slice-01` · evidence commit: `7c41e9d` · diff: `git diff feature/link-expiry...feature/link-expiry-slice-01`

## Purpose and why now
Record an optional expiry so slice 02 can enforce it. Additive and safe to merge alone.

## Behavior changes
`create()` accepts `ttl_seconds`; invalid values raise `InvalidTTL`. No change for calls without it.

## Public contract changes
`create(url, ttl_seconds=None)`; `Link.expires_at: Optional[float] = None` (last field, defaulted);
`InvalidTTL(ValueError)` exported.

## Architecture changes
NONE

## New abstractions
NONE (simplicity-reviewer: "no new layer; a constant and a field").

## Consumers affected
NONE

## Compatibility impact
Backward compatible: positional `Link(...)` and keyword-free `create()` unchanged (AC-4 tests).

## Rollout impact
NONE

## Agent review
| Reviewer | Routed because | BLOCKING | MAJOR | MINOR | Findings file |
|----------|----------------|----------|-------|-------|---------------|
| code-reviewer | productionCode | 0 | 0 | 1 → fixed | findings/code-reviewer.md (local) |
| simplicity-reviewer | productionCode, not mechanicalOnly | 0 | 0 | 0 | findings/simplicity-reviewer.md (local) |
| contract-reviewer | publicContract | 0 | 1 → fixed | 0 | findings/contract-reviewer.md (local) |
| integration-reviewer | publicContract | 0 | 0 | 0 | findings/integration-reviewer.md (local) |

Reviewers not routed: security-reviewer (no `security` trigger: no auth, secrets or untrusted parsing beyond the
existing URL check); reliability-reviewer (no `concurrency` trigger).

## Verification
Scope check:        IN_SCOPE   (`src/shortener/{models,service,__init__}.py`, `tests/test_expiry_create.py`; `.ai/` excluded)
Build:              PASS
Static analysis:    NOT_APPLICABLE   (no linter configured in the repo)
Unit tests:         PASS   (run: 11, failures: 0)   `python -m pytest -q`, 0.4 s
Integration tests:  NOT_APPLICABLE
Validation tiers:   unit LOCAL — PASS
New tests added:    tests/test_expiry_create.py (7 tests)
Acceptance criteria verified:      AC-1, AC-2, AC-3, AC-4 (4/4)
Acceptance criteria NOT verified:  NONE
Failure scenarios exercised:       ttl 0, -1, max+1, 1.5, "60", True; clock at 0.0
Confidence: HIGH   Reason: every AC has a test that fails when the AC is broken; boundaries covered.

## Blocking findings encountered and how they were resolved
None BLOCKING. Fixed in round 1:
- contract-001 (MAJOR, owner implementer): `expires_at` was added as a required field before `created_at`,
  breaking positional construction. Fixed: moved last with default `None`. Test: AC-4 positional test.
- code-001 (MINOR, owner implementer): `ttl_seconds=True` was accepted as 1 second. Fixed: explicit `bool`
  check. Test: `test_ac3_rejects_non_integer_ttl`.

## Known risks
NONE

## Revision rounds used: 1 of 3

## Expected next slice
02 — Expired links stop resolving.

## Diff summary
3 code files, +24 −3; 1 test file, +62. Commits: `slice 01 round 0: code`, `slice 01 round 0: tests`,
`slice 01 round 1: code`. (`.ai/` is on the notes branch, not the slice branch.)

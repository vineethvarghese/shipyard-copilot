> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: REVIEW.HUMAN.md (written when ready).
# Slice 02: Expired links stop resolving
State: TEST_PLANNING
Revision round: 0 of 3

## Objective
`Shortener.resolve(code)` raises a new `LinkExpired` error when the injected clock is at or past the link's
`expires_at`. Unknown codes still raise `UnknownCode`.

## Motivation
Delivers the request's "stop working" behaviour on top of slice 01's recorded expiry. Keeping expired links in
the store (G2) lets callers tell "expired" from "unknown" (value lens).

## Prerequisites
Slice 01 (MERGED).

## Scope
- New `LinkExpired(LookupError)` carrying the code and `expires_at`, exported from the package.
- `resolve()` compares `clock() >= expires_at` for links that have an expiry.

## Non-goals
- Deleting expired links (G2).
- Extending or changing an expiry.

## Affected components
`shortener.service`, `shortener.errors` (new), `shortener/__init__.py` (export).

## Expected touch set — code
- src/shortener/service.py
- src/shortener/errors.py
- src/shortener/__init__.py

## Expected touch set — tests
- tests/test_expiry_resolve.py

## Branch
`feature/link-expiry-slice-02`

## Affected consumers
None outside this repo. `DERIVED`

## Contract changes
Behavioural: `resolve()` may now raise `LinkExpired` for links created with a TTL. New exported exception.

## Architecture constraints
- INV-001 (tier: none): links created without a TTL behave exactly as before.
- INV-002 (tier: none): all times come from the injected clock.

## Seams under test
- `Shortener.resolve(code)` and `Shortener.create(url, ttl_seconds)` (the package's public API; one seam)

## Prior art
- `tests/test_expiry_create.py :: CreateWithExpiryTest` (slice 01: same fake clock, same `Shortener(clock=...)` setup)

## Acceptance criteria
- [ ] AC-1: `resolve(code)` returns the URL while `clock() < expires_at`.
- [ ] AC-2: `resolve(code)` raises `LinkExpired` when `clock() >= expires_at` (the boundary instant counts as expired).
- [ ] AC-3: `LinkExpired` is distinct from `UnknownCode` (not a subclass of it) and exposes `code` and `expires_at`.
- [ ] AC-4: links without an expiry resolve at any clock value, including far in the future.
- [ ] AC-5: an expired link stays in the store (`len(store)` unchanged after resolving it).

## Test expectations
Unit tests with a controllable clock; boundary at exactly `expires_at`; far-future clock for AC-4.

## Validation tiers
| Tier | Environment | ACs | Why above the cheapest |
|------|-------------|-----|------------------------|
| unit | LOCAL | AC-1..AC-5 | Cheapest tier; fully covers the change |

## How this is verified
`python -m pytest -q` (whole suite, < 2 s).

## Pending human approval
NONE

## Review routing
Decided by the slice workflow from VERIFY `routingFacts`. Expected: code-review, simplicity-review,
contract-review and integration-review (`publicContract`: new exception from a public method).

## Rollout impact
None (library).

## Rollback
Revert the merge commit on `feature/link-expiry`; slice 01 can stay.

## Known risks
Callers that catch only `UnknownCode` will see a new exception type for expired links. Intended (AC-3); called
out in the merge brief.

## Acceptance criteria NOT verifiable here
None.

## Next-slice dependency
None. Last slice.

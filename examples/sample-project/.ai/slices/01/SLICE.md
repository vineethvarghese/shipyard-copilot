> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: REVIEW.HUMAN.md.
# Slice 01: Store an optional expiry on links
State: MERGED
Revision round: 1 of 3

## Objective
`Shortener.create()` accepts an optional `ttl_seconds` and records an absolute `expires_at` (UTC epoch seconds)
on the `Link`. `resolve()` behaviour does not change in this slice.

## Motivation
Enforcement (slice 02) needs the expiry recorded first. Splitting keeps each slice small (C-1) and makes slice 01
safe to merge alone: it is purely additive.

## Prerequisites
None.

## Scope
- `Link.expires_at: Optional[float] = None`.
- `create(url, ttl_seconds=None)`: validate, compute `expires_at = clock() + ttl_seconds`.
- New `InvalidTTL` error, exported from the package.

## Non-goals
- Enforcing expiry in `resolve()` (slice 02).
- Any clean-up of stored links (G2).

## Affected components
`shortener.models`, `shortener.service`, `shortener/__init__.py` (export).

## Expected touch set — code
- src/shortener/models.py
- src/shortener/service.py
- src/shortener/__init__.py

## Expected touch set — tests
- tests/test_expiry_create.py

## Branch
`feature/link-expiry-slice-01`

## Affected consumers
None outside this repo. `DERIVED`

## Contract changes
Additive: optional keyword `ttl_seconds` on `create()`; optional field `expires_at` on `Link` (last, defaulted);
new exception `InvalidTTL(ValueError)`.

## Architecture constraints
- INV-001: links created without a TTL behave exactly as before.
- INV-002: all times come from the injected clock, never from `time.time()` directly inside methods.

## Acceptance criteria
- [x] AC-1: `create(url, ttl_seconds=n)` returns a `Link` with `expires_at == clock() + n`.
- [x] AC-2: `create(url)` returns a `Link` with `expires_at is None`.
- [x] AC-3: `ttl_seconds` must be an integer in `1..MAX_TTL_SECONDS` (one year); anything else raises `InvalidTTL`.
- [x] AC-4: existing callers are unaffected: positional `Link(code, url, created_at)` still works and `resolve()`
  returns the URL for links with or without an expiry.

## Test expectations
Unit tests with a fixed clock. Boundaries 0, 1, max, max+1. Non-integer inputs including `True`.

## Validation tiers
| Tier | Environment | ACs | Why above the cheapest |
|------|-------------|-----|------------------------|
| unit | LOCAL | AC-1..AC-4 | Cheapest tier; fully covers the change |

## How this is verified
`python -m pytest -q` (whole suite, < 2 s). Proven to run at P1.

## Pending human approval
NONE

## Review routing
- code-review — `productionCode`
- simplicity-review — `productionCode`, not `mechanicalOnly`
- contract-review — `publicContract` (new keyword, new field, new exception)
- integration-review — `publicContract`

## Rollout impact
None (library, additive).

## Rollback
Revert the merge commit on `feature/link-expiry`.

## Known risks
Positional construction of `Link` by callers — covered by AC-4.

## Acceptance criteria NOT verifiable here
None.

## Next-slice dependency
Slice 02 reads `expires_at` in `resolve()`.

> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: REVIEW.HUMAN.md.
Status: APPROVED
# Test plan: Slice 01 — Store an optional expiry on links

Written by the verifier (TEST_PLAN, revision 1, after the code-reviewer asked for a non-integer case for AC-3 in
`findings/code-reviewer.test-plan.md`). The status line above is the code-reviewer's approval.

## Acceptance criteria → planned tests
| AC | Planned test(s) | Level | Fails if |
|----|-----------------|-------|----------|
| AC-1 | `tests/test_expiry_create.py::CreateWithExpiryTest::test_ac1_ttl_sets_expires_at_in_utc_seconds` | unit | `expires_at` is relative, local-time, or off by one |
| AC-2 | `…::test_ac2_no_ttl_means_never_expires` | unit | a default TTL is applied |
| AC-3 | `…::test_ac3_rejects_zero_negative_and_too_long`, `…::test_ac3_rejects_non_integer_ttl`, `…::test_ac3_accepts_the_boundaries` | unit | 0, negatives, max+1, floats, strings or `True` are accepted; 1 or max are rejected |
| AC-4 | `…::test_ac4_existing_positional_construction_still_works`, `…::test_ac4_resolve_unchanged_for_links_with_expiry`, plus the untouched `tests/test_shortener.py` | unit | `Link` gains a required field, or `resolve()` changes |

## Levels
Unit only. The package has no I/O; a fixed clock makes every case deterministic.

## Failure and edge cases
- `ttl_seconds=0` (must be rejected, not treated as "no expiry").
- `ttl_seconds=True` (a `bool` is an `int` in Python; must be rejected).
- Exactly `MAX_TTL_SECONDS` (accepted) and one more (rejected).
- Clock at `0.0` (no falsy-time bugs).

## Benchmarks
None: no performance acceptance criterion.

## ACs not verifiable here
None.

## Validation tiers
| Tier | Environment | ACs | Why needed |
|------|-------------|-----|------------|
| unit | LOCAL | AC-1..AC-4 | Covers the whole change |

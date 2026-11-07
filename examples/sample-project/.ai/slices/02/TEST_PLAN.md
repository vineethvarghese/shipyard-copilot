> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: REVIEW.HUMAN.md (written when ready).
Status: DRAFT
# Test plan: Slice 02 — Expired links stop resolving

Written by the verifier (TEST_PLAN, round 0). Awaiting the code-reviewer's TEST_PLAN review. No code or tests
may be written for this slice until the code-reviewer approves the status line above.

## Acceptance criteria → planned tests
| AC | Planned test(s) | Level | Fails if |
|----|-----------------|-------|----------|
| AC-1 | `tests/test_expiry_resolve.py::ResolveExpiryTest::test_ac1_resolves_before_expiry` | unit | a live link raises, or the URL is wrong |
| AC-2 | `…::test_ac2_expired_after_expiry`, `…::test_ac2_boundary_instant_is_expired` | unit | an expired link resolves; `>` used instead of `>=` |
| AC-3 | `…::test_ac3_expired_is_not_unknown`, `…::test_ac3_error_exposes_code_and_expiry` | unit | `LinkExpired` subclasses `UnknownCode`, or lacks `code` / `expires_at` |
| AC-4 | `…::test_ac4_no_ttl_resolves_far_future` | unit | a link without expiry raises at any clock value |
| AC-5 | `…::test_ac5_expired_link_stays_in_store` | unit | resolving deletes or mutates the stored link |

## Seams under test
`Shortener.resolve` / `Shortener.create` (from SLICE.md); every test below calls the public API only.

## Levels
Unit only, with a mutable fake clock (`clock.now = …`) passed to `Shortener(clock=...)`.

## Test doubles
- clock: the fake clock from `tests/test_expiry_create.py` (system boundary: time). No fake of any `shortener.*` module.

## Failure and edge cases
- Clock exactly equal to `expires_at` (expired).
- Clock one second before `expires_at` (live).
- Clock moved backwards after expiry (expired → live again is acceptable and documented; tested so the
  behaviour is explicit).
- Resolving the same expired code twice gives `LinkExpired` both times (not `UnknownCode` the second time).

## Benchmarks
None: no performance acceptance criterion.

## ACs not verifiable here
None.

## Validation tiers
| Tier | Environment | ACs | Why needed |
|------|-------------|-----|------------|
| unit | LOCAL | AC-1..AC-5 | Covers the whole change |

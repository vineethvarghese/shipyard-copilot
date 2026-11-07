> 👤 HUMAN: read this. ~2 min. Decision needed: approve the delivery plan, or change something below.

# link-expiry: plan approval

**Recommendation:** APPROVE. Two small slices; the first is additive and safe to merge alone.

## What we will build
Links can be created with an optional time to live. Once it passes, resolving the link raises a clear
"expired" error instead of returning the URL. Links without a TTL behave exactly as today.

## Slices
- 01 Store an optional expiry on links: records the data first, no behaviour change.
- 02 Expired links stop resolving: enforces it, after 01 is merged.

## Decisions you are approving
1. Absolute `expires_at` on the link / a stored TTL / one comparison on read, clock-injectable.
2. Keep expired links / delete on read / "expired" stays distinguishable from "unknown".
3. Maximum TTL one year, as a constant / configurable / no config change (C-4).

## Risks you are accepting
- Callers that catch only `UnknownCode` will see `LinkExpired` for expired links (slice 02). ASSUMED acceptable:
  no callers outside this repo.

## Questions for you now
NONE

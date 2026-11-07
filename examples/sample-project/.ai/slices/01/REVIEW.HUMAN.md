> 👤 HUMAN: read this. ~2 min. Decision needed: merge slice 01, or request changes.

# Slice 01: Store an optional expiry on links

**Recommendation:** MERGE. Additive change, all 4 criteria tested, two review findings fixed in one round.

## Check these
1. `src/shortener/models.py` — is `expires_at` as an absolute UTC timestamp (not a TTL) the shape you want
   slice 02 to enforce against?
2. `src/shortener/service.py` — is one year the right maximum TTL (your P4 answer to G3)?

## What changes
`create(url, ttl_seconds=None)` records an expiry on the link. Bad TTLs raise `InvalidTTL`.
Nothing changes for links created without a TTL. Expired links still resolve until slice 02.

## Risks you are accepting
NONE

## Evidence
Build PASS · tests PASS (11 run) · criteria verified 4/4 · reviewers code, simplicity, contract, integration ·
BLOCKING resolved 0 (MAJOR 1 and MINOR 1 fixed). Full record: EVIDENCE.md

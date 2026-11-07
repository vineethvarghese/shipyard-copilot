> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: none (concepts reach the human at P4 in chat).
# Concepts brief: link-expiry

Request (verbatim): "Add expiry to short links. Campaign links should stop working after a while."
Brainstorm breadth: 1 (lenses: technical, value, contrarian).

## Sealed elephant take
Written by discovery before any goldfish ran. Not edited afterwards.

> Add an optional `ttl_seconds` to `create()`, store an absolute `expires_at` on `Link`, and make `resolve()`
> raise a new `LinkExpired` error once the injected clock passes it. Two slices: store, then enforce. Keep
> expired links in the store so "expired" and "unknown" stay distinguishable. Risk: positional construction of
> `Link` by callers if a required field is added.

## Goldfish results

### Lens: technical
1. **Absolute expiry on the record** (S). Store `expires_at`; check on read. Why: one comparison, no jobs.
   Risk: clock source must be injectable for tests.
2. **Lazy delete on read** (S). Delete the link when an expired read happens. Risk: "expired" becomes "unknown"
   after the first read.
3. **Background sweeper** (M). Periodic clean-up of expired links. Risk: a new moving part for a toy store.

### Lens: value
1. **Expiry with a clear "expired" signal** (S). Owners care that visitors see "this link has expired", not
   "not found". Why: support load and trust.
2. **Preset durations** (S). Offer 1 day / 7 days / 30 days only. Risk: rigid; callers want seconds.
3. **Expiry report** (M). List links expiring soon. Risk: no consumer asked.

### Lens: contrarian ("much smaller or nothing")
1. **Do nothing; document "delete the link"** (S). Owners delete campaign links by hand. Risk: no delete API
   exists, so this is not actually smaller.
2. **Expiry only, no enforcement** (S). Record the date and let callers check it. Risk: every caller repeats the
   check; the request says links should "stop working".

## Clusters and ranking
Ranked against C-1 (≤150 lines per slice), C-2 (no new packages), C-4 (`src/shortener/` only) and repo facts.

| Rank | Concept | Lenses that proposed it | Fit |
|------|---------|-------------------------|-----|
| 1 | **A. Absolute expiry + `LinkExpired` on resolve, keep record** | technical, value, elephant | Fits C-1..C-4; two small slices |
| 2 | **B. Absolute expiry + lazy delete on read** | technical | Fits, but loses the expired/unknown distinction value asked for |
| 3 | **C. Record expiry only, callers enforce** | contrarian | Smallest, but does not meet "stop working" |

Rejected: background sweeper (new moving part, violates the spirit of C-2), preset durations (no evidence of need),
expiry report (no consumer).

## Disagreements
- **Goldfish (contrarian) vs elephant:** contrarian says enforcement could be left to callers (C). The elephant
  enforces in `resolve()`. Not settled by evidence; the request wording favours enforcement → asked at P4 (G1).
- **Goldfish (technical) vs value:** lazy delete (B) vs a distinct "expired" signal (A). Recorded, routed to P4.

## Open questions
None beyond the gap list.

## Gap list
| ID | Question | Why it matters | Options | Recommendation | Blocking |
|----|----------|----------------|---------|----------------|----------|
| G1 | Should `resolve()` enforce expiry, or only record it? | Decides concept A vs C | enforce / record only | Enforce (A) | yes |
| G2 | Keep expired links in the store, or delete them? | Decides whether "expired" stays distinguishable from "unknown" | keep / lazy delete / sweeper | Keep; no clean-up in this project | yes |
| G3 | Maximum TTL? | Validation bound for AC-3 of slice 01 | none / 1 year / configurable | 1 year, constant, no config (C-4) | no |

P4 answers (2026-10-12, human): concept **A**; G1 enforce; G2 keep, no clean-up; G3 one year.

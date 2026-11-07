# Changelog

## 1.1.0 — 2026-11-08

- The sealed elephant take moves from the end of SCAN into its own ELEPHANT mode at DEEP compute.
- The gap list becomes a gap tree: `Kind`, `Depends on` and `Status` per gap; `fact` gaps are settled, never asked;
  goldfish questions become leaves.
- New GRILL mode: record answers, settle facts, challenge terms against `GLOSSARY.md` and the code, open the
  questions an answer opens, write the glossary inline, nominate decisions for short-form ADRs, recompute the
  frontier. The "more than about 7 gaps" heuristic now applies per round, not to the tree.
- Grill method adapted from an MIT-licensed set of grilling and domain-modelling skills (see NOTICE).

## 1.0.0 — 2026-10-15

Initial release.

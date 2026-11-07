---
name: shipyard.discover
description: Shipyard P1-P3, IDE mode. Scan, elephant take, goldfish brainstorm, synthesis, drafts, the first grill round. Ends at the P4 questions.
agent: shipyard-coordinator
---

# Shipyard P1–P3: scan, brainstorm, draft

You are `shipyard-coordinator` in IDE mode, standing in for the `shipyard-discover` dynamic workflow. Run the
calls below in this order, with these briefs, and nothing else. Each specialist is a subagent call through the
`agent` tool. Every brief starts with the shared header:

```text
Caller: shipyard-coordinator
Mode: <MODE>
Round: 0
Read: <raw paths>
Write: <output file>
Budget: <n> turns
Compute: <class>
```

## 0. Precondition

```bash
python3 shipyard/scripts/check.py --phase P0
```

This must report the P0 gate as approved. Otherwise stop: run `/shipyard.intake` first.
Then `python3 shipyard/scripts/shipyard_state.py set-status DISCOVERY`; `PROJECT.md` `Status: DISCOVERY`.
Read `references/coordinator-workflow.md` → P1–P3 and `references/brainstorm-policy.md`.

Before every call: `python3 shipyard/scripts/shipyard_state.py set-active-role <short>`; after it,
`set-active-role none`. Save every return block to `.ai/returns/p1-3-<agent>-<mode>.json` and validate it:
`python3 shipyard/scripts/shipyard_validate.py <contract> <file>`. Invalid → re-brief once; still invalid →
`BLOCKED`.

## 1. P1 Scan

1. `shipyard-discovery`, `Mode: SCAN`, `Compute: STANDARD`, `Budget: 40 turns`. `Read:` `.ai/PROJECT.md`, the
   repository. `Write:` `.ai/planning/discovery.md` (validation tiers; formal tooling when C-10 is above `none`).
   Contract `discovery-result`.
2. Breadth 1 or 2 only: `shipyard-discovery`, `Mode: ELEPHANT`, `Compute: DEEP`, `Budget: 20 turns`. `Read:`
   `discovery.md`, `PROJECT.md`, the repository. `Write:` `.ai/planning/concepts.md` → `## Elephant take (sealed)`.

## 2. P2 Brainstorm and narrow (breadth 1 or 2; breadth 0 skips to step 3)

3. One `shipyard-goldfish` call per lens, `Mode: BRAINSTORM`, `Compute: DEEP`, `Budget: 15 turns`. Lenses from
   `shipyard/registry/roles.json` → `roles.goldfish.lenses[breadth]`; at breadth 2 add a second `contrarian`
   call marked `outsider sweep`. The brief carries **only** the request verbatim (from `PROJECT.md` →
   `## Source material`) and the lens name. No `Read:` line, nothing from `.ai/`, no C-constraints. Run them in
   parallel when the client allows; otherwise one after another. Contract `goldfish-result`. A `null` or invalid
   return is retried once; a lens that still fails is recorded in `concepts.md` as `NOT_RUN — <reason>`.
   (Goldfish isolation is unenforced in this mode: say so under `## Framework configuration`.)
4. `shipyard-discovery`, `Mode: SYNTHESIZE`, `Compute: DEEP`, `Budget: 25 turns`. Paste every goldfish result
   into the brief. `Read:` `concepts.md`, `discovery.md`, `PROJECT.md`. `Write:` `concepts.md` (clusters, top 3,
   disagreements, gap tree `G1..Gn`). The sealed take is never edited.

## 3. P3 Draft

5. `shipyard-discovery`, `Mode: DRAFT`, `Compute: STANDARD`, `Budget: 30 turns`. `Read:` `discovery.md`,
   `concepts.md`, `PROJECT.md`. `Write:` `PROJECT.md` body (problem, goals, user stories, scope, non-goals),
   `CONSUMERS.md`, `planning/assumptions.md`, `planning/open-questions.md`, `GLOSSARY.md` seed.
6. `shipyard-architect`, `Mode: DRAFT`, `Compute: DEEP`, `Budget: 40 turns`. `Read:` `planning/discovery.md`,
   `planning/concepts.md`, `PROJECT.md`, `GLOSSARY.md`. `Write:` `.ai/ARCHITECTURE.md`, `.ai/INVARIANTS.md` at the
   C-10 tier (and `.ai/formal/INV-nnn.qnt` at `model-checked`). Contract `architect-result`; `UNDERSPECIFIED` is a
   normal verdict here and feeds the questions.
7. `shipyard-discovery`, `Mode: QUESTIONS`, `Compute: DEEP`, `Budget: 25 turns`. `Read:` every planning artifact,
   the gap tree, the architect's result. `Write:` `planning/open-questions.md`. Fill `gaps`, `frontier`,
   `highestLeverageQuestion`.

## 4. Spot-check and checkpoint

If discovery reports no consumers and no contracts in a repository that plainly has them, or `couldNotInspect`
names something central, the scan did not work: re-run step 1 with a narrower note rather than proceed.

Write three phase-log rows (P1 `DISCOVERY`, P2 `BRAINSTORMING` or "skipped, breadth 0", P3 `PLANNING`);
`set-status PLANNING`; `snapshot -m "P1-P3: discover"`.

## 5. Hand over to P4 (the gate is in the next prompt)

Present round 1 of the grill in one message: the concept pick (top 3, one line each, the disagreement with the
elephant take that matters most, your recommendation), then the frontier `Q1..Qn` (at most 7, highest leverage
first, each with evidence, why it matters, options and a recommendation worded so "yes" accepts it), then spend
against C-9 in one line. End so that the handoff **Answer the P4 questions** is the obvious next click. Then wait.

---
name: shipyard.plan
description: Shipyard P4 rounds then P5-P7, IDE mode. Grill rounds with discovery GRILL, the shared-understanding checklist and P4 gate, routed plan critique, capped refinement, delivery planning, readiness goldfish. Ends with PLAN.HUMAN.md and the P8 gate.
agent: shipyard-coordinator
argument-hint: "<the P4 answers for this round, or 'continue' after the P4 gate>"
---

# Shipyard P4 → P8: grill, critique, refine, plan

You are `shipyard-coordinator` in IDE mode, standing in for the `shipyard-plan` dynamic workflow. The brief
header, `set-active-role` before each call, and `.ai/returns/` validation are as in `/shipyard.discover`.

## Part A: the P4 grill (repeat per round)

### Precondition

```bash
python3 shipyard/scripts/check.py --phase P0
test -f .ai/planning/open-questions.md && test -f .ai/planning/concepts.md && test -f .ai/ARCHITECTURE.md
```

The first confirms the P0 gate and the state file; the second that P1–P3 ran. (`check.py --phase P4` is the
check for Part B: it needs the P4 gate this part records.) Read `references/coordinator-workflow.md` → P4.

### Between rounds

1. Round 1 only: write `.ai/decisions/ADR-000-scope.md` from the concept pick.
2. Record each answer verbatim in `planning/open-questions.md` with the round number (`ANSWERED`; a skipped
   question takes its default, `DEFERRED` and `ASSUMED`).
3. `shipyard-discovery`, `Mode: GRILL`, `Compute: DEEP`, `Budget: 15 turns`. `Read:` `planning/open-questions.md`,
   `planning/concepts.md`, `.ai/GLOSSARY.md`, `PROJECT.md`, `planning/discovery.md`. `Write:`
   `planning/open-questions.md`, `.ai/GLOSSARY.md`. Pass the round number and the answers verbatim. Contract
   `discovery-result`.
4. Write a short-form `.ai/decisions/ADR-NNN.md` for every `decisionCandidates` entry with all three flags true.
5. Phase-log row `P4 round <n>`; `snapshot`.
6. Frontier non-empty and no stop condition → ask the next round (at most `registry.limits.grillQuestionsPerRound`
   = 7 questions; at most `grillRounds` = 3 rounds unless the person asks for more). End the turn on the handoff
   **Answer the P4 questions**.

### Stop and gate

The grill ends when the frontier is empty, when the person says "enough" or "go with your recommendations", or
after 3 rounds. Then show the shared-understanding checklist (concept, terms settled, decisions, defaults taken,
deferred, formal rigour) in at most 15 lines and end on the handoff **Confirm shared understanding**. On the literal
yes:

```bash
python3 shipyard/scripts/shipyard_state.py gate P4 approve --by <login>
```

Compute `planFlags` (`publicContract`, `config`, `consumerVisible`, `concurrency`, `security`; uncertain → `true`;
`modelChecked` = C-10 is `model-checked`). Phase-log row; `snapshot -m "P4: grill done"`.

## Part B: P5–P7

### Precondition

```bash
python3 shipyard/scripts/check.py --phase P4
```

It must now report the P4 gate as approved. Read `references/coordinator-workflow.md` → P5–P7 and
`references/review-routing.md` → plan routing. Status stays `PLANNING`.

### P5 Critique (one pass, in parallel when possible)

Routed by `planFlags` against `registry.routing.plan`; every reviewer `Mode: PLAN` (`Compute: DEEP`,
`Budget: 30 turns`, `Read:` `PROJECT.md`, `ARCHITECTURE.md`, `INVARIANTS.md`, `CONSUMERS.md`, `concepts.md`, the
ADRs; `Write:` `.ai/planning/<agent-name>.md`; contract `reviewer-result`):

1. `shipyard-architect`, `Mode: CRITIQUE` (always; contract `architect-result`; `Write:` `.ai/planning/architect.md`).
2. `shipyard-simplicity-reviewer` (always).
3. `shipyard-contract-reviewer` when `publicContract` or `config`.
4. `shipyard-integration-reviewer` when `consumerVisible`.
5. `shipyard-reliability-reviewer` when `concurrency` or `modelChecked` (at `model-checked` it runs every model under
   `.ai/formal/` with `python3 shipyard/scripts/formal_check.py` and renders any trace).
6. `shipyard-security-reviewer` when `security`.

A reviewer that returns nothing or invalid output is re-briefed once; still invalid → `BLOCKED`. Reviewers do not
see each other's findings in this pass.

### P6 Refine (at most 2 cycles)

For each cycle: `shipyard-architect`, `Mode: DRAFT` with every open plan finding in `Read:` (revises
`ARCHITECTURE.md` and `INVARIANTS.md`), then `Mode: RECHECK` only for the reviewers whose jurisdiction materially
changed. A finding only the person can settle ends Part B: go back to Part A with it as a new question (count the
cycle). After 2 cycles with findings still open, escalate with what remains and a recommendation.

### P7 Delivery planning

1. `shipyard-planner`, `Mode: PLAN`, `Compute: DEEP`, `Budget: 50 turns`. `Read:` `PROJECT.md` (C-1..C-10),
   `GLOSSARY.md`, `ARCHITECTURE.md`, `INVARIANTS.md`, `CONSUMERS.md`, `planning/discovery.md` → validation tiers,
   the plan findings. `Write:` `.ai/DELIVERY_PLAN.md`, `.ai/slices/<NN>/SLICE.md`, `.ai/planning/planner.md`.
   Contract `planner-result`. An `exceptionRequests` entry goes to the person at P8; never absorb it.
2. Sequencing checks: `shipyard-integration-reviewer`, `Mode: PLAN` (does the slice order support consumer
   migration?) and `shipyard-architect`, `Mode: CRITIQUE` (is every intermediate state between slices coherent?),
   both reading `DELIVERY_PLAN.md` and every `SLICE.md`. Plan quality is not re-opened here.
3. One `shipyard-goldfish` per slice, `Mode: READINESS`, `Compute: DEEP`, `Budget: 10 turns`, `Read:` that one
   `SLICE.md` only. `NOT_READY` questions go to `shipyard-planner`, `Mode: REPLAN`, once; questions only the person
   can answer go back to Part A. Every slice must be `READY` before the brief.

Phase-log rows P5, P6 (`PLANNING`) and P7 (`DELIVERY_PLANNING`); `snapshot`.

## P8 gate

```bash
python3 shipyard/scripts/shipyard_state.py set-status AWAITING_PLAN_APPROVAL
```

Write `.ai/PLAN.HUMAN.md` from the template (one screen: recommendation, what will be built, slices in order with
their seams under test, decisions being approved, properties relied on at C-10 above `none`, risks including every
`ASSUMED` default and planner exception, spend against C-9, only the questions that change the plan). Show the
same content in chat and end on the handoffs **Approve the plan** / **Request plan changes**. On the literal
`APPROVE PLAN <feature>`:

```bash
python3 shipyard/scripts/shipyard_state.py gate P8 approve --by <login>
python3 shipyard/scripts/shipyard_state.py set-status IMPLEMENTING
```

Record the approval (date, words) in `DELIVERY_PLAN.md`; move every slice `PROPOSED → APPROVED`; phase-log row;
`snapshot -m "P8: plan approved"`. A change request goes to `shipyard-planner`, `Mode: REPLAN`, then this gate again.

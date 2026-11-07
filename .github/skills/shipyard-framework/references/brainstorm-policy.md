# Brainstorm policy (P2) and readiness checks (P7)

Shipyard uses the elephant/goldfish method, adapted from https://github.com/vshvedov/elephant-goldfish (MIT). The
**elephant** remembers everything: discovery, with the whole repository and request in context. The **goldfish**
remember nothing: fresh agents that see only the request, one lens and the code. People with full context stop seeing
some options; a cold mind still sees them. The value is in the gap between the two.

How discovery runs the method (take format, clustering, ranking) lives in the `brainstorm-elephant-goldfish`
capability skill. This file fixes the rules the workflows and the coordinator enforce.

## When P2 runs

P2 runs inside the `shipyard-discover` workflow, after the P1 scan and before the P3 drafts, whenever the brainstorm breadth is 1
or 2. With breadth 0 it is skipped: discovery still writes `concepts.md` with the gap list only.

Breadth is a P0 parameter, chosen with C-6 (time and artifact budget) and C-9 (cost budget):

| Breadth | Lenses (`registry.roles.goldfish.lenses`) | Recommend it when |
|---|---|---|
| `0` | none | The design is already decided, or C-6 says "minimal". The human brought a design, not an idea. |
| `1` (default) | `technical`, `value`, `contrarian` | The goal is clear but the approach is open. |
| `2` | `technical`, `value`, `experience`, `contrarian`, `market` + a contrarian **outsider** sweep | The idea itself is open, the stakes are high, and C-6 and C-9 allow it. |

The lenses:

- `technical` — the cleanest build on what the repository already has.
- `value` — what the requester actually gets, and the smallest thing that delivers most of it.
- `experience` — the consumer's and the operator's day: setup, failure, diagnosis.
- `contrarian` — "much smaller, or nothing at all". The outsider sweep answers as someone who has never seen this
  codebase or this domain.
- `market` — how others solve this. The only lens allowed to read the web.

Cap breadth before depth (`compute-policy.md`): more goldfish on the same question mostly return the same ideas.

## Order inside the `shipyard-discover` workflow

```text
P1  discovery SCAN        -> discovery.md, validation tiers                 (STANDARD)
    discovery ELEPHANT    -> concepts.md "## Elephant take (sealed)"      (breadth 1-2, DEEP)
P2  goldfish BRAINSTORM   -> one agent per lens, in parallel              (breadth 1-2)
    discovery SYNTHESIZE  -> clusters, top 3, disagreements, open questions, gap list G1..Gn
P3  discovery DRAFT       -> PROJECT.md body and user stories, GLOSSARY.md seed, CONSUMERS.md,
                             assumptions.md, open-questions.md
    architect DRAFT       -> ARCHITECTURE.md, INVARIANTS.md (and .ai/formal/ at C-10 model-checked)
    discovery QUESTIONS   -> the gap tree and the first grill round for P4
```

The workflow returns `NEEDS_HUMAN` with the top concepts, disagreements, the gap tree and the first round's frontier
for the P4 gate.

## The sealed elephant take

Discovery writes its own best concept to `concepts.md` under `## Elephant take (sealed)` in its `ELEPHANT` mode,
after `SCAN` and **before any goldfish runs**. It runs at `DEEP` compute on purpose: the disagreement between this
take and the goldfish is the brainstorm's main signal, and a weak elephant makes a weak signal. After that it is
never edited. If the elephant writes after reading the goldfish, the disagreements — the most valuable output —
vanish into a blended answer.

## Goldfish isolation

Each goldfish gets **only**:

- the human's request, verbatim (from `PROJECT.md` → `## Source material`, passed as `args.request`);
- its one lens;
- read access to the repository's code.

It does **not** get `discovery.md`, `concepts.md`, the elephant take, the C-constraints, other goldfish output, or
anything else under `.ai/`. The brief says so; the goldfish agent refuses `.ai/` reads; it has no write tools. The
workflow passes no planning context in the prompt. Shared framing makes independent ideas correlated, and correlated
ideas look like agreement.

Goldfish run in parallel and return `contracts/goldfish-result.schema.json`: 2–4 concepts (title, summary, why,
risks, relative size S/M/L) and the questions they would ask the requester. A goldfish that returns `null` or invalid
output is retried once; a lens that still fails is recorded in `concepts.md` as `NOT_RUN — <reason>` and named at P4.
The brainstorm never silently shrinks.

## Convergence (discovery SYNTHESIZE, DEEP)

Discovery reads the goldfish results, its sealed take, `discovery.md` and the C-constraints, then:

1. **Clusters** similar concepts and records which lenses proposed each cluster. Several lenses landing on one idea
   is provenance, not proof (hard rule 3).
2. **Ranks** clusters against the C-constraints (slice budget, new-project budget, reuse posture, blast radius) and
   repository facts, with evidence. A concept that breaks a `SPECIFIED` constraint is ranked out, with the reason.
3. **Flags disagreements** with the elephant take — every place a goldfish proposed something the elephant did not
   consider, or argued the opposite. These lines are the most valuable in the file.
4. **Picks a top 3.** Always keep the contrarian's "much smaller or nothing" in view: if it survives ranking it goes in
   the top 3; if not, say why in one line.
5. **Writes the gap list `G1..Gn`** as a tree: every unknown that would change which concept wins or how it is
   built, each with question, kind (`concept`, `scope`, `term`, `decision`, `invariant`, `fact`), the gaps it
   depends on, why it matters, evidence, options, a recommendation worded so that "yes" accepts it, and `BLOCKING`
   or `DEFERRABLE`. The questions each goldfish returned become leaves of the tree, tagged with their lens, so none
   is lost. `fact` gaps are settled from the repository and never asked.

## The grill at P4

P4 is a short series of rounds, not one turn (`coordinator-workflow.md` → P4). Round 1 is the concept pick plus the
**frontier**: every open gap whose dependencies are settled, highest leverage first, at most
`registry.limits.grillQuestionsPerRound`. Present the top 3 as one line each (what it is, why, size, main risk), name
the disagreement that matters most, and recommend one. After each answer set the coordinator calls discovery in
`GRILL` mode (DEEP): it records the answers, settles any new fact from the repository, challenges terms the human
used against `GLOSSARY.md` and the code, writes the glossary, and returns the next frontier plus candidate
decisions. The loop ends when the frontier is empty, when the human says "enough" or "go with your recommendations",
or at `registry.limits.grillRounds`; the coordinator then shows the shared-understanding checklist and waits for an
explicit yes.

When the human picks the concept (round 1):

1. Write `.ai/decisions/ADR-000-scope.md` (title **ADR-000: Scope**): context = the top 3, options = each concept,
   decision = the human's pick quoted verbatim, consequences = what is now out of scope. Status `ACCEPTED`, deciders
   the human.
2. Record every answer verbatim in `planning/open-questions.md` and close it; an answer that is hard to reverse,
   surprising without context and a real trade-off also becomes a short-form ADR (`artifact-templates.md`).
3. After the checklist, pass the pick and every answer to the `shipyard-plan` workflow as `args.answers`.

The human may pick a concept outside the top 3, combine two, or reject all of them. Record exactly what they said.
"None of these" sends discovery back to `DRAFT` with that answer; it does not re-run the brainstorm unless the human
asks for a wider breadth.

## Readiness goldfish (P7, inside the `shipyard-plan` workflow)

After the planner writes the slices, one goldfish in `READINESS` mode reads **each `SLICE.md` cold** — only that file,
any file it names explicitly, and the code — and answers one question: *could a first-time implementer ship this
without asking anything?*

It returns `READY`, or `NOT_READY` with each question the implementer would have to ask. It checks that every
acceptance criterion is testable as written, both touch sets and the branch are stated, `## Seams under test` names
a seam that exists in the repository, the verification commands exist, and the prerequisites are named. It files no
style or design opinions.

`NOT_READY` questions go back to the planner once. Questions the planner can answer from approved sources are fixed in
the `SLICE.md`; questions only the human can answer end the workflow with `NEEDS_HUMAN` and go to P4. Every slice must
be `READY` before `PLAN.HUMAN.md` is written.

## Credit

The elephant/goldfish method is adapted from https://github.com/vshvedov/elephant-goldfish (MIT licence). See
`NOTICE` at the plugin root.

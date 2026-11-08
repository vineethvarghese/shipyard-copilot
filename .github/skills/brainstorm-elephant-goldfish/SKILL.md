---
name: brainstorm-elephant-goldfish
description: >
  Elephant/goldfish brainstorm and P4 grill method for Shipyard. Discovery loads it in ELEPHANT mode to write the
  sealed elephant take, in SYNTHESIZE mode to cluster and rank goldfish concepts against the C-1..C-10 constraints
  and repository facts, flag disagreements and write the G1..Gn gap tree, in QUESTIONS mode to turn the tree into
  the first grill round, and in GRILL mode to record the human's answers, settle facts, challenge terms against the
  glossary and recompute the frontier round by round until shared understanding. It also defines the lens prompts
  (technical, value, experience, contrarian, market), goldfish isolation, the contrarian outsider sweep at breadth
  2, the glossary rules, and the cold readiness check of a SLICE.md. Not for reviewing code or plans.
---

# Brainstorm: elephant and goldfish

Version 1.1.0 · used by discovery (`shipyard-discovery`, ELEPHANT, SYNTHESIZE, QUESTIONS and GRILL); defines the
goldfish briefs that the discover and plan workflows send to `shipyard-goldfish`

The brainstorm method is adapted from the elephant/goldfish workflow (https://github.com/vshvedov/elephant-goldfish,
MIT licence). The grill (a design tree asked frontier by frontier until shared understanding, with the glossary and
decision records updated inline) is adapted from an MIT-licensed set of grilling, domain-modelling and
specification skills. Both credits are recorded in the plugin's NOTICE.

## The idea

Someone with full context (the **elephant**) knows the codebase, the constraints and the history. That knowledge
makes it good at judging ideas and bad at having new ones: it sees what the repository already suggests. Someone
with almost no context (a **goldfish**) sees the problem fresh. It misses constraints, but it proposes the things
the elephant can no longer see. The method gets both views without letting either contaminate the other, then puts
them side by side. **Where they disagree is the main signal.**

| Role | Who | Sees | Produces |
|---|---|---|---|
| Elephant | `shipyard-discovery` (ELEPHANT, then SYNTHESIZE, QUESTIONS, GRILL) | Everything: request, repository, `discovery.md`, C-1..C-10 | The sealed elephant take; later the synthesis, the gap tree and each grill round |
| Goldfish | `shipyard-goldfish` (BRAINSTORM), one per lens, in parallel | Only the verbatim request, one lens, and read-only repository code | 2–4 concepts through its lens, plus questions it would ask |
| Readiness goldfish | `shipyard-goldfish` (READINESS), one per slice | One `SLICE.md`, files it names, repository code | READY or NOT_READY plus questions |

Breadth (P0 parameter): `0` skips the brainstorm; `1` runs technical, value and contrarian; `2` runs all five lenses
plus the contrarian outsider sweep.

## Step 1 — The sealed elephant take (ELEPHANT, before any goldfish runs)

In ELEPHANT mode (a separate, deep-compute call right after SCAN, unless breadth is 0), write your own best concept
to `.ai/planning/concepts.md`. You have `discovery.md` and the whole repository; use them. This is the one moment
full context is an asset rather than a bias:

```markdown
## Elephant take (sealed)
Sealed: before any goldfish ran. Never edited after this point.
Concept: <one sentence>
Shape: <3-6 lines: what gets built, on which existing modules>
Builds on: <path:line evidence>
Relative size: S | M | L
Fits constraints: <C-ids it satisfies; any it strains, and how>
Biggest risk: <one line>
What I would cut first: <one line>
Confidence: HIGH | MEDIUM | LOW — <why>
```

Sealing is what makes later disagreement meaningful. If you revise the take after reading goldfish output, you have
averaged the views and lost the signal. In SYNTHESIZE you may write a **separate** "Elephant, revised" note; never
change the sealed section.

## Step 2 — Goldfish isolation

Each goldfish brief contains the routing header, the verbatim request (quoted, unedited), one lens and its prompt,
and a turn budget. Nothing else. The goldfish never reads `.ai/` (not `discovery.md`, not `concepts.md`, not the
elephant take, not another goldfish's output). Do not summarise or "helpfully" frame the request: a paraphrase
carries the elephant's framing in with it.

## Step 3 — Lenses and prompt sketches

Each sketch is the lens text placed in the goldfish brief after the verbatim request.

| Lens | Breadth | Prompt sketch |
|---|---|---|
| technical | 1, 2 | "Looking only at this request and this repository's code, what is the cleanest way to build it on what already exists? Name the modules you would extend and what you would not need to write. Give 2–4 distinct approaches, not variations of one." |
| value | 1, 2 | "What does the requester actually get from this? What is the smallest thing that delivers most of that value, and what could be left out with little loss? Propose 2–4 concepts ordered by value per unit of effort." |
| experience | 2 | "Picture the consumer who calls this and the operator who runs it. Walk through first setup, a normal day, a failure, and diagnosing that failure. What design makes those moments easy? Propose 2–4 concepts." |
| contrarian | 1, 2 | "Argue for doing much less, or nothing. What existing feature, configuration, script or process already covers most of this? What would a version one-tenth the size look like? Propose 2–4 concepts, at least one of which builds nothing new." |
| market | 2 | "How do other public tools and projects solve this problem? Read public pages only. Summarise 2–4 approaches and say which fits this repository and why. Cite each page you read." |

**Contrarian outsider sweep (breadth 2 only).** One extra contrarian goldfish answers as an outsider who has never
seen this codebase or this domain: "Without looking at any code, what would a sensible engineer from a different
field do here? What assumption in the request would they question first?" It gets only the verbatim request. Its
value is in questioning the request itself.

## Step 4 — Convergence (SYNTHESIZE)

Inputs: the goldfish results, the sealed take, `discovery.md`, `PROJECT.md` (C-1..C-9). Write to `concepts.md`:

1. **Cluster.** Group concepts by underlying approach, not by wording. Two goldfish proposing "a cache in front of
   the client" from different lenses are one cluster with two sources. Record each source lens.
2. **Rank each cluster** against hard facts, in this order:
   - C-constraints: C-1 slice budget, C-2 new-project budget, C-3 reuse posture, C-4 blast radius, C-6 time and
     artifact budget, C-7 convention posture, C-9 cost budget (C-5 and C-8 rarely discriminate). Mark each
     `fits | strains | breaks` with one line of why.
   - Repository facts from `discovery.md`, with `path:line`: what it builds on, what it would have to replace.
   - Value delivered and relative size.
   A cluster that breaks a hard constraint drops out unless the constraint itself looks wrong; then it becomes a gap.
3. **Disagreements, the main signal.** For every place a goldfish differs from the sealed take (a different
   approach, a different size, a claim the elephant thought settled), write: what the elephant said, what the
   goldfish said and from which lens, the evidence each rests on, and what it would take to decide. Never resolve a
   disagreement by counting votes. Agreement between goldfish is provenance, not evidence.
4. **Top 3**, each with: one-paragraph shape, sources (lenses + elephant), constraints fit, biggest risk, size.
5. **Open questions** raised by goldfish that the repository cannot answer.

Then write the gap list.

## Step 5 — Gap tree G1..Gn

A gap is something the plan cannot be made safely without: an open requirement, a disagreement only a human can
settle, a constraint that blocks every good concept, a term the human and the code use differently, an invariant the
human has not stated, a missing fact. Gaps form a **design tree**: a decision opens the decisions that hang off it.
Highest leverage first (the gap whose answer makes others moot). Format:

```markdown
### G3: <short title>
Kind: concept | scope | term | decision | invariant | fact
Depends on: <gap ids that must be answered or settled first | none>
Evidence: <path:line, discovery.md section, the goldfish lens that raised it, or the disagreement it comes from>
Why it matters: <what in the plan changes depending on the answer>
Options: A) <option> · B) <option> · C) <option, optional>
Recommendation: <A|B|C>, because <evidence-based reason>; worded so that "yes" accepts it
Blocking?: YES — no safe default | NO — default if unanswered: <the default>
Status: OPEN | ANSWERED | SETTLED | DEFERRED
```

Kinds: `concept` (which approach), `scope` (in or out), `term` (what a word means here; feeds `GLOSSARY.md`),
`decision` (a design or product choice), `invariant` (a property that must always hold; feeds `INVARIANTS.md` and
the C-10 tier), `fact` (answerable from the repository or a command). **A `fact` gap is never asked.** Settle it
yourself, cite the evidence and mark it `SETTLED`. If you cannot, it is `UNRESOLVED` and becomes a `decision` gap
with the evidence you have.

The questions each goldfish returned become leaves of the tree, tagged with their lens in `Evidence:`, so none is
lost; the outsider sweep's questions usually become `scope` gaps about the request itself.

In QUESTIONS mode, the concept pick and the **frontier** (every `OPEN` gap whose `Depends on` are all resolved:
`ANSWERED`, `SETTLED`, or `DEFERRED` because the human took the default, which still unblocks what hangs off it;
highest leverage first) become round 1 of the P4 grill. Return the frontier's ids in `frontier`; a gap
whose dependency is still open belongs to a later round, not this one. Non-blocking gaps in the frontier are listed
with their defaults so the human can override them in the same turn.

## Step 5b — GRILL mode: recompute the frontier

The coordinator calls you once per round with the round number and the human's answers, verbatim. In order:

1. **Record.** Write each answer verbatim into `planning/open-questions.md` under its question (`Answer:`,
   `Round:`), set `ANSWERED`. A skipped question takes its default: `DEFERRED`.
2. **Settle facts.** Any new `fact` the answers raise is settled from the repository now; never carried to the human.
3. **Challenge terms.** Compare every term the human used against `.ai/GLOSSARY.md` and the code. A conflict
   ("the glossary defines cancellation as X, but you seem to mean Y") or a fuzzy word ("the customer or the user?")
   becomes a `term` gap for the next round, with the two meanings and where each lives. Cross-reference with the
   code: "the code cancels whole orders, but you just said partial cancellation is possible" is a question, not a
   note.
4. **Open what the answers opened.** A decision usually opens two or three narrower ones; add them with `Kind`,
   `Depends on`, evidence and a recommendation. Invent concrete edge-case scenarios ("what happens when the retry
   lands after the lease expired?") and make each a gap when the answer would change the plan.
5. **Write the glossary now.** Every term settled in this round goes into `.ai/GLOSSARY.md` in this call: term, one
   or two sentences free of implementation detail, `Avoid:` the other words seen for it, `Source:` the human's
   words and the round. Never batch glossary edits for later. Return the terms in `glossaryTerms`.
6. **Nominate decisions.** For each answer, judge three things: hard to reverse; surprising without context; the
   result of a real trade-off. Return every answer as a `decisionCandidates` entry with the three flags; the
   coordinator writes an ADR only when all three are true.
7. **Recompute the frontier** (Step 5 definition: a `DEFERRED` dependency counts as resolved) and return it in
   `frontier`, highest leverage first. An empty frontier means nothing is left to ask; the defaults the human took
   stay `ASSUMED` and are listed on the checklist, so nothing is silently assumed.

You never talk to the human and never decide for them: a recommendation is still a question.

## Step 6 — Readiness check of a SLICE.md (P7)

Each slice gets one readiness goldfish that reads it cold. The question: **could a first-time implementer ship this
without asking anything?** The brief tells it to check:

- Objective in one or two sentences; what is out of scope.
- Every AC is testable as written: an observable outcome, concrete values, no "should be fast" or "handle errors".
- Both touch sets (`## Expected touch set — code`, `## Expected touch set — tests`) and `## Branch` exist and are
  plausible for the ACs.
- Every command the slice relies on (build, canonical test, tiers) exists in the repository.
- Prerequisites (earlier slices, migrations, flags, data) are named.
- Every term and every referenced file exists or is defined.

Verdict `READY` only with zero questions. `NOT_READY` lists each question a first-time implementer would have to
ask, quoting the line that raises it. The plan workflow passes NOT_READY questions to the planner; any the planner
cannot answer from approved sources become gaps.

## Calibration

- A gap is `Blocking?: YES` only if every reasonable default could make the plan unsafe or wasted. Otherwise give
  the default and mark `NO`.
- There is no cap on the size of the tree; some plans need three questions and some need forty. The cap is on
  the **frontier**: more than about 7 gaps ready in one round usually means the tree was cut flat (dependencies
  missing) or the request is two projects. Say which, and put the rest behind the decision they hang off.
- A `fact` gap that reaches the human is a defect of this method, not a question.
- A readiness `NOT_READY` needs at least one concrete question. Style or design opinions are not readiness issues.

## Examples

Gaps are not reviewer findings; they use the gap format above.

GOOD (kind, dependency, evidence, consequence, options, recommendation, default):

```markdown
### G2: Keep the existing retry contract for streaming responses?
Kind: decision
Depends on: G1
Evidence: src/client/retry.go:88 retries 502 and 503; the value-lens and contrarian goldfish both propose
  streaming export, which the sealed elephant take did not.
Why it matters: A failure after part of a stream is sent would be retried and duplicate rows downstream; the answer
  decides whether slice 2 needs a resumable cursor.
Options: A) Partial-stream failure is terminal · B) Resumable cursor with idempotency key
Recommendation: A, because no consumer in CONSUMERS.md needs resume and B adds a protocol change.
Blocking?: NO — default if unanswered: A
Status: OPEN
```

BAD (no evidence, no options, nothing decided by the answer):

```markdown
### G5: Error handling
Kind: decision
Depends on: none
Evidence: none
Why it matters: Errors are important.
Options: -
Recommendation: Handle errors well.
Blocking?: YES
```

What is wrong with it: it cites nothing, names no plan decision that depends on it, offers no options, and is marked
blocking with no reason.

## Out of jurisdiction

- Choosing the concept, or answering any question for the human: the human picks at P4. You recommend.
- Talking to the human: only the coordinator does; you return the frontier.
- Architecture and invariants: the architect drafts them from your outputs (an `invariant` gap's answer is its
  input, not your `INVARIANTS.md` entry).
- Slicing the work: the planner.
- Editing the sealed take after any goldfish has run: never.

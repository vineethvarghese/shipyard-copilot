# Artifact templates

Templates for everything under `.ai/` in the target repository. These files are **agent-generated**: discovery and
the architect draft them from repository evidence, then the human edits and decides. Never hand a human a blank
template and ask them to fill in fifty fields.

Every material fact carries an assumption label: `SPECIFIED`, `DERIVED`, `ASSUMED` or `UNRESOLVED`.

## Who writes what

| File | Writer (enforced by the write-scope hook) |
|---|---|
| `state.json`, `PROJECT.md` status/parameters/phase log, `PLAN.HUMAN.md`, `EVIDENCE.md`, `REVIEW.HUMAN.md`, `FINDINGS.json`, `returns/`, ADR-000 and the short-form grill ADRs | coordinator |
| `PROJECT.md` body, `GLOSSARY.md`, `CONSUMERS.md`, `planning/discovery.md`, `planning/concepts.md`, `planning/assumptions.md`, `planning/open-questions.md` | discovery |
| `ARCHITECTURE.md`, `INVARIANTS.md`, `decisions/**`, `formal/**`, `planning/architect.md` | architect |
| `DELIVERY_PLAN.md`, `slices/*/SLICE.md`, `planning/planner.md` | planner |
| `slices/<id>/TEST_PLAN.md` (always as `DRAFT`) | verifier |
| The `Status: DRAFT` → `Status: APPROVED` line of `TEST_PLAN.md`, nothing else | code-reviewer |
| `planning/<agent-name>.md`, `slices/<id>/findings/<agent-name>[.test-plan].md` | that reviewer |

The coordinator may also update slice `State:` lines, the slice table in `DELIVERY_PLAN.md`, and
`## Pending human approval` and `## Human change requests` in `SLICE.md`, because it owns state transitions and the
channel to the human.

## Audience banner: the first line of every `.ai/` file

The file name and the first line both say who reads it. Use exactly one of these:

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: <path to *.HUMAN.md | none>.
```

```markdown
> 👤 HUMAN: read this. ~<N> min. Decision needed: <one line>.
```

Only files named `*.HUMAN.md` carry the 👤 banner. They have a hard cap of one screen (~40 lines). Lead with the
decision and the recommendation. Use no tables wider than the screen and no detail that only matters to an agent. If
the human needs it, it is in the file. If they don't, it isn't.

`state.json` and `FINDINGS.json` are JSON and carry no banner.

## `state.json`: machine state (coordinator only)

Read by every hook and by resume. Valid against `contracts/state.schema.json`. Write it only through
`python3 shipyard/scripts/shipyard_state.py` (`init`, `show`, `set-status`, `set-slice`;
`ignore-ai`, `snapshot` and `restore` manage where `.ai/` lives in git), never by hand, so it always validates.

```json
{
  "schemaVersion": "1.0",
  "project": "<name>",
  "status": "INTAKE",
  "featureBranch": "feature/x",
  "baseBranch": "main",
  "protectedBranches": ["main", "master"],
  "activeSlice": null,
  "sliceBranch": null,
  "brainstormBreadth": 1
}
```

- `status` is the `PROJECT.md` status, always the same value.
- `protectedBranches` holds `main`, `master`, the repository's default branch, and any branch the human named at P0.
- `activeSlice` / `sliceBranch` are set before the `shipyard-slice` workflow launches (`"03"`, `"feature/x-slice-03"`) and
  cleared to `null` after the slice merges.
- `notesBranch` is the branch `shipyard_state.py snapshot` commits `.ai/` to (default `<featureBranch>-shipyard`).
- `state.json`, like all of `.ai/`, never enters a work branch: `.ai/` is ignored there through `.git/info/exclude`
  and committed only to the notes branch (`branch-policy.md`), so it stays put while the coordinator switches
  between the slice and feature branches.

## `PLAN.HUMAN.md`: the plan-approval brief (P8)

The coordinator writes this from `ARCHITECTURE.md`, `DELIVERY_PLAN.md`, the assumptions and ADR-000, and presents
the same content in chat. It summarises; it does not restate.

```markdown
> 👤 HUMAN: read this. ~3 min. Decision needed: approve the delivery plan, or change something below.

# <project>: plan approval

**Recommendation:** APPROVE | CHANGE <what>. <one sentence why>

## What we will build                  <= 5 lines, outcomes not mechanics; the chosen concept from ADR-000
## Slices                              one line each: <id> <title>: <why it comes in this order>
## Decisions you are approving         <= 5; each: decision / the alternative rejected / why. Include the seams
                                       the tests will observe each slice through (from `## Seams under test`):
                                       approving the plan approves the seams.
## Properties you are relying on       <= 5 lines, only when C-10 is above none: INV id, one-line meaning, tier
                                       (invariants | property-tested | model-checked, bounded N steps) and status;
                                       a VIOLATED model names the ADR that redesigned it. NONE when C-10 is none.
## Risks you are accepting             <= 5 ASSUMED facts with material risk-if-wrong, unanswered P0 defaults,
                                       planner exception requests, any model NOT_RUN; NONE if none
## Cost so far and expected            one line against C-9
## Questions for you now               only ones that change the plan; NONE if none
```

## `PROJECT.md`

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: <path to *.HUMAN.md | none>.
# Project: <name>
Status: INTAKE | DISCOVERY | PLANNING | AWAITING_PLAN_APPROVAL | IMPLEMENTING | COMPLETE | BLOCKED
Blocked reason: <one line, only while Status is BLOCKED>

## Source material            <what the human supplied, verbatim, with links or paths>
## Problem statement
## Goals
## Non-goals
## Success criteria           <measurable>
## User stories               <numbered; "As <actor>, I want <capability>, so that <benefit>"; drafted by discovery
                               from the request, confirmed or corrected in the P4 grill; extensive beats short>
## Scope
## Delivery parameters        <-- answers to the P0 gate, verbatim, each with an ID
| ID | Parameter | Value | Label |
|----|-----------|-------|-------|
| C-1 | Slice budget | <n, or "no cap stated"> | SPECIFIED / ASSUMED |
| C-2 | New-project budget | | |
| C-3 | Reuse posture | | |
| C-4 | Existing-code blast radius | | |
| C-5 | Tracking artifacts | | |
| C-6 | Time and artifact budget | | |
| C-7 | Convention posture | | |
| C-8 | Feature branch / base branch | feature/x from main | |
| C-9 | Cost budget | | |
| C-10 | Formal rigour | none / invariants / properties / model-checked | |
| BB  | Brainstorm breadth | 0 / 1 / 2 | |
## Stakeholders
## Constraints
## Relevant repositories and services
## Known dependencies
## Key terminology            <one line: "See GLOSSARY.md", which is the source of truth for every project term>
## Framework configuration    <size-check override; protected branches; notes branch; .ai/ ignored via .git/info/exclude (date);
                               lowered compute minimums or waivers; workflow approval mode>
## Phase log
| Date | Phase | Status | What it produced |
```

The coordinator owns `Status`, `Blocked reason`, `## Delivery parameters`, `## Framework configuration` and
`## Phase log`. Discovery drafts the rest.

Delivery parameters are gathered at P0 **before** discovery and outrank agent judgment. A parameter added or changed
later is a scope change: record it as a new row, note which artifacts it invalidated, and say so at the next gate.

Phase labels: P0 `INTAKE` · P1 `DISCOVERY` · P2 `BRAINSTORMING` · P3–P6 `PLANNING` · P7 `DELIVERY_PLANNING` ·
P8 `AWAITING_PLAN_APPROVAL` · P9–P10 `IMPLEMENTING` · done `COMPLETE`. `BLOCKED` replaces any of them on a
fail-closed stop. A dynamic workflow cannot write files, so `Status` only changes between workflows: the coordinator
sets `DISCOVERY` before launching the `shipyard-discover` workflow (P1–P3) and `PLANNING` before the `shipyard-plan` workflow (P5–P7), and
when the workflow returns writes one phase-log row per phase it ran, each row carrying that phase's label.
`BRAINSTORMING` and `DELIVERY_PLANNING` therefore appear in phase-log rows, never as the `Status` line.

## `ARCHITECTURE.md` (architect only)

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: <path to *.HUMAN.md | none>.
## Current state
## Target state
## Major components + responsibilities
## Dependency direction
## Data and control flow
## Contract boundaries
## Concurrency model
## Failure model
## Lifecycle
## Configuration
## Observability
## Security assumptions
## Migration architecture
## Open architectural questions
```

## `INVARIANTS.md` (architect only)

Properties every current and future slice must preserve. Project-specific — the framework hard-codes none.

The first four lines are the minimum (C-10 `none`). At C-10 `invariants` and above every invariant carries the
extended block, so a non-specialist can read what it means, what it prevents and how it is checked:

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: <path to *.HUMAN.md | none>.
### INV-001: <name, a sentence a newcomer understands>
Statement:        <the property, precise and testable; glossary terms only>
Rationale:        <why it must hold>
How to verify:    <test, metric, or review check>
Introduced by:    <slice or ADR>
Plain English:    <what it means for a user or operator, one or two lines>        (C-10 invariants and above)
Why it matters:   <the concrete failure it prevents>
Satisfied by:     <one short sequence of events that keeps it>
Violated by:      <one short sequence of events that breaks it; "none found" is a finding, not an answer>
Check:            tier 0: <table or diagram below> · tier 1: <property test or assertion, file :: name>
                  · tier 2: <.ai/formal/INV-001.qnt, invariant name>                 (only the tiers C-10 selects)
Status:           <per tier: PLANNED | PASS (slice <id>) | VIOLATED (trace in <file>) | NOT_RUN (<reason>)>
Tags:             <concurrency | lifecycle | partial-failure | data | security | none>
```

For anything stateful add, under the block, a state-by-event table (`State | Event | Next state | Side effect |
Allowed?`, one row per reachable pair, forbidden pairs included) and a Mermaid `stateDiagram-v2` of the same
machine. The reliability reviewer reads the table to find missing cells; the verifier copies the "Violated by"
sequence into a failure case. Properties come from the human's words or an accepted ADR (`SPECIFIED` or
`DERIVED`); an `ASSUMED` property can never carry `model-checked` status.

## `GLOSSARY.md` (discovery)

The project's language, in the project's words. Seeded in `DRAFT` from the request and the code, sharpened during
the P4 grill (never batched up: a term settled in a round is written in that round), and read by the architect,
planner, verifier and code-reviewer. Every later artifact uses these terms; `domain-design` reviews code against
them.

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: none.
# Glossary: <project>

### <Term>
<One or two sentences: what it means in this project, free of implementation detail.>
Avoid: <other words the code or the request uses for the same thing>
Source: <the human's words at P4 round <n> | path:line | request>
```

Only project-specific terms: a word a newcomer could look up in a dictionary does not belong here. Be opinionated:
one term per concept, the rest under `Avoid`. A term the human and the code use differently is a `term` gap in the
grill, not a silent choice.

## `CONSUMERS.md`

One block per consumer.

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: <path to *.HUMAN.md | none>.
### <consumer name>
Owner:                      Integration mechanism:
Contract / API used:        Configuration:
Authentication:             Traffic characteristics:
Deployment cadence:         Compatibility requirements:
Operational assumptions:    Migration dependency:
Migration state:            NOT_STARTED | IN_PROGRESS | COMPLETE | NOT_REQUIRED
Testing:                    Rollback considerations:
Notes:
```

## `DELIVERY_PLAN.md` (planner; the coordinator updates slice states)

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: PLAN.HUMAN.md.
Feature branch: <feature/x>   Base branch: <main>   (C-8)
Plan approved: <date, by human in chat | not yet>

## Rollout strategy
## Slices
| ID | Title | State | Depends on | Slice branch | Merge commit |
|----|-------|-------|------------|--------------|--------------|
## Work items                 <omit if C-5 says no tracking artifacts>
Parent + inherited metadata   <fetched and verified; the single source of truth, referenced by each SLICE.md>
| Slice | Work item title | Type | Parent | Shares slice with |
## Human gates                <P8 plan approval, every merge, every SHARED tier>
## Compatibility stages
## Consumer migration order
## Deprecation and removal sequence
## Rollout observability      <how we know migration is complete>
## Rollback strategy
## Completion criteria
## Speculative dependencies   <slices the human allowed to start before a predecessor merged; NONE if none>
## Reconciliation log
| After slice | Architect verdict | Planner verdict | What changed | Action taken |
```

## `planning/concepts.md`: the brainstorm record (discovery)

Written in two passes. Discovery `SCAN` writes the sealed elephant take before any goldfish runs. Discovery
`SYNTHESIZE` appends everything else and never edits the sealed take. With brainstorm breadth 0 the file holds only
the gap list.

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: PLAN.HUMAN.md.
# Concepts: <project>
Brainstorm breadth: 0 | 1 | 2 (C-6, BB)   Lenses run: <technical, value, contrarian, ...>

## Elephant take (sealed)
Sealed: <date>, before any goldfish ran. Never edited after this line.
Concept:      <the elephant's own best concept from full context>
Why:          <the evidence that drives it, with paths>
Builds on:    <existing modules, contracts, conventions>
Risks:
Relative size: S | M | L

## Goldfish ideas (raw)
| Lens | Title | One-line summary | Size |

## Clusters
### K1: <name>
Lenses that proposed it: <technical, contrarian>
Matches the elephant take: YES | PARTLY | NO
Summary:   Fits C-constraints: <C-1 ok, C-2 violates ...>   Repository evidence: <path:line>

## Top 3
| Rank | Concept | Lenses | Fits C-constraints | Main risk | Size |

## Disagreements with the elephant take
- <lens> vs elephant: <what differs> — <why it matters> — <evidence each side cites>

## Open questions             <questions the goldfish raised that the repository cannot answer>

## Gap list
### G1  [BLOCKING | DEFERRABLE]
Question:        Why it matters:
Evidence:        Options:
Recommendation:
```

Gap IDs run `G1..Gn` and match the `gaps[].id` values in the discovery result. `BLOCKING` gaps must be answered at
P4; `DEFERRABLE` gaps are recorded with their recommended default.

## `planning/assumptions.md`

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: <path to *.HUMAN.md | none>.
### ASM-001
Assumption:       Why it is needed:
Evidence:         Risk if wrong:
Owner:            Status: OPEN | CONFIRMED | REFUTED | ACCEPTED
Resolution:
```

## `planning/open-questions.md`

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: <path to *.HUMAN.md | none>.
### Q-001  [BLOCKING_IMPLEMENTATION | DEFERRABLE]   From gap: G<n> | critique finding <id>
Kind:             concept | scope | term | decision | invariant | fact       Depends on: <Q/G ids | none>
Question:         Why it matters:
Evidence so far:  Options:
Recommendation:   <worded so that "yes" accepts it>
Round:            <grill round it was asked in, or SETTLED (from evidence, never asked)>
Answer:           <verbatim human answer, date>
```

`fact` questions are never put to the human: discovery settles them from the repository and records the evidence
in `Answer:` with `SETTLED`.

The planning gate does not require zero open questions. It requires zero **material** unresolved questions — ones that
would make implementation unsafe or cause substantial rework.

## `decisions/ADR-NNN.md`

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: <path to *.HUMAN.md | none>.
# ADR-NNN: <title>
Status: PROPOSED | ACCEPTED | SUPERSEDED by ADR-YYY
Date:   Deciders:

## Context
## Options considered      <with pros and cons>
## Decision
## Consequences            <including what this forecloses>
```

Use an ADR for any decision future agents must not relitigate.

**Short form, for grill answers.** An answer the human gives at P4 becomes an ADR only when all three hold: it is
**hard to reverse**, it would be **surprising without context**, and it is the result of a **real trade-off**.
Otherwise it stays in `open-questions.md`. The short form is enough:

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: PLAN.HUMAN.md.
# ADR-NNN: <title>
Status: ACCEPTED   Date: <date>   Deciders: the human (P4 grill, round <n>, gap G<n>)

<One to three sentences: the context, what was decided, and why.>
Their words: "<the human's answer, verbatim>"
Forecloses: <what is now off the table; one line>
```

The coordinator writes it in the round the answer arrives, numbered from ADR-001 upward (ADR-000 stays the scope
record). The architect's four-section form stays for architecture decisions.

**ADR-000 Scope** is written by the coordinator at P4 from the human's concept pick. Context: the top 3 from
`concepts.md`. Options considered: each of them, plus "much smaller or nothing" when the contrarian lens raised it.
Decision: the human's pick, quoted verbatim. Consequences: what is now out of scope. Status `ACCEPTED`, Deciders:
the human. Every later phase treats it as a human decision (source-of-truth rank 1).

## `slices/<id>/SLICE.md` (planner)

The hooks parse `## Expected touch set — code`, `## Expected touch set — tests` and `## Branch`. Use these headings
exactly (em dash; a plain `-` is also accepted) and one repo-relative glob per line as `- path/glob`. `**` is allowed.
The two touch sets must not overlap.

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: REVIEW.HUMAN.md.
# Slice <id>: <title>
State: PROPOSED | APPROVED | TEST_PLANNING | IMPLEMENTING | VERIFYING | AGENT_REVIEW |
       CHANGES_REQUESTED | READY_FOR_HUMAN | HUMAN_REVIEW | MERGED
Revision round: N of 3

## Branch
feature/x-slice-03

## Objective
## Motivation                 <why now, why this order>
## Prerequisites              <slice IDs that must be MERGED first; NONE if none>
## Scope
## Non-goals
## Affected components
## Expected touch set — code
- src/cache/**
- src/config/cache.ts
## Expected touch set — tests
- tests/cache/**
## Affected consumers
## Contract changes           NONE if none
## Architecture constraints   <invariants this slice must preserve, each as "INV-nnn (tier: invariants | properties |
                              model-checked)" from INVARIANTS.md; NONE if none>
## Seams under test           <the public interface each AC is observed through: a module boundary, an HTTP or RPC
                              endpoint, a CLI, a message topic. Existing seams first; the highest seam that can
                              observe the behaviour; ideally one. The verifier plans tests only at these seams;
                              the human approves them at P8 as part of the plan>
## Prior art                  <existing tests in the repository that exercise the same seams, as path:: name; NONE
                              if none. The verifier follows their layout and helpers>
## Acceptance criteria
- [ ] AC-1: <specific and verifiable>
## Test expectations          <levels and risks the test plan must cover; the verifier turns this into TEST_PLAN.md>
## Validation tiers           <from discovery.md; simplest tier that fully tests the change. Per tier: LOCAL|SHARED /
                              which ACs / for any tier above the cheapest, what the lower tier cannot exercise>
## How this is verified       <planned canonical command(s); the planner proves each runs on this repository.
                              Results go to EVIDENCE.md, not here>
## Pending human approval     <NONE, or per SHARED tier: tier / environment / requested date /
                              outcome PENDING | APPROVED | DENIED. Written by the coordinator before asking.>
## Human change requests      <NONE, or H1, H2, ...: date / the human's words verbatim / ACs changed (planner) or
                              "no AC change". Written by the coordinator at HUMAN_REVIEW; read by every author.>
## Work item                  <omit if C-5 says no tracking artifacts>
Title:            <plain-English imperative — not the commit or merge title>
Type:             <constrained by the parent's type in most trackers — read it>
Parent:           <the single project-wide tracking parent; no per-slice parent layer>
Description:      <3-6 sentences for a teammate who has read neither the spec nor .ai/>
Criteria:         <the externally meaningful subset of the AC list; one to three items, flat>
## Expected review routing    <the triggers the planner expects to fire; the slice workflow recomputes routing from
                              the verifier's routingFacts and records the real set in EVIDENCE.md>
## Rollout impact
## Rollback
## Known risks
## Acceptance criteria NOT verifiable here   <with what is checked instead>
## Next-slice dependency
```

Two titles, never interchangeable: the **merge title** (`Merge slice <id>: <title>`) and the **work item title**
(plain English for a backlog). Label both explicitly so neither is pasted into the wrong system.

## `slices/<id>/TEST_PLAN.md` (verifier writes; code-reviewer approves)

The status line is a line that is exactly `Status: DRAFT` or `Status: APPROVED`, within the first 10 lines. The
verifier always writes `Status: DRAFT`. Only the code-reviewer changes it, with one Edit (old `Status: DRAFT`, new
`Status: APPROVED`). The test-plan-gate hook reads this line. See `test-plan.md`.

```markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: REVIEW.HUMAN.md.
Status: DRAFT
# Test plan: Slice <id> <title>
Revision: <0 | 1 | 2> of 2    Derived from: SLICE.md acceptance criteria (not from any implementation)

## AC → planned tests
| AC | Planned test (file :: name) | Level | What it proves |
|----|-----------------------------|-------|----------------|
| AC-1 | tests/cache/ttl.test.ts :: expires after ttl | unit | entry is gone after ttl, present before |

## Seams under test           <copied from SLICE.md; every planned test sits at one of these. A test that needs
                              another seam is a question for the planner, not a test>
## Levels                     <why each AC is tested at the level chosen: unit | integration | e2e | benchmark | tier>
## Failure, edge and boundary cases   <one line each, mapped to an AC>
## Benchmarks                 <for every performance AC: what is measured, baseline, threshold, command; NONE if none>
## Invariants exercised
| INV | Tier | Test (file :: name) | Would fail against a no-op stub? |
|-----|------|---------------------|----------------------------------|
| INV-002 | properties | tests/cache/isolation_test.py :: never_returns_another_tenants_entry | yes: stub returns the first entry |
## Test doubles               <each fake and the system boundary it stands in for (external API, clock, randomness,
                              file system); never an internal collaborator; NONE if none>
## ACs not verifiable here    <AC / why / what is checked instead; NONE if none>
## Validation tiers           <name / LOCAL | SHARED / ACs / why needed>
## Deliberately not tested    <e.g. guaranteed by the type system; NONE if none>
## Commands                   <canonical suite command; narrowest command per test file>
```

## `slices/<id>/REVIEW.HUMAN.md`: the merge brief (coordinator)

The human reads top-down and stops early, so the decision comes first and the file stops at one screen
(**≤ 40 lines, hard cap**). The coordinator presents the same content in chat.

```markdown
> 👤 HUMAN: read this. ~2 min. Decision needed: merge slice <id> into <feature branch>, or request changes.

# Slice <id>: <title>

**Recommendation:** MERGE | REQUEST_CHANGES. <one sentence why>

## Check these                       max 3; each: <file or decision> - <the question to ask about it>
1.

## What changes                      <= 3 lines; behaviour, contract, or consumer changes; NONE if none
## Risks you are accepting           open MAJOR/MINOR findings carried to you, acceptance criteria NOT verified,
                                     tiers NOT_RUN, reviewers SKIPPED_BY_HUMAN, material ASSUMED facts; NONE if
                                     none. Never omit unverified criteria.
## Evidence                          one line: build PASS, tests PASS (n run), criteria verified n/m,
                                     invariants n/m exercised (k model-checked, bounded N steps) when C-10 is
                                     above none, reviewers <names>, findings fixed n / rebutted n,
                                     rounds n of 3, commit <short sha>. Full record: EVIDENCE.md
```

Point the human at architectural and semantic risk. Never ask for line-by-line review of mechanical code; that is
exactly the attention this framework exists to reclaim. To review the code itself the human runs
`git diff <feature-branch>...<slice-branch>` — say so in one line in chat, not in the file.

## `slices/<id>/EVIDENCE.md`: the full record behind the brief (coordinator)

Written from the the `shipyard-slice` workflow result. The machine block at the end is that result, verbatim, and must pass
`python3 shipyard/scripts/shipyard_validate.py slice-workflow-result -`.

````markdown
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: REVIEW.HUMAN.md.

# Evidence: Slice <id>
Evidence commit: <full sha of the slice branch HEAD that was verified and reviewed>
Feature branch: <name> at <sha when the slice branch was cut>   Slice branch: <name>

## Purpose and why now
## Behaviour changes
## Public contract changes      NONE if none
## Architecture changes         NONE if none
## New abstractions             <each with its justification>
## Consumers affected           NONE if none
## Compatibility impact
## Rollout impact

## Test plan
Status: APPROVED by code-reviewer after <n> revision(s)   ACs covered: n/m   Not verifiable here: <list | NONE>

## Agent review
| Reviewer | Routed because | BLOCKING | MAJOR | MINOR | NOTE | Findings file |
Reviewers not routed: <role + why not, for every role in registry.routing.slice>

## Findings
Fixed: n   Rebutted (accepted by reviewer): n   Carried to the human: n   Full list: FINDINGS.json

## Verification
Scope check:        IN_SCOPE | DRIFT   <out-of-set paths and undeclared contract changes>
Build:              PASS | FAIL
Static analysis:    PASS | FAIL | NOT_APPLICABLE
Unit tests:         PASS | FAIL   (run: N, failures: N)
Integration tests:  PASS | FAIL | NOT_APPLICABLE
Validation tiers:   <each planned tier: PASS | FAIL | NOT_RUN | AWAITING_APPROVAL + why>
Formal (C-10):      <tier; INV ids checked; INV ids NOT_RUN with reason; "none" when C-10 is none>
Command used:       <exact command, duration>
New tests added:
Acceptance criteria verified:
Acceptance criteria NOT verified:      <-- never omit this
Failure scenarios exercised:
Confidence: HIGH | MEDIUM | LOW   Reason:

## Capability skills used
| Skill | Version | Used by |
<from the result's abilityVersions; a reviewer that reported none is listed as "not reported">

## Revision rounds used: N of 3   Workflow launches: N   Human change requests: N (not counted toward the cap)
## Known risks
## Expected next slice
## Diff summary                 <git diff --stat <feature>...<slice>, trimmed>

## Machine record
```json
{ "slice": "03", "status": "READY_FOR_HUMAN", "rounds": 1, "...": "the slice-workflow-result object, verbatim" }
```
````

## `slices/<id>/FINDINGS.json` (coordinator)

The merged, deduplicated `findings` array from the last the `shipyard-slice` workflow result, written verbatim: a JSON array of
objects, each valid against `contracts/finding.schema.json`. It replaces the previous run's file. It is the record
a resumed session and P10 read; the per-reviewer `findings/` files are working copies.

## `.ai/returns/` (coordinator)

One file per direct Agent call: `<phase>-<agent-name>-<mode>[-<slice>].json`, holding the call's fenced ```json
block, validated with `shipyard_validate.py <contract-stem> <file>`. Kept for audit and resume.

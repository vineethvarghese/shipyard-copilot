---
name: integration-review
description: >
  Ecosystem-fit review method for the Shipyard integration-reviewer. Load it in PLAN mode to judge planned consumer
  impact, migration order and rollout, and in SLICE and RECHECK mode when a slice changes consumer-visible
  behaviour, a public contract, configuration, onboarding, rollout or deployment assumptions. Gives the consumer
  inventory checks (including searching for unlisted consumers and cadence mismatches), the onboarding analysis,
  and the rollout and migration analysis (coexistence, independent migration, staged rollout, rollback after
  partial migration, a measurable completion signal). Not for API shape (contract-review) or concurrency
  (reliability-review).
---

# Integration review

Version 1.0.0 · used by integration-review (`shipyard-integration-reviewer`, PLAN, SLICE and RECHECK)

The contract reviewer asks *is this API well designed?* You ask **what happens to everyone who has to consume,
operate, migrate to, or onboard onto it?** A service is not finished because its main code path works. Finding a
consumer problem in the plan is far cheaper than finding it after release, so your PLAN review matters most.

## Inputs

Read `.ai/CONSUMERS.md` and `.ai/DELIVERY_PLAN.md` (if it exists) first, then:

- **SLICE / RECHECK:** the raw `SLICE.md` and the raw diff.
- **PLAN:** `.ai/PROJECT.md`, `.ai/ARCHITECTURE.md`, `.ai/INVARIANTS.md`, and `SLICE.md` drafts.

If `.ai/CONSUMERS.md` does not exist and consumers plainly do (imports, clients, published packages, queues, shared
tables), that is a `BLOCKING` planning gap. Do not review as though there are none.

## Rules

1. **Never assume the consumer inventory is complete.** Search the repository for call sites: imports of the
   changed module, HTTP routes and client calls, queue or topic names, table names, config keys, CLI flags, exported
   package names. If the wider organization is searchable from here, search it too. An unlisted consumer is the most
   expensive kind; each one you find is a finding.
2. **"Consumers will adapt" is not a migration strategy.** It is the absence of one.
3. Stay inside your jurisdiction (below). Attach evidence to every finding.

## Consumer analysis

For each consumer, check that the inventory records: owner; integration mechanism; contract or API used;
configuration; authentication; traffic characteristics; deployment cadence; compatibility requirements; operational
assumptions; migration dependency; migration state; test strategy; rollback considerations.

**Flag every consumer whose deployment cadence is slower than the rollout assumes.** That is the most common way a
staged migration silently stalls: the plan removes the old path after two weeks; a consumer releases quarterly.

## Onboarding analysis

- Can a new consumer use this without reading the implementation?
- Is required configuration discoverable, and are defaults safe?
- Is local development documented? Is test integration straightforward (a fake, a fixture, a sandbox mode)?
- Are expected failure modes documented?
- Are metrics and logs enough for a **consumer** to diagnose its own failures?
- Is ownership and support clear?

## Rollout and migration analysis

- Is the new behaviour transparent, or opt-in?
- Can old and new coexist? For how long?
- Can consumers migrate **independently** of each other?
- Can rollout be staged, and can it be rolled back **after partial migration** (some consumers moved, data written
  in the new format)?
- **How do we know migration is complete?** Name the metric, log query or count. "We'll check" is not an answer.
- Is legacy removal gated on measured evidence of zero use, not on elapsed time?
- Are any consumers on a different release cadence, or outside this repository's control?

Report in the return block's `extras`: `consumersAffected`, `unlistedConsumers`, `migrationSignal` (the metric, or
`NONE DEFINED`), `rollback` (`YES | NO | PARTIAL`).

Category is `integration/<topic>`: `unlisted-consumer`, `cadence-mismatch`, `no-coexistence`, `no-completion-signal`,
`rollback`, `onboarding`, `config-discoverability`, `consumer-diagnostics`, `inventory-gap`.

## Severity calibration

- `BLOCKING`: a consumer breaks or is stranded with no coexistence path; an unlisted consumer of a changed contract;
  no rollback after partial migration where data changes shape; `CONSUMERS.md` missing when consumers exist.
- `MAJOR`: no measurable completion signal; legacy removal gated on time only; a cadence mismatch that stalls the
  plan; required configuration with an unsafe default.
- `MINOR`: onboarding documentation gaps; consumer diagnostics that are weak but workable.
- `NOTE`: improvements to the inventory with no current risk.

## Finding examples

GOOD (consumer found by search, cadence evidence, minimum fix):

```text
ID: integration-001
Severity: BLOCKING
Category: integration/unlisted-consumer
Location: src/reports/export.py:12-30
Finding: The slice removes the `/v1/export` route, but tools/nightly_sync.sh still calls it and is not in
  CONSUMERS.md.
Why it matters: The nightly sync, run by the data team's scheduler, will fail on the first night after merge and
  nobody owning it has been told; rollback after the v1 data files are deleted is not possible.
Evidence: `grep -rn "/v1/export" .` -> tools/nightly_sync.sh:8 `curl -fsS "$BASE/v1/export?day=$D"`; CONSUMERS.md
  lists only the web dashboard.
Required resolution: Keep `/v1/export` in this slice; add nightly_sync to CONSUMERS.md with owner and cadence; plan
  its migration and remove v1 only when the access log shows zero calls for a full cycle.
Confidence: HIGH
Owner: planner
Status: OPEN
```

BAD (generic worry, no consumer, no signal):

```text
ID: integration-004
Severity: MAJOR
Category: integration
Location: whole slice
Finding: Consumers might be affected by this change.
Why it matters: We should be careful with consumers.
Evidence: None.
Required resolution: Communicate with consumers.
Confidence: LOW
Owner: implementer
Status: OPEN
```

What is wrong with it: no consumer is named, nothing was searched, there is no evidence, and the resolution is not a
change anyone can make.

## Out of jurisdiction

- API shape, DTOs, serialization and compatibility class → contract-review.
- Concurrency, retries, timeouts and shutdown behaviour → reliability-review.
- Whether the feature should exist → simplicity-review.
- Contacting consumer owners: never. The coordinator raises human questions.

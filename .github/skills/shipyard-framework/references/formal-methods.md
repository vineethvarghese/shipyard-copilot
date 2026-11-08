# Formal rigour (C-10): what each tier asks of each role

C-10 is a P0 delivery parameter: `none` (default), `invariants`, `properties` or `model-checked`. It is opt-in and
cumulative: each tier includes the ones below it. The human-facing explanation is `docs/formal-methods.md`; this
file is the contract between roles.

## Why tiers

Every reliable result from model-generated specifications has a **checker in the loop**: a property test that runs,
a model checker that explores, a planted fault that fails. A specification that is only written and read back is a
story. And the weak point is never the syntax; it is the **strength of the property**: a property that a do-nothing
implementation satisfies proves nothing. The tiers exist so a project pays for exactly the checking it needs, and so
every claim carries its evidence kind: `tested`, `property-tested`, `model-checked (bounded, N steps)`. Never
"verified" or "proved".

## The tiers

| Tier | Artifact | Who writes | Who checks | Tooling |
|---|---|---|---|---|
| `none` | `INVARIANTS.md` four-line blocks | architect | reviewers by reading | none |
| `invariants` | The extended block for every invariant (plain English, why it matters, satisfied by, violated by, check, status, tags); a state-by-event table and a Mermaid `stateDiagram-v2` for anything stateful | architect `DRAFT` | reliability reviewer `PLAN` hunts missing cells and reachable `Violated by:` sequences; the verifier copies them into failure cases | none |
| `properties` | A property-based test (the repository's library, per `lang-packs`) or a runtime assertion plus a test that it fires, for every invariant whose `Check:` says `property` | verifier `TEST_PLAN` plans it in `## Invariants exercised`; `WRITE_TESTS` writes it; the implementer adds assertions in the code touch set | code-reviewer `TEST_PLAN` asks "which violating implementation does it fail against?"; `VERIFY` reports `formal.checked` | one dev dependency the repository already has or C-7 allows |
| `model-checked` | A small model per concurrency, lifecycle or partial-failure invariant at `.ai/formal/INV-nnn.qnt`, with a sibling `INV-nnn.fault.qnt` holding a planted fault | architect `DRAFT` | reliability reviewer `PLAN` runs both with `scripts/formal_check.py` and renders any trace; the verifier may add a trace-replay or property test so the model stays linked to the code | `quint` (and `java` for `--verify`), user-installed, discovered at P1, never installed by Shipyard |

Only invariants tagged `concurrency`, `lifecycle` or `partial-failure` get a model. A model of a create-read-update
flow is cost without signal; the simplicity reviewer may file against it.

## The model shape (model-checked)

```quint
// .ai/formal/INV-003.qnt
// Covers: src/jobs/worker.go, src/jobs/queue.go    Confirmed-at: <commit>    ADR: ADR-003
module inv003 {
  type Status = Pending | Leased | Done
  var status: Status
  var applied: int
  var ackPending: bool

  action init = all { status' = Pending, applied' = 0, ackPending' = false }
  action lease   = all { status == Pending, status' = Leased, applied' = applied, ackPending' = false }
  action execute = all { status == Leased, not(ackPending), applied' = applied + 1, ackPending' = true, status' = status }
  action ack     = all { ackPending, status' = Done, ackPending' = false, applied' = applied }
  action crash   = all { status == Leased, status' = Pending, ackPending' = false, applied' = applied }
  action step = any { lease, execute, ack, crash }

  val executeAtMostOnce = applied <= 1          // INV-003
}
```

`INV-003.fault.qnt` is the same module with one deliberate break (for example `execute` without `not(ackPending)`)
and a top comment `// PLANTED FAULT: <what was broken>`. The header comment's `Covers:` paths let P10 `REVALIDATE`
mark the model `possibly stale` when those paths change.

## Running it (reliability reviewer, PLAN mode)

```bash
python3 shipyard/scripts/formal_check.py tools
python3 shipyard/scripts/formal_check.py run .ai/formal/INV-003.qnt --invariant executeAtMostOnce \
    --max-steps 20 --timeout 300 --verify --backend tlc --out .ai/formal/INV-003.trace.itf.json
python3 shipyard/scripts/formal_check.py run .ai/formal/INV-003.fault.qnt --invariant executeAtMostOnce \
    --verify --backend tlc --expect VIOLATED
```

The script prints one JSON object and writes it to `.ai/formal/INV-003.result.json`: `status` (`PASS`, `VIOLATED`,
`NOT_RUN`, `ERROR`, `UNEXPECTED`), `checker`, `evidence` (`simulated (random, N steps)` without `--verify`,
`model-checked (bounded, N steps)` with it), `modelSha256`, `steps`, and `markdown` (the trace as a step table with
changed values in bold). The verifier reads the result file at VERIFY and compares the sha with the model as it is
then. The reviewer writes two or three plain sentences that tell the trace's story in glossary terms, then the
table, into its findings file; the human reads the sentences.

| Result | Meaning | Finding |
|---|---|---|
| `PASS` with `verified: true` | No violation within the bound | None; `Status:` in `INVARIANTS.md` becomes `model-checked (bounded, N steps)` |
| `PASS` with `evidence: simulated` | Random simulation only; the checker did not run | Reported as `NOT_RUN (simulation only)` with why `--verify` could not run |
| `ERROR` | The tooling failed and showed nothing | Recorded as `NOT_RUN (checker error)`; never read as a violation, even on the fault model |
| `VIOLATED` on the real model | The invariant as stated cannot hold in the planned design | Six-part reliability finding, owner `architect`, trace as evidence; usually a restated invariant plus the smallest mechanism |
| `UNEXPECTED` on the fault model | The planted fault did not fail: the model is too weak to prove anything | Finding "model too weak", owner `architect` |
| `NOT_RUN` | Tooling missing or timed out | Not a finding. Recorded as `NOT_RUN (<reason>)`; the coordinator lists it under risks at P8 and at the merge gate |

## What the human sees

- P4: an `invariant` question is how the human states a property in their own words; that wording is the
  property's provenance (`SPECIFIED`). An `ASSUMED` property can never be reported as model-checked.
- P8: `PLAN.HUMAN.md ## Properties you are relying on`, at most five lines: INV id, meaning, tier, status, any
  `NOT_RUN`. The human approves properties, not models.
- Merge gate: `REVIEW.HUMAN.md ## Evidence` carries `invariants n/m exercised (k model-checked, bounded N steps)`;
  any `NOT_RUN` or a model "written with the code" (the same request wrote model and implementation) goes under
  risks.

## Drift

A model describes the design at P3. By slice four the code may differ. Three things keep the link honest: the
model's `Covers:` and `Confirmed-at:` header (P10 `REVALIDATE` marks it `possibly stale` when a covered path
changed), the tier-1 property tests that live in the normal suite, and an optional trace-replay test the verifier
writes from the ITF file. A model nobody re-ran after the code changed is reported as `NOT_RUN (stale)`, never as
`PASS`.

---
name: reliability-review
description: >
  Adversarial failure review method for the Shipyard reliability-reviewer. Load it in PLAN mode to judge a planned
  concurrency, failure and lifecycle model, and in SLICE and RECHECK mode when a slice touches async code,
  concurrency, synchronization, retries, timeouts, cancellation, networking, streaming, resource lifetime, shared
  mutable state or deployment lifecycle. Gives the six-part finding discipline (failure scenario, plausibility,
  impact, current behaviour, why insufficient, minimum correction), the probes, the THEORETICAL severity cap, and
  the model-checked invariant procedure (run the models under .ai/formal/ with scripts/formal_check.py, require the
  planted fault to fail, render a counterexample trace as a plain-English scenario). Not for API shape, consumer
  migration, or steady-state speed (performance).
---

# Reliability review

Version 1.1.0 · used by reliability-review (`shipyard-reliability-reviewer`, PLAN, SLICE and RECHECK)

Assume the happy path works. Your job is to find **how this fails in production**, and to propose the smallest
mechanism that stops it. A reliability review that adds a circuit breaker for an event that cannot happen has made
the system worse; honesty about plausibility is what keeps this review useful.

## Inputs

Read `.ai/INVARIANTS.md` first for the resource and ordering guarantees the system claims, then:

- **SLICE / RECHECK:** the raw `SLICE.md` and the raw diff.
- **PLAN:** `.ai/PROJECT.md`, `.ai/ARCHITECTURE.md`, `.ai/CONSUMERS.md`, and drafts of `.ai/DELIVERY_PLAN.md` and
  `SLICE.md`. Judge the planned concurrency, failure and lifecycle model.

If the diff's concurrency behaviour depends on code you were not given, say so and name what you need. Do not
speculate.

## Jurisdiction

Async behaviour; concurrency; synchronization; cancellation; networking; retry; timeout; lifecycle; resource
ownership; partial failure; backpressure; bounded resource use; dependency degradation; process shutdown;
deployment termination; race conditions; memory pressure; connection pressure.

## Six-part finding discipline

Every finding states all six, in this order, mapped onto the shared finding fields:

| Part | Goes in | Content |
|---|---|---|
| Failure scenario | `Finding:` (first) | The specific sequence of events, step by step. |
| Why insufficient | `Finding:` (after the scenario) | The gap between what the code does and what the scenario needs. |
| Plausibility | `Why it matters:` (first) | `LIKELY`, `POSSIBLE` or `THEORETICAL`, plus why. |
| Impact | `Why it matters:` | What a user or operator experiences. |
| Current behaviour | `Evidence:` | What the code does today, with `path:line`. |
| Minimum correction | `Required resolution:` | The smallest mechanism that closes the gap. |

No scenario, no finding. Plausibility guide:

- `LIKELY`: happens in normal operation at the stated load, or on every deploy, timeout or restart.
- `POSSIBLE`: needs an ordinary but less common event: a slow dependency, a retry, two users at once, a redeploy
  mid-request.
- `THEORETICAL`: needs an unusual combination of events or an environment the system does not run in.

**`THEORETICAL` findings are capped at `MINOR`** unless the impact is data loss or crossing a security boundary.
This cap is the main defence against reliability review turning into architecture astronomy.

## Probes

Category is `reliability/<probe>`.

| Probe | Ask |
|---|---|
| `cancellation` | Is cancellation propagated, or dropped at a boundary? What happens to work already in flight? Who observes a cancelled operation, and does a partly committed response leave a consumer in an unknown state? |
| `timeout` | Who owns each timeout? Do nested timeouts compose, or does an inner one exceed its outer bound? Is there any timeout at all on each remote call? |
| `retry` | Are retries bounded, with backoff and jitter? Is the operation idempotent? Do retries stack across layers (client, SDK, proxy) and multiply load? |
| `concurrency` | What shared mutable state exists? Where is the real synchronization boundary? Can two callers interleave into an invalid state (check-then-act, read-modify-write)? |
| `resource-bounds` | Are queues, buffers, pools and concurrency bounded? At the bound, does the code block, drop or grow? Who is told? |
| `partial-failure` | What if a dependency gets slow instead of failing? Slow is harder than down: threads and connections pile up. |
| `lifecycle` | What happens on shutdown mid-request, eviction or redeploy? Is in-flight work drained, handed off or lost? Are resources closed on every path, including errors? |
| `backpressure` | When the consumer is slower than the producer, what gives, and is that choice deliberate? |

Report in the return block's `extras`: `plausibility` (`{LIKELY: n, POSSIBLE: n, THEORETICAL: n}`) and
`unboundedResources` (list, or `[]`).

## Invariants as input, at every tier

`INVARIANTS.md` is your first read. At C-10 `invariants` and above every invariant has a `Violated by:` sequence and,
when stateful, a state-by-event table: look for the **missing cells** (a state and event pair with no row is a
scenario nobody wrote down) and for a `Violated by:` that is reachable in the planned design. Either is a finding
with the six parts; the table row or the missing cell is its evidence.

## Model-checked invariants (C-10 `model-checked`, PLAN mode)

When the plan brief says the tier is `model-checked`, the architect has written one small model per concurrency,
lifecycle or partial-failure invariant to `.ai/formal/INV-nnn.qnt`, each with a **planted fault**: a deliberately
broken action, marked in a comment, that must make the checker fail. You run the models; you never write them.

1. Run each model with the plugin's script, which finds the tooling, caps the run and renders the trace:

   ```bash
   python3 shipyard/scripts/formal_check.py run .ai/formal/INV-003.qnt --invariant executeAtMostOnce \
       --out .ai/formal/INV-003.trace.itf.json --timeout 300
   ```

   It prints a JSON summary (`status`: `PASS`, `VIOLATED`, `NOT_RUN`, `ERROR` or `UNEXPECTED`; the checker and
   bound; `steps`; `markdown`, the trace rendered as a step table). Then run the sibling planted-fault model with
   `--expect VIOLATED` (`.ai/formal/INV-003.fault.qnt`): that run must come back `VIOLATED`, or the script reports
   `UNEXPECTED`. Never install tooling (the readonly-bash hook stops you anyway): a `NOT_RUN`
   with its reason is a correct result, and the coordinator carries it to the human as a risk.
2. A **`VIOLATED` run** is a finding with the six parts: the trace is the failure scenario (paste the rendered step
   table into `Evidence:`), plausibility from the events the trace needs, impact from the invariant's
   `Why it matters:`, and the minimum correction is usually a restated invariant plus the smallest mechanism
   (an idempotency key, a bound, a fence), owner `architect`. Precede the table with two or three plain sentences
   that tell the story of the trace in glossary terms; the human reads those, not the table.
3. A **planted fault that passes** is a finding ("model too weak to fail", owner `architect`): the invariant or the
   model is vacuous and proves nothing.
4. A **`PASS`** is bounded evidence, never a proof. Say `model-checked (bounded, N steps)` and name the bound.
5. **Never add machinery because a model could be written for it.** Tier 2 is for the invariants the reliability
   probes already tag; a checked model of a create-read-update flow is cost without signal, and the simplicity
   reviewer may file against it.

## Minimum correction, not maximum machinery

Prefer, in order: removing the hazard (make the operation idempotent, drop the shared state), a bound or timeout on
the existing call, a small local mechanism (a bounded channel, a lock around the check-then-act, `finally`/`defer`
cleanup), and only then new machinery (circuit breaker, queue, outbox). Name why each cheaper option is not enough
before proposing the next.

## Severity calibration

- `BLOCKING`: `LIKELY` or `POSSIBLE` scenario with data loss, corruption, duplicated side effects (double charge),
  deadlock, unbounded growth that takes the process down, or a violated invariant.
- `MAJOR`: `LIKELY` or `POSSIBLE` scenario with user-visible errors or degraded service that recovers on its own;
  missing timeout on a remote call in a request path.
- `MINOR`: `THEORETICAL` scenarios (cap), or `POSSIBLE` with minor impact.
- `NOTE`: hardening ideas with no concrete scenario.

## Finding examples

GOOD (six parts, plausibility honest, minimum correction):

```text
ID: reliability-001
Severity: BLOCKING
Category: reliability/retry
Location: src/payments/client.rs:40-58
Finding: Failure scenario: the payment provider accepts POST /charges, then the response is lost to a connection
  reset; the loop at lines 44-55 retries the POST up to 5 times, creating up to 5 charges. Why insufficient: the
  request carries no idempotency key and the retry treats every IO error as safe to repeat.
Why it matters: Plausibility: POSSIBLE — connection resets after the server commits happen during provider deploys
  and network blips. Impact: customers are charged more than once; support must refund by hand.
Evidence: Current behaviour: client.rs:46 `loop { match http.post(url).json(&req).send().await { Err(_) if n < 5 =>
  { n += 1; continue } ... } }`; no Idempotency-Key header is set anywhere in src/payments/.
Required resolution: Minimum correction: generate one idempotency key per charge before the loop and send it on every
  attempt (the provider deduplicates by it); retry only on connect errors and 5xx, with capped backoff.
Confidence: HIGH
Owner: implementer
Status: OPEN
```

BAD (no scenario, theoretical, heavy machinery, inflated):

```text
ID: reliability-006
Severity: BLOCKING
Category: reliability
Location: src/report/job.java
Finding: This could fail under load.
Why it matters: Distributed systems are unreliable.
Evidence: None.
Required resolution: Add a circuit breaker, a dead-letter queue and a saga coordinator.
Confidence: LOW
Owner: implementer
Status: OPEN
```

What is wrong with it: no failure sequence, no plausibility, no current behaviour, and three new subsystems
proposed for a risk nobody has described.

## Out of jurisdiction

- API shape and visible error contracts → contract-review.
- Consumer migration and rollout → integration-review.
- Steady-state speed and cost on hot paths → `performance` (you use it for resource reasoning; behaviour at and
  beyond the bound is yours).
- Security boundaries under attack → security-review.
- Writing or editing a model under `.ai/formal/` → the architect. You run and interpret; you file findings.

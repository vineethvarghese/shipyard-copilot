---
name: performance
description: >
  Performance review method for Shipyard code review. The code-reviewer loads it in SLICE and RECHECK mode to judge
  the runtime cost a change adds (hot-path latency, algorithmic complexity, allocation and copying in loops, N+1
  IO, locks held across IO, blocking calls on async paths, unbounded caches and queues, serialization cost) and in
  TEST_PLAN mode to check that performance acceptance criteria have benchmarks. The reliability-reviewer loads it
  for resource-bound reasoning. Uses resource-by-resource utilization, saturation and errors thinking and workload
  characterization. Every finding states its workload assumption and the measurement that would settle it. Not
  for behaviour under failure or overload (reliability-review) or readability (code-clarity).
---

# Performance

Version 1.0.0 · used by code-review (`shipyard-code-reviewer`), reliability-review (`shipyard-reliability-reviewer`)

Performance review on a diff is reasoning about cost before anyone has measured it. That is useful only when it is
honest about what it does not know. Your job is to find the cost **this change adds** on a path that matters, say
under what workload it matters, and name the cheapest measurement that would prove or disprove it.

The method below paraphrases ideas from Brendan Gregg, *Systems Performance* (the USE method, workload
characterization, latency analysis, and the chapter on methodologies and anti-methods), adapted from live-system
analysis to code review. Cite the book by topic when it helps; repository evidence always outranks a citation.

## How to review

1. **Characterize the workload first.** Read `SLICE.md`, `.ai/PROJECT.md` and `.ai/ARCHITECTURE.md` for scale facts:
   who calls this, how often, with how much data, under what latency target. Write down the answers you found and
   the ones you had to assume. Typical questions:
   - Who or what calls this path? A user request, a batch job, startup, an admin tool?
   - How often? Per request, per item, per minute, once per deploy?
   - How big is the input: typical and worst case? Is it bounded by anything?
   - Is there a stated target (p99 latency, throughput, memory ceiling) in an acceptance criterion?
2. **Find the hot paths in the diff.** A hot path is code that runs per request, per item or per message at the
   stated workload. Code that runs once at startup or in a nightly job of bounded size is cold; treat it as cold
   unless a requirement says otherwise.
3. **Walk the resources the change consumes** (table below). For each, ask the three USE questions.
4. **Run the code-level checks** on the hot paths.
5. For each candidate, write the **workload assumption** and the **settling measurement** before you choose a
   severity. If you cannot state a workload under which it matters, it is not a finding.

## USE thinking, per resource

For every resource the change touches, ask:

- **Utilization:** how much of it does this change use per operation, and how does that grow with input size?
- **Saturation:** can work queue up waiting for it (a pool, a lock, a single thread, a bounded channel)? What waits,
  and for how long?
- **Errors:** what does the code do when the resource is exhausted or returns an error? (If the question is
  correctness under failure, hand it to reliability-review by name.)

| Resource | What to look for in a diff |
|---|---|
| CPU | Nested loops over growing data, repeated parsing or regex compilation, hashing or sorting inside loops, busy waiting. |
| Memory | Loading whole files or result sets, copies of large buffers, per-item allocation in tight loops, caches with no bound or eviction. |
| Disk / IO | Many small reads or writes instead of one batched one, sync flush per item, reading the same file repeatedly. |
| Network | One round trip per item (N+1), chatty protocols, large payloads where a projection would do, no connection reuse. |
| Locks | A lock held across IO or a remote call, a global lock on a per-request path, lock order that serializes independent work. |
| Pools | Connections or threads taken and held for long work, pool size smaller than the concurrency the path implies. |
| Queues | Producers with no bound, consumers that cannot keep up at the stated rate, queues that grow with input. |

## Code-level checks

Category is `performance/<check-id>`.

| Check id | Look for | Evidence to give |
|---|---|---|
| `hot-path-latency` | New work added to a per-request path: extra remote call, extra serialization, synchronous logging of large objects. | The path from entry point to the new work, and the per-call cost (one round trip, one parse). |
| `algorithmic-complexity` | Quadratic or worse work over input that can grow: `list.contains` inside a loop, repeated linear search, sort inside a loop. | The loop nesting, the input that grows, and the size at which it hurts. |
| `allocation-in-loop` | Building strings by repeated concatenation, creating objects or buffers per iteration that could be reused, boxing in a numeric loop. | The loop and the allocation, with the item count from the workload. |
| `copying` | Copying large collections or buffers to pass them on, converting formats back and forth. | Source and destination of each copy and the data size. |
| `n-plus-one-io` | A query, file read or HTTP call inside a loop over results of another query. | The outer query, the inner call, and the expected item count. |
| `lock-across-io` | A mutex or synchronized block that contains a network call, disk write or `await`. | The lock scope and the IO inside it. |
| `blocking-on-async` | A blocking call (sync file IO, sleep, sync HTTP client, CPU-heavy work) on an event loop or async executor thread. | The async context and the blocking call. |
| `unbounded-growth` | Caches, maps, queues or buffers that only grow; memoization keyed by unbounded user input. | The insert site and the absence of eviction or bound. |
| `serialization-cost` | Serializing or deserializing large objects per request, reflection-based mapping in a hot loop, pretty-printing in production paths. | The call site and payload size. |
| `missing-index` | A new query filtering or sorting on columns with no index, on a table that grows. | The query and the schema or migration showing no index. |
| `premature-optimization` | A clever optimization (manual unrolling, hand-written pooling, bit tricks, caching) with no measurement behind it that makes the code harder to read or change. | The construct, the readability cost, and the missing measurement. This is a finding in its own right. |

## Every finding states a workload and a way to settle it

Put these in the finding, in this order, inside `Evidence:` (or `Why it matters:` for the workload):

- **Workload assumption:** the call rate and data size you assumed, with the source (`SLICE.md` AC-3, `PROJECT.md`
  scale section) or `ASSUMED` if you had to guess.
- **Measurement or benchmark that would settle it:** a profile you ran, a command output, or a cheap benchmark the
  verifier can add (for example "a benchmark calling `listOrders` with 1,000 orders; pass if p95 < 50 ms"). When the
  finding is not already settled by evidence, add the benchmark to `Required resolution` as a test to add with
  `Owner: verifier`, or split it into a separate verifier-owned finding.

Do not use these anti-methods, and do not accept them in a rebuttal:

- **Guess and tweak:** changing things at random until a number moves. Ask for the measurement instead.
- **Streetlight:** looking only where it is easy to look (the code in the diff you understand) instead of where the
  time goes (often the IO the diff triggers).
- **Blame someone else:** declaring the database, network or another team's service slow without evidence.
- **Optimizing the cold path:** tuning code that runs once while the per-request path is untouched.

## Severity calibration

- `BLOCKING` only when the regression is **evidenced** on a hot path: a measurement or command output, or a stated
  performance acceptance criterion that the change provably cannot meet (for example an N+1 over a list the AC says
  holds 10,000 items under a 100 ms target). Say which.
- `MAJOR`: a clear cost on a hot path at the documented workload, not yet measured (N+1 on a per-request list, a lock
  held across a remote call on a shared path, an unbounded cache keyed by user input).
- `MINOR` at most for speculative findings: the workload is `ASSUMED`, or the path may not be hot. Also
  `premature-optimization` without evidence is `MINOR` (or `MAJOR` if it makes the code materially harder to change).
- `NOTE`: cold paths, startup, tiny bounded inputs, and pre-existing cost the diff does not make worse.
- Never escalate severity because something "could be slow at scale" without naming the scale.

## Finding examples

GOOD (hot path, workload stated, settling benchmark, minimum fix):

```text
ID: code-006
Severity: MAJOR
Category: performance/n-plus-one-io
Location: src/orders/list.ts:31-44
Finding: listOrders runs one SELECT per order to load its customer inside the for-loop at lines 38-42.
Why it matters: listOrders serves GET /orders on every dashboard load. Workload assumption: up to 200 orders per
  page (SLICE.md AC-2 page size); 200 sequential round trips at ~1 ms each adds ~200 ms per request.
Evidence: list.ts:38 `for (const o of orders) { o.customer = await db.customers.findById(o.customerId) }`.
  Settling measurement: benchmark listOrders with 200 orders against the local test database and record p95.
Required resolution: Load customers in one query (`WHERE id IN (...)`) and join in memory. Verifier: add the
  benchmark above with the AC-2 target as its pass line.
Confidence: HIGH
Owner: implementer
Status: OPEN
```

BAD (no workload, no measurement, cold path, inflated):

```text
ID: code-012
Severity: BLOCKING
Category: performance
Location: src/config/load.go:10-30
Finding: This loop is O(n^2) and will be slow.
Why it matters: Performance is important at scale.
Evidence: Nested loop.
Required resolution: Use a hash map.
Confidence: MEDIUM
Owner: implementer
Status: OPEN
```

What is wrong with it: config loading runs once at startup over a handful of entries, no workload or size is
stated, nothing would settle it, and it is `BLOCKING` with no evidence.

## Out of jurisdiction

- Behaviour under failure, overload, timeouts, retries and backpressure policy → reliability-review. You may note
  the cost; reliability owns what happens when the bound is hit.
- Readability of the code → `code-clarity` (except `premature-optimization`, which is yours).
- Whether a cache or layer should exist at all → simplicity-review.
- Capacity planning and production tuning of live systems: out of scope for review; never run load against shared
  or live environments.

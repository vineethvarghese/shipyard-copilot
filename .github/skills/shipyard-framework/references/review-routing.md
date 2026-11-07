# Review routing

Do not invoke every reviewer for every change. Reviewer sprawl produces noise, burns money, and trains the human to
skim. Route by **jurisdiction**: a reviewer runs when its trigger fires, and not otherwise.

Routing is **data and code**, not judgment: the triggers live in `registry/roles.json` → `routing`, and the saved
workflows apply them. Change routing in the registry, never in a prompt.

## Slice routing (inside the `shipyard-slice` workflow)

The verifier's `VERIFY` result carries `routingFacts`: for each trigger, a boolean `value` and the `evidence` (paths,
hunks) behind it. The slice workflow computes the routing set from those facts and `registry.routing.slice`, against
the raw diff `git diff <featureBranch>...<sliceBranch>`. It recomputes after every fix round, because a fix can fire a
new trigger.

| Role | Runs when | Trigger meaning (`registry.routing.triggerDefinitions`) |
|---|---|---|
| `code-review` | always | **Every slice**, production code or tests or both. Reviews code and tests together; a test-only slice still has its tests reviewed. |
| `simplicity-review` | `productionCode` **unless** `mechanicalOnly` | Skipped only for mechanical slices (renames, version bumps, generated code, formatting, config values); `EVIDENCE.md` says so. |
| `security-review` | `security` | Authentication, authorization, tokens or secrets, tenant/user isolation, parsing untrusted input, cryptography, a new external network surface. |
| `contract-review` | `publicContract` or `config` | Public API, RPC contract, DTO, wire format, public interface, externally visible error or cancellation behaviour; config schema or defaults consumers rely on. |
| `integration-review` | `consumerVisible`, `publicContract` or `config` | Behaviour a consumer or operator can observe; onboarding, rollout, migration, deployment assumptions. |
| `reliability-review` | `concurrency` | Async, concurrency, synchronization, retry, timeout, cancellation, networking, streaming, resource lifetime, shared mutable state, deployment lifecycle. |

**An uncertain flag routes** (`registry.routing.uncertainFlag: "route"`). If the verifier cannot tell, it sets the
value `true` and says why in `evidence`. A missed review costs more than an extra one.

The result lists every role in `reviewersRouted` or `reviewersNotRouted`, each with `because`. `EVIDENCE.md` copies
both lists. Silence reads as "not run", which is hard rule 4 territory. The code reviewer is always routed, so no slice
reaches the human unreviewed.

**A finding can route a reviewer.** If any reviewer files a finding with category `security` and the security
reviewer has not run on this slice, the workflow runs it at once (`because`: the finding that triggered it).

### Security is an in-family reviewer

`shipyard-security-reviewer` is a normal routed reviewer: same brief, same finding schema, same findings file
(`.ai/slices/<id>/findings/security-reviewer.md`), same fail-closed rule. It rates vulnerabilities on its own scale
and maps them with `registry.severityMap.security`; a missing or unknown rating maps to `BLOCKING`
(`finding-schema.md`).

### Scope drift

When the verifier reports `scopeCheck: DRIFT` (the diff touches paths outside both touch sets, or changes a contract
or component the slice did not declare), the drift goes to the architect in `CONFORMANCE` mode with one question: is
this drift consistent with the approved architecture? Inconsistent drift becomes a `BLOCKING` finding owned by the
implementer. Consistent drift is recorded in `EVIDENCE.md`, and the planner widens the touch set before the next
slice run. If the slice result comes back with unresolved drift, the coordinator makes the `CONFORMANCE` call
directly and validates its return (`shipyard_validate.py architect-result -`).

## Every routed reviewer fails closed

A routed review did not happen if the agent errored or timed out, returned `null`, returned output that fails its
contract, or left no findings file that parses (the findings-gate hook also checks this). The workflow retries it
`registry.limits.reviewerRetries` (1) time. Still failing → the workflow returns `status: BLOCKED_REVIEWER` with the
role and reason. The slice cannot reach `READY_FOR_HUMAN`.

The coordinator then asks the human live: wait (re-launch the slice workflow), or proceed without that review. Only
an explicit "proceed" lets the slice continue. Record it in `EVIDENCE.md` as
`<role>: SKIPPED_BY_HUMAN — <unavailable | empty | invalid>, <date>` (never `PASS`) and add the same line under risks
in `REVIEW.HUMAN.md`. A skipped review is re-attempted on the next slice run; it is not a standing waiver.

## Parallelism and independence

All routed reviewers for a pass run **concurrently** (`parallel()` in the workflow). Each gets the same brief inputs:
the raw `SLICE.md`, the raw `TEST_PLAN.md` and the raw diff — never a summary, and never another reviewer's findings
in the first pass. Shared framing produces correlated findings that look like independent agreement.

In `RECHECK`, a reviewer gets its own open findings, the new diff and the incremental diff since its last review
(`git diff <last reviewed commit>..<slice-branch>`), and answers: "are these closed, and did the change open
anything new in my jurisdiction?" It returns its full list; an open finding it leaves out stays open. Reviewers with
no open findings are not re-run unless the new diff fires their trigger for the first time, with one exception: the
code reviewer reviews every fix round's changes, because a fix made for another reviewer is still new code and new
tests.

A rebuttal goes to the reviewer that filed the finding in its own `REBUTTAL` mode: one finding, one rebuttal, an
answer (`ACCEPT_REBUTTAL` or `MAINTAIN_FINDING`) on the `rebuttal-response` contract, nothing else reviewed.

## Plan routing (inside the `shipyard-plan` workflow)

Before any slice exists, `registry.routing.plan` applies. The coordinator passes `planFlags` to the `shipyard-plan` workflow: the
booleans `publicContract`, `config`, `consumerVisible`, `concurrency`, `security` and `modelChecked`, each set from
`discovery.md`, the chosen concept (ADR-000), the P4 answers and C-10, with an uncertain flag set `true`
(`modelChecked` is simply "C-10 is `model-checked`").

| Role | Runs when |
|---|---|
| `architect` (`CRITIQUE`) | always |
| `simplicity-review` | always — complexity is cheapest to delete before any of it is built |
| `contract-review` | `publicContract` or `config` |
| `integration-review` | `consumerVisible` |
| `reliability-review` | `concurrency` or `modelChecked` (it runs the models under `.ai/formal/` and renders any trace) |
| `security-review` | `security` |

Rows are additive. One critique pass, then bounded rechecks only for reviewers whose jurisdiction materially changed
(≤ `registry.limits.planRefineCycles`, 2). At P7 the scope narrows to sequencing and mergeability: the integration
reviewer checks the slice order supports consumer migration, and the architect checks no intermediate state between
slices is incoherent. Plan quality is not re-opened there.

## Review modes

Every reviewer brief carries `Mode:` on its second line, after `Caller: shipyard-coordinator`.

| Mode | Who | Reads | Writes findings to | Verdicts |
|---|---|---|---|---|
| `PLAN` | security, contract, integration, reliability, simplicity reviewers (architect uses `CRITIQUE`) | The planning artifacts that exist: `PROJECT.md`, `ARCHITECTURE.md`, `INVARIANTS.md`, `CONSUMERS.md`, `concepts.md`, ADRs, `DELIVERY_PLAN.md` and `SLICE.md` drafts. No diff. | `.ai/planning/<agent-name>.md` | `PASS`, `CHANGES_REQUIRED`, `NOT_APPLICABLE` |
| `TEST_PLAN` | code-reviewer only | Raw `SLICE.md` and `TEST_PLAN.md`. No diff (there is no code yet). | `.ai/slices/<id>/findings/code-reviewer.test-plan.md` | `APPROVE` (and the status flip), `REVISE` |
| `SLICE` | every routed slice reviewer | Raw `SLICE.md`, raw `TEST_PLAN.md`, raw diff (`Diff:` line). A missing diff is a fail-closed stop. | `.ai/slices/<id>/findings/<agent-name>.md` | `PASS`, `CHANGES_REQUIRED`, `NOT_APPLICABLE` |
| `RECHECK` | reviewers with open findings, plus newly triggered ones, plus the code reviewer in every fix round | As `SLICE`, plus its open findings and the incremental diff since its last review. Carries `Round: n`. | the same file, rewritten | `PASS`, `CHANGES_REQUIRED` |
| `REBUTTAL` | the reviewer that filed a rebutted finding | The finding and the rebuttal, in the brief | nothing | `ACCEPT_REBUTTAL`, `MAINTAIN_FINDING` (`rebuttal-response`) |

In `PLAN` mode reviewers critique the **plan**, not code, and judge planned components and slices instead of a diff.
In `TEST_PLAN` mode the code-reviewer judges the tests that are planned, not the code (`test-plan.md`).

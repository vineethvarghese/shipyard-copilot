# Finding schema, rebuttal and fix scope

Every Shipyard reviewer emits findings in this exact shape. A shared schema is what lets the slice workflow
deduplicate across reviewers without re-reading and re-interpreting prose. The machine form is
`contracts/finding.schema.json`; the file form is below. Both carry the same fields.

## Where findings go

| Review mode | Findings file |
|---|---|
| `SLICE`, `RECHECK` | `.ai/slices/<id>/findings/<agent-name>.md` |
| `TEST_PLAN` (code-reviewer only) | `.ai/slices/<id>/findings/<agent-name>.test-plan.md` |
| `PLAN` (and architect `CRITIQUE`) | `.ai/planning/<agent-name>.md` |

`<agent-name>` is the short agent name: `code-reviewer`, `security-reviewer`, `contract-reviewer`,
`integration-reviewer`, `reliability-reviewer`, `simplicity-reviewer`, `architect`. A `RECHECK` rewrites the same
file with the current status of every finding. The human never reads findings files.

The reviewer **also** returns the findings in its return block (`contracts/reviewer-result.schema.json`): inside a
dynamic workflow the script needs them to dedupe and route fixes, and script variables never reach the coordinator's
context. The coordinator sees only the workflow's merged result. The findings-gate hook refuses to let a reviewer
stop until its findings file exists and parses.

## Findings file format

The first line is the agent banner. Then either the exact line `NO FINDINGS`, or one block per finding, separated by
a blank line, with these lines in this order:

```text
> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: REVIEW.HUMAN.md.

ID:                  code-001
Severity:            BLOCKING | MAJOR | MINOR | NOTE
Category:            <jurisdiction-specific category>
Location:            <path:line-range> | PR metadata | whole slice | <planning artifact path>
Finding:             <what is wrong, stated as a fact>
Why it matters:      <consequence if shipped as-is>
Evidence:            <code, command output, contract, ADR or doc reference a human can open>
Required resolution: <the minimum change that would clear this finding>
Confidence:          HIGH | MEDIUM | LOW
Owner:               implementer | verifier | architect | planner | human
Status:              OPEN | FIXED | REBUTTED | ACCEPTED_BY_HUMAN
```

The file has no `Reporter:` line: the reporter is the agent the file belongs to. In the JSON form, `reporters` is an
array; a reviewer sets it to its own short name, and dedupe extends it.

ID prefixes: `code-`, `security-`, `contract-`, `integration-`, `reliability-`, `simplicity-`, `architect-`, then a
three-digit number. Dedupe keeps the ID of the highest-severity source.

Field rules:

- **`Evidence` is mandatory** and must point at something a human can open. A finding with no evidence is an opinion,
  and opinions do not block merges.
- **`Required resolution`** states the **minimum** corrective change. "Redesign the module" is not a resolution.
- **`Owner`** is who must act. In slice modes it is `implementer` (production-code paths, code actions) or `verifier`
  (test paths; tests to add, remove or reshape). When one finding needs both, file two findings. `architect`,
  `planner` and `human` are for plan-mode findings, or for a slice finding only a spec or architecture change can
  clear.
- **`Status`** starts `OPEN`. It moves to `FIXED` only when a re-check confirms the fix in the new diff, to `REBUTTED`
  only when the reporter answered `ACCEPT_REBUTTAL`, and to `ACCEPTED_BY_HUMAN` only on the human's explicit word,
  recorded by the coordinator.
- **Cap:** at most `registry.limits.findingsCapPerReviewer` (15) findings per reviewer per pass, highest severity
  first. Forty `MINOR` observations spend the human's attention on nothing.

## Severity ladder

| Severity | Meaning | Before READY_FOR_HUMAN |
|---|---|---|
| `BLOCKING` | Cannot merge safely: correctness, contract break, data loss, security, invariant violation. Also a newly introduced layer or abstraction that serves no approved requirement, under the simplicity reviewer's strict criteria. | Fix or rebut |
| `MAJOR` | A substantial issue that should normally be fixed. | Fix or rebut |
| `MINOR` | A real improvement with limited correctness or architectural consequence. | Fix or rebut |
| `NOTE` | Observation or future consideration. | Optional |

Severity inflation destroys the signal. If everything is `BLOCKING`, the human stops reading. A reviewer whose
findings are more than half `BLOCKING` on a routine slice re-examines its calibration before returning.

## Fix scope

`registry.fixScope` is `BLOCKING`, `MAJOR`, `MINOR`. Every finding in scope is either fixed or formally rebutted
before a slice reaches the human. `NOTE` findings are optional; an author may fix one if it is cheap and inside the
touch set.

Any open finding in scope starts a fix round: the implementer (`FIX`) takes findings owned by `implementer`, the
verifier (`FIX_TESTS`) takes those owned by `verifier`, in parallel, each in its own touch set. Then the slice is
re-verified and re-reviewed. After `registry.limits.fixRounds` (3) rounds, the workflow returns `ESCALATE` with the
open findings; the coordinator brings them to the human with options and a recommendation. Only the human can set
`ACCEPTED_BY_HUMAN`.

## Rebuttal protocol

The owner may rebut each finding **once**, instead of fixing it. A rebuttal cites one of: an approved requirement,
the approved architecture, an accepted ADR, the code itself, test evidence, or an established repository convention.
"I disagree" is not a rebuttal. Rebuttals go in the author's return block:

```json
{ "findingId": "code-004", "citation": "ADR-002 §Decision; src/cache/lru.ts:12-30", "argument": "<one paragraph>" }
```

The reporting reviewer answers each rebuttal with `contracts/rebuttal-response.schema.json`: exactly one response
plus one sentence of reasoning.

```text
ACCEPT_REBUTTAL   — the citation resolves it; status becomes REBUTTED
MAINTAIN_FINDING  — the citation does not resolve it; status stays OPEN
```

A finding reported by several reviewers needs `ACCEPT_REBUTTAL` from every reporter.

If a `BLOCKING` finding is maintained and the disagreement is architectural:

```text
reviewer <-> author unresolved
            |
            v
     architect ADJUDICATE
            |
   resolvable from approved sources?
      /                    \
    yes                     no
     |                       |
   RESOLVED: decision      ESCALATE: the workflow returns
   in .ai/decisions/,      ESCALATE; the coordinator asks
   finding fixed or        the human
   withdrawn
```

A maintained non-architectural finding stays `OPEN` and must be fixed in the next round. The coordinator **never**
resolves a technical disagreement itself and never manufactures agreement. Its only moves are: route to the
architect, or escalate to the human.

## Deduplication across reviewers

The slice workflow collapses findings from **different reviewers** with the **same location and the same category**
into one entry: the highest severity among the open sources, every reporter kept in `reporters`. Two findings from
the same reviewer are never merged, even at the same location: a reviewer that files two findings there means two
problems. Rebuttal and adjudication state is kept per original finding (`<reporter>:<id>`), so merging never loses
one.

```json
{ "id": "contract-002", "severity": "BLOCKING", "reporters": ["contract-reviewer", "integration-reviewer"], "...": "..." }
```

Independent agreement is worth recording as provenance. It is **not** additional evidence, and it does not raise
severity by itself (hard rule 3).

## Security severity mapping

The security reviewer rates each vulnerability `CRITICAL | HIGH | MEDIUM | LOW | INFORMATIONAL`, maps it with
`registry.severityMap.security`, writes the mapped value in `Severity`, and keeps its own rating, OWASP category and
CWE in `Category` (for example `Category: CWE-532 Sensitive info in log (HIGH)`).

| Security rating | Severity |
|---|---|
| CRITICAL, HIGH | BLOCKING |
| MEDIUM | MAJOR |
| LOW | MINOR |
| INFORMATIONAL | NOTE |
| missing, or not one of the five | **BLOCKING** |

Guessing low is the false pass this rule exists to prevent. The same fallback applies anywhere a finding's severity
is missing or unrecognisable: treat it as `BLOCKING`.

Example: a HIGH "token logged in plaintext" at `src/auth/token.go:42-45`, reviewer confidence 8/10, becomes
`Severity: BLOCKING`, `Category: CWE-532 Sensitive info in log (HIGH)`, `Location: src/auth/token.go:42-45`,
`Confidence: HIGH`.

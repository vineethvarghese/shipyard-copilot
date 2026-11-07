# Compute policy

Model choice is a real cost and quality lever. Use it deliberately: neither "the biggest model everywhere" nor "the
cheapest model everywhere" is correct.

## Platform facts (Copilot)

| Fact | Consequence for Shipyard |
|---|---|
| A custom agent's frontmatter `model` is honoured by the CLI, the cloud agent and VS Code. There is no `effort` key. | Each `.agent.md` sets its role's **default** class through `model` only (`shipyard/scripts/gen_agents.py` writes it from the registry). Effort per mode is dropped. |
| Model precedence in the CLI: agent `model` > `--model` > `COPILOT_MODEL` > settings. Effort is a global CLI setting (`effortLevel`). | The human launches the coordinator with `--model`; a global effort setting applies to every agent in the session. |
| VS Code caps a subagent's cost tier at the parent's; a subagent above that tier does not run. | "No delegate above the coordinator" holds by construction in the IDE. |
| Whether a dynamic workflow's `ctx.agent` accepts a custom-agent name or a `model` is **(unverified)**. | The workflows pass the registry's class names; if the runtime ignores them, every workflow agent runs at the session model and the coordinator says so under `## Framework configuration`. |
| The SDK's `customAgents` accept `reasoningEffort` per agent **(unverified for the CLI and IDE)**. | Not used by this port. |

Evidence: the custom-agents configuration reference, the VS Code subagents page and the CLI command reference, read
2026-11-08. This is a baseline, not a guarantee. Treat any fact this session has not confirmed as `UNRESOLVED`.

**Session check (P0, once per session, before the first delegation).** Run `copilot --version` and
`python3 shipyard/scripts/check.py --env`, which prints the client, the effective guardrails and the model settings it
can see. Record them under `## Framework configuration` in `PROJECT.md`. If the session model is weaker than the
class a `DEEP` role needs, stop and tell the human (escalation: MUST). Never silently fall back to a weaker class.

## Classes, not model names

Role definitions name a **class**. `registry/roles.json` → `computeClasses` resolves each class:

| Class | model | effort | Used for |
|---|---|---|---|
| `COORDINATOR` | `opus` | `max` | The coordinator session only. Set at launch. |
| `DEEP` | `opus` | `high` | Adversarial judgment, decomposition, contract calls, test design. |
| `STANDARD` | `sonnet` | `medium` | Bulk reading, writing code to an approved spec, running tests. |

Change a class in the registry, not in an agent file or a workflow. A delegate may be raised to `xhigh` effort for a
narrow but hard task, never above the coordinator. Prefer raising effort within a class over reaching for a larger
model.

## The coordinator runs at the top

The coordinator is the only agent the human talks to. It decides what reaches the human, adjudicates specialist
disagreements, and gates every merge. It is the highest-judgment seat and the only session that lives for the whole
project. So:

- **Launch it as `copilot --agent=shipyard-coordinator Its frontmatter says the same,
  but the launch flags make the intent explicit.
- **No delegate may run above the coordinator.** If the coordinator finds itself on a weaker model or effort than a
  delegate would get, it stops before planning or delegating and tells the human. It continues only on an explicit
  human waiver, recorded under `## Framework configuration`.
- **Peers, not subordinates, on judgment.** Architect, planner and reviewers also run at `DEEP`. The coordinator's
  edge is the whole picture, not a bigger model. It stays lean by having delegates write to `.ai/` and return short
  results.

## Per-role defaults and minimums

From `registry/roles.json`. The workflows pass the mode's class on every `ctx.agent()` call (honoured only if the
runtime accepts a model there, **unverified**). On a direct subagent call the coordinator names the class in the brief
(`Compute: DEEP`); the agent file's `model` is what actually runs.

| Role | Mode → class | Minimum | Why |
|---|---|---|---|
| coordinator | SESSION → COORDINATOR | COORDINATOR | Sole human interface; gates and adjudication. |
| discovery | SCAN, DRAFT → STANDARD; ELEPHANT, SYNTHESIZE, QUESTIONS, GRILL → DEEP | as listed | Scanning is high-volume, low-judgment reading. The sealed take, synthesis, the question tree and each grill round are where the value is. |
| goldfish | BRAINSTORM, READINESS → DEEP | DEEP | A cold mind is only useful if it is a strong one. |
| architect | all modes → DEEP | DEEP | Broad, ambiguous, consequential. |
| planner | all modes → DEEP | DEEP | Decomposition errors are expensive and found late. |
| implementer | IMPLEMENT, FIX → STANDARD | STANDARD | Lots of code, low ambiguity, spec and test plan already approved. |
| verifier | TEST_PLAN → DEEP; WRITE_TESTS, VERIFY, FIX_TESTS → STANDARD | as listed | Designing the tests is judgment; writing and running them is execution. |
| code-review | TEST_PLAN, SLICE, RECHECK → DEEP | DEEP | Gate owner for the test plan; design depth and test quality. |
| security, contract, integration, reliability, simplicity review | all modes → DEEP | DEEP | Irreversible or cross-system consequences; simplicity can file `BLOCKING`. |

Lowering a minimum is an explicit configuration decision recorded in `PROJECT.md`, not an ad-hoc call. The two
discovery rows show why the class belongs to the **mode**, not the agent: scanning and questioning are the same
agent at different moments, with different needs.

**Time-box every delegation.** Every brief carries `Budget: <n> turns` and asks for a bounded, prioritised result
when the budget runs short. An agent given no budget optimises for completeness, which is how a planning phase
silently becomes an afternoon. Derive budgets from C-6.

## What drives the requirement

Compute need is not a function of how much code is involved. It rises with:

```text
scope + ambiguity + consequence + difficulty of verification
```

| | LOW | HIGH |
|---|---|---|
| Scope | narrow, local | cross-system |
| Ambiguity | explicit spec | underspecified |
| Consequence | reversible | contract or architecture |
| Verification | deterministic | judgment-heavy |

A task can be tiny and still need `DEEP`: "can this shared async work be cancelled incorrectly when one consumer
disconnects?" is narrow in scope but high in every other dimension.

## Escalation is delegation

An agent cannot change its own model mid-run. A `STANDARD` agent that hits one of these **stops and reports**
(`architectureConcerns` or `humanInputRequested`) — it never pushes through:

- a conflict with approved architecture;
- an ambiguous or underspecified contract;
- a non-obvious concurrency or lifecycle question;
- contradictory tests or a test plan that contradicts the spec;
- cross-service uncertainty;
- any decision that would set a precedent for later slices.

```text
implementer (STANDARD) detects an architecture conflict
    -> stops, returns architectureConcerns
    -> the slice workflow or the coordinator routes it to the architect (DEEP)
    -> the implementer is re-briefed with the resolution
```

## Budget discipline and C-9

Every routed reviewer is a separate subagent with its own context and cost. A slice that routes five reviewers plus
the verifier's three modes costs eight or more runs, most at `DEEP`. That is the intended price for a consequential
slice and a waste on a trivial one — which is why routing is jurisdictional and the fix-round cap exists.

### Where the cost actually lands

Measured on a real planning run (a 6-slice plan, ~175M input tokens across two sessions): the large majority of
spend was **high-volume repository and specification reading** during discovery and spec extraction — not the
judgment-heavy phases that produced the value. The blocking findings that changed the outcome came from adversarial
review, a small fraction of the total.

That asymmetry drives two rules:

1. **Match the class to the work, not to the phase's importance.** Bulk reading with low judgment — repository
   inventory, spec transcription, call-site enumeration — runs at `STANDARD`. Reserve `DEEP` for adversarial
   judgment, decomposition, test design and contract calls.
2. **Cap breadth before raising depth.** A second reviewer on the same artifacts usually returns correlated findings;
   the same budget spent verifying an empirical premise returns a wrong answer corrected. When a phase feels
   under-powered, ask whether it is under-*verified* first. The brainstorm follows the same rule: breadth 2 is for a
   genuinely open question, not a default.

### C-9: the cost budget

C-9 is the human's spending limit in their own terms (for example "keep it moderate", a token figure, or a money
figure). Apply it like this:

- **At P0**, recommend a brainstorm breadth that fits C-9 and C-6 together.
- **At every gate** (P4, P8, each merge brief), report spend so far in one line, from the usage figures the client
  shows (`/usage` in the CLI; premium-request counts on GitHub.com for the cloud agent).
- **When projected spend will pass C-9**, say so at the next gate with the cheapest option that keeps the rules:
  narrower brainstorm, smaller slices, fewer refine cycles. Never meet C-9 by running a role below its minimum,
  skipping a routed reviewer, or skipping verification. Those are not cost levers; they are hard rules.
- A run that needs to exceed C-9 to finish safely is a human decision, asked with a recommendation.

### Cost signals worth watching

Report these to the human at a gate when any looks wrong, rather than silently absorbing them:

| Signal | What it means |
|---|---|
| Artifacts far exceed the C-6 artifact budget | Analysis is being produced that nobody will read. |
| A large fraction of output is superseded in one replan | A delivery parameter was discovered too late — see the P0 gate. |
| Multiple review passes over one unchanged artifact | Fan-out is not jurisdictional. Collapse them. |
| A slice routinely hits fix round 3 | The slice or its spec is wrong; more rounds will not help. |
| An escalation resting on an unverified premise | Stop and run the command first. It is almost always cheaper than the human turn. |

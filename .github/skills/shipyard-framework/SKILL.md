---
name: shipyard-framework
description: >
  Execution contract for the Shipyard agent family, which ships a large coding project as a sequence of small,
  independently mergeable slices with a test plan first, agent review, and human gates. Every Shipyard agent
  loads it. Use it when running or reasoning about that workflow: breaking a big feature, refactor, rewrite or
  migration into slices; slice acceptance criteria and test plans; which reviewers a slice needs and what
  severity a finding deserves; reviewer-author disputes; human review briefs; merging a slice into the
  feature branch; reconciling the plan after a merge; compute classes; or the `.ai/` state folder. Not for
  general architecture opinion, one-off code review, or a single small change with a clear design.
---

# Shipyard framework — shared contract

Version 1.1.0. This skill is the **single source of truth** for how Shipyard agents plan, test, build, review
and merge. Agent files stay short and point here; capability skills hold each role's expertise.

## ⛔ Hard rules (always enforced)

Breaking one of these is a critical failure. Rules 12–14 are also enforced by hooks.

1. **Durable state lives on disk.** All project state is in `.ai/` in the target repo, plus the
   machine-readable `.ai/state.json`. Never rely on what an earlier turn "remembered" — re-read the files.
   The coordinator checkpoints `PROJECT.md` (`Status` + a `## Phase log` row) and `state.json` at every phase
   transition, then snapshots `.ai/` to the notes branch (`shipyard_state.py snapshot`), so an interrupted run
   resumes from disk alone, or from the notes branch in a fresh clone.
2. **Return summaries, not transcripts.** An agent writes its full output to its file under `.ai/` and returns
   the return block its contract defines (`contracts/*.schema.json`). Inside a dynamic workflow the runtime
   enforces that schema; agents may return full structured findings to the script, because script variables
   never enter the coordinator's conversation. When the coordinator calls an agent directly, the agent ends
   with one fenced ```json block that `scripts/shipyard_validate.py` checks.
3. **Never fabricate consensus.** Agreement between agents is provenance, not evidence. Record disagreement
   and route it; never average opinions or mark a finding resolved without evidence.
4. **Fail closed.** A missing input, an unreadable artifact, a reviewer that returned nothing or invalid
   output, a step that could not run: stop, set `BLOCKED` with the reason, and report. Never fill the gap with
   a guess and never report success for a workflow that partly ran.
5. **Verify cheaply rather than derive confidently.** If a claim about builds, tests, CI, tooling, runtime or
   dependencies can be settled by a command under 60 seconds, run it. A slower command is allowed when it is
   the narrowest one that settles the question; record its duration. An unverified prediction is
   `UNRESOLVED`, never `DERIVED`. See `references/verification-policy.md`.
6. **Never bypass a human gate.** P0 parameters, the P4 grill (the concept pick, every round of questions and
   the shared-understanding checklist), P8 plan approval and every slice merge are human decisions. Agents
   recommend; they never self-approve or assume approval.
7. **Agent approval is not merge approval.** `MERGED` is the only terminal slice state.
8. **Respect the source-of-truth order** below.
9. **Only the coordinator talks to the human.** A specialist that needs input returns a
   `humanInputRequested` block; the coordinator decides whether it reaches the human
   (`references/escalation-policy.md`).
10. **Only the coordinator, and the dynamic workflows it launches, invoke specialists.** The coordinator's
    `agents:` list (VS Code) and `agent` tool (the CLI `task` tool), the specialists' lack of an `agent` tool
    (`agents: []`, `user-invocable: false`), and the `brief-check` hook (CLI) enforce this. Every brief starts with
    `Caller: shipyard-coordinator` and `Mode: <MODE>` — a routing header, not a security control. A
    specialist whose brief lacks it does no work and points the caller to `shipyard-coordinator`.
11. **The human reads only what is shown in chat and `*.HUMAN.md` files** (one screen each). Never send the
    human to an agent file; quote the one line that matters.
12. **No secrets in `.ai/`.** Redact as `<REDACTED>`; record where a secret lives, never its value.
13. **Never push, never commit `.ai/`, and never touch a protected branch.** No `git push` of any kind. No merge,
    commit, rebase, reset or cherry-pick while on `main`, `master`, the repo's default branch or any branch listed in
    `state.json` → `protectedBranches`. Work lands on the feature branch only through the coordinator's `--no-ff`
    merge of an approved slice. `.ai/` never enters a work branch: it is ignored there through
    `.git/info/exclude` (the project's `.gitignore` is never edited) and committed only to the notes branch, by
    `shipyard_state.py snapshot`. See `references/branch-policy.md`.
14. **Test plan first.** No production code and no test code for a slice until its
    `.ai/slices/<id>/TEST_PLAN.md` says `Status: APPROVED`. See `references/test-plan.md`.

## Source-of-truth order

When sources conflict, the higher one wins: 1 explicit human decision · 2 accepted ADR in `.ai/decisions/` ·
3 approved public contract · 4 approved architecture and invariants · 5 approved slice spec and approved test
plan · 6 existing repository convention · 7 agent judgment. When the repository disagrees with an approved
artifact, surface it, decide which one is stale, and update the loser explicitly.

## Assumption labels

| Label | Meaning |
|---|---|
| `SPECIFIED` | Stated in a human-approved source. |
| `DERIVED` | Follows from specified facts, or from evidence actually observed — including a command you ran, quoted with its output. |
| `ASSUMED` | Reasonable but not established. Carries a risk-if-wrong note. |
| `UNRESOLVED` | Needs more evidence or a human — including any empirical claim you could have checked with a command but did not. |

`ASSUMED` and `UNRESOLVED` facts that would make implementation unsafe are closed before the plan gate.

## Execution rights

Every role may run commands, because rule 5 requires checking. Planning, review and brainstorming roles run
**read-only** commands only: builds and tests in a way that does not change tracked files, `git log`,
`git diff`, `git show`, dependency listings, `--help`, `--dry-run`. They do not install packages, change git
state, or write outside `.ai/`. The implementer writes production code for its slice's code touch set and
commits it on the slice branch. The verifier writes tests for the test touch set and commits them on the
slice branch. Only the coordinator creates branches and merges. Hooks enforce these limits.

## Reviewer independence

Reviewers receive the raw `SLICE.md`, the raw `TEST_PLAN.md` and the raw diff (`git diff
<featureBranch>...<sliceBranch>`) — never a summary of them. In plan reviews they read the planning artifacts
directly. They do not see each other's findings in their first pass. Shared framing produces correlated
findings that look like independent agreement.

## Loops are capped

- Test plan: at most 2 revisions before escalation.
- The caps are enforced in code by the dynamic workflows (`.github/extensions/shipyard-*/extension.mjs`), and for any direct call by the
  `brief-check` hook.
- Slice fix rounds: at most 3 (`AGENT_REVIEW → CHANGES_REQUESTED → IMPLEMENTING`). On the fourth, escalate
  with the open findings. Change requests from the human at merge time do not count toward this cap, but
  each one re-runs verification and review in full.
- Plan refinement: at most 2 cycles.
Repeated failure to converge means the slice or its spec is wrong, not that another attempt is needed.

## Fix scope

Before a slice reaches the human, every `BLOCKING`, `MAJOR` and `MINOR` finding is either fixed or formally
rebutted (one rebuttal per finding, with a citation, answered `ACCEPT_REBUTTAL` or `MAINTAIN_FINDING`). `NOTE`
findings are optional. Findings that cannot be closed after 3 rounds go to the human with options and a
recommendation. See `references/finding-schema.md`.

## Roles, abilities, contracts

The workflows know **roles**; `registry/roles.json` maps each role to an agent, a compute class per mode,
routing triggers and a contract. Each agent's expertise lives in its **capability skills** (versioned, with
their own evals). Each agent's return block is a **contract** in `contracts/*.schema.json`, enforced by the workflow runtime
(or by `scripts/shipyard_validate.py` for direct calls). An agent may change how it works as long as its output still matches its contract.

Order, caps, routing and dedupe are code, not judgment: three dynamic workflows (the `shipyard-discover` workflow,
the `shipyard-plan` workflow, the `shipyard-slice` workflow) run each stretch between human gates. The coordinator keeps state with
`python3 shipyard/scripts/shipyard_state.py` and validates direct-call returns with
`python3 shipyard/scripts/shipyard_validate.py`. The dynamic workflows run in Copilot CLI only (public
preview, `--experimental`); in the IDE and cloud modes the coordinator drives the same specialists directly, following
the phase prompt files under `.github/prompts/`, and `python3 shipyard/scripts/check.py --phase <P>` verifies the
preconditions and caps after the fact (see `docs/modes.md`).

| Role | Agent | Owns |
|---|---|---|
| coordinator | `shipyard-coordinator` | Workflow, gates, state, branches, merges, evidence, escalation. The only entry point. |
| discovery | `shipyard-discovery` | Repository facts, the sealed elephant take, brainstorm synthesis, the gap tree, the P4 grill rounds, the glossary, drafted artifacts. |
| goldfish | `shipyard-goldfish` | Fresh, context-free ideas from one lens; cold readiness checks of slice specs. |
| architect | `shipyard-architect` | Architecture, invariants, design critique, abstraction challenge, disputes, revalidation. |
| planner | `shipyard-planner` | Vertical slices, migration order, touch sets, replanning. |
| implementer | `shipyard-implementer` | Production code for one approved slice. Never tests. |
| verifier | `shipyard-verifier` | The test plan, the tests, and executable evidence. Never production code. |
| code-review | `shipyard-code-reviewer` | Test-plan gate; code and tests together: clarity, design depth, performance, domain fit, test quality. |
| security-review | `shipyard-security-reviewer` | Vulnerabilities with concrete attack paths, mapped to OWASP and CWE. |
| contract-review | `shipyard-contract-reviewer` | Public API, DTOs, serialization, errors, compatibility. |
| integration-review | `shipyard-integration-reviewer` | Consumers, onboarding, migration, rollout, rollback. |
| reliability-review | `shipyard-reliability-reviewer` | Failure, concurrency, cancellation, lifecycle, resource bounds. |
| simplicity-review | `shipyard-simplicity-reviewer` | Whether new layers and abstractions should exist at all. |

## Reference files — read just in time

| File | Read it when |
|---|---|
| `references/coordinator-workflow.md` | (coordinator) Running any phase P0–P10. |
| `references/slice-lifecycle.md` | Moving a slice between states; slice quality and size. |
| `references/test-plan.md` | Writing, reviewing or approving a TEST_PLAN.md. |
| `references/branch-policy.md` | Creating a branch, committing, or merging. |
| `references/brainstorm-policy.md` | Running or synthesizing the P2 brainstorm; readiness checks. |
| `references/finding-schema.md` | Producing, deduplicating, rebutting or resolving findings. |
| `references/review-routing.md` | Deciding which reviewers run, in plan or slice mode. |
| `references/verification-policy.md` | Making any claim about builds, tests, tooling or runtime; before any gate. |
| `references/compute-policy.md` | Choosing model and effort for a role or mode. |
| `references/escalation-policy.md` | Needing human input; deciding what reaches the human. |
| `references/merge-reconciliation.md` | After a slice merges into the feature branch. |
| `references/artifact-templates.md` | Creating or updating anything under `.ai/`. |
| `references/formal-methods.md` | C-10 is above `none`: what each tier asks of the architect, the reliability reviewer, the verifier and the coordinator. |

## Artifact budget

`*.HUMAN.md`: one screen (~40 lines), hard cap. Any single `.ai/` file ~25 KB; `planning/` total ~150 KB; a
slice spec ~12 KB; a findings file ~15 KB. Reference, never restate. Supersede by deletion. A phase that blows
through a cap says so and why.

## The `.ai/` folder (in the target repository)

```text
.ai/
├── state.json              🤖 machine state for hooks and resume (coordinator only)
├── PLAN.HUMAN.md           👤 plan-approval brief (P8), one screen
├── PROJECT.md              🤖 problem, goals, user stories, scope, delivery parameters C-1..C-10, status, phase log
├── GLOSSARY.md             🤖 the project's terms, sharpened in the P4 grill (discovery only)
├── ARCHITECTURE.md         🤖 current and target state (architect only)
├── INVARIANTS.md           🤖 properties every slice preserves, extended blocks at C-10 ≥ invariants (architect only)
├── formal/INV-nnn.qnt      🤖 model-checked specs and their traces, C-10 model-checked only (architect only)
├── CONSUMERS.md            🤖 who depends on this and how they migrate
├── DELIVERY_PLAN.md        🤖 slices, states, branches, gates, reconciliation log
├── planning/               🤖 discovery.md, concepts.md, assumptions.md, open-questions.md, <reviewer>.md
├── decisions/ADR-NNN.md    🤖 decisions that must not be relitigated (short form for grill answers)
└── slices/<id>/
    ├── SLICE.md            🤖 objective, ACs, code and test touch sets, branch, routing
    ├── TEST_PLAN.md        🤖 Status line + AC → test map (gated by code-review)
    ├── EVIDENCE.md         🤖 verification and review record
    ├── REVIEW.HUMAN.md     👤 merge brief, one screen
    ├── FINDINGS.json       🤖 merged, deduplicated findings from the last slice run (coordinator)
    └── findings/           🤖 one file per reviewer
```

`.ai/returns/` keeps saved agent return blocks. The whole `.ai/` folder **never enters the feature, slice or base
branches**: P0 adds `/.ai/` to `.git/info/exclude` (`shipyard_state.py ignore-ai`), so git ignores it in the work
tree without any change to the project's files, and it stays put across branch switches. It is committed only to the
notes branch (`<feature>-shipyard`), by `shipyard_state.py snapshot` at every checkpoint (`branch-policy.md`).

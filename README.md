# shipyard-copilot

shipyard-copilot runs the [Shipyard](https://github.com/vineethvarghese/shipyard) method under GitHub Copilot:
Copilot CLI, Copilot agent mode in VS Code (JetBrains in preview), and the Copilot coding agent on GitHub.com. It
ships a large coding job (a big feature, refactor, rewrite or migration) as a chain of small, independently
mergeable slices. Every slice gets a test plan before any code, is built and verified by specialist agents, and is
reviewed by the right reviewers before you see it. You approve the plan and every merge; slices merge into a
feature branch you name, and you raise the pull request to `main` yourself.

It is a template repository: copy `.github/` and `shipyard/` (and `AGENTS.md`) into your own repository.

```mermaid
flowchart LR
    req["Your request"] --> p0["P0 Intake: you set limits and the branch"]
    p0 --> disc["Discover: scan, brainstorm, draft"]
    disc --> p4["P4 Grill: you pick a direction and answer rounds of questions"]
    p4 --> plan["Plan: critique, refine, cut slices"]
    plan --> p8["P8 Plan approval: you approve"]
    p8 --> loop["Slice loop × N: test plan, build, verify, review"]
    loop --> gate["Merge gate: you approve each slice"]
    gate --> merge["Local merge into the feature branch"]
    merge -->|"more slices"| loop
    merge -->|"all slices merged"| pr["You push and raise the PR to main"]
    classDef human fill:#fde68a,stroke:#b45309,color:#000000
    class p0,p4,p8,gate,pr human
```

<sub>Yellow boxes are yours. Source: [docs/diagrams/01-hero.mmd](docs/diagrams/01-hero.mmd).</sub>

## What you get, honestly

Copilot has three clients, and they do not enforce the same things. Shipyard's guarantees map onto them like this
(**full** = the same guarantee; **degraded** = works but weaker or client-dependent; **manual** = convention plus a
later check). Details: [docs/capability-map.md](docs/capability-map.md) and
[docs/unenforced.md](docs/unenforced.md).

| Shipyard guarantee | CLI | IDE (VS Code) | Cloud (coding agent) |
|---|---|---|---|
| Phase order, loop caps, reviewer routing are code | full (dynamic workflows, public preview) | degraded (prompt files + `check.py --phase`) | degraded (one task per phase + `check.py`) |
| Test plan before code, at write time | full (agent-scoped hooks) | manual (pull-request check only) | degraded (hook with inferred role + pull-request check) |
| Each agent writes only its own paths | full | manual (tools restriction + pull-request check) | degraded |
| Goldfish sees nothing in `.ai/` | full | manual | manual |
| Never push, never touch `main` | full (hook + ruleset) | full (ruleset) | full (ruleset, no bypass) |
| `.ai/` never on a work branch | full | full | degraded (restored and synced by Actions) |
| Human gates P0 / P4 / P8 / merge | full (chat) | full (handoff buttons, nothing auto-sent) | manual (issue comments, a label, pull-request review) |
| Reviewer returns checked against a schema | full inside workflows | after the fact | after the fact |

Everything marked (unverified) in the docs came from a single source or a page that was silent on the point.

## Quickstart

**CLI (recommended).** Copilot CLI with dynamic workflows (`--experimental`), git, Python 3.9+.

```bash
python3 shipyard/scripts/check.py --env             # what this client will enforce
copilot --experimental --agent=shipyard-coordinator
```

Describe the job in plain words. The coordinator does the rest and stops when it needs you.

**IDE (VS Code).** Pick **shipyard-coordinator** in the agent picker and run `/shipyard.intake`. Then
`/shipyard.discover`, `/shipyard.plan`, `/shipyard.slice NN`, `/shipyard.merge NN`, `/shipyard.reconcile`.
Each gate ends with a handoff button that pre-fills your reply; nothing is sent until you send it.

**Cloud (coding agent).** Import the rulesets in `.github/rulesets/`, keep Copilot off the bypass list, then open
an issue with the **Shipyard intake (P0)** form and assign it to Copilot naming `shipyard-coordinator`. One task
per phase; gates are issue comments, the label `shipyard:plan-approved`, and the slice pull requests.

Full walkthrough: [docs/getting-started.md](docs/getting-started.md). Modes: [docs/modes.md](docs/modes.md).

## The four human stops

| Stop | When | You decide |
|---|---|---|
| **P0 Intake** | Right after your request | Delivery limits C-1..C-10 (C-10 is the optional formal rigour tier), the feature branch and base branch, brainstorm breadth. Skipped items take a marked default. |
| **P4 Grill** | After the repo scan and brainstorm | Which concept to build, then rounds of questions (at most 7 per round, 3 rounds unless you ask for more) until nothing is silently assumed. Each has a recommendation a plain "yes" accepts; "enough" ends it. A short checklist closes the gate. |
| **P8 Plan approval** | After critique and slicing | Approve `PLAN.HUMAN.md` (`APPROVE PLAN <feature>`), or ask for changes. |
| **Merge approval** | After each slice is clean | Merge the slice into the feature branch (`APPROVE MERGE slice <id>`), or request changes (`REVIEW.HUMAN.md`). |

Every approval is recorded with `shipyard_state.py gate <P> approve --by <login>`, and `check.py --phase` refuses
to advance without it, in every mode ([docs/gates.md](docs/gates.md)). Shipyard may also stop for a shared
validation environment, an escalation after capped loops, or a fail-closed block, always with a one-line reason
and a recommendation.

## The agents

| Agent | One line |
|---|---|
| `shipyard-coordinator` | The only entry point: runs phases, gates, state, branches, merges and human briefs. |
| `shipyard-discovery` | Scans the repo, seals the elephant take, synthesises the brainstorm, drafts artifacts and the glossary, runs the grill rounds. |
| `shipyard-goldfish` | Context-free thinker: one brainstorm lens, or a cold readiness read of a slice spec. |
| `shipyard-architect` | Architecture, invariants (and formal models at C-10 model-checked), plan critique, dispute adjudication, post-merge revalidation. |
| `shipyard-planner` | Cuts the work into vertical slices with touch sets, order and branches. |
| `shipyard-implementer` | Writes production code for one approved slice. Never tests. |
| `shipyard-verifier` | The slice's test engineer: test plan, tests, verification and routing facts. Never production code. |
| `shipyard-code-reviewer` | Gates the test plan; reviews code and tests together for clarity, depth, performance and test quality. |
| `shipyard-security-reviewer` | Finds vulnerabilities with concrete attack paths. |
| `shipyard-contract-reviewer` | Public API, DTOs, serialization, errors and compatibility. |
| `shipyard-integration-reviewer` | Consumers, onboarding, migration, rollout and rollback. |
| `shipyard-reliability-reviewer` | Failure, concurrency, cancellation, lifecycle and resource bounds. |
| `shipyard-simplicity-reviewer` | Asks whether each new layer or abstraction should exist at all. |

The twelve specialists are hidden from the agent picker and work only on a brief from the coordinator.

## Requirements

- GitHub Copilot with custom agents (CLI, coding agent, VS Code; JetBrains in preview).
- Copilot CLI with dynamic workflows (`--experimental`) for CLI mode; without it the coordinator falls back to
  the IDE procedure.
- git, and a git repository to work in.
- Python 3.9 or later (standard library only) for the hooks and scripts.
- Node 22 only to run this repository's own extension tests.
- The rulesets in `.github/rulesets/` imported, with no bypass for Copilot (required in cloud mode).

## Repo map

```text
AGENTS.md                      root agent instructions: who you are, the .ai/ map, the rules that are always on
.github/
  copilot-instructions.md      repository-wide instructions: entry point, .ai/, findings, severities, labels
  instructions/                path-scoped instructions: .ai/**, slice branches, test files
  agents/                      13 custom agents, generated from shipyard/source-agents by gen_agents.py
  skills/                      shipyard-framework (the shared contract) + one capability skill per ability
  prompts/                     IDE-mode phase checklists: intake, discover, plan, slice, merge, reconcile, resume
  extensions/                  CLI-mode dynamic workflows: shipyard-discover, shipyard-plan, shipyard-slice
  hooks/shipyard.json          the repository hook file (CLI and cloud)
  workflows/                   copilot-setup-steps, shipyard-slice-check, shipyard-notes-guard, shipyard-plan-gate, shipyard-notes-sync
  rulesets/                    importable rulesets for main and feature/**
  ISSUE_TEMPLATE/              the cloud-mode P0 intake form
  PULL_REQUEST_TEMPLATE/       the slice pull request
  CODEOWNERS                   .ai/ and the framework files
shipyard/
  registry/roles.json          role -> agent, compute per mode, routing triggers, contract
  contracts/                   JSON Schemas for every agent return block and .ai/state.json
  scripts/                     state helper, validator, checks (check.py --env / --phase / --pr), gen_agents.py, hooks/
  tests/                       hooks (unittest), scripts (unittest), extensions (node --test)
docs/                          guides, the design document, ADRs, diagrams
examples/sample-project/       a tiny project with an illustrative .ai/ folder
```

## Documentation

- [Getting started](docs/getting-started.md) · [Modes](docs/modes.md) · [Concepts](docs/concepts.md) ·
  [Workflow P0–P10](docs/workflow.md) · [The slice loop](docs/slice-loop.md)
- [Gates](docs/gates.md) · [Capability map](docs/capability-map.md) · [Unenforced](docs/unenforced.md)
- [Brainstorm](docs/brainstorm.md) · [Formal rigour](docs/formal-methods.md) · [Branching](docs/branching.md) ·
  [Guardrails](docs/guardrails.md) · [Hooks](docs/hooks.md) · [Workflows](docs/workflows.md)
- [Design document](docs/DESIGN.md) · [Decisions](docs/decisions/) · [Sample project](examples/sample-project/README.md)
- [Contributing](CONTRIBUTING.md)

## Credits

This is a port of [Shipyard](https://github.com/vineethvarghese/shipyard) (MIT). Shipyard's brainstorm builds on
the elephant/goldfish method ([elephant-goldfish](https://github.com/vshvedov/elephant-goldfish), MIT). The P4
grill, the glossary and the seam-first test discipline adapt [Matt Pocock's skills](https://github.com/mattpocock/skills)
(MIT). The simplicity reviewer's voice is adapted from the MIT-licensed "Cranky Old Sam" reviewer persona. Ideas
from Ousterhout, Gregg and Evans are paraphrased, never quoted. Full credits: [NOTICE](NOTICE).

## Licence

MIT. See [LICENSE](LICENSE).

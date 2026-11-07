# Workflow: phases P0 to P10

Shipyard runs eleven phases. Four of them are stops where you decide. The rest run on their own.

```mermaid
flowchart TD
    P0["P0 Intake: limits, branch, breadth, formal rigour"]
    subgraph DW["Workflow: discover"]
        P1["P1 Scan"] --> P2["P2 Brainstorm and narrow"] --> P3["P3 Draft"]
    end
    P4["P4 Grill: concept pick, then rounds of questions until shared understanding"]
    subgraph PW["Workflow: plan"]
        P5["P5 Plan critique"] --> P6["P6 Refine, up to 2 cycles"] --> P7["P7 Delivery planning"]
    end
    P8["P8 Plan approval"]
    subgraph SW["Workflow: slice"]
        P9["P9 Slice: test plan, build, verify, review"]
    end
    P99["P9.9 Merge approval"]
    P10["P10 Reconcile"]
    done["Complete: you push and raise the PR"]
    P0 --> P1
    P3 --> P4
    P4 --> P5
    P6 -->|"new human questions"| P4
    P7 --> P8
    P8 --> P9
    P9 --> P99
    P99 --> P10
    P10 -->|"next slice"| P9
    P10 -->|"replan or architecture decision"| P8
    P10 -->|"all slices merged"| done
    classDef human fill:#fde68a,stroke:#b45309,stroke-width:3px,color:#000000
    class P0,P4,P8,P99 human
```

<sub>Source: [04-phases.mmd](diagrams/04-phases.mmd) · rendered: [04-phases.svg](diagrams/04-phases.svg)</sub>

The yellow boxes are the four human stops.

| Phase | What runs | Run by | What you see |
|---|---|---|---|
| **P0 Intake** (stop) | `check.py --phase P0`. Size check. One batched question: C-1 to C-10 (C-10 is the optional formal rigour tier, see [formal-methods.md](formal-methods.md)) and brainstorm breadth, each with a default. Branch check and creation. `state.json` written. `.ai/` kept off the work branches (`.git/info/exclude`) and snapshotted to the notes branch `<feature>-shipyard`. | Coordinator | One message to answer (the intake issue form in cloud mode). A refusal if you name `main`, `master` or another protected branch. |
| P1 Scan | Discovery reads the repo: build, tests, structure, consumers, validation tiers, the terms the code uses. Then, at deep compute, it seals its own elephant take. | `shipyard-discover` (CLI) or `/shipyard.discover` | Status lines |
| P2 Brainstorm and narrow | Goldfish brainstorm, then synthesis and a gap tree (each gap with its kind and the gaps it depends on). Skipped at breadth 0. | `shipyard-discover` (CLI) or `/shipyard.discover` | Status lines |
| P3 Draft | Discovery drafts the planning artifacts, user stories and the glossary; the architect drafts the architecture and invariants at the chosen rigour tier; discovery drafts round 1 of the grill. | `shipyard-discover` (CLI) or `/shipyard.discover` | Status lines |
| **P4 Grill** (stop) | The concept pick, then rounds: each round asks every question whose prerequisites are settled (at most 7), with a recommendation a plain "yes" accepts. Between rounds discovery records your answers, settles facts from the repo, challenges terms, writes the glossary and recomputes. Ends when nothing is left to ask, when you say "enough", or after 3 rounds (you can ask for more), with a short checklist you confirm. Decisions that are hard to reverse become short ADRs. | Coordinator, with discovery `GRILL` between rounds | Top concepts, disagreements, then numbered questions per round, then the checklist |
| P5 Plan critique | Architect and simplicity reviewer always. Contract, integration, reliability and security reviewers when triggered; at C-10 `model-checked` the reliability reviewer also runs the formal models and renders any counterexample. | `shipyard-plan` (CLI) or `/shipyard.plan` | Status lines |
| P6 Refine | Fix the plan from the critique. At most 2 cycles. New questions for you end the workflow and go back to P4. | `shipyard-plan` (CLI) or `/shipyard.plan` | Status lines, or new questions |
| P7 Delivery planning | Planner cuts slices with touch sets, seams under test and prior art. Integration and architect check the order. One readiness goldfish per `SLICE.md`. | `shipyard-plan` (CLI) or `/shipyard.plan` | Status lines |
| **P8 Plan approval** (stop) | `PLAN.HUMAN.md` shown in chat: slices, the seams their tests observe, the properties you rely on, risks. Your explicit approval moves every slice to `APPROVED`. | Coordinator | One-screen plan brief |
| P9 Slice | Coordinator creates the slice branch. The workflow runs test plan, build, verify, review and fix rounds. Coordinator writes the evidence and brief. | Coordinator, then the `shipyard-slice` workflow (CLI) or `/shipyard.slice` (IDE, cloud) | Status lines; a question if a shared tier is needed; an escalation if it cannot converge |
| **P9.9 Merge** (stop) | You approve. Coordinator checks, merges with `--no-ff` into the feature branch, re-runs the tests. | Coordinator | `REVIEW.HUMAN.md` in chat, then a merge result |
| P10 Reconcile | Compare plan with reality. Architect REVALIDATE, planner RECONCILE. A replan or architecture decision goes back to P8. | Coordinator, direct calls | A short summary, or a new plan to approve |

P9 to P10 repeat for each slice. When all slices are merged, the status becomes `COMPLETE`. You push the feature
branch and raise the pull request. See [branching.md](branching.md).

In CLI mode the three workflows enforce the order and caps in code. In IDE and cloud modes the coordinator follows
the phase prompt files under `.github/prompts/` instead; `python3 shipyard/scripts/check.py --phase <P>` checks the
previous gate before each phase, and every human yes is recorded with `shipyard_state.py gate <P> approve`. See
[modes.md](modes.md) and [gates.md](gates.md).

## Project status values

`state.json` and `PROJECT.md` carry one of: `INTAKE`, `DISCOVERY`, `PLANNING`, `AWAITING_PLAN_APPROVAL`,
`IMPLEMENTING`, `COMPLETE`, `BLOCKED`. Status changes only between workflows, so `BRAINSTORMING` (P2) and
`DELIVERY_PLANNING` (P7) appear as phase-log labels rather than as the status line.

`BLOCKED` is set every time Shipyard stops safely. It always comes with a reason.

## Checkpoints

The coordinator updates `PROJECT.md` (status and a phase log row) and `state.json` at every phase change. That is
what makes a run resumable. See [getting-started.md](getting-started.md#resuming-after-an-interruption).

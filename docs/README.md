# shipyard-copilot documentation

shipyard-copilot runs the Shipyard method under GitHub Copilot. It takes a large feature, refactor, rewrite or
migration and ships it as a series of small slices. Each slice gets a test plan before any code. Each slice is
built, verified and reviewed by specialist agents. You approve the plan and every merge. Slices merge into a
feature branch you name. Shipyard never touches `main` and never pushes. When the work is done, you push the
feature branch and raise the pull request yourself.

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

<sub>Source: [01-hero.mmd](diagrams/01-hero.mmd) · rendered: [01-hero.svg](diagrams/01-hero.svg)</sub>

## Is it for you?

| Use Shipyard when | Use a normal session when |
|---|---|
| The change spans many files or several weeks of work | The change is small and the design is clear |
| You want reviewable steps with evidence | You only want a quick answer or one-off fix |
| You want a test plan before code, every time | Tests are already obvious or not needed |
| You want to approve each step before it lands | You are happy to review one big diff at the end |

## Reading order

New here? Read the first five pages in order. Read the rest when you need them.

| # | Page | What it covers |
|---|---|---|
| 1 | [getting-started.md](getting-started.md) | Install, first run in each mode, the four times Shipyard stops for you |
| 2 | [modes.md](modes.md) | CLI, IDE and cloud: what runs where, and what each enforces |
| 3 | [concepts.md](concepts.md) | Slices, gates, evidence, findings, roles, the `.ai/` folder |
| 4 | [workflow.md](workflow.md) | The phases P0 to P10 |
| 5 | [slice-loop.md](slice-loop.md) | What happens inside one slice |
| 6 | [gates.md](gates.md) | The human gates under each mode |
| 7 | [capability-map.md](capability-map.md) | Every Shipyard mechanism, its Copilot equivalent and its fidelity |
| 8 | [unenforced.md](unenforced.md) | What is dropped, what each mode does not enforce, the top risks |
| 9 | [brainstorm.md](brainstorm.md) | The elephant/goldfish brainstorm, the P4 grill and readiness checks |
| 10 | [formal-methods.md](formal-methods.md) | The optional formal rigour tiers: readable invariants, property tests, model checking |
| 11 | [branching.md](branching.md) | Branches, commits, the merge procedure |
| 12 | [guardrails.md](guardrails.md) | The eight hooks and what they block, per client |
| 13 | [hooks.md](hooks.md) | The Copilot hook wiring and payload adapter |
| 14 | [workflows.md](workflows.md) | The three dynamic workflows (CLI mode) |
| — | [DESIGN.md](DESIGN.md) | The design document this port follows |
| — | [decisions/](decisions/) | Architecture decision records |
| — | [diagrams/](diagrams/) | Mermaid sources (`.mmd`) and rendered `.svg` files |

## Decisions

| ADR | Decision |
|---|---|
| [ADR-0001](decisions/ADR-0001-three-modes.md) | One procedure, three modes; gates recorded in `state.json`; fidelity stated per mode |

The decisions Shipyard itself made (saved workflows, test plan first, local merge and never `main`, roles not
agent names, hooks over prompt rules, `.ai/` off the work branches, the P4 grill, formal rigour tiers) carry
over unchanged and are explained in the pages above.

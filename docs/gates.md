# The human gates under Copilot

Shipyard stops four times for you: P0 intake, P4 grill, P8 plan approval, and the merge of every slice. In
Shipyard one coordinator session owned the chat, so the gates were chat turns. Under Copilot there are three
owners of "the chat", so there are three gate models. All three write the same `.ai/state.json`, and
`python3 shipyard/scripts/check.py --phase <P>` refuses to advance a phase whose gate is not recorded, so the modes
can be mixed (discover in the CLI, slices in the cloud).

What is recorded, in every mode:

```bash
python3 shipyard/scripts/shipyard_state.py gate P0 approve --by <login>
python3 shipyard/scripts/shipyard_state.py gate P4 approve --by <login>
python3 shipyard/scripts/shipyard_state.py gate P8 approve --by <login>
python3 shipyard/scripts/shipyard_state.py gate MERGE approve --by <login> --slice <id>
```

The coordinator runs these only after a literal yes. Silence, enthusiasm, an unclicked button, a missing label
or an unapproved pull request are not approval.

## CLI mode (primary, highest fidelity)

- Launch: `copilot --experimental --agent=shipyard-coordinator` in the project folder, after
  `python3 shipyard/scripts/check.py --env`, with the hooks trusted.
- The coordinator is the chat owner. It asks the P0 batched question itself, writes `state.json`, creates the
  branches, and then runs `shipyard-discover` as a dynamic workflow. The workflow returns `NEEDS_HUMAN` with
  concepts, gaps and questions; the coordinator presents P4 and waits. Same for `shipyard-plan` (returns
  `AWAITING_PLAN_APPROVAL`, the coordinator shows `PLAN.HUMAN.md`) and `shipyard-slice` (returns `READY_FOR_HUMAN`,
  the coordinator shows `REVIEW.HUMAN.md`).
- A workflow never pauses for the human; it ends. `ctx.pause` is used only for the SHARED-tier stop inside a slice,
  because the resumed run replays journaled steps and continues at VERIFY.
- Headless use (`copilot workflow run shipyard-slice --args @slice.json --result-file out.json`) is for
  conformance tests, not for production runs, because headless runs cannot resume and need pre-granted permissions.

## IDE mode (VS Code; JetBrains with custom agents in preview)

- No dynamic workflows, so the coordinator orchestrates the specialists directly as subagents (`agents:` lists the
  twelve; specialists have `agents: []` and no `agent` tool). The phase prompt files are the checklists the
  coordinator follows and you can read.
- Gates are **handoffs with `send: false`**: after P3 the coordinator's response ends with **Answer the P4
  questions**, which pre-fills a reply template you edit and send; after the checklist, **Confirm shared
  understanding**; after P7, **Approve the plan** pre-fills `APPROVE PLAN <feature>`; after P9, **Approve the slice
  merge** / **Request slice changes**. Nothing is sent until you click and send, and the coordinator records the
  gate only on receipt of the literal phrase.
- Order and caps are convention here. `check.py --phase` at the top of every prompt file and `shipyard-slice-check`
  on the slice pull request are the enforcement. This is degraded fidelity, and documented as such.

## Cloud mode (Copilot coding agent)

There is no interactive session, so the issue and the pull request are the gates, and one task is one phase (a
task opens at most one pull request and runs at most 59 minutes on Actions).

| Gate | Mechanism |
|---|---|
| P0 Intake | The issue form `shipyard-intake.yml` (request, C-1..C-10 with defaults, breadth, feature and base branch). Assigning the issue to Copilot with `shipyard-coordinator` named in a comment starts task 1 (intake and discover). |
| P4 Questions | Task 1 ends by posting the concepts, gaps and questions as a comment on the issue and uploading `.ai/` as the artifact `shipyard-notes`, which `shipyard-notes-sync.yml` commits to the notes branch. You answer in a comment and re-assign; task 2 (plan) reads the answers. One grill round per task. |
| P8 Plan approval | Task 2 posts `PLAN.HUMAN.md` as a comment. A maintainer adds the label `shipyard:plan-approved`. `shipyard-plan-gate.yml` requires that label, or the recorded P8 gate in `state.json` on the notes branch, before any slice pull request can pass. |
| Merge | Each slice task opens a pull request from its branch into the feature branch with the slice template. Required checks: `shipyard-slice-check`, `shipyard-notes-guard`, `shipyard-plan-gate`, and the project's test command inside the slice check. The feature-branch ruleset requires one human review and allows merge commits only, so the evidence summary in the pull-request body is kept. Change requests are review comments; the agent iterates in the same task. |
| Final pull request | You raise it from the feature branch to `main` exactly as in Shipyard. |

Honest limits of cloud mode: no local hooks except the `.github/hooks` subset; no `.git/info/exclude`
persistence between tasks; `.ai/` reaches the notes branch through Actions rather than the coordinator; goldfish
isolation is not enforced; and Copilot must **not** be granted the ruleset bypass or it can push to protected
branches.

Source: section C of [DESIGN.md](DESIGN.md).

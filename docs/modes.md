# The three modes

Shipyard's method is one procedure: eleven phases, four human stops, one `.ai/` folder. Under Copilot there are
three places to run it, and they do not enforce the same things. This page says what each mode does, what it
enforces, and how to pick one. The modes can be mixed on one project: the gates are recorded in
`.ai/state.json`, and `python3 shipyard/scripts/check.py --phase <P>` refuses to advance in any mode without the
previous gate.

| | CLI | IDE | Cloud |
|---|---|---|---|
| Where | Copilot CLI in a terminal | VS Code agent mode (JetBrains: custom agents in preview) | Copilot coding agent on GitHub.com |
| Start | `copilot --experimental --agent=shipyard-coordinator` | Pick `shipyard-coordinator` in the agent picker; run `/shipyard.intake` | Open an issue with the **Shipyard intake** form and assign it to Copilot |
| P1–P3, P5–P7, P9 | Dynamic workflows `shipyard-discover`, `shipyard-plan`, `shipyard-slice` (order, caps, routing and dedupe are code) | The coordinator drives the specialists as subagents, following the prompt files `.github/prompts/shipyard.*.prompt.md` | As IDE, inside one coding-agent task per phase |
| Gates | The coordinator asks in chat | Handoff buttons pre-fill the reply (`send: false`); you click, edit, send | Issue comments (P4), `PLAN.HUMAN.md` as a comment plus the label `shipyard:plan-approved` (P8), the slice pull request review and merge |
| Hooks | All eight, agent-scoped (`SHIPYARD_ROLE` in each agent file) plus the repository file `.github/hooks/shipyard.json` | Agent-scoped hooks where the client supports them (unverified); otherwise the `tools` restriction only | The `.github/hooks` subset; the role is inferred from `state.json` → `activeRole` |
| `.ai/` | Local, ignored through `.git/info/exclude`, snapshotted to `<feature>-shipyard` | Same | Restored by `copilot-setup-steps.yml` from the notes branch; uploaded as an artifact and committed by `shipyard-notes-sync.yml` |
| Merge | `git merge --no-ff` by the coordinator after your yes | Same | You merge the slice pull request into the feature branch (merge commit only) |
| Fidelity | **full** | **degraded** | **manual** |

Fidelity words: **full** means the same guarantee as Shipyard; **degraded** means it works but weaker or
client-dependent; **manual** means a convention plus a later check, not enforcement at the moment of action.
[capability-map.md](capability-map.md) has the mechanism-by-mechanism table and [unenforced.md](unenforced.md) the
rules each mode does not enforce.

## CLI mode

The primary mode. Requirements: Copilot CLI with dynamic workflows (public preview, `--experimental`), git, Python
3.9+.

```bash
cd <your project>
python3 shipyard/scripts/check.py --env          # what this client enforces (project install)
copilot --experimental --agent=shipyard-coordinator
# plugin install (copilot plugin install vineethvarghese/shipyard-copilot): the ids carry the plugin name
copilot --experimental --agent=shipyard:shipyard-coordinator
```

The coordinator owns the chat. It asks the P0 question, writes `state.json`, creates the branches, then runs
`shipyard-discover`. The workflow returns `NEEDS_HUMAN` with the concepts, gaps and first grill round; the
coordinator presents P4 and waits. `shipyard-plan` returns `AWAITING_PLAN_APPROVAL` and the coordinator shows
`PLAN.HUMAN.md`; `shipyard-slice` returns `READY_FOR_HUMAN` and the coordinator shows `REVIEW.HUMAN.md`. A
workflow never pauses for you; it ends at a gate ([ADR-0001](decisions/ADR-0001-three-modes.md)).

Approval is explicit: the coordinator records `shipyard_state.py gate P8 approve --by <login>` only after a
literal yes. Keep `--no-ask-user` off; the hooks keep the coordinator inside `.ai/**`.

If the CLI has no workflow runner (no `--experimental`, or an older version), the coordinator says so once and
continues in IDE mode with the prompt files.

Model settings: the CLI resolves a model as agent `model` > `--model` > `COPILOT_MODEL` > settings. The agent
files carry no model id until you set `MODEL_MAP` in `shipyard/scripts/gen_agents.py` (or pass `--model DEEP=<id>`)
and regenerate; until then every agent runs at the session model. Effort is the `--reasoning-effort` launch flag or the `effortLevel` setting (verified on CLI 1.0.107),
not per agent.

## IDE mode

Requirements: VS Code with Copilot agent mode (custom agents, subagents, handoffs); JetBrains supports custom
agents and subagents in preview, handoffs are (unverified) there.

1. Pick **shipyard-coordinator** in the agent picker. The twelve specialists are hidden (`user-invocable: false`)
   and reachable only through the coordinator's `agents:` list.
2. Run `/shipyard.intake` and answer the P0 form. Then `/shipyard.discover`, `/shipyard.plan`, `/shipyard.slice NN`,
   `/shipyard.merge NN`, `/shipyard.reconcile`, in that order; `/shipyard.resume` finds the step after an
   interruption. Each prompt starts with `check.py --phase`, lists the specialist calls in order with the exact
   brief header, states the caps, and ends at the gate.
3. At a gate the coordinator's turn ends with handoff buttons (**Answer the P4 questions**, **Approve the plan**,
   **Approve the slice merge**, …). Clicking one pre-fills the reply; nothing is sent until you send it, and the
   coordinator records the gate only on the literal phrase.

Order and caps are convention here: the coordinator follows the prompt file, `check.py --phase` checks the
preconditions, and `shipyard-slice-check` on the slice pull request is the backstop for touch sets and the
test-plan order. Subagents run one after another unless the client runs them in parallel. VS Code caps a
subagent's model at the parent's cost tier, which gives "no delegate above the coordinator" for free.

## Cloud mode

Requirements: Copilot coding agent enabled on the repository; the rulesets from `.github/rulesets/` imported;
`copilot-setup-steps.yml` on the default branch; the Agents variable `SHIPYARD_FEATURE` set to the feature branch
once P0 has chosen it; Copilot **not** granted a bypass on any ruleset.

There is no interactive session, so the issue and the pull request are the gates, and **one task is one phase**
(a task opens at most one pull request and runs at most 59 minutes):

| Gate | Mechanism |
|---|---|
| P0 | The issue form `.github/ISSUE_TEMPLATE/shipyard-intake.yml` (request, C-1..C-10 with defaults, breadth, feature and base branch). Assign the issue to Copilot naming `shipyard-coordinator`; task 1 runs intake and discover. |
| P4 | Task 1 ends by posting the concepts, gaps and questions as an issue comment and uploading `.ai/` as the artifact `shipyard-notes`, which `shipyard-notes-sync.yml` commits to the notes branch. You answer in a comment and re-assign; one round per task. |
| P8 | The plan task posts `PLAN.HUMAN.md` as a comment. A maintainer adds the label `shipyard:plan-approved`. `shipyard-plan-gate.yml` requires that label or the recorded P8 gate before any slice pull request can pass. |
| Merge | Each slice task opens a pull request from its branch into the feature branch using the slice template. Required checks: `shipyard-slice-check`, `shipyard-notes-guard`, `shipyard-plan-gate`. The feature-branch ruleset requires one review and allows merge commits only, so the evidence summary in the pull request body survives. Change requests are review comments; the agent iterates in the same task. |
| Final | You raise the pull request from the feature branch to `main` yourself, as in every mode. |

Honest limits: only the `.github/hooks` subset of hooks runs (`ask` is treated as `deny`, timeouts fail open);
`.git/info/exclude` does not persist between tasks; `.ai/` reaches the notes branch through Actions rather than
the coordinator; goldfish isolation is not enforced; and the name of the coding agent's own Actions workflow,
which `shipyard-notes-sync.yml` follows, is (unverified).

## Choosing

- You have the CLI and can turn on `--experimental`: **CLI**. It is the only mode where order, caps and routing are
  code and every hook runs.
- You live in VS Code and want to watch the agents work: **IDE**, with the pull-request checks turned on.
- The work must run unattended on GitHub.com: **cloud**, accepting manual fidelity and the per-task overhead.
- Mixing is fine: discover and plan in the CLI, slices in the cloud, or the reverse. The gates live in
  `state.json` on the notes branch, and `check.py --phase` reads them in every mode.

# Getting started

This page takes you from an empty `.github/` to your first merged slice. Pick a mode first:
[modes.md](modes.md) explains the three and what each enforces. The CLI is the recommended one.

## Requirements

| Need | Why | Notes |
|---|---|---|
| GitHub Copilot with custom agents | The thirteen `.github/agents/*.agent.md` files | CLI (GA), coding agent, VS Code; JetBrains in preview. |
| Copilot CLI with dynamic workflows | CLI mode runs the three workflows | Public preview, behind `--experimental`. Without it the coordinator falls back to IDE mode. |
| git | Branches, commits and local merges | Your project must be a git repository. |
| Python 3.9 or later | The hooks, the scripts and the checks | Standard library only. Nothing to install. |
| Node 22 | Only for this repository's own extension tests | Not needed to use Shipyard. |
| Rulesets imported, Copilot without bypass | Server-side protection of `main` and `feature/**` | Required in cloud mode; recommended everywhere. |

## Install

Copy two folders into your repository: `.github/` (agents, skills, prompts, instructions, hooks, extensions,
workflows, templates, rulesets) and `shipyard/` (registry, contracts, scripts, hooks and tests), plus `AGENTS.md`.
Or create your repository from this one as a template (`gh repo create --template`).

Then:

1. **Set the model ids** (optional). The agent files carry no model id until you set `MODEL_MAP` in
   `shipyard/scripts/gen_agents.py` or run `python3 shipyard/scripts/gen_agents.py --model DEEP=<id>
   --model STANDARD=<id> --model COORDINATOR=<id>`. Until then every agent runs at the session model.
2. **Import the rulesets** from `.github/rulesets/main-protection.json` and `feature-branches.json`
   (repository Settings → Rules → Rulesets → New ruleset → Import). Do not add Copilot as a bypass actor.
3. **Replace `@OWNER`** in `.github/CODEOWNERS` with your maintainers.
4. **Check the environment** in your project folder:

   ```bash
   python3 shipyard/scripts/check.py --env
   ```

   It prints the client it can see, the guardrails that will be active, and the ones that will not.

## Launch

### CLI

```bash
copilot --experimental --agent=shipyard-coordinator
```

Describe the job in plain words, for example "Replace our hand-rolled cache with a bounded LRU cache and move
every caller to it." The coordinator is the only agent you talk to. It launches the workflows and the other
agents for you, and stops when it needs you.

### IDE (VS Code)

Pick **shipyard-coordinator** in the agent picker, then run `/shipyard.intake` and describe the job. The
coordinator follows the prompt files from there: `/shipyard.discover`, `/shipyard.plan`, `/shipyard.slice NN`,
`/shipyard.merge NN`, `/shipyard.reconcile`. At each gate it ends with a handoff button that pre-fills your reply.

### Cloud (Copilot coding agent)

Open a new issue with the **Shipyard intake (P0)** form, fill in the request and the limits, and assign the issue
to Copilot with a comment that names `shipyard-coordinator`. Each task is one phase; the gates are issue comments,
the `shipyard:plan-approved` label and the slice pull requests. Set the Agents variable `SHIPYARD_FEATURE` to the
feature branch once P0 has chosen it, so each task restores `.ai/` from the notes branch.

## Your first project: the four stops

Shipyard stops and waits for you four times. Between stops it works on its own and posts short status lines.

| Stop | When | What you see | What you do |
|---|---|---|---|
| 1. Intake (P0) | Right after your request | One message with the delivery limits C-1 to C-10, the feature branch and base branch, and the brainstorm breadth. Each item has a recommended default. | Answer what you care about. Anything you skip takes the default and is marked `ASSUMED`. Name the feature branch, for example `feature/lru-cache`. |
| 2. Grill (P4) | After the repo scan and brainstorm | The top concepts, where agents disagreed, then rounds of numbered questions (at most 7 each) with a recommendation apiece. Between rounds the agents record your answers, settle facts from the repo and update the glossary. A short checklist at the end. | Pick a concept. Answer each round, or say "yes" to take every recommendation, or "enough" to stop. Confirm the checklist. |
| 3. Plan approval (P8) | After the plan has been critiqued and cut into slices | `PLAN.HUMAN.md`: one screen with the slices, their order, risks and anything still `ASSUMED`. | Say `APPROVE PLAN <feature>`, or ask for changes. Only an explicit approval moves on. |
| 4. Merge approval (each slice) | After a slice is built, verified and reviewed clean | `REVIEW.HUMAN.md`: recommendation first, up to three things to check, risks, one line of evidence. | `APPROVE MERGE slice <id>`, or ask for changes. In cloud mode, review and merge the slice pull request. |

The intake limits are:

| Item | What it sets |
|---|---|
| C-1 | Slice budget: how many slices at most |
| C-2 | New-project budget: whether new packages or services may be created |
| C-3 | Reuse posture: prefer existing code or allow new building blocks |
| C-4 | Blast radius: what the work may touch |
| C-5 | Tracking artifacts: what records to keep |
| C-6 | Time and artifact budget |
| C-7 | Convention posture: follow repo conventions or improve them |
| C-8 | Feature branch and base branch |
| C-9 | Cost budget |
| C-10 | Formal rigour: `none`, `invariants`, `properties` or `model-checked` (see [formal-methods.md](formal-methods.md)) |
| Breadth | Brainstorm breadth 0, 1 or 2 (see [brainstorm.md](brainstorm.md)) |

Shipyard may also stop between the four stops, but only when it must: a shared validation tier it never runs on
its own, an escalation after a capped loop (2 test-plan revisions, 3 fix rounds), or a block with a one-line reason.

## Resuming after an interruption

All state lives on disk in `.ai/` and on the notes branch `<feature>-shipyard`. Nothing depends on the chat.

- CLI: start the same command again in the same folder and say "resume".
- IDE: run `/shipyard.resume`.
- Cloud: assign the next task; `copilot-setup-steps.yml` restores `.ai/` from the notes branch first.

The coordinator reads `.ai/state.json` and `.ai/PROJECT.md`, tells you the phase, the active slice and the next
action, and continues from the last recorded step. In a fresh clone, push or fetch the notes branch first; work
done after the last snapshot is lost, and the coordinator says so.

## Finishing

When every slice is merged into the feature branch, the status becomes `COMPLETE`. Shipyard reminds you of your
last step:

```bash
git push -u origin feature/lru-cache
```

Then raise a pull request from the feature branch to `main` in your usual tool. Shipyard never pushes and never
opens that pull request. The slice merges make the feature branch history easy to review one slice at a time.

## Next

- [modes.md](modes.md) for what each mode enforces, and [unenforced.md](unenforced.md) for what it does not.
- [concepts.md](concepts.md) explains the words used above; [workflow.md](workflow.md) shows every phase.

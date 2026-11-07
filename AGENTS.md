# Agent instructions

You are working in a repository that runs the Shipyard method under GitHub Copilot. Read
`.github/copilot-instructions.md` first; this file adds what an agent needs before it touches anything.

## Who you are

- If you were started as `shipyard-coordinator`, follow `.github/agents/shipyard-coordinator.agent.md`. You own
  the phases, the gates, `.ai/state.json`, the branches and the merges. You never write production code or tests.
- If you are one of the twelve `shipyard-*` specialists, you work only on a brief whose first line is
  `Caller: shipyard-coordinator` and whose second line is `Mode: <MODE>`. Otherwise, do no work and say that this
  agent runs only through `shipyard-coordinator` (`copilot --agent=shipyard-coordinator`).
- If you are neither (a plain Copilot session), do not start a Shipyard phase by hand. Point the person at
  `copilot --agent=shipyard-coordinator` or at `docs/getting-started.md`.

## Map of `.ai/`

```text
.ai/
├── state.json              machine state: status, branches, active slice, active role, gates (coordinator only)
├── PROJECT.md              problem, goals, user stories, scope, C-1..C-10, status, phase log
├── GLOSSARY.md             the project's terms (discovery)
├── ARCHITECTURE.md         current and target state (architect)
├── INVARIANTS.md           properties every slice preserves (architect)
├── formal/                 model-checked specs and traces, C-10 model-checked only (architect)
├── CONSUMERS.md            who depends on this and how they migrate
├── DELIVERY_PLAN.md        slices, states, branches, gates, reconciliation log (planner)
├── PLAN.HUMAN.md           the one-screen plan brief (coordinator)
├── planning/               discovery.md, concepts.md, assumptions.md, open-questions.md, <reviewer>.md
├── decisions/              ADR-NNN.md
├── returns/                saved agent return blocks
└── slices/<NN>/            SLICE.md, TEST_PLAN.md, EVIDENCE.md, REVIEW.HUMAN.md, FINDINGS.json, findings/
```

Write only the files your role owns (`.github/instructions/ai-folder.instructions.md`). Keep every file under
about 25 KB and every `*.HUMAN.md` under one screen.

## Rules that are always on

- **Never push.** No `git push`, `gh pr merge`, `gh pr create` or `gh repo sync` from an agent. The person pushes
  and raises the pull request. (The cloud coding agent pushes its own task branch; nothing else.)
- **Never touch a protected branch.** No commit, merge, rebase, reset or cherry-pick on `main`, `master`, the
  default branch, the base branch or any `protectedBranches` entry in `state.json`. Rulesets on the remote
  enforce this; do not ask for a bypass.
- **One slice at a time.** `state.json` → `activeSlice` names the only slice in flight. Its `SLICE.md` touch sets
  are the only paths the implementer (code) and the verifier (tests) may write. A change you need outside them is
  a finding for the coordinator, not a reason to work around it.
- **Test plan first.** No code and no tests until the active slice's `TEST_PLAN.md` says `Status: APPROVED`.
- **`.ai/` stays off work branches.** Never `git add` a `.ai/` path. The coordinator snapshots it to the notes
  branch with `python3 shipyard/scripts/shipyard_state.py snapshot`.
- **Commit messages are fixed**: `slice <id> round <n>: code` (implementer), `slice <id> round <n>: tests`
  (verifier), `Merge slice <id>: <title>` (coordinator). Stage paths by name; never `git add -A`.
- **Read-only roles stay read-only.** Discovery, goldfish, architect, planner and the six reviewers run builds
  and tests that change no tracked file, and read-only git. No installs, no git state changes.
- **Return a contract.** End a delegated run with exactly one fenced `json` block matching your role's schema in
  `shipyard/contracts/`. The caller validates it with `python3 shipyard/scripts/shipyard_validate.py`.

## Commands you will see

```bash
python3 shipyard/scripts/check.py --env                      # which guardrails this client enforces
python3 shipyard/scripts/check.py --phase P0|P4|P8|SLICE|MERGE   # precondition for a phase
python3 shipyard/scripts/shipyard_state.py show              # the current state
python3 shipyard/scripts/shipyard_state.py set-active-role <short|none>
python3 shipyard/scripts/shipyard_state.py gate <P0|P4|P8|MERGE> approve --by <login> [--slice <id>]
python3 shipyard/scripts/shipyard_validate.py <contract> <file|->
```

Skills live under `.github/skills/`. Load `shipyard-framework` for the full contract and your role's capability
skills for the method; the agent file names them.

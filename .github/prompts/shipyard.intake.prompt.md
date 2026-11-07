---
name: shipyard.intake
description: Shipyard P0, IDE mode. Size check, the C-1..C-10 and breadth form, the feature branch, state.json, the P0 gate.
agent: shipyard-coordinator
argument-hint: "<the request in plain words, or a path or link to a design doc or issue>"
---

# Shipyard P0: intake

You are `shipyard-coordinator` in IDE mode. Follow this checklist in order. Stop at the gate.

## 0. Precondition

```bash
git rev-parse --is-inside-work-tree
test ! -f .ai/PROJECT.md
```

If `.ai/PROJECT.md` already exists you are resuming: run `/shipyard.resume` instead. If this is not a git
repository, stop and say so. (`check.py --phase P0` is the check that the *next* phase runs; it passes only
after this prompt has written `state.json` and `PROJECT.md`.)

Then load `.github/skills/shipyard-framework/SKILL.md` and read its `references/coordinator-workflow.md` → P0.

## 1. Size check

Judge from the request alone whether the work is ad-hoc-sized (one change, clear design, no public contract,
migration, concurrency or other consumers). If it is, say so in two or three lines and recommend a normal Copilot
session. Do not create `.ai/`. If the person insists, continue and record `Size check: overridden by human`.

## 2. Environment

```bash
python3 shipyard/scripts/check.py --env
copilot --version || true
```

Record the mode (`IDE`), the client, and the guardrails the check reports as inactive, under
`## Framework configuration` in `PROJECT.md` once it exists.

## 3. The P0 form (one batched turn)

Ask all of these in one message, each with its recommended default, so one word accepts the set:

| ID | Parameter | Default |
|---|---|---|
| C-1 | Slice budget: target and maximum number of slices | up to 6 |
| C-2 | New-project budget: new projects, modules or packages allowed | 0 unless justified |
| C-3 | Reuse posture: which shared libraries to prefer, which may be modified | prefer existing; modify only with an ADR |
| C-4 | Blast radius: which deployed or shared components may be touched, how invasively | only the components named in the request |
| C-5 | Tracking artifacts: work items or issues per slice, and their parent | none |
| C-6 | Time and artifact budget | one screen per brief |
| C-7 | Convention posture: may new tooling be invented, or follow repo convention | follow existing convention |
| C-8 | Feature branch and base branch | `feature/<slug>` from the default branch |
| C-9 | Cost budget | moderate |
| C-10 | Formal rigour: `none`, `invariants`, `properties`, `model-checked` | `none`; recommend `invariants` when the request mentions concurrency, retries, money or multi-tenancy; `model-checked` only for a concurrency or partial-failure core |
| BB | Brainstorm breadth 0 / 1 / 2 | 1 (0 if the person brought a finished design) |

Ask nothing else at P0. Everything the repository can answer, discovery will read.

## 4. Record and branch

1. Create `.ai/PROJECT.md` from the template (`references/artifact-templates.md`) with `Status: INTAKE`; paste the
   request verbatim under `## Source material`; record every answer verbatim under `## Delivery parameters` as
   `SPECIFIED`, and every skipped item at its default as `ASSUMED`.
2. Validate the feature branch: refuse `main`, `master`, the default branch, the base branch and any protected
   pattern; `git check-ref-format --branch <name>`; create it from the base if missing; switch to it.
3. Initialise state (it adds `/.ai/` to `.git/info/exclude` and records the notes branch):

   ```bash
   python3 shipyard/scripts/shipyard_state.py init --project <name> --feature-branch <feature> \
       --base-branch <base> --protected <names> --breadth <0|1|2> --formal-rigour <C-10>
   ```

   If it refuses because `.ai/` files are already tracked, ask the person; never run `git rm` for them.

## 5. Gate

Show the recorded parameters in one block and ask for an explicit yes. On the literal yes:

```bash
python3 shipyard/scripts/shipyard_state.py gate P0 approve --by <login>
python3 shipyard/scripts/shipyard_state.py snapshot -m "P0: intake"
python3 shipyard/scripts/check.py --phase P0
```

The last command confirms discovery may start. Add the P0 phase-log row. Then tell the person to run
`/shipyard.discover`. Silence is not a yes.

# Dynamic workflows

Shipyard's three saved workflows run under Copilot CLI as **dynamic workflows**: ES modules in
`.github/extensions/<name>/extension.mjs`. They are the same three workflows as Shipyard's `workflows/*.js`, with the
same arguments, phases, statuses, caps, routing, dedupe rules and briefs. Only the runtime glue changed, and all of it
lives in `.github/extensions/shipyard-lib/index.mjs`.

Dynamic workflows are a **public preview** of Copilot CLI. They need `--experimental` (or `/experimental on` in a
session) and a trusted folder. See "What is preview or unverified" at the end before relying on any detail.

| Workflow | Folder | Shipyard phases | Ends with |
|---|---|---|---|
| `shipyard-discover` | `.github/extensions/shipyard-discover/` | P1 scan, P2 brainstorm, P3 draft | `NEEDS_HUMAN` (the P4 grill) or `BLOCKED` |
| `shipyard-plan` | `.github/extensions/shipyard-plan/` | P5 critique, P6 refine, P7 delivery plan | `AWAITING_PLAN_APPROVAL`, `NEEDS_HUMAN` or `BLOCKED` |
| `shipyard-slice` | `.github/extensions/shipyard-slice/` | P9 for one slice | `READY_FOR_HUMAN`, `NEEDS_SHARED_APPROVAL`, `ESCALATE`, `BLOCKED_REVIEWER` or `BLOCKED` |

A workflow never asks the human anything. It ends at a gate and the coordinator (`shipyard-coordinator`) presents
the result in chat. That keeps the upstream Shipyard plugin's ADR-0001 (the three-workflow split; this
repository's ADR-0001 covers the three modes). See `docs/decisions/ADR-0002-dynamic-workflows.md`.

## How a workflow runs

1. The coordinator, in a CLI session started with `copilot --experimental --agent=shipyard-coordinator`, asks for the
   workflow by name with its arguments ("run the shipyard-slice workflow with args …"). In CI or for a conformance
   test, `copilot workflow run` starts it headless (below).
2. The runtime validates the arguments against `meta.argsSchema` and calls `run(ctx)`.
3. `run(ctx)` builds the shared toolkit (`makeToolkit`): it loads the registry and the contracts, checks the
   workflow's own result contract major, and wires `call()`, `step()`, `parallel()`, `enter()` and `log()` to `ctx`.
4. Every specialist call goes through `call(role, mode, brief, label)`:
   - the brief is built by `brief()` with the Shipyard header lines (`Caller: shipyard:coordinator`, `Mode:`,
     `Slice:`, `Round:`, `Feature-branch:`, `Slice-branch:`, `Diff:`, `Read:`, `Write:`, `Budget:`);
   - the contract named in the registry for that role and mode is stripped of `$schema`, `$id`, `title`,
     `description` and `x-contract-version` and passed as `schema`;
   - `ctx.agent(prompt, { agent: "shipyard-<short>", model, reasoningEffort, label, schema })` runs the subagent;
   - the result is re-validated against the **full** contract inside `ctx.step`, because the runtime only enforces a
     structural subset (`type`, `required`, `enum`, `const`, nested `properties` and `items`, `anyOf`/`oneOf`/`allOf`;
     it ignores `pattern`, `minLength`, numeric ranges and `additionalProperties`);
   - a `null` or invalid result is retried once (`registry.limits.reviewerRetries`) under a new label, then the
     workflow fails closed (`BLOCKED`, or `BLOCKED_REVIEWER` for a reviewer).
5. Deterministic decisions (routing, dedupe, the grill frontier, slice ids, the test-plan gate verdict, pending
   SHARED tiers, verification failures, fix groups) run inside `ctx.step(key, fn)`, so a resumed run replays them
   instead of recomputing. Every step key and every agent label is unique within a run (a counter suffix), because
   the runtime memoises identical calls.
6. Fan-out uses `ctx.parallel`: goldfish lenses, implementer with verifier, reviewers, rebuttal answers, sequencing
   checks with the readiness goldfish.
7. The workflow returns one plain JSON object. The coordinator reads it; nothing else is written by the workflow.

The registry (`shipyard/registry/roles.json`) and the contracts (`shipyard/contracts/*.schema.json`) are read from
the repository when the arguments omit them, so a `--args` file only needs the workflow's own inputs. Passing them
explicitly (`registry`, `contracts`) still works and wins.

## Arguments

Common to all three: `registry`, `contracts` (optional, see above), `shipyardDir` (folder holding `registry/` and
`contracts/`, default `shipyard/` at the repository root), `agentSelection` (`"agent"`, the default, or
`"prompt"`; see the ADR).

### shipyard-discover

| Arg | Type | Meaning |
|---|---|---|
| `request` | string, required | The verbatim request. |
| `breadth` | 0, 1 or 2 | Brainstorm breadth: none, three lenses (default), five lenses plus an outsider sweep. |
| `constraints` | string or object | C-1..C-10 as recorded at P0. |
| `formalRigour` | `none`, `invariants`, `properties`, `model-checked` | C-10 (default `none`). |

Returns `status`, `topConcepts`, `gaps`, `questions` (each with `kind`, `dependsOn`, `status`), `frontier` (the first
grill round), `formalRigour`, `artifacts`, `disagreements`, `reason`.

### shipyard-plan

| Arg | Type | Meaning |
|---|---|---|
| `planFlags` | object | `publicContract`, `consumerVisible`, `concurrency`, `security`, `config`, `modelChecked`; absent or non-boolean means uncertain, and uncertain routes the reviewer. |
| `cycle` | integer | Refine cycles already used by earlier launches (0 on the first). The cap `planRefineCycles` counts across launches. |
| `answers` | string or object | The P4 answers. |
| `formalRigour` | tier | As above; `model-checked` routes the reliability reviewer to run the models. |

Returns `status`, `slices` (ids `01..NN`), `readiness`, `findings`, `openFindings` (when NEEDS_HUMAN),
`humanInputRequests`, `cyclesUsed` (relaunch with `cycle` set to it), `reviewersRouted`, `reviewersNotRouted`, `reason`.

### shipyard-slice

| Arg | Type | Meaning |
|---|---|---|
| `slice`, `featureBranch`, `sliceBranch` | strings, required | The approved slice and its branches (the coordinator has created and checked out the slice branch). |
| `round` | integer | Fix rounds already used (0 on a fresh run); the cap is `limits.fixRounds`. |
| `startAt` | `TEST_PLAN` or `VERIFY` | `VERIFY` resumes after a SHARED-tier decision without redoing the test plan or the build. |
| `sharedApproved` | list or map | Approved SHARED tier names, or `{tier: true/false}`. Data only. |
| `humanChanges` | list | Merge-gate change requests `{id, owner (implementer or verifier), finding, requiredResolution?, location?}`. The run starts at Fix, outside the round cap, and review re-runs in full. |
| `humanRound` | integer | 1, 2, … for successive change requests. |
| `pauseForShared` | boolean | Use `ctx.pause` for the SHARED-tier stop (interactive sessions only; see below). |

Returns a `slice-workflow-result` (contract `shipyard/contracts/slice-workflow-result.schema.json`): `status`,
`rounds`, `commit`, `verify`, `testPlan`, `reviewersRouted`, `reviewersNotRouted`, `findings`, `openFindings`,
`humanInputRequests`, `abilityVersions`, `authorNotes`, `humanChanges`, `reason`.

## Statuses and what the coordinator does next

| Status | Workflow | Next |
|---|---|---|
| `NEEDS_HUMAN` | discover, plan | Present the questions (discover: the `frontier`, capped at `limits.grillQuestionsPerRound`) or the open findings; record the answers; relaunch (plan: with `cycle: cyclesUsed`). |
| `AWAITING_PLAN_APPROVAL` | plan | Show `PLAN.HUMAN.md`; on a literal yes record the P8 gate (`shipyard_state.py gate P8 approve --by <login>`). |
| `READY_FOR_HUMAN` | slice | Write `EVIDENCE.md` and `REVIEW.HUMAN.md`; show the brief; on approval record the MERGE gate and merge `--no-ff`. |
| `NEEDS_SHARED_APPROVAL` | slice | Ask the human about the named SHARED tier(s); relaunch with `startAt: "VERIFY"`, `round: <rounds>` and `sharedApproved`. |
| `ESCALATE` | slice | Bring the open findings, the unmet rulings or the unfinished work to the human with options. |
| `BLOCKED_REVIEWER` | slice | A reviewer returned nothing valid twice; rerun or skip with the human's explicit say-so. |
| `BLOCKED` | all | A required specialist returned nothing valid twice, or an invariant failed (for example `TEST_PLAN.md` not `APPROVED` at VERIFY). The reason says which. |

### The SHARED-tier stop

By default a SHARED tier that needs approval ends the run with `NEEDS_SHARED_APPROVAL`, exactly as in Shipyard, and
the coordinator relaunches with `startAt: "VERIFY"`. That works in every mode, including headless runs, which cannot
resume. With `pauseForShared: true` the workflow calls `ctx.pause("shared-approval: <tiers>")` instead; if the
resumed run hands back `{ sharedApproved: {...} }` it continues at Verify in the same run, keeping the journaled test
plan and build. If the resume carries no decision the workflow falls back to `NEEDS_SHARED_APPROVAL`. This is the only
use of `ctx.pause`, and the shape of a resume payload is unverified (see below).

## Headless runs and CI conformance

`copilot workflow run` runs a workflow without a session. It shows no approval prompts, so permissions are granted up
front, and it cannot resume: treat `paused` as a failure in CI.

```shell
export GITHUB_COPILOT_PROMPT_MODE_EXTENSIONS=true   # load project extensions in an untrusted checkout
copilot --experimental --allow-tool=read --allow-tool='shell(git:*)' \
  workflow run shipyard-slice \
  --args @slice-args.json \
  --result-file slice-result.json \
  --silent --output-format json
echo "exit $?"
python3 shipyard/scripts/shipyard_validate.py slice-workflow-result slice-result.json
```

- Global flags (`--experimental`, `--allow-tool`, `--model`, `--add-dir`) go **before** `workflow`.
- `--args` takes inline JSON or `@file`; the arguments are validated against `argsSchema` first (exit 2 on failure).
- `--result-file` holds only the returned value and is written only after a completed run; check the exit code
  before reading it (0 completed; 1 paused, limit reached, cancelled or threw; 2 not found or bad arguments;
  130 interrupted). With `--output-format json` the last stdout line is a `workflow.result` record.
- `--agent`, `--fleet`, `--autopilot`, `--resume` and `--continue` are not supported with `workflow run`.
- Pin the CLI version in CI (`COPILOT_AUTO_UPDATE=false` and an explicit package version) and never run the
  conformance job on a fork's PR, because the checkout's `extension.mjs` executes with the job's privileges.

A conformance test runs `shipyard-slice` on `examples/sample-project` with a fixed `slice-args.json` and asserts on
`status`, `reviewersRouted` and `openFindings` in the result file. The node tests under `shipyard/tests/extensions/`
cover the same behaviours offline with a fake `ctx` (`npm test`, or `node --test shipyard/tests/extensions/`).

## Checks that guard the workflows

- `python3 shipyard/scripts/check.py` (repository hygiene): every `extension.mjs` exports
  `defineWorkflow({ meta, run })`, is named after its folder, imports only `../shipyard-lib/` (and the SDK), and uses
  no `Date.now`, `Math.random`, `new Date`, `process.env`, `fetch`, `require` or Node `fs`; the lib may read files
  but never the clock or the network.
- `check.py --phase SLICE` before a slice run and `check.py --phase MERGE` before a merge (the gates in
  `.ai/state.json`, the slice state, the touch sets, `TEST_PLAN.md` approved before the first code commit).
- `check.py --pr` in the `shipyard-slice-check` Action on every PR into the feature branch.
- `check.py --env` prints which guardrails are effective in CLI, cloud and IDE modes.

## What is preview or unverified

Confirmed by the GitHub docs: the folder layout (`.github/extensions/<name>/extension.mjs`, `~/.copilot/extensions/`),
`--experimental`, `copilot workflow run` with `--args @file`, `--result-file`, `--silent`, `--output-format json`, the
exit codes, `GITHUB_COPILOT_PROMPT_MODE_EXTENSIONS`, pause and resume as run states, and that limits can stop a run.

Documented only by a third party (treated as likely, not certain): the module shape
(`import { defineWorkflow, joinSession } from '@github/copilot-sdk/extension'`, then `joinSession({ workflows })`),
`meta.phases`, `meta.argsSchema`, `meta.limits` (`maxConcurrentSubagents`, `maxTotalSubagents`, `timeoutSeconds`,
`maxAiCredits`), `ctx.agent(prompt, { label, schema })` with null on failure and one automatic retry on a schema
mismatch, memoisation by label, the honoured schema subset, `ctx.step`, `ctx.parallel`, `ctx.pipeline`, `ctx.pause`,
`ctx.phase`, `ctx.log`, `ctx.signal`.

Verified on CLI 1.0.107 (2026-11-09), by mounting this repository with `copilot --plugin-dir`: the three workflows
register from `.github/extensions/` when `plugin.json` names that folder under `extensions`; `copilot --experimental
workflow run shipyard-discover --args '{}'` reaches the workflow and fails on its argument check ("Invalid
arguments"); `workflow run shipyard-plan --args '{}'` ran to the end and printed the workflow's own fail-closed
result (`{"status":"BLOCKED", "reason":"plan critique: no valid result after retry: …"}`), so the module shape,
`defineWorkflow`, `meta.argsSchema`, `ctx.agent`, `ctx.step`, the retry loop and the `node:fs` import in the lib
are all accepted by the runtime; and a plugin's workflows load without the project being a trusted folder, unlike
`.github/extensions/` in the project itself. Whether that empty-args run's subagents failed because `ctx.agent`
ignores the `agent` option or simply because they had nothing to critique is not yet known; run a real discover
first and compare `agentSelection: "agent"` with `"prompt"`. Plugin agent ids carry the plugin name (`shipyard:shipyard-discovery`);
the lib adds the prefix through `pluginAgentPrefix()` when it runs from a plugin.

Not documented anywhere we found, and not yet exercised end to end: whether `ctx.agent` accepts `agent` (a custom
agent name), `model` or `reasoningEffort`; what `ctx.pause` resolves to on resume; whether unknown `meta` keys are
rejected. The lib isolates each of these behind one switch or one function, and
`docs/decisions/ADR-0002-dynamic-workflows.md` lists how to confirm them with `copilot --help` and a two-line spike.

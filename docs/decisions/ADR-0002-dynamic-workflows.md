# ADR-0002: Port the saved workflows as Copilot CLI dynamic workflows

Status: accepted (preview-dependent; revisit when the extension API leaves preview)
Date: 2026-11-08

## Context

Shipyard's orchestration lives in three saved workflow scripts (`discover.js`, `plan.js`, `slice.js`). They hold
the order of calls, the caps (test-plan revisions, fix rounds, refine cycles), the reviewer routing, the findings
dedupe and the fail-closed rules. The upstream Shipyard plugin's ADR-0001 split the work into exactly three
workflows because a workflow cannot talk to the human: each one runs until a human gate and returns. (This
repository's `ADR-0001-three-modes.md` is a different decision: one procedure, three client modes.)

Copilot CLI has a public-preview feature with the same shape: **dynamic workflows**, ES modules in
`.github/extensions/<name>/extension.mjs` built with `defineWorkflow({ meta, run })`, where `ctx.agent` runs a
subagent with a schema, `ctx.step` journals deterministic work for resume, `ctx.parallel` fans out and `ctx.pause`
checkpoints. It is CLI-only, behind `--experimental`, and its authoring API is documented mainly by third parties.
The cloud coding agent and the IDEs have no workflow engine at all.

## Decision

1. **Keep the three-workflow split.** `shipyard-discover`, `shipyard-plan` and `shipyard-slice` are one-to-one
   ports of Shipyard's scripts: same arguments, phases, statuses, caps, routing, dedupe and briefs. A workflow still
   ends at a gate and never asks the human. The coordinator agent owns the chat and the gates, as in Shipyard.
   Reasons: the gates are the safety model; a workflow that paused for every human question would be unresumable in
   headless runs and would move the gate logic into a preview API; and keeping the split keeps the Shipyard tests
   portable (they ran unchanged in spirit against the ports).

2. **Isolate the runtime in one module.** Everything that touches `ctx` or the SDK lives in
   `.github/extensions/shipyard-lib/index.mjs`: `defineWorkflow` (shape check), `attach` (dynamic import of
   `@github/copilot-sdk/extension`, a no-op when absent), `makeToolkit` (`call`, `step`, `parallel`, `enter`,
   `log`), `brief`, `schemaFor`, a full JSON-schema validator, `agentOptions`, routing and dedupe. A change in the
   preview API is a change in one file. The workflow modules import nothing else.

3. **Re-validate every agent return.** The runtime enforces a structural subset of JSON Schema. The lib validates
   the full contract inside `ctx.step` after every `ctx.agent`, retries once under a new label, then fails closed.

4. **Journal deterministic decisions.** Routing, dedupe, the grill frontier, slice ids, the test-plan verdict,
   pending SHARED tiers and verification failures run in `ctx.step` with unique keys, so a resume replays them.
   Agent labels are unique within a run (a call counter), because the runtime memoises identical calls; without
   this, the architect's ruling follow-up call in a fix round would have returned the first call's result.

5. **`ctx.pause` only for the SHARED-tier stop, and only on request.** The default is Shipyard's
   `NEEDS_SHARED_APPROVAL` plus a relaunch with `startAt: "VERIFY"`, which works headless. `pauseForShared: true`
   switches to a durable pause that continues at Verify if the resume carries `sharedApproved`.

6. **Agent selection behind one switch.** Whether `ctx.agent` accepts a custom agent name and a model is
   unverified. `agentOptions(registry, role, mode, selection)` is the single place that decides:
   - `agentSelection: "agent"` (default): pass `agent: "shipyard-<short>"`, `model` and `reasoningEffort` from the
     registry's compute class;
   - `agentSelection: "prompt"`: pass only `label` and `schema`, and start the prompt with
     ``Act as `shipyard-<short>`: read .github/agents/shipyard-<short>.agent.md first …``.
   If the spike shows the runtime rejects unknown options, flip the default in `agentSelectionOf` and nothing else.

7. **Fallback where there is no engine.** In IDE mode (VS Code, JetBrains) and in the cloud coding agent, the
   coordinator follows the phase prompt files under `.github/prompts/` and calls the specialists directly as
   subagents. Order, caps and routing are instructions there, and `python3 shipyard/scripts/check.py --phase …`
   at the top of every prompt plus the `shipyard-slice-check` Action (`check.py --pr`) on every slice PR are the
   enforcement. The README and `check.py --env` state this as degraded fidelity.

## Consequences

- CLI mode has code-enforced caps and routing; IDE and cloud modes have convention plus after-the-fact checks.
- The node tests (`node --test shipyard/tests/extensions/`) exercise the ports with a fake `ctx` and cover every
  behaviour Shipyard's tests covered, plus the journal, label uniqueness, the pause and the selection switch.
- One deliberate deviation from the source: in `plan.js` the architect's recheck runs in `CRITIQUE` mode (it has
  no `RECHECK` mode), so a finding it forgot to list vanished. The port treats any recheck job (one that carries the
  reviewer's open findings) as a recheck, so the forgotten finding stays `OPEN`. That matches the stated rule.
- `meta.whenToUse` from Shipyard is folded into `meta.description`, because unknown `meta` keys may be rejected.

## Unverified points and how to confirm them

Run these in a trusted checkout with the pinned CLI version. Each takes minutes.

| Point | How to confirm |
|---|---|
| The SDK entry point and registration (`@github/copilot-sdk/extension`, `defineWorkflow`, `joinSession`) | `copilot --help` and `copilot workflow --help`; then in a session ask "Show me the guidance for writing dynamic workflows" (the docs say this guidance is built in) and compare the import line and the registration call with `attach()` in the lib. |
| Whether `ctx.agent` accepts `agent`, `model`, `reasoningEffort` | **Confirmed for `agent` and `model` on CLI 1.0.108 (2026-11-10)** from the CLI log of `copilot workflow run shipyard-plan --args '{}'`: a specialist with `disable-model-invocation: true` is rejected (`custom_agent_model_invocation_disabled`), without the flag it launches and returns a contract-valid result; `model` needs a Copilot id (`claude-opus-5.5`), the alias `opus` is logged as unavailable and the default model is used. `reasoningEffort` is accepted without complaint; whether it is honoured is still open. If `agent` is ever rejected again, set `agentSelection: "prompt"` (or flip the default). |
| Memoisation by label | Call `ctx.agent` twice with the same prompt and label and once with a new label; compare the subagent count in the run view. |
| The honoured schema subset | Return `{ ok: 'x' }` against `ok: { type: 'string', minLength: 5 }`; the runtime should accept it and the lib should reject it (this is why the lib re-validates). |
| What `ctx.pause(name)` resolves to on resume | Pause, resume from the run list, log the resolved value. Until known, `pauseForShared` stays off by default. |
| Node builtins (`fs`) inside an extension | The lib already imports `node:fs`; a load failure would surface as "workflow not found" (exit 2). If builtins are blocked, pass `registry` and `contracts` in `--args` (the lib's `loadInputs` prefers them). |
| Unknown `meta` keys | Add `whenToUse` to a fixture's meta and run it. |
| `subagentStart`/`subagentStop` hook matcher targets (hooks builder) | Out of scope here; see `docs/hooks.md`. |
| The `.agent.md` `model` ids per compute class (agents builder) | The registry's `computeClasses` currently carry Shipyard's names; `copilot --help` lists the valid model ids for `--model`. The lib passes the value through unchanged. |

## Alternatives considered

- **One workflow with `ctx.pause` at every human gate.** Rejected: headless runs cannot resume, the pause payload
  shape is unverified, and the gate rules would move into a preview API. The three-workflow split keeps the gates in
  the coordinator and in `check.py`.
- **GitHub Agentic Workflows (gh-aw) for the slice loop.** Rejected as the primary engine: read-only jobs with
  `safe-outputs` suit a CI reviewer sweep, not an interactive slice with fix rounds. It remains an optional add-on.
- **Inline the agent bodies in the prompt instead of naming custom agents.** Kept as the `prompt` selection
  fallback, not the default: the body is up to 30 000 characters per agent and would be repeated on every call.

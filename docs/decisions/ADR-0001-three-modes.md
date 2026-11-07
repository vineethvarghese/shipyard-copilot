# ADR-0001: One procedure, three modes, gates in `state.json`

Status: ACCEPTED · Date: 2026-11-08

## Context

Shipyard ran under one client with one set of levers: saved workflows that enforce order and caps in code, hooks
that know which agent is running, and a coordinator session that owns the chat at every gate. Copilot has three
clients with different levers:

- Copilot CLI has dynamic workflows (public preview, `--experimental`), agent-scoped hooks and a `task` tool.
- VS Code has custom agents, subagents with an `agents:` allowlist and handoff buttons, but no workflow runner and
  hooks only where the client supports agent-scoped ones (unverified).
- The Copilot coding agent has no interactive session at all: a task opens one pull request and ends.

Porting the method to the strongest client only would exclude most users; porting to the weakest would throw away
the enforcement the CLI offers.

## Decision

1. **One procedure.** The eleven phases, the four human stops, the `.ai/` folder, the contracts and the registry
   are the same in every mode. The agent bodies are shared; only how the three agent-only stretches run differs.
2. **Three modes, declared.** CLI runs P1–P3, P5–P7 and P9 as dynamic workflows (`shipyard-discover`,
   `shipyard-plan`, `shipyard-slice`); each workflow ends at a gate and never pauses for the human. IDE runs the
   same stretches by having the coordinator drive the specialists directly, following the phase prompt files under
   `.github/prompts/`. Cloud runs one task per phase, with the issue and the pull request as the gates.
3. **Gates live in `state.json`.** `shipyard_state.py gate <P0|P4|P8|MERGE> approve --by <login>` records every
   approval, and `check.py --phase <P>` refuses to run a phase whose gate is missing. This is what makes the modes
   mixable and what makes the IDE and cloud modes safe enough to use.
4. **Fidelity is stated, not implied.** The README and `docs/capability-map.md` label each mechanism full,
   degraded or manual per mode, and `docs/unenforced.md` lists what each mode does not enforce. A mode never claims
   a guarantee it does not have.
5. **Enforcement moves to the pull request where the client cannot enforce at write time.** The Actions checks
   (`shipyard-slice-check`, `shipyard-notes-guard`, `shipyard-plan-gate`) and the rulesets are the backstop in
   every mode and the only enforcement in cloud mode.

## Consequences

- CLI mode keeps Shipyard's guarantees closest; it is the recommended mode and the one the docs lead with.
- IDE mode is degraded: order, caps and routing are convention plus `check.py`. The prompt files are written so a
  human can read them as a checklist and see what should have happened.
- Cloud mode is manual: `.ai/` round-trips through an artifact and a sync workflow, hooks are a subset, and gates
  are labels and reviews. It is documented as such and must never be granted a ruleset bypass.
- Every rule has two homes: text in the agent and skill files, and a check somewhere a human can see it fail.
- The dynamic-workflow API is a moving target; the prompt files are the always-working fallback, and the
  coordinator falls back to them when the runner is absent.

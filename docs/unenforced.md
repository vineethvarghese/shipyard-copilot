# What is dropped, and what each mode does not enforce

The original Shipyard plugin enforced its hard rules with saved workflows and eight hooks that knew which agent was
running. Copilot does not give every client the same levers. This page is the honest list. Read it before trusting
a mode with something that matters. Points marked (unverified) have not been confirmed against a running client.

## Dropped

1. **`effort` per mode and `maxTurns` per agent.** No `.agent.md` keys for them. The CLI does take `--reasoning-effort` per launch (verified on 1.0.107), so the coordinator session's effort is settable; per-subagent effort is not. Replaced by `model` per agent,
   workflow `limits`, and the `Budget:` line in every brief.
2. **Plugin evals** (the original plugin's eval suites). Replaced by conformance runs on `examples/sample-project` (planned).
3. **Marketplace listing.** Not dropped any more: `copilot plugin install vineethvarghese/shipyard-copilot` installs the CLI
   plugin straight from the repository, and `install.sh` / `install.py` give a checksummed project install with
   `remove`. Only a marketplace entry is missing.
4. **The single-entry-point guarantee.** `Caller: shipyard-coordinator` stays as text in every specialist body;
   it is enforced only by the CLI `brief-check` hook on `task` calls and by `user-invocable: false` (hidden from
   pickers). `disable-model-invocation: true` is deliberately not set on the specialists: Copilot's
   model-invocation gate also rejects the dynamic workflows' `ctx.agent` launches of such an agent
   (`custom_agent_model_invocation_disabled`, CLI 1.0.108), so the flag would switch the workflows off.
5. **Hook retries.** `findings-gate` sends a reviewer back where `subagentStop` can `block`; the retry counter is
   best effort and keyed by session.

## Stated as unenforced, per mode

| Rule | CLI | IDE | Cloud |
|---|---|---|---|
| Hooks apply only to Shipyard agents | inferred from agent-scoped hooks (`SHIPYARD_ROLE`) and `state.json` | agent-scoped hooks where supported (unverified), else none | inferred from `state.json` → `activeRole` |
| Per-role write scope at write time | enforced (agent-scoped hooks) | `tools` restriction only; the pull-request check is the backstop | hook with the inferred role; the pull-request check is the backstop |
| Test plan before code at write time | enforced | unenforced; `shipyard-slice-check` catches it on the pull request | hook with the inferred role; pull-request check |
| Goldfish sees nothing in `.ai/` | enforced (agent-scoped hook) | unenforced; the brief carries only the verbatim request | unenforced |
| Schema-checked agent returns | enforced inside workflows (structural subset) | after the fact with `shipyard_validate.py` | after the fact |
| Loop caps and routing | code (the workflows) | convention in the prompt files, plus `check.py` | convention, plus `check.py` |
| Never push, never touch `main` | hook plus ruleset | ruleset | ruleset (Copilot has no bypass) |
| `.ai/` never on a work branch | hook (`git add` of `.ai` denied) plus `.git/info/exclude` plus `shipyard-notes-guard` | exclude plus `shipyard-notes-guard` | `shipyard-notes-guard` only; the exclude line is re-added by `copilot-setup-steps.yml` each task |
| Reviewer independence (no shared findings in the first pass) | code | convention | convention |
| Parallel implementer and verifier | `ctx.parallel` | sequential unless the client runs subagents in parallel | sequential |

## How role inference works, and why it is spoofable

Copilot's hook payload carries `toolName`, `toolArgs` and `cwd`, not the custom agent that is running. So the
hooks learn the role two ways:

1. **Agent-scoped hooks (CLI).** Each `.agent.md` carries its own `hooks:` block whose commands pass
   `SHIPYARD_ROLE=<short>`. The role comes from the agent file, not from state. This is the strong path.
2. **Repository hooks (`.github/hooks/shipyard.json`, cloud and CLI).** The hook reads `.ai/state.json` →
   `activeRole`, which the coordinator sets with `shipyard_state.py set-active-role <short>` before every
   delegation and clears afterwards.

A confused coordinator that forgets `set-active-role` weakens every per-role hook on the second path. The
backstops are the Actions checks on the pull request (`check.py --pr`: diff against touch sets, test-plan order,
findings files, evidence) and the rulesets on the remote.

## Top risks

1. **Dynamic workflows are a moving target.** Public preview, `--experimental`, authoring API documented mainly by
   third parties, no headless resume; `ctx.agent`'s `agent` and `model` options are verified on CLI 1.0.108,
   whether `reasoningEffort` is honoured is (unverified). Mitigation: the prompt files are the always-working
   fallback.
2. **Hook parity across clients.** CLI full, cloud subset (`ask` becomes `deny`, timeouts fail open), VS Code
   agent-scoped only (unverified), JetBrains preview. Mitigation: `check.py --env` prints the effective guardrails
   at startup; this page.
3. **Role inference is spoofable** (above). Mitigation: agent-scoped hooks in the CLI; Actions diff checks.
4. **Cloud-mode state fragility.** One pull request per task, a 59-minute cap, a fresh clone each task, `.ai/`
   round-tripped through an artifact and a sync workflow. Mitigation: every task posts a compact summary comment;
   `shipyard-notes-sync` is idempotent; cloud mode is documented as manual fidelity.
5. **Cost and prompt-injection surface.** Up to six DEEP reviewers plus goldfish fan-out per slice is many premium
   requests; the cloud agent and code review read instructions and skills from the pull request's head branch, so
   a malicious slice branch could alter the reviewers' instructions. Mitigation: `limits` in every workflow;
   CODEOWNERS on `.github/agents`, `skills`, `hooks`, `extensions` and `.ai/`; `shipyard-notes-guard` on every
   pull request.

Source: section D of [DESIGN.md](DESIGN.md).

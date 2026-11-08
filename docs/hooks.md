# Hooks under GitHub Copilot

Shipyard ships eight small Python scripts (standard library, Python 3.9+) that make its most important rules hard
to break. They live in `shipyard/scripts/hooks/`. This page says what they do under Copilot, which client runs
which of them, how the hooks learn which Shipyard role is running, and how to debug them. The rules themselves are
in `shipyard/scripts/hooks/README.source.md` (the original hook reference); nothing in the rules changed.

**Guardrails, not a sandbox.** The hooks look at tool calls by pattern. They stop the mistakes an agent is likely
to make. They cannot see what a program does once it runs. Keep branch protection and push protection on the remote
(see `docs/guardrails.md`); those are the real guarantees.

## How a hook runs

Copilot sends one JSON object on stdin, for example
`{"sessionId": "...", "timestamp": 1730000000000, "cwd": "/work/app", "toolName": "bash", "toolArgs": "{\"command\": \"git push\"}"}`.
`shipyard/scripts/hooks/copilot_hooklib.py` turns that into the shape the scripts were written for (`tool_name`,
`tool_input`, `cwd`, `agent_type`), maps the Copilot tool name onto the Claude name the scripts switch on, and
infers the Shipyard role. The script then runs unchanged.

A refusal is one JSON line on stdout plus the reason on stderr:

| Event | Refusal | Exit code |
|---|---|---|
| `preToolUse` | `{"permissionDecision": "deny", "permissionDecisionReason": "Shipyard <hook> blocked this: ..."}` | 2 |
| `subagentStop` | `{"decision": "block", "reason": "Shipyard findings-gate blocked this: ..."}` | 0 |
| `subagentStart` | never refuses (records the start time) | 0 |

Allow is exit 0 with nothing on stdout. For `preToolUse` the CLI and the cloud agent both treat exit 2 as deny and
both read the JSON, so either one is enough. For `subagentStop` exit 2 is only a warning, so the JSON carries the
decision and the exit code stays 0.

**Timeouts fail open.** Copilot kills a hook after `timeoutSec` (10 s for tool hooks, 15 s for the findings gate
in `.github/hooks/shipyard.json`) and continues as if it had allowed. The scripts are fast (one `git rev-parse`,
a few file reads), but a slow disk or a huge `SLICE.md` could pass the limit. Raise `timeoutSec` if you see
"hook timed out" in the CLI log. A hook that crashes while a Shipyard role is active denies (fail closed) and
says so; a hook that cannot even read its input allows.

## Which role is running

Copilot hook payloads do not say which custom agent is running a tool. The adapter looks, in this order:

1. **`SHIPYARD_ROLE`** in the environment. The agent-scoped hooks in each `.agent.md` set it
   (`SHIPYARD_ROLE=implementer python3 shipyard/scripts/hooks/write-scope.py`); see
   `shipyard/scripts/hooks/agent-hooks.md`. `SHIPYARD_ROLE=none` switches the hooks off for that process.
2. **The agent name in the payload.** `subagentStart` and `subagentStop` carry `agentName`; a tool call made
   inside a subagent may carry `agentType`. When it names a Shipyard agent (`shipyard-code-reviewer`,
   `shipyard:code-reviewer` or `code-reviewer`) that is the role.
3. **`activeRole` in `.ai/state.json`.** The coordinator runs `python3 shipyard/scripts/shipyard_state.py
   set-active-role <role>` before each delegation and `set-active-role none` after it.
4. **No role**: the hook exits 0 and prints nothing. A plain Copilot session in a repository that contains this
   template is never affected.

The role becomes `agent_type = shipyard:<role>`, so the per-role tables in the hook reference apply as written.

**Limits of this rule.** Sources 2 and 3 are inferred, not proven:

- `activeRole` is a file in the working tree. Any agent with a write tool, and any human, can change it. A stale
  value (the coordinator forgot `set-active-role none`) makes the hooks apply the wrong role to the next tool
  call; a wrong value weakens every per-role rule. Only agent-scoped hooks (source 1) carry the role from the agent
  definition itself. `check.py` and the PR checks in `.github/workflows` are the backstop: they compare the diff
  with the slice touch sets after the fact.
- An unknown value in `activeRole` (a typo) is passed through, so write-scope denies every write with "unknown
  Shipyard agent" rather than silently allowing it. `set-active-role` refuses unknown names, so this only happens
  when the file is edited by hand.
- Whether a live client fills `agentType` on tool calls inside a custom agent, and whether `agentName` is the
  frontmatter `name` or the file name, is not documented (unverified). The adapter accepts both spellings.

## What each hook blocks, per client

| Hook | Copilot event and tools | Blocks |
|---|---|---|
| `protect-branches.py` | `preToolUse` on shell tools | `git push`, history rewrites, commits on protected branches, merges by anyone but the coordinator, `gh pr merge` and `gh pr create` |
| `readonly-bash.py` | `preToolUse` on shell tools | installs, git state changes, deletes and writes outside `.ai/` for discovery, goldfish, architect, planner and the six reviewers |
| `write-scope.py` | `preToolUse` on shell, create and edit tools | writes outside the role's allowed paths; the implementer outside the code touch set; the verifier outside the test touch set; anyone flipping a test plan to APPROVED except the code-reviewer through one exact edit |
| `test-plan-gate.py` | `preToolUse` on shell, create and edit tools | implementer or verifier writes outside `.ai/` while the active slice's `TEST_PLAN.md` is not `Status: APPROVED` |
| `secrets-guard.py` | `preToolUse` on create and edit tools | content that looks like a secret written under `.ai/` |
| `goldfish-blinders.py` | `preToolUse` on read and search tools | the goldfish reading or searching `.ai/` except a `SLICE.md` |
| `brief-check.py` | `preToolUse` on task and agent tools | the coordinator briefing a Shipyard agent without `Caller: shipyard:coordinator`, a valid `Mode:`, or a `Round:` within the cap |
| `findings-gate.py` | `subagentStart`, `subagentStop` | a reviewer stopping without a findings file that parses and was written during this run; sent back at most 3 times (counter in the system temp folder, keyed by session id and reviewer) |

The tool names each matcher lists are in `.github/hooks/shipyard.json`. They cover the names the hooks reference
documents for the CLI and the cloud agent (`bash`, `powershell`, `create`, `edit`, `str_replace_editor`,
`apply_patch`, `view`, `grep`, `rg`, `glob`, `task`) plus the names VS Code and JetBrains use (`runCommands`,
`editFiles`, `runSubagent`, `codebase`, and others). A tool name outside the list runs no hook.

| Client | What runs | What does not |
|---|---|---|
| **Copilot CLI** | Everything: `.github/hooks/shipyard.json` (role from `activeRole`) and the agent-scoped hooks in each `.agent.md` (role from the agent file). All events, deny and block honoured. | `ask` decisions become `deny` in autopilot mode. |
| **Copilot cloud agent** | `.github/hooks/*.json` only, `bash` entries only, from the default branch. `preToolUse` deny and `subagentStop` block work. Role comes from `activeRole` or the subagent name. | Agent-scoped hooks; `powershell` entries; hooks that need a host outside the firewall allow list. Goldfish isolation is unenforced in practice because the role is inferred. |
| **VS Code** | Agent-scoped hooks in `.agent.md` (release notes; not in the reference page, unverified) with the role from the agent file. | The repository hook file, unless a later release reads it (unverified). Tool restrictions in `tools:` are the main guard. |
| **JetBrains** | Hooks are in public preview; treat as unverified. | Everything until you have tested it in your IDE. |

Under Claude Code the same scripts still work: a snake_case payload with `agent_type: shipyard:<role>` takes the
original path (reason on stderr, exit 2, no JSON).

## Settings

`.github/copilot/settings.json` is the repository-level CLI settings file. It sets `disableAllHooks: false` and
`effortLevel: "high"`. Both apply only when the working directory is trusted (`copilot --trust-folder` or the
interactive trust prompt). A personal `.github/copilot/settings.local.json` overrides it; keep that file out of
git.

## Setting the active role (coordinator)

```bash
python3 shipyard/scripts/shipyard_state.py set-active-role implementer   # before delegating
python3 shipyard/scripts/shipyard_state.py set-active-role none          # after the delegation returns
python3 shipyard/scripts/shipyard_state.py gate P8 approve --by <login>  # record a human gate
```

`gate` appends `{gate, by, at, slice}` to `gates` in `state.json`; `at` is the committer date of `HEAD` when the
repository has a commit, else the current UTC time. `MERGE` needs `--slice <id>` or an active slice.

## Debugging

1. Read the reason. It is on stderr and inside the JSON on stdout; it names the rule and the file or branch.
2. Set `SHIPYARD_HOOK_DEBUG=1` in the environment that starts Copilot (or in the hook entry's `env`). Each hook
   then writes one line to stderr with the event, the mapped tool name, the role and where the role came from
   (`env`, `payload:agentName`, `state.json`), followed by its decision.
3. Check `.ai/state.json` (`activeRole`, `activeSlice`, `sliceBranch`, `featureBranch`) and the active
   `SLICE.md` touch-set headings.
4. Run a hook by hand with a Copilot payload:

```bash
printf '{"sessionId":"s","timestamp":0,"cwd":"%s","toolName":"bash","toolArgs":"{\\"command\\":\\"git push\\"}"}' "$PWD" \
  | SHIPYARD_ROLE=implementer SHIPYARD_HOOK_DEBUG=1 python3 shipyard/scripts/hooks/protect-branches.py; echo "exit $?"
```

For the findings gate add `--event subagentStop` and send
`{"sessionId":"s","cwd":"<repo>","agentName":"shipyard-code-reviewer","response":"done","stopReason":"end_turn"}`.

5. `SHIPYARD_PROJECT_DIR=<repo>` pins the project folder when Copilot was started in a subfolder (by default the
   adapter walks up from `cwd` to the first folder with `.ai/state.json`, then to the git root).

## Tests

```bash
python3 -m unittest discover -s shipyard/tests/hooks
```

`test_copilot_payloads.py` covers the Copilot shape (role sources, aliases, the JSON decisions, the findings-gate
retry cap); `test_wiring.py` binds `.github/hooks/shipyard.json` to the scripts and the alias table; the other
files are the original rule tests with Claude-shaped payloads, unchanged.


## Verified against Copilot CLI 1.0.107 (2026-11-08)

These points were observed on a real CLI session in this repository and are no longer unverified:

- The repository hook file `.github/hooks/shipyard.json` is loaded once the folder is trusted (`--trust-folder` for a
  prompt-mode session, or the folder in `trustedFolders`). Without trust the CLI prints a warning and skips it.
- A `preToolUse` deny is honoured: the agent sees `Denied by preToolUse hook: Shipyard write-scope blocked this: …`
  and the file is not written.
- Tool names and argument shapes seen: `view` with `toolArgs` as a JSON object (`{"path": "...", "view_range":
  [1, 3]}`), and `apply_patch` with `toolArgs` as the raw patch text (`*** Begin Patch` / `*** Add File: <path>` /
  `+line` / `*** End Patch`). The adapter parses `Add`, `Update`, `Delete` and `Move to` headers and the hooks check
  every file in a multi-file patch. `--allow-tool 'create'` does not cover `apply_patch`; allow the tool by its real
  name.
- `user-invocable: false` does not stop `copilot --agent=<specialist>` from loading the agent. The caller check in
  each specialist's body does the refusing, as designed.
- The CLI warns `unknown fields ignored: agents, handoffs` on the coordinator file. Those keys are read by VS Code
  only; the warning is harmless.
- `--trust-folder` works only with `-p`, so `copilot workflow run` needs the folder in `trustedFolders`.
- `--reasoning-effort none|minimal|low|medium|high|xhigh|max` and `--model` exist as launch flags, so the
  coordinator session's effort can be set per launch. An administrator-managed model setting can override `--model`.
- All 13 skills under `.github/skills` and all 5 instruction files are discovered (`copilot skill list`,
  `copilot instruction list`).

- End to end, in a scratch repository with `.ai/state.json`, an active slice and a `DRAFT` test plan: the
  implementer's write inside the code touch set was refused by test-plan-gate ("test plan first"); after the plan
  was set to `APPROVED` the same write landed, and a write into the test touch set was refused by write-scope
  ("Tests belong to shipyard:verifier"). Hooks run before Copilot's own permission prompt.
- Run Copilot from the folder that holds `.github/`: started from a subfolder, the repository hooks were not loaded.
- Copilot's permission name for file writes is `write` (`--allow-tool 'write'`); `--allow-tool 'edit'` or `'create'`
  do not cover `apply_patch`.
- Hook processes receive the full environment of the Copilot process plus `COPILOT_PROJECT_DIR`, `COPILOT_HOOK_DIR`
  and `COPILOT_HOOK_DEPTH`. A Copilot session started from inside a Claude Code session therefore inherits that
  session's `CLAUDE_PROJECT_DIR`, which points at the wrong repository. The hooks resolve the project as
  `SHIPYARD_PROJECT_DIR`, then `COPILOT_PROJECT_DIR`, then `CLAUDE_PROJECT_DIR`, then the nearest `.ai/state.json`
  above the working directory.

Still unverified: whether `agentName` in subagent payloads is the frontmatter name, VS Code and JetBrains hook
behaviour, whether `matcher` is honoured inside agent frontmatter, and everything about dynamic workflows (the
folder must be in `trustedFolders` first; see docs/workflows.md).

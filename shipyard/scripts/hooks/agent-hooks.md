# Agent-scoped hooks for the Shipyard `.agent.md` files

Copilot CLI runs the hooks declared in a custom agent's frontmatter only while that agent is selected. That is the
one place where a hook knows for sure which Shipyard role is running, so each block below passes the role to the
script with `SHIPYARD_ROLE=<role>`. The scripts then behave exactly as they do under Claude Code.

Paste the block for the role into the frontmatter of `.github/agents/shipyard-<role>.agent.md`, between the
`---` lines, after `tools:`. Paths resolve from the repository root. The repository-level file
`.github/hooks/shipyard.json` keeps running too (it infers the role from `.ai/state.json`); when both fire, every
entry runs and any deny wins.

What the docs say and do not say:

- Documented: a `hooks` map in the agent frontmatter, keyed by event name (runtime names such as `preToolUse`
  or aliases such as `PreToolUse`), entries with `type: command`, `command` (fallback) and `windows`, `linux`,
  `osx` overrides; CLI only; eight consecutive scoped blocks are ignored thereafter; timeouts still apply.
- Not documented, so unverified: whether `matcher` and `timeoutSec` are honoured inside the frontmatter (they are
  in `.github/hooks/*.json`). The blocks carry them anyway; if a client ignores the matcher, the script still
  exits 0 for tools it does not handle, so the only cost is an extra process per tool call.
- `SHIPYARD_ROLE=<role> python3 ...` needs a POSIX shell. The `windows:` line sets the variable in PowerShell; if
  the Windows client runs `cmd.exe`, replace it with `cmd /c "set SHIPYARD_ROLE=<role>&& python3 ..."` (unverified).
- VS Code: agent-scoped hooks exist per the release notes, with the same frontmatter (unverified against a
  reference page). JetBrains hooks are in preview. The cloud agent ignores agent-scoped hooks.

Role values: `coordinator`, `discovery`, `goldfish`, `architect`, `planner`, `implementer`, `verifier`,
`code-reviewer`, `security-reviewer`, `contract-reviewer`, `integration-reviewer`, `reliability-reviewer`,
`simplicity-reviewer`.

## Matchers

Two matcher strings are reused below. They must match the full tool name (Copilot anchors them).

- `SHELL`: `bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command`
- `WRITE`: `create|write|write_file|create_file|edit|str_replace|str_replace_editor|str_replace_based_edit_tool|apply_patch|edit_file|editFiles|insert_edit_into_file|replace_string_in_file|multi_edit|insert`
- `READ`: `view|read|read_file|grep|rg|glob|search|grep_search|file_search|codebase|semantic_search|list_dir|list_code_usages`
- `TASK`: `task|agent|runSubagent|run_subagent|custom-agent|custom_agent|spawn_agent|delegate`

Write the string out in full in the YAML; the names above are only shorthand for this document.

## shipyard-coordinator

```yaml
hooks:
  preToolUse:
    - type: command
      matcher: "task|agent|runSubagent|run_subagent|custom-agent|custom_agent|spawn_agent|delegate"
      command: SHIPYARD_ROLE=coordinator python3 shipyard/scripts/hooks/brief-check.py
      windows: $env:SHIPYARD_ROLE='coordinator'; python3 shipyard/scripts/hooks/brief-check.py
      timeoutSec: 10
    - type: command
      matcher: "bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command"
      command: SHIPYARD_ROLE=coordinator python3 shipyard/scripts/hooks/protect-branches.py
      windows: $env:SHIPYARD_ROLE='coordinator'; python3 shipyard/scripts/hooks/protect-branches.py
      timeoutSec: 10
    - type: command
      matcher: "bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command|create|write|write_file|create_file|edit|str_replace|str_replace_editor|str_replace_based_edit_tool|apply_patch|edit_file|editFiles|insert_edit_into_file|replace_string_in_file|multi_edit|insert"
      command: SHIPYARD_ROLE=coordinator python3 shipyard/scripts/hooks/write-scope.py
      windows: $env:SHIPYARD_ROLE='coordinator'; python3 shipyard/scripts/hooks/write-scope.py
      timeoutSec: 10
    - type: command
      matcher: "create|write|write_file|create_file|edit|str_replace|str_replace_editor|str_replace_based_edit_tool|apply_patch|edit_file|editFiles|insert_edit_into_file|replace_string_in_file|multi_edit|insert"
      command: SHIPYARD_ROLE=coordinator python3 shipyard/scripts/hooks/secrets-guard.py
      windows: $env:SHIPYARD_ROLE='coordinator'; python3 shipyard/scripts/hooks/secrets-guard.py
      timeoutSec: 10
```

## shipyard-implementer and shipyard-verifier

Same block for both; replace `implementer` with `verifier` in every line of the verifier's copy.

```yaml
hooks:
  preToolUse:
    - type: command
      matcher: "bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command"
      command: SHIPYARD_ROLE=implementer python3 shipyard/scripts/hooks/protect-branches.py
      windows: $env:SHIPYARD_ROLE='implementer'; python3 shipyard/scripts/hooks/protect-branches.py
      timeoutSec: 10
    - type: command
      matcher: "bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command|create|write|write_file|create_file|edit|str_replace|str_replace_editor|str_replace_based_edit_tool|apply_patch|edit_file|editFiles|insert_edit_into_file|replace_string_in_file|multi_edit|insert"
      command: SHIPYARD_ROLE=implementer python3 shipyard/scripts/hooks/write-scope.py
      windows: $env:SHIPYARD_ROLE='implementer'; python3 shipyard/scripts/hooks/write-scope.py
      timeoutSec: 10
    - type: command
      matcher: "bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command|create|write|write_file|create_file|edit|str_replace|str_replace_editor|str_replace_based_edit_tool|apply_patch|edit_file|editFiles|insert_edit_into_file|replace_string_in_file|multi_edit|insert"
      command: SHIPYARD_ROLE=implementer python3 shipyard/scripts/hooks/test-plan-gate.py
      windows: $env:SHIPYARD_ROLE='implementer'; python3 shipyard/scripts/hooks/test-plan-gate.py
      timeoutSec: 10
    - type: command
      matcher: "create|write|write_file|create_file|edit|str_replace|str_replace_editor|str_replace_based_edit_tool|apply_patch|edit_file|editFiles|insert_edit_into_file|replace_string_in_file|multi_edit|insert"
      command: SHIPYARD_ROLE=implementer python3 shipyard/scripts/hooks/secrets-guard.py
      windows: $env:SHIPYARD_ROLE='implementer'; python3 shipyard/scripts/hooks/secrets-guard.py
      timeoutSec: 10
```

## shipyard-goldfish

```yaml
hooks:
  preToolUse:
    - type: command
      matcher: "view|read|read_file|grep|rg|glob|search|grep_search|file_search|codebase|semantic_search|list_dir|list_code_usages"
      command: SHIPYARD_ROLE=goldfish python3 shipyard/scripts/hooks/goldfish-blinders.py
      windows: $env:SHIPYARD_ROLE='goldfish'; python3 shipyard/scripts/hooks/goldfish-blinders.py
      timeoutSec: 10
    - type: command
      matcher: "bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command"
      command: SHIPYARD_ROLE=goldfish python3 shipyard/scripts/hooks/readonly-bash.py
      windows: $env:SHIPYARD_ROLE='goldfish'; python3 shipyard/scripts/hooks/readonly-bash.py
      timeoutSec: 10
    - type: command
      matcher: "bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command|create|write|write_file|create_file|edit|str_replace|str_replace_editor|str_replace_based_edit_tool|apply_patch|edit_file|editFiles|insert_edit_into_file|replace_string_in_file|multi_edit|insert"
      command: SHIPYARD_ROLE=goldfish python3 shipyard/scripts/hooks/write-scope.py
      windows: $env:SHIPYARD_ROLE='goldfish'; python3 shipyard/scripts/hooks/write-scope.py
      timeoutSec: 10
```

## shipyard-discovery, shipyard-architect, shipyard-planner

Same block for the three; replace `discovery` with `architect` or `planner` in every line.

```yaml
hooks:
  preToolUse:
    - type: command
      matcher: "bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command"
      command: SHIPYARD_ROLE=discovery python3 shipyard/scripts/hooks/readonly-bash.py
      windows: $env:SHIPYARD_ROLE='discovery'; python3 shipyard/scripts/hooks/readonly-bash.py
      timeoutSec: 10
    - type: command
      matcher: "bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command"
      command: SHIPYARD_ROLE=discovery python3 shipyard/scripts/hooks/protect-branches.py
      windows: $env:SHIPYARD_ROLE='discovery'; python3 shipyard/scripts/hooks/protect-branches.py
      timeoutSec: 10
    - type: command
      matcher: "bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command|create|write|write_file|create_file|edit|str_replace|str_replace_editor|str_replace_based_edit_tool|apply_patch|edit_file|editFiles|insert_edit_into_file|replace_string_in_file|multi_edit|insert"
      command: SHIPYARD_ROLE=discovery python3 shipyard/scripts/hooks/write-scope.py
      windows: $env:SHIPYARD_ROLE='discovery'; python3 shipyard/scripts/hooks/write-scope.py
      timeoutSec: 10
    - type: command
      matcher: "create|write|write_file|create_file|edit|str_replace|str_replace_editor|str_replace_based_edit_tool|apply_patch|edit_file|editFiles|insert_edit_into_file|replace_string_in_file|multi_edit|insert"
      command: SHIPYARD_ROLE=discovery python3 shipyard/scripts/hooks/secrets-guard.py
      windows: $env:SHIPYARD_ROLE='discovery'; python3 shipyard/scripts/hooks/secrets-guard.py
      timeoutSec: 10
```

## The six reviewers

Same block for `code-reviewer`, `security-reviewer`, `contract-reviewer`, `integration-reviewer`,
`reliability-reviewer` and `simplicity-reviewer`; replace `code-reviewer` in every line. The `Stop` entry is the
findings gate: a subagent's scoped `Stop` runs as `subagentStop`, and `--event subagentStop` tells the script
which event it is (the Copilot payload does not say). The start time comes from the repository-level
`subagentStart` entry in `.github/hooks/shipyard.json`; without it the gate checks the newest findings file.

```yaml
hooks:
  preToolUse:
    - type: command
      matcher: "bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command"
      command: SHIPYARD_ROLE=code-reviewer python3 shipyard/scripts/hooks/readonly-bash.py
      windows: $env:SHIPYARD_ROLE='code-reviewer'; python3 shipyard/scripts/hooks/readonly-bash.py
      timeoutSec: 10
    - type: command
      matcher: "bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command"
      command: SHIPYARD_ROLE=code-reviewer python3 shipyard/scripts/hooks/protect-branches.py
      windows: $env:SHIPYARD_ROLE='code-reviewer'; python3 shipyard/scripts/hooks/protect-branches.py
      timeoutSec: 10
    - type: command
      matcher: "bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command|create|write|write_file|create_file|edit|str_replace|str_replace_editor|str_replace_based_edit_tool|apply_patch|edit_file|editFiles|insert_edit_into_file|replace_string_in_file|multi_edit|insert"
      command: SHIPYARD_ROLE=code-reviewer python3 shipyard/scripts/hooks/write-scope.py
      windows: $env:SHIPYARD_ROLE='code-reviewer'; python3 shipyard/scripts/hooks/write-scope.py
      timeoutSec: 10
    - type: command
      matcher: "create|write|write_file|create_file|edit|str_replace|str_replace_editor|str_replace_based_edit_tool|apply_patch|edit_file|editFiles|insert_edit_into_file|replace_string_in_file|multi_edit|insert"
      command: SHIPYARD_ROLE=code-reviewer python3 shipyard/scripts/hooks/secrets-guard.py
      windows: $env:SHIPYARD_ROLE='code-reviewer'; python3 shipyard/scripts/hooks/secrets-guard.py
      timeoutSec: 10
  Stop:
    - type: command
      command: SHIPYARD_ROLE=code-reviewer python3 shipyard/scripts/hooks/findings-gate.py --event subagentStop
      windows: $env:SHIPYARD_ROLE='code-reviewer'; python3 shipyard/scripts/hooks/findings-gate.py --event subagentStop
      timeoutSec: 15
```

## Checking a block by hand

```bash
printf '{"sessionId":"s","timestamp":0,"cwd":"%s","toolName":"bash","toolArgs":"{\\"command\\":\\"git push\\"}"}' "$PWD" \
  | SHIPYARD_ROLE=implementer SHIPYARD_HOOK_DEBUG=1 python3 shipyard/scripts/hooks/protect-branches.py; echo "exit $?"
```

Expected: the reason on stderr, one JSON line `{"permissionDecision": "deny", ...}` on stdout, exit 2.

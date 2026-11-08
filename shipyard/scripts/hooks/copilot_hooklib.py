"""Copilot payload adapter for the Shipyard hooks (Python 3.9+, standard library only).

The eight hook scripts were written for Claude Code, whose hook input looks like
``{"tool_name": "Bash", "tool_input": {"command": ...}, "agent_type": "shipyard:implementer", "cwd": ...}``.
GitHub Copilot sends ``{"sessionId", "timestamp", "cwd", "toolName", "toolArgs"}`` for tool events and
``{"sessionId", "cwd", "agentName", "agentType", "agentId", "transcriptPath", "response", "stopReason"}``
for subagent events, and it does not say which Shipyard role is running. This module turns a Copilot payload
into the Claude shape so the hook logic runs unchanged.

Role inference (first match wins):

1. ``SHIPYARD_ROLE`` in the environment (agent-scoped hooks set it, for example
   ``SHIPYARD_ROLE=implementer python3 shipyard/scripts/hooks/write-scope.py``).
2. The agent name in the payload (``agentName`` or ``agentType``) when it names a Shipyard role, for example
   ``shipyard-code-reviewer``. Subagent events always carry it; tool events carry it only inside a subagent,
   and only when the client fills it in.
3. ``activeRole`` in ``.ai/state.json``, which the coordinator sets before each delegation.
4. No role: the hook does nothing (exit 0, no output). A plain Copilot session is never affected.

A role becomes ``agent_type = "shipyard:<role>"``. ``shipyard_hooklib`` then applies its usual fail-closed rule
for Shipyard agents: an internal error denies.

Output: for ``preToolUse`` a denial prints ``{"permissionDecision": "deny", "permissionDecisionReason": ...}``
on stdout and exits 2 (Copilot CLI and the cloud agent both honour exit 2 and the JSON). For ``subagentStop`` a
denial prints ``{"decision": "block", "reason": ...}`` and exits 0, because exit 2 is only a warning for that
event. Allow is exit 0 with no output.
"""

import json
import os
import re

SHIPYARD_PREFIX = "shipyard:"

# The thirteen Shipyard roles (registry/roles.json, `agent` values without the `shipyard:` prefix).
ROLES = ("coordinator", "discovery", "goldfish", "architect", "planner", "implementer", "verifier",
         "code-reviewer", "security-reviewer", "contract-reviewer", "integration-reviewer",
         "reliability-reviewer", "simplicity-reviewer")

# Copilot tool names (CLI, cloud agent, VS Code, JetBrains) grouped by the Claude name the hooks switch on.
# Matching is case-insensitive and ignores `-`/`_` differences, so `runSubagent`, `run_subagent` and
# `run-subagent` are one alias. Keep `.github/hooks/shipyard.json` and `agent-hooks.md` in step with this table.
TOOL_ALIASES = {
    "Bash": ("bash", "shell", "powershell", "execute", "exec", "sh", "terminal", "run_in_terminal",
             "run_command", "run_commands", "run_terminal_cmd", "execute_command", "run_shell_command",
             "shell_command", "command"),
    "Write": ("create", "write", "write_file", "create_file", "write_to_file", "new_file", "save_file"),
    "Edit": ("edit", "str_replace", "str_replace_editor", "str_replace_based_edit_tool", "apply_patch",
             "edit_file", "edit_files", "insert_edit_into_file", "replace_string_in_file", "multi_edit",
             "insert", "patch", "text_editor", "editor", "notebook_edit", "edit_notebook_file"),
    "Read": ("view", "read", "read_file", "cat", "open_file", "get_file_contents", "view_file",
             "notebook_read", "read_notebook"),
    "Grep": ("grep", "rg", "ripgrep", "search", "grep_search", "text_search", "search_files",
             "codebase", "semantic_search", "search_code", "list_code_usages", "usages"),
    "Glob": ("glob", "file_search", "find_files", "list_dir", "list_files", "ls", "find", "list_directory",
             "directory_tree"),
    "Agent": ("task", "agent", "run_subagent", "custom_agent", "spawn_agent", "delegate", "subagent",
              "run_agent", "invoke_agent", "delegate_task"),
}

# Argument keys per Claude name: (claude key, copilot candidates in priority order).
_ARG_KEYS = {
    "Bash": (("command", ("command", "cmd", "commandLine", "command_line", "script", "input", "code")),
             ("description", ("description", "explanation")),
             ("timeout", ("timeout", "timeoutSec", "timeout_ms"))),
    "Write": (("file_path", ("path", "file_path", "filePath", "file", "filename", "target_file", "uri")),
              ("content", ("content", "file_text", "text", "contents", "code", "new_content", "data"))),
    "Edit": (("file_path", ("path", "file_path", "filePath", "file", "filename", "target_file", "uri")),
             ("old_string", ("old_str", "old_string", "oldString", "oldText", "old_text", "search", "find")),
             ("new_string", ("new_str", "new_string", "newString", "newText", "new_text", "replace",
                             "replacement", "code", "content", "text")),
             ("replace_all", ("replace_all", "replaceAll", "all"))),
    "Read": (("file_path", ("path", "file_path", "filePath", "file", "filename", "target_file", "uri")),),
    "Grep": (("pattern", ("pattern", "query", "regex", "regexp", "search", "text", "searchString")),
             ("path", ("path", "dir", "directory", "cwd", "root", "folder", "includePattern_path")),
             ("glob", ("glob", "include", "includePattern", "include_pattern", "file_pattern")),
             ("output_mode", ("output_mode", "outputMode", "mode"))),
    "Glob": (("pattern", ("pattern", "glob", "globPattern", "glob_pattern", "query", "filePattern")),
             ("path", ("path", "dir", "directory", "cwd", "root", "folder"))),
    "Agent": (("subagent_type", ("agent", "agent_type", "agentType", "subagent_type", "agentName",
                                 "agent_name", "name", "type", "subagent")),
              ("prompt", ("prompt", "task", "description", "input", "message", "instructions", "query")),
              ("description", ("description", "label", "title"))),
}

_COPILOT_MARKERS = ("toolName", "toolArgs", "sessionId", "agentName", "stopReason", "transcriptPath")


def _norm(name):
    return re.sub(r"[-_\s]", "", name.strip().lower()) if isinstance(name, str) else ""


_ALIAS_INDEX = {}
for _claude, _names in TOOL_ALIASES.items():
    for _n in _names:
        _ALIAS_INDEX[_norm(_n)] = _claude
    _ALIAS_INDEX[_norm(_claude)] = _claude  # Claude names pass through (MultiEdit etc. are mapped below)
_ALIAS_INDEX.update({_norm("MultiEdit"): "Edit", _norm("NotebookEdit"): "Edit", _norm("Task"): "Agent"})


def is_copilot_payload(data):
    """True when the hook input carries Copilot's camelCase fields rather than Claude Code's."""
    if not isinstance(data, dict):
        return False
    if "tool_name" in data or "hook_event_name" in data:
        return False
    return any(k in data for k in _COPILOT_MARKERS)


def claude_tool_name(name):
    """Map a Copilot tool name to the Claude name the hooks use, or return it unchanged when unknown."""
    if not isinstance(name, str) or not name.strip():
        return ""
    return _ALIAS_INDEX.get(_norm(name), name.strip())


def parse_args(raw, claude_name):
    """toolArgs is a JSON string in the CLI, sometimes already an object. Return a dict."""
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if text:
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str):
                text = parsed
            if claude_name == "Bash":
                return {"command": text}
            if claude_name in ("Edit", "Write") and _PATCH_FILE_RX.search(text):
                # `apply_patch` (the CLI's file-writing tool, observed 2026-11) sends the patch text itself as
                # toolArgs, not a JSON object.
                return {"patch": text}
    return {}


def _pick(args, candidates):
    for key in candidates:
        if key in args:
            return args[key]
    return None


_PATCH_FILE_RX = re.compile(r"^\*\*\*\s+(Add|Update|Delete)\s+File:\s*(.+?)\s*$", re.M)
_PATCH_MOVE_RX = re.compile(r"^\*\*\*\s+Move\s+to:\s*(.+?)\s*$", re.M)


def parse_patch(patch):
    """Split an `apply_patch` document into (kind, path, added_text) per file. Kinds: Add, Update, Delete.
    A `*** Move to:` line adds the destination as a second Update target."""
    out = []
    current = None
    for line in patch.splitlines():
        m = _PATCH_FILE_RX.match(line)
        if m:
            current = [m.group(1), m.group(2).strip(), []]
            out.append(current)
            continue
        mv = _PATCH_MOVE_RX.match(line)
        if mv:
            out.append(["Update", mv.group(1).strip(), []])
            continue
        if current is not None and line.startswith("+") and not line.startswith("+++"):
            current[2].append(line[1:])
    return [(k, p, "\n".join(added)) for k, p, added in out]


def _editor_subcommand(claude_name, args):
    """`str_replace_editor`-style tools carry a `command` subfield (create, str_replace, view, insert)."""
    sub = args.get("command")
    if claude_name not in ("Edit", "Write", "Read") or not isinstance(sub, str):
        return claude_name
    sub = sub.strip().lower()
    if sub == "create":
        return "Write"
    if sub == "view":
        return "Read"
    if sub in ("str_replace", "insert", "undo_edit", "edit"):
        return "Edit"
    return claude_name


def claude_tool_input(claude_name, args):
    """Build the Claude `tool_input` dict for `claude_name` from Copilot tool arguments."""
    out = {}
    for claude_key, candidates in _ARG_KEYS.get(claude_name, ()):
        value = _pick(args, candidates)
        if value is not None:
            out[claude_key] = value
    if claude_name in ("Edit", "Write") and "file_path" not in out:
        patch = _pick(args, ("patch", "input", "diff"))
        if isinstance(patch, str):
            files = parse_patch(patch)
            if files:
                kinds = {k for k, _, _ in files}
                out["file_path"] = files[0][1]
                out["extra_paths"] = [p for _, p, _ in files[1:]]
                added = "\n".join(t for _, _, t in files if t)
                if kinds == {"Add"}:
                    out["content"] = added          # a pure Add behaves like Write
                    out["_claude_tool"] = "Write"
                else:
                    out["new_string"] = added
                    out["_claude_tool"] = "Edit"
                out["patch_files"] = [{"kind": k, "path": p} for k, p, _ in files]
    if claude_name == "Grep":
        mode = out.get("output_mode")
        if isinstance(mode, str):
            m = _norm(mode)
            out["output_mode"] = "content" if m in ("content", "matches", "lines") else (
                "files_with_matches" if m in ("fileswithmatches", "files", "filesonly", "list") else mode)
        elif args.get("files_with_matches") is True or args.get("filesOnly") is True or args.get("-l") is True:
            out["output_mode"] = "files_with_matches"
    if claude_name == "Agent":
        sub = out.get("subagent_type")
        role = role_from_name(sub)
        if role:
            out["subagent_type"] = SHIPYARD_PREFIX + role
    # Keep every original key too, so a hook that knows a client-specific field can still read it.
    for k, v in args.items():
        out.setdefault(k, v)
    return out


def role_from_name(name):
    """`shipyard-code-reviewer`, `shipyard:code-reviewer`, `shipyard_code_reviewer` or `code-reviewer` ->
    `code-reviewer`. None when the name is not a Shipyard role."""
    if not isinstance(name, str) or not name.strip():
        return None
    n = name.strip().lower().replace("_", "-")
    for prefix in ("shipyard:", "shipyard-", "shipyard."):
        if n.startswith(prefix):
            n = n[len(prefix):]
            break
    return n if n in ROLES else None


def _find_project(cwd):
    """Walk up from cwd to the folder that holds .ai/state.json (or .git). Falls back to cwd."""
    explicit = (os.environ.get("SHIPYARD_PROJECT_DIR") or os.environ.get("COPILOT_PROJECT_DIR")
                or os.environ.get("CLAUDE_PROJECT_DIR"))  # Shipyard's own variable, then Copilot's, then Claude Code's
    if explicit:
        return os.path.realpath(os.path.abspath(os.path.expanduser(explicit)))
    start = os.path.realpath(os.path.abspath(os.path.expanduser(cwd))) if cwd else os.path.realpath(os.getcwd())
    d = start
    git_root = None
    while True:
        if os.path.isfile(os.path.join(d, ".ai", "state.json")):
            return d
        if git_root is None and os.path.exists(os.path.join(d, ".git")):
            git_root = d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return git_root or start


def state_role(project):
    """`activeRole` from .ai/state.json: a known role name, a non-empty unknown value (returned as is so the
    hooks fail closed on it), or None."""
    path = os.path.join(project, ".ai", "state.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(state, dict):
        return None
    value = state.get("activeRole")
    if not isinstance(value, str) or not value.strip():
        return None
    return role_from_name(value) or value.strip()


def infer_role(data, project):
    """Return (role, source) using the order documented at the top of this module."""
    env = os.environ.get("SHIPYARD_ROLE", "").strip()
    if env:
        if env.lower() in ("none", "null", "-", "off"):
            return None, "env"
        return role_from_name(env) or env, "env"
    for key in ("agentName", "agentType", "agent_name", "agent_type", "agentDisplayName"):
        role = role_from_name(data.get(key))
        if role:
            return role, "payload:" + key
    role = state_role(project)
    if role:
        return role, "state.json"
    return None, None


def infer_event(data, explicit=None):
    """The Copilot event name: `--event` / SHIPYARD_HOOK_EVENT when given, else inferred from the fields."""
    name = explicit or os.environ.get("SHIPYARD_HOOK_EVENT") or data.get("hookEventName") or data.get("event")
    if isinstance(name, str) and name.strip():
        n = name.strip()
        low = _norm(n)
        if low in ("pretooluse",):
            return "preToolUse"
        if low in ("subagentstart",):
            return "subagentStart"
        if low in ("subagentstop", "stop", "agentstop"):
            return "subagentStop"
        return n
    if "toolName" in data or "toolArgs" in data:
        return "preToolUse"
    if "stopReason" in data or "response" in data or "agentId" in data:
        return "subagentStop"
    if "agentName" in data:
        return "subagentStart"
    return "preToolUse"


_CLAUDE_EVENT = {"preToolUse": "PreToolUse", "subagentStart": "SubagentStart", "subagentStop": "SubagentStop",
                 "postToolUse": "PostToolUse", "agentStop": "Stop", "sessionStart": "SessionStart"}


def adapt(data, event=None):
    """Turn a Copilot payload into the Claude-shaped dict `shipyard_hooklib.Context` expects.

    Returns the new dict. It carries `_copilot` (True), `_copilot_event` (the Copilot event name) and
    `_role_source` (where the role came from, or None). When no role applies, `agent_type` is empty, and
    `shipyard_hooklib.run` exits 0 without running the hook."""
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else ""
    project = _find_project(cwd)
    ev = infer_event(data, event)
    role, source = infer_role(data, project)
    out = {
        "_copilot": True,
        "_copilot_event": ev,
        "_role_source": source,
        "hook_event_name": _CLAUDE_EVENT.get(ev, ev),
        "session_id": data.get("sessionId") or data.get("session_id") or "",
        "cwd": cwd or project,
        "project_dir": project,
        "agent_type": (SHIPYARD_PREFIX + role) if role else "",
    }
    session = out["session_id"] or "nosession"
    if ev == "preToolUse":
        claude_name = claude_tool_name(data.get("toolName"))
        args = parse_args(data.get("toolArgs"), claude_name)
        claude_name = _editor_subcommand(claude_name, args)
        tool_input = claude_tool_input(claude_name, args)
        override = tool_input.pop("_claude_tool", None)
        out["tool_name"] = override or claude_name
        out["copilot_tool_name"] = data.get("toolName") or ""
        out["tool_input"] = tool_input
        out["tool_use_id"] = data.get("toolCallId") or data.get("toolUseId") or ""
        agent_id = data.get("agentId")
        out["agent_id"] = agent_id if isinstance(agent_id, str) and agent_id else "%s:%s" % (session, role or "")
    else:
        # Subagent events: key the start-time and retry files by session + role, because subagentStart has
        # no agentId and the id on subagentStop may differ between clients.
        out["agent_id"] = "%s:%s" % (session, role or "")
        out["agent_name"] = data.get("agentName") or ""
        out["agent_transcript_path"] = data.get("transcriptPath") or data.get("transcript_path") or ""
        response = data.get("response")
        if response is None:
            response = data.get("last_assistant_message")
        out["last_assistant_message"] = response if isinstance(response, str) else ""
        out["stop_reason"] = data.get("stopReason") or ""
        sha = data.get("stop_hook_active")
        if sha is None:
            sha = data.get("stopHookActive")
        out["stop_hook_active"] = sha is True
    return out


def deny_json(event, reason):
    """The one-line JSON a Copilot hook prints to refuse. Returns (json text, exit code)."""
    if event == "preToolUse":
        return json.dumps({"permissionDecision": "deny", "permissionDecisionReason": reason}), 2
    if event in ("subagentStop", "agentStop"):
        return json.dumps({"decision": "block", "reason": reason}), 0
    return "", 0

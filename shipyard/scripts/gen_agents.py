#!/usr/bin/env python3
"""Generate the Copilot custom agents from Shipyard's agent shells.

    python3 shipyard/scripts/gen_agents.py [--root PATH] [--model CLASS=id ...]
    python3 shipyard/scripts/gen_agents.py --check

Reads `shipyard/source-agents/<short>.md` (the Shipyard agent shells, with their original frontmatter) and
`shipyard/registry/roles.json`, and writes `.github/agents/shipyard-<short>.agent.md` for every role in the
registry. Standard library only, Python 3.9+.

What the generator does with each shell:

* `name`        -> `shipyard-<short>` (the registry's `agent` value for the role).
* `description` -> Shipyard's description, with the Claude-specific names rewritten.
* `tools`       -> Claude tool names mapped to Copilot tool aliases (TOOL_MAP).
* `model`       -> from the registry compute class whose model and effort match the shell's frontmatter, through
                   MODEL_MAP. The default map holds no model ids: the key is then omitted and a comment names the
                   class. Set the ids in MODEL_MAP or pass `--model DEEP=<id>`.
* specialists   -> `user-invocable: false`, `disable-model-invocation: true`, `agents: []`.
* coordinator   -> `agents:` = the twelve specialists, `handoffs` for the P4, P8 and merge gates, `send: false`.
* `hooks`       -> CLI agent-scoped hooks per role (HOOKS), each passing `SHIPYARD_ROLE=<short>`.
* body          -> the Shipyard body with the wording rules in BODY_RULES applied; `Step 0`, `Mode:` and the hook
                   mentions stay. Must be at most BODY_LIMIT characters.

The coordinator body is hand-maintained (BODY_KEEP): the generator writes it once from the shell as a seed,
then only refreshes its frontmatter and checks it still carries the required markers.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shipyard_frontmatter as fm  # noqa: E402

DEFAULT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SOURCE_DIR = os.path.join("shipyard", "source-agents")
REGISTRY = os.path.join("shipyard", "registry", "roles.json")
OUT_DIR = os.path.join(".github", "agents")
AGENT_PREFIX = "shipyard-"
BODY_LIMIT = 30000  # custom-agents-configuration reference: the prompt body is at most 30,000 characters

# Claude tool name -> Copilot tool alias (custom-agents-configuration reference, "Tool aliases").
# `execute` is the documented primary alias for shell access; `shell` and `Bash` are compatible aliases.
TOOL_MAP = {
    "Read": "read",
    "Grep": "search",
    "Glob": "search",
    "Bash": "execute",
    "Write": "edit",
    "Edit": "edit",
    "MultiEdit": "edit",
    "NotebookEdit": "edit",
    "WebSearch": "web",
    "WebFetch": "web",
    "TodoWrite": "todo",
    "Agent": "agent",
    # No Copilot equivalent: skills load by relevance, and dynamic workflows are run from the shell / `copilot workflow run`.
    "Skill": None,
    "Workflow": None,
}

# Compute class -> Copilot model id. Users set these: leave a value empty to omit `model` from the agent file so
# the client's default (or the model picker / --model flag) applies.
MODEL_MAP = {
    "COORDINATOR": "",
    "DEEP": "",
    "STANDARD": "",
}

# Matchers for the CLI agent-scoped hooks, as fixed in shipyard/scripts/hooks/agent-hooks.md. Copilot anchors a
# matcher to the full tool name; the lists cover the names the CLI, the cloud agent and the IDEs are known or
# believed to report. The exact runtime names per client are (unverified); an unmatched name only means the
# repository-level hook file is the one that fires.
SHELL_TOOLS = "bash|shell|powershell|execute|run_in_terminal|runCommands|run_command|run_terminal_cmd|execute_command"
WRITE_TOOLS = ("create|write|write_file|create_file|edit|str_replace|str_replace_editor|str_replace_based_edit_tool|"
               "apply_patch|edit_file|editFiles|insert_edit_into_file|replace_string_in_file|multi_edit|insert")
READ_TOOLS = ("view|read|read_file|grep|rg|glob|search|grep_search|file_search|codebase|semantic_search|list_dir|"
              "list_code_usages")
TASK_TOOLS = "task|agent|runSubagent|run_subagent|custom-agent|custom_agent|spawn_agent|delegate"
HOOK_TIMEOUT = 10

# (hook script stem, matcher) per role, in the order agent-hooks.md lists them. A matcher of None means the entry
# goes under `Stop` (the findings gate for the reviewers) instead of `preToolUse`.
_READONLY = [("readonly-bash", SHELL_TOOLS), ("protect-branches", SHELL_TOOLS),
             ("write-scope", SHELL_TOOLS + "|" + WRITE_TOOLS), ("secrets-guard", WRITE_TOOLS)]
_REVIEWER = _READONLY + [("findings-gate", None)]
_AUTHOR = [("protect-branches", SHELL_TOOLS), ("write-scope", SHELL_TOOLS + "|" + WRITE_TOOLS),
           ("test-plan-gate", SHELL_TOOLS + "|" + WRITE_TOOLS), ("secrets-guard", WRITE_TOOLS)]
HOOKS = {
    "coordinator": [("brief-check", TASK_TOOLS), ("protect-branches", SHELL_TOOLS),
                    ("write-scope", SHELL_TOOLS + "|" + WRITE_TOOLS), ("secrets-guard", WRITE_TOOLS)],
    "discovery": _READONLY,
    "goldfish": [("goldfish-blinders", READ_TOOLS), ("readonly-bash", SHELL_TOOLS),
                 ("write-scope", SHELL_TOOLS + "|" + WRITE_TOOLS)],
    "architect": _READONLY,
    "planner": _READONLY,
    "implementer": _AUTHOR,
    "verifier": _AUTHOR,
    "code-reviewer": _REVIEWER,
    "security-reviewer": _REVIEWER,
    "contract-reviewer": _REVIEWER,
    "integration-reviewer": _REVIEWER,
    "reliability-reviewer": _REVIEWER,
    "simplicity-reviewer": _REVIEWER,
}

HANDOFFS = [
    ("Answer the P4 questions", "P4 answers, round <n>: <the concept pick on round 1, then Q1: ..., Q2: ...; "
                                "or \"yes\" to take every recommendation; or \"enough\" to end the grill>"),
    ("Confirm shared understanding", "Shared-understanding checklist: yes"),
    ("Approve the plan", "APPROVE PLAN <feature>"),
    ("Request plan changes", "Plan change request: <what to change>"),
    ("Approve the slice merge", "APPROVE MERGE slice <id>"),
    ("Request slice changes", "Slice <id> change request: H1: <what to change>"),
]

# Roles whose body is hand-maintained after the first generation.
BODY_KEEP = {"coordinator"}
# The hand-maintained coordinator body must keep these markers (checked by --check).
COORDINATOR_MARKERS = (
    "## Modes",
    "--agent=shipyard-coordinator",
    "check.py --phase",
    "set-active-role",
    "gate P0 approve",
    "gate P4 approve",
    "gate P8 approve",
    "gate MERGE approve",
    "C-10",
    "grill",
    "shipyard-discover",
    "shipyard-plan",
    "shipyard-slice",
    "Caller: shipyard-coordinator",
)

# Wording rules applied to every body and description, in order. (regex, replacement)
BODY_RULES = [
    # Launch command, with or without the model and effort flags.
    (r"claude --agent shipyard:coordinator(?: --model [^\s)]+)?(?: --effort [^\s)]+)?",
     "copilot --agent=shipyard-coordinator"),
    # Saved workflow slash names become the dynamic workflow names.
    (r"`/shipyard:(discover|plan|slice)`", r"the `shipyard-\1` workflow"),
    (r"/shipyard:(discover|plan|slice)", r"shipyard-\1"),
    (r"`/shipyard:setup`", "`python3 shipyard/scripts/check.py --env`"),
    # Agent names.
    (r"shipyard:([a-z-]+|\*)", r"shipyard-\1"),
    # Plugin paths.
    (r"\"?\$\{CLAUDE_PLUGIN_ROOT\}/scripts/([A-Za-z_]+\.py)\"?", r"shipyard/scripts/\1"),
    (r"\$\{CLAUDE_PLUGIN_ROOT\}/registry/roles\.json", "shipyard/registry/roles.json"),
    (r"\$\{CLAUDE_PLUGIN_ROOT\}/contracts/", "shipyard/contracts/"),
    (r"\$\{CLAUDE_PLUGIN_ROOT\}/workflows/", ".github/extensions/"),
    (r"\$\{CLAUDE_PLUGIN_ROOT\}", "the repository root"),
    # Workflow wording.
    (r"saved workflows?", lambda m: "dynamic workflow" + ("s" if m.group(0).endswith("s") else "")),
    (r"the \*\*Workflow\*\* tool", "the dynamic workflow runner (`copilot workflow run`)"),
    (r"the Workflow tool", "the dynamic workflow runner"),
    (r"the \*\*Agent\*\* tool", "the `agent` tool"),
    (r"the Agent tool", "the `agent` tool"),
    (r"on the Agent call", "on the subagent call"),
    (r"the Edit tool", "the edit tool"),
    (r"the Skill tool", "the skill"),
    (r"WebSearch and WebFetch", "the web tool"),
    # Skills: no preload list in Copilot, so each agent loads its skills explicitly.
    (r"Your skills are preloaded: ", "Load these skills from `.github/skills` before you start: "),
    (r"Your skill `shipyard-framework` is preloaded\.",
     "Load the skill `shipyard-framework` from `.github/skills` before you start."),
    (r"Load the \*\*`shipyard-framework`\*\* skill \(preloaded; if it is not in your context, invoke it with the skill\)\.",
     "Load the **`shipyard-framework`** skill from `.github/skills/shipyard-framework/SKILL.md` before you start."),
    (r"You load no skills and no project memory \(`CLAUDE\.md` is skipped for you\)\.",
     "You load no skills and no project memory: ignore `AGENTS.md`, `.github/copilot-instructions.md` and every "
     "skill under `.github/skills`."),
    (r"`CLAUDE\.md`", "`AGENTS.md`"),
    (r"Claude Code", "Copilot"),
]


class GenError(Exception):
    pass


def load_registry(root):
    with open(os.path.join(root, REGISTRY), encoding="utf-8") as fh:
        return json.load(fh)


def role_order(registry):
    """[(role key, short name)] in registry order; the short name is the agent value without its prefix."""
    out = []
    for key, role in registry["roles"].items():
        agent = role.get("agent", "")
        short = agent.split(":", 1)[1] if ":" in agent else agent[len(AGENT_PREFIX):] if agent.startswith(AGENT_PREFIX) else agent
        out.append((key, short))
    return out


def compute_class(registry, src_fm):
    model, effort = src_fm.get("model"), src_fm.get("effort")
    for name, cls in registry["computeClasses"].items():
        if cls.get("model") == model and cls.get("effort") == effort:
            return name
    raise GenError("no compute class matches model=%r effort=%r" % (model, effort))


def map_tools(src_fm, short):
    out = []
    for entry in fm.tools_list(src_fm.get("tools")):
        base = entry.split("(", 1)[0].strip()
        if base not in TOOL_MAP:
            raise GenError("%s: unknown Claude tool %r" % (short, entry))
        alias = TOOL_MAP[base]
        if alias == "agent" and short != "coordinator":
            raise GenError("%s: only the coordinator may carry the agent tool" % short)
        if alias and alias not in out:
            out.append(alias)
    return out


def adapt_text(text, short, skills):
    for pattern, repl in BODY_RULES:
        text = re.sub(pattern, repl, text)
    # "Your skills are preloaded. ..." (no list in the sentence): name the registry's skills for the role.
    if skills:
        names = ", ".join("`%s`" % s for s in skills)
        text = text.replace("Your skills are preloaded. ",
                            "Load these skills from `.github/skills` before you start: %s. " % names)
    if "preloaded" in text or "CLAUDE" in text or "shipyard:" in text:
        raise GenError("%s: unadapted wording remains (preloaded / CLAUDE / shipyard:)" % short)
    return text


def yaml_str(value):
    """Quote a scalar for the frontmatter."""
    return json.dumps(value, ensure_ascii=False)


def wrap(text, width=108, indent="  "):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(indent + cur)
            cur = w
        else:
            cur = (cur + " " + w) if cur else w
    if cur:
        lines.append(indent + cur)
    return "\n".join(lines)


def frontmatter(short, description, tools, cls, model_map, specialists):
    lines = ["---", "name: %s%s" % (AGENT_PREFIX, short), "description: >", wrap(description)]
    lines.append("tools: [%s]" % ", ".join(tools))
    model_id = model_map.get(cls, "")
    if model_id:
        lines.append("model: %s" % yaml_str(model_id))
    else:
        lines.append("# model: %s class in shipyard/registry/roles.json -> computeClasses; set MODEL_MAP in "
                     "shipyard/scripts/gen_agents.py or pass --model %s=<id>" % (cls, cls))
    if short == "coordinator":
        lines.append("agents:")
        for s in specialists:
            lines.append("  - %s%s" % (AGENT_PREFIX, s))
        lines.append("handoffs:")
        for label, prompt in HANDOFFS:
            lines.append("  - label: %s" % yaml_str(label))
            lines.append("    agent: %s%s" % (AGENT_PREFIX, short))
            lines.append("    prompt: %s" % yaml_str(prompt))
            lines.append("    send: false")
    else:
        lines.append("user-invocable: false")
        lines.append("disable-model-invocation: true")
        lines.append("agents: []")
    hooks = HOOKS.get(short, [])
    if hooks:
        lines.append("hooks:")
        lines.append("  preToolUse:")
        for hook, matcher in hooks:
            if matcher is not None:
                lines.extend(hook_entry(short, hook, matcher))
        stops = [hook for hook, matcher in hooks if matcher is None]
        if stops:
            lines.append("  Stop:")
            for hook in stops:
                lines.extend(hook_entry(short, hook, None))
    lines.append("---")
    return "\n".join(lines) + "\n"


def hook_entry(short, hook, matcher):
    """One agent-scoped hook entry (the form fixed in shipyard/scripts/hooks/agent-hooks.md)."""
    script = "shipyard/scripts/hooks/%s.py" % hook
    args = " --event subagentStop" if matcher is None else ""
    out = ["    - type: command"]
    if matcher is not None:
        out.append("      matcher: %s" % yaml_str(matcher))
    out.append("      command: SHIPYARD_ROLE=%s python3 %s%s" % (short, script, args))
    out.append("      windows: $env:SHIPYARD_ROLE='%s'; python3 %s%s" % (short, script, args))
    out.append("      timeoutSec: %d" % (15 if matcher is None else HOOK_TIMEOUT))
    return out


def render(root, model_map):
    """Return {relative output path: (frontmatter text, body text, short)} for every role."""
    registry = load_registry(root)
    roles = role_order(registry)
    specialists = [s for _, s in roles if s != "coordinator"]
    out = {}
    for key, short in roles:
        src = os.path.join(root, SOURCE_DIR, short + ".md")
        if not os.path.isfile(src):
            raise GenError("missing source agent %s" % os.path.relpath(src, root))
        src_fm, body = fm.read(src)
        skills = registry["roles"][key].get("skills") or []
        description = adapt_text(src_fm.get("description", "").strip(), short, skills)
        body = adapt_text(body.strip() + "\n", short, skills)
        if len(body) > BODY_LIMIT:
            raise GenError("%s: body is %d characters, over the %d limit" % (short, len(body), BODY_LIMIT))
        head = frontmatter(short, description, map_tools(src_fm, short), compute_class(registry, src_fm),
                           model_map, specialists)
        out[os.path.join(OUT_DIR, "%s%s.agent.md" % (AGENT_PREFIX, short))] = (head, body, short)
    return out


def split_existing(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    head, body = fm.split(text)
    return "---\n" + head + "---\n", body.lstrip("\n")


def check_kept_body(short, body):
    problems = []
    if len(body) > BODY_LIMIT:
        problems.append("%s: body is %d characters, over the %d limit" % (short, len(body), BODY_LIMIT))
    if short == "coordinator":
        for marker in COORDINATOR_MARKERS:
            if marker not in body:
                problems.append("coordinator: body lacks the marker %r" % marker)
    # `shipyard:plan-approved` is the cloud-mode label and `shipyard:shipyard-<short>` a plugin-install agent id,
    # not upstream agent names.
    if re.search(r"shipyard:(?!plan-approved|shipyard-)[a-z]|CLAUDE|\bpreloaded\b", body):
        problems.append("%s: body carries unadapted wording (shipyard: / CLAUDE / preloaded)" % short)
    return problems


def generate(root, model_map, check=False):
    rendered = render(root, model_map)
    problems, written = [], []
    for rel, (head, body, short) in sorted(rendered.items()):
        path = os.path.join(root, rel)
        exists = os.path.isfile(path)
        if short in BODY_KEEP and exists:
            old_head, old_body = split_existing(path)
            problems.extend(check_kept_body(short, old_body))
            if check:
                if old_head != head:
                    problems.append("%s: frontmatter is out of date" % rel)
                continue
            if old_head != head:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(head + "\n" + old_body)
                written.append(rel)
            continue
        text = head + "\n" + body
        if check:
            if not exists:
                problems.append("%s: missing" % rel)
            else:
                with open(path, encoding="utf-8") as fh:
                    if fh.read() != text:
                        problems.append("%s: out of date" % rel)
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        written.append(rel)
    return problems, written


def parse_model_args(items):
    model_map = dict(MODEL_MAP)
    for item in items or []:
        if "=" not in item:
            raise GenError("--model expects CLASS=id, got %r" % item)
        cls, model_id = item.split("=", 1)
        if cls not in model_map:
            raise GenError("unknown compute class %r (known: %s)" % (cls, ", ".join(sorted(model_map))))
        model_map[cls] = model_id
    return model_map


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate .github/agents/*.agent.md from shipyard/source-agents")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="repository root (default: this script's repo)")
    parser.add_argument("--check", action="store_true", help="report files that are missing or out of date; write nothing")
    parser.add_argument("--model", action="append", metavar="CLASS=id", help="model id for a compute class (repeatable)")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    try:
        problems, written = generate(root, parse_model_args(args.model), check=args.check)
    except (GenError, fm.FrontmatterError, OSError, ValueError) as exc:
        print("gen_agents.py: %s" % exc)
        return 1
    if problems:
        print("gen_agents.py: %d problem%s" % (len(problems), "" if len(problems) == 1 else "s"))
        for p in problems:
            print("  - " + p)
        return 1
    if args.check:
        print("gen_agents.py: OK (%d agent files up to date)" % len(render(root, parse_model_args(args.model))))
    else:
        print("gen_agents.py: wrote %d file%s" % (len(written), "" if len(written) == 1 else "s"))
        for rel in written:
            print("  - " + rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())

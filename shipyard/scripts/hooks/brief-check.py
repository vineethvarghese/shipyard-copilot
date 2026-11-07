#!/usr/bin/env python3
"""brief-check (PreToolUse, Agent|Task): when the coordinator calls a Shipyard specialist directly, the
brief must start with `Caller: shipyard:coordinator`, name a valid `Mode:` for that role, and carry a
`Round: n` within the fix-round cap for FIX / FIX_TESTS / RECHECK."""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import copilot_hooklib  # noqa: E402
import shipyard_hooklib as lib  # noqa: E402

HOOK = "brief-check"
ROUND_MODES = ("FIX", "FIX_TESTS", "RECHECK")
MODE_RX = re.compile(r"^Mode:[ \t]*(\S*)[ \t]*$", re.M)
ROUND_RX = re.compile(r"^Round:[ \t]*(\S*)[ \t]*$", re.M)


def registry_path():
    root = os.environ.get("SHIPYARD_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "registry", "roles.json")


def load_registry(ctx):
    path = registry_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            reg = json.load(fh)
    except (OSError, ValueError) as exc:
        ctx.deny("cannot read the role registry %s (%s); failing closed." % (path, exc))
    if not isinstance(reg, dict) or not isinstance(reg.get("roles"), dict):
        ctx.deny("the role registry %s has no 'roles' object; failing closed." % path)
    return reg


def main(ctx):
    if ctx.agent != "coordinator":
        return
    sub = ctx.tool_input.get("subagent_type")
    if not lib.is_shipyard(sub):
        return
    prompt = ctx.tool_input.get("prompt")
    prompt = prompt if isinstance(prompt, str) else ""
    if not prompt.lstrip().startswith("Caller: shipyard:coordinator"):
        ctx.deny("the brief for %s must start with the line 'Caller: shipyard:coordinator'." % sub)
    reg = load_registry(ctx)
    role_name, role = None, None
    wanted = copilot_hooklib.role_from_name(sub) or sub
    for name, r in reg["roles"].items():
        if not isinstance(r, dict):
            continue
        agent = r.get("agent")  # `shipyard:architect` (Claude) or `shipyard-architect` (Copilot agent name)
        if agent == sub or (copilot_hooklib.role_from_name(agent) or agent) == wanted:
            role_name, role = name, r
            break
    if role is None:
        ctx.deny("'%s' is not an agent in registry/roles.json." % sub)
    modes = sorted((role.get("modes") or {}).keys())
    found = MODE_RX.findall(prompt)
    if not found:
        ctx.deny("the brief for %s has no 'Mode: <MODE>' line. Valid modes for role %s: %s."
                 % (sub, role_name, ", ".join(modes)))
    if len(set(found)) > 1:
        ctx.deny("the brief for %s has conflicting Mode lines (%s)." % (sub, ", ".join(found)))
    mode = found[0]
    if mode not in modes:
        ctx.deny("'Mode: %s' is not a mode of role %s (%s). Valid modes: %s."
                 % (mode, role_name, sub, ", ".join(modes)))
    if mode in ROUND_MODES:
        cap = (reg.get("limits") or {}).get("fixRounds")
        if not isinstance(cap, int):
            ctx.deny("registry/roles.json has no integer limits.fixRounds; failing closed.")
        rounds = ROUND_RX.findall(prompt)
        if not rounds:
            ctx.deny("mode %s needs a 'Round: <n>' line (n <= %d)." % (mode, cap))
        if len(set(rounds)) > 1 or not rounds[0].isdigit():
            ctx.deny("mode %s needs exactly one 'Round: <n>' line with a whole number (got %s)."
                     % (mode, ", ".join(rounds)))
        n = int(rounds[0])
        if n > cap:
            ctx.deny("Round %d exceeds the fix-round cap of %d. Escalate to the human with the open findings "
                     "instead of another round." % (n, cap))


if __name__ == "__main__":
    lib.run(HOOK, main)

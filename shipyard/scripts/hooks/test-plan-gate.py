#!/usr/bin/env python3
"""test-plan-gate (PreToolUse, Edit|Write|MultiEdit|NotebookEdit|Bash): no code and no tests for a slice
until its `.ai/slices/<id>/TEST_PLAN.md` says `Status: APPROVED` in its first 10 lines. For Bash, every
project path the command visibly writes counts."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shipyard_hooklib as lib  # noqa: E402

HOOK = "test-plan-gate"
GATED = ("implementer", "verifier")


def main(ctx):
    if ctx.agent not in GATED:
        return
    ti = ctx.tool_input
    if ctx.tool_name == "Bash":
        cmd = ti.get("command")
        cmds = lib.parse_commands(cmd) if isinstance(cmd, str) else []
        targets = lib.bash_write_targets(cmds)
        moved = lib.has_cd(cmds)
        rels = []
        for t in targets:
            absolute = os.path.isabs(os.path.expanduser(t))
            r = lib.normalize_path(ctx.project, t, ctx.cwd)
            if (moved and not absolute) or (r is None and not absolute):
                rels.append(t)  # cannot place it: treat as a project write
            elif r is not None and not lib.under_ai(r):
                rels.append(r)
        rels.extend(lib.bash_opaque_writers(cmds, ctx.project, ctx.cwd))
        if not rels:
            return  # writes nothing in the project outside .ai/ (write-scope polices .ai/)
        rel = rels[0]
    else:
        path = ti.get("file_path") or ti.get("notebook_path") or ti.get("path")
        rel = lib.normalize_path(ctx.project, path, ctx.cwd) if isinstance(path, str) else None
        if lib.under_ai(rel):
            return  # .ai/ files (e.g. the verifier's TEST_PLAN.md) are not gated here; write-scope decides.
    state, err = ctx.state()
    if state is None:
        ctx.deny("shipyard:%s may not write code or tests: %s, so the test-plan approval cannot be checked."
                 % (ctx.agent, err))
    sid = lib.active_slice(state)
    if not sid:
        ctx.deny("shipyard:%s may not write code or tests: .ai/state.json has no activeSlice." % ctx.agent)
    plan_rel = lib.slice_rel(sid, "TEST_PLAN.md")
    status = lib.test_plan_status(os.path.join(ctx.project, plan_rel))
    if status == "APPROVED":
        ctx.debug("%s is APPROVED; allowing %s" % (plan_rel, rel))
        return
    shown = {"MISSING": "the file does not exist", None: "it has no 'Status:' line in its first 10 lines",
             "DRAFT": "it says 'Status: DRAFT'"}[status]
    ctx.deny("test plan first: %s is not approved (%s). No code or test for slice %s until the "
             "code-reviewer sets 'Status: APPROVED'." % (plan_rel, shown, sid))


if __name__ == "__main__":
    lib.run(HOOK, main)

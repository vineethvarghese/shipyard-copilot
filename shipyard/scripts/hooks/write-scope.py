#!/usr/bin/env python3
"""write-scope (PreToolUse, Edit|Write|MultiEdit|NotebookEdit|Bash): each Shipyard agent writes only the
paths its role owns (the write-permission table in the Shipyard spec). For Bash, the same table applies to
every path the command line visibly writes (redirections, tee, sed -i, cp, mv, rm, touch, git rm/mv/restore);
nobody writes inside .git/, and TEST_PLAN.md changes only through the Write and Edit tools."""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shipyard_hooklib as lib  # noqa: E402

HOOK = "write-scope"
REVIEWERS = {"code-reviewer", "security-reviewer", "contract-reviewer", "integration-reviewer",
             "reliability-reviewer", "simplicity-reviewer"}
APPROVED_RX = re.compile(r"Status:\s*APPROVED", re.I)


def target_path(ti):
    for key in ("file_path", "notebook_path", "path"):
        v = ti.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return None


def new_texts(tool, ti):
    out = []
    for key in ("content", "new_string", "new_source"):
        v = ti.get(key)
        if isinstance(v, str):
            out.append(v)
    edits = ti.get("edits")
    if isinstance(edits, list):
        for e in edits:
            if isinstance(e, dict) and isinstance(e.get("new_string"), str):
                out.append(e["new_string"])
    return out


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def simulate(tool, ti, before):
    """Return the file text after the write/edit (best effort)."""
    if tool == "Write" or "content" in ti:
        return ti.get("content") if isinstance(ti.get("content"), str) else ""
    text = before
    edits = ti.get("edits") if isinstance(ti.get("edits"), list) else [ti]
    for e in edits:
        if not isinstance(e, dict):
            continue
        old, new = e.get("old_string"), e.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str) or old == "":
            continue
        if old in text:
            text = text.replace(old, new) if e.get("replace_all") else text.replace(old, new, 1)
    return text


def introduces_approval(ctx, rel, strict):
    """True when this write would make a TEST_PLAN.md say `Status: APPROVED` (strict: any new text that
    contains `Status: APPROVED` counts, even if the plan was already approved)."""
    path = os.path.join(ctx.project, rel)
    before = read_text(path)
    texts = new_texts(ctx.tool_name, ctx.tool_input)
    if strict and any(APPROVED_RX.search(t) for t in texts):
        return True
    before_status = lib.plan_status_from_text(before)
    after = simulate(ctx.tool_name, ctx.tool_input, before)
    after_status = lib.plan_status_from_text(after)
    if after_status == "APPROVED" and before_status != "APPROVED":
        return True
    if before_status != "APPROVED" and any(APPROVED_RX.search(t) for t in texts):
        return True
    return False


def need_slice(ctx):
    """For implementer/verifier: return (state, sid, sets) or deny naming what is missing."""
    state, err = ctx.state()
    if state is None:
        ctx.deny("shipyard:%s needs .ai/state.json to know the active slice, but %s. Ask the coordinator to "
                 "set up state before writing." % (ctx.agent, err))
    sid = lib.active_slice(state)
    if not sid:
        ctx.deny("shipyard:%s cannot write: .ai/state.json has no activeSlice." % ctx.agent)
    sets, err = lib.load_touch_sets(ctx.project, state)
    if sets is None:
        ctx.deny("shipyard:%s cannot write: %s (the touch sets decide what you may write)." % (ctx.agent, err))
    return state, sid, sets


def fmt(patterns):
    return ", ".join(patterns) if patterns else "(empty)"


def check_coordinator(ctx, rel):
    if not lib.under_ai(rel):
        ctx.deny("shipyard:coordinator writes only .ai/**, not '%s' (the project's own files, .gitignore included, "
                 "are the human's work; .ai/ is ignored locally through .git/info/exclude). Code goes to "
                 "shipyard:implementer, tests to shipyard:verifier." % rel)
    if lib.glob_match(rel, ".ai/slices/*/TEST_PLAN.md") and introduces_approval(ctx, rel, strict=False):
        ctx.deny("shipyard:coordinator may not set 'Status: APPROVED' in %s. Only shipyard:code-reviewer flips "
                 "the status line, on an APPROVE verdict." % rel)


def check_discovery(ctx, rel):
    if not lib.under_ai(rel):
        ctx.deny("shipyard:discovery writes only under .ai/, not '%s'." % rel)
    if rel in (".ai/ARCHITECTURE.md", ".ai/INVARIANTS.md", ".ai/state.json") or rel.startswith(".ai/slices/") \
            or rel == ".ai/slices" or rel.startswith(".ai/formal/") or rel == ".ai/formal":
        ctx.deny("shipyard:discovery may not write '%s' (ARCHITECTURE.md, INVARIANTS.md and formal/** belong to "
                 "the architect, state.json to the coordinator, slices/** to the planner and slice agents)." % rel)


def check_list(ctx, rel, patterns, label):
    if lib.match_any(rel, patterns):
        return
    ctx.deny("shipyard:%s may write only %s; '%s' is outside that." % (ctx.agent, label, rel))


def check_reviewer(ctx, rel):
    name = ctx.agent
    own = [".ai/planning/%s.md" % name, ".ai/slices/*/findings/%s.md" % name,
           ".ai/slices/*/findings/%s.test-plan.md" % name]
    if lib.match_any(rel, own):
        return
    if name == "code-reviewer" and lib.glob_match(rel, ".ai/slices/*/TEST_PLAN.md"):
        check_status_flip(ctx, rel)
        return
    ctx.deny("shipyard:%s may write only its own findings files (%s); '%s' is outside that."
             % (name, ", ".join(own), rel))


def check_status_flip(ctx, rel):
    state, err = ctx.state()
    if state is None:
        ctx.deny("the TEST_PLAN status flip needs .ai/state.json, but %s." % err)
    sid = lib.active_slice(state)
    expected = lib.slice_rel(sid, "TEST_PLAN.md") if sid else None
    if rel != expected:
        ctx.deny("shipyard:code-reviewer may flip the status only in the active slice's TEST_PLAN.md (%s), not "
                 "'%s'." % (expected or "state.json has no activeSlice", rel))
    ti = ctx.tool_input
    if ctx.tool_name != "Edit" or ti.get("old_string") != "Status: DRAFT" or \
            ti.get("new_string") != "Status: APPROVED" or ti.get("replace_all"):
        ctx.deny("shipyard:code-reviewer may make exactly one change to %s: the Edit tool with old_string "
                 "'Status: DRAFT' and new_string 'Status: APPROVED'. Put every other comment in your findings "
                 "file (.ai/slices/%s/findings/code-reviewer.test-plan.md)." % (rel, sid))
    status = lib.test_plan_status(os.path.join(ctx.project, rel))
    if status != "DRAFT":
        ctx.deny("%s has no 'Status: DRAFT' line in its first 10 lines (found: %s); nothing to approve."
                 % (rel, status))


def check_implementer(ctx, rel):
    state, sid, sets = need_slice(ctx)
    if lib.under_ai(rel):
        ctx.deny("shipyard:implementer never writes .ai/** ('%s'). Report through your return block." % rel)
    hit = lib.match_any(rel, sets["tests"])
    if hit:
        ctx.deny("'%s' is in the slice's test touch set (%s). Tests belong to shipyard:verifier; the "
                 "implementer writes production code only." % (rel, hit))
    if not lib.match_any(rel, sets["code"]):
        ctx.deny("'%s' is outside slice %s's code touch set (%s). If the slice really needs it, stop and report "
                 "it as a scope change." % (rel, sid, fmt(sets["code"])))


def check_verifier(ctx, rel):
    state, sid, sets = need_slice(ctx)
    plan = lib.slice_rel(sid, "TEST_PLAN.md")
    if rel == plan:
        if introduces_approval(ctx, rel, strict=True):
            ctx.deny("shipyard:verifier may not write 'Status: APPROVED' into %s. Write 'Status: DRAFT'; only "
                     "shipyard:code-reviewer approves the plan." % rel)
        if lib.test_plan_status(os.path.join(ctx.project, rel)) == "APPROVED":
            content = ctx.tool_input.get("content")
            if not (ctx.tool_name == "Write" and isinstance(content, str) and
                    lib.plan_status_from_text(content) == "DRAFT"):
                ctx.deny("%s is APPROVED, so it is frozen: planned tests are not dropped or changed after "
                         "approval. To change the plan, rewrite the whole file with the Write tool and "
                         "'Status: DRAFT', which sends it back to shipyard:code-reviewer." % rel)
        return
    if lib.match_any(rel, [".ai/slices/%s/findings/verifier.md" % sid,
                           ".ai/slices/%s/findings/verifier.*.md" % sid]):
        return
    if lib.under_ai(rel):
        ctx.deny("shipyard:verifier may write only %s and its findings file under .ai/, not '%s'." % (plan, rel))
    if not lib.match_any(rel, sets["tests"]):
        ctx.deny("'%s' is outside slice %s's test touch set (%s). The verifier never writes production code."
                 % (rel, sid, fmt(sets["tests"])))


def check_path(ctx, rel):
    agent = ctx.agent
    ctx.debug("agent=%s tool=%s rel=%s" % (agent, ctx.tool_name, rel))
    if agent == "coordinator":
        check_coordinator(ctx, rel)
    elif agent == "discovery":
        check_discovery(ctx, rel)
    elif agent == "goldfish":
        ctx.deny("shipyard:goldfish writes nothing; return your ideas in the structured result instead.")
    elif agent == "architect":
        check_list(ctx, rel, [".ai/ARCHITECTURE.md", ".ai/INVARIANTS.md", ".ai/decisions/**", ".ai/formal/**",
                              ".ai/planning/architect.md", ".ai/slices/*/findings/architect.md",
                              ".ai/slices/*/findings/architect.*.md"],
                   ".ai/ARCHITECTURE.md, .ai/INVARIANTS.md, .ai/decisions/**, .ai/formal/**, "
                   ".ai/planning/architect.md and its findings files")
    elif agent == "planner":
        check_list(ctx, rel, [".ai/DELIVERY_PLAN.md", ".ai/slices/*/SLICE.md", ".ai/planning/planner.md"],
                   ".ai/DELIVERY_PLAN.md, .ai/slices/*/SLICE.md and .ai/planning/planner.md")
    elif agent in REVIEWERS:
        check_reviewer(ctx, rel)
    elif agent == "implementer":
        check_implementer(ctx, rel)
    elif agent == "verifier":
        check_verifier(ctx, rel)
    else:
        ctx.deny("unknown Shipyard agent '%s' has no write permissions." % ctx.agent_type)


def check_bash(ctx):
    cmd = ctx.tool_input.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return
    cmds = lib.parse_commands(cmd)
    opaque = lib.bash_opaque_writers(cmds, ctx.project, ctx.cwd)
    if opaque:
        ctx.deny("`%s` writes files whose paths the hook cannot see (%s). Write files with the Write and Edit "
                 "tools, or extract and download under /tmp." % (cmd.strip()[:80], ", ".join(opaque)))
    moved = lib.has_cd(cmds)
    for target in lib.bash_write_targets(cmds):
        absolute = os.path.isabs(os.path.expanduser(target))
        if moved and not absolute:
            ctx.deny("`%s` writes '%s' after a `cd` on the same command line, so the hook cannot tell where it "
                     "lands. Write with a path from the project root, without `cd`." % (cmd.strip()[:80], target))
        rel = lib.normalize_path(ctx.project, target, ctx.cwd)
        if rel is None:
            if not absolute:
                ctx.deny("`%s` writes '%s', a relative path that leaves the project." % (cmd.strip()[:80], target))
            continue  # an absolute path outside the project (e.g. /tmp): not Shipyard state, not the deliverable
        if lib.under_git_dir(rel):
            ctx.deny("`%s` writes inside .git/ ('%s'). Shipyard agents change git state only through git "
                     "commands, which protect-branches checks." % (cmd.strip()[:80], rel))
        if rel == "" or rel == ".ai":
            ctx.deny("`%s` would write or delete the %s itself." % (cmd.strip()[:80],
                                                                    "project folder" if rel == "" else ".ai/ folder"))
        if lib.glob_match(rel, ".ai/slices/*/TEST_PLAN.md"):
            ctx.deny("'%s' changes only through the Write and Edit tools, so its status line can be checked; "
                     "not through Bash." % rel)
        check_path(ctx, rel)


def main(ctx):
    if ctx.tool_name == "Bash":
        check_bash(ctx)
        return
    path = target_path(ctx.tool_input)
    if path is None:
        ctx.deny("could not find the target path in the %s tool input." % (ctx.tool_name or "write"))
    rel = lib.normalize_path(ctx.project, path, ctx.cwd)
    if rel is None:
        ctx.deny("'%s' is outside the project (%s). Shipyard agents write only inside the project."
                 % (path, ctx.project))
    if rel == "":
        ctx.deny("refusing to write the project directory itself.")
    check_path(ctx, rel)


if __name__ == "__main__":
    lib.run(HOOK, main)

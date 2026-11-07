#!/usr/bin/env python3
"""findings-gate (SubagentStart + SubagentStop, reviewers): a reviewer may not finish until its findings file
exists, was written during this run, and parses: banner line, then `NO FINDINGS` or at least one block with
ID:, Severity: and Evidence:. SubagentStart records when the reviewer started (outside the repository, in the
system temp folder, keyed by agent_id) so a findings file left over from an earlier run does not count.

Under Copilot (`subagentStart` / `subagentStop`, wired with `--event <name>` because the payload carries no
event name) the key is `<sessionId>:<role>`, the role comes from the payload's agentName, and the reviewer is
sent back at most MAX_BLOCKS times before it is allowed to stop."""

import hashlib
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shipyard_hooklib as lib  # noqa: E402

HOOK = "findings-gate"
REVIEWER_RX = re.compile(r"^shipyard:(code|security|contract|integration|reliability|simplicity)-reviewer$")
SEVERITIES = {"BLOCKING", "MAJOR", "MINOR", "NOTE"}
FIELD_RX = re.compile(r"^(?:[-*]\s+)?(?:\*\*)?([A-Za-z][A-Za-z ]*?)(?:\*\*)?:(?:\*\*)?\s*(.*)$")


def field(line):
    m = FIELD_RX.match(line.strip())
    if not m:
        return None, None
    return m.group(1).strip().lower(), m.group(2).strip().strip("*").strip()


def validate(text):
    """Return None when valid, else a short reason."""
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return "the file is empty"
    first = lines[0].strip()
    if not (first.startswith(">") and "AGENT FILE" in first.upper()):
        return "the first line must be the agent banner ('> \U0001F916 AGENT FILE. ...')"
    body = [l for l in lines[1:]]
    if any(l.strip() == "NO FINDINGS" for l in body):
        if any(field(l)[0] == "id" for l in body):
            return "it says NO FINDINGS but also contains finding blocks"
        return None
    blocks, cur = [], None
    for l in body:
        key, val = field(l)
        if key == "id":
            cur = {"id": val}
            blocks.append(cur)
        elif cur is not None and key in ("severity", "evidence"):
            cur[key] = val
    if not blocks:
        return "it has neither a 'NO FINDINGS' line nor any finding block starting with 'ID:'"
    for b in blocks:
        name = b.get("id") or "(no id)"
        if not b.get("id"):
            return "a finding block has an empty ID"
        if "severity" not in b:
            return "finding %s has no 'Severity:' line" % name
        sev = re.match(r"[A-Za-z]*", b["severity"]).group(0).upper()
        if sev not in SEVERITIES:
            return "finding %s has severity '%s' (use BLOCKING, MAJOR, MINOR or NOTE)" % (name, b["severity"])
        if "evidence" not in b:
            return "finding %s has no 'Evidence:' line (evidence is mandatory)" % name
    return None


def candidates(ctx, name):
    """Slice findings files for the active slice (if any) plus the planning file; the newest one is checked,
    so a PLAN-mode review that runs while a slice is active is still found."""
    state, _err = ctx.state()
    sid = lib.active_slice(state)
    rels = []
    if sid:
        rels += [lib.slice_rel(sid, "findings/%s.md" % name), lib.slice_rel(sid, "findings/%s.test-plan.md" % name)]
    rels.append(".ai/planning/%s.md" % name)
    return rels


def start_file(ctx):
    agent_id = ctx.data.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        return None
    key = hashlib.sha256(("%s\0%s" % (ctx.project, agent_id)).encode("utf-8")).hexdigest()[:32]
    return os.path.join(tempfile.gettempdir(), "shipyard-findings-gate", key)


MAX_BLOCKS = 3


def _blocks_file(ctx):
    path = start_file(ctx)
    return None if path is None else path + ".blocks"


def read_blocks(ctx):
    """How many times this reviewer has been refused so far in this run."""
    path = _blocks_file(ctx)
    if path is None:
        return MAX_BLOCKS
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return int(fh.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def bump_blocks(ctx):
    path = _blocks_file(ctx)
    if path is None:
        return
    n = read_blocks(ctx) + 1
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(str(n))
    except OSError:
        pass


def forget(ctx):
    path = start_file(ctx)
    if path:
        for p in (path, path + ".blocks"):
            try:
                os.remove(p)
            except OSError:
                pass


def record_start(ctx):
    path = start_file(ctx)
    if path is None:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("%.3f\n" % time.time())
    except OSError as exc:
        ctx.debug("could not record start time: %s" % exc)


def started_at(ctx):
    path = start_file(ctx)
    if path is None:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return float(fh.read().strip())
    except (OSError, ValueError):
        return None


MODE_RX = re.compile(r"Mode: ([A-Z_]+)")
NO_FILE_MODES = {"REBUTTAL"}  # answers one rebuttal in its return block; writes no findings file


def brief_mode(ctx):
    """The Mode: line of the reviewer's brief, read from the start of its transcript (the brief is the first
    message). Falls back to the shape of the final message for a rebuttal answer. None when unknown."""
    path = ctx.data.get("agent_transcript_path")
    if isinstance(path, str) and path:
        try:
            with open(os.path.expanduser(path), "r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(65536)
            m = MODE_RX.search(head)
            if m:
                return m.group(1)
        except OSError:
            pass
    last = ctx.data.get("last_assistant_message")
    if isinstance(last, str) and re.search(r'"response"\s*:\s*"(ACCEPT_REBUTTAL|MAINTAIN_FINDING)"', last):
        return "REBUTTAL"
    return None


def refuse(ctx, reason):
    bump_blocks(ctx)
    ctx.deny(reason)


def main(ctx):
    if not REVIEWER_RX.match(ctx.agent_type):
        return
    if ctx.data.get("hook_event_name") == "SubagentStart":
        record_start(ctx)
        return
    if brief_mode(ctx) in NO_FILE_MODES:
        ctx.debug("brief mode writes no findings file; gate not applicable")
        forget(ctx)
        return
    # Copilot does not always say whether an earlier block forced this turn, so under Copilot the retry counter
    # alone (kept in the temp folder, keyed by session + reviewer) decides when to let the reviewer stop.
    if (ctx.data.get("stop_hook_active") is True or ctx.copilot) and read_blocks(ctx) >= MAX_BLOCKS:
        forget(ctx)
        sys.stderr.write("Shipyard %s: %s was already sent back %d times; letting it stop so it cannot loop. The "
                         "workflow still validates its result.\n" % (HOOK, ctx.agent_type, MAX_BLOCKS))
        sys.exit(0)
    if not os.path.isfile(os.path.join(ctx.project, ".ai", "state.json")):
        # Not inside a Shipyard project run (e.g. a one-off review or an ability eval): nothing to gate.
        ctx.debug("no .ai/state.json; findings gate not applicable")
        forget(ctx)
        return
    name = ctx.agent
    rels = candidates(ctx, name)
    existing = [(os.path.getmtime(os.path.join(ctx.project, r)), r) for r in rels
                if os.path.isfile(os.path.join(ctx.project, r))]
    if not existing:
        refuse(ctx, "%s must write its findings file before finishing: expected %s. Use the format: first line the "
                    "agent banner, then 'NO FINDINGS' or one block per finding with ID:, Severity:, Category:, "
                    "Location:, Finding:, Why it matters:, Evidence:, Required resolution:, Confidence:, Owner:, "
                    "Status:." % (ctx.agent_type, " or ".join(rels)))
    existing.sort(reverse=True)
    start = started_at(ctx)
    if start is not None:
        fresh = [e for e in existing if e[0] >= start - 1.0]
        if not fresh:
            refuse(ctx, "%s has not written its findings file during this run: %s predates the start of this "
                        "review. Rewrite it with this run's findings (or 'NO FINDINGS') before finishing."
                        % (ctx.agent_type, existing[0][1]))
        existing = fresh
    else:
        ctx.debug("no recorded start time; checking the newest findings file")
    rel = existing[0][1]
    try:
        with open(os.path.join(ctx.project, rel), "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        refuse(ctx, "cannot read %s (%s); rewrite it before finishing." % (rel, exc))
    problem = validate(text)
    if problem:
        refuse(ctx, "%s does not parse: %s. Fix the findings file before finishing." % (rel, problem))
    ctx.debug("%s is valid" % rel)
    forget(ctx)


if __name__ == "__main__":
    lib.run(HOOK, main)

#!/usr/bin/env python3
"""goldfish-blinders (PreToolUse, Read|Grep|Glob): the goldfish stays cold. It may not read anything under
`.ai/` (the elephant's sealed take, discovery notes, other goldfish output) except a slice's SLICE.md, which
READINESS mode reads. Content searches that would sweep `.ai/` from the project root are refused too."""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shipyard_hooklib as lib  # noqa: E402

HOOK = "goldfish-blinders"
ALLOWED = ".ai/slices/*/slice.md"  # compared case-folded


def fold(rel):
    """Case-fold a project-relative path: on a case-insensitive disk `.AI/` is `.ai/`."""
    return rel.lower() if isinstance(rel, str) else rel


def contains_ai(rel):
    """True when the folder `rel` is .ai/ itself, inside it, or an ancestor of it (so a recursive search
    from there reaches .ai/)."""
    if rel is None:
        return False
    rel = fold(rel)
    return rel == "" or lib.under_ai(rel) or ".ai".startswith(rel + "/")


_AI_RX = re.compile(r"(^|[/{,])\.ai($|[/},*])", re.I)


def mentions_ai(pattern):
    return isinstance(pattern, str) and bool(_AI_RX.search(pattern.replace("\\", "/")))


def deny_ai(ctx, what):
    ctx.deny("shipyard:goldfish stays cold: %s reaches into .ai/ (planning notes, the sealed elephant take, other "
             "goldfish output). Read the repository's code instead; in READINESS read only the SLICE.md named in "
             "your brief." % what)


def main(ctx):
    if ctx.agent != "goldfish":
        return
    ti = ctx.tool_input
    if ctx.tool_name == "Read":
        rel = fold(lib.normalize_path(ctx.project, ti.get("file_path"), ctx.cwd))
        if lib.under_ai(rel) and not lib.glob_match(rel, ALLOWED):
            deny_ai(ctx, "Read of '%s'" % rel)
        return
    if ctx.tool_name in ("Grep", "Glob"):
        path = ti.get("path")
        rel = lib.normalize_path(ctx.project, path, ctx.cwd) if isinstance(path, str) and path.strip() else \
            lib.normalize_path(ctx.project, ctx.cwd, ctx.project)
        rel = fold(rel)
        if lib.under_ai(rel) and not lib.glob_match(rel, ALLOWED):
            deny_ai(ctx, "%s in '%s'" % (ctx.tool_name, rel))
        for key in ("pattern", "glob") if ctx.tool_name == "Glob" else ("glob",):
            if mentions_ai(ti.get(key)):
                deny_ai(ctx, "%s with %s '%s'" % (ctx.tool_name, key, ti.get(key)))
        if ctx.tool_name == "Grep" and ti.get("output_mode") == "content" and contains_ai(rel):
            ctx.deny("shipyard:goldfish stays cold: a content search from '%s' also searches .ai/. Search a code "
                     "folder (for example src/), or use output_mode files_with_matches and Read the files you "
                     "need." % (rel or "the project root"))


if __name__ == "__main__":
    lib.run(HOOK, main)

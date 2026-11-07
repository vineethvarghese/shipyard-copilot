#!/usr/bin/env python3
"""Check that every relative Markdown link in *.md files points at an existing file or folder.

    python3 scripts/check_links.py [--root PATH]

Skips external links (http:, https:, mailto:, ...), pure #anchors, links inside fenced code blocks
and inline code, and template placeholders (targets containing <, >, {, }, * or $).
Exits 0 when every link resolves, 1 otherwise. Stdlib only.
"""

import argparse
import os
import re
import sys

DEFAULT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
LINK_RE = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+\"[^\"]*\"|\s+'[^']*')?\s*\)")
REF_DEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s+(\S+)")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
PLACEHOLDER_CHARS = set("<>{}*$")


def markdown_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.lower().endswith(".md"):
                yield os.path.join(dirpath, name)


def links_in(text):
    """Yield (line number, target) for each link outside code."""
    in_fence = None
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        fence = re.match(r"(`{3,}|~{3,})", stripped)
        if fence:
            marker = fence.group(1)[0]
            if in_fence is None:
                in_fence = marker
            elif in_fence == marker:
                in_fence = None
            continue
        if in_fence:
            continue
        code_free = re.sub(r"`+[^`]*`+", "", line)
        for m in LINK_RE.finditer(code_free):
            yield lineno, m.group(1)
        m = REF_DEF_RE.match(code_free)
        if m:
            yield lineno, m.group(1)


def check_target(md_path, target, root):
    """Return None if fine (or skipped), else a reason string."""
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if not target or target.startswith("#") or SCHEME_RE.match(target):
        return None
    if PLACEHOLDER_CHARS & set(target):
        return None
    path = target.split("#", 1)[0].split("?", 1)[0]
    if not path:
        return None
    path = path.replace("%20", " ")
    if path.startswith("/"):
        resolved = os.path.normpath(os.path.join(root, path.lstrip("/")))
    else:
        resolved = os.path.normpath(os.path.join(os.path.dirname(md_path), path))
    if not os.path.exists(resolved):
        return "broken link %s" % target
    return None


def run(root):
    problems = []
    for md in markdown_files(root):
        try:
            with open(md, encoding="utf-8") as fh:
                text = fh.read()
        except UnicodeDecodeError:
            continue
        for lineno, target in links_in(text):
            reason = check_target(md, target, root)
            if reason:
                problems.append("%s:%d: %s" % (os.path.relpath(md, root).replace(os.sep, "/"), lineno, reason))
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check relative Markdown links")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    problems = run(root)
    if problems:
        print("check_links.py: %d broken link%s" % (len(problems), "" if len(problems) == 1 else "s"))
        for p in problems:
            print("  - " + p)
        return 1
    print("check_links.py: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

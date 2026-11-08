#!/usr/bin/env python3
"""secrets-guard (PreToolUse, Edit|Write|MultiEdit): no secret values in `.ai/`. Write `<REDACTED>` and
record where the secret lives instead."""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shipyard_hooklib as lib  # noqa: E402

HOOK = "secrets-guard"

PATTERNS = [
    ("private key block", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----")),
    ("cloud access key ID", re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("chat workspace token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("JSON Web Token", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("connection-string password", re.compile(r"(?i)\b(?:password|pwd)=(?!<REDACTED>)[^;\s'\"<]{4,}")),
    ("connection-string account key", re.compile(r"(?i)\bAccountKey=(?!<REDACTED>)[^;\s'\"<]{8,}")),
    ("signed URL signature", re.compile(r"(?i)[?&]sig=(?!<REDACTED>)[^&\s'\"<]{8,}")),
    ("URL with embedded credentials", re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@<>]+:[^/\s@<>]+@")),
    ("API key, secret, token or password assignment",
     re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=]{12,}")),
]


def texts(ti):
    out = []
    for key in ("content", "new_string", "new_source"):
        if isinstance(ti.get(key), str):
            out.append(ti[key])
    if isinstance(ti.get("edits"), list):
        for e in ti["edits"]:
            if isinstance(e, dict) and isinstance(e.get("new_string"), str):
                out.append(e["new_string"])
    return out


def scan(text):
    """Return a list of (label, line number) hits. Never returns the secret itself."""
    hits = []
    for label, rx in PATTERNS:
        for m in rx.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append((label, line))
            break
    return hits


def main(ctx):
    ti = ctx.tool_input
    path = ti.get("file_path") or ti.get("notebook_path") or ti.get("path")
    extra = ti.get("extra_paths")
    candidates = [path] + [p for p in (extra if isinstance(extra, list) else []) if isinstance(p, str)]
    rels = [lib.normalize_path(ctx.project, c, ctx.cwd) for c in candidates if isinstance(c, str)]
    rels = [r for r in rels if lib.under_ai(r)]
    if not rels:
        return
    rel = rels[0]
    hits = []
    for t in texts(ti):
        hits.extend(scan(t))
    if not hits:
        return
    where = "; ".join("%s (line %d)" % h for h in hits)
    ctx.deny("possible secret in a write to %s: %s. Replace the value with `<REDACTED>` and record only where "
             "the secret lives (for example 'set in env var DB_PASSWORD' or 'stored in the team secret "
             "manager'), never the value itself." % (rel, where))


if __name__ == "__main__":
    lib.run(HOOK, main)

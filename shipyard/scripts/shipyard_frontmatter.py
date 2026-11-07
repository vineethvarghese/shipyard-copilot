"""Tiny stdlib parser for the YAML frontmatter Shipyard agent and skill files use.

Supports: `key: scalar`, quoted scalars, folded/literal block scalars (`>`, `>-`, `|`, `|-`),
indented continuation lines, block lists (`- item`), inline lists (`[a, b]`), true/false and integers.
Nested mappings are kept as raw text. This is enough for agents/*.md and skills/*/SKILL.md;
it is not a general YAML parser.
"""

import re

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:(.*)$")


class FrontmatterError(ValueError):
    pass


def split(text):
    """Return (frontmatter_text, body). Raises FrontmatterError if there is no frontmatter."""
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.splitlines(True)
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError("file does not start with a '---' frontmatter line")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "".join(lines[1:i]), "".join(lines[i + 1:])
    raise FrontmatterError("frontmatter has no closing '---' line")


def _scalar(raw):
    s = raw.strip()
    if not s:
        return ""
    if (s[0] == s[-1]) and s[0] in "\"'" and len(s) >= 2:
        inner = s[1:-1]
        return inner.replace("''", "'") if s[0] == "'" else inner.replace('\\"', '"')
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_scalar(p) for p in inner.split(",")] if inner else []
    low = s.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~"):
        return None
    if re.match(r"^-?\d+$", s):
        return int(s)
    return s


def parse(fm_text):
    """Parse frontmatter text into a dict. Raises FrontmatterError on lines it cannot place."""
    data = {}
    lines = fm_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if line[0] in " \t":
            raise FrontmatterError("unexpected indented line %d: %r" % (i + 1, line))
        m = _KEY_RE.match(line)
        if not m:
            raise FrontmatterError("cannot parse line %d: %r" % (i + 1, line))
        key, rest = m.group(1), m.group(2).strip()
        if key in data:
            raise FrontmatterError("duplicate key %r" % key)
        i += 1
        block = []
        while i < len(lines) and (not lines[i].strip() or lines[i][0] in " \t"):
            block.append(lines[i])
            i += 1
        while block and not block[-1].strip():
            block.pop()
        if rest in (">", ">-", ">+", "|", "|-", "|+"):
            texts = [b.strip() for b in block]
            if rest.startswith(">"):
                paras, cur = [], []
                for t in texts:
                    if t:
                        cur.append(t)
                    else:
                        paras.append(" ".join(cur))
                        cur = []
                paras.append(" ".join(cur))
                data[key] = "\n".join(p for p in paras if p)
            else:
                data[key] = "\n".join(texts)
        elif rest == "":
            items = [b.strip() for b in block if b.strip()]
            if items and all(t.startswith("- ") or t == "-" for t in items):
                data[key] = [_scalar(t[1:]) for t in items]
            elif items:
                data[key] = "\n".join(items)  # nested mapping: keep raw
            else:
                data[key] = None
        else:
            if block:
                data[key] = " ".join([rest] + [b.strip() for b in block if b.strip()])
            else:
                data[key] = _scalar(rest)
    return data


def read(path):
    """Return (frontmatter dict, body) for a Markdown file."""
    with open(path, encoding="utf-8") as fh:
        fm, body = split(fh.read())
    return parse(fm), body


def tools_list(value):
    """Split a `tools:` value ('Read, Grep, Agent(a, b)' or a list) into tool entries."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    out, depth, cur = [], 0, ""
    for ch in str(value):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            if cur.strip():
                out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out

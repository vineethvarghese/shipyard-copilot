"""Shared helpers for the Shipyard hooks (Python 3.9+, standard library only).

Every hook script does the same first steps: read the hook JSON from stdin, return at once for sessions that
are not Shipyard agents, find the project directory, and read `.ai/state.json` and the active slice's
`SLICE.md`. This module holds those steps plus a small, conservative shell parser used by the Bash hooks.

These hooks are guardrails, not a sandbox. They catch the mistakes an agent is likely to make; they cannot
stop a determined process (for example a script that writes files itself).
"""

import fnmatch
import json
import os
import re
import subprocess
import sys

SHIPYARD_PREFIX = "shipyard:"
ALWAYS_PROTECTED = ("main", "master")

# --------------------------------------------------------------------------------------------------------
# Input, output, logging
# --------------------------------------------------------------------------------------------------------


def debug_enabled():
    return os.environ.get("SHIPYARD_HOOK_DEBUG") == "1"


def debug(hook, msg):
    if debug_enabled():
        sys.stderr.write("[shipyard-hook:%s] %s\n" % (hook, msg))


def read_input():
    """Return the hook input as a dict, or None when stdin is empty or not a JSON object."""
    try:
        raw = sys.stdin.read()
    except Exception:  # pragma: no cover - stdin closed
        return None
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


# Output mode: "claude" (reason on stderr, exit 2) or a Copilot event name ("preToolUse", "subagentStop", ...),
# where the refusal is also printed as one JSON line on stdout. Set by run() after the payload is read.
MODE = "claude"


def copilot_mode():
    return MODE != "claude"


def deny(hook, reason):
    """Block the action: reason on stderr (fed back to the agent) and exit code 2. Under Copilot the decision
    JSON goes to stdout too (`{"permissionDecision": "deny", ...}` for preToolUse, `{"decision": "block", ...}`
    for subagentStop, where exit 2 would only be a warning, so that one exits 0)."""
    text = "Shipyard %s blocked this: %s" % (hook, reason)
    sys.stderr.write(text + "\n")
    if copilot_mode():
        import copilot_hooklib
        payload, code = copilot_hooklib.deny_json(MODE, text)
        if payload:
            sys.stdout.write(payload + "\n")
            sys.stdout.flush()
        sys.exit(code)
    sys.exit(2)


def allow(hook=None, msg=None):
    if hook and msg:
        debug(hook, "allow: " + msg)
    sys.exit(0)


def is_shipyard(agent_type):
    return isinstance(agent_type, str) and agent_type.startswith(SHIPYARD_PREFIX)


def short_name(agent_type):
    return agent_type[len(SHIPYARD_PREFIX):] if is_shipyard(agent_type) else ""


class Context(object):
    """The parsed hook input plus the project it applies to."""

    def __init__(self, hook, data):
        self.hook = hook
        self.data = data
        self.agent_type = data.get("agent_type") or ""
        self.agent = short_name(self.agent_type)
        self.tool_name = data.get("tool_name") or ""
        ti = data.get("tool_input")
        self.tool_input = ti if isinstance(ti, dict) else {}
        self.project = project_dir(data)
        cwd = data.get("cwd")
        self.cwd = real(cwd) if isinstance(cwd, str) and cwd else self.project
        self._state = None
        self._state_err = None
        self._state_loaded = False

    def state(self):
        """Return (state dict or None, error message or None). Cached."""
        if not self._state_loaded:
            self._state, self._state_err = load_state(self.project)
            self._state_loaded = True
        return self._state, self._state_err

    def deny(self, reason):
        deny(self.hook, reason)

    def debug(self, msg):
        debug(self.hook, msg)

    @property
    def copilot(self):
        """True when the input came from GitHub Copilot (adapted by copilot_hooklib)."""
        return self.data.get("_copilot") is True


def _event_arg(argv):
    """`--event NAME` on the hook's command line (used by the Copilot wiring, where the payload has no event)."""
    for i, a in enumerate(argv):
        if a == "--event" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--event="):
            return a.split("=", 1)[1]
    return None


def run(hook, main, require_shipyard=True):
    """Common entry point. Non-Shipyard sessions always pass. Unexpected errors fail closed for Shipyard.

    A Copilot payload (`toolName`/`toolArgs`, or a subagent event with `agentName`) is first turned into the
    Claude shape by `copilot_hooklib.adapt`, which also infers the Shipyard role (SHIPYARD_ROLE, the agent name
    in the payload, then `.ai/state.json` activeRole). No role means no Shipyard agent: exit 0, no output."""
    global MODE
    data = read_input()
    if data is None:
        debug(hook, "no JSON input; allowing")
        sys.exit(0)
    import copilot_hooklib
    if copilot_hooklib.is_copilot_payload(data):
        try:
            data = copilot_hooklib.adapt(data, _event_arg(sys.argv[1:]))
        except Exception as exc:  # cannot even read the payload: stay out of the way
            debug(hook, "could not adapt the Copilot payload (%s: %s); allowing" % (type(exc).__name__, exc))
            sys.exit(0)
        MODE = data["_copilot_event"]
        debug(hook, "copilot event=%s tool=%s role=%r (from %s)" % (
            MODE, data.get("tool_name"), data.get("agent_type"), data.get("_role_source")))
    elif os.environ.get("SHIPYARD_ROLE", "").strip() and not is_shipyard(data.get("agent_type")):
        role = copilot_hooklib.infer_role({}, project_dir(data))[0]
        data["agent_type"] = (SHIPYARD_PREFIX + role) if role else ""
    agent_type = data.get("agent_type")
    if require_shipyard and not is_shipyard(agent_type):
        debug(hook, "agent_type %r is not a Shipyard agent; allowing" % (agent_type,))
        sys.exit(0)
    ctx = Context(hook, data)
    try:
        main(ctx)
    except SystemExit:
        raise
    except Exception as exc:  # fail closed for Shipyard agents
        deny(hook, "internal hook error (%s: %s); failing closed. Re-run with SHIPYARD_HOOK_DEBUG=1 and "
                   "report the problem." % (type(exc).__name__, exc))
    sys.exit(0)


# --------------------------------------------------------------------------------------------------------
# Project, paths, state
# --------------------------------------------------------------------------------------------------------


def real(path):
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


def project_dir(data):
    env = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("SHIPYARD_PROJECT_DIR")
    if env:
        return real(env)
    found = data.get("project_dir") if isinstance(data, dict) else None  # set by the Copilot adapter
    if isinstance(found, str) and found:
        return real(found)
    cwd = data.get("cwd") if isinstance(data, dict) else None
    if isinstance(cwd, str) and cwd:
        return real(cwd)
    return real(os.getcwd())


def normalize_path(project, path, base=None):
    """Return `path` relative to `project` in POSIX form, or None when it lies outside the project."""
    if not isinstance(path, str) or not path.strip():
        return None
    p = os.path.expanduser(path.strip())
    if not os.path.isabs(p):
        p = os.path.join(base or project, p)
    p = real(p)
    try:
        rel = os.path.relpath(p, project)
    except ValueError:  # different drive on Windows
        return None
    rel = rel.replace(os.sep, "/")
    if rel == ".." or rel.startswith("../") or os.path.isabs(rel):
        return None
    return "" if rel == "." else rel


def under_ai(rel):
    return rel is not None and (rel == ".ai" or rel.startswith(".ai/"))


def load_state(project):
    path = os.path.join(project, ".ai", "state.json")
    if not os.path.isfile(path):
        return None, ".ai/state.json is missing"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, ".ai/state.json is unreadable or not valid JSON (%s)" % exc
    if not isinstance(state, dict):
        return None, ".ai/state.json is not a JSON object"
    return state, None


def active_slice(state):
    if not isinstance(state, dict):
        return None
    sid = state.get("activeSlice")
    if isinstance(sid, str) and sid.strip() and "/" not in sid and sid not in (".", ".."):
        return sid.strip()
    return None


def slice_rel(sid, name):
    return ".ai/slices/%s/%s" % (sid, name)


# --------------------------------------------------------------------------------------------------------
# SLICE.md touch sets and TEST_PLAN.md status
# --------------------------------------------------------------------------------------------------------

_TOUCH_HEADING = re.compile(r"^#{2,6}\s+Expected touch set\s*[—–-]+\s*(code|tests?)\s*$", re.I)
_ANY_HEADING = re.compile(r"^#{1,6}\s")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*\S)\s*$")


def parse_touch_sets(text):
    """Return {'code': [...], 'tests': [...]} or {} keys missing when the heading is absent."""
    sets = {}
    current = None
    for line in text.splitlines():
        m = _TOUCH_HEADING.match(line.strip())
        if m:
            current = "code" if m.group(1).lower() == "code" else "tests"
            sets.setdefault(current, [])
            continue
        if _ANY_HEADING.match(line.strip()):
            current = None
            continue
        if current is None:
            continue
        b = _BULLET.match(line)
        if not b:
            continue
        item = b.group(1).strip().strip("`").strip()
        item = item.split()[0].strip("`") if item else ""
        if not item or item.lower() in ("none", "(none)", "n/a", "-"):
            continue
        if item.startswith("./"):
            item = item[2:]
        sets[current].append(item)
    return sets


def load_touch_sets(project, state):
    """Return (sets, error). sets has keys 'code' and 'tests'."""
    sid = active_slice(state)
    if not sid:
        return None, "state.json has no activeSlice"
    rel = slice_rel(sid, "SLICE.md")
    path = os.path.join(project, rel)
    if not os.path.isfile(path):
        return None, "%s is missing" % rel
    try:
        with open(path, "r", encoding="utf-8") as fh:
            sets = parse_touch_sets(fh.read())
    except OSError as exc:
        return None, "%s is unreadable (%s)" % (rel, exc)
    missing = [k for k in ("code", "tests") if k not in sets]
    if missing:
        return None, "%s has no '## Expected touch set — %s' section" % (rel, missing[0])
    return sets, None


_STATUS_LINE = re.compile(r"^Status:\s*(DRAFT|APPROVED)\s*$")


def plan_status_from_text(text):
    for line in text.splitlines()[:10]:
        m = _STATUS_LINE.match(line.strip())
        if m:
            return m.group(1)
    return None


def test_plan_status(path):
    """'APPROVED', 'DRAFT', None (no status line) or 'MISSING' (no file)."""
    if not os.path.isfile(path):
        return "MISSING"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return plan_status_from_text(fh.read())
    except OSError:
        return "MISSING"


# --------------------------------------------------------------------------------------------------------
# Globs
# --------------------------------------------------------------------------------------------------------

_GLOB_CACHE = {}


def glob_to_regex(pattern):
    if pattern in _GLOB_CACHE:
        return _GLOB_CACHE[pattern]
    pat = pattern.strip()
    if pat.startswith("./"):
        pat = pat[2:]
    if pat.startswith("/"):
        pat = pat[1:]
    if pat.endswith("/"):
        pat += "**"
    i, n, out = 0, len(pat), []
    while i < n:
        c = pat[i]
        if c == "*":
            if pat.startswith("**", i):
                j = i + 2
                if j < n and pat[j] == "/":
                    out.append("(?:.*/)?")
                    i = j + 1
                else:
                    out.append(".*")
                    i = j
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = pat.find("]", i + 1)
            if j == -1:
                out.append(re.escape(c))
            else:
                body = pat[i + 1:j]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    rx = re.compile("^" + "".join(out) + "$")
    _GLOB_CACHE[pattern] = rx
    return rx


def glob_match(rel, pattern):
    if glob_to_regex(pattern).match(rel):
        return True
    # A plain directory entry (no wildcard) covers everything below it.
    if not any(ch in pattern for ch in "*?[") and rel.startswith(pattern.rstrip("/") + "/"):
        return True
    return False


def match_any(rel, patterns):
    for p in patterns or []:
        if glob_match(rel, p):
            return p
    return None


# --------------------------------------------------------------------------------------------------------
# Git
# --------------------------------------------------------------------------------------------------------


def git(args, cwd):
    try:
        res = subprocess.run(["git"] + list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             universal_newlines=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip()


def current_branch(cwd):
    """Branch name, 'HEAD' when detached, or None when not a git repo. Uses `git rev-parse --abbrev-ref HEAD`,
    falling back to `git symbolic-ref` for a branch with no commits yet."""
    return git(["rev-parse", "--abbrev-ref", "HEAD"], cwd) or git(["symbolic-ref", "--short", "-q", "HEAD"], cwd)


def default_branch(cwd):
    out = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd)
    if out and "/" in out:
        return out.split("/", 1)[1]
    return None


def branch_exists(name, cwd):
    return git(["rev-parse", "--verify", "--quiet", "refs/heads/" + name], cwd) is not None


def protected_patterns(state, cwd):
    pats = set(ALWAYS_PROTECTED)
    if isinstance(state, dict):
        for b in state.get("protectedBranches") or []:
            if isinstance(b, str) and b.strip():
                pats.add(b.strip())
        base = state.get("baseBranch")
        if isinstance(base, str) and base.strip():
            pats.add(base.strip())
    d = default_branch(cwd)
    if d:
        pats.add(d)
    return pats


def strip_ref(name):
    if not isinstance(name, str):
        return name
    for prefix in ("refs/heads/",):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def is_protected(branch, patterns):
    if not branch:
        return False
    branch = strip_ref(branch)
    return any(fnmatch.fnmatchcase(branch, p) for p in patterns)


# --------------------------------------------------------------------------------------------------------
# Shell parsing (conservative)
# --------------------------------------------------------------------------------------------------------

_OPERATORS = sorted(["&&", "||", ";;", ">>", "&>>", "&>", ">&", ">|", "<<<", "<<-", "<<", "<&", "<>", "|&",
                     ";", "|", "&", "(", ")", ">", "<", "\n"], key=len, reverse=True)
SEPARATORS = {"&&", "||", ";;", ";", "|", "|&", "&", "(", ")", "\n"}
OUTPUT_REDIRECTS = {">", ">>", ">|", "&>", "&>>", ">&", "<>"}
INPUT_REDIRECTS = {"<", "<<", "<<-", "<<<", "<&"}
_RESERVED = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}", "time", "fi", "done"}
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\])?\+?=")


class SimpleCommand(object):
    def __init__(self, argv, redirects):
        self.argv = argv
        self.redirects = redirects  # list of (op, target or None)

    @property
    def name(self):
        return os.path.basename(self.argv[0]) if self.argv else ""

    def __repr__(self):  # pragma: no cover - debugging aid
        return "SimpleCommand(%r, %r)" % (self.argv, self.redirects)


def _match_close(s, start, close=")"):
    """Index of the closing paren for a `$(` whose body starts at `start` (quote-aware, nesting-aware)."""
    depth, i, n = 1, start, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            j = s.find("'", i + 1)
            i = n if j < 0 else j + 1
            continue
        if c == '"':
            i += 1
            while i < n and s[i] != '"':
                i += 2 if s[i] == "\\" else 1
            i += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def _lex(s, subs):
    """Tokenise a shell string into ('w', text, quoted) and ('op', text). Command substitutions are
    appended to `subs` so they can be checked as commands of their own."""
    tokens = []
    word, in_word, quoted = [], False, False
    pending_heredocs, expect_delim = [], [False]
    i, n = 0, len(s)

    def flush():
        if in_word:
            text = "".join(word)
            if expect_delim[0]:
                pending_heredocs.append(text)
                expect_delim[0] = False
            tokens.append(("w", text, quoted))

    while i < n:
        c = s[i]
        if c == "\\":
            if i + 1 < n:
                if s[i + 1] == "\n":
                    i += 2
                    continue
                word.append(s[i + 1])
                in_word, quoted = True, True
                i += 2
            else:
                i += 1
            continue
        if c == "'":
            j = s.find("'", i + 1)
            j = n if j < 0 else j
            word.append(s[i + 1:j])
            in_word, quoted = True, True
            i = j + 1
            continue
        if c == '"':
            i += 1
            in_word, quoted = True, True
            while i < n and s[i] != '"':
                if s[i] == "\\" and i + 1 < n:
                    word.append(s[i + 1])
                    i += 2
                    continue
                if s.startswith("$(", i) and not s.startswith("$((", i):
                    j = _match_close(s, i + 2)
                    subs.append(s[i + 2:j])
                    word.append("$(...)")
                    i = j + 1
                    continue
                if s[i] == "`":
                    j = s.find("`", i + 1)
                    j = n if j < 0 else j
                    subs.append(s[i + 1:j])
                    word.append("`...`")
                    i = j + 1
                    continue
                word.append(s[i])
                i += 1
            i += 1
            continue
        if c == "$" and s.startswith("$(", i) and not s.startswith("$((", i):
            j = _match_close(s, i + 2)
            subs.append(s[i + 2:j])
            word.append("$(...)")
            in_word = True
            i = j + 1
            continue
        if c == "`":
            j = s.find("`", i + 1)
            j = n if j < 0 else j
            subs.append(s[i + 1:j])
            word.append("`...`")
            in_word = True
            i = j + 1
            continue
        if c == "#" and not in_word:
            j = s.find("\n", i)
            i = n if j < 0 else j
            continue
        if c in " \t\r":
            flush()
            word, in_word, quoted = [], False, False
            i += 1
            continue
        op = None
        for cand in _OPERATORS:
            if s.startswith(cand, i):
                op = cand
                break
        if op:
            if op[0] in "<>" and in_word and not quoted and "".join(word).isdigit():
                word, in_word = [], False  # file-descriptor prefix such as 2>
            flush()
            word, in_word, quoted = [], False, False
            tokens.append(("op", op))
            i += len(op)
            if op in ("<<", "<<-"):
                expect_delim[0] = True
            if op == "\n" and pending_heredocs:
                for delim in pending_heredocs:
                    while i < n:
                        j = s.find("\n", i)
                        j = n if j < 0 else j
                        line = s[i:j]
                        i = j + 1
                        if line.strip() == delim:
                            break
                pending_heredocs = []
            continue
        word.append(c)
        in_word = True
        i += 1
    flush()
    return tokens


def _split_commands(tokens):
    cmds = []
    argv, redirs = [], []
    i, n = 0, len(tokens)
    while i < n:
        t = tokens[i]
        if t[0] == "op":
            op = t[1]
            if op in SEPARATORS:
                if argv or redirs:
                    cmds.append(SimpleCommand(argv, redirs))
                argv, redirs = [], []
                i += 1
                continue
            target = None
            if i + 1 < n and tokens[i + 1][0] == "w":
                target = tokens[i + 1][1]
                i += 1
            redirs.append((op, target))
            i += 1
            continue
        argv.append(t[1])
        i += 1
    if argv or redirs:
        cmds.append(SimpleCommand(argv, redirs))
    return cmds


_SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "ash", "fish"}


def _skip_opts(args, with_value=()):
    """Skip leading options; `with_value` options consume the following token."""
    i = 0
    while i < len(args) and args[i].startswith("-") and args[i] != "-":
        if args[i] == "--":
            return args[i + 1:]
        if args[i] in with_value:
            i += 2
        else:
            i += 1
    return args[i:]


def unwrap(argv):
    """Strip environment assignments and wrapper commands (env, command, nice, timeout, xargs, ...).
    Returns (argv, wrappers) where wrappers lists the wrapper names removed."""
    wrappers = []
    changed = True
    while argv and changed:
        changed = False
        while argv and (_ASSIGN.match(argv[0]) or argv[0] in _RESERVED):
            argv = argv[1:]
            changed = True
        if not argv:
            break
        name = os.path.basename(argv[0])
        rest = argv[1:]
        if name == "env":
            rest = _skip_opts(rest, ("-u", "--unset", "-C", "--chdir", "-S", "--split-string"))
            while rest and _ASSIGN.match(rest[0]):
                rest = rest[1:]
        elif name == "command":
            if rest and rest[0] in ("-v", "-V"):
                return [], wrappers + [name]
            rest = _skip_opts(rest)
        elif name in ("nice", "ionice"):
            rest = _skip_opts(rest, ("-n", "--adjustment", "-c", "-p", "-t"))
        elif name in ("nohup", "exec", "builtin", "unbuffer", "chronic"):
            rest = _skip_opts(rest, ("-a",))
        elif name == "stdbuf":
            rest = _skip_opts(rest, ("-i", "-o", "-e"))
        elif name == "timeout":
            rest = _skip_opts(rest, ("-s", "--signal", "-k", "--kill-after"))
            rest = rest[1:] if rest else rest
        elif name in ("sudo", "doas"):
            rest = _skip_opts(rest, ("-u", "-g", "-h", "-p", "-C", "-D", "-U", "-r", "-t"))
        elif name == "xargs":
            rest = _skip_opts(rest, ("-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a", "-i", "-l", "-e",
                                     "--max-args", "--max-procs", "--delimiter", "--arg-file", "--replace"))
        elif name == "time":
            rest = _skip_opts(rest, ("-f", "-o", "--format", "--output"))
        else:
            break
        wrappers.append(name)
        argv = rest
        changed = True
    return argv, wrappers


def parse_commands(cmd, _depth=0):
    """Parse a shell string into a flat list of (SimpleCommand, wrappers). Nested `bash -c`, `eval`,
    command substitutions and `find -exec` bodies become commands of their own."""
    if not isinstance(cmd, str) or _depth > 6:
        return []
    subs = []
    tokens = _lex(cmd, subs)
    out = []
    for sc in _split_commands(tokens):
        argv, wrappers = unwrap(sc.argv)
        sc.argv = argv
        out.append((sc, wrappers))
        if not argv:
            continue
        name = os.path.basename(argv[0])
        if name in _SHELLS:
            for k, a in enumerate(argv[1:], start=1):
                if a == "-c" or (a.startswith("-") and not a.startswith("--") and "c" in a[1:]):
                    if k + 1 < len(argv):
                        out.extend(parse_commands(argv[k + 1], _depth + 1))
                    break
        elif name == "eval":
            out.extend(parse_commands(" ".join(argv[1:]), _depth + 1))
        elif name == "find":
            k = 1
            while k < len(argv):
                if argv[k] in ("-exec", "-execdir", "-ok", "-okdir"):
                    j = k + 1
                    while j < len(argv) and argv[j] not in (";", "+"):
                        j += 1
                    body = [a for a in argv[k + 1:j] if a != "{}"]
                    if body:
                        inner, w = unwrap(body)
                        out.append((SimpleCommand(inner, []), w))
                    k = j
                k += 1
    for sub in subs:
        out.extend(parse_commands(sub, _depth + 1))
    return out


# --------------------------------------------------------------------------------------------------------
# Git command-line parsing
# --------------------------------------------------------------------------------------------------------

_GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env",
                          "--super-prefix", "--list-cmds"}


class GitCall(object):
    def __init__(self, sub, args, dirs, config):
        self.sub = sub
        self.args = args
        self.dirs = dirs  # successive -C values
        self.config = config  # -c key=value pairs

    def workdir(self, base):
        d = base
        for c in self.dirs:
            d = c if os.path.isabs(c) else os.path.join(d, c)
        return d


def parse_git(argv):
    """argv[0] is git. Returns GitCall (sub may be None)."""
    i, dirs, config = 1, [], {}
    while i < len(argv):
        a = argv[i]
        if a in _GIT_GLOBAL_WITH_VALUE:
            val = argv[i + 1] if i + 1 < len(argv) else ""
            if a == "-C":
                dirs.append(val)
            elif a == "-c" and "=" in val:
                k, v = val.split("=", 1)
                config[k.lower()] = v
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        break
    sub = argv[i] if i < len(argv) else None
    return GitCall(sub, list(argv[i + 1:]), dirs, config)


def expand_git_alias(gc, cwd, depth=0):
    """Resolve a git alias (from -c or git config). Returns a list of GitCall or SimpleCommand-argv lists.
    Result: ('git', GitCall) entries or ('shell', str) for '!'-aliases."""
    if gc.sub is None or depth > 4:
        return [("git", gc)]
    key = "alias." + gc.sub.lower()
    val = gc.config.get(key)
    if val is None and gc.sub not in KNOWN_GIT_COMMANDS:
        val = git(["config", "--get", key], cwd)
    if not val:
        return [("git", gc)]
    if val.startswith("!"):
        return [("shell", val[1:] + " " + " ".join(gc.args))]
    try:
        import shlex
        parts = shlex.split(val)
    except ValueError:
        parts = val.split()
    new = parse_git(["git"] + parts + gc.args)
    new.dirs = gc.dirs + new.dirs
    new.config = dict(gc.config, **new.config)
    return expand_git_alias(new, cwd, depth + 1)


KNOWN_GIT_COMMANDS = set("""
add am annotate apply archive bisect blame branch bundle cat-file check-attr check-ignore check-mailmap
check-ref-format checkout checkout-index cherry cherry-pick citool clean clone column commit commit-graph
commit-tree config count-objects credential describe diff diff-files diff-index diff-tree difftool fast-export
fast-import fetch fetch-pack filter-branch filter-repo fmt-merge-msg for-each-ref format-patch fsck gc
get-tar-commit-id grep gui hash-object help http-push index-pack init instaweb interpret-trailers log ls-files
ls-remote ls-tree mailinfo mailsplit maintenance merge merge-base merge-file merge-index merge-tree mergetool
mktag mktree mv name-rev notes pack-objects pack-redundant pack-refs prune prune-packed pull push range-diff
read-tree rebase receive-pack reflog remote repack replace request-pull rerere reset restore rev-list rev-parse
revert rm send-email send-pack shortlog show show-branch show-index show-ref sparse-checkout stage stash status
stripspace submodule switch symbolic-ref tag unpack-file unpack-objects update-index update-ref
update-server-info upload-archive upload-pack var verify-commit verify-pack verify-tag version whatchanged
worktree write-tree
""".split())


CD_COMMANDS = {"cd", "pushd", "popd", "chdir"}


def git_calls(cmds, cwd, on_shell=None):
    """Yield (GitCall, workdir) for every git invocation in parsed commands, aliases resolved.
    `on_shell(parsed)` is called with the commands of each '!' shell alias before its git calls are yielded."""
    queue = list(cmds)
    seen = 0
    while queue and seen < 200:
        seen += 1
        sc, _w = queue.pop(0)
        if not sc.argv or os.path.basename(sc.argv[0]) != "git":
            continue
        gc = parse_git(sc.argv)
        workdir = gc.workdir(cwd)
        for kind, item in expand_git_alias(gc, workdir):
            if kind == "git":
                yield item, item.workdir(cwd)
            else:
                parsed = parse_commands(item)
                if on_shell is not None:
                    on_shell(parsed)
                queue.extend(parsed)


# Branch-listing flags vs mutating flags for `git branch`.
BRANCH_MUTATING = {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy", "-f", "--force", "-u",
                   "--set-upstream-to", "--unset-upstream", "--edit-description", "-t", "--track", "--no-track",
                   "--create-reflog"}
BRANCH_LISTING = {"-l", "--list", "-a", "--all", "-r", "--remotes", "--contains", "--no-contains", "--merged",
                  "--no-merged", "--points-at", "--show-current", "-v", "-vv", "--verbose", "--sort",
                  "--format", "--column", "--no-column", "--color", "--no-color", "-i", "--ignore-case",
                  "--abbrev", "--no-abbrev", "-q", "--quiet"}


def branch_flags(args):
    flags = set()
    for a in args:
        if a.startswith("--"):
            flags.add(a.split("=", 1)[0])
        elif a.startswith("-") and len(a) > 1:
            if a in ("-vv",):
                flags.add(a)
            else:
                for ch in a[1:]:
                    flags.add("-" + ch)
    return flags


def branch_positionals(args):
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a in ("--contains", "--no-contains", "--merged", "--no-merged", "--points-at", "--sort", "--format",
                 "-u", "--set-upstream-to", "--column"):
            skip = True
            continue
        if a.startswith("-"):
            continue
        out.append(a)
    return out


def branch_is_read_only(args):
    flags = branch_flags(args)
    if flags & BRANCH_MUTATING:
        return False
    pos = branch_positionals(args)
    if not pos:
        return True
    return bool(flags & {"-l", "--list", "--contains", "--no-contains", "--merged", "--no-merged",
                         "--points-at"})


# --------------------------------------------------------------------------------------------------------
# Paths a shell command writes (best effort; used to apply the write-scope and test-plan rules to Bash)
# --------------------------------------------------------------------------------------------------------

_SINKS = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "-"}
_INPLACE = {"sed", "perl", "ruby"}
_TARGET_LAST = {"cp", "install", "rsync", "ln"}
_TARGET_ALL = {"touch", "truncate", "rm", "rmdir", "unlink", "shred", "chmod", "chown", "chgrp"}


def _positionals(args, with_value=()):
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            out.extend(args[i + 1:])
            break
        if a in with_value:
            i += 2
            continue
        if not a.startswith("-") or a == "-":
            out.append(a)
        i += 1
    return out


def _is_inplace_flag(name, a):
    if a.startswith("--"):
        return a.startswith("--in-place")
    if not a.startswith("-") or len(a) < 2:
        return False
    if name != "sed" and a[1] in "MIeEx0":  # perl/ruby options whose value may contain an 'i'
        return False
    return "i" in re.match(r"-[A-Za-z]*", a).group(0)


def bash_write_targets(cmds):
    """Return the paths a parsed command line would write, move or delete, as written in the command.
    Covers output redirections, tee, in-place editors, cp/mv/install/rsync/ln targets, touch/rm/truncate
    and friends, dd of=, and git rm/mv/restore/checkout pathspecs. It cannot see writes made by
    interpreters (python -c, node -e) or by build tools; those are documented gaps."""
    out = []
    for sc, _w in cmds:
        for op, target in sc.redirects:
            if op not in OUTPUT_REDIRECTS or target is None:
                continue
            if op == ">&" and (target.isdigit() or target == "-"):
                continue
            if target in _SINKS or target.startswith("&"):
                continue
            out.append(target)
        if not sc.argv:
            continue
        name, args = sc.name, sc.argv[1:]
        if name == "tee":
            out.extend(a for a in _positionals(args) if a not in _SINKS)
        elif name in _INPLACE and any(_is_inplace_flag(name, a) for a in args):
            has_script_opt = any(a in ("-e", "-f", "--expression", "--file") for a in args)
            pos = _positionals(args, ("-e", "-f", "--expression", "--file", "-I", "-M", "-m"))
            out.extend(pos if has_script_opt else pos[1:])
        elif name == "mv":
            out.extend(_positionals(args, ("-t", "--target-directory", "-S", "--suffix")))
        elif name in _TARGET_LAST:
            pos = _positionals(args, ("-t", "--target-directory", "-S", "--suffix", "-m", "--mode", "-o", "-g"))
            out.extend(pos[-1:])
        elif name in _TARGET_ALL:
            out.extend(_positionals(args, ("-s", "--size", "-r", "--reference", "-n", "--iterations")))
        elif name == "dd":
            out.extend(a[3:] for a in args if a.startswith("of="))
        elif name == "curl":
            for i, a in enumerate(args):
                if a in ("-o", "--output") and i + 1 < len(args):
                    out.append(args[i + 1])
                elif a.startswith("--output="):
                    out.append(a.split("=", 1)[1])
                elif re.match(r"^-[A-Za-z]*o$", a) and i + 1 < len(args):
                    out.append(args[i + 1])
        elif name == "wget":
            for i, a in enumerate(args):
                if a in ("-O", "--output-document") and i + 1 < len(args):
                    out.append(args[i + 1])
                elif a.startswith("--output-document="):
                    out.append(a.split("=", 1)[1])
        elif name == "git":
            gc = parse_git(sc.argv)
            if gc.sub in ("rm", "mv", "restore"):
                out.extend(_positionals(gc.args, ("-s", "--source", "--pathspec-from-file")))
            elif gc.sub == "checkout" and "--" in gc.args:
                out.extend(gc.args[gc.args.index("--") + 1:])
    return [t for t in out if t and t not in _SINKS]


def under_git_dir(rel):
    return rel is not None and (rel == ".git" or rel.startswith(".git/"))


def has_cd(cmds):
    """True when the command line changes directory (cd, pushd, popd) anywhere."""
    return any(sc.argv and sc.name in CD_COMMANDS for sc, _ in cmds)


def _dest_outside(project, cwd, dest):
    if not dest:
        return False
    d = os.path.expanduser(dest)
    return os.path.isabs(d) and normalize_path(project, d, cwd) is None


def bash_opaque_writers(cmds, project, cwd):
    """Commands that write files in the project whose paths the command line does not show: patch application,
    stash pop/apply, archive extraction into the project, and downloads named by the server. Returns short
    descriptions; empty when none."""
    out = []
    for sc, _w in cmds:
        if not sc.argv:
            continue
        name, args = sc.name, sc.argv[1:]
        if name == "git":
            gc = parse_git(sc.argv)
            if gc.sub == "apply" and not any(a in ("--check", "--stat", "--numstat", "--summary") for a in gc.args):
                out.append("git apply")
            elif gc.sub == "stash" and gc.args[:1] in (["pop"], ["apply"]):
                out.append("git stash %s" % gc.args[0])
        elif name == "patch" and "--dry-run" not in args:
            out.append("patch")
        elif name == "unzip" and not any(a in ("-l", "-v", "-t", "-Z") for a in args):
            dest = args[args.index("-d") + 1] if "-d" in args and args.index("-d") + 1 < len(args) else None
            if not _dest_outside(project, cwd, dest):
                out.append("unzip")
        elif name == "tar" and args and ("x" in args[0].lstrip("-") and not args[0].startswith("--")
                                        or "--extract" in args or "-x" in args):
            dest = None
            for i, a in enumerate(args):
                if a in ("-C", "--directory") and i + 1 < len(args):
                    dest = args[i + 1]
                elif a.startswith("--directory="):
                    dest = a.split("=", 1)[1]
            if not _dest_outside(project, cwd, dest):
                out.append("tar extract")
        elif name == "curl" and any(a in ("-O", "--remote-name", "--remote-name-all") or
                                    re.match(r"^-[A-Za-z]*O[A-Za-z]*$", a) for a in args):
            out.append("curl -O")
        elif name == "wget" and not any(a in ("-O", "--output-document", "--spider") or
                                        a.startswith("--output-document=") for a in args):
            out.append("wget (saves into the current folder)")
    return out

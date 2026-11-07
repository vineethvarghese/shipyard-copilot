#!/usr/bin/env python3
"""readonly-bash (PreToolUse, Bash): planning, review and brainstorming roles run read-only commands only.
Builds and tests stay allowed; installs, git state changes, file deletion and writes outside `.ai/` do not.
The goldfish gets an even shorter list: read-only inspection commands only."""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shipyard_hooklib as lib  # noqa: E402

HOOK = "readonly-bash"
READONLY_ROLES = {"discovery", "goldfish", "architect", "planner", "code-reviewer", "security-reviewer",
                  "contract-reviewer", "integration-reviewer", "reliability-reviewer", "simplicity-reviewer"}

GOLDFISH_COMMANDS = {"ls", "cat", "grep", "egrep", "fgrep", "rg", "find", "git", "wc", "head", "tail", "pwd", "cd"}
GOLDFISH_GIT = {"log", "show", "diff", "ls-files"}

GIT_READ_ONLY = {"log", "diff", "show", "status", "rev-parse", "ls-files", "ls-tree", "blame", "annotate", "grep",
                 "describe", "shortlog", "cat-file", "rev-list", "merge-base", "for-each-ref", "show-ref",
                 "name-rev", "diff-tree", "diff-files", "diff-index", "check-ignore", "check-attr",
                 "check-ref-format", "count-objects", "whatchanged", "range-diff", "help", "version", "var",
                 "verify-commit", "verify-tag", "show-branch", "cherry", "check-mailmap"}

DESTRUCTIVE = {"rm", "rmdir", "mv", "chmod", "chown", "chgrp", "truncate", "dd", "shred", "unlink", "ln"}
SAFE_SINKS = {"/dev/null", "/dev/stdout", "/dev/stderr", "-"}
PRIV = {"sudo", "doas", "su"}


class Denied(Exception):
    pass


def no(msg):
    raise Denied(msg)


def first_positional(args, value_opts=()):
    i = 0
    while i < len(args):
        a = args[i]
        if a in value_opts:
            i += 2
            continue
        if not a.startswith("-"):
            return a, args[i + 1:]
        i += 1
    return None, []


def path_ok(ctx, target, goldfish):
    """Output target is /dev/null-like, or (non-goldfish) a path under the project's .ai/."""
    if target is None:
        return True
    if target in SAFE_SINKS or target.isdigit() or target == "&1" or target == "&2":
        return True
    if goldfish:
        return False
    rel = lib.normalize_path(ctx.project, target, ctx.cwd)
    return lib.under_ai(rel)


def check_redirects(ctx, sc, goldfish):
    for op, target in sc.redirects:
        if op not in lib.OUTPUT_REDIRECTS:
            continue
        if op == ">&" and target is not None and (target.isdigit() or target == "-"):
            continue
        if not path_ok(ctx, target, goldfish):
            no("output redirection `%s %s` writes outside .ai/. Read-only roles may redirect only to /dev/null"
               "%s." % (op, target, "" if goldfish else " or into .ai/"))


def check_packages(name, args):
    sub, rest = first_positional(args)
    if name in ("npm", "pnpm"):
        bad = {"install", "i", "in", "ins", "inst", "insta", "instal", "isnt", "isnta", "isntal", "add", "ci",
               "clean-install", "install-test", "it", "install-ci-test", "cit", "uninstall", "un", "remove", "rm",
               "r", "unlink", "update", "up", "upgrade", "link", "ln", "dedupe", "prune", "publish"}
        if sub in bad:
            no("`%s %s` installs, removes or publishes packages; read-only roles may not." % (name, sub))
    elif name == "yarn":
        if sub is None or sub in {"install", "add", "remove", "upgrade", "up", "upgrade-interactive", "link",
                                  "unlink", "publish", "dlx"}:
            no("`yarn%s` installs or changes packages; read-only roles may not." % (" " + sub if sub else ""))
    elif name in ("pip", "pip3", "pipx"):
        if sub in ("install", "uninstall", "download"):
            no("`%s %s` changes installed packages; read-only roles may not." % (name, sub))
    elif re.match(r"^python[0-9.]*$", name):
        if len(args) >= 3 and args[0] == "-m" and args[1] in ("pip", "pip3", "ensurepip") and \
                args[2] in ("install", "uninstall"):
            no("`%s -m pip %s` changes installed packages; read-only roles may not." % (name, args[2]))
    elif name == "uv":
        if sub in ("add", "remove", "sync") or (sub == "pip" and rest[:1] and rest[0] in ("install", "uninstall")) \
                or (sub == "tool" and rest[:1] == ["install"]):
            no("`uv %s` installs or changes packages; read-only roles may not." % sub)
    elif name in ("poetry", "pipenv", "conda", "mamba"):
        if sub in ("add", "install", "remove", "update", "uninstall", "sync", "lock"):
            no("`%s %s` installs or changes packages; read-only roles may not." % (name, sub))
    elif name == "cargo":
        if sub in ("add", "install", "remove", "rm", "uninstall", "update", "publish"):
            no("`cargo %s` installs, changes or publishes packages; read-only roles may not." % sub)
    elif name == "go":
        if sub in ("get", "install") or (sub == "mod" and rest[:1] and rest[0] in ("tidy", "edit", "vendor",
                                                                                   "download")):
            no("`go %s` installs or changes modules; read-only roles may not." % " ".join([sub] + rest[:1]))
    elif name == "gem":
        if sub in ("install", "uninstall", "update", "push"):
            no("`gem %s` changes installed packages; read-only roles may not." % sub)
    elif name == "bundle":
        if sub is None or sub in ("install", "add", "update", "remove"):
            no("`bundle%s` installs or changes gems; read-only roles may not." % (" " + sub if sub else ""))
    elif name in ("apt", "apt-get", "aptitude", "brew", "dnf", "yum", "apk", "pacman", "zypper", "port",
                  "snap", "choco", "winget", "scoop"):
        no("`%s` is a system package manager; read-only roles may not run it." % name)
    elif name == "composer":
        if sub in ("require", "install", "update", "remove"):
            no("`composer %s` installs or changes packages; read-only roles may not." % sub)
    elif name in ("mvn", "mvnw", "./mvnw"):
        if "deploy" in args:
            no("`mvn deploy` publishes artifacts; read-only roles may not.")
    elif name in ("gradle", "gradlew"):
        if any(a.startswith("publish") for a in args):
            no("`gradle publish` publishes artifacts; read-only roles may not.")
    elif name == "twine" and sub == "upload":
        no("`twine upload` publishes packages; read-only roles may not.")


def check_git(ctx, gc, goldfish):
    sub, args = gc.sub, gc.args
    if sub is None:
        return
    if any(a.startswith("--output") for a in args):
        no("`git %s --output` writes a file; read-only roles may not." % sub)
    if goldfish:
        if sub not in GOLDFISH_GIT:
            no("shipyard:goldfish may run only `git log`, `git show`, `git diff` and `git ls-files`, not "
               "`git %s`." % sub)
        return
    if sub in GIT_READ_ONLY:
        return
    if sub == "branch" and lib.branch_is_read_only(args):
        return
    if sub == "tag":
        flags = set(a.split("=", 1)[0] for a in args if a.startswith("-"))
        mutating = {"-a", "-s", "-u", "-f", "-d", "-m", "-F", "--delete", "--annotate", "--sign", "--force",
                    "--message", "--file", "-e", "--edit"}
        positional = [a for a in args if not a.startswith("-")]
        if not (flags & mutating) and (not positional or flags & {"-l", "--list", "--contains", "--points-at",
                                                                  "--merged", "--no-merged"}):
            return
    if sub == "stash" and args[:1] in (["list"], ["show"]):
        return
    if sub == "config" and any(a in ("--get", "--get-all", "--get-regexp", "--list", "-l", "--get-urlmatch")
                               for a in args):
        return
    if sub == "remote" and (not args or args[0] in ("-v", "--verbose", "get-url")):
        return
    if sub == "reflog" and (not args or args[0] == "show" or args[0].startswith("-")):
        return
    if sub == "symbolic-ref" and len([a for a in args if not a.startswith("-")]) <= 1:
        return
    if sub == "worktree" and args[:1] == ["list"]:
        return
    if sub == "notes" and args[:1] in (["list"], ["show"]):
        return
    no("`git %s` changes repository state (or is not on the read-only list). Read-only roles may run git log, "
       "diff, show, status, rev-parse, ls-files, blame and similar read-only commands." % sub)


def check_curl(ctx, args, goldfish):
    i = 0
    while i < len(args):
        a = args[i]
        nxt = args[i + 1] if i + 1 < len(args) else None
        if a.startswith("--"):
            key = a.split("=", 1)[0]
            val = a.split("=", 1)[1] if "=" in a else nxt
            if key == "--request" and (val or "").upper() in ("POST", "PUT", "PATCH", "DELETE"):
                no("`curl --request %s` changes remote state; read-only roles may not." % val)
            if key.startswith("--data") or key in ("--json", "--form", "--form-string", "--upload-file"):
                no("`curl %s` sends data; read-only roles may not." % key)
            if key == "--output" and not path_ok(ctx, val, goldfish):
                no("`curl --output %s` writes outside .ai/." % val)
            if key in ("--remote-name", "--remote-name-all"):
                no("`curl %s` saves a file outside .ai/." % key)
            if key in ("--request", "--output") and "=" not in a:
                i += 1
            i += 1
            continue
        if a.startswith("-") and len(a) > 1:
            letters = a[1:]
            for k, ch in enumerate(letters):
                if ch in "dFT":
                    no("`curl -%s` sends data or uploads; read-only roles may not." % ch)
                if ch == "X":
                    val = letters[k + 1:] or nxt
                    if (val or "").upper() in ("POST", "PUT", "PATCH", "DELETE"):
                        no("`curl -X %s` changes remote state; read-only roles may not." % val)
                    if not letters[k + 1:]:
                        i += 1
                    break
                if ch == "O":
                    no("`curl -O` saves a file outside .ai/.")
                if ch == "o":
                    val = letters[k + 1:] or nxt
                    if not path_ok(ctx, val, goldfish):
                        no("`curl -o %s` writes outside .ai/." % val)
                    if not letters[k + 1:]:
                        i += 1
                    break
                if ch in "HuAebcKwmrxEYyzCUQtJ":
                    if not letters[k + 1:]:
                        i += 1
                    break
        i += 1


def check_wget(ctx, args, goldfish):
    out = None
    spider = False
    i = 0
    while i < len(args):
        a = args[i]
        nxt = args[i + 1] if i + 1 < len(args) else None
        key = a.split("=", 1)[0]
        val = a.split("=", 1)[1] if "=" in a else nxt
        if key in ("--post-data", "--post-file", "--body-data", "--body-file"):
            no("`wget %s` sends data; read-only roles may not." % key)
        if key == "--method" and (val or "").upper() not in ("GET", "HEAD"):
            no("`wget --method %s` changes remote state; read-only roles may not." % val)
        if key == "--spider":
            spider = True
        if key in ("-O", "--output-document"):
            out = val
            i += 1 if "=" in a else 2
            continue
        if a.startswith("-") and not a.startswith("--") and "O" in a[1:]:
            letters = a[1:]
            rest = letters[letters.index("O") + 1:]
            out = rest if rest else nxt
            i += 1 if rest else 2
            continue
        if key in ("-o", "--output-file", "-a", "--append-output") and not path_ok(ctx, val, goldfish):
            no("`wget %s %s` writes a log outside .ai/." % (key, val))
        i += 1
    if spider:
        return
    if out is None:
        no("`wget` without `-O -` saves a file in the working directory; use `-O -`, `-O /dev/null` or "
           "`--spider`.")
    if not path_ok(ctx, out, goldfish):
        no("`wget -O %s` writes outside .ai/." % out)


def check_command(ctx, sc, wrappers, goldfish):
    check_redirects(ctx, sc, goldfish)
    if PRIV & set(wrappers):
        no("`sudo`/`doas` is not allowed for read-only roles.")
    if not sc.argv:
        return
    name = sc.name
    args = sc.argv[1:]
    if name in PRIV:
        no("`%s` is not allowed for read-only roles." % name)
    if goldfish and name not in GOLDFISH_COMMANDS:
        no("shipyard:goldfish may run only read-only inspection commands (ls, cat, grep, rg, find, git "
           "log/show/diff/ls-files, wc, head, tail), not `%s`." % name)
    if name in DESTRUCTIVE:
        no("`%s` changes or deletes files; read-only roles may not run it." % name)
    if name in ("sed", "perl", "ruby") and any(a == "-i" or a.startswith("-i") or a.startswith("--in-place")
                                               for a in args):
        no("`%s -i` edits files in place; read-only roles may not." % name)
    if name == "find":
        for a in args:
            if a in ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"):
                no("`find %s` can change or write files; read-only roles may not use it." % a)
    if name == "rg" and any(a == "--pre" or a.startswith("--pre=") for a in args):
        no("`rg --pre` runs another program; not allowed for read-only roles.")
    if name == "tee":
        for a in args:
            if not a.startswith("-") and not path_ok(ctx, a, goldfish):
                no("`tee %s` writes outside .ai/. Read-only roles may write only into .ai/." % a)
    if name in ("cp", "touch", "mkdir", "install", "rsync"):
        paths = [a for a in args if not a.startswith("-")]
        targets = paths[-1:] if name in ("cp", "install", "rsync") else paths
        for t in targets:
            if not path_ok(ctx, t, goldfish):
                no("`%s` would write '%s' outside .ai/. Read-only roles may write only into .ai/." % (name, t))
    if name == "curl":
        check_curl(ctx, args, goldfish)
    if name == "wget":
        check_wget(ctx, args, goldfish)
    check_packages(name, args)


def main(ctx):
    if ctx.agent not in READONLY_ROLES:
        return
    if ctx.tool_name and ctx.tool_name != "Bash":
        return
    cmd = ctx.tool_input.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return
    goldfish = ctx.agent == "goldfish"
    cmds = lib.parse_commands(cmd)
    try:
        for sc, wrappers in cmds:
            check_command(ctx, sc, wrappers, goldfish)
        for gc, _workdir in lib.git_calls(cmds, ctx.cwd):
            check_git(ctx, gc, goldfish)
    except Denied as d:
        ctx.deny("shipyard:%s runs read-only commands only: %s" % (ctx.agent, d))


if __name__ == "__main__":
    lib.run(HOOK, main)

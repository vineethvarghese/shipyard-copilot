#!/usr/bin/env python3
"""protect-branches (PreToolUse, Bash): keep Shipyard agents off protected branches and away from history
rewrites. Never push; merge only by the coordinator, --no-ff, slice branch into feature branch."""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shipyard_hooklib as lib  # noqa: E402

HOOK = "protect-branches"
COORDINATOR = "coordinator"
AUTHORS = ("implementer", "verifier")

PUSH_LIKE = {"push", "send-pack", "http-push"}
HISTORY_REWRITE = {"rebase", "cherry-pick", "am", "filter-branch", "filter-repo", "update-ref", "replace"}
# Subcommands that change a branch or the working tree of whatever folder they run in. After a `cd` on the
# same command line the hook cannot be sure which folder that is, so these must run from the session folder
# (or name their folder with `git -C <dir>`, which the hook does resolve).
DIR_SENSITIVE = {"commit", "merge", "revert", "reset", "checkout", "switch", "branch", "worktree", "fetch",
                 "stash", "restore", "rm", "mv", "tag", "notes", "symbolic-ref"}
MERGE_VALUE_OPTS = {"-m", "-F", "-s", "-X", "--message", "--file", "--strategy", "--strategy-option",
                    "--into-name", "--cleanup"}


class Sim(object):
    """Tracks a branch switch earlier in the same command line (e.g. `git checkout x && git commit`)."""

    def __init__(self):
        self.branch = None


def branch_now(ctx, workdir, sim):
    if sim.branch:
        return sim.branch
    return lib.current_branch(workdir)


def check_branch_cmd(ctx, gc, workdir, state, protected, sim):
    args = gc.args
    if lib.branch_is_read_only(args):
        return
    if ctx.agent != COORDINATOR:
        ctx.deny("`git branch %s`: only shipyard:coordinator creates, deletes, renames or moves branches. "
                 "Read-only listing (`git branch`, `git branch --list`) is allowed." % " ".join(args))
    flags = lib.branch_flags(args)
    pos = [lib.strip_ref(p) for p in lib.branch_positionals(args)]
    feature = (state or {}).get("featureBranch")
    notes = (state or {}).get("notesBranch")
    guarded = lambda b: b and (lib.is_protected(b, protected) or b in (feature, notes))  # noqa: E731
    if flags & {"-d", "-D", "--delete"}:
        for b in pos:
            if guarded(b):
                ctx.deny("`git branch` delete of '%s': the feature branch and protected branches are never "
                         "deleted." % b)
    if flags & {"-m", "-M", "--move", "-c", "-C", "--copy"}:
        targets = list(pos)
        if len(pos) < 2:
            targets.append(branch_now(ctx, workdir, sim))
        for b in targets:
            if guarded(b):
                ctx.deny("`git branch` rename/copy involving '%s': the feature branch and protected branches "
                         "are never renamed, copied over or replaced." % b)
    if flags & {"-f", "--force"}:
        for b in pos[:1]:
            if guarded(b):
                ctx.deny("`git branch --force %s` would move a protected or feature branch." % b)
    if not flags & {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy"}:
        for b in pos[:1]:
            if lib.is_protected(b, protected):
                ctx.deny("refusing to create or reset a branch named '%s' (protected)." % b)


def checkout_targets(sub, args):
    """Return (new_branch, force_create, switch_target)."""
    create_flags = {"checkout": {"-b"}, "switch": {"-c", "--create"}}[sub]
    force_flags = {"checkout": {"-B"}, "switch": {"-C", "--force-create"}}[sub]
    value_flags = {"--orphan", "--conflict", "--pathspec-from-file"} | create_flags | force_flags
    new_branch, force, positional = None, False, []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            break
        key = a.split("=", 1)[0]
        if key in create_flags or key in force_flags or key == "--orphan":
            val = a.split("=", 1)[1] if "=" in a else (args[i + 1] if i + 1 < len(args) else None)
            new_branch = val
            force = force or key in force_flags
            i += 1 if "=" in a else 2
            continue
        if re.match(r"^-[A-Za-z]+$", a) and len(a) > 2:
            letters = a[1:]
            hit = [ch for ch in letters if ("-" + ch) in (create_flags | force_flags)]
            if hit:
                new_branch = args[i + 1] if i + 1 < len(args) else None
                force = force or any(("-" + ch) in force_flags for ch in hit)
                i += 2
                continue
        if key in value_flags:
            i += 1 if "=" in a else 2
            continue
        if not a.startswith("-"):
            positional.append(a)
        i += 1
    return new_branch, force, (positional[0] if positional else None)


def check_checkout(ctx, gc, workdir, state, protected, sim):
    if ctx.agent != COORDINATOR:
        ctx.deny("`git %s`: only shipyard:coordinator switches or creates branches. Stay on the branch you were "
                 "started on (use `git restore` to discard a file change)." % gc.sub)
    new_branch, force, target = checkout_targets(gc.sub, gc.args)
    feature = (state or {}).get("featureBranch")
    notes = (state or {}).get("notesBranch")
    for b in (new_branch, target):
        if b and notes and lib.strip_ref(b) == notes:
            ctx.deny("`git %s %s`: '%s' is Shipyard's notes branch. It holds only .ai/ snapshots and is never "
                     "checked out or reset; `shipyard_state.py snapshot` writes it." % (gc.sub, b, notes))
    if new_branch:
        nb = lib.strip_ref(new_branch)
        if lib.is_protected(nb, protected):
            ctx.deny("`git %s %s %s`: refusing to create or reset protected branch '%s'."
                     % (gc.sub, "-B" if gc.sub == "checkout" else "-C", nb, nb))
        if force and nb == feature:
            ctx.deny("`git %s` force-create would reset the feature branch '%s'." % (gc.sub, nb))
        sim.branch = nb
    elif target and lib.branch_exists(lib.strip_ref(target), workdir):
        sim.branch = lib.strip_ref(target)


def check_commit(ctx, gc, workdir, state, state_err, protected, sim):
    branch = branch_now(ctx, workdir, sim)
    if branch is None:
        ctx.deny("`git commit`: could not determine the current branch.")
    if lib.is_protected(branch, protected):
        ctx.deny("`git commit` on protected branch '%s'. Shipyard never commits on main, master, the default "
                 "branch or state.json protectedBranches." % branch)
    if ctx.agent in AUTHORS:
        if state is None:
            ctx.deny("`git commit`: %s, so the slice branch cannot be checked." % state_err)
        slice_branch = state.get("sliceBranch")
        if not slice_branch or branch != slice_branch:
            ctx.deny("`git commit` on '%s': shipyard:%s may commit only on %s." % (
                branch, ctx.agent, "'%s'" % slice_branch if slice_branch else
                "the active slice branch (state.json sliceBranch is not set)"))
        return
    ctx.deny("`git commit`: shipyard:%s may not commit. Only the implementer and the verifier commit, on the slice "
             "branch; the coordinator only merges, and `.ai/` reaches git only through `shipyard_state.py "
             "snapshot` (the notes branch)." % ctx.agent)


def check_add(ctx, gc, workdir):
    """`.ai/` never enters a work branch (snapshots go to the notes branch): no forced adds, no `.ai` pathspecs."""
    for a in gc.args:
        if a in ("-f", "--force") or (a.startswith("-") and not a.startswith("--") and "f" in a[1:]):
            ctx.deny("`git add %s` forces ignored files in; `.ai/` and other ignored files stay out of commits."
                     % a)
        if not a.startswith("-"):
            spec = a[2:] if a.startswith(":/") else a
            base = ctx.project if a.startswith(":/") else workdir
            rel = lib.normalize_path(ctx.project, spec, base)
            if lib.under_ai(rel):
                ctx.deny("`git add %s`: `.ai/` never enters a work branch; `shipyard_state.py snapshot` commits it to "
                         "the notes branch." % a)


def merge_sources(args):
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a in MERGE_VALUE_OPTS:
            i += 2
            continue
        if not a.startswith("-"):
            out.append(a)
        i += 1
    return out


def check_merge(ctx, gc, workdir, state, state_err, protected, sim):
    args = gc.args
    if ctx.agent != COORDINATOR:
        ctx.deny("`git merge`: only shipyard:coordinator merges (an approved slice into the feature branch).")
    if args == ["--abort"] or (args and args[0] == "--abort"):
        return
    branch = branch_now(ctx, workdir, sim)
    if lib.is_protected(branch, protected):
        ctx.deny("`git merge` while on protected branch '%s'. Merges land on the feature branch only; the human "
                 "raises the pull request to the base branch." % branch)
    if state is None:
        ctx.deny("`git merge`: %s, so the feature and slice branches cannot be checked." % state_err)
    feature = state.get("featureBranch")
    if not feature or branch != feature:
        ctx.deny("`git merge` on '%s': merge only while the feature branch '%s' is checked out." % (branch, feature))
    flags = set(a.split("=", 1)[0] for a in args if a.startswith("-"))
    for bad in ("--continue", "--quit", "--squash", "--ff-only", "--ff"):
        if bad in flags:
            ctx.deny("`git merge %s` is not allowed; use `git merge --no-ff <slice-branch> -m \"Merge slice <id>: "
                     "<title>\"` or `git merge --abort`." % bad)
    if "--no-ff" not in flags:
        ctx.deny("`git merge` must use --no-ff: `git merge --no-ff <slice-branch> -m \"Merge slice <id>: <title>\"`.")
    sources = [lib.strip_ref(s) for s in merge_sources(args)]
    pattern = re.compile("^" + re.escape(feature) + r"-slice-.+$")
    slice_branch = state.get("sliceBranch")
    if len(sources) != 1:
        ctx.deny("`git merge` must name exactly one slice branch (got %d)." % len(sources))
    src = sources[0]
    if not (src == slice_branch or pattern.match(src)):
        ctx.deny("`git merge %s`: only the slice branch ('%s' or '%s-slice-*') may be merged into the feature "
                 "branch." % (src, slice_branch, feature))


def check_git(ctx, gc, workdir, state, state_err, protected, sim):
    sub = gc.sub
    if sub is None:
        return
    args = gc.args
    if sub in PUSH_LIKE:
        ctx.deny("`git %s` is never allowed for Shipyard agents. The human pushes the feature branch and raises "
                 "the pull request." % sub)
    if sub in HISTORY_REWRITE:
        ctx.deny("`git %s` rewrites or replays history and is not allowed for Shipyard agents." % sub)
    if sub == "reset" and any(a == "--hard" or a.startswith("--hard=") for a in args):
        ctx.deny("`git reset --hard` discards work and is not allowed for Shipyard agents.")
    if sub == "reset" and not ("--" in args or any(a in ("-p", "--patch") for a in args)):
        branch = branch_now(ctx, workdir, sim)
        if lib.is_protected(branch, protected):
            ctx.deny("`git reset` while on protected branch '%s' would move it." % branch)
    if sub == "revert":
        check_revert(ctx, gc, workdir, state, state_err, protected, sim)
    if sub == "fetch":
        check_fetch(ctx, gc, state, protected)
    if sub == "symbolic-ref" and len([a for a in args if not a.startswith("-")]) >= 2:
        ctx.deny("`git symbolic-ref <name> <ref>` repoints a ref and is not allowed for Shipyard agents.")
    if sub == "pull":
        ctx.deny("`git pull` merges or rebases remote work and is not allowed for Shipyard agents.")
    if sub == "branch":
        check_branch_cmd(ctx, gc, workdir, state, protected, sim)
    elif sub in ("checkout", "switch"):
        check_checkout(ctx, gc, workdir, state, protected, sim)
    elif sub == "commit":
        check_commit(ctx, gc, workdir, state, state_err, protected, sim)
    elif sub in ("add", "stage"):
        check_add(ctx, gc, workdir)
    elif sub == "merge":
        check_merge(ctx, gc, workdir, state, state_err, protected, sim)
    elif sub == "worktree" and args and args[0] in ("add", "move", "remove", "prune", "repair"):
        if ctx.agent != COORDINATOR:
            ctx.deny("`git worktree %s`: only shipyard:coordinator manages branches and worktrees." % args[0])
        if args[0] == "add":
            notes = (state or {}).get("notesBranch")
            check_worktree_add(ctx, args[1:], list(protected) + ([notes] if notes else []))


def check_revert(ctx, gc, workdir, state, state_err, protected, sim):
    """`git revert` adds a new commit (it does not rewrite history). Only the coordinator uses it, and only
    on the feature branch, to back out a slice merge whose post-merge checks failed."""
    if ctx.agent != COORDINATOR:
        ctx.deny("`git revert`: only shipyard:coordinator reverts, and only a slice merge on the feature branch.")
    if gc.args[:1] in (["--abort"], ["--quit"], ["--skip"]):
        return
    branch = branch_now(ctx, workdir, sim)
    if lib.is_protected(branch, protected):
        ctx.deny("`git revert` on protected branch '%s'." % branch)
    if state is None:
        ctx.deny("`git revert`: %s, so the feature branch cannot be checked." % state_err)
    if branch != state.get("featureBranch"):
        ctx.deny("`git revert` on '%s': revert only on the feature branch '%s'." % (branch,
                                                                                   state.get("featureBranch")))


def refspec_dst(spec):
    spec = spec.lstrip("+")
    if ":" not in spec:
        return None
    return spec.split(":", 1)[1]


def check_fetch(ctx, gc, state, protected):
    """Plain `git fetch [remote]` only updates remote-tracking refs. A refspec with a destination
    (`src:dst`) writes a local ref, which could move a protected branch; Shipyard never does that."""
    for a in gc.args:
        if a.startswith("-"):
            if a.split("=", 1)[0] in ("--update-head-ok", "-u", "--refmap"):
                ctx.deny("`git fetch %s` can update local branches; Shipyard agents may not use it." % a)
            continue
        dst = refspec_dst(a)
        if dst is None:
            continue
        name = lib.strip_ref(dst)
        if dst.startswith("refs/remotes/") or dst.startswith("refs/tags/"):
            continue
        ctx.deny("`git fetch ... %s` writes the local ref '%s'. Shipyard agents fetch into remote-tracking "
                 "refs only (plain `git fetch` or `git fetch <remote>`)." % (a, name))


def check_worktree_add(ctx, rest, protected):
    """`git worktree add <path> [<branch>]` and `-b/-B <branch>`: never on a protected branch."""
    i, pos = 0, []
    while i < len(rest):
        a = rest[i]
        if a in ("-b", "-B", "--orphan"):
            nb = rest[i + 1] if i + 1 < len(rest) else ""
            if lib.is_protected(lib.strip_ref(nb), protected):
                ctx.deny("`git worktree add %s %s`: refusing to create or reset protected branch '%s'."
                         % (a, nb, nb))
            i += 2
            continue
        if a.startswith("-"):
            if a == "--reason":
                i += 1
            i += 1
            continue
        pos.append(a)
        i += 1
    for b in pos[1:2]:
        if lib.is_protected(lib.strip_ref(b), protected):
            ctx.deny("`git worktree add ... %s`: a worktree on protected branch '%s' would let later commands "
                     "commit or merge there. Shipyard works on the feature and slice branches only." % (b, b))


def check_gh(ctx, argv):
    pos, i = [], 1
    while i < len(argv):
        a = argv[i]
        if a in ("-R", "--repo"):
            i += 2
            continue
        if not a.startswith("-"):
            pos.append(a)
        i += 1
    if pos[:2] == ["pr", "merge"]:
        ctx.deny("`gh pr merge` is not allowed for Shipyard agents; the human merges pull requests.")
    if pos[:2] in (["pr", "create"], ["repo", "sync"]):
        ctx.deny("`gh %s %s` pushes to the remote and is not allowed for Shipyard agents." % (pos[0], pos[1]))


def main(ctx):
    if ctx.tool_name and ctx.tool_name != "Bash":
        return
    cmd = ctx.tool_input.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return
    cmds = lib.parse_commands(cmd)
    has_git = any(sc.argv and sc.name == "git" for sc, _ in cmds)
    for sc, _w in cmds:
        if sc.argv and sc.name == "gh":
            check_gh(ctx, sc.argv)
    if not has_git:
        return
    state, state_err = ctx.state()
    protected = lib.protected_patterns(state, ctx.cwd)
    sim = Sim()
    moved = [False]
    if re.search(r"(--git-dir|--work-tree|\bGIT_DIR\b|\bGIT_WORK_TREE\b|\bGIT_INDEX_FILE\b)", cmd):
        moved[0] = True  # the repository or worktree is redirected: the hook cannot tell which branch is hit

    def saw_shell(parsed):
        if any(p.argv and p.name in lib.CD_COMMANDS for p, _ in parsed):
            moved[0] = True

    for sc, w in cmds:
        if sc.argv and sc.name in lib.CD_COMMANDS:
            moved[0] = True
            continue
        if not (sc.argv and sc.name == "git"):
            continue
        for gc, workdir in lib.git_calls([(sc, w)], ctx.cwd, on_shell=saw_shell):
            ctx.debug("git %s %r in %s" % (gc.sub, gc.args, workdir))
            if moved[0] and gc.sub in DIR_SENSITIVE:
                ctx.deny("`git %s` after a `cd`, or with --git-dir/--work-tree/GIT_DIR, on the same command line: "
                         "the hook checks branches in the folder the command runs in and cannot follow those. Run "
                         "it as its own command from the project, or use `git -C <dir> %s ...`." % (gc.sub, gc.sub))
            check_git(ctx, gc, workdir, state, state_err, protected, sim)


if __name__ == "__main__":
    lib.run(HOOK, main)

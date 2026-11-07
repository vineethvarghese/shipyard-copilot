#!/usr/bin/env python3
"""Read and write `.ai/state.json` in the target repository.

Stdlib only. The coordinator is the only writer of state.json; it uses this
script so every write is validated against contracts/state.schema.json and
written atomically.

Usage (run from inside the target repo, or pass --repo PATH):
    shipyard_state.py init --project NAME --feature-branch F --base-branch B
                           [--protected a,b] [--breadth 0|1|2]
                           [--formal-rigour none|invariants|properties|model-checked] [--force]
    shipyard_state.py show [--get KEY]
    shipyard_state.py set-status STATUS
    shipyard_state.py set-slice ID|none [--slice-branch NAME]
    shipyard_state.py set-active-role ROLE|none
    shipyard_state.py gate P0|P4|P8|MERGE approve --by LOGIN [--slice ID]
    shipyard_state.py ignore-ai
    shipyard_state.py snapshot -m MESSAGE
    shipyard_state.py restore --from BRANCH

`.ai/` never enters the feature, slice or base branches. `ignore-ai` (also run by `init`) adds `/.ai/` to the
repository's local exclude file (`.git/info/exclude`: a gitignore that lives only on this machine, so the
project's own files are not changed) and checks that git now ignores `.ai/` and tracks nothing in it.

`snapshot` commits the current `.ai/` folder to the notes branch (`state.json` → `notesBranch`, default
`<featureBranch>-shipyard`) with git plumbing: a private index, `write-tree`, `commit-tree` and a checked
`update-ref`. It never checks anything out and never touches the working tree, the index or the current branch.
The notes branch holds only `.ai/`; it is never checked out or merged. `restore` writes `.ai/` back from a notes
branch into a fresh clone, so a project can resume on another machine.

`set-active-role` records which Shipyard role the coordinator is about to delegate to (`activeRole`). Under
GitHub Copilot the hooks read it when neither `SHIPYARD_ROLE` nor the hook payload names the role. `none` clears
it. `gate <P0|P4|P8|MERGE> approve --by <login>` appends `{gate, by, at, slice}` to `gates`; `at` is the ISO 8601
committer date of HEAD (`git log -1 --format=%cI`) when the repository has a commit, else the current UTC time.

Exit codes: 0 ok, 1 refused or invalid, 2 usage error.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shipyard_validate import load_contract, validate  # noqa: E402

SCHEMA_VERSION = "1.0"
DEFAULT_PROTECTED = ["main", "master"]
ROLES = ["coordinator", "discovery", "goldfish", "architect", "planner", "implementer", "verifier",
         "code-reviewer", "security-reviewer", "contract-reviewer", "integration-reviewer",
         "reliability-reviewer", "simplicity-reviewer"]
GATES = ["P0", "P4", "P8", "MERGE"]


class Refused(Exception):
    """A request the state rules do not allow."""


def _git(repo, *args):
    try:
        proc = subprocess.run(["git"] + list(args), cwd=repo, capture_output=True, text=True)
    except FileNotFoundError:
        raise Refused("git is not installed or not on PATH")
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def find_repo(explicit):
    if explicit:
        if not os.path.isdir(explicit):
            raise Refused("--repo %s is not a directory" % explicit)
        return os.path.abspath(explicit)
    try:
        code, out, _ = _git(os.getcwd(), "rev-parse", "--show-toplevel")
    except Refused:
        code, out = 1, ""
    return out if code == 0 and out else os.getcwd()


def state_path(repo):
    return os.path.join(repo, ".ai", "state.json")


def default_branch(repo):
    """The remote's default branch if git knows it, else None."""
    code, out, _ = _git(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if code == 0 and "/" in out:
        return out.split("/", 1)[1]
    return None


def check_branch_name(repo, name, what):
    if not name or not name.strip():
        raise Refused("%s is empty" % what)
    code, _, err = _git(repo, "check-ref-format", "--branch", name)
    if code != 0:
        raise Refused("%s %r is not a valid branch name (git check-ref-format --branch): %s" % (what, name, err))


def check_not_protected(name, protected, what):
    if name in protected:
        raise Refused("%s %r is protected (%s); Shipyard never works on a protected branch"
                      % (what, name, ", ".join(protected)))


def load_state(repo):
    path = state_path(repo)
    if not os.path.isfile(path):
        raise Refused("no state at %s; run `init` first" % path)
    with open(path, encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except ValueError as exc:
            raise Refused("%s does not parse: %s" % (path, exc))


def write_state(repo, state):
    errors = validate(state, load_contract("state"))
    if errors:
        raise Refused("refusing to write an invalid state.json:\n  " + "\n  ".join(errors))
    path = state_path(repo)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".state.", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


EXCLUDE_LINE = "/.ai/"
EXCLUDE_COMMENT = "# Shipyard: .ai/ stays off the work branches (snapshots go to the notes branch)"


def exclude_path(repo):
    code, out, err = _git(repo, "rev-parse", "--git-path", "info/exclude")
    if code != 0 or not out:
        raise Refused("not a git repository (%s); Shipyard works inside a git repository" % (err or repo))
    return out if os.path.isabs(out) else os.path.join(repo, out)


def ignore_ai(repo):
    """Make git ignore .ai/ locally. Returns a list of notes; raises Refused when .ai/ is still visible to git."""
    notes = []
    path = exclude_path(repo)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = [l.strip() for l in fh.read().splitlines()]
    except FileNotFoundError:
        lines = []
    if EXCLUDE_LINE not in lines and ".ai/" not in lines and "/.ai" not in lines:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            if lines and lines[-1] != "":
                fh.write("\n")
            fh.write("%s\n%s\n" % (EXCLUDE_COMMENT, EXCLUDE_LINE))
        notes.append("added %s to %s" % (EXCLUDE_LINE, path))
    else:
        notes.append("%s already excludes .ai/" % path)
    code, out, _ = _git(repo, "ls-files", "--", ".ai")
    if code == 0 and out:
        n = len(out.splitlines())
        raise Refused("%d file(s) under .ai/ are already tracked by git, so ignoring cannot keep them out of your "
                      "commits. Ask the human: `git rm -r --cached .ai` (their decision; it changes their repo) "
                      "before Shipyard continues" % n)
    code, _, _ = _git(repo, "check-ignore", "-q", "--no-index", ".ai/state.json")
    if code != 0:
        raise Refused("git does not ignore .ai/ even after the local exclude (a .gitignore rule such as `!.ai/` "
                      "may re-include it); ask the human to remove that rule")
    return notes


def cmd_ignore_ai(repo, args):
    for note in ignore_ai(repo):
        print(note)
    print(".ai/ is ignored locally and nothing in it is tracked")
    return 0


def notes_branch_for(repo, state, override=None):
    name = override or state.get("notesBranch") or "%s-shipyard" % state.get("featureBranch", "")
    check_branch_name(repo, name, "notes branch")
    protected = list(state.get("protectedBranches", [])) + DEFAULT_PROTECTED + [state.get("baseBranch")]
    check_not_protected(name, [p for p in protected if p], "notes branch")
    if name in (state.get("featureBranch"), state.get("sliceBranch")):
        raise Refused("notes branch %r must differ from the feature and slice branches" % name)
    return name


def _rev(repo, ref):
    code, out, _ = _git(repo, "rev-parse", "--verify", "--quiet", ref)
    return out if code == 0 and out else None


def _git_env(repo, env, *args):
    try:
        proc = subprocess.run(["git"] + list(args), cwd=repo, capture_output=True, text=True, env=env)
    except FileNotFoundError:
        raise Refused("git is not installed or not on PATH")
    if proc.returncode != 0:
        raise Refused("git %s failed: %s" % (" ".join(args[:2]), proc.stderr.strip()))
    return proc.stdout.strip()


def snapshot(repo, message):
    """Commit .ai/ to the notes branch without touching the working tree, the index or HEAD. Returns
    (branch, sha or None when nothing changed)."""
    state = load_state(repo)
    branch = notes_branch_for(repo, state)
    ref = "refs/heads/" + branch
    parent = _rev(repo, ref)
    if parent:
        code, out, _ = _git(repo, "ls-tree", "--name-only", parent)
        if code != 0 or [l for l in out.splitlines() if l != ".ai"]:
            raise Refused("branch %r exists and holds more than .ai/; it is not a Shipyard notes branch. Choose "
                          "another name (state.json notesBranch)" % branch)
    code, idx, _ = _git(repo, "rev-parse", "--git-path", "shipyard-snapshot.index")
    if code != 0:
        raise Refused("not a git repository")
    idx = idx if os.path.isabs(idx) else os.path.join(repo, idx)
    if os.path.exists(idx):
        os.unlink(idx)
    env = dict(os.environ, GIT_INDEX_FILE=idx)
    try:
        _git_env(repo, env, "add", "--force", "--", ".ai")
        tree = _git_env(repo, env, "write-tree")
    finally:
        if os.path.exists(idx):
            os.unlink(idx)
    if parent and _rev(repo, parent + "^{tree}") == tree:
        return branch, None
    if _git(repo, "config", "user.email")[0] != 0 or _git(repo, "config", "user.name")[0] != 0:
        env.setdefault("GIT_AUTHOR_NAME", "Shipyard")
        env.setdefault("GIT_AUTHOR_EMAIL", "shipyard@localhost")
        env.setdefault("GIT_COMMITTER_NAME", "Shipyard")
        env.setdefault("GIT_COMMITTER_EMAIL", "shipyard@localhost")
    env.pop("GIT_INDEX_FILE", None)
    cmd = ["commit-tree", tree, "-m", message] + (["-p", parent] if parent else [])
    sha = _git_env(repo, env, *cmd)
    _git_env(repo, env, "update-ref", "-m", "shipyard snapshot", ref, sha, parent or "0" * 40)
    if state.get("notesBranch") != branch:
        state["notesBranch"] = branch
        write_state(repo, state)
    return branch, sha


def cmd_snapshot(repo, args):
    branch, sha = snapshot(repo, args.message)
    if sha:
        print("snapshot %s on %s" % (sha[:12], branch))
    else:
        print("no change since the last snapshot on %s" % branch)
    return 0


def cmd_restore(repo, args):
    import io
    import tarfile
    if os.path.exists(os.path.join(repo, ".ai")):
        raise Refused(".ai/ already exists here; restore only into a clone without it (move it aside first)")
    if not _rev(repo, args.source):
        raise Refused("no branch or ref %r (fetch it first, e.g. `git fetch origin %s:%s`)"
                      % (args.source, args.source, args.source))
    ignore_ai(repo)
    try:
        proc = subprocess.run(["git", "archive", "--format=tar", args.source, ".ai"], cwd=repo, capture_output=True)
    except FileNotFoundError:
        raise Refused("git is not installed or not on PATH")
    if proc.returncode != 0:
        raise Refused("git archive failed: %s" % proc.stderr.decode("utf-8", "replace").strip())
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
        for m in tar.getmembers():
            if not (m.name == ".ai" or m.name.startswith(".ai/")) or ".." in m.name.split("/") or m.issym() or m.islnk():
                raise Refused("refusing to restore unexpected entry %r" % m.name)
        if hasattr(tarfile, "data_filter"):
            tar.extractall(repo, filter="data")
        else:  # Python < 3.12: entries were checked above
            tar.extractall(repo)
    print("restored .ai/ from %s; check `shipyard_state.py show`, then resume" % args.source)
    return 0


def cmd_init(repo, args):
    for note in ignore_ai(repo):
        print(note)
    if os.path.isfile(state_path(repo)) and not args.force:
        raise Refused("%s already exists; use `show`, or pass --force to overwrite" % state_path(repo))
    feature, base = args.feature_branch, args.base_branch
    check_branch_name(repo, base, "base branch")
    check_branch_name(repo, feature, "feature branch")
    protected = [p.strip() for p in args.protected.split(",")] if args.protected else list(DEFAULT_PROTECTED)
    protected = [p for p in protected if p]
    for extra in (base, default_branch(repo)):
        if extra and extra not in protected:
            protected.append(extra)
    if feature == base:
        raise Refused("feature branch %r equals the base branch; pick a new branch such as feature/<name>" % feature)
    check_not_protected(feature, protected + DEFAULT_PROTECTED, "feature branch")
    state = {
        "schemaVersion": SCHEMA_VERSION,
        "project": args.project,
        "status": "INTAKE",
        "featureBranch": feature,
        "baseBranch": base,
        "protectedBranches": protected,
        "activeSlice": None,
        "sliceBranch": None,
        "brainstormBreadth": args.breadth,
    }
    if args.formal_rigour and args.formal_rigour != "none":
        state["formalRigour"] = args.formal_rigour
    state["notesBranch"] = notes_branch_for(repo, state, args.notes_branch)
    print("wrote %s" % write_state(repo, state))
    return 0


def cmd_show(repo, args):
    state = load_state(repo)
    if args.get:
        if args.get not in state:
            raise Refused("state.json has no key %r" % args.get)
        value = state[args.get]
        print(value if isinstance(value, str) else json.dumps(value))
    else:
        print(json.dumps(state, indent=2))
    errors = validate(state, load_contract("state"))
    if errors:
        sys.stderr.write("warning: state.json does not match the contract:\n  " + "\n  ".join(errors) + "\n")
        return 1
    return 0


def cmd_set_status(repo, args):
    state = load_state(repo)
    state["status"] = args.status
    write_state(repo, state)
    print("status = %s" % args.status)
    return 0


def cmd_set_slice(repo, args):
    state = load_state(repo)
    if args.slice.lower() == "none":
        if args.slice_branch:
            raise Refused("--slice-branch makes no sense with `none`")
        state["activeSlice"] = None
        state["sliceBranch"] = None
    else:
        branch = args.slice_branch or "%s-slice-%s" % (state.get("featureBranch", ""), args.slice)
        check_branch_name(repo, branch, "slice branch")
        protected = list(state.get("protectedBranches", [])) + DEFAULT_PROTECTED + [state.get("baseBranch")]
        check_not_protected(branch, [p for p in protected if p], "slice branch")
        if branch == state.get("featureBranch"):
            raise Refused("slice branch must differ from the feature branch %r" % branch)
        state["activeSlice"] = args.slice
        state["sliceBranch"] = branch
    write_state(repo, state)
    print("activeSlice = %s, sliceBranch = %s" % (state["activeSlice"], state["sliceBranch"]))
    return 0


def normalize_role(value):
    """`shipyard:code-reviewer`, `shipyard-code-reviewer` or `code-reviewer` -> `code-reviewer`; None when unknown."""
    name = value.strip().lower().replace("_", "-")
    for prefix in ("shipyard:", "shipyard-"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name if name in ROLES else None


def cmd_set_active_role(repo, args):
    state = load_state(repo)
    if args.role.strip().lower() == "none":
        state.pop("activeRole", None)
        write_state(repo, state)
        print("activeRole cleared")
        return 0
    role = normalize_role(args.role)
    if role is None:
        raise Refused("%r is not a Shipyard role (one of: %s)" % (args.role, ", ".join(ROLES)))
    state["activeRole"] = role
    write_state(repo, state)
    print("activeRole = %s" % role)
    return 0


def gate_timestamp(repo):
    """ISO 8601 committer date of HEAD when there is a commit, else the current UTC time (seconds)."""
    code, out, _ = _git(repo, "log", "-1", "--format=%cI")
    if code == 0 and out:
        return out.splitlines()[0].strip()
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def cmd_gate(repo, args):
    if args.action != "approve":
        raise Refused("the only gate action is `approve`")
    by = (args.by or "").strip()
    if not by:
        raise Refused("--by LOGIN must not be empty")
    state = load_state(repo)
    entry = {"gate": args.gate, "by": by, "at": gate_timestamp(repo)}
    slice_id = (args.slice or "").strip() or None
    if args.gate == "MERGE" and not slice_id:
        slice_id = state.get("activeSlice")
        if not slice_id:
            raise Refused("a MERGE gate needs --slice ID (state.json has no activeSlice)")
    if slice_id:
        entry["slice"] = slice_id
    gates = state.get("gates")
    if not isinstance(gates, list):
        gates = []
    gates.append(entry)
    state["gates"] = gates
    write_state(repo, state)
    print("gate %s approved by %s at %s%s" % (args.gate, by, entry["at"],
                                              " (slice %s)" % slice_id if slice_id else ""))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="shipyard_state.py", description="Manage .ai/state.json")
    parser.add_argument("--repo", help="target repository (default: the git repo containing the current directory)")
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    p = sub.add_parser("init", help="create .ai/state.json")
    p.add_argument("--project", required=True)
    p.add_argument("--feature-branch", required=True)
    p.add_argument("--base-branch", required=True)
    p.add_argument("--protected", help="comma-separated protected branches (default: main,master)")
    p.add_argument("--breadth", type=int, choices=[0, 1, 2], default=1, help="brainstorm breadth (default 1)")
    p.add_argument("--formal-rigour", choices=["none", "invariants", "properties", "model-checked"], default="none",
                   help="C-10 formal rigour (default none)")
    p.add_argument("--force", action="store_true", help="overwrite an existing state.json")
    p.add_argument("--notes-branch", help="branch for .ai/ snapshots (default: <feature-branch>-shipyard)")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("snapshot", help="commit .ai/ to the notes branch without touching the working tree")
    p.add_argument("-m", "--message", required=True)
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("restore", help="write .ai/ back from a notes branch into a clone that has none")
    p.add_argument("--from", dest="source", required=True, metavar="BRANCH")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("ignore-ai", help="ignore .ai/ locally via .git/info/exclude and check nothing in it is tracked")
    p.set_defaults(func=cmd_ignore_ai)

    p = sub.add_parser("show", help="print state.json")
    p.add_argument("--get", metavar="KEY", help="print one key only")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("set-status", help="set the PROJECT status")
    p.add_argument("status")
    p.set_defaults(func=cmd_set_status)

    p = sub.add_parser("set-slice", help="set or clear the active slice")
    p.add_argument("slice", metavar="ID|none")
    p.add_argument("--slice-branch", help="default: <featureBranch>-slice-<ID>")
    p.set_defaults(func=cmd_set_slice)

    p = sub.add_parser("set-active-role", help="record the role the coordinator delegates to next (hooks read it)")
    p.add_argument("role", metavar="ROLE|none")
    p.set_defaults(func=cmd_set_active_role)

    p = sub.add_parser("gate", help="record a human gate approval")
    p.add_argument("gate", choices=GATES)
    p.add_argument("action", choices=["approve"])
    p.add_argument("--by", required=True, metavar="LOGIN", help="who approved (for example a GitHub login)")
    p.add_argument("--slice", metavar="ID", help="slice id (required for MERGE unless activeSlice is set)")
    p.set_defaults(func=cmd_gate)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        repo = find_repo(args.repo)
        return args.func(repo, args)
    except Refused as exc:
        sys.stderr.write("refused: %s\n" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())

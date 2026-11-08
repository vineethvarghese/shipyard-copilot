#!/usr/bin/env python3
"""Install, update, inspect or remove Shipyard's files in a project.

This is the "project install" of Shipyard for Copilot: the files land inside the target repository, where every
Copilot client (CLI, the coding agent, the IDEs) reads them. The alternative, `copilot plugin install`, reaches the
CLI only and needs nothing from this script.

    python3 shipyard/scripts/install.py init    [--target DIR] [--skip-github] [--skip GLOB]... [--force] [--dry-run]
    python3 shipyard/scripts/install.py update  [--target DIR] [--force] [--dry-run]
    python3 shipyard/scripts/install.py status  [--target DIR]
    python3 shipyard/scripts/install.py remove  [--target DIR] [--force] [--dry-run]

What it copies (relative to the source repository, which defaults to the repository this script lives in):

* core: `AGENTS.md`, `.github/copilot-instructions.md`, `.github/copilot/settings.json`, `.github/agents/`,
  `.github/skills/`, `.github/prompts/`, `.github/instructions/`, `.github/hooks/shipyard.json`,
  `.github/extensions/`, `shipyard/registry/`, `shipyard/contracts/`, `shipyard/scripts/` (this script included,
  so the uninstaller travels with the install).
* github (skipped with `--skip-github`): the Shipyard Actions (`copilot-setup-steps.yml`, `shipyard-*.yml`),
  `.github/rulesets/`, the intake issue form, the slice pull request template and `CODEOWNERS`.

Everything written is recorded with its SHA-256 in `shipyard/INSTALL.json`. `remove` deletes exactly those files
and only while they still match; a file you changed is kept and reported (or deleted with `--force`). `update`
replaces unchanged files, keeps changed ones (or replaces them with `--force`) and removes files the new source no
longer ships. Nothing under `.ai/` is ever touched. Exit code 0 on success, 1 on a refusal or an error.
"""

import argparse
import fnmatch
import hashlib
import io
import json
import os
import shutil
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SOURCE = os.path.normpath(os.path.join(HERE, "..", ".."))
MANIFEST = os.path.join("shipyard", "INSTALL.json")
MANIFEST_VERSION = 1

# (relative path, group). A path ending in "/" is a folder copied recursively; a glob is expanded in its folder.
COMPONENTS = (
    ("AGENTS.md", "core"),
    (".github/copilot-instructions.md", "core"),
    (".github/copilot/settings.json", "core"),
    (".github/agents/", "core"),
    (".github/skills/", "core"),
    (".github/prompts/", "core"),
    (".github/instructions/", "core"),
    (".github/hooks/shipyard.json", "core"),
    (".github/extensions/", "core"),
    ("shipyard/registry/", "core"),
    ("shipyard/contracts/", "core"),
    ("shipyard/scripts/", "core"),
    (".github/workflows/copilot-setup-steps.yml", "github"),
    (".github/workflows/shipyard-*.yml", "github"),
    (".github/rulesets/", "github"),
    (".github/ISSUE_TEMPLATE/shipyard-intake.yml", "github"),
    (".github/PULL_REQUEST_TEMPLATE/shipyard-slice.md", "github"),
    (".github/CODEOWNERS", "github"),
)
# Never copied even when inside a listed folder.
EXCLUDED_DIRS = {"__pycache__", "node_modules", ".git"}
EXCLUDED_SUFFIXES = (".pyc", ".DS_Store")
PROTECTED_PREFIX = ".ai" + os.sep


class InstallError(Exception):
    pass


# ---------------------------------------------------------------- helpers

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def to_posix(rel):
    return rel.replace(os.sep, "/")


def from_posix(rel):
    return rel.replace("/", os.sep)


def _walk(folder):
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        for name in sorted(filenames):
            if name.endswith(EXCLUDED_SUFFIXES):
                continue
            yield os.path.join(dirpath, name)


def source_files(source, skip_github=False, skips=()):
    """Sorted list of POSIX-relative paths this install ships from `source`."""
    out = []
    for spec, group in COMPONENTS:
        if group == "github" and skip_github:
            continue
        if spec.endswith("/"):
            folder = os.path.join(source, from_posix(spec.rstrip("/")))
            if not os.path.isdir(folder):
                continue
            for path in _walk(folder):
                out.append(to_posix(os.path.relpath(path, source)))
        elif any(ch in spec for ch in "*?["):
            folder = os.path.join(source, from_posix(os.path.dirname(spec)))
            if not os.path.isdir(folder):
                continue
            for name in sorted(os.listdir(folder)):
                if fnmatch.fnmatch(name, os.path.basename(spec)) and os.path.isfile(os.path.join(folder, name)):
                    out.append(to_posix(os.path.join(os.path.dirname(spec), name)))
        elif os.path.isfile(os.path.join(source, from_posix(spec))):
            out.append(spec)
    manifest_rel = to_posix(MANIFEST)
    files = [r for r in out if r != manifest_rel and not any(fnmatch.fnmatch(r, g) for g in skips)]
    return sorted(set(files))


def source_version(source):
    try:
        with io.open(os.path.join(source, "package.json"), encoding="utf-8") as fh:
            return str(json.load(fh).get("version") or "unknown")
    except (OSError, ValueError):
        return "unknown"


def read_manifest(target):
    path = os.path.join(target, MANIFEST)
    if not os.path.isfile(path):
        return None
    try:
        with io.open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise InstallError("%s is not readable JSON: %s" % (to_posix(MANIFEST), exc))
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        raise InstallError("%s has no 'files' map" % to_posix(MANIFEST))
    return data


def write_manifest(target, source, files):
    data = {
        "schemaVersion": MANIFEST_VERSION,
        "version": source_version(source),
        "source": os.path.abspath(source),
        "installedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "files": {rel: sha256_of(os.path.join(target, from_posix(rel))) for rel in sorted(files)},
    }
    path = os.path.join(target, MANIFEST)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return data


def _guard(target, rel):
    if from_posix(rel).startswith(PROTECTED_PREFIX) or rel.startswith(".ai/"):
        raise InstallError("refusing to touch %s: nothing under .ai/ is managed by the installer" % rel)
    path = os.path.normpath(os.path.join(target, from_posix(rel)))
    if not path.startswith(os.path.normpath(target) + os.sep):
        raise InstallError("refusing to touch %s: outside the target" % rel)
    return path


def _copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    shutil.copymode(src, dst)


def _prune_empty_dirs(target, rels):
    """Remove folders left empty by a deletion, up to (not including) the target."""
    target = os.path.normpath(target)
    for rel in sorted(rels, key=lambda r: -r.count("/")):
        d = os.path.dirname(os.path.normpath(os.path.join(target, from_posix(rel))))
        while d != target and d.startswith(target + os.sep):
            try:
                if os.listdir(d):
                    break
                os.rmdir(d)
            except OSError:
                break
            d = os.path.dirname(d)


def classify(target, manifest):
    """{rel: 'unchanged' | 'modified' | 'missing'} for every file the manifest records."""
    out = {}
    for rel, digest in manifest["files"].items():
        path = os.path.join(target, from_posix(rel))
        if not os.path.isfile(path):
            out[rel] = "missing"
        elif sha256_of(path) == digest:
            out[rel] = "unchanged"
        else:
            out[rel] = "modified"
    return out


# ---------------------------------------------------------------- commands

def cmd_init(args, out):
    source, target = args.source, args.target
    files = source_files(source, args.skip_github, args.skip)
    if not files:
        raise InstallError("nothing to install from %s (is it a shipyard-copilot checkout?)" % source)
    prior = read_manifest(target)
    if prior is not None and not args.force:
        raise InstallError("%s already exists: use `update`, or `init --force` to overwrite everything" % to_posix(MANIFEST))
    known = (prior or {}).get("files", {})
    conflicts = []
    for rel in files:
        dst = _guard(target, rel)
        if os.path.isfile(dst) and rel not in known and sha256_of(dst) != sha256_of(os.path.join(source, from_posix(rel))):
            conflicts.append(rel)
    if conflicts and not args.force:
        raise InstallError("these files already exist in the target and differ (nothing was written):\n  "
                           + "\n  ".join(conflicts)
                           + "\nRe-run with --force to overwrite them, or --skip '<glob>' to leave them alone.")
    for rel in files:
        if not args.dry_run:
            _copy(os.path.join(source, from_posix(rel)), _guard(target, rel))
        out.append(("write", rel))
    if not args.dry_run:
        write_manifest(target, source, files)
    out.append(("manifest", to_posix(MANIFEST)))
    return 0


def cmd_update(args, out):
    source, target = args.source, args.target
    manifest = read_manifest(target)
    if manifest is None:
        raise InstallError("%s not found: run `init` first" % to_posix(MANIFEST))
    state = classify(target, manifest)
    skip_github = not any(r.startswith(".github/workflows/") or r.startswith(".github/rulesets/") for r in manifest["files"])
    files = source_files(source, skip_github or args.skip_github, args.skip)
    kept = []
    for rel in files:
        dst = _guard(target, rel)
        src = os.path.join(source, from_posix(rel))
        status = state.get(rel)
        if status == "modified" and not args.force:
            kept.append(rel)
            out.append(("keep", rel))
            continue
        if status is None and os.path.isfile(dst) and sha256_of(dst) != sha256_of(src) and not args.force:
            kept.append(rel)
            out.append(("keep", rel))
            continue
        if not args.dry_run:
            _copy(src, dst)
        out.append(("write", rel))
    dropped = [rel for rel in manifest["files"] if rel not in files]
    removed = []
    for rel in dropped:
        if state.get(rel) == "unchanged" or (args.force and state.get(rel) == "modified"):
            if not args.dry_run:
                os.remove(_guard(target, rel))
            removed.append(rel)
            out.append(("remove", rel))
        elif state.get(rel) == "modified":
            kept.append(rel)
            out.append(("keep", rel))
    if not args.dry_run:
        _prune_empty_dirs(target, removed)
        recorded = [r for r in files if r not in kept] + [r for r in kept if os.path.isfile(os.path.join(target, from_posix(r)))]
        write_manifest(target, source, recorded)
    out.append(("manifest", to_posix(MANIFEST)))
    return 0


def cmd_status(args, out):
    manifest = read_manifest(args.target)
    if manifest is None:
        out.append(("not-installed", to_posix(MANIFEST)))
        return 1
    out.append(("version", str(manifest.get("version", "unknown"))))
    state = classify(args.target, manifest)
    for rel in sorted(state):
        out.append((state[rel], rel))
    return 0


def cmd_remove(args, out):
    target = args.target
    manifest = read_manifest(target)
    if manifest is None:
        raise InstallError("%s not found: nothing to remove" % to_posix(MANIFEST))
    state = classify(target, manifest)
    removed, kept = [], []
    for rel in sorted(state):
        path = _guard(target, rel)
        if state[rel] == "missing":
            out.append(("missing", rel))
        elif state[rel] == "unchanged" or args.force:
            if not args.dry_run:
                os.remove(path)
            removed.append(rel)
            out.append(("remove", rel))
        else:
            kept.append(rel)
            out.append(("keep", rel))
    if not args.dry_run:
        os.remove(os.path.join(target, MANIFEST))
        _prune_empty_dirs(target, removed + [to_posix(MANIFEST)])
    out.append(("remove", to_posix(MANIFEST)))
    if kept:
        out.append(("note", "%d changed file(s) kept; re-run with --force to delete them too" % len(kept)))
    return 0


COMMANDS = {"init": cmd_init, "update": cmd_update, "status": cmd_status, "remove": cmd_remove}


def main(argv=None):
    parser = argparse.ArgumentParser(description="install, update, inspect or remove Shipyard's files in a project")
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--target", default=os.getcwd(), help="project folder (default: the current directory)")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="shipyard-copilot checkout to copy from (default: this script's repository)")
    parser.add_argument("--skip-github", action="store_true", help="init: leave out the Actions, rulesets, templates and CODEOWNERS")
    parser.add_argument("--skip", action="append", default=[], metavar="GLOB", help="init/update: leave out files matching this glob (repeatable)")
    parser.add_argument("--force", action="store_true", help="overwrite or delete files that differ from what was installed")
    parser.add_argument("--dry-run", action="store_true", help="print what would happen and change nothing")
    parser.add_argument("--json", action="store_true", help="print the actions as JSON lines")
    args = parser.parse_args(argv)
    args.target = os.path.abspath(args.target)
    args.source = os.path.abspath(args.source)
    out = []
    try:
        if not os.path.isdir(args.target):
            raise InstallError("target %s is not a folder" % args.target)
        if args.command in ("init", "update") and not os.path.isdir(args.source):
            raise InstallError("source %s is not a folder" % args.source)
        code = COMMANDS[args.command](args, out)
    except InstallError as exc:
        for action, rel in out:
            print(_fmt(action, rel, args))
        print("install.py: %s" % exc, file=sys.stderr)
        return 1
    for action, rel in out:
        print(_fmt(action, rel, args))
    if args.dry_run:
        print("(dry run: nothing was changed)")
    return code


def _fmt(action, rel, args):
    if args.json:
        return json.dumps({"action": action, "path": rel})
    return "%-14s %s" % (action + (" (dry)" if args.dry_run and action in ("write", "remove") else ""), rel)


if __name__ == "__main__":
    sys.exit(main())

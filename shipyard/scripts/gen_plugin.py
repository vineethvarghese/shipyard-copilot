#!/usr/bin/env python3
"""Write (or check) the two files that make this repository a Copilot CLI plugin.

    python3 shipyard/scripts/gen_plugin.py            # write plugin.json and hooks.json at the repository root
    python3 shipyard/scripts/gen_plugin.py --check    # exit 1 when either file is out of date

* `plugin.json` names the plugin `shipyard`, takes the version from `package.json`, and points the manifest keys
  at the folders the project install already uses: `.github/agents`, `.github/skills`, `.github/extensions`.
* `hooks.json` is `.github/hooks/shipyard.json` rewritten for a plugin: a plugin hook runs with the plugin folder as
  its working directory, so every `python3 shipyard/scripts/hooks/<hook>.py` becomes
  `python3 "${PLUGIN_ROOT}/shipyard/scripts/hooks/<hook>.py"` and the `cwd` key is dropped. Copilot expands
  `${PLUGIN_ROOT}` before running the command (verified on CLI 1.0.107) and passes the project folder as
  `COPILOT_PROJECT_DIR`, which the hooks already honour.

Both files are derived; edit `.github/hooks/shipyard.json` or `package.json` and re-run this script.
"""

import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PLUGIN_NAME = "shipyard"
HOOK_RX = re.compile(r"python3 shipyard/scripts/hooks/([A-Za-z0-9_.-]+\.py)")


def read_json(path):
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def plugin_manifest(root):
    pkg = read_json(os.path.join(root, "package.json"))
    return {
        "name": PLUGIN_NAME,
        "version": str(pkg.get("version", "0.0.0")),
        "description": ("Shipyard for GitHub Copilot: a coordinator and twelve specialists that ship a large change as "
                        "small, independently mergeable slices, with a grill of questions first, a test plan before "
                        "code, routed review, human gates, and hooks that enforce the rules."),
        "repository": "https://github.com/vineethvarghese/shipyard-copilot",
        "license": "MIT",
        "keywords": ["workflow", "planning", "slices", "tdd", "review", "hooks", "agents"],
        "agents": ".github/agents",
        "skills": ".github/skills",
        "extensions": ".github/extensions",
        "hooks": "hooks.json",
    }


def plugin_hooks(repo_hooks):
    """The repository hook file rewritten for a plugin install."""
    out = {"version": repo_hooks.get("version", 1), "hooks": {}}
    for event, entries in repo_hooks.get("hooks", {}).items():
        rewritten = []
        for entry in entries:
            e = {}
            for key, value in entry.items():
                if key == "cwd":
                    continue
                if key in ("bash", "powershell", "command") and isinstance(value, str):
                    value = HOOK_RX.sub(r'python3 "${PLUGIN_ROOT}/shipyard/scripts/hooks/\1"', value)
                e[key] = value
            rewritten.append(e)
        out["hooks"][event] = rewritten
    return out


def render(data):
    return json.dumps(data, indent=2) + "\n"


def outputs(root):
    repo_hooks = read_json(os.path.join(root, ".github", "hooks", "shipyard.json"))
    return {
        os.path.join(root, "plugin.json"): render(plugin_manifest(root)),
        os.path.join(root, "hooks.json"): render(plugin_hooks(repo_hooks)),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="write or check plugin.json and hooks.json")
    parser.add_argument("--root", default=ROOT)
    parser.add_argument("--check", action="store_true", help="exit 1 when a file differs from what would be written")
    args = parser.parse_args(argv)
    stale = []
    for path, text in outputs(args.root).items():
        rel = os.path.relpath(path, args.root)
        current = None
        if os.path.isfile(path):
            with io.open(path, encoding="utf-8") as fh:
                current = fh.read()
        if current == text:
            continue
        if args.check:
            stale.append(rel)
            continue
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("wrote %s" % rel)
    if stale:
        print("gen_plugin.py: out of date: %s (run python3 shipyard/scripts/gen_plugin.py)" % ", ".join(stale), file=sys.stderr)
        return 1
    if args.check:
        print("gen_plugin.py: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

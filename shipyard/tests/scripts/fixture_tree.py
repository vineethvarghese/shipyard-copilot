"""Helpers shared by the script tests: paths and a minimal, valid shipyard-copilot-shaped repo tree."""

import json
import os
import shutil
import subprocess
import sys

# shipyard/ (registry, contracts, scripts) and the template repository root above it.
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TEMPLATE_ROOT = os.path.normpath(os.path.join(REPO_ROOT, ".."))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def run_script(name, *args, cwd=None, stdin=None):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, name)] + list(args), cwd=cwd,
                          input=stdin, capture_output=True, text=True)


def write(root, relpath, content):
    path = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content if isinstance(content, str) else json.dumps(content, indent=2))
    return path


AGENT_MD = """---
name: {name}
description: >
  Test agent {name}. Used only by the fixture tree.
tools: [read, search, shell]
model: deep-model
user-invocable: false
agents: []
hooks:
  preToolUse:
    - matcher: shell
      command: python3 shipyard/scripts/hooks/readonly-bash.py
---

# {name}

You are the {name} fixture. You exist to be documented.

## Step 0

Do nothing.
"""

COORDINATOR_MD = """---
name: shipyard-coordinator
description: The fixture coordinator: the only user-invocable agent.
tools: [read, search, shell, write, edit, task]
model: deep-model
agents: [shipyard-alpha, shipyard-beta]
---

# Coordinator

Runs the fixture workflows.
"""

SKILL_MD = """---
name: demo-skill
description: A fixture skill.
---

# Demo skill

Version 1.0.0.
"""

EXTENSION_MJS = """// Fixture dynamic workflow.
import {{ defineWorkflow, attach }} from '../shipyard-lib/index.mjs';

export const meta = {{
  name: '{name}',
  description: 'A fixture workflow',
  phases: [{{ title: 'One', detail: 'Do one thing' }}],
  argsSchema: {{ type: 'object', properties: {{}}, required: [] }},
  limits: {{ maxConcurrentSubagents: 1, maxTotalSubagents: 2 }},
}};

export async function run(ctx) {{
  ctx.phase('One');
  const r = await ctx.agent('Caller: shipyard:coordinator\\nMode: DEMO', {{ label: 'demo #1', schema: {{ type: 'object', properties: {{}} }} }});
{extra}
  return {{ ok: r !== null }};
}}

export const workflow = defineWorkflow({{ meta, run }});
export default workflow;
await attach(workflow);
"""

LIB_MJS = """// Fixture shared lib (reads files, never the clock or the network).
import { readFileSync } from 'node:fs';
export function defineWorkflow(def) { return def; }
export async function attach() { return false; }
export function readJson(path) { return JSON.parse(readFileSync(path, 'utf8')); }
"""


def extension_source(name="demo", extra=""):
    return EXTENSION_MJS.format(name=name, extra=extra)


def make_tree(root):
    """Create a small template repository that passes shipyard/scripts/check.py."""
    shutil.copytree(os.path.join(REPO_ROOT, "contracts"), os.path.join(root, "shipyard", "contracts"))
    write(root, ".github/agents/shipyard-alpha.agent.md", AGENT_MD.format(name="shipyard-alpha"))
    write(root, ".github/agents/shipyard-beta.agent.md", AGENT_MD.format(name="shipyard-beta"))
    write(root, ".github/agents/shipyard-coordinator.agent.md", COORDINATOR_MD)
    write(root, ".github/skills/demo-skill/SKILL.md", SKILL_MD)
    write(root, ".github/skills/demo-skill/CHANGELOG.md", "# Changelog\n\n## 1.0.0 — 2026-10-15\n\nInitial release.\n")
    write(root, ".github/extensions/demo/extension.mjs", extension_source())
    write(root, ".github/extensions/shipyard-lib/index.mjs", LIB_MJS)
    write(root, "README.md", "# Fixture\n\nSee [the agents](.github/agents/shipyard-alpha.agent.md).\n")
    write(root, "shipyard/registry/roles.json", {
        "computeClasses": {"COORDINATOR": {"model": "deep-model", "effort": "max"},
                           "DEEP": {"model": "deep-model", "effort": "high"},
                           "STANDARD": {"model": "fast-model", "effort": "medium"}},
        "roles": {
            "coordinator": {"agent": "shipyard-coordinator", "modes": {"SESSION": "COORDINATOR"},
                            "contract": None, "skills": ["demo-skill"]},
            "alpha-role": {"agent": "shipyard-alpha", "modes": {"SLICE": "DEEP", "RECHECK": "STANDARD"},
                           "contract": "reviewer-result@1", "skills": ["demo-skill"]},
            "beta-role": {"agent": "shipyard:beta", "modes": {"PLAN": "DEEP"},
                          "contracts": {"PLAN": "planner-result@1"}, "skills": []},
        },
        "routing": {
            "slice": [{"role": "alpha-role", "when": ["productionCode"], "unless": ["mechanicalOnly"]}],
            "plan": [{"role": "beta-role", "when": ["always"]}],
            "uncertainFlag": "route",
            "triggerDefinitions": {"productionCode": "Any source change", "mechanicalOnly": "Renames only"},
        },
    })
    return root


# ---------------------------------------------------------------- a project with .ai/ and git (phase checks)

SLICE_MD = """> AGENT FILE.
# Slice {sid}: Demo slice
State: {state}

## Objective
Do the thing.

## Expected touch set — code
- src/app.py
- src/lib/

## Expected touch set — tests
- tests/test_app.py

## Branch
`{branch}`

## Acceptance criteria
- [ ] AC-1: it works.
"""

DELIVERY_PLAN_MD = """> AGENT FILE.
# Delivery plan: demo

## Slices
| ID | Title | State | Depends on | Reviewers routed | Branch |
|----|-------|-------|------------|------------------|--------|
| 01 | Demo slice | {state} | — | code | `feature/demo-slice-01` |

## Human gates
{gates}
"""


def git(repo, *args, env=None):
    e = dict(os.environ)
    e.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
              "GIT_COMMITTER_EMAIL": "t@example.com"})
    if env:
        e.update(env)
    return subprocess.run(["git"] + list(args), cwd=repo, check=True, capture_output=True, text=True, env=e).stdout.strip()


def make_project(root, phase="MERGE", gates=None, slice_state="HUMAN_REVIEW", plan_state=None, plan_gates=None):
    """A git repository with .ai/ that passes `check.py --phase <phase>`.

    gates: the state.json `gates` list (default: P4, P8, TEST_PLAN and MERGE for slice 01, in that order).
    """
    git(root, "init", "-q", "-b", "main")
    write(root, "README.md", "# demo\n")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")
    git(root, "checkout", "-q", "-b", "feature/demo")
    git(root, "checkout", "-q", "-b", "feature/demo-slice-01")
    if gates is None:
        gates = [
            {"gate": "P4", "by": "me", "at": "2026-01-01T10:00:00Z", "slice": None},
            {"gate": "P8", "by": "me", "at": "2026-01-02T10:00:00Z", "slice": None},
            {"gate": "TEST_PLAN", "by": "shipyard-code-reviewer", "at": "2026-01-03T10:00:00Z", "slice": "01"},
            {"gate": "MERGE", "by": "me", "at": "2026-01-05T10:00:00Z", "slice": "01"},
        ]
    state = {
        "schemaVersion": "1.0", "project": "demo", "status": "IMPLEMENTING", "featureBranch": "feature/demo",
        "baseBranch": "main", "protectedBranches": ["main"], "activeSlice": "01",
        "sliceBranch": "feature/demo-slice-01", "gates": gates, "activeRole": None,
    }
    write(root, ".ai/state.json", state)
    write(root, ".ai/PROJECT.md", "# demo\n\n## Phase log\n| P0 | done |\n")
    write(root, ".ai/planning/discovery.md", "# discovery\n")
    write(root, ".ai/ARCHITECTURE.md", "# arch\n")
    write(root, ".ai/INVARIANTS.md", "# inv\n")
    write(root, ".ai/DELIVERY_PLAN.md", DELIVERY_PLAN_MD.format(state=plan_state or slice_state, gates=plan_gates or "- none recorded here"))
    write(root, ".ai/slices/01/SLICE.md", SLICE_MD.format(sid="01", state=slice_state, branch="feature/demo-slice-01"))
    write(root, ".ai/slices/01/TEST_PLAN.md", "> AGENT FILE.\nStatus: APPROVED\n# Test plan\n")
    write(root, ".ai/slices/01/EVIDENCE.md", "# Evidence\n")
    write(root, ".ai/slices/01/findings/code-reviewer.md", "# Findings\n")
    # the first code commit lands after the recorded TEST_PLAN gate (2026-01-03)
    write(root, "src/app.py", "print('hi')\n")
    write(root, "tests/test_app.py", "def test(): pass\n")
    git(root, "add", "src", "tests")
    git(root, "commit", "-q", "-m", "slice 01 round 0: code",
        env={"GIT_AUTHOR_DATE": "2026-01-04T10:00:00Z", "GIT_COMMITTER_DATE": "2026-01-04T10:00:00Z"})
    return root

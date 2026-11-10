#!/usr/bin/env python3
"""Checks for shipyard-copilot. Stdlib only (Python 3.9+).

Repository hygiene (the template repository, default):

    python3 shipyard/scripts/check.py [--root PATH]

  * every *.json file parses;
  * every contract under shipyard/contracts has $id, title, x-contract-version and a sane schema shape;
  * .github/agents/*.agent.md: frontmatter name (= file stem) and description; every specialist has
    `user-invocable: false`, not `disable-model-invocation: true` (it would also block the dynamic workflows'
    `ctx.agent` launches) and no agent-spawning tool (agent, task, runSubagent); non-empty body;
  * every .github/skills/<name>/ has SKILL.md (name = folder, description) and CHANGELOG.md;
  * shipyard/registry/roles.json references existing agents (`shipyard-<short>`; the older `shipyard:<short>` is
    accepted), skills, contracts and compute classes, and every agent file is in the registry;
  * .github/extensions/<name>/extension.mjs exports `defineWorkflow({ meta, run })`, names itself after its
    folder, imports only ../shipyard-lib, and uses no clock, randomness, network, process.env or Node fs;
    .github/extensions/shipyard-lib/index.mjs uses no clock, randomness or network;
  * README.md's first Mermaid block matches docs/diagrams/01-hero.mmd (when both exist);
  * no banned (vendor-specific) words in any text file, except NOTICE.

Phase gates (a project that uses Shipyard; reads .ai/ and git):

    python3 shipyard/scripts/check.py --phase P0|P4|P8|SLICE|MERGE [--project PATH]

  P0     .ai/state.json is present and well formed, .ai/PROJECT.md exists: discovery may start.
  P4     P0, the discovery artifacts exist, and the P4 gate is recorded: planning may start.
  P8     P4, DELIVERY_PLAN.md exists, and the P8 gate is recorded: slices may start.
  SLICE  P8, an active slice that is APPROVED (or later, not MERGED), its SLICE.md with both touch sets, and a
         slice branch: the slice workflow may run.
  MERGE  SLICE, TEST_PLAN.md APPROVED before the first code commit on the slice branch, EVIDENCE.md and at least
         one findings file present, and a MERGE gate recorded for the slice: the coordinator may merge.

  Gates are read from state.json `gates: [{gate, by, at, slice}]` (optional; written by shipyard_state.py), with
  DELIVERY_PLAN.md's "## Human gates" lines and PROJECT.md's phase log accepted as the older record.

Pull-request checks (GitHub Actions, on a PR into the feature branch):

    python3 shipyard/scripts/check.py --pr [--project PATH] [--base REF] [--head REF]

  The diff base...head stays inside the active slice's touch sets, touches nothing under .ai/, and the slice has
  EVIDENCE.md and at least one findings file.

Guardrail matrix:

    python3 shipyard/scripts/check.py --env [--project PATH]

Exits 0 when clean, 1 with a list of problems otherwise.
"""

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shipyard_frontmatter as fmlib  # noqa: E402

DEFAULT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

REQUIRED_AGENT_KEYS = ("name", "description")
SPAWN_TOOLS = {"agent", "task", "runsubagent", "subagent"}
JSON_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}
PHASES = ("P0", "P4", "P8", "SLICE", "MERGE")
STATE_STATUSES = {"INTAKE", "DISCOVERY", "BRAINSTORMING", "PLANNING", "DELIVERY_PLANNING", "AWAITING_PLAN_APPROVAL",
                  "IMPLEMENTING", "COMPLETE", "BLOCKED"}
STATE_REQUIRED = ("schemaVersion", "project", "status", "featureBranch", "baseBranch", "protectedBranches",
                  "activeSlice", "sliceBranch")
SLICE_STATES_AFTER_APPROVAL = {"APPROVED", "TEST_PLANNING", "IMPLEMENTING", "VERIFYING", "AGENT_REVIEW",
                               "CHANGES_REQUESTED", "READY_FOR_HUMAN", "HUMAN_REVIEW"}

# Stored reversed so this file does not trip its own scan.
_BANNED_REVERSED = ("tfosorcim", "eruza", "eruzasm", "evirdeno", "pecib", "tentod", "xnls", "rca",
                    "kooltuo")
BANNED_WORDS = tuple(w[::-1] for w in _BANNED_REVERSED)
BANNED_RE = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(BANNED_WORDS) + r")(?![A-Za-z0-9])", re.IGNORECASE)

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
BANNED_SCAN_EXEMPT = {"NOTICE"}

AGENTS_DIR = os.path.join(".github", "agents")
SKILLS_DIR = os.path.join(".github", "skills")
EXTENSIONS_DIR = os.path.join(".github", "extensions")
LIB_NAME = "shipyard-lib"

# Forbidden in every extension: nothing that makes a run depend on the clock, randomness or the network.
EXTENSION_FORBIDDEN = [
    (re.compile(r"\bDate\s*\.\s*now\b"), "Date.now"),
    (re.compile(r"\bMath\s*\.\s*random\b"), "Math.random"),
    (re.compile(r"\bnew\s+Date\b"), "new Date()"),
    (re.compile(r"\bfetch\s*\("), "fetch()"),
    (re.compile(r"\brequire\s*\("), "require()"),
    (re.compile(r"['\"]node:(child_process|http|https|net|dns|tls)['\"]"), "a network or process builtin"),
]
# Forbidden in the workflow modules on top of the above: the shared lib is the only place that reads files.
WORKFLOW_FORBIDDEN = EXTENSION_FORBIDDEN + [
    (re.compile(r"\bprocess\s*\.\s*env\b"), "process.env"),
    (re.compile(r"['\"](node:)?fs(/promises)?['\"]"), "node fs"),
]


def rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def walk_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            yield os.path.join(dirpath, name)


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------- JSON + contracts

def check_json_files(root, problems):
    for path in walk_files(root):
        if path.endswith(".json"):
            try:
                load_json(path)
            except (ValueError, UnicodeDecodeError) as exc:
                problems.append("%s: invalid JSON: %s" % (rel(root, path), exc))


def _schema_shape(schema, where, problems):
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        problems.append("%s: schema must be an object or boolean" % where)
        return
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        bad = [x for x in types if x not in JSON_TYPES]
        if bad:
            problems.append("%s: unknown type %s" % (where, bad))
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        problems.append("%s: enum must be a non-empty list" % where)
    props = schema.get("properties")
    if props is not None:
        if not isinstance(props, dict):
            problems.append("%s: properties must be an object" % where)
            props = {}
        for key, sub in props.items():
            _schema_shape(sub, "%s.properties.%s" % (where, key), problems)
    req = schema.get("required")
    if req is not None:
        if not isinstance(req, list) or not all(isinstance(r, str) for r in req):
            problems.append("%s: required must be a list of strings" % where)
        elif isinstance(props, dict):
            for r in req:
                if r not in props:
                    problems.append("%s: required property %r is not defined in properties" % (where, r))
    ap = schema.get("additionalProperties")
    if ap is not None:
        if isinstance(ap, dict):
            _schema_shape(ap, where + ".additionalProperties", problems)
        elif not isinstance(ap, bool):
            problems.append("%s: additionalProperties must be a boolean or a schema" % where)
    if "items" in schema:
        _schema_shape(schema["items"], where + ".items", problems)
    for kw in ("minLength", "maxLength", "minItems", "maxItems"):
        if kw in schema and (not isinstance(schema[kw], int) or isinstance(schema[kw], bool) or schema[kw] < 0):
            problems.append("%s: %s must be a non-negative integer" % (where, kw))


def contracts_dir(root):
    return os.path.join(root, "shipyard", "contracts")


def check_contracts(root, problems):
    cdir = contracts_dir(root)
    if not os.path.isdir(cdir):
        problems.append("shipyard/contracts/: missing")
        return
    for name in sorted(os.listdir(cdir)):
        if not name.endswith(".json"):
            continue
        where = "shipyard/contracts/" + name
        if not name.endswith(".schema.json"):
            problems.append("%s: contract files must be named <stem>.schema.json" % where)
        try:
            schema = load_json(os.path.join(cdir, name))
        except ValueError:
            continue  # reported by check_json_files
        if not isinstance(schema, dict):
            problems.append("%s: root must be an object" % where)
            continue
        for key in ("$id", "title", "x-contract-version"):
            if not schema.get(key):
                problems.append("%s: missing %s" % (where, key))
        version = schema.get("x-contract-version")
        if version and not re.match(r"^\d+\.\d+\.\d+$", str(version)):
            problems.append("%s: x-contract-version %r is not MAJOR.MINOR.PATCH" % (where, version))
        if schema.get("type") != "object":
            problems.append("%s: root type must be \"object\"" % where)
        _schema_shape(schema, where, problems)


# ---------------------------------------------------------------- agents + skills

AGENT_SUFFIX = ".agent.md"


def agent_names(root):
    """File stems of .github/agents/*.agent.md (for example shipyard-goldfish)."""
    adir = os.path.join(root, AGENTS_DIR)
    if not os.path.isdir(adir):
        return []
    return sorted(n[:-len(AGENT_SUFFIX)] for n in os.listdir(adir) if n.endswith(AGENT_SUFFIX))


def skill_names(root):
    sdir = os.path.join(root, SKILLS_DIR)
    if not os.path.isdir(sdir):
        return []
    return sorted(n for n in os.listdir(sdir) if os.path.isdir(os.path.join(sdir, n)))


def registry_path(root):
    return os.path.join(root, "shipyard", "registry", "roles.json")


def load_registry(root):
    path = registry_path(root)
    if not os.path.isfile(path):
        return None
    try:
        reg = load_json(path)
    except ValueError:
        return None
    return reg if isinstance(reg, dict) else None


def agent_short(agent):
    """`shipyard-goldfish` or `shipyard:goldfish` -> `goldfish`; None when the prefix is wrong."""
    m = re.match(r"^shipyard[-:]([a-z0-9][a-z0-9-]*)$", str(agent or ""))
    return m.group(1) if m else None


def agent_file_stem(agent):
    short = agent_short(agent)
    return "shipyard-" + short if short else None


def coordinator_stems(root):
    """The agent file stems that are allowed to be user-invocable (the coordinator role's agent)."""
    reg = load_registry(root) or {}
    stems = set()
    for role_name, role in (reg.get("roles") or {}).items():
        if role_name == "coordinator" and isinstance(role, dict):
            stem = agent_file_stem(role.get("agent"))
            if stem:
                stems.add(stem)
    return stems or {"shipyard-coordinator"}


def _tools_of(fm):
    return [t.strip().lower() for t in fmlib.tools_list(fm.get("tools"))]


def check_agents(root, problems):
    names = agent_names(root)
    if not names:
        problems.append("%s/: no *.agent.md files" % AGENTS_DIR.replace(os.sep, "/"))
    coordinators = coordinator_stems(root)
    for name in names:
        where = "%s/%s%s" % (AGENTS_DIR.replace(os.sep, "/"), name, AGENT_SUFFIX)
        try:
            fm, body = fmlib.read(os.path.join(root, AGENTS_DIR, name + AGENT_SUFFIX))
        except (fmlib.FrontmatterError, UnicodeDecodeError) as exc:
            problems.append("%s: %s" % (where, exc))
            continue
        for key in REQUIRED_AGENT_KEYS:
            if not fm.get(key):
                problems.append("%s: frontmatter is missing %s" % (where, key))
        if fm.get("name") and fm["name"] != name:
            problems.append("%s: name %r must equal the file stem %r" % (where, fm["name"], name))
        if name not in coordinators:
            if fm.get("user-invocable") is not False:
                problems.append("%s: specialist must set `user-invocable: false`" % where)
            if fm.get("disable-model-invocation") is True:
                problems.append("%s: specialist must not set `disable-model-invocation: true` (it blocks the "
                                "workflows' ctx.agent launches too)" % where)
            spawn = sorted(t for t in _tools_of(fm) if re.sub(r"\(.*$", "", t) in SPAWN_TOOLS)
            if spawn:
                problems.append("%s: specialist must not have an agent-spawning tool (%s)" % (where, ", ".join(spawn)))
        if not body.strip():
            problems.append("%s: empty body" % where)


def check_skills(root, problems):
    sdir_rel = SKILLS_DIR.replace(os.sep, "/")
    if not os.path.isdir(os.path.join(root, SKILLS_DIR)):
        problems.append("%s/: missing" % sdir_rel)
        return
    for name in skill_names(root):
        sdir = os.path.join(root, SKILLS_DIR, name)
        where = "%s/%s" % (sdir_rel, name)
        skill_md = os.path.join(sdir, "SKILL.md")
        if not os.path.isfile(skill_md):
            problems.append("%s: missing SKILL.md" % where)
        else:
            try:
                fm, _ = fmlib.read(skill_md)
                if fm.get("name") != name:
                    problems.append("%s/SKILL.md: name %r must equal the folder name" % (where, fm.get("name")))
                if not fm.get("description"):
                    problems.append("%s/SKILL.md: frontmatter is missing description" % where)
            except (fmlib.FrontmatterError, UnicodeDecodeError) as exc:
                problems.append("%s/SKILL.md: %s" % (where, exc))
        if not os.path.isfile(os.path.join(sdir, "CHANGELOG.md")):
            problems.append("%s: missing CHANGELOG.md" % where)


# ---------------------------------------------------------------- registry

def _contract_refs(role):
    refs = []
    if role.get("contract"):
        refs.append(role["contract"])
    for ref in (role.get("contracts") or {}).values():
        if ref:
            refs.append(ref)
    return refs


def check_registry(root, problems):
    where = "shipyard/registry/roles.json"
    if not os.path.isfile(registry_path(root)):
        problems.append("%s: missing" % where)
        return
    reg = load_registry(root)
    if reg is None:
        return  # reported by check_json_files
    agents = set(agent_names(root))
    skills = set(skill_names(root))
    classes = set((reg.get("computeClasses") or {}).keys())
    roles = reg.get("roles") or {}
    referenced_agents = set()
    adir = AGENTS_DIR.replace(os.sep, "/")
    for role_name, role in sorted(roles.items()):
        rw = "%s: role %s" % (where, role_name)
        agent = role.get("agent", "")
        stem = agent_file_stem(agent)
        if not stem:
            problems.append("%s: agent %r must be shipyard-<name>" % (rw, agent))
        else:
            referenced_agents.add(stem)
            if stem not in agents:
                problems.append("%s: agent %s has no %s/%s%s" % (rw, agent, adir, stem, AGENT_SUFFIX))
        modes = role.get("modes") or {}
        if not modes:
            problems.append("%s: no modes" % rw)
        for mode, cls in sorted(modes.items()):
            if cls not in classes:
                problems.append("%s: mode %s uses unknown compute class %r" % (rw, mode, cls))
        for skill in role.get("skills") or []:
            if skill not in skills:
                problems.append("%s: skill %r has no %s/%s/ folder" % (rw, skill, SKILLS_DIR.replace(os.sep, "/"), skill))
        for mode in (role.get("contracts") or {}):
            if mode not in modes:
                problems.append("%s: contracts names unknown mode %s" % (rw, mode))
        for ref in _contract_refs(role):
            stem_c, _, major = ref.partition("@")
            cpath = os.path.join(contracts_dir(root), stem_c + ".schema.json")
            if not os.path.isfile(cpath):
                problems.append("%s: contract %r has no shipyard/contracts/%s.schema.json" % (rw, ref, stem_c))
                continue
            try:
                version = str(load_json(cpath).get("x-contract-version", ""))
            except ValueError:
                continue
            if major and version.split(".")[0] != major:
                problems.append("%s: contract %r but shipyard/contracts/%s.schema.json is version %s"
                                % (rw, ref, stem_c, version))
    routing = reg.get("routing") or {}
    triggers = set((routing.get("triggerDefinitions") or {}).keys()) | {"always"}
    for stage in ("slice", "plan"):
        for rule in routing.get(stage) or []:
            if rule.get("role") not in roles:
                problems.append("%s: routing.%s names unknown role %r" % (where, stage, rule.get("role")))
            for key in ("when", "unless"):
                for trig in rule.get(key) or []:
                    if trig not in triggers:
                        problems.append("%s: routing.%s role %s uses undefined trigger %r"
                                        % (where, stage, rule.get("role"), trig))
    for stem in sorted(agents - referenced_agents):
        problems.append("%s: %s/%s%s is not referenced by any role" % (where, adir, stem, AGENT_SUFFIX))


# ---------------------------------------------------------------- extensions (dynamic workflows)

def _strip_js_comments(src):
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.DOTALL)
    return re.sub(r"(^|[^:\\])//[^\n]*", r"\1", src)


def _report_forbidden(code, where, rules, problems):
    for pattern, label in rules:
        m = pattern.search(code)
        if m:
            line = code.count("\n", 0, m.start()) + 1
            problems.append("%s:%d: uses %s (not allowed in an extension)" % (where, line, label))


def check_extensions(root, problems):
    edir = os.path.join(root, EXTENSIONS_DIR)
    edir_rel = EXTENSIONS_DIR.replace(os.sep, "/")
    if not os.path.isdir(edir):
        return
    lib = os.path.join(edir, LIB_NAME, "index.mjs")
    if os.path.isfile(lib):
        _report_forbidden(_strip_js_comments(read_text(lib)), "%s/%s/index.mjs" % (edir_rel, LIB_NAME),
                          EXTENSION_FORBIDDEN, problems)
    for name in sorted(os.listdir(edir)):
        folder = os.path.join(edir, name)
        if not os.path.isdir(folder) or name == LIB_NAME:
            continue
        where = "%s/%s/extension.mjs" % (edir_rel, name)
        path = os.path.join(folder, "extension.mjs")
        if not os.path.isfile(path):
            problems.append("%s: missing (every extension folder needs extension.mjs)" % where)
            continue
        src = read_text(path)
        code = _strip_js_comments(src)
        if not re.search(r"^export\b", code, re.MULTILINE):
            problems.append("%s: must `export` the workflow" % where)
        if not re.search(r"\bdefineWorkflow\s*\(", code):
            problems.append("%s: must call defineWorkflow({ meta, run })" % where)
        if not re.search(r"\bname:\s*'%s'" % re.escape(name), code) and not re.search(r'\bname:\s*"%s"' % re.escape(name), code):
            problems.append("%s: meta.name must be %r (the folder name)" % (where, name))
        for m in re.finditer(r"^\s*import\b[^;]*?from\s+['\"]([^'\"]+)['\"]", code, re.MULTILINE):
            spec = m.group(1)
            if spec.startswith("../%s/" % LIB_NAME) or spec.startswith("./") or spec == "@github/copilot-sdk/extension":
                continue
            problems.append("%s: import of %r (only ../%s/ and @github/copilot-sdk/extension are allowed)"
                            % (where, spec, LIB_NAME))
        _report_forbidden(code, where, WORKFLOW_FORBIDDEN, problems)


# ---------------------------------------------------------------- README hero diagram

def first_mermaid_block(text):
    m = re.search(r"^```mermaid[ \t]*\n(.*?)^```", text, re.DOTALL | re.MULTILINE)
    return m.group(1) if m else None


def _norm(text):
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def check_hero_diagram(root, problems):
    readme = os.path.join(root, "README.md")
    hero = os.path.join(root, "docs", "diagrams", "01-hero.mmd")
    if not (os.path.isfile(readme) and os.path.isfile(hero)):
        return
    block = first_mermaid_block(read_text(readme))
    mmd = read_text(hero)
    if block is None:
        problems.append("README.md: no ```mermaid block (expected the hero diagram)")
    elif _norm(block) != _norm(mmd):
        problems.append("README.md: first Mermaid block differs from docs/diagrams/01-hero.mmd; keep them identical")


# ---------------------------------------------------------------- banned words

def check_banned_words(root, problems):
    for path in walk_files(root):
        r = rel(root, path)
        if os.path.basename(path) in BANNED_SCAN_EXEMPT and os.path.dirname(r) == "":
            continue
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            continue
        if b"\x00" in data[:8192]:
            continue  # binary
        text = data.decode("utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in BANNED_RE.finditer(line):
                problems.append("%s:%d: banned word %r" % (r, lineno, m.group(1)))
        for m in BANNED_RE.finditer(r):
            problems.append("%s: banned word %r in the path" % (r, m.group(1)))


CHECKS = (check_json_files, check_contracts, check_agents, check_skills, check_registry,
          check_extensions, check_hero_diagram, check_banned_words)


def run_checks(root):
    problems = []
    for check in CHECKS:
        check(root, problems)
    return problems


# ================================================================ project-side checks (.ai/ and git)

def git(project, *args):
    """(returncode, stdout) for a git command in the project; (None, '') when git is unavailable."""
    try:
        proc = subprocess.run(["git"] + list(args), cwd=project, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    return proc.returncode, proc.stdout.strip()


def load_state(project):
    """(state dict or None, problem string or None). Lenient: optional keys (gates, activeRole) may be absent."""
    path = os.path.join(project, ".ai", "state.json")
    if not os.path.isfile(path):
        return None, ".ai/state.json: missing (run shipyard_state.py init at P0)"
    try:
        state = load_json(path)
    except (ValueError, UnicodeDecodeError) as exc:
        return None, ".ai/state.json: invalid JSON: %s" % exc
    if not isinstance(state, dict):
        return None, ".ai/state.json: root must be an object"
    return state, None


def gates_of(state):
    """The recorded gates as a list of dicts {gate, by, at, slice}; tolerant of missing or odd entries."""
    out = []
    for g in (state or {}).get("gates") or []:
        if isinstance(g, dict) and g.get("gate"):
            out.append({"gate": str(g.get("gate")).upper(), "by": g.get("by"), "at": g.get("at"),
                        "slice": None if g.get("slice") is None else str(g.get("slice"))})
        elif isinstance(g, str):
            out.append({"gate": g.upper(), "by": None, "at": None, "slice": None})
    return out


def gate_recorded(state, gate, slice_id=None):
    for g in gates_of(state):
        if g["gate"] != gate.upper():
            continue
        if slice_id is None or g["slice"] is None or g["slice"] == str(slice_id):
            return True
    return False


def ai_text(project, relpath):
    path = os.path.join(project, ".ai", relpath)
    if not os.path.isfile(path):
        return None
    try:
        return read_text(path)
    except (OSError, UnicodeDecodeError):
        return None


_TOUCH_HEADING = re.compile(r"^#{2,6}\s+Expected touch set\s*[—–-]+\s*(code|tests?)\s*$", re.I)
_ANY_HEADING = re.compile(r"^#{1,6}\s")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*\S)\s*$")


def parse_touch_sets(text):
    """{'code': [...], 'tests': [...]}; a key is missing when its heading is absent. Same rules as the hooks."""
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


def glob_to_regex(pattern):
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
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def glob_match(path, pattern):
    if glob_to_regex(pattern).match(path):
        return True
    if not any(ch in pattern for ch in "*?[") and path.startswith(pattern.rstrip("/") + "/"):
        return True
    return False


def in_touch_sets(path, sets):
    for key in ("code", "tests"):
        for p in sets.get(key) or []:
            if glob_match(path, p):
                return True
    return False


def slice_state_of(slice_md):
    m = re.search(r"^State:\s*([A-Z_]+)\s*$", slice_md or "", re.MULTILINE)
    return m.group(1) if m else None


def test_plan_status(text):
    for line in (text or "").splitlines()[:10]:
        m = re.match(r"^Status:\s*(DRAFT|APPROVED)\s*$", line.strip())
        if m:
            return m.group(1)
    return None


def plan_table_state(plan_md, slice_id):
    """The State column of the slice's row in DELIVERY_PLAN.md's slice table, or None."""
    for line in (plan_md or "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] == str(slice_id):
            return cells[2]
    return None


def _human_gate_lines(plan_md):
    lines, inside = [], False
    for line in (plan_md or "").splitlines():
        if re.match(r"^##\s+Human gates", line):
            inside = True
            continue
        if inside and re.match(r"^#{1,6}\s", line):
            break
        if inside and line.strip():
            lines.append(line.strip())
    return lines


def p8_recorded(state, plan_md):
    if gate_recorded(state, "P8"):
        return True
    return any(re.search(r"P8", l) and re.search(r"approved", l, re.I) for l in _human_gate_lines(plan_md))


def merge_recorded(state, plan_md, slice_id):
    if gate_recorded(state, "MERGE", slice_id):
        return True
    for l in _human_gate_lines(plan_md):
        if re.search(r"\bmerge\b", l, re.I) and re.search(r"\bslice\s+%s\b" % re.escape(str(slice_id)), l, re.I) \
                and re.search(r"approved", l, re.I):
            return True
    return False


def p4_recorded(state, project_md):
    if gate_recorded(state, "P4"):
        return True
    return bool(re.search(r"^\|?\s*P4\b.*\b(answer|closed|complete|approved)", project_md or "", re.I | re.MULTILINE))


def first_code_commit(project, feature, slice_branch, sets):
    """(sha, committer epoch) of the first commit on the slice branch that touches the code touch set,
    or one whose subject ends with ': code'; (None, None) when there is none or git is unavailable."""
    code, out = git(project, "log", "--reverse", "--format=%H %ct %s", "%s..%s" % (feature, slice_branch))
    if code != 0:
        return None, None
    for line in out.splitlines():
        parts = line.split(" ", 2)
        if len(parts) < 2:
            continue
        sha, epoch = parts[0], parts[1]
        subject = parts[2] if len(parts) > 2 else ""
        if re.search(r": code$", subject):
            return sha, int(epoch)
        _, files = git(project, "show", "--pretty=format:", "--name-only", sha)
        if any(in_touch_sets(f.strip(), {"code": sets.get("code") or []}) for f in files.splitlines() if f.strip()):
            return sha, int(epoch)
    return None, None


def test_plan_approval_epoch(project, state, slice_id, slice_branch):
    """When TEST_PLAN.md became APPROVED: a TEST_PLAN gate in state.json, else the git commit that introduced
    `Status: APPROVED` on the slice branch (cloud mode, where .ai/ is committed). None when unknown."""
    for g in gates_of(state):
        if g["gate"] in ("TEST_PLAN", "TEST-PLAN", "TESTPLAN") and (g["slice"] is None or g["slice"] == str(slice_id)):
            epoch = _parse_epoch(g["at"])
            if epoch is not None:
                return epoch
    rel_tp = ".ai/slices/%s/TEST_PLAN.md" % slice_id
    code, out = git(project, "log", "--format=%ct", "-S", "Status: APPROVED", slice_branch, "--", rel_tp)
    if code == 0 and out.strip():
        return int(out.strip().splitlines()[-1])
    return None


def _parse_epoch(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    s = str(value).strip()
    if re.match(r"^\d{9,}$", s):
        return int(s)
    try:
        from datetime import datetime, timezone
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return None


def check_phase(project, phase, problems):
    phase = phase.upper()
    state, err = load_state(project)
    if err:
        problems.append(err)
        return
    for key in STATE_REQUIRED:
        if key not in state:
            problems.append(".ai/state.json: missing %s" % key)
    if state.get("status") not in STATE_STATUSES:
        problems.append(".ai/state.json: status %r is not one of %s" % (state.get("status"), sorted(STATE_STATUSES)))
    feature = state.get("featureBranch")
    protected = state.get("protectedBranches") or []
    if feature in protected:
        problems.append(".ai/state.json: featureBranch %r is protected; Shipyard never works on a protected branch" % feature)
    if ai_text(project, "PROJECT.md") is None:
        problems.append(".ai/PROJECT.md: missing")
    if phase == "P0":
        return

    project_md = ai_text(project, "PROJECT.md")
    for name in ("planning/discovery.md", "ARCHITECTURE.md", "INVARIANTS.md"):
        if ai_text(project, name) is None:
            problems.append(".ai/%s: missing (discovery has not run)" % name)
    if not p4_recorded(state, project_md):
        problems.append("P4 gate not recorded: answer the P4 questions and record the gate "
                        "(shipyard_state.py gate P4 approve --by <login>) before planning")
    if phase == "P4":
        return

    plan_md = ai_text(project, "DELIVERY_PLAN.md")
    if plan_md is None:
        problems.append(".ai/DELIVERY_PLAN.md: missing (the plan workflow has not run)")
    if not p8_recorded(state, plan_md):
        problems.append("P8 gate not recorded: the human must approve the plan "
                        "(shipyard_state.py gate P8 approve --by <login>) before any slice starts")
    if phase == "P8":
        return

    slice_id = state.get("activeSlice")
    if not isinstance(slice_id, str) or not slice_id.strip():
        problems.append(".ai/state.json: activeSlice is not set (shipyard_state.py set-slice <id>)")
        return
    slice_id = slice_id.strip()
    slice_branch = state.get("sliceBranch")
    if not slice_branch:
        problems.append(".ai/state.json: sliceBranch is not set for slice %s" % slice_id)
    slice_md = ai_text(project, "slices/%s/SLICE.md" % slice_id)
    sets = {}
    if slice_md is None:
        problems.append(".ai/slices/%s/SLICE.md: missing" % slice_id)
    else:
        st = slice_state_of(slice_md)
        if st not in SLICE_STATES_AFTER_APPROVAL:
            problems.append(".ai/slices/%s/SLICE.md: State is %s; the slice must be APPROVED (and not MERGED) to run"
                            % (slice_id, st or "missing"))
        sets = parse_touch_sets(slice_md)
        for key in ("code", "tests"):
            if key not in sets:
                problems.append(".ai/slices/%s/SLICE.md: no '## Expected touch set — %s' section" % (slice_id, key))
        m = re.search(r"^##\s+Branch\s*\n+\s*`?([^`\n]+)`?", slice_md, re.MULTILINE)
        if m and slice_branch and m.group(1).strip() != str(slice_branch):
            problems.append(".ai/slices/%s/SLICE.md: ## Branch says %r but state.json sliceBranch is %r"
                            % (slice_id, m.group(1).strip(), slice_branch))
    table_state = plan_table_state(plan_md, slice_id)
    if table_state is not None and table_state not in SLICE_STATES_AFTER_APPROVAL:
        problems.append(".ai/DELIVERY_PLAN.md: slice %s is %s in the slice table; it must be APPROVED first"
                        % (slice_id, table_state))
    if phase == "SLICE":
        return

    tp = ai_text(project, "slices/%s/TEST_PLAN.md" % slice_id)
    if tp is None:
        problems.append(".ai/slices/%s/TEST_PLAN.md: missing" % slice_id)
    elif test_plan_status(tp) != "APPROVED":
        problems.append(".ai/slices/%s/TEST_PLAN.md: Status is %s, not APPROVED" % (slice_id, test_plan_status(tp) or "missing"))
    if ai_text(project, "slices/%s/EVIDENCE.md" % slice_id) is None:
        problems.append(".ai/slices/%s/EVIDENCE.md: missing" % slice_id)
    fdir = os.path.join(project, ".ai", "slices", slice_id, "findings")
    if not os.path.isdir(fdir) or not any(n.endswith(".md") for n in os.listdir(fdir)):
        problems.append(".ai/slices/%s/findings/: no findings file (every routed reviewer writes one)" % slice_id)
    if not merge_recorded(state, plan_md, slice_id):
        problems.append("MERGE gate not recorded for slice %s: the human must approve the brief "
                        "(shipyard_state.py gate MERGE approve --slice %s --by <login>)" % (slice_id, slice_id))
    if feature and slice_branch and tp is not None and test_plan_status(tp) == "APPROVED":
        sha, code_epoch = first_code_commit(project, feature, slice_branch, sets)
        if sha is None:
            problems.append("slice %s: no code commit found on %s (nothing to merge, or git is unavailable)" % (slice_id, slice_branch))
        else:
            approved = test_plan_approval_epoch(project, state, slice_id, slice_branch)
            if approved is None:
                problems.append("slice %s: cannot show that TEST_PLAN.md was APPROVED before the first code commit %s; "
                                "record the gate (shipyard_state.py gate TEST_PLAN approve --slice %s) or commit .ai/ on the slice branch"
                                % (slice_id, sha[:7], slice_id))
            elif approved > code_epoch:
                problems.append("slice %s: TEST_PLAN.md was APPROVED after the first code commit %s (test plan first)"
                                % (slice_id, sha[:7]))


# ---------------------------------------------------------------- pull-request checks (Actions)

def check_pr(project, base, head, problems):
    state, err = load_state(project)
    if err:
        problems.append(err)
        return
    base = base or state.get("featureBranch")
    head = head or "HEAD"
    if not base:
        problems.append("--pr: no base (pass --base or set featureBranch in state.json)")
        return
    code, out = git(project, "diff", "--name-only", "%s...%s" % (base, head))
    if code != 0:
        problems.append("--pr: git diff %s...%s failed (is the base branch fetched?)" % (base, head))
        return
    files = [f.strip() for f in out.splitlines() if f.strip()]
    for f in files:
        if f == ".ai" or f.startswith(".ai/"):
            problems.append("--pr: %s must never enter a work branch (.ai/ lives on the notes branch)" % f)
    slice_id = state.get("activeSlice")
    if not isinstance(slice_id, str) or not slice_id.strip():
        problems.append("--pr: state.json has no activeSlice to check the diff against")
        return
    slice_id = slice_id.strip()
    slice_md = ai_text(project, "slices/%s/SLICE.md" % slice_id)
    if slice_md is None:
        problems.append("--pr: .ai/slices/%s/SLICE.md is missing" % slice_id)
        return
    sets = parse_touch_sets(slice_md)
    for key in ("code", "tests"):
        if key not in sets:
            problems.append("--pr: .ai/slices/%s/SLICE.md has no '## Expected touch set — %s' section" % (slice_id, key))
    for f in files:
        if f.startswith(".ai/"):
            continue
        if not in_touch_sets(f, sets):
            problems.append("--pr: %s is outside slice %s's touch sets" % (f, slice_id))
    if ai_text(project, "slices/%s/EVIDENCE.md" % slice_id) is None:
        problems.append("--pr: .ai/slices/%s/EVIDENCE.md is missing" % slice_id)
    fdir = os.path.join(project, ".ai", "slices", slice_id, "findings")
    if not os.path.isdir(fdir) or not any(n.endswith(".md") for n in os.listdir(fdir)):
        problems.append("--pr: .ai/slices/%s/findings/ has no findings file" % slice_id)


# ---------------------------------------------------------------- guardrail matrix

GUARDRAILS = (
    # hook, CLI, cloud coding agent, IDE (VS Code / JetBrains)
    ("protect-branches", "hook + ruleset", "ruleset (no bypass for the agent)", "ruleset"),
    ("write-scope", "enforced (agent-scoped hooks)", "hook with role from state.json; PR check", "tools restriction only; PR check"),
    ("test-plan-gate", "enforced", "hook with inferred role; PR check", "unenforced; PR check"),
    ("readonly-bash", "tool removed from reviewers", "tool removed from reviewers", "tool removed from reviewers"),
    ("goldfish-blinders", "enforced (agent-scoped hook)", "unenforced", "unenforced"),
    ("secrets-guard", "hook + push protection", "push protection", "push protection"),
    ("findings-gate", "subagentStop block (best effort)", "subagentStop block (best effort)", "unenforced"),
    ("brief-check", "preToolUse on task", "unenforced", "unenforced"),
    ("schema-checked returns", "workflows (subset) + lib re-validation", "post-hoc shipyard_validate.py", "post-hoc shipyard_validate.py"),
    ("loop caps and routing", "code (dynamic workflows)", "convention + check.py", "convention + check.py"),
)


def env_report(project, root):
    lines = ["Shipyard guardrail matrix (what is enforced where)", ""]
    lines.append("%-24s %-40s %-44s %s" % ("rule", "CLI", "cloud coding agent", "IDE"))
    for name, cli, cloud, ide in GUARDRAILS:
        lines.append("%-24s %-40s %-44s %s" % (name, cli, cloud, ide))
    lines.append("")
    hooks_dir = os.path.join(root, ".github", "hooks")
    hooks = sorted(n for n in os.listdir(hooks_dir) if n.endswith(".json")) if os.path.isdir(hooks_dir) else []
    exts = sorted(n for n in os.listdir(os.path.join(root, EXTENSIONS_DIR))
                  if os.path.isfile(os.path.join(root, EXTENSIONS_DIR, n, "extension.mjs"))) if os.path.isdir(os.path.join(root, EXTENSIONS_DIR)) else []
    state, err = load_state(project)
    lines.append("Detected in this checkout:")
    lines.append("  hook files:          %s" % (", ".join(".github/hooks/" + h for h in hooks) or "none"))
    lines.append("  dynamic workflows:   %s" % (", ".join(exts) or "none"))
    lines.append("  copilot on PATH:     %s" % ("yes" if _on_path("copilot") else "no"))
    lines.append("  .ai/state.json:      %s" % ("present (status %s, active slice %s)" % (state.get("status"), state.get("activeSlice")) if state else err))
    lines.append("")
    lines.append("Dynamic workflows are a public preview: run the CLI with --experimental and trust the folder")
    lines.append("(or set GITHUB_COPILOT_PROMPT_MODE_EXTENSIONS=true for a headless run). See docs/workflows.md.")
    return "\n".join(lines)


def _on_path(name):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if d and os.path.isfile(os.path.join(d, name)):
            return True
    return False


# ---------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description="shipyard-copilot checks: repository hygiene, phase gates, PR checks")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="template repository root (default: this script's repo)")
    parser.add_argument("--project", default=None, help="project folder holding .ai/ (default: current directory)")
    parser.add_argument("--phase", choices=PHASES, help="check the gate for this phase against .ai/ instead of the repository")
    parser.add_argument("--pr", action="store_true", help="check a pull request diff against the active slice (Actions)")
    parser.add_argument("--base", default=None, help="--pr: base ref (default: featureBranch from state.json)")
    parser.add_argument("--head", default=None, help="--pr: head ref (default: HEAD)")
    parser.add_argument("--env", action="store_true", help="print the guardrail matrix and what this checkout provides")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    project = os.path.abspath(args.project or os.getcwd())

    if args.env:
        print(env_report(project, root))
        return 0

    problems = []
    if args.phase:
        check_phase(project, args.phase, problems)
        label = "check.py --phase %s" % args.phase
    elif args.pr:
        check_pr(project, args.base, args.head, problems)
        label = "check.py --pr"
    else:
        problems = run_checks(root)
        label = "check.py"
    if problems:
        print("%s: %d problem%s" % (label, len(problems), "" if len(problems) == 1 else "s"))
        for p in problems:
            print("  - " + p)
        return 1
    print("%s: OK" % label)
    return 0


if __name__ == "__main__":
    sys.exit(main())

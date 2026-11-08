"""Wiring tests: bind `.github/hooks/shipyard.json` (the Copilot hook file) to the scripts it names and to
the tool aliases the payload adapter understands. The other test files exercise each script in isolation with
a synthetic payload; nothing there proves the hook file itself is correct. These tests close that seam.

They cannot prove what a live Copilot client sends as `toolName`; only a real session can. What they can do:
fail loudly if the hook file drifts from the scripts, if a matcher stops compiling, if a tool alias the
adapter maps is not routed to the hooks that should see it, or if the fail-open-without-a-role assumption
silently changes.
"""

import json
import os
import re
import sys
import unittest

import helpers

sys.path.insert(0, helpers.SCRIPTS)
import copilot_hooklib  # noqa: E402

HOOKS_JSON = helpers.HOOKS_JSON
SCRIPTS_DIR = helpers.SCRIPTS
SCRIPT_RX = re.compile(r"shipyard/scripts/hooks/([A-Za-z0-9_-]+\.py)")

# Every event this file wires must be a real Copilot hook event (camelCase runtime names).
KNOWN_EVENTS = {
    "sessionStart", "sessionEnd", "userPromptSubmitted", "preToolUse", "postToolUse", "postToolUseFailure",
    "permissionRequest", "agentStop", "subagentStart", "subagentStop", "errorOccurred", "preCompact",
    "notification",
}

# Which hooks each Claude tool family must reach (the adapter maps Copilot aliases onto these names).
EXPECTED_ROUTES = {
    "Bash": {"protect-branches.py", "readonly-bash.py", "write-scope.py", "test-plan-gate.py"},
    "Write": {"write-scope.py", "test-plan-gate.py", "secrets-guard.py"},
    "Edit": {"write-scope.py", "test-plan-gate.py", "secrets-guard.py"},
    "Read": {"goldfish-blinders.py"},
    "Grep": {"goldfish-blinders.py"},
    "Glob": {"goldfish-blinders.py"},
    "Agent": {"brief-check.py"},
}

# Short generic aliases the adapter accepts but the matcher does not list on their own.
UNWIRED_SHORT_ALIASES = {"command", "sh", "exec", "editor", "patch", "find", "ls", "usages", "search", "insert",
                         "subagent", "delegate", "agent"}


def load():
    with open(HOOKS_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def entries(cfg):
    for event, items in cfg["hooks"].items():
        for h in items:
            yield event, h


def script_of(entry):
    m = SCRIPT_RX.search(entry.get("bash", ""))
    return m.group(1) if m else None


def anchored(pattern):
    """Copilot compiles a matcher as ^(?:PATTERN)$ and tests the full tool name."""
    return re.compile("^(?:%s)$" % pattern)


class Structure(unittest.TestCase):
    def setUp(self):
        self.cfg = load()

    def test_top_level_shape(self):
        self.assertEqual(self.cfg.get("version"), 1)
        self.assertIsInstance(self.cfg.get("hooks"), dict)

    def test_events_are_real(self):
        for event in self.cfg["hooks"]:
            self.assertIn(event, KNOWN_EVENTS, "unknown Copilot hook event %r" % event)

    def test_entries_are_commands_with_both_shells_and_timeouts(self):
        for event, h in entries(self.cfg):
            self.assertEqual(h.get("type"), "command", "%s: every entry must be a command hook" % event)
            self.assertIn("bash", h, "%s: the cloud agent honours only `bash`" % event)
            self.assertIn("powershell", h, "%s: Windows needs `powershell`" % event)
            self.assertEqual(h.get("cwd", "."), ".", "%s: scripts are addressed from the repository root" % event)
            self.assertIsInstance(h.get("timeoutSec"), int)
            self.assertLessEqual(h["timeoutSec"], 30)

    def test_matchers_compile(self):
        for event, h in entries(self.cfg):
            if "matcher" not in h:
                continue
            try:
                anchored(h["matcher"])
            except re.error as exc:
                self.fail("matcher %r (%s) is not a valid regex: %s" % (h["matcher"], event, exc))

    def test_pretooluse_entries_have_matchers(self):
        for event, h in entries(self.cfg):
            if event == "preToolUse":
                self.assertIn("matcher", h, "a preToolUse entry without a matcher would run on every tool")

    def test_commands_resolve(self):
        for event, h in entries(self.cfg):
            for key in ("bash", "powershell"):
                m = SCRIPT_RX.search(h[key])
                self.assertTrue(m, "%s names no shipyard/scripts/hooks script: %r" % (key, h[key]))
                self.assertTrue(os.path.isfile(os.path.join(SCRIPTS_DIR, m.group(1))),
                                "hook file references missing script %s" % m.group(1))
                self.assertTrue(h[key].startswith("python3 "), "run the script with python3: %r" % h[key])

    def test_no_orphan_scripts(self):
        referenced = {script_of(h) for _e, h in entries(self.cfg)}
        on_disk = {n for n in os.listdir(SCRIPTS_DIR)
                   if n.endswith(".py") and n not in ("shipyard_hooklib.py", "copilot_hooklib.py")}
        orphans = on_disk - referenced
        self.assertFalse(orphans, "hook scripts not wired into shipyard.json: %s" % ", ".join(sorted(orphans)))


class Routing(unittest.TestCase):
    """Every Copilot alias the adapter maps must reach the hooks for its Claude tool family."""

    def setUp(self):
        self.cfg = load()
        self.pre = [h for e, h in entries(self.cfg) if e == "preToolUse"]

    def scripts_for(self, tool_name):
        return {script_of(h) for h in self.pre if anchored(h["matcher"]).match(tool_name)}

    def test_every_alias_reaches_its_hooks(self):
        for claude, aliases in copilot_hooklib.TOOL_ALIASES.items():
            for alias in aliases:
                if alias in UNWIRED_SHORT_ALIASES:
                    continue
                self.assertTrue(EXPECTED_ROUTES[claude] <= self.scripts_for(alias),
                                "alias %r (%s) reaches %s, expected at least %s"
                                % (alias, claude, sorted(self.scripts_for(alias)), sorted(EXPECTED_ROUTES[claude])))

    def test_documented_runtime_names(self):
        """The names the hooks reference lists for the CLI and the cloud agent, plus the VS Code subagent tool."""
        for name, scripts in (("bash", EXPECTED_ROUTES["Bash"]), ("powershell", EXPECTED_ROUTES["Bash"]),
                              ("create", EXPECTED_ROUTES["Write"]), ("edit", EXPECTED_ROUTES["Edit"]),
                              ("str_replace_editor", EXPECTED_ROUTES["Edit"]),
                              ("apply_patch", EXPECTED_ROUTES["Edit"]), ("view", EXPECTED_ROUTES["Read"]),
                              ("grep", EXPECTED_ROUTES["Grep"]), ("rg", EXPECTED_ROUTES["Grep"]),
                              ("glob", EXPECTED_ROUTES["Glob"]), ("task", EXPECTED_ROUTES["Agent"]),
                              ("runSubagent", EXPECTED_ROUTES["Agent"])):
            self.assertEqual(self.scripts_for(name), scripts, name)

    def test_unrelated_tools_reach_nothing(self):
        for name in ("web_fetch", "web_search", "ask_user", "update_todo", "github/create_issue", "fetch",
                     "bash_extra", "xbash"):
            self.assertEqual(self.scripts_for(name), set(), "%r must not trigger any hook" % name)

    def test_matchers_are_full_match(self):
        for h in self.pre:
            self.assertFalse(anchored(h["matcher"]).match("bash2"), "matcher %r is not anchored" % h["matcher"])


class SubagentEvents(unittest.TestCase):
    def setUp(self):
        self.cfg = load()

    def test_findings_gate_on_both_events_with_explicit_event(self):
        for event in ("subagentStart", "subagentStop"):
            items = [h for e, h in entries(self.cfg) if e == event]
            self.assertEqual(len(items), 1, "%s must have exactly one findings-gate entry" % event)
            self.assertEqual(script_of(items[0]), "findings-gate.py")
            for key in ("bash", "powershell"):
                self.assertIn("--event " + event, items[0][key],
                              "the Copilot payload has no event name; pass it on the command line")
            self.assertNotIn("matcher", items[0],
                             "subagent entries carry no matcher: the script filters on the reviewer role")

    def test_reviewer_names_map_to_roles(self):
        for name in ("code", "security", "contract", "integration", "reliability", "simplicity"):
            for form in ("shipyard-%s-reviewer", "shipyard:%s-reviewer", "%s-reviewer"):
                self.assertEqual(copilot_hooklib.role_from_name(form % name), "%s-reviewer" % name)
        self.assertIsNone(copilot_hooklib.role_from_name("general-purpose"))
        self.assertIsNone(copilot_hooklib.role_from_name("shipyard-code-reviewer-extra"))
        # a plugin install namespaces every agent id with the plugin name
        self.assertEqual(copilot_hooklib.role_from_name("shipyard:shipyard-code-reviewer"), "code-reviewer")
        self.assertEqual(copilot_hooklib.role_from_name("shipyard:shipyard-coordinator"), "coordinator")
        self.assertIsNone(copilot_hooklib.role_from_name("shipyard:"))
        self.assertIsNone(copilot_hooklib.role_from_name("other-plugin:shipyard-verifier"))


class RoleSeam(unittest.TestCase):
    """The guardrails engage only when a role is known. This binds the preToolUse/bash wiring to
    protect-branches.py: with a role a push is blocked; without one the hook fails open so plain Copilot
    sessions are untouched."""

    @classmethod
    def setUpClass(cls):
        cls.repo = helpers.Repo()
        cls.cfg = load()

    @classmethod
    def tearDownClass(cls):
        cls.repo.cleanup()

    def setUp(self):
        self.repo.reset()

    def test_protect_branches_wired_for_bash(self):
        scripts = {script_of(h) for e, h in entries(self.cfg) if e == "preToolUse"
                   and anchored(h["matcher"]).match("bash")}
        self.assertIn("protect-branches.py", scripts)

    def _push(self, role):
        env = {"SHIPYARD_ROLE": role} if role else None
        payload = helpers.copilot_payload("bash", {"command": "git push origin feature/x"}, self.repo.path)
        return helpers.run_hook("protect-branches.py", payload, self.repo.path, env_extra=env, project_env=False)

    def test_role_engages_guardrail(self):
        res = self._push("coordinator")
        self.assertEqual(res.returncode, 2, "a Shipyard role's push must be blocked; got: %s" % res.stderr)
        self.assertEqual(helpers.decision(res)["permissionDecision"], "deny")

    def test_no_role_fails_open(self):
        res = self._push(None)  # default fixture state has no activeRole
        self.assertEqual(res.returncode, 0, "without a role the hook must fail open: %s" % res.stderr)
        self.assertEqual(res.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()

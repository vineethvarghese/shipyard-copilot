import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
SCRIPTS = os.path.join(REPO_ROOT, "shipyard", "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import gen_agents  # noqa: E402
import shipyard_frontmatter as fm  # noqa: E402

SHORTS = ["coordinator", "discovery", "goldfish", "architect", "planner", "implementer", "verifier",
          "code-reviewer", "security-reviewer", "contract-reviewer", "integration-reviewer",
          "reliability-reviewer", "simplicity-reviewer"]


def run(*args, cwd=None):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "gen_agents.py")] + list(args),
                          cwd=cwd, capture_output=True, text=True)


class GenAgents(unittest.TestCase):
    """Runs the generator against a copy of the real source agents and registry."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        shutil.copytree(os.path.join(REPO_ROOT, "shipyard", "source-agents"),
                        os.path.join(self.root, "shipyard", "source-agents"))
        shutil.copytree(os.path.join(REPO_ROOT, "shipyard", "registry"),
                        os.path.join(self.root, "shipyard", "registry"))
        # The coordinator body is hand-maintained: start from the repository's copy when it exists.
        coord = os.path.join(REPO_ROOT, ".github", "agents", "shipyard-coordinator.agent.md")
        if os.path.isfile(coord):
            os.makedirs(os.path.join(self.root, ".github", "agents"))
            shutil.copy(coord, os.path.join(self.root, ".github", "agents"))

    def tearDown(self):
        self._tmp.cleanup()

    def gen(self, *args):
        return run("--root", self.root, *args)

    def agent(self, short):
        path = os.path.join(self.root, ".github", "agents", "shipyard-%s.agent.md" % short)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        head, body = fm.split(text)
        return fm.parse(head), body, text

    def test_check_fails_before_generation_and_passes_after(self):
        proc = self.gen("--check")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".github", "agents", "shipyard-planner.agent.md")),
                         "--check must not write")
        proc = self.gen()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.gen("--check")
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_writes_thirteen_agents_with_registry_names(self):
        self.gen()
        names = sorted(os.listdir(os.path.join(self.root, ".github", "agents")))
        self.assertEqual(names, sorted("shipyard-%s.agent.md" % s for s in SHORTS))
        with open(os.path.join(self.root, "shipyard", "registry", "roles.json"), encoding="utf-8") as fh:
            registry = json.load(fh)
        for role in registry["roles"].values():
            self.assertTrue(role["agent"].startswith("shipyard-"), role["agent"])

    def test_tool_mapping(self):
        self.gen()
        self.assertEqual(self.agent("goldfish")[0]["tools"], ["read", "search", "web"])
        self.assertEqual(self.agent("implementer")[0]["tools"], ["read", "search", "execute", "edit"])
        self.assertEqual(self.agent("security-reviewer")[0]["tools"], ["read", "search", "execute", "edit"])
        coord = self.agent("coordinator")[0]
        self.assertIn("agent", coord["tools"])
        self.assertNotIn("Skill", coord["tools"])
        self.assertNotIn("Workflow", coord["tools"])

    def test_specialists_are_hidden_and_cannot_delegate(self):
        self.gen()
        for short in SHORTS[1:]:
            head, _, text = self.agent(short)
            self.assertEqual(head["name"], "shipyard-" + short)
            self.assertIs(head["user-invocable"], False, short)
            self.assertIs(head["disable-model-invocation"], True, short)
            self.assertIn("\nagents: []\n", text, short)
            self.assertNotIn("handoffs:", text, short)

    def test_coordinator_lists_specialists_and_handoffs(self):
        self.gen()
        head, _, text = self.agent("coordinator")
        self.assertNotIn("user-invocable", head)
        for short in SHORTS[1:]:
            self.assertIn("  - shipyard-%s\n" % short, text)
        self.assertIn("handoffs:", text)
        self.assertIn('    agent: shipyard-coordinator\n    prompt: "APPROVE PLAN <feature>"\n    send: false', text)
        self.assertIn("matcher", text)
        self.assertIn('SHIPYARD_ROLE=coordinator python3 shipyard/scripts/hooks/brief-check.py', text)

    def test_agent_scoped_hooks_pass_the_role(self):
        self.gen()
        _, _, text = self.agent("implementer")
        self.assertIn("hooks:\n  preToolUse:\n    - type: command", text)
        self.assertIn("SHIPYARD_ROLE=implementer python3 shipyard/scripts/hooks/write-scope.py", text)
        self.assertIn("SHIPYARD_ROLE=implementer python3 shipyard/scripts/hooks/test-plan-gate.py", text)
        self.assertIn("      windows: $env:SHIPYARD_ROLE='implementer'; python3 shipyard/scripts/hooks/write-scope.py",
                      text)
        self.assertIn("      timeoutSec: 10", text)
        self.assertNotIn("Stop:", text)
        _, _, gold = self.agent("goldfish")
        self.assertIn("SHIPYARD_ROLE=goldfish python3 shipyard/scripts/hooks/goldfish-blinders.py", gold)
        self.assertNotIn("test-plan-gate", gold)
        _, _, rev = self.agent("security-reviewer")
        self.assertIn("  Stop:\n    - type: command\n      command: SHIPYARD_ROLE=security-reviewer python3 "
                      "shipyard/scripts/hooks/findings-gate.py --event subagentStop", rev)

    def test_model_is_a_comment_until_mapped(self):
        self.gen()
        head, _, text = self.agent("architect")
        self.assertNotIn("model", head)
        self.assertIn("# model: DEEP class", text)
        self.assertIn("# model: STANDARD class", self.agent("implementer")[2])
        self.assertIn("# model: COORDINATOR class", self.agent("coordinator")[2])
        self.gen("--model", "DEEP=example-deep-model")
        head, _, _ = self.agent("architect")
        self.assertEqual(head["model"], "example-deep-model")

    def test_body_wording_is_adapted(self):
        self.gen()
        for short in SHORTS:
            head, body, text = self.agent(short)
            self.assertIsNone(re.search(r"shipyard:(?!plan-approved|shipyard-)", text), short)  # label and plugin ids are fine
            self.assertNotIn("CLAUDE", text, short)
            self.assertNotIn("preloaded", body, short)
            self.assertLessEqual(len(body), gen_agents.BODY_LIMIT, short)
        _, body, _ = self.agent("architect")
        self.assertIn("Caller: shipyard-coordinator", body)
        self.assertIn("copilot --agent=shipyard-coordinator", body)
        self.assertIn("Load these skills from `.github/skills` before you start: `shipyard-framework`, "
                      "`domain-design`, `code-clarity`.", body)
        self.assertIn("The write-scope hook enforces this.", body)
        _, body, _ = self.agent("code-reviewer")
        self.assertIn("Load these skills from `.github/skills` before you start: `shipyard-framework`, "
                      "`code-clarity`, `performance`, `domain-design`, `test-quality`, `lang-packs`.", body)
        self.assertIn("with the edit tool", body)
        _, body, _ = self.agent("goldfish")
        self.assertIn("ignore `AGENTS.md`", body)
        self.assertIn("Only this lens may use the web tool", body)
        _, body, _ = self.agent("planner")
        self.assertIn("Load the skill `shipyard-framework` from `.github/skills` before you start.", body)
        self.assertIn("dynamic workflow", body)
        self.assertNotIn("saved workflow", body)

    def test_coordinator_body_is_kept_but_frontmatter_refreshed(self):
        self.gen()
        path = os.path.join(self.root, ".github", "agents", "shipyard-coordinator.agent.md")
        head, _, text = self.agent("coordinator")
        new_body = "\n".join(gen_agents.COORDINATOR_MARKERS) + "\n\nHand-maintained body.\n"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("---\nname: stale\n---\n\n" + new_body)
        self.assertEqual(self.gen("--check").returncode, 1)
        self.assertEqual(self.gen().returncode, 0)
        _, body, text = self.agent("coordinator")
        self.assertEqual(body.lstrip("\n"), new_body)
        self.assertTrue(text.startswith("---\nname: shipyard-coordinator\n"))
        self.assertEqual(self.gen("--check").returncode, 0)

    def test_check_rejects_coordinator_body_without_markers(self):
        self.gen()
        path = os.path.join(self.root, ".github", "agents", "shipyard-coordinator.agent.md")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace("set-active-role", "set-role"))
        proc = self.gen("--check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("set-active-role", proc.stdout)

    def test_check_detects_specialist_drift(self):
        self.gen()
        path = os.path.join(self.root, ".github", "agents", "shipyard-planner.agent.md")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\nextra line\n")
        proc = self.gen("--check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("shipyard-planner.agent.md: out of date", proc.stdout)

    def test_unknown_model_class_is_an_error(self):
        proc = self.gen("--model", "HUGE=x")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("unknown compute class", proc.stdout)


if __name__ == "__main__":
    unittest.main()

import io
import json
import os
import sys
import tempfile
import unittest

from fixture_tree import SCRIPTS, TEMPLATE_ROOT, run_script

sys.path.insert(0, SCRIPTS)
import gen_plugin  # noqa: E402


class Transform(unittest.TestCase):
    def test_hook_commands_point_at_the_plugin_root_and_drop_cwd(self):
        repo_hooks = {"version": 1, "hooks": {"preToolUse": [
            {"type": "command", "matcher": "view", "bash": "python3 shipyard/scripts/hooks/goldfish-blinders.py",
             "powershell": "python3 shipyard/scripts/hooks/goldfish-blinders.py", "cwd": ".", "timeoutSec": 10}],
            "subagentStop": [{"type": "command", "bash": "python3 shipyard/scripts/hooks/findings-gate.py --event subagentStop",
                              "powershell": "python3 shipyard/scripts/hooks/findings-gate.py --event subagentStop", "cwd": ".", "timeoutSec": 15}]}}
        out = gen_plugin.plugin_hooks(repo_hooks)
        pre = out["hooks"]["preToolUse"][0]
        self.assertEqual(pre["bash"], 'python3 "${PLUGIN_ROOT}/shipyard/scripts/hooks/goldfish-blinders.py"')
        self.assertEqual(pre["powershell"], pre["bash"])
        self.assertNotIn("cwd", pre)
        self.assertEqual(pre["matcher"], "view")
        self.assertEqual(pre["timeoutSec"], 10)
        stop = out["hooks"]["subagentStop"][0]
        self.assertEqual(stop["bash"], 'python3 "${PLUGIN_ROOT}/shipyard/scripts/hooks/findings-gate.py" --event subagentStop')
        self.assertEqual(out["version"], 1)

    def test_manifest_points_at_the_github_folders(self):
        m = gen_plugin.plugin_manifest(TEMPLATE_ROOT)
        self.assertEqual(m["name"], "shipyard")
        self.assertEqual(m["agents"], ".github/agents")
        self.assertEqual(m["skills"], ".github/skills")
        self.assertEqual(m["extensions"], ".github/extensions")
        self.assertEqual(m["hooks"], "hooks.json")
        with io.open(os.path.join(TEMPLATE_ROOT, "package.json"), encoding="utf-8") as fh:
            self.assertEqual(m["version"], json.load(fh)["version"])


class Files(unittest.TestCase):
    def test_repository_files_are_current(self):
        proc = run_script("gen_plugin.py", "--check")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        with io.open(os.path.join(TEMPLATE_ROOT, "hooks.json"), encoding="utf-8") as fh:
            hooks = json.load(fh)
        for entries in hooks["hooks"].values():
            for e in entries:
                self.assertNotIn("cwd", e)
                self.assertIn('"${PLUGIN_ROOT}/shipyard/scripts/hooks/', e["bash"])

    def test_check_fails_when_stale_and_write_repairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".github", "hooks"))
            with io.open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as fh:
                json.dump({"version": "9.9.9"}, fh)
            with io.open(os.path.join(tmp, ".github", "hooks", "shipyard.json"), "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "hooks": {}}, fh)
            proc = run_script("gen_plugin.py", "--root", tmp, "--check")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("out of date", proc.stderr)
            proc = run_script("gen_plugin.py", "--root", tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with io.open(os.path.join(tmp, "plugin.json"), encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["version"], "9.9.9")
            proc = run_script("gen_plugin.py", "--root", tmp, "--check")
            self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()

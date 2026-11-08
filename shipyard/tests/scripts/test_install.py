import io
import json
import os
import sys
import tempfile
import unittest

from fixture_tree import SCRIPTS, TEMPLATE_ROOT, run_script

sys.path.insert(0, SCRIPTS)
import install  # noqa: E402


def put(root, rel, text="x\n"):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def read(root, rel):
    with io.open(os.path.join(root, *rel.split("/")), encoding="utf-8") as fh:
        return fh.read()


SOURCE_FILES = {
    "package.json": json.dumps({"version": "0.1.0"}),
    "AGENTS.md": "agents\n",
    ".github/copilot-instructions.md": "instructions\n",
    ".github/copilot/settings.json": "{}\n",
    ".github/agents/shipyard-coordinator.agent.md": "coordinator\n",
    ".github/skills/shipyard-framework/SKILL.md": "skill\n",
    ".github/prompts/shipyard.intake.prompt.md": "prompt\n",
    ".github/instructions/tests.instructions.md": "i\n",
    ".github/hooks/shipyard.json": "{\"version\": 1}\n",
    ".github/extensions/shipyard-lib/index.mjs": "export const x = 1;\n",
    "shipyard/registry/roles.json": "{}\n",
    "shipyard/contracts/state.schema.json": "{}\n",
    "shipyard/scripts/install.py": "# installer\n",
    "shipyard/scripts/hooks/write-scope.py": "# hook\n",
    "shipyard/scripts/hooks/__pycache__/write-scope.cpython-312.pyc": "bin",
    "shipyard/tests/hooks/test_x.py": "# never copied\n",
    "shipyard/source-agents/coordinator.md": "never copied\n",
    ".github/workflows/copilot-setup-steps.yml": "setup\n",
    ".github/workflows/shipyard-slice-check.yml": "slice\n",
    ".github/workflows/ci.yml": "this repo's own CI, never copied\n",
    ".github/rulesets/main-protection.json": "{}\n",
    ".github/ISSUE_TEMPLATE/shipyard-intake.yml": "form\n",
    ".github/PULL_REQUEST_TEMPLATE/shipyard-slice.md": "pr\n",
    ".github/CODEOWNERS": "owners\n",
    "plugin.json": "never copied\n",
    "hooks.json": "never copied\n",
    "README.md": "never copied\n",
}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.source = os.path.join(self._tmp.name, "src")
        self.target = os.path.join(self._tmp.name, "proj")
        os.makedirs(self.target)
        for rel, text in SOURCE_FILES.items():
            put(self.source, rel, text)
        put(self.target, ".ai/state.json", "{\"mine\": true}\n")

    def tearDown(self):
        self._tmp.cleanup()

    def run_install(self, *args):
        return run_script("install.py", *args, "--target", self.target, "--source", self.source)

    def manifest(self):
        return json.load(io.open(os.path.join(self.target, "shipyard", "INSTALL.json"), encoding="utf-8"))


class Init(Base):
    def test_copies_the_components_and_records_them(self):
        proc = self.run_install("init")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        m = self.manifest()
        self.assertEqual(m["version"], "0.1.0")
        files = set(m["files"])
        for rel in ("AGENTS.md", ".github/agents/shipyard-coordinator.agent.md", ".github/hooks/shipyard.json",
                    ".github/extensions/shipyard-lib/index.mjs", "shipyard/scripts/install.py",
                    "shipyard/scripts/hooks/write-scope.py", ".github/workflows/shipyard-slice-check.yml",
                    ".github/workflows/copilot-setup-steps.yml", ".github/CODEOWNERS"):
            self.assertIn(rel, files)
            self.assertTrue(os.path.isfile(os.path.join(self.target, *rel.split("/"))), rel)
        for rel in ("shipyard/tests/hooks/test_x.py", "shipyard/source-agents/coordinator.md", ".github/workflows/ci.yml",
                    "plugin.json", "hooks.json", "README.md", "package.json",
                    "shipyard/scripts/hooks/__pycache__/write-scope.cpython-312.pyc"):
            self.assertNotIn(rel, files)
            self.assertFalse(os.path.exists(os.path.join(self.target, *rel.split("/"))), rel)
        self.assertEqual(read(self.target, ".ai/state.json"), "{\"mine\": true}\n")
        self.assertEqual(len(m["files"]["AGENTS.md"]), 64)

    def test_skip_github_and_skip_globs(self):
        proc = self.run_install("init", "--skip-github", "--skip", ".github/prompts/*")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        files = set(self.manifest()["files"])
        self.assertNotIn(".github/CODEOWNERS", files)
        self.assertNotIn(".github/workflows/shipyard-slice-check.yml", files)
        self.assertNotIn(".github/prompts/shipyard.intake.prompt.md", files)
        self.assertIn("AGENTS.md", files)

    def test_refuses_to_overwrite_a_differing_file_and_writes_nothing(self):
        put(self.target, "AGENTS.md", "the project's own agents file\n")
        proc = self.run_install("init")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("AGENTS.md", proc.stderr)
        self.assertIn("--force", proc.stderr)
        self.assertEqual(read(self.target, "AGENTS.md"), "the project's own agents file\n")
        self.assertFalse(os.path.exists(os.path.join(self.target, ".github", "agents")))
        self.assertFalse(os.path.exists(os.path.join(self.target, "shipyard", "INSTALL.json")))

    def test_identical_existing_file_is_not_a_conflict_and_force_overwrites(self):
        put(self.target, "AGENTS.md", "agents\n")
        self.assertEqual(self.run_install("init").returncode, 0)
        put(self.target, "AGENTS.md", "changed\n")
        proc = self.run_install("init")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("already exists", proc.stderr)
        proc = self.run_install("init", "--force")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(read(self.target, "AGENTS.md"), "agents\n")

    def test_dry_run_changes_nothing(self):
        proc = self.run_install("init", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("dry run", proc.stdout)
        self.assertEqual(os.listdir(self.target), [".ai"])

    def test_json_output(self):
        proc = self.run_install("init", "--json")
        lines = [json.loads(l) for l in proc.stdout.splitlines() if l.startswith("{")]
        self.assertIn({"action": "write", "path": "AGENTS.md"}, lines)
        self.assertIn({"action": "manifest", "path": "shipyard/INSTALL.json"}, lines)


class StatusUpdateRemove(Base):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.run_install("init").returncode, 0)

    def test_status_reports_unchanged_modified_and_missing(self):
        put(self.target, "AGENTS.md", "edited\n")
        os.remove(os.path.join(self.target, ".github", "CODEOWNERS"))
        proc = self.run_install("status")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("modified       AGENTS.md", proc.stdout)
        self.assertIn("missing        .github/CODEOWNERS", proc.stdout)
        self.assertIn("unchanged      shipyard/registry/roles.json", proc.stdout)
        self.assertIn("version        0.1.0", proc.stdout)

    def test_status_when_not_installed(self):
        other = os.path.join(self._tmp.name, "empty")
        os.makedirs(other)
        proc = run_script("install.py", "status", "--target", other)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not-installed", proc.stdout)

    def test_update_replaces_unchanged_keeps_modified_and_drops_removed(self):
        put(self.target, "AGENTS.md", "my edits\n")
        put(self.source, ".github/skills/shipyard-framework/SKILL.md", "skill v2\n")
        os.remove(os.path.join(self.source, ".github", "prompts", "shipyard.intake.prompt.md"))
        put(self.source, ".github/prompts/shipyard.new.prompt.md", "new\n")
        proc = self.run_install("update")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(read(self.target, "AGENTS.md"), "my edits\n")
        self.assertIn("keep           AGENTS.md", proc.stdout)
        self.assertEqual(read(self.target, ".github/skills/shipyard-framework/SKILL.md"), "skill v2\n")
        self.assertFalse(os.path.exists(os.path.join(self.target, ".github", "prompts", "shipyard.intake.prompt.md")))
        self.assertEqual(read(self.target, ".github/prompts/shipyard.new.prompt.md"), "new\n")
        m = self.manifest()
        self.assertIn(".github/prompts/shipyard.new.prompt.md", m["files"])
        self.assertNotIn(".github/prompts/shipyard.intake.prompt.md", m["files"])
        # the kept file is still managed, with the digest of what is on disk now
        self.assertEqual(m["files"]["AGENTS.md"], install.sha256_of(os.path.join(self.target, "AGENTS.md")))
        proc = self.run_install("update", "--force")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(read(self.target, "AGENTS.md"), "agents\n")

    def test_update_keeps_the_skip_github_choice(self):
        self.assertEqual(self.run_install("remove").returncode, 0)
        self.assertEqual(self.run_install("init", "--skip-github").returncode, 0)
        proc = self.run_install("update")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.target, ".github", "CODEOWNERS")))

    def test_remove_deletes_unchanged_keeps_modified_prunes_dirs_and_spares_ai(self):
        put(self.target, "AGENTS.md", "my edits\n")
        put(self.target, ".github/workflows/ci.yml", "the project's own CI\n")
        proc = self.run_install("remove")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(read(self.target, "AGENTS.md"), "my edits\n")
        self.assertIn("keep           AGENTS.md", proc.stdout)
        self.assertIn("1 changed file(s) kept", proc.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.target, "shipyard")))
        self.assertFalse(os.path.exists(os.path.join(self.target, ".github", "agents")))
        self.assertFalse(os.path.exists(os.path.join(self.target, ".github", "extensions")))
        self.assertEqual(read(self.target, ".github/workflows/ci.yml"), "the project's own CI\n")
        self.assertEqual(read(self.target, ".ai/state.json"), "{\"mine\": true}\n")
        proc = self.run_install("remove")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("nothing to remove", proc.stderr)

    def test_remove_force_deletes_modified_too(self):
        put(self.target, "AGENTS.md", "my edits\n")
        proc = self.run_install("remove", "--force")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.target, "AGENTS.md")))

    def test_remove_dry_run_deletes_nothing(self):
        proc = self.run_install("remove", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.target, "AGENTS.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.target, "shipyard", "INSTALL.json")))

    def test_manifest_pointing_into_ai_is_refused(self):
        path = os.path.join(self.target, "shipyard", "INSTALL.json")
        m = json.load(io.open(path, encoding="utf-8"))
        m["files"][".ai/state.json"] = "0" * 64
        with io.open(path, "w", encoding="utf-8") as fh:
            json.dump(m, fh)
        proc = self.run_install("remove", "--force")
        self.assertEqual(proc.returncode, 1)
        self.assertIn(".ai/", proc.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.target, ".ai", "state.json")))


class RealRepository(unittest.TestCase):
    def test_real_checkout_installs_into_an_empty_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_script("install.py", "init", "--target", tmp, "--source", TEMPLATE_ROOT)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            files = set(json.load(io.open(os.path.join(tmp, "shipyard", "INSTALL.json"), encoding="utf-8"))["files"])
            for rel in ("AGENTS.md", ".github/agents/shipyard-coordinator.agent.md", ".github/hooks/shipyard.json",
                        ".github/extensions/shipyard-discover/extension.mjs", "shipyard/scripts/install.py",
                        "shipyard/scripts/hooks/copilot_hooklib.py", "shipyard/registry/roles.json"):
                self.assertIn(rel, files)
            self.assertFalse(any(r.startswith("shipyard/tests/") for r in files))
            self.assertNotIn(".github/workflows/ci.yml", files)
            self.assertNotIn("plugin.json", files)
            # the installed copy of the installer removes the install again
            proc = run_script("install.py", "remove", "--target", tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(os.listdir(tmp), [])


if __name__ == "__main__":
    unittest.main()

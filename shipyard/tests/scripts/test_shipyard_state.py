import json
import os
import subprocess
import tempfile
import unittest

from fixture_tree import run_script
from shipyard_validate import load_contract, validate


def git(repo, *args):
    subprocess.run(["git"] + list(args), cwd=repo, check=True, capture_output=True)


class StateTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = self._tmp.name
        git(self.repo, "init", "-q", "-b", "main")

    def tearDown(self):
        self._tmp.cleanup()

    def state(self, *args):
        return run_script("shipyard_state.py", "--repo", self.repo, *args)

    def init(self, feature="feature/expiry", base="main", *extra):
        return self.state("init", "--project", "demo", "--feature-branch=" + feature, "--base-branch=" + base, *extra)

    def read(self):
        with open(os.path.join(self.repo, ".ai", "state.json")) as fh:
            return json.load(fh)

    def assertSchemaValid(self):
        self.assertEqual(validate(self.read(), load_contract("state")), [])


class Init(StateTestCase):
    def test_init_writes_valid_state(self):
        proc = self.init()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        s = self.read()
        self.assertEqual(s["status"], "INTAKE")
        self.assertEqual(s["featureBranch"], "feature/expiry")
        self.assertEqual(s["protectedBranches"], ["main", "master"])
        self.assertIsNone(s["activeSlice"])
        self.assertIsNone(s["sliceBranch"])
        self.assertEqual(s["brainstormBreadth"], 1)
        self.assertSchemaValid()

    def test_breadth_and_custom_protected(self):
        proc = self.init("feature/x", "develop", "--protected", "main,release", "--breadth", "2")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        s = self.read()
        self.assertEqual(s["protectedBranches"], ["main", "release", "develop"])
        self.assertEqual(s["brainstormBreadth"], 2)

    def test_formal_rigour_recorded_only_when_set(self):
        proc = self.init("feature/x", "main", "--formal-rigour", "properties")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read()["formalRigour"], "properties")
        self.assertSchemaValid()
        self.state("init", "--project", "demo", "--feature-branch=feature/y", "--base-branch=main", "--force")
        self.assertNotIn("formalRigour", self.read())
        self.assertSchemaValid()

    def test_refuses_main_master_base_and_protected(self):
        cases = [("main", "main"), ("master", "main"), ("develop", "develop"), ("main", "develop"),
                 ("release", "develop", "--protected", "release")]
        for case in cases:
            with self.subTest(case=case):
                proc = self.init(*case)
                self.assertEqual(proc.returncode, 1, proc.stdout)
                self.assertIn("refused", proc.stderr)
                self.assertFalse(os.path.exists(os.path.join(self.repo, ".ai", "state.json")))

    def test_refuses_default_branch_of_remote(self):
        git(self.repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        proc = self.init("trunk", "main")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("protected", proc.stderr)

    def test_refuses_invalid_ref_names(self):
        for bad in ("bad..name", "has space", "ends.lock", "-leading-dash", "feature/x~1"):
            with self.subTest(name=bad):
                proc = self.init(bad)
                self.assertEqual(proc.returncode, 1)
                self.assertIn("not a valid branch name", proc.stderr)

    def test_refuses_overwrite_without_force(self):
        self.assertEqual(self.init().returncode, 0)
        self.assertEqual(self.init("feature/other").returncode, 1)
        self.assertEqual(self.init("feature/other", "main", "--force").returncode, 0)
        self.assertEqual(self.read()["featureBranch"], "feature/other")

    def test_usage_error_exit_2(self):
        self.assertEqual(self.state("init", "--project", "x").returncode, 2)
        self.assertEqual(self.init("feature/x", "main", "--breadth", "5").returncode, 2)


class Transitions(StateTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.init().returncode, 0)

    def test_set_status_through_phases(self):
        for status in ("DISCOVERY", "BRAINSTORMING", "PLANNING", "DELIVERY_PLANNING", "AWAITING_PLAN_APPROVAL",
                       "IMPLEMENTING", "BLOCKED", "IMPLEMENTING", "COMPLETE"):
            proc = self.state("set-status", status)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(self.read()["status"], status)
            self.assertSchemaValid()

    def test_unknown_status_refused_and_state_unchanged(self):
        before = self.read()
        proc = self.state("set-status", "SHIPPED")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("$.status", proc.stderr)
        self.assertEqual(self.read(), before)

    def test_set_slice_default_branch_and_clear(self):
        self.assertEqual(self.state("set-slice", "01").returncode, 0)
        s = self.read()
        self.assertEqual((s["activeSlice"], s["sliceBranch"]), ("01", "feature/expiry-slice-01"))
        self.assertSchemaValid()
        self.assertEqual(self.state("set-slice", "02", "--slice-branch", "feature/expiry-s2").returncode, 0)
        self.assertEqual(self.read()["sliceBranch"], "feature/expiry-s2")
        self.assertEqual(self.state("set-slice", "none").returncode, 0)
        s = self.read()
        self.assertEqual((s["activeSlice"], s["sliceBranch"]), (None, None))
        self.assertSchemaValid()

    def test_set_slice_refuses_protected_or_feature_branch(self):
        for branch in ("main", "master", "feature/expiry", "bad..ref"):
            with self.subTest(branch=branch):
                self.assertEqual(self.state("set-slice", "01", "--slice-branch", branch).returncode, 1)
        self.assertIsNone(self.read()["activeSlice"])

    def test_show_and_get(self):
        proc = self.state("show")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["project"], "demo")
        proc = self.state("show", "--get", "featureBranch")
        self.assertEqual(proc.stdout.strip(), "feature/expiry")
        self.assertEqual(self.state("show", "--get", "nope").returncode, 1)

    def test_no_temp_files_left(self):
        self.state("set-status", "DISCOVERY")
        self.state("set-status", "NOPE")
        self.assertEqual(sorted(os.listdir(os.path.join(self.repo, ".ai"))), ["state.json"])

    def test_commands_need_state(self):
        os.remove(os.path.join(self.repo, ".ai", "state.json"))
        for args in (("show",), ("set-status", "DISCOVERY"), ("set-slice", "01")):
            with self.subTest(args=args):
                proc = self.state(*args)
                self.assertEqual(proc.returncode, 1)
                self.assertIn("run `init` first", proc.stderr)

    def test_finds_repo_from_subdirectory(self):
        sub = os.path.join(self.repo, "src", "deep")
        os.makedirs(sub)
        proc = run_script("shipyard_state.py", "show", "--get", "project", cwd=sub)
        self.assertEqual(proc.stdout.strip(), "demo", proc.stderr)


class ActiveRole(StateTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.init().returncode, 0)

    def test_set_and_clear(self):
        proc = self.state("set-active-role", "implementer")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read()["activeRole"], "implementer")
        self.assertSchemaValid()
        self.assertEqual(self.state("set-active-role", "none").returncode, 0)
        self.assertNotIn("activeRole", self.read())
        self.assertSchemaValid()

    def test_accepts_prefixed_names(self):
        for given in ("shipyard:code-reviewer", "shipyard-code-reviewer", "Code-Reviewer", "code_reviewer"):
            with self.subTest(given=given):
                self.assertEqual(self.state("set-active-role", given).returncode, 0)
                self.assertEqual(self.read()["activeRole"], "code-reviewer")

    def test_refuses_unknown_role(self):
        proc = self.state("set-active-role", "janitor")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not a Shipyard role", proc.stderr)
        self.assertNotIn("activeRole", self.read())

    def test_schema_rejects_unknown_role_value(self):
        s = self.read()
        s["activeRole"] = "janitor"
        self.assertTrue(validate(s, load_contract("state")))

    def test_contract_version_bumped(self):
        self.assertGreaterEqual(tuple(int(x) for x in load_contract("state")["x-contract-version"].split(".")),
                                (1, 3, 0))


class Gates(StateTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.init().returncode, 0)

    def test_approve_appends_in_order(self):
        for gate in ("P0", "P4", "P8"):
            proc = self.state("gate", gate, "approve", "--by", "octocat")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("gate %s approved by octocat" % gate, proc.stdout)
        gates = self.read()["gates"]
        self.assertEqual([g["gate"] for g in gates], ["P0", "P4", "P8"])
        for g in gates:
            self.assertEqual(g["by"], "octocat")
            self.assertRegex(g["at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
            self.assertNotIn("slice", g)
        self.assertSchemaValid()

    def test_at_is_head_committer_date_when_there_is_a_commit(self):
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "T")
        with open(os.path.join(self.repo, "README.md"), "w") as fh:
            fh.write("hi\n")
        git(self.repo, "add", "README.md")
        env = dict(os.environ, GIT_COMMITTER_DATE="2026-01-02T03:04:05+00:00", GIT_AUTHOR_DATE="2026-01-02T03:04:05+00:00")
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=self.repo, check=True, capture_output=True, env=env)
        self.assertEqual(self.state("gate", "P0", "approve", "--by", "octocat").returncode, 0)
        self.assertIn(self.read()["gates"][0]["at"], ("2026-01-02T03:04:05+00:00", "2026-01-02T03:04:05Z"))

    def test_merge_gate_records_slice(self):
        proc = self.state("gate", "MERGE", "approve", "--by", "octocat", "--slice", "02")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read()["gates"][-1]["slice"], "02")
        self.assertSchemaValid()

    def test_merge_gate_uses_active_slice_or_refuses(self):
        proc = self.state("gate", "MERGE", "approve", "--by", "octocat")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--slice", proc.stderr)
        self.assertNotIn("gates", self.read())
        self.assertEqual(self.state("set-slice", "01").returncode, 0)
        self.assertEqual(self.state("gate", "MERGE", "approve", "--by", "octocat").returncode, 0)
        self.assertEqual(self.read()["gates"][-1]["slice"], "01")

    def test_usage_errors(self):
        self.assertEqual(self.state("gate", "P1", "approve", "--by", "x").returncode, 2)
        self.assertEqual(self.state("gate", "P0", "reject", "--by", "x").returncode, 2)
        self.assertEqual(self.state("gate", "P0", "approve").returncode, 2)
        self.assertEqual(self.state("gate", "P0", "approve", "--by", " ").returncode, 1)


class IgnoreAi(StateTestCase):
    def exclude(self):
        with open(os.path.join(self.repo, ".git", "info", "exclude")) as fh:
            return fh.read()

    def test_init_ignores_ai_locally(self):
        proc = self.init()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("/.ai/", self.exclude())
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=self.repo,
                                capture_output=True, text=True).stdout
        self.assertNotIn(".ai", status)
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".gitignore")))  # the project's files are untouched

    def test_idempotent(self):
        self.assertEqual(self.state("ignore-ai").returncode, 0)
        self.assertEqual(self.state("ignore-ai").returncode, 0)
        self.assertEqual(self.exclude().count("/.ai/"), 1)

    def test_refuses_when_ai_already_tracked(self):
        os.makedirs(os.path.join(self.repo, ".ai"))
        with open(os.path.join(self.repo, ".ai", "PROJECT.md"), "w") as fh:
            fh.write("x\n")
        git(self.repo, "add", ".ai/PROJECT.md")
        proc = self.state("ignore-ai")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("already tracked", proc.stderr)
        self.assertIn("git rm -r --cached .ai", proc.stderr)

    def test_refuses_when_gitignore_reincludes(self):
        with open(os.path.join(self.repo, ".gitignore"), "w") as fh:
            fh.write("!.ai/\n!.ai/**\n")
        proc = self.state("ignore-ai")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("does not ignore .ai/", proc.stderr)


class NotesBranch(StateTestCase):
    def setUp(self):
        super().setUp()
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "T")
        with open(os.path.join(self.repo, "README.md"), "w") as fh:
            fh.write("hi\n")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-q", "-m", "init")
        git(self.repo, "switch", "-q", "-c", "feature/expiry")
        self.assertEqual(self.init().returncode, 0)
        self.write(".ai/PROJECT.md", "plan v1\n")
        with open(os.path.join(self.repo, "src.py"), "w") as fh:
            fh.write("work in progress\n")  # the human's uncommitted work must survive untouched

    def write(self, rel, text):
        p = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(text)

    def out(self, *args):
        return subprocess.run(["git"] + list(args), cwd=self.repo, capture_output=True, text=True).stdout.strip()

    def test_init_records_default_notes_branch(self):
        self.assertEqual(self.read()["notesBranch"], "feature/expiry-shipyard")
        self.assertSchemaValid()

    def test_snapshot_commits_only_ai_and_touches_nothing_else(self):
        head, status = self.out("rev-parse", "HEAD"), self.out("status", "--porcelain")
        proc = self.state("snapshot", "-m", "P0 intake")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.out("rev-parse", "HEAD"), head)
        self.assertEqual(self.out("branch", "--show-current"), "feature/expiry")
        self.assertEqual(self.out("status", "--porcelain"), status)
        self.assertEqual(self.out("diff", "--cached", "--name-only"), "")
        files = self.out("ls-tree", "-r", "--name-only", "feature/expiry-shipyard").splitlines()
        self.assertIn(".ai/PROJECT.md", files)
        self.assertIn(".ai/state.json", files)
        self.assertTrue(all(f.startswith(".ai/") for f in files))
        self.assertEqual(self.out("log", "-1", "--format=%s", "feature/expiry-shipyard"), "P0 intake")
        self.assertNotIn(".ai", self.out("ls-tree", "-r", "--name-only", "HEAD"))

    def test_snapshot_chains_and_skips_no_change(self):
        self.state("snapshot", "-m", "one")
        first = self.out("rev-parse", "feature/expiry-shipyard")
        proc = self.state("snapshot", "-m", "same")
        self.assertIn("no change", proc.stdout)
        self.assertEqual(self.out("rev-parse", "feature/expiry-shipyard"), first)
        self.write(".ai/PROJECT.md", "plan v2\n")
        self.state("snapshot", "-m", "two")
        self.assertEqual(self.out("rev-parse", "feature/expiry-shipyard^"), first)

    def test_refuses_foreign_branch_name(self):
        git(self.repo, "branch", "feature/expiry-shipyard")  # holds README.md, not a notes branch
        proc = self.state("snapshot", "-m", "x")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not a Shipyard notes branch", proc.stderr)

    def test_restore_into_fresh_clone(self):
        self.state("snapshot", "-m", "P0 intake")
        with tempfile.TemporaryDirectory() as clone:
            subprocess.run(["git", "clone", "-q", "--no-local", self.repo, clone], check=True, capture_output=True)
            git(clone, "fetch", "-q", "origin", "feature/expiry-shipyard:feature/expiry-shipyard")
            proc = run_script("shipyard_state.py", "--repo", clone, "restore", "--from", "feature/expiry-shipyard")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(os.path.join(clone, ".ai", "PROJECT.md")) as fh:
                self.assertEqual(fh.read(), "plan v1\n")
            st = subprocess.run(["git", "status", "--porcelain"], cwd=clone, capture_output=True, text=True).stdout
            self.assertNotIn(".ai", st)
            again = run_script("shipyard_state.py", "--repo", clone, "restore", "--from", "feature/expiry-shipyard")
            self.assertEqual(again.returncode, 1)
            self.assertIn("already exists", again.stderr)


if __name__ == "__main__":
    unittest.main()


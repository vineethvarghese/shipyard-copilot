import json
import os
import tempfile
import unittest

from fixture_tree import make_tree, make_project, run_script, write, extension_source, git
import check  # noqa: E402  (fixture_tree puts scripts/ on sys.path)

# Built at run time so this file does not trip the repository's own banned-word scan.
BANNED_SAMPLE = "".join(reversed("eruzA"))


class CheckTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_tree(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def problems(self):
        return check.run_checks(self.root)

    def assertProblem(self, fragment):
        problems = self.problems()
        self.assertTrue(any(fragment in p for p in problems), "expected %r in %s" % (fragment, problems))

    def read(self, relpath):
        with open(os.path.join(self.root, relpath), encoding="utf-8") as fh:
            return fh.read()


class CleanTree(CheckTestCase):
    def test_fixture_tree_is_clean(self):
        self.assertEqual(self.problems(), [])

    def test_cli_exit_codes(self):
        self.assertEqual(run_script("check.py", "--root", self.root).returncode, 0)
        write(self.root, "docs/x.md", "Hosted on %s.\n" % BANNED_SAMPLE)
        proc = run_script("check.py", "--root", self.root)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("banned word", proc.stdout)

    def test_real_repository_layout_has_the_checked_paths(self):
        from fixture_tree import TEMPLATE_ROOT
        self.assertTrue(os.path.isdir(os.path.join(TEMPLATE_ROOT, ".github", "skills")))
        self.assertTrue(os.path.isfile(os.path.join(TEMPLATE_ROOT, ".github", "extensions", "shipyard-lib", "index.mjs")))
        self.assertTrue(os.path.isfile(os.path.join(TEMPLATE_ROOT, "shipyard", "registry", "roles.json")))
        problems = check.run_checks(TEMPLATE_ROOT)
        # the extensions and the lib in the real repository pass their own checks
        self.assertEqual([p for p in problems if ".github/extensions" in p], [])


class BannedWords(CheckTestCase):
    def test_banned_word_in_text_file_fails(self):
        write(self.root, "docs/guide.md", "# Guide\n\nDeploy it to %s today.\n" % BANNED_SAMPLE)
        self.assertProblem("docs/guide.md:3: banned word")

    def test_case_insensitive_whole_word(self):
        write(self.root, "a.txt", BANNED_SAMPLE.upper() + "\n")
        self.assertProblem("a.txt:1: banned word")

    def test_substring_inside_longer_word_is_fine(self):
        write(self.root, "a.txt", "The %sness of it.\n" % BANNED_SAMPLE.lower())
        self.assertEqual(self.problems(), [])

    def test_notice_is_exempt(self):
        write(self.root, "NOTICE", "Credits mention %s.\n" % BANNED_SAMPLE)
        self.assertEqual(self.problems(), [])

    def test_git_dir_is_skipped(self):
        write(self.root, ".git/config", "url = %s\n" % BANNED_SAMPLE)
        self.assertEqual(self.problems(), [])


class Json(CheckTestCase):
    def test_broken_json(self):
        write(self.root, "x/broken.json", "{not json")
        self.assertProblem("x/broken.json: invalid JSON")

    def test_contract_missing_version(self):
        write(self.root, "shipyard/contracts/new.schema.json", {"$id": "x", "title": "New", "type": "object"})
        self.assertProblem("shipyard/contracts/new.schema.json: missing x-contract-version")

    def test_contract_root_not_object(self):
        write(self.root, "shipyard/contracts/arr.schema.json",
              {"$id": "x", "title": "A", "x-contract-version": "1.0.0", "type": "array"})
        self.assertProblem('shipyard/contracts/arr.schema.json: root type must be "object"')

    def test_contract_required_not_in_properties(self):
        write(self.root, "shipyard/contracts/r.schema.json", {"$id": "x", "title": "R", "x-contract-version": "1.0.0",
                                                              "type": "object", "properties": {}, "required": ["a"]})
        self.assertProblem("required property 'a' is not defined")


class Agents(CheckTestCase):
    AGENT = ".github/agents/shipyard-alpha.agent.md"

    def test_name_must_match_file_stem(self):
        write(self.root, self.AGENT, self.read(self.AGENT).replace("name: shipyard-alpha", "name: shipyard-gamma"))
        self.assertProblem("must equal the file stem")

    def test_missing_description(self):
        write(self.root, ".github/agents/shipyard-beta.agent.md",
              "---\nname: shipyard-beta\nuser-invocable: false\ntools: [read]\n---\n\nBody.\n")
        self.assertProblem(".github/agents/shipyard-beta.agent.md: frontmatter is missing description")

    def test_specialist_must_not_be_user_invocable(self):
        write(self.root, self.AGENT, self.read(self.AGENT).replace("user-invocable: false\n", ""))
        self.assertProblem("shipyard-alpha.agent.md: specialist must set `user-invocable: false`")
        write(self.root, self.AGENT, self.read(self.AGENT).replace("user-invocable: false", "user-invocable: true"))
        self.assertProblem("specialist must set `user-invocable: false`")

    def test_specialist_must_not_disable_model_invocation(self):
        write(self.root, self.AGENT, self.read(self.AGENT).replace("user-invocable: false\n",
                                                                   "user-invocable: false\ndisable-model-invocation: true\n"))
        self.assertProblem("shipyard-alpha.agent.md: specialist must not set `disable-model-invocation: true`")

    def test_specialist_must_not_spawn_agents(self):
        for tools in ("tools: [read, task]", "tools: read, agent", "tools: [read, runSubagent]", "tools: [Agent(x)]"):
            with self.subTest(tools=tools):
                write(self.root, self.AGENT, self.read(self.AGENT).replace("tools: [read, search, shell]", tools))
                self.assertProblem("specialist must not have an agent-spawning tool")

    def test_coordinator_may_be_invocable_and_spawn(self):
        self.assertEqual(self.problems(), [])

    def test_unregistered_agent(self):
        write(self.root, ".github/agents/shipyard-gamma.agent.md",
              "---\nname: shipyard-gamma\ndescription: x\nuser-invocable: false\ntools: [read]\n---\n\nBody.\n")
        self.assertProblem(".github/agents/shipyard-gamma.agent.md is not referenced by any role")

    def test_empty_body(self):
        write(self.root, self.AGENT, "---\nname: shipyard-alpha\ndescription: x\nuser-invocable: false\n---\n\n")
        self.assertProblem("shipyard-alpha.agent.md: empty body")

    def test_no_agents_folder(self):
        import shutil
        shutil.rmtree(os.path.join(self.root, ".github", "agents"))
        self.assertProblem(".github/agents/: no *.agent.md files")


class Skills(CheckTestCase):
    def test_missing_changelog(self):
        os.remove(os.path.join(self.root, ".github", "skills", "demo-skill", "CHANGELOG.md"))
        self.assertProblem(".github/skills/demo-skill: missing CHANGELOG.md")

    def test_missing_skill_md(self):
        write(self.root, ".github/skills/empty/CHANGELOG.md", "# Changelog\n")
        self.assertProblem(".github/skills/empty: missing SKILL.md")

    def test_name_must_match_folder(self):
        write(self.root, ".github/skills/demo-skill/SKILL.md", "---\nname: other\ndescription: d\n---\n\nx\n")
        self.assertProblem("name 'other' must equal the folder name")


class Registry(CheckTestCase):
    def load(self):
        with open(os.path.join(self.root, "shipyard", "registry", "roles.json")) as fh:
            return json.load(fh)

    def test_missing_contract_skill_and_agent(self):
        reg = self.load()
        reg["roles"]["ghost"] = {"agent": "shipyard-ghost", "modes": {"X": "HUGE"},
                                 "contract": "nope-result@1", "skills": ["no-skill"]}
        reg["routing"]["slice"].append({"role": "ghost", "when": ["undefinedTrigger"]})
        write(self.root, "shipyard/registry/roles.json", reg)
        problems = "\n".join(self.problems())
        for fragment in ("has no .github/agents/shipyard-ghost.agent.md", "unknown compute class 'HUGE'",
                         "has no shipyard/contracts/nope-result.schema.json", "skill 'no-skill'",
                         "undefined trigger 'undefinedTrigger'"):
            self.assertIn(fragment, problems)

    def test_both_agent_prefixes_are_accepted_but_nothing_else(self):
        self.assertEqual(self.problems(), [])  # fixture has shipyard-alpha and shipyard:beta
        reg = self.load()
        reg["roles"]["alpha-role"]["agent"] = "copilot-alpha"
        write(self.root, "shipyard/registry/roles.json", reg)
        self.assertProblem("agent 'copilot-alpha' must be shipyard-<name>")

    def test_contract_major_mismatch(self):
        reg = self.load()
        reg["roles"]["alpha-role"]["contract"] = "reviewer-result@2"
        write(self.root, "shipyard/registry/roles.json", reg)
        self.assertProblem("is version 1.")

    def test_missing_registry(self):
        os.remove(os.path.join(self.root, "shipyard", "registry", "roles.json"))
        self.assertProblem("shipyard/registry/roles.json: missing")


class Extensions(CheckTestCase):
    def test_forbidden_calls(self):
        for snippet, label in (("  const t = Date.now();", "Date.now"), ("  const r = Math.random();", "Math.random"),
                               ("  const d = new Date();", "new Date()"), ("  const fs = require('fs');", "require()"),
                               ("  const e = process.env.HOME;", "process.env"), ("  await fetch('https://x');", "fetch()")):
            with self.subTest(label=label):
                write(self.root, ".github/extensions/demo/extension.mjs", extension_source(extra=snippet))
                self.assertProblem("uses %s" % label)

    def test_fs_import_in_a_workflow_is_forbidden_but_fine_in_the_lib(self):
        write(self.root, ".github/extensions/demo/extension.mjs",
              "import { readFileSync } from 'node:fs';\n" + extension_source())
        problems = "\n".join(self.problems())
        self.assertIn("uses node fs", problems)
        self.assertIn("import of 'node:fs'", problems)
        self.assertNotIn("shipyard-lib/index.mjs", problems)

    def test_lib_must_not_use_clock_or_network(self):
        write(self.root, ".github/extensions/shipyard-lib/index.mjs",
              "export const t = Date.now();\nimport http from 'node:http';\n")
        problems = "\n".join(self.problems())
        self.assertIn(".github/extensions/shipyard-lib/index.mjs:1: uses Date.now", problems)
        self.assertIn("uses a network or process builtin", problems)

    def test_mentions_in_comments_are_fine(self):
        write(self.root, ".github/extensions/demo/extension.mjs", extension_source(extra="  // never call Date.now() or require() here"))
        self.assertEqual(self.problems(), [])

    def test_must_export_and_define_workflow(self):
        write(self.root, ".github/extensions/demo/extension.mjs", "const x = 1;\n")
        problems = "\n".join(self.problems())
        self.assertIn("must `export` the workflow", problems)
        self.assertIn("must call defineWorkflow({ meta, run })", problems)

    def test_meta_name_equals_folder(self):
        write(self.root, ".github/extensions/demo/extension.mjs", extension_source(name="other"))
        self.assertProblem("meta.name must be 'demo' (the folder name)")

    def test_missing_extension_file(self):
        os.makedirs(os.path.join(self.root, ".github", "extensions", "empty"))
        self.assertProblem(".github/extensions/empty/extension.mjs: missing")

    def test_only_lib_and_sdk_imports(self):
        write(self.root, ".github/extensions/demo/extension.mjs",
              "import x from 'left-pad';\nimport { joinSession } from '@github/copilot-sdk/extension';\n" + extension_source())
        problems = "\n".join(self.problems())
        self.assertIn("import of 'left-pad'", problems)
        self.assertNotIn("import of '@github/copilot-sdk/extension'", problems)


class HeroDiagram(CheckTestCase):
    def test_readme_must_match_hero(self):
        write(self.root, "docs/diagrams/01-hero.mmd", "flowchart LR\n  A --> B\n")
        write(self.root, "README.md", "# X\n\n```mermaid\nflowchart LR\n  A --> B\n```\n")
        self.assertEqual(self.problems(), [])
        write(self.root, "README.md", "# X\n\n```mermaid\nflowchart LR\n  A --> C\n```\n")
        self.assertProblem("differs from docs/diagrams/01-hero.mmd")


# ================================================================ phase gates, PR checks, env

class ProjectTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def phase(self, name):
        problems = []
        check.check_phase(self.project, name, problems)
        return problems

    def state(self):
        with open(os.path.join(self.project, ".ai", "state.json")) as fh:
            return json.load(fh)

    def set_state(self, **changes):
        s = self.state()
        s.update(changes)
        write(self.project, ".ai/state.json", s)

    def assertProblemIn(self, problems, fragment):
        self.assertTrue(any(fragment in p for p in problems), "expected %r in %s" % (fragment, problems))


class PhaseGates(ProjectTestCase):
    def test_full_project_passes_every_phase(self):
        make_project(self.project)
        for name in check.PHASES:
            with self.subTest(phase=name):
                self.assertEqual(self.phase(name), [])

    def test_cli(self):
        make_project(self.project)
        proc = run_script("check.py", "--phase", "MERGE", "--project", self.project)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("check.py --phase MERGE: OK", proc.stdout)
        proc = run_script("check.py", "--phase", "P4", cwd=self.project)  # default project = cwd
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_p0_needs_state_and_project_md(self):
        self.assertProblemIn(self.phase("P0"), ".ai/state.json: missing")
        make_project(self.project)
        os.remove(os.path.join(self.project, ".ai", "PROJECT.md"))
        self.assertProblemIn(self.phase("P0"), ".ai/PROJECT.md: missing")
        self.set_state(status="WEIRD")
        self.assertProblemIn(self.phase("P0"), "status 'WEIRD' is not one of")
        self.set_state(status="INTAKE", featureBranch="main")
        self.assertProblemIn(self.phase("P0"), "featureBranch 'main' is protected")

    def test_state_without_optional_keys_is_fine(self):
        make_project(self.project, gates=[])
        s = self.state()
        del s["gates"]
        del s["activeRole"]
        write(self.project, ".ai/state.json", s)
        self.assertEqual(self.phase("P0"), [])
        self.assertProblemIn(self.phase("P4"), "P4 gate not recorded")

    def test_p4_needs_discovery_artifacts_and_the_gate(self):
        make_project(self.project, gates=[])
        problems = self.phase("P4")
        self.assertProblemIn(problems, "P4 gate not recorded")
        os.remove(os.path.join(self.project, ".ai", "ARCHITECTURE.md"))
        self.assertProblemIn(self.phase("P4"), ".ai/ARCHITECTURE.md: missing")
        # the phase log in PROJECT.md is accepted as the older record
        write(self.project, ".ai/PROJECT.md", "# demo\n\n## Phase log\n| P4 | questions answered 2026-01-01 |\n")
        self.assertEqual([p for p in self.phase("P4") if "P4 gate" in p], [])

    def test_p8_needs_the_plan_and_the_gate(self):
        make_project(self.project, gates=[{"gate": "P4"}])
        self.assertProblemIn(self.phase("P8"), "P8 gate not recorded")
        # DELIVERY_PLAN.md's human gates section is accepted
        make_project(tempfile.mkdtemp(dir=self.project), gates=[{"gate": "P4"}])
        write(self.project, ".ai/DELIVERY_PLAN.md", "# plan\n\n## Human gates\n- P8 plan approval: approved 2026-01-02.\n")
        self.assertEqual(self.phase("P8"), [])
        os.remove(os.path.join(self.project, ".ai", "DELIVERY_PLAN.md"))
        self.assertProblemIn(self.phase("P8"), ".ai/DELIVERY_PLAN.md: missing")

    def test_slice_needs_an_approved_active_slice_with_touch_sets(self):
        make_project(self.project)
        self.set_state(activeSlice=None)
        self.assertProblemIn(self.phase("SLICE"), "activeSlice is not set")
        self.set_state(activeSlice="02", sliceBranch="feature/demo-slice-02")
        self.assertProblemIn(self.phase("SLICE"), ".ai/slices/02/SLICE.md: missing")
        self.set_state(activeSlice="01", sliceBranch="feature/demo-slice-01")
        from fixture_tree import SLICE_MD
        write(self.project, ".ai/slices/01/SLICE.md", SLICE_MD.format(sid="01", state="PROPOSED", branch="feature/demo-slice-01"))
        self.assertProblemIn(self.phase("SLICE"), "State is PROPOSED; the slice must be APPROVED")
        write(self.project, ".ai/slices/01/SLICE.md", SLICE_MD.format(sid="01", state="MERGED", branch="feature/demo-slice-01"))
        self.assertProblemIn(self.phase("SLICE"), "State is MERGED")
        write(self.project, ".ai/slices/01/SLICE.md", SLICE_MD.format(sid="01", state="APPROVED", branch="feature/demo-slice-09"))
        self.assertProblemIn(self.phase("SLICE"), "## Branch says 'feature/demo-slice-09' but state.json sliceBranch is 'feature/demo-slice-01'")
        write(self.project, ".ai/slices/01/SLICE.md", "# Slice 01\nState: APPROVED\n\n## Expected touch set — code\n- src/\n")
        self.assertProblemIn(self.phase("SLICE"), "no '## Expected touch set — tests' section")

    def test_slice_checks_the_plan_table(self):
        make_project(self.project, plan_state="PROPOSED")
        self.assertProblemIn(self.phase("SLICE"), "slice 01 is PROPOSED in the slice table")

    def test_merge_needs_gate_evidence_findings_and_approved_plan(self):
        make_project(self.project, gates=[{"gate": "P4"}, {"gate": "P8"}, {"gate": "TEST_PLAN", "slice": "01", "at": "2026-01-03T10:00:00Z"}])
        self.assertProblemIn(self.phase("MERGE"), "MERGE gate not recorded for slice 01")
        # a MERGE gate for another slice does not count
        self.set_state(gates=self.state()["gates"] + [{"gate": "MERGE", "slice": "02"}])
        self.assertProblemIn(self.phase("MERGE"), "MERGE gate not recorded for slice 01")
        self.set_state(gates=self.state()["gates"] + [{"gate": "MERGE", "slice": "01", "by": "me"}])
        self.assertEqual(self.phase("MERGE"), [])
        os.remove(os.path.join(self.project, ".ai", "slices", "01", "EVIDENCE.md"))
        self.assertProblemIn(self.phase("MERGE"), "EVIDENCE.md: missing")
        os.remove(os.path.join(self.project, ".ai", "slices", "01", "findings", "code-reviewer.md"))
        self.assertProblemIn(self.phase("MERGE"), "findings/: no findings file")
        write(self.project, ".ai/slices/01/TEST_PLAN.md", "Status: DRAFT\n")
        self.assertProblemIn(self.phase("MERGE"), "TEST_PLAN.md: Status is DRAFT, not APPROVED")

    def test_merge_gate_from_delivery_plan_text(self):
        make_project(self.project, gates=[{"gate": "P4"}, {"gate": "P8"}, {"gate": "TEST_PLAN", "slice": "01", "at": "2026-01-03T10:00:00Z"}],
                     plan_gates="- P8 plan approval: approved 2026-01-02.\n- Merge of slice 01 into `feature/demo`: approved 2026-01-05.")
        self.assertEqual(self.phase("MERGE"), [])

    def test_merge_refuses_a_test_plan_approved_after_the_first_code_commit(self):
        make_project(self.project, gates=[{"gate": "P4"}, {"gate": "P8"},
                                          {"gate": "TEST_PLAN", "slice": "01", "at": "2026-01-04T12:00:00Z"},
                                          {"gate": "MERGE", "slice": "01"}])
        self.assertProblemIn(self.phase("MERGE"), "TEST_PLAN.md was APPROVED after the first code commit")

    def test_merge_without_any_approval_time_evidence_is_refused(self):
        make_project(self.project, gates=[{"gate": "P4"}, {"gate": "P8"}, {"gate": "MERGE", "slice": "01"}])
        self.assertProblemIn(self.phase("MERGE"), "cannot show that TEST_PLAN.md was APPROVED before the first code commit")

    def test_merge_accepts_git_history_of_a_committed_test_plan(self):
        make_project(self.project, gates=[{"gate": "P4"}, {"gate": "P8"}, {"gate": "MERGE", "slice": "01"}])
        # cloud mode: .ai/ is committed on the slice branch; the approval commit predates the code commit
        git(self.project, "checkout", "-q", "feature/demo")
        git(self.project, "checkout", "-q", "-b", "feature/demo-slice-01b")
        write(self.project, ".ai/slices/01/TEST_PLAN.md", "Status: APPROVED\n# Test plan\n")
        git(self.project, "add", "-f", ".ai/slices/01/TEST_PLAN.md")
        git(self.project, "commit", "-q", "-m", "test plan approved",
            env={"GIT_AUTHOR_DATE": "2026-01-03T10:00:00Z", "GIT_COMMITTER_DATE": "2026-01-03T10:00:00Z"})
        write(self.project, "src/app.py", "print('later')\n")
        git(self.project, "add", "src")
        git(self.project, "commit", "-q", "-m", "slice 01 round 0: code",
            env={"GIT_AUTHOR_DATE": "2026-01-04T10:00:00Z", "GIT_COMMITTER_DATE": "2026-01-04T10:00:00Z"})
        self.set_state(sliceBranch="feature/demo-slice-01b")
        from fixture_tree import SLICE_MD
        write(self.project, ".ai/slices/01/SLICE.md", SLICE_MD.format(sid="01", state="HUMAN_REVIEW", branch="feature/demo-slice-01b"))
        self.assertEqual(self.phase("MERGE"), [])

    def test_merge_without_a_code_commit(self):
        make_project(self.project)
        git(self.project, "reset", "-q", "--hard", "feature/demo")
        write(self.project, ".ai/slices/01/TEST_PLAN.md", "Status: APPROVED\n")  # .ai/ is untracked, restore it
        self.assertProblemIn(self.phase("MERGE"), "no code commit found on feature/demo-slice-01")


class PullRequest(ProjectTestCase):
    def pr(self, base=None, head=None):
        problems = []
        check.check_pr(self.project, base, head, problems)
        return problems

    def test_clean_diff_inside_touch_sets(self):
        make_project(self.project)
        self.assertEqual(self.pr(), [])
        self.assertEqual(self.pr("feature/demo", "feature/demo-slice-01"), [])

    def test_file_outside_touch_sets(self):
        make_project(self.project)
        write(self.project, "src/other/thing.py", "x = 1\n")
        git(self.project, "add", "src")
        git(self.project, "commit", "-q", "-m", "drift")
        self.assertProblemIn(self.pr(), "src/other/thing.py is outside slice 01's touch sets")
        write(self.project, "src/lib/ok.py", "x = 1\n")  # a directory entry in the touch set covers its children
        git(self.project, "add", "src")
        git(self.project, "commit", "-q", "-m", "inside")
        self.assertEqual([p for p in self.pr() if "ok.py" in p], [])

    def test_ai_in_diff(self):
        make_project(self.project)
        git(self.project, "add", "-f", ".ai/state.json")
        git(self.project, "commit", "-q", "-m", "oops")
        problems = self.pr()
        self.assertProblemIn(problems, ".ai/state.json must never enter a work branch")
        self.assertEqual([p for p in problems if "outside" in p], [])

    def test_missing_evidence_and_findings(self):
        make_project(self.project)
        os.remove(os.path.join(self.project, ".ai", "slices", "01", "EVIDENCE.md"))
        os.remove(os.path.join(self.project, ".ai", "slices", "01", "findings", "code-reviewer.md"))
        problems = self.pr()
        self.assertProblemIn(problems, "EVIDENCE.md is missing")
        self.assertProblemIn(problems, "findings/ has no findings file")

    def test_cli(self):
        make_project(self.project)
        proc = run_script("check.py", "--pr", "--project", self.project, "--base", "feature/demo")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = run_script("check.py", "--pr", "--project", self.project, "--base", "nope")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("git diff nope...HEAD failed", proc.stdout)


class Env(unittest.TestCase):
    def test_env_prints_the_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(tmp)
            proc = run_script("check.py", "--env", "--root", root, "--project", root)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for word in ("guardrail matrix", "write-scope", "goldfish-blinders", "CLI", "cloud coding agent", "IDE",
                         "dynamic workflows:   demo", ".ai/state.json:      .ai/state.json: missing", "--experimental"):
                self.assertIn(word, proc.stdout)


if __name__ == "__main__":
    unittest.main()

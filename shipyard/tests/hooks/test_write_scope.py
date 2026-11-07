import os
import unittest

from helpers import SLICE_MD_HYPHEN, HookTestCase

C = "shipyard:coordinator"
I = "shipyard:implementer"
V = "shipyard:verifier"
CR = "shipyard:code-reviewer"
PLAN = ".ai/slices/01/TEST_PLAN.md"


class Base(HookTestCase):
    script = "write-scope.py"

    def write(self, agent, path, content="x\n"):
        return self.run_tool(agent, "Write", {"file_path": path, "content": content})

    def edit(self, agent, path, old, new, **extra):
        ti = {"file_path": path, "old_string": old, "new_string": new}
        ti.update(extra)
        return self.run_tool(agent, "Edit", ti)

    def abs(self, rel):
        return os.path.join(self.repo.path, rel)


class PassThroughAndOutside(Base):
    def test_non_shipyard_passthrough(self):
        self.assertAllowed(self.write(None, "/etc/whatever"))
        self.assertAllowed(self.write("general-purpose", "/etc/whatever"))

    def test_outside_project_denied(self):
        for agent in (C, I, V, CR):
            self.assertDenied(self.write(agent, "/tmp/elsewhere/file.txt"), "outside the project")
            self.assertDenied(self.write(agent, "../escape.txt"), "outside the project")

    def test_unknown_shipyard_agent_denied(self):
        self.assertDenied(self.write("shipyard:intruder", self.abs(".ai/x.md")), "unknown Shipyard agent")


class Coordinator(Base):
    def test_ai_allowed_gitignore_denied(self):
        for rel in (".ai/PROJECT.md", ".ai/state.json", ".ai/slices/01/EVIDENCE.md"):
            self.assertAllowed(self.write(C, self.abs(rel)))
        self.assertDenied(self.write(C, self.abs(".gitignore")), "coordinator writes only")

    def test_relative_path_allowed(self):
        self.assertAllowed(self.write(C, ".ai/PLAN.HUMAN.md"))

    def test_code_denied(self):
        self.assertDenied(self.write(C, self.abs("src/cache/a.ts")), "implementer")
        self.assertDenied(self.write(C, self.abs("sub/.gitignore")), "coordinator writes only")

    def test_coordinator_cannot_approve_test_plan(self):
        self.assertDenied(self.write(C, self.abs(PLAN), "# p\nStatus: APPROVED\n"), "code-reviewer")
        self.assertDenied(self.edit(C, self.abs(PLAN), "Status: DRAFT", "Status: APPROVED"), "code-reviewer")

    def test_coordinator_other_plan_edit_allowed(self):
        self.assertAllowed(self.edit(C, self.abs(PLAN), "| AC1 |", "| AC-1 |"))


class Discovery(Base):
    A = "shipyard:discovery"

    def test_allowed(self):
        self.assertAllowed(self.write(self.A, self.abs(".ai/planning/discovery.md")))
        self.assertAllowed(self.write(self.A, self.abs(".ai/PROJECT.md")))
        self.assertAllowed(self.write(self.A, self.abs(".ai/GLOSSARY.md")))

    def test_denied(self):
        for rel in (".ai/ARCHITECTURE.md", ".ai/INVARIANTS.md", ".ai/state.json", ".ai/slices/01/SLICE.md",
                    "src/a.ts"):
            self.assertDenied(self.write(self.A, self.abs(rel)))


class Goldfish(Base):
    def test_everything_denied(self):
        for rel in (".ai/planning/goldfish.md", "notes.md"):
            self.assertDenied(self.write("shipyard:goldfish", self.abs(rel)), "goldfish writes nothing")


class Architect(Base):
    A = "shipyard:architect"

    def test_allowed(self):
        for rel in (".ai/ARCHITECTURE.md", ".ai/INVARIANTS.md", ".ai/decisions/ADR-001.md",
                    ".ai/planning/architect.md", ".ai/slices/01/findings/architect.md",
                    ".ai/formal/INV-003.qnt", ".ai/formal/INV-003.trace.itf.json"):
            self.assertAllowed(self.write(self.A, self.abs(rel)))

    def test_denied(self):
        for rel in (".ai/PROJECT.md", ".ai/planning/discovery.md", ".ai/state.json", ".ai/GLOSSARY.md", "src/a.ts"):
            self.assertDenied(self.write(self.A, self.abs(rel)), "shipyard:architect may write only")

    def test_formal_models_are_the_architects(self):
        for agent in ("shipyard:discovery", "shipyard:planner", "shipyard:reliability-reviewer", "shipyard:verifier"):
            self.assertDenied(self.write(agent, self.abs(".ai/formal/INV-003.qnt")))


class Planner(Base):
    A = "shipyard:planner"

    def test_allowed(self):
        for rel in (".ai/DELIVERY_PLAN.md", ".ai/slices/02/SLICE.md", ".ai/planning/planner.md"):
            self.assertAllowed(self.write(self.A, self.abs(rel)))

    def test_denied(self):
        for rel in (PLAN, ".ai/state.json", ".ai/ARCHITECTURE.md", "src/a.ts"):
            self.assertDenied(self.write(self.A, self.abs(rel)), "shipyard:planner may write only")


class Reviewers(Base):
    def test_own_findings_allowed(self):
        for name in ("code", "security", "contract", "integration", "reliability", "simplicity"):
            agent = "shipyard:%s-reviewer" % name
            for rel in (".ai/slices/01/findings/%s-reviewer.md" % name,
                        ".ai/slices/01/findings/%s-reviewer.test-plan.md" % name,
                        ".ai/planning/%s-reviewer.md" % name):
                self.assertAllowed(self.write(agent, self.abs(rel)))

    def test_other_files_denied(self):
        a = "shipyard:security-reviewer"
        for rel in (".ai/slices/01/findings/code-reviewer.md", ".ai/PROJECT.md", "src/cache/a.ts", PLAN):
            self.assertDenied(self.write(a, self.abs(rel)), "own findings files")


class CodeReviewerStatusFlip(Base):
    def test_exact_flip_allowed(self):
        self.assertAllowed(self.edit(CR, self.abs(PLAN), "Status: DRAFT", "Status: APPROVED"))

    def test_other_edits_denied(self):
        self.assertDenied(self.edit(CR, self.abs(PLAN), "| AC1 |", "| AC9 |"), "exactly one change")
        self.assertDenied(self.edit(CR, self.abs(PLAN), "Status: DRAFT", "Status: APPROVED\nextra"),
                          "exactly one change")
        self.assertDenied(self.edit(CR, self.abs(PLAN), "Status: DRAFT", "Status: APPROVED", replace_all=True),
                          "exactly one change")
        self.assertDenied(self.write(CR, self.abs(PLAN), "Status: APPROVED\n"), "exactly one change")
        self.assertDenied(self.run_tool(CR, "MultiEdit", {"file_path": self.abs(PLAN), "edits": [
            {"old_string": "Status: DRAFT", "new_string": "Status: APPROVED"}]}), "exactly one change")

    def test_flip_only_on_active_slice(self):
        self.repo.set_plan("DRAFT", slice_id="02")
        self.assertDenied(self.edit(CR, self.abs(".ai/slices/02/TEST_PLAN.md"), "Status: DRAFT",
                                    "Status: APPROVED"), "active slice")

    def test_flip_needs_draft_status(self):
        self.repo.set_plan("APPROVED")
        self.assertDenied(self.edit(CR, self.abs(PLAN), "Status: DRAFT", "Status: APPROVED"), "Status: DRAFT")

    def test_other_reviewer_cannot_flip(self):
        self.assertDenied(self.edit("shipyard:security-reviewer", self.abs(PLAN), "Status: DRAFT",
                                    "Status: APPROVED"), "own findings files")


class Implementer(Base):
    def test_code_touch_set_allowed(self):
        self.assertAllowed(self.write(I, self.abs("src/cache/store.ts")))
        self.assertAllowed(self.write(I, self.abs("src/cache/deep/nested/x.ts")))
        self.assertAllowed(self.write(I, "src/config/cache.ts"))
        self.assertAllowed(self.edit(I, self.abs("src/cache/store.ts"), "a", "b"))
        self.assertAllowed(self.run_tool(I, "NotebookEdit", {"notebook_path": self.abs("src/cache/n.ipynb"),
                                                             "new_source": "x"}))

    def test_tests_denied_and_test_set_wins_on_overlap(self):
        self.assertDenied(self.write(I, self.abs("tests/cache/store.test.ts")), "verifier")
        self.assertDenied(self.write(I, self.abs("src/cache/store.test.ts")), "test touch set")

    def test_outside_code_set_denied(self):
        self.assertDenied(self.write(I, self.abs("src/other.ts")), "outside slice 01's code touch set")
        self.assertDenied(self.write(I, self.abs("src/config/other.ts")), "outside")

    def test_ai_denied(self):
        self.assertDenied(self.write(I, self.abs(".ai/slices/01/notes.md")), "never writes .ai")

    def test_missing_state(self):
        self.repo.remove(".ai/state.json")
        self.assertDenied(self.write(I, self.abs("src/cache/a.ts")), ".ai/state.json is missing")

    def test_no_active_slice(self):
        self.repo.set_state(activeSlice=None, sliceBranch=None)
        self.assertDenied(self.write(I, self.abs("src/cache/a.ts")), "no activeSlice")

    def test_missing_slice_md(self):
        self.repo.remove(".ai/slices/01/SLICE.md")
        self.assertDenied(self.write(I, self.abs("src/cache/a.ts")), ".ai/slices/01/SLICE.md is missing")

    def test_missing_touch_set_section(self):
        self.repo.write(".ai/slices/01/SLICE.md", "# s\n## Expected touch set — code\n- src/**\n")
        self.assertDenied(self.write(I, self.abs("src/a.ts")), "tests")

    def test_hyphen_headings_accepted(self):
        self.repo.write(".ai/slices/01/SLICE.md", SLICE_MD_HYPHEN)
        self.assertAllowed(self.write(I, self.abs("lib/a.py")))
        self.assertDenied(self.write(I, self.abs("spec/a_spec.py")), "verifier")


class Verifier(Base):
    def test_test_touch_set_allowed(self):
        self.assertAllowed(self.write(V, self.abs("tests/cache/store.test.ts")))
        self.assertAllowed(self.write(V, self.abs("src/cache/store.test.ts")))

    def test_code_denied(self):
        self.assertDenied(self.write(V, self.abs("src/cache/store.ts")), "never writes production code")

    def test_test_plan_draft_allowed(self):
        self.assertAllowed(self.write(V, self.abs(PLAN), "# plan\nStatus: DRAFT\n"))
        self.assertAllowed(self.edit(V, self.abs(PLAN), "| AC1 |", "| AC1 (rev) |"))

    def test_verifier_cannot_set_approved(self):
        self.assertDenied(self.write(V, self.abs(PLAN), "# plan\nStatus: APPROVED\n"), "may not write")
        self.assertDenied(self.edit(V, self.abs(PLAN), "Status: DRAFT", "Status: APPROVED"), "may not write")
        self.assertDenied(self.edit(V, self.abs(PLAN), "DRAFT", "APPROVED"), "may not write")
        self.assertDenied(self.run_tool(V, "MultiEdit", {"file_path": self.abs(PLAN), "edits": [
            {"old_string": "DRAFT", "new_string": "APPROV"}, {"old_string": "APPROV", "new_string": "APPROVED"}]}),
            "may not write")

    def test_findings_file_allowed_other_ai_denied(self):
        self.assertAllowed(self.write(V, self.abs(".ai/slices/01/findings/verifier.md")))
        self.assertDenied(self.write(V, self.abs(".ai/PROJECT.md")), "may write only")
        self.assertDenied(self.write(V, self.abs(".ai/slices/02/TEST_PLAN.md")), "may write only")

    def test_missing_state(self):
        self.repo.remove(".ai/state.json")
        self.assertDenied(self.write(V, self.abs("tests/cache/a.test.ts")), ".ai/state.json is missing")


class BashWrites(Base):
    """The write table applies to what a Bash command visibly writes."""

    def test_author_cannot_flip_or_touch_ai_via_bash(self):
        for agent in (I, V):
            self.assertDenied(self.bash(agent, "sed -i s/DRAFT/APPROVED/ " + PLAN), "Write and Edit tools")
            self.assertDenied(self.bash(agent, "echo '{}' > .ai/state.json"))
        self.assertDenied(self.bash(CR, "printf 'Status: APPROVED' > " + PLAN), "Write and Edit tools")

    def test_bash_writes_follow_touch_sets(self):
        self.repo.set_plan("APPROVED")
        self.assertAllowed(self.bash(I, "cat > src/cache/a.ts <<EOF\nx\nEOF\n"))
        self.assertDenied(self.bash(I, "echo x > src/other.ts"), "code touch set")
        self.assertDenied(self.bash(I, "echo x > tests/cache/a.test.ts"), "verifier")
        self.assertAllowed(self.bash(V, "echo x | tee tests/cache/b.test.ts"))
        self.assertDenied(self.bash(V, "cp tests/cache/b.test.ts src/cache/b.ts"), "test touch set")
        self.assertDenied(self.bash(I, "rm README.md"), "code touch set")

    def test_outside_project_and_sinks_allowed(self):
        self.assertAllowed(self.bash(I, "npm test > /tmp/out.log 2>&1"))
        self.assertAllowed(self.bash(V, "pytest -q 2>/dev/null | tee /tmp/t.log"))

    def test_nobody_writes_git_dir(self):
        for agent in (C, I, V):
            self.assertDenied(self.bash(agent, "echo abc > .git/refs/heads/main"), ".git/")

    def test_coordinator_bash_follows_table(self):
        self.assertDenied(self.bash(C, "echo '.ai/' >> .gitignore"), "coordinator writes only")
        self.assertAllowed(self.bash(C, "mkdir -p .ai/slices/02 && touch .ai/slices/02/EVIDENCE.md"))
        self.assertDenied(self.bash(C, "echo x > src/cache/a.ts"), "coordinator writes only")


class BashGaps(Base):
    """Gaps found by the second review."""

    def test_writes_after_cd_denied(self):
        self.repo.set_plan("APPROVED")
        self.assertDenied(self.bash(V, "cd tests && sed -i s/a/b/ ../.ai/slices/01/TEST_PLAN.md"), "after a `cd`")
        self.assertDenied(self.bash(I, "cd src && echo x > ../tests/cache/a.test.ts"), "after a `cd`")
        self.assertAllowed(self.bash(I, "cd src && npm test > /tmp/o.log"))

    def test_relative_escape_denied(self):
        self.assertDenied(self.bash(I, "echo x > ../elsewhere.txt"), "leaves the project")

    def test_opaque_writers_denied(self):
        for cmd in ("git apply fix.patch", "patch -p1 < fix.patch", "git stash pop", "tar xzf f.tgz",
                    "unzip f.zip", "curl -O https://example.com/x", "wget https://example.com/x"):
            self.assertDenied(self.bash(I, cmd), "cannot see")
        for cmd in ("git apply --check fix.patch", "tar xzf f.tgz -C /tmp/x", "unzip f.zip -d /tmp/x",
                    "curl -s https://example.com/x -o /tmp/x", "wget -O - https://example.com/x"):
            self.assertAllowed(self.bash(I, cmd))

    def test_curl_output_into_repo_is_a_write(self):
        self.repo.set_plan("APPROVED")
        self.assertDenied(self.bash(I, "curl -s https://example.com/x -o README.md"), "code touch set")


class FrozenPlan(Base):
    def test_verifier_cannot_edit_approved_plan(self):
        self.repo.set_plan("APPROVED")
        self.assertDenied(self.edit(V, self.abs(PLAN), "| AC1 |", "| AC9 |"), "frozen")
        self.assertDenied(self.write(V, self.abs(PLAN), "# p\nStatus: APPROVED\n"), "Status: APPROVED")

    def test_verifier_may_reset_approved_plan_to_draft(self):
        self.repo.set_plan("APPROVED")
        self.assertAllowed(self.write(V, self.abs(PLAN), "> banner\nStatus: DRAFT\n\n| AC | Test |\n"))

    def test_verifier_edits_draft_plan(self):
        self.assertAllowed(self.edit(V, self.abs(PLAN), "| AC1 |", "| AC-1 |"))


if __name__ == "__main__":
    unittest.main()

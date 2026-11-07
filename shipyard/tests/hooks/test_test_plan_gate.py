import os
import unittest

from helpers import BANNER, HookTestCase

I = "shipyard:implementer"
V = "shipyard:verifier"


class TestPlanGate(HookTestCase):
    script = "test-plan-gate.py"

    def write(self, agent, rel, tool="Write"):
        ti = {"file_path": os.path.join(self.repo.path, rel)}
        ti.update({"content": "x"} if tool == "Write" else {"old_string": "a", "new_string": "b"})
        return self.run_tool(agent, tool, ti)

    def test_non_shipyard_passthrough(self):
        self.assertAllowed(self.write(None, "src/cache/a.ts"))

    def test_other_shipyard_agents_not_gated(self):
        self.assertAllowed(self.write("shipyard:coordinator", ".ai/PROJECT.md"))
        self.assertAllowed(self.write("shipyard:code-reviewer", "src/cache/a.ts"))

    def test_draft_blocks_code_and_tests(self):
        for tool in ("Write", "Edit", "MultiEdit"):
            self.assertDenied(self.write(I, "src/cache/a.ts", tool), "Status: DRAFT", "TEST_PLAN.md")
            self.assertDenied(self.write(V, "tests/cache/a.test.ts", tool), "not approved")

    def test_approved_allows(self):
        self.repo.set_plan("APPROVED")
        self.assertAllowed(self.write(I, "src/cache/a.ts"))
        self.assertAllowed(self.write(V, "tests/cache/a.test.ts", "Edit"))

    def test_ai_writes_not_gated(self):
        self.assertAllowed(self.write(V, ".ai/slices/01/TEST_PLAN.md"))

    def test_missing_plan_blocks(self):
        self.repo.remove(".ai/slices/01/TEST_PLAN.md")
        self.assertDenied(self.write(I, "src/cache/a.ts"), "does not exist")

    def test_status_line_must_be_in_first_10_lines(self):
        self.repo.write(".ai/slices/01/TEST_PLAN.md", BANNER + "\n" + "\n" * 12 + "Status: APPROVED\n")
        self.assertDenied(self.write(I, "src/cache/a.ts"), "first 10 lines")

    def test_status_line_with_trailing_space(self):
        self.repo.write(".ai/slices/01/TEST_PLAN.md", BANNER + "\nStatus: APPROVED  \n")
        self.assertAllowed(self.write(I, "src/cache/a.ts"))

    def test_missing_state_blocks(self):
        self.repo.remove(".ai/state.json")
        self.assertDenied(self.write(I, "src/cache/a.ts"), ".ai/state.json is missing")

    def test_no_active_slice_blocks(self):
        self.repo.set_state(activeSlice=None, sliceBranch=None)
        self.assertDenied(self.write(V, "tests/cache/a.test.ts"), "no activeSlice")


class BashGate(HookTestCase):
    script = "test-plan-gate.py"

    def test_bash_writes_gated_until_approved(self):
        for agent, cmd in ((I, "cat > src/cache/a.ts <<EOF\nx\nEOF\n"), (V, "echo t | tee tests/cache/a.test.ts"),
                           (I, "sed -i s/a/b/ src/cache/a.ts")):
            self.assertDenied(self.bash(agent, cmd), "test plan first")
        self.repo.set_plan("APPROVED")
        self.assertAllowed(self.bash(I, "cat > src/cache/a.ts <<EOF\nx\nEOF\n"))

    def test_cd_and_opaque_writes_gated(self):
        self.assertDenied(self.bash(I, "cd src && echo x > cache/a.ts"), "test plan first")
        self.assertDenied(self.bash(V, "git apply tests.patch"), "test plan first")

    def test_bash_without_project_writes_not_gated(self):
        for cmd in ("npm test > /tmp/o.log", "pytest -q", "git status", "ls -la src"):
            self.assertAllowed(self.bash(I, cmd))


if __name__ == "__main__":
    unittest.main()

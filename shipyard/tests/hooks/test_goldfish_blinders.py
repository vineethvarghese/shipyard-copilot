import os
import unittest

from helpers import HookTestCase

G = "shipyard:goldfish"
D = "shipyard:discovery"


class GoldfishBlinders(HookTestCase):
    script = "goldfish-blinders.py"

    def read(self, agent, rel):
        return self.run_tool(agent, "Read", {"file_path": os.path.join(self.repo.path, rel)})

    def test_reads_of_planning_denied(self):
        for rel in (".ai/planning/concepts.md", ".ai/planning/discovery.md", ".ai/PROJECT.md", ".ai/state.json"):
            self.assertDenied(self.read(G, rel), "stays cold")

    def test_slice_spec_and_code_allowed(self):
        self.assertAllowed(self.read(G, ".ai/slices/01/SLICE.md"))
        self.assertAllowed(self.read(G, "src/cache/a.ts"))
        self.assertDenied(self.read(G, ".ai/slices/01/TEST_PLAN.md"), "stays cold")

    def test_case_folded(self):
        self.assertDenied(self.read(G, ".AI/planning/concepts.md"), "stays cold")
        self.assertDenied(self.run_tool(G, "Glob", {"pattern": ".AI/**"}), "stays cold")

    def test_other_agents_unaffected(self):
        self.assertAllowed(self.read(D, ".ai/planning/concepts.md"))

    def test_grep_and_glob(self):
        g = lambda ti: self.run_tool(G, "Grep", ti)  # noqa: E731
        self.assertDenied(g({"pattern": "x", "path": os.path.join(self.repo.path, ".ai/planning")}), "stays cold")
        self.assertDenied(g({"pattern": "x", "output_mode": "content"}), "content search")
        self.assertDenied(g({"pattern": "x", "glob": ".ai/**"}), "stays cold")
        self.assertAllowed(g({"pattern": "x"}))
        self.assertAllowed(g({"pattern": "x", "output_mode": "content", "path": os.path.join(self.repo.path, "src")}))
        gl = lambda ti: self.run_tool(G, "Glob", ti)  # noqa: E731
        self.assertDenied(gl({"pattern": ".ai/**/*.md"}), "stays cold")
        self.assertDenied(gl({"pattern": "**/.ai/*"}), "stays cold")
        self.assertAllowed(gl({"pattern": "src/**/*.ts"}))


if __name__ == "__main__":
    unittest.main()

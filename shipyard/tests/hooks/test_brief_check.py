import unittest

from helpers import HookTestCase

C = "shipyard:coordinator"


def brief(mode, round_=None, caller="Caller: shipyard:coordinator", extra=""):
    lines = [caller] if caller else []
    if mode is not None:
        lines.append("Mode: %s" % mode)
    if round_ is not None:
        lines.append("Round: %s" % round_)
    lines += ["Read: .ai/DELIVERY_PLAN.md", "Budget: 20 turns", "", "Do the thing." + extra]
    return "\n".join(lines)


class BriefCheck(HookTestCase):
    script = "brief-check.py"

    def call(self, subagent, prompt, agent=C, tool="Agent", **kw):
        return self.run_tool(agent, tool, {"subagent_type": subagent, "description": "d", "prompt": prompt}, **kw)

    def test_passthrough(self):
        self.assertAllowed(self.call("shipyard:architect", "no header", agent=None))
        self.assertAllowed(self.call("shipyard:architect", "no header", agent="shipyard:planner"))
        self.assertAllowed(self.call("general-purpose", "no header"))
        self.assertAllowed(self.call("Explore", "anything", tool="Task"))

    def test_valid_briefs(self):
        self.assertAllowed(self.call("shipyard:architect", brief("REVALIDATE")))
        self.assertAllowed(self.call("shipyard:planner", brief("RECONCILE", 0), tool="Task"))
        self.assertAllowed(self.call("shipyard:implementer", brief("FIX", 3)))
        self.assertAllowed(self.call("shipyard:verifier", brief("FIX_TESTS", 1)))
        self.assertAllowed(self.call("shipyard:code-reviewer", brief("RECHECK", 2)))
        self.assertAllowed(self.call("shipyard:discovery", brief("GRILL")))
        self.assertAllowed(self.call("shipyard:discovery", brief("ELEPHANT")))

    def test_caller_must_come_first(self):
        self.assertDenied(self.call("shipyard:architect", brief("REVALIDATE", caller=None)), "Caller:")
        self.assertDenied(self.call("shipyard:architect", "Please help.\n" + brief("REVALIDATE")), "must start")
        self.assertDenied(self.call("shipyard:architect", brief("REVALIDATE", caller="Caller: someone")), "Caller:")

    def test_mode_required_and_valid(self):
        self.assertDenied(self.call("shipyard:architect", brief(None)), "no 'Mode:")
        res = self.call("shipyard:architect", brief("PLAN"))
        self.assertDenied(res, "'Mode: PLAN' is not a mode", "REVALIDATE")
        self.assertDenied(self.call("shipyard:implementer", brief("TEST_PLAN")), "not a mode")
        self.assertDenied(self.call("shipyard:architect", brief("REVALIDATE", extra="\nMode: DRAFT")), "conflicting")

    def test_unknown_shipyard_agent(self):
        self.assertDenied(self.call("shipyard:nope", brief("FIX", 1)), "not an agent")

    def test_round_rules(self):
        self.assertDenied(self.call("shipyard:implementer", brief("FIX")), "Round:")
        self.assertDenied(self.call("shipyard:implementer", brief("FIX", 4)), "exceeds the fix-round cap of 3")
        self.assertDenied(self.call("shipyard:verifier", brief("FIX_TESTS", 9)), "cap")
        self.assertDenied(self.call("shipyard:code-reviewer", brief("RECHECK", "two")), "whole number")

    def test_registry_fallback_without_plugin_root(self):
        self.assertAllowed(self.call("shipyard:architect", brief("CONFORMANCE"), plugin_root=False))
        self.assertDenied(self.call("shipyard:architect", brief("FIX", 1), plugin_root=False), "not a mode")

    def test_missing_registry_fails_closed(self):
        res = self.call("shipyard:architect", brief("REVALIDATE"), env_extra={"CLAUDE_PLUGIN_ROOT": "/nonexistent"})
        self.assertDenied(res, "registry")


if __name__ == "__main__":
    unittest.main()

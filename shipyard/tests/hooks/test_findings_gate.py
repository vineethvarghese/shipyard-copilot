import os
import time
import unittest

from helpers import BANNER, HookTestCase

CR = "shipyard:code-reviewer"

VALID_BLOCK = BANNER + """

ID: CR-1
Severity: MAJOR
Category: clarity
Location: src/cache/store.ts:12
Finding: The eviction rule is hidden in a helper.
Why it matters: Readers miss the size bound.
Evidence: store.ts:12 calls evict() with no comment.
Required resolution: Name the bound.
Confidence: HIGH
Owner: implementer
Status: OPEN
"""

NO_FINDINGS = BANNER + "\n\nNO FINDINGS\n"


class FindingsGate(HookTestCase):
    script = "findings-gate.py"

    def stop(self, agent, **extra):
        payload = {"stop_hook_active": False, "last_assistant_message": "done"}
        payload.update(extra)
        return self.run_tool(agent, None, None, event="SubagentStop", **payload)

    def put(self, rel, text, age=0):
        p = self.repo.write(rel, text)
        if age:
            t = time.time() - age
            os.utime(p, (t, t))

    def test_non_reviewers_pass(self):
        self.assertAllowed(self.stop(None))
        self.assertAllowed(self.stop("shipyard:implementer"))
        self.assertAllowed(self.stop("shipyard:architect"))
        self.assertAllowed(self.stop("other:code-reviewer"))

    def test_missing_file_blocks(self):
        res = self.stop(CR)
        self.assertDenied(res, ".ai/slices/01/findings/code-reviewer.md", "code-reviewer.test-plan.md",
                          "before finishing")

    def test_valid_files_pass(self):
        self.put(".ai/slices/01/findings/code-reviewer.md", NO_FINDINGS)
        self.assertAllowed(self.stop(CR))
        self.put(".ai/slices/01/findings/code-reviewer.md", VALID_BLOCK)
        self.assertAllowed(self.stop(CR))

    def test_all_six_reviewers(self):
        for name in ("code", "security", "contract", "integration", "reliability", "simplicity"):
            agent = "shipyard:%s-reviewer" % name
            self.assertDenied(self.stop(agent), "%s-reviewer.md" % name)
            self.put(".ai/slices/01/findings/%s-reviewer.md" % name, NO_FINDINGS)
            self.assertAllowed(self.stop(agent))

    def test_invalid_files_block(self):
        rel = ".ai/slices/01/findings/code-reviewer.md"
        cases = {
            "banner": "NO FINDINGS\n",
            "neither": BANNER + "\nLooks fine to me.\n",
            "Evidence": VALID_BLOCK.replace("Evidence: store.ts:12 calls evict() with no comment.\n", ""),
            "Severity": VALID_BLOCK.replace("Severity: MAJOR\n", ""),
            "use BLOCKING": VALID_BLOCK.replace("Severity: MAJOR", "Severity: HUGE"),
            "empty": "",
        }
        for needle, text in cases.items():
            self.put(rel, text)
            self.assertDenied(self.stop(CR), "does not parse" if needle != "empty" else "empty", needle)

    def test_most_recent_file_is_checked(self):
        md = ".ai/slices/01/findings/code-reviewer.md"
        tp = ".ai/slices/01/findings/code-reviewer.test-plan.md"
        self.put(md, "garbage", age=100)
        self.put(tp, NO_FINDINGS)
        self.assertAllowed(self.stop(CR))
        self.put(tp, NO_FINDINGS, age=100)
        self.put(md, "garbage")
        self.assertDenied(self.stop(CR), "code-reviewer.md does not parse")

    def test_plan_mode_uses_planning_file(self):
        self.repo.set_state(activeSlice=None, sliceBranch=None)
        self.assertDenied(self.stop("shipyard:simplicity-reviewer"), ".ai/planning/simplicity-reviewer.md")
        self.put(".ai/planning/simplicity-reviewer.md", VALID_BLOCK)
        self.assertAllowed(self.stop("shipyard:simplicity-reviewer"))

    def test_plan_review_while_slice_active_uses_newest_file(self):
        # A PLAN-mode review that runs while a slice is active writes to .ai/planning/; it must be found.
        self.put(".ai/slices/01/findings/code-reviewer.md", VALID_BLOCK, age=100)
        self.put(".ai/planning/code-reviewer.md", "garbage")
        self.assertDenied(self.stop(CR), "planning/code-reviewer.md does not parse")
        self.put(".ai/planning/code-reviewer.md", NO_FINDINGS)
        self.assertAllowed(self.stop(CR))

    def test_no_state_means_not_a_shipyard_run(self):
        os.remove(os.path.join(self.repo.path, ".ai", "state.json"))
        self.assertAllowed(self.stop(CR))

    def test_stop_hook_active_rechecks_until_cap(self):
        # A reviewer that was sent back is checked again; only after MAX_BLOCKS retries is it let go.
        for _ in range(3):
            self.assertDenied(self.stop(CR, stop_hook_active=True, agent_id="cap-1"), "must write its findings")
        res = self.stop(CR, stop_hook_active=True, agent_id="cap-1")
        self.assertAllowed(res)
        self.assertIn("already sent back", res.stderr)

    def start(self, agent, agent_id):
        return self.run_tool(agent, None, None, event="SubagentStart", agent_id=agent_id)

    def test_stale_file_from_earlier_run_rejected(self):
        self.put(".ai/slices/01/findings/code-reviewer.md", VALID_BLOCK, age=300)
        self.assertAllowed(self.start(CR, "fresh-1"))
        self.assertDenied(self.stop(CR, agent_id="fresh-1"), "predates the start")
        self.put(".ai/slices/01/findings/code-reviewer.md", NO_FINDINGS)
        self.assertAllowed(self.stop(CR, agent_id="fresh-1"))

    def test_file_written_during_run_accepted(self):
        self.assertAllowed(self.start(CR, "fresh-2"))
        self.put(".ai/slices/01/findings/code-reviewer.md", VALID_BLOCK)
        self.assertAllowed(self.stop(CR, agent_id="fresh-2"))

class RebuttalMode(HookTestCase):
    script = "findings-gate.py"
    stop = FindingsGate.stop
    start = FindingsGate.start
    put = FindingsGate.put

    def transcript(self, mode):
        p = os.path.join(self.repo.path, "..", "t-%s.jsonl" % mode)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write('{"type":"user","message":{"content":"Caller: shipyard:coordinator\\nMode: %s\\nSlice: 01"}}\n' % mode)
        return os.path.realpath(p)

    def test_rebuttal_answer_needs_no_findings_file(self):
        self.put(".ai/slices/01/findings/code-reviewer.md", VALID_BLOCK, age=300)
        self.assertAllowed(self.start(CR, "reb-1"))
        self.assertAllowed(self.stop(CR, agent_id="reb-1", agent_transcript_path=self.transcript("REBUTTAL")))

    def test_rebuttal_detected_from_final_message(self):
        self.assertAllowed(self.stop(CR, agent_id="reb-2",
                                     last_assistant_message='{"findingId": "code-001", "response": "MAINTAIN_FINDING", "reason": "x"}'))

    def test_slice_mode_still_gated(self):
        self.assertDenied(self.stop(CR, agent_id="reb-3", agent_transcript_path=self.transcript("SLICE")),
                          "must write its findings")


if __name__ == "__main__":
    unittest.main()

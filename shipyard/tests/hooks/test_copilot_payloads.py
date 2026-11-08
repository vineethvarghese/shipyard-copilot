"""The hooks under GitHub Copilot: camelCase payloads, `toolArgs` as a JSON string, the role inferred from
SHIPYARD_ROLE, the payload's agent name or `.ai/state.json`, and the decision printed as JSON on stdout."""

import json
import os
import sys
import time
import unittest

import helpers
from helpers import BANNER, HookTestCase, copilot_payload, decision, run_hook

sys.path.insert(0, helpers.SCRIPTS)
import copilot_hooklib  # noqa: E402

NO_FINDINGS = BANNER + "\n\nNO FINDINGS\n"
PUSH = {"command": "git push origin feature/x"}


class RoleInference(HookTestCase):
    script = "protect-branches.py"

    def test_no_role_allows(self):
        """Default fixture: no SHIPYARD_ROLE, no activeRole in state.json, no agent name in the payload."""
        res = self.run_copilot("bash", PUSH)
        self.assertAllowed(res)

    def test_role_from_env(self):
        res = self.run_copilot("bash", PUSH, role="implementer")
        self.assertCopilotDenied(res, "`git push` is never allowed")

    def test_env_accepts_agent_name_forms(self):
        for role in ("shipyard-implementer", "shipyard:implementer", "Implementer"):
            self.assertCopilotDenied(self.run_copilot("bash", PUSH, role=role), "git push")

    def test_role_from_state_json(self):
        self.repo.set_state(activeRole="verifier")
        res = self.run_copilot("bash", PUSH)
        self.assertCopilotDenied(res, "`git push` is never allowed")

    def test_env_none_overrides_state(self):
        self.repo.set_state(activeRole="verifier")
        self.assertAllowed(self.run_copilot("bash", PUSH, role="none"))

    def test_role_from_payload_agent_name(self):
        res = self.run_copilot("bash", PUSH, agentType="shipyard-implementer", agentId="x1")
        self.assertCopilotDenied(res, "git push")
        res = self.run_copilot("bash", PUSH, agentName="shipyard:coordinator")
        self.assertCopilotDenied(res, "git push")

    def test_unknown_payload_agent_is_ignored(self):
        self.assertAllowed(self.run_copilot("bash", PUSH, agentType="general-purpose"))

    def test_env_wins_over_payload_and_state(self):
        self.repo.set_state(activeRole="verifier")
        res = self.run_copilot("bash", {"command": "git commit -m x"}, role="coordinator",
                               agentType="shipyard-implementer")
        self.assertCopilotDenied(res, "shipyard:coordinator may not commit")

    def test_unknown_state_role_fails_closed_on_writes(self):
        self.repo.set_state(activeRole="janitor")
        res = self.run_copilot("create", {"path": "src/cache/a.ts", "content": "x"}, script="write-scope.py")
        self.assertCopilotDenied(res, "unknown Shipyard agent 'shipyard:janitor'")

    def test_project_found_from_subfolder_cwd(self):
        self.repo.set_state(activeRole="implementer")
        sub = os.path.join(self.repo.path, "src", "deep")
        os.makedirs(sub, exist_ok=True)
        payload = copilot_payload("bash", PUSH, sub)
        res = run_hook("protect-branches.py", payload, self.repo.path, project_env=False)
        self.assertCopilotDenied(res, "git push")

    def test_claude_shaped_payload_with_env_role(self):
        """A snake_case payload (Copilot's PascalCase mode or Claude Code) without a Shipyard agent_type still
        engages when SHIPYARD_ROLE is set; the refusal uses the exit-code path, no JSON."""
        res = self.run_tool(None, "Bash", PUSH, env_extra={"SHIPYARD_ROLE": "implementer"})
        self.assertDenied(res, "git push")
        self.assertEqual(res.stdout.strip(), "")
        self.assertAllowed(self.run_tool(None, "Bash", PUSH))

    def test_bad_input_allows(self):
        res = run_hook("protect-branches.py", None, self.repo.path, raw="not json", env_extra={"SHIPYARD_ROLE": "implementer"})
        self.assertAllowed(res)


class ShellPayloads(HookTestCase):
    script = "protect-branches.py"

    def test_push_denied_with_json_decision_and_exit_2(self):
        res = self.run_copilot("bash", PUSH, role="implementer")
        d = self.assertCopilotDenied(res, "`git push` is never allowed for Shipyard agents")
        self.assertTrue(d["permissionDecisionReason"].startswith("Shipyard protect-branches blocked this"))
        self.assertEqual(len(res.stdout.strip().splitlines()), 1, "exactly one JSON line on stdout")

    def test_tool_args_as_object(self):
        res = self.run_copilot("bash", PUSH, role="implementer", args_as="object")
        self.assertCopilotDenied(res, "git push")

    def test_tool_args_raw_string_for_shell(self):
        payload = copilot_payload("bash", {}, self.repo.path)
        payload["toolArgs"] = "git push origin main"
        res = run_hook("protect-branches.py", payload, self.repo.path, env_extra={"SHIPYARD_ROLE": "implementer"},
                       project_env=False)
        self.assertCopilotDenied(res, "git push")

    def test_shell_aliases(self):
        for name in ("shell", "powershell", "run_in_terminal", "runCommands", "execute"):
            with self.subTest(tool=name):
                self.assertCopilotDenied(self.run_copilot(name, PUSH, role="implementer"), "git push")

    def test_read_only_commands_allowed(self):
        self.assertAllowed(self.run_copilot("bash", {"command": "git status && git log -3"}, role="implementer"))

    def test_readonly_bash_for_reviewer(self):
        res = self.run_copilot("shell", {"command": "rm -rf build"}, role="code-reviewer", script="readonly-bash.py")
        self.assertCopilotDenied(res, "read-only commands only", "`rm`")
        self.assertAllowed(self.run_copilot("shell", {"command": "npm test"}, role="code-reviewer",
                                            script="readonly-bash.py"))


class WritePayloads(HookTestCase):
    script = "write-scope.py"

    def test_outside_touch_set_denied(self):
        res = self.run_copilot("create", {"path": "docs/notes.md", "content": "hi"}, role="implementer")
        d = self.assertCopilotDenied(res, "'docs/notes.md' is outside slice 01's code touch set")
        self.assertEqual(d["permissionDecision"], "deny")

    def test_inside_touch_set_allowed(self):
        self.assertAllowed(self.run_copilot("create", {"path": "src/cache/store.ts", "content": "x"},
                                            role="implementer"))
        self.assertAllowed(self.run_copilot("edit", {"path": "src/cache/store.ts", "old_str": "a", "new_str": "b"},
                                            role="implementer"))

    def test_implementer_never_writes_tests_or_ai(self):
        self.assertCopilotDenied(self.run_copilot("create", {"path": "tests/cache/a.test.ts", "content": "x"},
                                                  role="implementer"), "test touch set")
        self.assertCopilotDenied(self.run_copilot("create", {"path": ".ai/PROJECT.md", "content": "x"},
                                                  role="implementer"), "never writes .ai/**")

    def test_write_aliases(self):
        for name, args in (("write", {"file_path": "docs/x.md", "content": "x"}),
                           ("write_file", {"filePath": "docs/x.md", "text": "x"}),
                           ("create_file", {"filename": "docs/x.md", "contents": "x"}),
                           ("str_replace_editor", {"command": "create", "path": "docs/x.md", "file_text": "x"}),
                           ("str_replace_editor", {"command": "str_replace", "path": "docs/x.md", "old_str": "a",
                                                   "new_str": "b"}),
                           ("replace_string_in_file", {"filePath": "docs/x.md", "oldString": "a", "newString": "b"}),
                           ("editFiles", {"filePath": "docs/x.md", "code": "x"}),
                           ("apply_patch", {"patch": "*** Begin Patch\n*** Update File: docs/x.md\n@@\n-a\n+b\n*** End Patch\n"})):
            with self.subTest(tool=name, args=args):
                self.assertCopilotDenied(self.run_copilot(name, args, role="implementer"), "docs/x.md")

    def test_test_plan_gate(self):
        res = self.run_copilot("create", {"path": "src/cache/store.ts", "content": "x"}, role="implementer",
                               script="test-plan-gate.py")
        self.assertCopilotDenied(res, "test plan first", "Status: DRAFT")
        self.repo.set_plan("APPROVED")
        self.assertAllowed(self.run_copilot("create", {"path": "src/cache/store.ts", "content": "x"},
                                            role="implementer", script="test-plan-gate.py"))

    def test_code_reviewer_status_flip_through_edit_alias(self):
        plan = ".ai/slices/01/TEST_PLAN.md"
        res = self.run_copilot("str_replace_editor", {"command": "str_replace", "path": plan,
                                                      "old_str": "Status: DRAFT", "new_str": "Status: APPROVED"},
                               role="code-reviewer")
        self.assertAllowed(res)
        res = self.run_copilot("create", {"path": plan, "content": "Status: APPROVED\n"}, role="code-reviewer")
        self.assertCopilotDenied(res, "exactly one change")

    def test_secrets_guard(self):
        res = self.run_copilot("create", {"path": ".ai/PROJECT.md", "content": "token = ghp_" + "A" * 30},
                               role="coordinator", script="secrets-guard.py")
        self.assertCopilotDenied(res, "possible secret", "GitHub token")
        self.assertAllowed(self.run_copilot("create", {"path": ".ai/PROJECT.md", "content": "token = <REDACTED>"},
                                            role="coordinator", script="secrets-guard.py"))


class ReadPayloads(HookTestCase):
    script = "goldfish-blinders.py"

    def test_goldfish_view_denied(self):
        self.repo.write(".ai/PROJECT.md", "x")
        res = self.run_copilot("view", {"path": ".ai/PROJECT.md"}, role="goldfish")
        self.assertCopilotDenied(res, "stays cold", "Read of '.ai/project.md'")
        self.assertAllowed(self.run_copilot("view", {"path": ".ai/slices/01/SLICE.md"}, role="goldfish"))
        self.assertAllowed(self.run_copilot("view", {"path": "README.md"}, role="goldfish"))

    def test_search_aliases(self):
        for name, args in (("grep", {"pattern": "cache", "path": ".ai"}),
                           ("rg", {"query": "cache", "dir": ".ai/planning"}),
                           ("glob", {"pattern": ".ai/**/*.md"}),
                           ("file_search", {"query": "**/.ai/*.md"}),
                           ("read_file", {"filePath": ".ai/planning/x.md"})):
            with self.subTest(tool=name):
                self.assertCopilotDenied(self.run_copilot(name, args, role="goldfish"), "stays cold")

    def test_other_roles_pass(self):
        self.assertAllowed(self.run_copilot("view", {"path": ".ai/PROJECT.md"}, role="architect"))


class AgentPayloads(HookTestCase):
    script = "brief-check.py"

    def test_task_without_caller_line_denied(self):
        res = self.run_copilot("task", {"agent": "shipyard-code-reviewer", "prompt": "Mode: SLICE\nReview."},
                               role="coordinator")
        self.assertCopilotDenied(res, "must start with the line 'Caller: shipyard:coordinator'")

    def test_valid_brief_allowed_and_aliases(self):
        brief = "Caller: shipyard:coordinator\nMode: SLICE\nReview the slice."
        for name, args in (("task", {"agent_type": "shipyard-code-reviewer", "prompt": brief}),
                           ("runSubagent", {"agentName": "shipyard-code-reviewer", "prompt": brief}),
                           ("agent", {"name": "shipyard:code-reviewer", "task": brief})):
            with self.subTest(tool=name):
                self.assertAllowed(self.run_copilot(name, args, role="coordinator"))

    def test_bad_mode_denied(self):
        res = self.run_copilot("task", {"agent": "shipyard-architect",
                                        "prompt": "Caller: shipyard:coordinator\nMode: SLICE\n"}, role="coordinator")
        self.assertCopilotDenied(res, "'Mode: SLICE' is not a mode")

    def test_non_shipyard_subagent_ignored(self):
        self.assertAllowed(self.run_copilot("task", {"agent": "general-purpose", "prompt": "hi"}, role="coordinator"))


class SubagentPayloads(HookTestCase):
    script = "findings-gate.py"
    REVIEWER = "shipyard-code-reviewer"

    def stop(self, agent=REVIEWER, **extra):
        return self.run_copilot(agent, None, event="subagentStop", **extra)

    def start(self, agent=REVIEWER, **extra):
        return self.run_copilot(agent, None, event="subagentStart", **extra)

    def put(self, rel, text, age=0):
        p = self.repo.write(rel, text)
        if age:
            t = time.time() - age
            os.utime(p, (t, t))

    def test_missing_findings_file_blocks(self):
        res = self.stop()
        d = self.assertCopilotBlocked(res, "must write its findings file before finishing",
                                      ".ai/slices/01/findings/code-reviewer.md")
        self.assertEqual(set(d), {"decision", "reason"})

    def test_valid_file_allows(self):
        self.put(".ai/slices/01/findings/code-reviewer.md", NO_FINDINGS)
        self.assertAllowed(self.stop())

    def test_non_reviewers_and_no_role_pass(self):
        self.assertAllowed(self.stop("shipyard-implementer"))
        self.assertAllowed(self.stop("general-purpose"))
        self.assertAllowed(self.stop("explore"))

    def test_role_from_env_for_agent_scoped_stop(self):
        res = self.stop("some-display-name", role="security-reviewer")
        self.assertCopilotBlocked(res, "security-reviewer.md")

    def test_start_then_stale_file_blocks(self):
        self.assertAllowed(self.start())
        self.put(".ai/slices/01/findings/code-reviewer.md", NO_FINDINGS, age=600)
        self.assertCopilotBlocked(self.stop(), "predates the start of this review")
        self.put(".ai/slices/01/findings/code-reviewer.md", NO_FINDINGS)
        self.assertAllowed(self.stop())

    def test_retry_cap_lets_reviewer_stop(self):
        session = "cap-%d" % int(time.time() * 1000)
        for _ in range(3):
            self.assertCopilotBlocked(self.stop(session=session))
        res = self.stop(session=session)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIsNone(decision(res))
        self.assertIn("already sent back 3 times", res.stderr)
        # the counter is cleared: the next stop in the same session blocks again
        self.assertCopilotBlocked(self.stop(session=session))

    def test_event_inferred_without_flag(self):
        payload = copilot_payload(self.REVIEWER, None, self.repo.path, event="subagentStop")
        res = run_hook("findings-gate.py", payload, self.repo.path, project_env=False)
        self.assertCopilotBlocked(res, "findings file")

    def test_rebuttal_mode_from_transcript(self):
        t = self.repo.write(".ai/transcript.txt", "Caller: shipyard:coordinator\nMode: REBUTTAL\n...")
        self.assertAllowed(self.stop(transcriptPath=t))


class Adapter(unittest.TestCase):
    """Unit checks on the mapping tables themselves."""

    def test_tool_name_aliases(self):
        cases = {"bash": "Bash", "shell": "Bash", "run_in_terminal": "Bash", "runCommands": "Bash",
                 "create": "Write", "write_file": "Write", "edit": "Edit", "str_replace_editor": "Edit",
                 "apply_patch": "Edit", "replace_string_in_file": "Edit", "editFiles": "Edit", "MultiEdit": "Edit",
                 "view": "Read", "read_file": "Read", "grep": "Grep", "rg": "Grep", "codebase": "Grep",
                 "glob": "Glob", "file_search": "Glob", "task": "Agent", "runSubagent": "Agent",
                 "run-subagent": "Agent", "custom-agent": "Agent", "Task": "Agent", "Bash": "Bash",
                 "web_fetch": "web_fetch", "": ""}
        for given, want in cases.items():
            self.assertEqual(copilot_hooklib.claude_tool_name(given), want, given)

    def test_argument_mapping(self):
        ti = copilot_hooklib.claude_tool_input("Bash", {"cmd": "ls"})
        self.assertEqual(ti["command"], "ls")
        ti = copilot_hooklib.claude_tool_input("Edit", {"filePath": "a.py", "oldString": "x", "newString": "y"})
        self.assertEqual((ti["file_path"], ti["old_string"], ti["new_string"]), ("a.py", "x", "y"))
        ti = copilot_hooklib.claude_tool_input("Grep", {"query": "x", "directory": "src", "outputMode": "files"})
        self.assertEqual((ti["pattern"], ti["path"], ti["output_mode"]), ("x", "src", "files_with_matches"))
        ti = copilot_hooklib.claude_tool_input("Agent", {"agent": "shipyard-planner", "prompt": "p"})
        self.assertEqual(ti["subagent_type"], "shipyard:planner")
        self.assertEqual(ti["agent"], "shipyard-planner")  # originals are kept

    def test_parse_args(self):
        self.assertEqual(copilot_hooklib.parse_args('{"command": "ls"}', "Bash"), {"command": "ls"})
        self.assertEqual(copilot_hooklib.parse_args({"command": "ls"}, "Bash"), {"command": "ls"})
        self.assertEqual(copilot_hooklib.parse_args("ls -la", "Bash"), {"command": "ls -la"})
        self.assertEqual(copilot_hooklib.parse_args("not json", "Write"), {})
        self.assertEqual(copilot_hooklib.parse_args(None, "Write"), {})

    def test_payload_detection(self):
        self.assertTrue(copilot_hooklib.is_copilot_payload({"toolName": "bash", "toolArgs": "{}"}))
        self.assertTrue(copilot_hooklib.is_copilot_payload({"sessionId": "s", "agentName": "x"}))
        self.assertFalse(copilot_hooklib.is_copilot_payload({"tool_name": "Bash", "tool_input": {}}))
        self.assertFalse(copilot_hooklib.is_copilot_payload({"hook_event_name": "SubagentStop"}))
        self.assertFalse(copilot_hooklib.is_copilot_payload({}))

    def test_adapt_shapes(self):
        data = {"sessionId": "s1", "timestamp": 1, "cwd": "/tmp", "toolName": "bash",
                "toolArgs": json.dumps({"command": "git push"})}
        out = copilot_hooklib.adapt(data)
        self.assertEqual(out["tool_name"], "Bash")
        self.assertEqual(out["tool_input"]["command"], "git push")
        self.assertEqual(out["hook_event_name"], "PreToolUse")
        self.assertEqual(out["_copilot_event"], "preToolUse")
        stop = copilot_hooklib.adapt({"sessionId": "s1", "cwd": "/tmp", "agentName": "shipyard-code-reviewer",
                                      "agentId": "a", "response": "done", "stopReason": "end_turn",
                                      "transcriptPath": "/t"})
        self.assertEqual(stop["hook_event_name"], "SubagentStop")
        self.assertEqual(stop["agent_type"], "shipyard:code-reviewer")
        self.assertEqual(stop["agent_id"], "s1:code-reviewer")
        self.assertEqual(stop["agent_transcript_path"], "/t")
        self.assertEqual(stop["last_assistant_message"], "done")
        start = copilot_hooklib.adapt({"sessionId": "s1", "cwd": "/tmp", "agentName": "shipyard-code-reviewer"})
        self.assertEqual(start["hook_event_name"], "SubagentStart")

    def test_deny_json(self):
        text, code = copilot_hooklib.deny_json("preToolUse", "r")
        self.assertEqual((json.loads(text), code), ({"permissionDecision": "deny", "permissionDecisionReason": "r"}, 2))
        text, code = copilot_hooklib.deny_json("subagentStop", "r")
        self.assertEqual((json.loads(text), code), ({"decision": "block", "reason": "r"}, 0))
        self.assertEqual(copilot_hooklib.deny_json("subagentStart", "r"), ("", 0))


if __name__ == "__main__":
    unittest.main()


class RealCliPayloads(HookTestCase):
    """Payloads captured from Copilot CLI 1.0.107 on 2026-11-08: `view` sends toolArgs as an object with
    `path`; `apply_patch` sends the patch document itself as a raw string."""
    script = "write-scope.py"

    PATCH_ADD = "*** Begin Patch\n*** Add File: %s/hook-probe.txt\n+probe\n*** End Patch\n"
    PATCH_TWO = ("*** Begin Patch\n*** Update File: %s/src/cache/store.ts\n@@\n-a\n+b\n"
                 "*** Add File: %s/src/other.ts\n+export const x = 1;\n*** End Patch\n")

    def test_view_object_args_map_to_read(self):
        data = {"sessionId": "s", "timestamp": 1794105655619, "cwd": self.repo.path, "toolCallId": "c1",
                "toolName": "view", "toolArgs": {"path": self.repo.path + "/README.md", "view_range": [1, 3]}}
        out = copilot_hooklib.adapt(data)
        self.assertEqual(out["tool_name"], "Read")
        self.assertEqual(out["tool_input"]["file_path"], self.repo.path + "/README.md")

    def test_apply_patch_raw_string_add_file_is_a_write(self):
        data = {"sessionId": "s", "timestamp": 1, "cwd": self.repo.path, "toolCallId": "c2",
                "toolName": "apply_patch", "toolArgs": self.PATCH_ADD % self.repo.path}
        out = copilot_hooklib.adapt(data)
        self.assertEqual(out["tool_name"], "Write")
        self.assertEqual(out["tool_input"]["file_path"], self.repo.path + "/hook-probe.txt")
        self.assertEqual(out["tool_input"]["content"], "probe")
        self.assertEqual(out["tool_input"]["patch_files"], [{"kind": "Add", "path": self.repo.path + "/hook-probe.txt"}])

    def test_apply_patch_outside_touch_set_denied_with_the_real_reason(self):
        self.repo.set_plan("APPROVED")
        res = self.run_copilot("apply_patch", self.PATCH_ADD % self.repo.path, role="implementer")
        self.assertCopilotDenied(res, "code touch set")
        self.assertNotIn("could not find the target path", res.stderr + res.stdout)

    def test_apply_patch_inside_touch_set_allowed(self):
        self.repo.set_plan("APPROVED")
        patch = "*** Begin Patch\n*** Add File: %s/src/cache/new.ts\n+export const y = 2;\n*** End Patch\n" % self.repo.path
        self.assertAllowed(self.run_copilot("apply_patch", patch, role="implementer"))

    def test_multi_file_patch_checks_every_file(self):
        self.repo.set_plan("APPROVED")
        res = self.run_copilot("apply_patch", self.PATCH_TWO % (self.repo.path, self.repo.path), role="implementer")
        self.assertCopilotDenied(res, "src/other.ts")

    def test_multi_file_patch_gated_before_approval(self):
        res = self.run_copilot("apply_patch", self.PATCH_TWO % (self.repo.path, self.repo.path), role="implementer",
                               script="test-plan-gate.py")
        self.assertCopilotDenied(res, "test plan first")

    def test_patch_into_ai_is_scanned_for_secrets(self):
        patch = ("*** Begin Patch\n*** Add File: %s/.ai/planning/notes.md\n+api_key = \"sk_live_%s\"\n*** End Patch\n"
                 % (self.repo.path, "a" * 40))
        res = self.run_copilot("apply_patch", patch, role="coordinator", script="secrets-guard.py")
        self.assertCopilotDenied(res, "possible secret")


class ProjectDirPrecedence(HookTestCase):
    script = "write-scope.py"

    def test_shipyard_project_dir_beats_inherited_claude_project_dir(self):
        self.repo.set_plan("APPROVED")
        # A stale CLAUDE_PROJECT_DIR (inherited from another harness) points at an empty folder with no .ai/;
        # SHIPYARD_PROJECT_DIR names the real project, so the write inside the touch set is allowed.
        import tempfile
        with tempfile.TemporaryDirectory() as other:
            res = self.run_copilot("apply_patch", "*** Begin Patch\n*** Add File: %s/src/cache/ok.ts\n+x\n*** End Patch\n" % self.repo.path,
                                   role="implementer", env_extra={"CLAUDE_PROJECT_DIR": other, "SHIPYARD_PROJECT_DIR": self.repo.path})
            self.assertAllowed(res)

    def test_copilot_project_dir_beats_inherited_claude_project_dir(self):
        self.repo.set_plan("APPROVED")
        import tempfile
        with tempfile.TemporaryDirectory() as other:
            res = self.run_copilot("apply_patch", "*** Begin Patch\n*** Add File: %s/src/cache/ok2.ts\n+x\n*** End Patch\n" % self.repo.path,
                                   role="implementer", env_extra={"CLAUDE_PROJECT_DIR": other, "COPILOT_PROJECT_DIR": self.repo.path})
            self.assertAllowed(res)

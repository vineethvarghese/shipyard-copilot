import json
import os
import stat
import sys
import tempfile
import unittest

from fixture_tree import SCRIPTS, run_script

sys.path.insert(0, SCRIPTS)
import formal_check  # noqa: E402

FAKE_QUINT = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
if args == ["--version"]:
    print("0.26.0"); sys.exit(0)
mode = os.environ.get("FAKE_QUINT", "ok")
if args and args[0] == "verify":
    mode = os.environ.get("FAKE_QUINT_VERIFY", mode)
out = args[args.index("--out-itf") + 1] if "--out-itf" in args else None
if mode == "hang":
    import time; time.sleep(5)
if mode == "violation":
    trace = {"#meta": {"format": "ITF"}, "vars": ["status", "applied", "ackPending"], "states": [
        {"#meta": {"index": 0}, "status": {"tag": "Pending", "value": {"#tup": []}}, "applied": {"#bigint": "0"}, "ackPending": False},
        {"#meta": {"index": 1}, "status": {"tag": "Leased", "value": {"#tup": []}}, "applied": {"#bigint": "0"}, "ackPending": False},
        {"#meta": {"index": 2}, "status": {"tag": "Leased", "value": {"#tup": []}}, "applied": {"#bigint": "1"}, "ackPending": True},
        {"#meta": {"index": 3}, "status": {"tag": "Pending", "value": {"#tup": []}}, "applied": {"#bigint": "1"}, "ackPending": False},
        {"#meta": {"index": 4}, "status": {"tag": "Leased", "value": {"#tup": []}}, "applied": {"#bigint": "2"}, "ackPending": True}]}
    with open(out, "w") as fh: json.dump(trace, fh)
    print("An example execution:\\n[violation] Found an issue (duration=12ms)."); sys.exit(1)
if mode == "error":
    sys.stderr.write("error: parsing failed\\n"); sys.exit(1)
print("[ok] No violation found (duration=20ms)."); sys.exit(0)
"""


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.model = os.path.join(self.dir, "INV-003.qnt")
        with open(self.model, "w") as fh:
            fh.write("module inv003 { val executeAtMostOnce = true }\n")
        self.bindir = os.path.join(self.dir, "bin")
        os.makedirs(self.bindir)

    def tearDown(self):
        self._tmp.cleanup()

    def fake_quint(self, mode="ok"):
        path = os.path.join(self.bindir, "quint")
        with open(path, "w") as fh:
            fh.write(FAKE_QUINT)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        return mode

    def run_check(self, *args, mode="ok", with_tool=True, verify_mode=None):
        env_path = (self.bindir + os.pathsep if with_tool else "") + os.environ.get("PATH", "")
        if with_tool:
            self.fake_quint(mode)
            # `quint verify` needs java: point at a stub so the --verify path is reachable in tests
            java = os.path.join(self.bindir, "java")
            with open(java, "w") as fh:
                fh.write("#!/bin/sh\necho 'openjdk 21' >&2\n")
            os.chmod(java, os.stat(java).st_mode | stat.S_IXUSR)
        old = dict(os.environ)
        os.environ["PATH"] = env_path if with_tool else self.bindir  # without the tool: an empty bin dir only
        os.environ["FAKE_QUINT"] = mode
        if verify_mode:
            os.environ["FAKE_QUINT_VERIFY"] = verify_mode
        else:
            os.environ.pop("FAKE_QUINT_VERIFY", None)
        try:
            return run_script("formal_check.py", *args)
        finally:
            os.environ.clear()
            os.environ.update(old)

    def out(self, proc):
        return json.loads(proc.stdout)


class Run(Base):
    def test_missing_tool_is_not_run_never_installed(self):
        proc = self.run_check("run", self.model, "--invariant", "executeAtMostOnce", with_tool=False)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        r = self.out(proc)
        self.assertEqual(r["status"], "NOT_RUN")
        self.assertIn("never installs", r["reason"])
        self.assertIsNone(r["tools"]["quint"]["path"])

    def test_simulation_pass_is_not_model_checked(self):
        proc = self.run_check("run", self.model, "--invariant", "executeAtMostOnce", "--max-steps", "12")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        r = self.out(proc)
        self.assertEqual(r["status"], "PASS")
        self.assertEqual(r["maxSteps"], 12)
        self.assertEqual(r["evidence"], "simulated (random, 12 steps)")
        self.assertFalse(r["verified"])
        self.assertIn("not model-checked evidence", r["reason"])
        self.assertEqual(r["steps"], 0)
        self.assertEqual(r["markdown"], "")
        self.assertEqual(len(r["modelSha256"]), 64)
        # the result is persisted next to the model so the verifier can read it later
        summary = os.path.join(self.dir, "INV-003.result.json")
        self.assertEqual(r["summary"], summary)
        with open(summary) as fh:
            self.assertEqual(json.load(fh)["status"], "PASS")

    def test_verify_pass_is_bounded_model_checked_evidence(self):
        proc = self.run_check("run", self.model, "--invariant", "executeAtMostOnce", "--verify", "--backend", "tlc",
                              "--max-steps", "8")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        r = self.out(proc)
        self.assertEqual(r["status"], "PASS")
        self.assertTrue(r["verified"])
        self.assertEqual(r["evidence"], "model-checked (bounded, 8 steps)")
        self.assertIn("quint verify (tlc", r["checker"])
        self.assertNotIn("reason", r)

    def test_checker_error_after_simulation_is_an_error_not_a_violation(self):
        # the simulation wrote a trace; a verify error must not be read as a violation because a file exists
        proc = self.run_check("run", self.model, "--invariant", "executeAtMostOnce", "--verify", mode="ok",
                              verify_mode="error")
        self.assertEqual(proc.returncode, 1)
        r = self.out(proc)
        self.assertEqual(r["status"], "ERROR")
        self.assertEqual(r["simulation"], "PASS")
        self.assertIn("nothing was proved", r["reason"])
        # and a planted-fault run that errors is not accepted as a successful fault check
        proc = self.run_check("run", self.model, "--invariant", "executeAtMostOnce", "--verify", "--expect",
                              "VIOLATED", mode="ok", verify_mode="error")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.out(proc)["status"], "ERROR")

    def test_violation_renders_the_trace(self):
        proc = self.run_check("run", self.model, "--invariant", "executeAtMostOnce", mode="violation")
        self.assertEqual(proc.returncode, 1)
        r = self.out(proc)
        self.assertEqual(r["status"], "VIOLATED")
        self.assertEqual(r["steps"], 4)
        self.assertTrue(r["trace"].endswith("INV-003.sim.itf.json"))
        self.assertEqual(r["evidence"], "simulated (random, 20 steps)")
        self.assertIn("| Step | status | applied | ackPending |", r["markdown"])
        self.assertIn("| 0 | Pending | 0 | no |", r["markdown"])
        self.assertIn("| 4 | **Leased** | **2** | **yes** |", r["markdown"])
        self.assertIn("violation", r["output"])

    def test_planted_fault_must_fail(self):
        proc = self.run_check("run", self.model, "--invariant", "executeAtMostOnce", "--expect", "VIOLATED", mode="violation")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(self.out(proc)["status"], "VIOLATED")
        proc = self.run_check("run", self.model, "--invariant", "executeAtMostOnce", "--expect", "VIOLATED", mode="ok")
        self.assertEqual(proc.returncode, 1)
        r = self.out(proc)
        self.assertEqual(r["status"], "UNEXPECTED")
        self.assertIn("too weak", r["reason"])

    def test_checker_error_and_timeout(self):
        proc = self.run_check("run", self.model, "--invariant", "x", mode="error")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.out(proc)["status"], "ERROR")
        proc = self.run_check("run", self.model, "--invariant", "x", "--timeout", "1", mode="hang")
        self.assertEqual(proc.returncode, 3)
        r = self.out(proc)
        self.assertEqual(r["status"], "NOT_RUN")
        self.assertIn("timed out", r["reason"])

    def test_missing_model(self):
        proc = self.run_check("run", os.path.join(self.dir, "nope.qnt"), "--invariant", "x")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.out(proc)["status"], "ERROR")


class Render(Base):
    def test_render_values_and_changes(self):
        trace = {"vars": ["q", "m", "t", "n"], "states": [
            {"#meta": {"index": 0, "action": "init"}, "q": {"#set": [1, 2]}, "m": {"#map": [["a", {"#bigint": "1"}]]},
             "t": {"#tup": [1, "x"]}, "n": {"tag": "Some", "value": 3}},
            {"#meta": {"index": 1, "action": "lease"}, "q": {"#set": [1]}, "m": {"#map": [["a", {"#bigint": "1"}]]},
             "t": {"#tup": [1, "x"]}, "n": {"tag": "None", "value": {"#tup": []}}},
        ]}
        md, steps = formal_check.render_trace(trace)
        self.assertEqual(steps, 1)
        self.assertIn("| Step | Action | q | m | t | n |", md)
        self.assertIn("| 0 | init | {1, 2} | {a: 1} | (1, x) | Some(3) |", md)
        self.assertIn("| 1 | lease | **{1}** | {a: 1} | (1, x) | **None** |", md)
        path = os.path.join(self.dir, "t.itf.json")
        with open(path, "w") as fh:
            json.dump(trace, fh)
        proc = run_script("formal_check.py", "render", path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("1 step(s)", proc.stdout)

    def test_render_rejects_garbage(self):
        path = os.path.join(self.dir, "bad.json")
        with open(path, "w") as fh:
            fh.write("[1, 2]")
        proc = run_script("formal_check.py", "render", path)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("cannot render", proc.stderr)

    def test_tools_subcommand(self):
        proc = self.run_check("tools", with_tool=False)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("tools", self.out(proc))


if __name__ == "__main__":
    unittest.main()

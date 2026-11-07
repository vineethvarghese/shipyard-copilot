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

    def run_check(self, *args, mode="ok", with_tool=True):
        env_path = (self.bindir + os.pathsep if with_tool else "") + os.environ.get("PATH", "")
        if with_tool:
            self.fake_quint(mode)
        old = dict(os.environ)
        os.environ["PATH"] = env_path if with_tool else self.bindir  # without the tool: an empty bin dir only
        os.environ["FAKE_QUINT"] = mode
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

    def test_pass_is_bounded_evidence(self):
        proc = self.run_check("run", self.model, "--invariant", "executeAtMostOnce", "--max-steps", "12")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        r = self.out(proc)
        self.assertEqual(r["status"], "PASS")
        self.assertEqual(r["maxSteps"], 12)
        self.assertEqual(r["tier"], "model-checked (bounded)")
        self.assertEqual(r["steps"], 0)
        self.assertEqual(r["markdown"], "")

    def test_violation_renders_the_trace(self):
        proc = self.run_check("run", self.model, "--invariant", "executeAtMostOnce", mode="violation")
        self.assertEqual(proc.returncode, 1)
        r = self.out(proc)
        self.assertEqual(r["status"], "VIOLATED")
        self.assertEqual(r["steps"], 4)
        self.assertTrue(r["trace"].endswith("INV-003.trace.itf.json"))
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

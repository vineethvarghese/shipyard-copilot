#!/usr/bin/env python3
"""Run a model-checked invariant (C-10 `model-checked`) and render its trace for humans. Stdlib only.

    formal_check.py tools
        Report which formal tools are on PATH (quint, java). Never installs anything.
    formal_check.py run MODEL.qnt --invariant NAME [--out TRACE.itf.json] [--summary RESULT.json] [--max-steps N]
                        [--timeout SECONDS] [--verify] [--backend tlc|apalache] [--expect PASS|VIOLATED]
        Run `quint run` (random simulation) and, with --verify, `quint verify` (bounded model checking) on the
        model. Prints one JSON object and writes the same object to RESULT.json (default <model>.result.json):
        status PASS | VIOLATED | NOT_RUN | ERROR | UNEXPECTED, the checker that produced it, the evidence kind
        (`simulated (random, N steps)` without --verify, `model-checked (bounded, N steps)` with it), the bound,
        the model's sha256, the trace rendered as a Markdown step table, and the reason when it did not run.
        A PASS from simulation alone is never model-checked evidence; only `quint verify` earns that label.
    formal_check.py render TRACE.itf.json
        Render an existing ITF trace (the JSON format Quint and the TLA+ tools write) as a Markdown step table.

A model is checked at most within its bound (`--max-steps`): a PASS is bounded evidence, never a proof. The
architect writes a sibling `<model>.fault.qnt` with a planted fault; run it with `--expect VIOLATED` to prove the
model can fail at all. Missing tooling is a NOT_RUN result with a reason, never an install.

Exit codes: 0 the run completed and matched --expect (PASS by default); 1 VIOLATED, UNEXPECTED or ERROR;
3 NOT_RUN (tooling missing or timed out); 2 usage error.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys


# ---------------------------------------------------------------- ITF rendering

def itf_value(v):
    """Render one ITF value compactly. ITF: https://apalache-mc.org/docs/adr/015adr-trace.html."""
    if isinstance(v, dict):
        if "#bigint" in v:
            return str(v["#bigint"])
        if "#set" in v:
            return "{" + ", ".join(itf_value(x) for x in v["#set"]) + "}"
        if "#tup" in v:
            return "(" + ", ".join(itf_value(x) for x in v["#tup"]) + ")"
        if "#map" in v:
            return "{" + ", ".join("%s: %s" % (itf_value(k), itf_value(x)) for k, x in v["#map"]) + "}"
        if "#unserializable" in v:
            return str(v["#unserializable"])
        if "tag" in v and set(v.keys()) <= {"tag", "value"}:
            inner = v.get("value")
            if inner is None or inner == {"#tup": []}:
                return str(v["tag"])
            return "%s(%s)" % (v["tag"], itf_value(inner))
        return "{" + ", ".join("%s: %s" % (k, itf_value(x)) for k, x in v.items() if not k.startswith("#")) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(itf_value(x) for x in v) + "]"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if v is None:
        return "-"
    return str(v)


def action_name(state):
    """Quint records the action taken in the meta or in an `action_taken`-style variable when asked to."""
    meta = state.get("#meta") or {}
    for key in ("action", "action_taken", "actionTaken"):
        if key in meta:
            return str(meta[key])
        if key in state:
            return itf_value(state[key])
    return ""


def render_trace(trace):
    """Markdown step table for an ITF trace dict. Returns (markdown, step count)."""
    if not isinstance(trace, dict):
        raise ValueError("trace must be a JSON object")
    states = trace.get("states")
    if not isinstance(states, list) or not states:
        return "_(no states in trace)_", 0
    declared = trace.get("vars")
    names = [v for v in declared if isinstance(v, str)] if isinstance(declared, list) else []
    if not names:
        seen = []
        for s in states:
            for k in s:
                if not k.startswith("#") and k not in seen:
                    seen.append(k)
        names = seen
    names = [n for n in names if n not in ("action_taken", "actionTaken", "action")]
    has_action = any(action_name(s) for s in states)
    header = ["Step"] + (["Action"] if has_action else []) + names
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    prev = None
    for i, s in enumerate(states):
        cells = [str(i)]
        if has_action:
            cells.append(action_name(s))
        for n in names:
            val = itf_value(s.get(n))
            changed = prev is not None and itf_value(prev.get(n)) != val
            cells.append("**%s**" % val if changed else val)
        lines.append("| " + " | ".join(cells) + " |")
        prev = s
    steps = len(states) - 1
    return "\n".join(lines), steps


def load_trace(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- tools

def tool_report():
    out = {}
    for name in ("quint", "java"):
        path = shutil.which(name)
        version = None
        if path:
            try:
                proc = subprocess.run([name, "--version"] if name == "quint" else [name, "-version"],
                                      capture_output=True, text=True, timeout=30)
                blob = (proc.stdout or "") + (proc.stderr or "")
                version = blob.strip().splitlines()[0][:80] if blob.strip() else "present"
            except (OSError, subprocess.SubprocessError):
                version = "present (version check failed)"
        out[name] = {"path": path, "version": version}
    return out


def cmd_tools(args):
    print(json.dumps({"tools": tool_report()}, indent=2))
    return 0


# ---------------------------------------------------------------- run

def result(status, **kw):
    r = {"status": status}
    r.update(kw)
    return r


def sha256_of(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            h.update(fh.read())
    except OSError:
        return None
    return h.hexdigest()


def write_summary(path, r):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=2)
            fh.write("\n")
        r["summary"] = path
    except OSError as exc:
        r["summaryError"] = "could not write %s: %s" % (path, exc)


def emit(args, r, code):
    write_summary(args.summary or (os.path.splitext(args.model)[0] + ".result.json"), r)
    print(json.dumps(r, indent=2))
    return code


def run_quint(argv, timeout):
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timed out after %d s" % timeout
    except OSError as exc:
        return None, "could not start %s: %s" % (argv[0], exc)
    return proc, None


def classify(proc):
    """Quint prints [ok] / [violation] and exits non-zero on a violation or an error. Only explicit violation
    text counts as a violation; a trace file on disk is never evidence by itself (a stale or partial file could
    otherwise turn a tooling error into a 'successful' planted-fault check)."""
    blob = (proc.stdout or "") + "\n" + (proc.stderr or "")
    low = blob.lower()
    if "[violation]" in low or ("violation" in low and "invariant" in low):
        return "VIOLATED", blob
    if proc.returncode == 0:
        return "PASS", blob
    return "ERROR", blob


def tail(text, n=20):
    lines = [l for l in (text or "").splitlines() if l.strip()]
    return "\n".join(lines[-n:])


def cmd_run(args):
    expect = args.expect or "PASS"
    base = dict(model=args.model, invariant=args.invariant, maxSteps=args.max_steps, expected=expect,
                modelSha256=sha256_of(args.model))
    if not os.path.isfile(args.model):
        return emit(args, result("ERROR", reason="model file not found", **base), 1)
    tools = tool_report()
    base["tools"] = tools
    if not tools["quint"]["path"]:
        return emit(args, result("NOT_RUN", reason="quint is not on PATH; install it yourself (npm i -g "
                                 "@informalsystems/quint) or lower C-10 to properties. Shipyard never installs "
                                 "tooling.", **base), 3)
    stem = os.path.splitext(args.model)[0]
    out = args.out or (stem + ".trace.itf.json")
    sim_out = stem + ".sim.itf.json"
    # Each phase writes its own trace file, so a simulation trace can never be mistaken for a checker result.
    for path in (out, sim_out):
        if os.path.isfile(path):
            os.unlink(path)

    sim_cmd = ["quint", "run", args.model, "--invariant", args.invariant, "--max-steps", str(args.max_steps),
               "--out-itf", sim_out]
    proc, err = run_quint(sim_cmd, args.timeout)
    if err:
        return emit(args, result("NOT_RUN", reason=err, command=" ".join(sim_cmd), **base), 3)
    status, blob = classify(proc)
    checker = "quint run (random simulation)"
    evidence = "simulated (random, %d steps)" % args.max_steps
    trace = sim_out if os.path.isfile(sim_out) else None
    simulation = status

    if status == "PASS" and args.verify:
        if not tools["java"]["path"]:
            return emit(args, result("NOT_RUN", reason="quint verify needs java on PATH (the model checkers run "
                                     "on the JVM); the simulation passed but bounded model checking did not run",
                                     simulation="PASS", checker=checker, evidence=evidence, **base), 3)
        verify_cmd = ["quint", "verify", args.model, "--invariant", args.invariant, "--max-steps",
                      str(args.max_steps), "--out-itf", out]
        if args.backend:
            verify_cmd += ["--backend", args.backend]
        proc, err = run_quint(verify_cmd, args.timeout)
        if err:
            return emit(args, result("NOT_RUN", reason=err, command=" ".join(verify_cmd), simulation="PASS",
                                     checker=checker, evidence=evidence, **base), 3)
        status, blob = classify(proc)
        checker = "quint verify (%s, bounded)" % (args.backend or "default backend")
        evidence = "model-checked (bounded, %d steps)" % args.max_steps
        trace = out if os.path.isfile(out) else None

    markdown, steps = "", 0
    if status == "VIOLATED" and trace:
        try:
            markdown, steps = render_trace(load_trace(trace))
        except (ValueError, OSError) as exc:
            markdown, steps = "_(trace could not be rendered: %s)_" % exc, 0
    elif status == "VIOLATED":
        markdown = "_(the checker reported a violation but wrote no trace)_"

    # Without --expect the observed status stands. With --expect (the planted-fault run), a mismatch is UNEXPECTED.
    final = status
    if args.expect and status in ("PASS", "VIOLATED") and status != args.expect:
        final = "UNEXPECTED"
    r = result(final, observed=status, simulation=simulation, checker=checker, evidence=evidence,
               verified=bool(args.verify and checker.startswith("quint verify")), steps=steps, trace=trace,
               markdown=markdown, output=tail(blob), **base)
    if final == "UNEXPECTED":
        r["reason"] = ("the planted fault did not make the checker fail: the model or the invariant is too weak "
                       "to prove anything" if args.expect == "VIOLATED" else "the invariant was violated")
    elif final == "VIOLATED":
        r["reason"] = "the invariant was violated within the bound; the trace below is the counterexample"
    elif final == "ERROR":
        r["reason"] = "the checker exited with an error and reported no violation; nothing was proved"
    elif final == "PASS" and not r["verified"]:
        r["reason"] = ("random simulation found no violation; this is not model-checked evidence. Add --verify "
                       "to run the bounded model checker.")
    code = 0 if (final == "PASS" or (final == "VIOLATED" and args.expect == "VIOLATED")) else 1
    return emit(args, r, code)


def cmd_render(args):
    try:
        markdown, steps = render_trace(load_trace(args.trace))
    except (OSError, ValueError) as exc:
        sys.stderr.write("formal_check.py: cannot render %s: %s\n" % (args.trace, exc))
        return 1
    print(markdown)
    print("\n%d step(s)" % steps)
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="formal_check.py", description="Run or render a model-checked invariant")
    sub = p.add_subparsers(dest="command")
    sub.required = True
    t = sub.add_parser("tools", help="report which formal tools are on PATH")
    t.set_defaults(func=cmd_tools)
    r = sub.add_parser("run", help="run a Quint model against one invariant")
    r.add_argument("model")
    r.add_argument("--invariant", required=True)
    r.add_argument("--out", help="ITF trace path for the checker run (default: <model>.trace.itf.json); the simulation writes <model>.sim.itf.json")
    r.add_argument("--summary", help="where to write the JSON result (default: <model>.result.json)")
    r.add_argument("--max-steps", type=int, default=20, help="the bound (default 20)")
    r.add_argument("--timeout", type=int, default=300, help="seconds per checker run (default 300)")
    r.add_argument("--verify", action="store_true", help="also run bounded model checking after the simulation")
    r.add_argument("--backend", choices=["tlc", "apalache"], help="model checker for --verify")
    r.add_argument("--expect", choices=["PASS", "VIOLATED"], help="use VIOLATED for the planted-fault model")
    r.set_defaults(func=cmd_run)
    d = sub.add_parser("render", help="render an ITF trace as a Markdown step table")
    d.add_argument("trace")
    d.set_defaults(func=cmd_render)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

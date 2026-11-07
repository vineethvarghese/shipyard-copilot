# Verification policy

**Cheap execution beats confident derivation.** This file exists because reasoning that *sounds* rigorous is
indistinguishable, in an artifact, from reasoning that was checked — and assumption labels were being used to
launder the difference.

## The rule

> If a claim can be settled by running a command that takes **under 60 seconds**, run the command.
> Do not infer it, do not derive it from configuration, and do not write it into an artifact as `DERIVED`.

**Extension: the narrowest slower command.** When no command under 60 seconds settles the claim, a slower one is
allowed if it is the **narrowest** command that does — one test file rather than the suite, one package rather than
the workspace, one target rather than the whole build. Record its duration next to the result. A broad slow command
run "to be safe" is not verification; it is cost.

This applies to every Shipyard agent, in every phase, including planning and brainstorming synthesis.

## What counts as an empirical claim

Any assertion about **observable system behaviour** rather than about code structure or intent:

| Claim type | Examples |
|---|---|
| Build and test tooling | "this target is broken", "this runner rejects that argument form", "these tests pass", "this filter selects nothing" |
| CI behaviour | "this pipeline builds that package", "nothing executes this Dockerfile", "this gate blocks merge" |
| Runtime/library behaviour | "this value is unreachable", "this client cannot accept a non-seekable stream", "this handler is registered outermost" |
| Dependency resolution | "this package brings that transitive dependency", "this version is pinned" |
| Counts and inventories | "N call sites", "no consumer reads this field", "this is the only usage" |
| Git state | "the slice branch tip is the evidence commit", "the feature branch is clean", "this merge has two parents" |

Reading a config file tells you what someone **intended**. Running the command tells you what **happens**. When an
artifact drives a human decision, only the second one counts.

## Label discipline

`DERIVED` means *necessarily follows from specified information or from repository evidence you actually observed*.
It does **not** cover an empirical prediction, however well reasoned.

| Situation | Correct label |
|---|---|
| Ran it, observed the result | `DERIVED` — quote the command and its output verbatim |
| Could run it, did not | **`UNRESOLVED`** — and it blocks the gate that depends on it |
| Cannot run it here (needs live infrastructure, a shared environment, production scale) | `ASSUMED` — with the risk-if-wrong note and an entry in `planning/assumptions.md` |

An empirical claim that reaches a human gate carrying `DERIVED` without a recorded command is a **framework
violation**, not a style preference.

## Agents that make empirical claims need execution

A role that asserts how tooling behaves must be able to observe it. Every Shipyard role except the goldfish has
`Bash`. The goldfish is deliberately tool-light; when it makes an empirical claim it has two honest options:

1. **State it as a question** in `questions`, naming the command that would settle it; or
2. **State it as a risk** of the concept, not as a fact.

Never quietly convert "I could not check this" into a confident assertion. If your tools cannot run a command, say so
next to the claim.

## Execution is for verification, not mutation

Planning, review and brainstorming roles run **read-only, non-destructive** commands: builds and tests that change no
tracked files, `git log`, `git diff`, `git show`, `git rev-parse`, dependency listings, `--help`, `--dry-run`. They do
not modify tracked files outside `.ai/`, do not install or update dependencies, do not change git state, do not push,
and do not touch anything outside the working tree. The readonly-bash hook enforces this for reviewers, the
architect, the planner and discovery. A verification command that changes state is not a verification command.

The implementer and the verifier write and commit inside their own touch sets (`branch-policy.md`). Their
verification commands follow the same read-only rule.

**Never run a `SHARED` validation tier** without the human's explicit approval for this run. The verifier returns
`AWAITING_APPROVAL` for it, and the slice workflow returns `NEEDS_SHARED_APPROVAL`.

Prefer the smallest command that settles the question: one test file over a whole suite, one `--help` over a full
build.

## Before any gate or escalation

Two checks, both cheap, both mandatory:

- **Escalation check.** Before asking a human to decide something — especially to approve a new mechanism, a new
  file, or an exception to convention — verify the premise that makes it necessary. A false premise produces a real
  decision about an imaginary problem, and the human has no way to detect it.
- **Gate check.** Before presenting a gate, list every empirical claim the recommendation rests on and confirm each
  is `DERIVED`-with-command or explicitly flagged. Claims that reach a gate unverified are named in the gate message,
  not buried in an artifact.

## Recording

Record verifications inline where the claim is made:

```text
Verified 2026-10-15 (node 22.11, linux):
    $ npm test -- tests/cache/ttl.test.ts
    Tests: 14 passed, 14 total            (duration 3.2 s)
```

Command, date, environment where it matters, the result, and the duration when it took 60 seconds or more. Enough
that the next agent re-runs it instead of re-deriving it — and enough that a stale claim can be spotted when the
repository moves.

## When verification refutes an earlier claim

Retract it explicitly and in place. Do not silently correct it.

State what was claimed, what was observed, why the original reasoning failed, and what downstream conclusions
change. The reasoning failure is the reusable part. In the run that produced this policy, the error was conflating
two argument shapes: the test runner rejected one form (a positional path to a workspace manifest file) and accepted
another (a positional path to the package directory). The distinction was invisible in configuration and obvious in
one 8-second command.

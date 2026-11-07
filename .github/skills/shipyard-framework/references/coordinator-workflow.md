# Coordinator workflow (P0–P10)

The step-by-step procedure for `shipyard-coordinator`. The agent file carries the safety constraints and the phase
table; this file carries the steps. Read the section for the phase you are about to run — not all of them.

| Phase | How | Gate |
|---|---|---|
| P0 Intake | You | HUMAN |
| P1 Scan · P2 Brainstorm & narrow · P3 Draft | Workflow `shipyard-discover` | — |
| P4 Grill | You, with discovery `GRILL` between rounds | HUMAN |
| P5 Critique · P6 Refine · P7 Delivery planning | Workflow `shipyard-plan` | — |
| P8 Plan approval | You | HUMAN |
| P9 Slice | You cut the branch; workflow `shipyard-slice`; you write the evidence and the brief | — |
| P9.9 Merge | You | HUMAN |
| P10 Reconcile | You, with direct subagent calls | — |

---

## Common mechanics

### Paths

Every command below is relative to the repository root, where the `shipyard/` folder and `.github/` live. Run them
from there.

### Three modes, one procedure

The three phases between gates (P1–P3, P5–P7, P9) are defined as dynamic workflows under `.github/extensions/`
(`shipyard-discover`, `shipyard-plan`, `shipyard-slice`). They enforce order, caps, routing and dedupe in code.
Which mode you are in decides how you run them (`docs/modes.md`):

| Mode | How the three phases run | Enforcement of order and caps |
|---|---|---|
| **CLI** (`copilot --experimental --agent=shipyard-coordinator`) | Launch the dynamic workflow in-session ("run the shipyard-discover workflow with args …") or with `copilot workflow run <name> --args @<file> --result-file <file>`; read the result file. | The workflow code. |
| **IDE** (VS Code or JetBrains agent picker) | No workflow runner. Follow the matching phase prompt file (`.github/prompts/shipyard.<phase>.prompt.md`) step by step, calling each specialist as a subagent with the shared brief header. | `python3 shipyard/scripts/check.py --phase <P>` before the phase, and the PR checks. |
| **Cloud** (Copilot coding agent, one task per phase) | As IDE mode, inside one task; the gate is the issue or pull request. | `check.py --phase` and the Actions checks. |

Before every phase, run `python3 shipyard/scripts/check.py --phase <P0|P4|P8|SLICE|MERGE>` and stop on a non-zero
exit: it checks the previous gate is recorded in `state.json` and the artifacts the phase needs exist. Before every
delegation, run `python3 shipyard/scripts/shipyard_state.py set-active-role <short>` (and `set-active-role none`
afterwards), so the repository hooks know which role is writing. After every explicit human yes, record it:
`python3 shipyard/scripts/shipyard_state.py gate <P0|P4|P8|MERGE> approve --by <login> [--slice <id>]`.

**In CLI mode, never run a workflow's steps by hand with direct subagent calls instead.** That would bypass the
order, the caps, the routing and the fail-closed checks the workflows enforce in code. If the workflow runner is
missing (no `--experimental`, or the CLI version has no dynamic workflows), say so once and continue in IDE mode with
the prompt files; record `Mode: IDE (no workflow runner)` under `## Framework configuration`.

### Building `registry` and `contracts`

Every launch passes both, read fresh from disk each time. Never embed an edited copy.

```bash
python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])), separators=(",",":")))' \
  shipyard/registry/roles.json
python3 -c 'import json,glob,os,sys
d={os.path.basename(p)[:-len(".schema.json")]: json.load(open(p)) for p in sorted(glob.glob(sys.argv[1]+"/contracts/*.schema.json"))}
print(json.dumps(d, separators=(",",":")))' "$ROOT"
```

- `registry` = the parsed `registry/roles.json` object.
- `contracts` = one object keyed by file stem (the file name without `.schema.json`), e.g. `contracts["reviewer-result"]`,
  `contracts["slice-workflow-result"]`.

Launch (CLI mode) with the dynamic workflow runner: write the args to `.ai/returns/<phase>-args.json`, then run
`copilot workflow run shipyard-discover | shipyard-plan | shipyard-slice --args @.ai/returns/<phase>-args.json
--result-file .ai/returns/<phase>-result.json`, or ask the session to run the named workflow with those args.
Wait for the run to finish. While it runs, do not do its work yourself and do not start the next phase. In IDE
and cloud modes, run the matching prompt file instead (the `Workflow` blocks below list the inputs it needs).

### Workflow results

A result whose `status` is not one the phase below lists, or a run that returned nothing, failed or was stopped, is a
fail-closed stop: `BLOCKED` with the reason. Never report success for a run that partly ran. Validate the slice result
before using it:

```bash
python3 "shipyard/scripts/shipyard_validate.py" slice-workflow-result .ai/returns/p9-slice-<id>.json
```

(save the result to that file first; like all of `.ai/`, it never enters a work branch).

### State

Write `state.json` only through the state script; it keeps the file valid against `contracts/state.schema.json`.

```bash
python3 "shipyard/scripts/shipyard_state.py" init --project <name> --feature-branch <feature> --base-branch <base> \
    --protected <comma-separated names> --breadth <0|1|2> --formal-rigour <none|invariants|properties|model-checked>
python3 "shipyard/scripts/shipyard_state.py" set-status <PROJECT STATUS>
python3 "shipyard/scripts/shipyard_state.py" set-slice <id> <slice-branch>      # before a slice launch
python3 "shipyard/scripts/shipyard_state.py" set-slice --clear                   # after the merge
python3 "shipyard/scripts/shipyard_state.py" show
python3 "shipyard/scripts/shipyard_state.py" snapshot -m "<phase>: <what changed>"   # commit .ai/ to the notes branch
python3 "shipyard/scripts/shipyard_state.py" restore --from <notes branch>         # fresh clone only
```

Run `shipyard_state.py --help` once per session and follow the argument names it prints if they differ.

**A checkpoint** is: update `PROJECT.md` (`Status` + a `## Phase log` row) and `state.json` together (hard rule 1),
then `snapshot`. Take one at every phase transition (each "phase-log row" in this file), after every slice result
you write up (9.5), after every merge (P9.9) and reconciliation (P10), and at completion. `snapshot` commits `.ai/`
to the notes branch without touching the working tree, the index or the current branch; "no change" is fine. It is
the only way `.ai/` reaches git (`branch-policy.md`).

### Direct subagent calls (outside workflows)

You call specialists directly only for work no workflow covers: the P4 grill rounds (discovery `GRILL`), P10
(architect `REVALIDATE`, planner `RECONCILE`), a drift conformance check (architect `CONFORMANCE`), an adjudication
the human asks for (architect `ADJUDICATE`), a replan between gates (planner `REPLAN`), and the slice-level re-check
described in P9. Every brief starts with the shared header:

```text
Caller: shipyard-coordinator
Mode: <MODE>
Slice: <id>                     (slice modes only)
Round: <n>                      (fix rounds; 0 for first pass)
Feature-branch: <name>          (slice modes)
Slice-branch: <name>            (slice modes)
Diff: git diff <featureBranch>...<sliceBranch>   (reviewers in SLICE/RECHECK mode)
Read: <path>, <path>, ...       (raw inputs to read, never a summary)
Write: <path>                   (the agent's output file, when it has one)
Budget: <n> turns
```

then free text (the question, findings to fix, rebuttals to answer). Pass the `model` and `effort` for the mode from
`registry.computeClasses` on the subagent call; never more than your own session.

The **brief-check** hook (CLI) denies a direct call to any `shipyard-` agent unless the prompt starts with
`Caller: shipyard-coordinator`, has a `Mode:` line that is a valid mode for that agent's role in the registry, and —
for `FIX`, `FIX_TESTS` and `RECHECK` — has `Round: <n>` with `n ≤ registry.limits.fixRounds`. A denial is a bug in
your brief: fix the brief; never work around the hook.

A directly called specialist ends its final message with exactly one fenced ```json block matching its contract.
Save it and validate it before acting on it:

```bash
python3 "shipyard/scripts/shipyard_validate.py" <contract-stem> .ai/returns/<phase>-<agent>-<mode>[-<id>].json
# or pipe the block on stdin:  ... shipyard_validate.py <contract-stem> -
```

A missing block, two blocks, or a non-zero exit is an invalid return: re-run once with the validator's message
added to the brief; still invalid → `BLOCKED`.

### Reporting to the human

Assume a very short attention span. The human reads only chat and `*.HUMAN.md` (hard rule 11). Never send them to an
agent file; quote the one line that matters. Lead with state, not narration:

```text
Project:     <name>             Phase: <P0–P10>
Slice:       <id> <title>       State: <slice state>
Round:       <n> of 3
Blocked on:  <human decision | nothing>
Next action: <what you will do next, or what you need>
```

Escalations use the decision format in `escalation-policy.md`: the question, the evidence, the options, and always a
recommendation.

---

## P0 — Intake (GATE)

Take whatever the human already has: a design doc, an issue, a diagram, or a rough idea. **Do not require a complete
design.** Producing one is the job of P1–P8.

### Size check (first, before anything else)

This workflow costs a P0 gate, a repository scan, a brainstorm, a critique round, a plan, a test plan per slice and
several `DEEP` reviewers per slice. That price is wrong for a small ask. Before creating `.ai/`, judge from the
request alone (and a quick look at the code if needed) whether the work is **ad-hoc-sized**: it fits in one change the
human would review in one sitting, the design is already clear, and it touches no public contract, migration,
concurrency/lifecycle behaviour, or other consumers.

If it is ad-hoc-sized, say so in two or three lines and recommend a normal Copilot session instead. Do not create
`.ai/`. If the human insists, proceed and record `Size check: overridden by human` under
`## Framework configuration`. If you are unsure, proceed; the P0 gate will surface it.

**The size check applies only to brand-new intake** — no `.ai/PROJECT.md` exists yet. Never run it, and never suggest
a normal session, once a project exists: running or resuming a slice, a fix round, a merge, reconciliation, a replan,
or any request that names an existing slice. Small slices are the intended output of planning, and redirecting one
would orphan it from the plan's state, prerequisites and reconciliation.

### Session checks

1. Workflows are available (above).
2. Compute and guardrail check (`compute-policy.md` → session check): `copilot --version` and
   `python3 shipyard/scripts/check.py --env`. Confirm you are running at `COORDINATOR` class and note which mode
   (CLI, IDE, cloud) and which guardrails are active. Record results under `## Framework configuration`.
3. `git rev-parse --is-inside-work-tree` succeeds in the target repository.

### Intake steps

1. Create `.ai/PROJECT.md` from the template with `Status: INTAKE`.
2. Record what the human supplied **verbatim** under `## Source material`, with links or paths.
3. Run the delivery-parameter gate below. It is the one set of questions you ask *before* reading the repository.
4. Validate and create the feature branch (`branch-policy.md` → P0). Refuse `main`, `master`, the default branch,
   the base branch and any protected name; check `git check-ref-format --branch <name>`; create it from the base if
   missing; switch to it.
5. `shipyard_state.py init …` (status `INTAKE`). It first adds `/.ai/` to `.git/info/exclude`, so git ignores the
   `.ai/` folder in the work tree without any change to the project's files; it refuses if `.ai/` files are already
   tracked (then ask the human; `branch-policy.md` → P0). It also records the notes branch (`<feature>-shipyard`,
   or the name the human gave as part of C-8). Record both under `## Framework configuration`. Never edit the
   project's `.gitignore`.
6. Add the P0 phase-log row and take the first checkpoint (`snapshot -m "P0: intake"`). Move to P1.

### The delivery-parameter gate

There is one category of question you have **not** earned by reading the repository and never will, because the
repository cannot answer it: **the shape of the deliverable the human wants.** Discovery cannot derive a slice
budget. The architect cannot derive how many new packages the human will accept. These are preferences, and asking
for them costs one turn.

Ask them as **one batched turn**, each with a recommended default, so the human can accept the whole set in one word:

| ID | Parameter | Why it must precede discovery | Typical default |
|---|---|---|---|
| C-1 | **Slice budget** — target/maximum number of slices | Drives every decomposition decision. Learning it after the plan exists invalidates the plan. | "up to 6" |
| C-2 | **New-project budget** — new projects, modules or packages allowed | Decides whether shared contracts get their own package. Changing it later reverses ADRs. | "0 unless justified" |
| C-3 | **Reuse posture** — which shared libraries must be preferred, which may be modified | Decides build vs reuse for every subsystem. | "prefer existing; modify only with an ADR" |
| C-4 | **Existing-code blast radius** — which deployed/shared components may be touched, how invasively | Turns whole classes of design options on or off. | "only the components named in the request" |
| C-5 | **Tracking artifacts** — work items or issues per slice, and the parent to hang them off | Changes the required shape of every slice spec. | "none" |
| C-6 | **Time and artifact budget** — how long to wait, how much to read | Governs delegation depth, critique fan-out, brainstorm breadth and artifact size. | "one screen per brief" |
| C-7 | **Convention posture** — may new tooling/test/build mechanisms be invented, or must everything follow repo convention | Decides whether a tooling gap is a design choice or a mandatory escalation. | "follow existing convention" |
| C-8 | **Feature branch and base branch** | Every slice branch and merge depends on them; Shipyard never touches the base. | `feature/<slug>` from the default branch |
| C-9 | **Cost budget** | Sets how much breadth the run can afford; reported at every gate. | "moderate" |
| C-10 | **Formal rigour** — `none`, `invariants`, `properties` or `model-checked` | Decides what the architect writes for every invariant and what the verifier must prove (`docs/formal-methods.md`). Discovering it later rewrites `INVARIANTS.md` and every test plan. | `none`; recommend `invariants` when the request mentions concurrency, retries, money or multi-tenancy; `model-checked` only for a concurrency or partial-failure core, and only after P1 found the tooling |
| BB | **Brainstorm breadth** 0 / 1 / 2 | Tied to C-6 and C-9 (`brainstorm-policy.md`). | `1` (`0` if the human brought a finished design) |

Record every answer **verbatim** in `PROJECT.md` → `## Delivery parameters`, each as a `SPECIFIED` constraint with
its ID. They outrank agent judgment for the rest of the project, and later phases cite them by ID.

**If the human declines to answer an item,** record the default as `ASSUMED` and flag it at P8 as an explicit risk.
Never pick silently.

**Do not ask anything else at P0.** Everything the repository can answer, you go and read. This gate is narrowly
about deliverable shape, not about design.

> **Why this gate exists.** It was added after a run that produced a 19-slice plan, four new projects and 1.29 MB of
> artifacts before learning the human wanted at most 6 slices, exactly one new project, and mandatory reuse of
> existing shared libraries. 27% of the output was discarded outright and the rest needed a full replan. The analysis
> was not wrong; it was answering a question nobody had asked. One batched turn at P0 would have prevented all of it.

---

## P1–P3 — Scan, brainstorm, draft (`shipyard-discover`)

1. `set-status DISCOVERY`; `PROJECT.md` `Status: DISCOVERY`.
2. Launch:

   ```text
   Workflow  name: "shipyard-discover"
   args: {
     "registry":    <registry>,
     "contracts":   <contracts>,
     "request":     "<PROJECT.md ## Source material, verbatim>",
     "breadth":     <0|1|2>,
     "constraints": { "C-1": "<value>", ..., "C-10": "<value>" },
     "formalRigour": "<C-10: none | invariants | properties | model-checked>"
   }
   ```

   The workflow runs discovery `SCAN` (STANDARD; `discovery.md`, validation tiers, formal tooling when C-10 is above
   `none`), discovery `ELEPHANT` (DEEP, breadth 1–2; the sealed take), the goldfish lenses in parallel, discovery
   `SYNTHESIZE` (DEEP; `concepts.md`, gap tree), discovery `DRAFT` (`PROJECT.md` body and user stories,
   `GLOSSARY.md` seed, `CONSUMERS.md`), architect `DRAFT` (`ARCHITECTURE.md`, `INVARIANTS.md` at the C-10 tier,
   `.ai/formal/` when model-checked) and discovery `QUESTIONS` (DEEP; the gap tree and the first grill round).
3. Handle the result:

| status | You do |
|---|---|
| `NEEDS_HUMAN` | Normal end. Go to P4 with its top concepts, disagreements, `questions` (the gap tree) and `frontier` (round 1). |
| `BLOCKED` | Fail closed: `BLOCKED` with its reason; report. |
| anything else, or no result | Fail closed. |

4. Write three phase-log rows (P1 `DISCOVERY`, P2 `BRAINSTORMING` or "skipped, breadth 0", P3 `PLANNING`) with what
   each produced. `set-status PLANNING`.
5. **Spot-check for a failed scan.** If discovery reports no consumers and no contracts in a repository that plainly
   has them, or `couldNotInspect` lists something central, the scan did not work. Re-launch with a narrower request
   note rather than proceed.

---

## P4 — Grill (GATE)

P4 reaches **shared understanding**, not a single answered turn. Discovery drafted a question tree
(`planning/open-questions.md`; the gap list in `concepts.md`; the result's `questions`, each with `kind`,
`dependsOn` and `status`). You run the tree as rounds: each round asks the whole **frontier** (every open question
whose dependencies are settled), waits, records, and recomputes. The loop is yours; discovery does the recomputing.

### Round 1

Adjudicate the frontier under `escalation-policy.md` — drop any question the repository, a command or an earlier
decision can settle (`kind: fact` questions never reach the human; if one is still `OPEN`, send it back to discovery)
— and put the survivors to the human in **one turn**, highest leverage first, at most
`registry.limits.grillQuestionsPerRound`:

1. **The concept pick** (breadth 1–2): the top 3 from `concepts.md`, one line each (what, why, size, main risk), the
   disagreement with the elephant take that matters most, and your recommendation.
2. **The frontier**: numbered `Q1..Qn`, each with its evidence, why it matters, the options, and a recommendation
   worded so that "yes" accepts it. Tell the human a plain "yes" accepts every recommendation in the round, and that
   "enough" or "go with your recommendations" ends the grill.
3. **Spend so far** against C-9, one line.

### Between rounds

When the human answers:

1. Round 1 only: write `.ai/decisions/ADR-000-scope.md` from the concept pick (`brainstorm-policy.md`).
2. Record each answer **verbatim** in `planning/open-questions.md` with the round number; mark the question
   `ANSWERED`. A question the human skipped takes its recommended default, marked `DEFERRED` and `ASSUMED`, and is
   listed at P8.
3. Direct call: `shipyard-discovery`, `Mode: GRILL`, `Budget: 15 turns`, `Read:` `planning/open-questions.md`,
   `planning/concepts.md`, `.ai/GLOSSARY.md`, `PROJECT.md`, `planning/discovery.md`; `Write:`
   `planning/open-questions.md`, `.ai/GLOSSARY.md`. Pass the round number and the answers verbatim. Discovery
   records them, settles every new `fact` from the repository, challenges any term the human used that conflicts
   with the glossary or the code (a `term` question for the next round), adds the questions the answers opened
   (each with `kind` and `dependsOn`), writes the glossary, and returns the next `frontier`, `glossaryTerms` and
   `decisionCandidates`. Validate against `discovery-result`.
4. For each `decisionCandidates` entry with all three flags true (hard to reverse, surprising without context, a real
   trade-off), write a short-form `.ai/decisions/ADR-NNN.md` (`artifact-templates.md`) in this round. Everything
   else stays in `open-questions.md`.
5. Phase-log row `P4 round <n>`; checkpoint.
6. If the frontier is non-empty and no stop condition holds, ask the next round (step 2 of round 1 again, without the
   concept pick).

### Stop conditions

The grill ends when any of these holds:

- the frontier is empty (every branch of the tree visited, nothing left silently assumed);
- the human says "enough", "go with your recommendations" or words to that effect: every open question takes its
  recommended default, marked `DEFERRED` and `ASSUMED`;
- `registry.limits.grillRounds` rounds have been asked. Say so; the human may ask for more rounds, which you grant.

Then show the **shared-understanding checklist** in chat (≤ 15 lines) and wait for an explicit yes:

```text
Concept:        <ADR-000, one line>
Terms settled:  <glossary terms added or sharpened, comma-separated | none>
Decisions:      <ADR ids written this grill, one line each | none>
Defaults taken: <questions left at their recommended default, one line each | none>
Deferred:       <questions that will be answered by readiness checks at P7 or at P8 | none>
Formal rigour:  <C-10 tier and the invariants the human named | none>
Say "yes" to start planning, or name anything above that is wrong.
```

Silence or enthusiasm is not a yes (hard rule 6). A correction reopens that question; discovery `GRILL` recomputes
and the checklist is shown again.

### Leaving P4

1. Compute `planFlags` (`review-routing.md` → plan routing): `publicContract`, `config`, `consumerVisible`,
   `concurrency`, `security`, each `true` or `false` from `discovery.md`, ADR-000 and the answers (uncertain →
   `true`); `modelChecked` is `true` exactly when C-10 is `model-checked`.
2. Phase-log row for P4 (rounds asked, questions answered, defaults taken, ADRs written); checkpoint. Move to P5.

Rules:

- **Ask the whole frontier per round**, highest leverage first; never one question per turn, and never a question
  whose dependency is still open.
- Every question **cites evidence** from the repository and says why it matters.
- **Recommend, and word it so "yes" accepts it.** "Here are three options, you pick" wastes the leverage.
- **Never ask what the repository can answer.** Go read it; a `fact` question is a discovery defect.
- **No total cap on questions.** The caps are per round and on rounds; the human can always extend. Hundreds of
  questions is a sign of a badly cut tree, not of a thorough grill.

Bad: *"How should errors work?"*

Good: *"`src/client/retry.go:88` retries HTTP 502 and 503. The proposed design adds a failure after partial response
commitment, which that loop would treat as retryable and so duplicate side effects. Keep the retry contract, or make
partial-stream failure terminal? Recommend terminal."*

---

## P5–P7 — Critique, refine, delivery planning (`shipyard-plan`)

1. `PROJECT.md` and `state.json` stay `PLANNING`.
2. Launch:

   ```text
   Workflow  name: "shipyard-plan"
   args: {
     "registry":  <registry>,
     "contracts": <contracts>,
     "planFlags": { "publicContract": bool, "config": bool, "consumerVisible": bool,
                    "concurrency": bool, "security": bool, "modelChecked": bool },
     "cycle":     <refine cycles already used: 0 on the first launch>,
     "answers":   { "concept": "<the human's pick, verbatim>", "gaps": { "G1": "<answer>", ... },
                    "questions": { "Q-003": "<answer>", ... }, "defaults": { "G4": "<default taken>" } },
     "formalRigour": "<C-10>"
   }
   ```

   The workflow runs the P5 critique (architect `CRITIQUE` and simplicity always; contract, integration, reliability
   and security by `planFlags`, each in `PLAN` mode, writing `.ai/planning/<agent-name>.md`; at C-10 `model-checked`
   the reliability reviewer runs every model under `.ai/formal/` with `scripts/formal_check.py`), P6 refinement
   (bounded rechecks, at most `registry.limits.planRefineCycles` cycles counted from `cycle`), and P7 delivery
   planning (planner `PLAN` with the C-constraints, seams under test and prior art per slice; integration and
   architect sequencing checks; one readiness goldfish per `SLICE.md`).
3. Handle the result:

| status | You do |
|---|---|
| `AWAITING_PLAN_APPROVAL` | Normal end. Phase-log rows P5, P6 (`PLANNING`) and P7 (`DELIVERY_PLANNING`). Go to P8. |
| `NEEDS_HUMAN` | New questions only the human can answer. Back to P4 with them; then re-launch with `cycle` set to the result's `cyclesUsed` (the refine cap counts across launches). If no refine cycle is left (`cyclesUsed` equals `registry.limits.planRefineCycles`) and findings are still open, escalate with what remains and a recommendation instead. |
| `BLOCKED` | Fail closed. |
| anything else, or no result | Fail closed. |

What the workflow holds the plan to — the **planning definition of done**:

- objective, scope and non-goals are explicit;
- current and target architecture are documented; invariants are recorded;
- consumers are inventoried and integration impact is understood;
- contract changes, failure semantics, concurrency and resource assumptions are explicit;
- deployment, rollout, rollback and migration strategies are understood;
- material assumptions are resolved or deliberately accepted;
- every slice has ACs, both touch sets, a branch, a verification command proven to run, and a `READY` readiness
  verdict.

Planning does not need to predict every implementation detail. Unknowns must be **known, bounded, and assigned** to
a later decision point.

**One critique pass, not three.** An earlier run executed a five-agent critique, then a disposition pass
re-processing its output, then a separate validation that re-derived the same ground — roughly 300 KB of findings
for a plan that changed for none of those reasons. The plan workflow folds disposition into refinement, keeps the
P7 checks to ordering and mergeability, and caps each reviewer's findings (`findingsCapPerReviewer`).

**Planner exception requests.** If the planner believes a C-constraint (usually the slice budget) forces an unsafe
boundary, it returns an explicit exception request with the minimum deviation. Bring it to the human at P8; never
absorb it.

### Tracking artifacts (C-5)

If the human asked for work items or issues, every `SLICE.md` carries a `## Work item` block and `DELIVERY_PLAN.md`
a roll-up table. Follow the target repository's own convention for fields, hierarchy and defaults — find it before
inventing a scheme.

- **One to three work items per slice, and prefer fewer.** Needing more than three is evidence the slice is too big.
  Split the slice.
- Size items so **a different person could pick each one up independently**, not by implementation sequence.
- **Keep the hierarchy flat**: one tracking parent for the project; no per-slice parent layer.
- Fetch the parent's real field values and **inherit** them; read the parent's type, which constrains the
  children's type in most trackers.
- Several items sharing one slice say so in their title prefix and first body line.
- Draft the content; **do not create the items** unless the human explicitly asks.

---

## P8 — Plan approval (GATE)

1. `set-status AWAITING_PLAN_APPROVAL`.
2. Write `.ai/PLAN.HUMAN.md` from the template (`artifact-templates.md`): recommendation, what will be built (from
   ADR-000), the slices in order, the decisions being approved (including each slice's seams under test), the
   properties being relied on (C-10 above `none`: INV id, meaning, tier, status, any model NOT_RUN), the risks being
   accepted (including every `ASSUMED` P0 default, every grill question left at its default, and every planner
   exception request), spend against C-9, and only the questions that change the plan.
3. **Present the same content in chat.** The human approves what you tell them, not what they might find in agent
   files. Anything material that does not fit on one screen is either cut or is a question now.
4. **Wait for explicit approval.** Silence or general enthusiasm is not approval. A change request goes to the
   planner (`REPLAN`, direct call) or back to P4/P5 as it requires, then this gate again.
5. On approval: record it with the date and the human's words in `DELIVERY_PLAN.md`; move every slice in the plan
   `PROPOSED → APPROVED` in the slice table and in each `SLICE.md`; `set-status IMPLEMENTING`; phase-log row.

When P10 sends you back here after a `REPLAN` or `ARCHITECTURE_DECISION`, regenerate `PLAN.HUMAN.md` for the changed
plan. Changed or new slices go back to `PROPOSED` until this gate clears again; merged slices stay `MERGED`.

---

## P9 — Slice (`shipyard-slice`)

Repeat per slice, in plan order. Never run P9 before the human has cleared P8.

### 9.1 Preconditions

The slice is `APPROVED` (or is being re-run), and every prerequisite is `MERGED` — unless the human explicitly
approved a speculative start, recorded in `DELIVERY_PLAN.md`. Otherwise stop.

### 9.2 Cut the slice branch and set state

Follow `branch-policy.md` → "Cutting a slice branch": clean tree, `git check-ref-format --branch`,
`git switch -c <feature>-slice-<id> <feature>` (or switch to the existing branch on a re-run). Then:

```bash
python3 "shipyard/scripts/shipyard_state.py" set-slice <id> <feature>-slice-<id>
```

Set the slice `TEST_PLANNING` (or `IMPLEMENTING` if its `TEST_PLAN.md` already says `APPROVED`) in `SLICE.md` and
`DELIVERY_PLAN.md`.

### 9.3 Launch

```text
Workflow  name: "shipyard-slice"
args: {
  "registry":       <registry>,
  "contracts":      <contracts>,
  "slice":          "<id>",
  "featureBranch":  "<feature>",
  "sliceBranch":    "<feature>-slice-<id>",
  "round":          0,
  "startAt":        "TEST_PLAN",
  "sharedApproved": { },
  "humanChanges":   [ ],
  "humanRound":     1
}
```

- `round`: fix rounds already used — `0` on a first launch; the result's `rounds` when re-launching after
  `NEEDS_SHARED_APPROVAL` or `BLOCKED_REVIEWER`.
- `startAt`: `"TEST_PLAN"` (default: a fresh run, test plan first) or `"VERIFY"` (resume at Verify: after a SHARED
  tier decision, an interruption, or a human edit to the slice branch). On resume, VERIFY re-reads the test plan's
  status and the workflow stops unless it is `APPROVED`.
- `sharedApproved`: SHARED tier name → `true` (the human said run it now) or `false` (the human said no: record it
  `NOT_RUN` and continue). Data only: it never decides where the run starts. Empty on a first launch.
- `humanChanges`: the human's merge-gate change requests (9.6), each `{ "id": "H1", "owner": "implementer" |
  "verifier", "finding": "<the human's words>", "requiredResolution": "<what to change>", "location": "<path,
  optional>" }`. Non-empty → the run starts at Fix with these items, then re-verifies and re-runs every routed review
  in full. They cannot be rebutted, and they do not count toward the fix-round cap. `humanRound`: 1 for the first
  change request on this slice, 2 for the next, and so on (it names the commits).

The workflow runs: verifier `TEST_PLAN` → code-reviewer `TEST_PLAN` (≤ 2 revisions; the code-reviewer flips the
status line on `APPROVE`) → implementer `IMPLEMENT` ‖ verifier `WRITE_TESTS` → verifier `VERIFY` (commits tests;
suite, scope check, tiers, `routingFacts`) → routed reviewers in parallel → dedupe → fix rounds (implementer `FIX` ‖
verifier `FIX_TESTS`; architect `ADJUDICATE` on author concerns and test disputes; rebuttals answered by the reporting
reviewer in `REBUTTAL` mode; `RECHECK` of open findings plus a code-review pass over everything changed since the last
review; ≤ 3) → result.

### 9.4 Handle the result

Save it to `.ai/returns/p9-slice-<id>.json` and validate it against `slice-workflow-result` first.

| status | You do |
|---|---|
| `READY_FOR_HUMAN` | 9.5. |
| `NEEDS_SHARED_APPROVAL` | Slice `VERIFYING`. Write the tier under `## Pending human approval` in `SLICE.md` (tier, environment, date, `PENDING`), then ask the human live, naming the tier and the environment. On yes: outcome `APPROVED`, re-launch with `startAt: "VERIFY"`, `round: <result rounds>` and `sharedApproved: {"<tier>": true}`. On no: outcome `DENIED`, re-launch the same way with `false` for it; the tier is `NOT_RUN` in the brief's risks. |
| `ESCALATE` | Slice `TEST_PLANNING` (test plan never approved) or `AGENT_REVIEW` (findings open after 3 rounds, an unresolved architectural `BLOCKING`, an architect escalation of an author's concern or test dispute, a human change request the authors could not do, or authors reporting stubs or unmet ACs — the `reason` and `authorNotes` say which). Write `FINDINGS.json` from the result. Bring the open findings to the human in the decision format with options — clarify the ACs and re-launch (planner updates `SLICE.md`); accept named findings as risks (`ACCEPTED_BY_HUMAN`, then write the brief from this result as in 9.5); split or replan the slice (planner `REPLAN`, then P8); drop the slice — and a recommendation. |
| `BLOCKED_REVIEWER` | Slice `AGENT_REVIEW`. Ask the human: wait (re-launch), or proceed without that reviewer. "Proceed" is possible only if every other routed reviewer finished and no in-scope finding is open in the result; then record `<role>: SKIPPED_BY_HUMAN — <reason>, <date>` in `EVIDENCE.md` and the brief's risks, and continue with 9.5. Otherwise re-launch. |
| `BLOCKED` | Fail closed: `set-status BLOCKED`, `Blocked reason:` in `PROJECT.md`, report the reason in one line. |

Also check `humanInputRequests` in every result and adjudicate each one (`escalation-policy.md`). Copy
`authorNotes` (architecture concerns, test disputes and the architect's rulings, out-of-scope notes) into
`EVIDENCE.md`; out-of-scope notes go to the planner at P10. If
`verify.scopeCheck` is `DRIFT` and the workflow did not settle it, call the architect `CONFORMANCE` directly
(`review-routing.md` → scope drift) before the brief.

### 9.5 Write the evidence and the brief

From the validated result, never from memory:

1. `.ai/slices/<id>/FINDINGS.json` — the result's `findings` array, verbatim.
2. `.ai/slices/<id>/EVIDENCE.md` — the full record (template in `artifact-templates.md`): `Evidence commit:` = the
   result's `commit`; the test plan line from `testPlan`; the review table from `reviewersRouted`,
   `reviewersNotRouted` and the counts; verification from `verify` (the `Formal (C-10):` line from `verify.formal`:
   tier, invariants checked, invariants `NOT_RUN` with reasons); capability skill versions from `abilityVersions`;
   rounds; and the machine block = the result verbatim. Reviewers not routed are listed with why,
   so silence is never ambiguous.
3. `.ai/slices/<id>/REVIEW.HUMAN.md` — **≤ 40 lines**: recommendation first, at most three things to check (each a
   file or decision and the question to ask about it), what changes, risks (never omit unverified ACs, `NOT_RUN`
   tiers or skipped reviewers), one-line evidence.
4. Set the slice `READY_FOR_HUMAN`, then `HUMAN_REVIEW`, in `SLICE.md` and `DELIVERY_PLAN.md`.
5. Checkpoint: `snapshot -m "P9 slice <id>: ready for review"`. The slice branch holds only the authors' code and
   test commits; `.ai/` goes to the notes branch.
6. **Show the brief in chat** in the same turn, plus one line: to see the code, run
   `git diff <feature>...<feature>-slice-<id>`.

### 9.6 The human's answer

- **Approve** (explicit, for this slice) → P9.9.
- **Change request** → slice `CHANGES_REQUESTED`. Record the human's words verbatim under `## Human change requests`
  in `SLICE.md` (H1, H2, …).
  - It changes an acceptance criterion or the test plan → call the planner (`REPLAN`, this slice only) to update the
    ACs, then re-launch `shipyard-slice` fresh (`startAt: "TEST_PLAN"`, `round: 0`): the verifier rewrites the test
    plan as `DRAFT` and it must be approved again. Slice `TEST_PLANNING`.
  - Otherwise → re-launch with `humanChanges` (one item per H-line, owner `implementer` for code and `verifier` for
    tests, the human's words in `finding`) and the next `humanRound`. Slice `IMPLEMENTING`.

  Human requests do not count toward the cap. Then 9.4 again: everything is re-verified and re-reviewed, and the
  brief is regenerated.
- **The human edited the slice branch themselves** → the evidence is stale. Re-launch `shipyard-slice` with
  `startAt: "VERIFY"` and `round: 0` so the edit is verified and every routed reviewer reviews in full; quote the
  edit in the next brief.
- **Questions** → answer from the artifacts, quoting the one line that matters. Not approval.

---

## P9.9 — Merge (GATE)

Only after the human explicitly approved this slice's brief. Follow `branch-policy.md` → "The merge procedure" step
by step:

1. Quote the approval in the phase log.
2. The tree is clean (`git status --porcelain` empty; `.ai/` is ignored).
3. The slice branch tip is the evidence commit.
4. `git switch <feature>`; clean tree; the feature branch is an ancestor of the slice branch.
5. `git merge --no-ff <feature>-slice-<id> -m "Merge slice <id>: <title>" -m "<evidence summary>"` (one short
   paragraph from `EVIDENCE.md`: ACs verified, test command and result, reviewers, rounds, accepted risks).
6. Conflict → `git merge --abort`, report in one line, slice stays `HUMAN_REVIEW`.
7. Re-run the canonical test command; record command, result and duration. Failure → `BLOCKED`, report, recommend a
   revert commit or a fix-forward slice; act only on the human's word.
8. Set the slice `MERGED` (with the merge sha) in `SLICE.md` and `DELIVERY_PLAN.md`; `set-slice --clear`; phase-log
   row; checkpoint (`snapshot -m "P9.9 slice <id>: merged <short sha>"`). Keep the slice branch.

Never push. Then P10, before anything else.

---

## P10 — Reconcile

Run `merge-reconciliation.md` in full after **every** merge, before the next slice:

1. Pin `B`, `S`, `M` (`HEAD^1`, `HEAD^2`, `HEAD`) and confirm `HEAD` is the slice's merge commit.
2. Compare planned against actual; list human edits (commits on `B..S` that are not in Shipyard's message forms, and
   changes made for human change requests) — the highest-signal changes.
3. Direct call: `shipyard-architect`, `Mode: REVALIDATE`, `Read:` the diff command, `ARCHITECTURE.md`,
   `INVARIANTS.md`, the slice's `SLICE.md` and `EVIDENCE.md`, the human-edit list. Validate against
   `architect-result`. Verdict `VALID | UPDATE | ARCHITECTURE_DECISION`.
4. Direct call: `shipyard-planner`, `Mode: RECONCILE`, `Read:` the same plus `DELIVERY_PLAN.md`, every remaining
   `SLICE.md` and the architect's verdict. Validate against `planner-result`. Verdict
   `UNCHANGED | MINOR_UPDATE | REPLAN | ARCHITECTURE_DECISION`.
5. Record both verdicts in the reconciliation log in `DELIVERY_PLAN.md`, a phase-log row and a checkpoint
   (`snapshot -m "P10 slice <id>: <verdicts>"`), then:
   - `UNCHANGED` (and architect `VALID` or `UPDATE`): next slice at P9;
   - `MINOR_UPDATE` (slice text only; scope, boundaries, ordering, dependencies and gates unchanged): tell the human
     in one line of chat, then next slice at P9;
   - `REPLAN`, or `ARCHITECTURE_DECISION` from either agent: back to P8. No slice starts until the human approves
     the changed plan.

Like the rest of `.ai/`, reconciliation changes stay in the working tree when the next slice branch is cut; the
checkpoint above has already put them on the notes branch.

---

## Completion

The project is complete when every planned slice is merged or deliberately dropped, consumer migrations and
deprecations are complete or separately tracked, success criteria are measured, open assumptions are closed or
handed to tracked follow-up work, documentation is done, and `ARCHITECTURE.md` reflects final reality.

1. `set-status COMPLETE`; phase-log row; checkpoint (`snapshot -m "complete"`).
2. Remind the human: nothing has been pushed. They push the feature branch themselves
   (`git push -u <remote> <feature>`) and raise the pull request from `<feature>` to `<base>`. The pull request
   contains only code and tests. Shipyard's notes are on the local notes branch; they can push it too
   (`git push -u <remote> <notes branch>`) for an off-machine copy.
3. Offer a short retrospective: which findings were high value, which reviewers generated noise, which slices were too
   large, which questions should have been asked earlier, which compute assignments were wrong, and actual spend
   against C-9. That feedback improves the framework itself.

---

## Resume after an interruption

Never reconstruct state from conversation history. Re-read the files.

1. Read `.ai/state.json` (`shipyard_state.py show`), `PROJECT.md` (`Status`, `## Phase log`) and `DELIVERY_PLAN.md`.
   In a fresh clone `.ai/` is absent: fetch the notes branch if it was pushed
   (`git fetch <remote> <notes>:<notes>`), then `restore --from <notes>` writes `.ai/` back (and sets up the local
   exclude); the last snapshot is where the project resumes. Work done after the last snapshot is lost, so say so.
   If only `state.json` is missing, rebuild it with `init` from `PROJECT.md` → C-8 and the protected set, then
   `set-status` and `set-slice` from `DELIVERY_PLAN.md`. If neither `.ai/` nor a notes branch exists, stop and tell
   the human: the merge commits' evidence summaries record what was merged, and a new P0 starts from there.
2. If `state.json` and `PROJECT.md` disagree, stop and reconcile them from the artifacts and `git` before anything
   else (`git branch --show-current`, `git log --oneline -5`, `git status --porcelain`).
3. Find the interrupted step:

| Last recorded state | Resume by |
|---|---|
| `INTAKE`, P0 answers incomplete | Re-ask only the missing P0 items, in one turn. |
| `DISCOVERY` with no P1–P3 rows | Re-launch `shipyard-discover`. In the same session (or after `copilot --resume`), ask for the stopped run to be relaunched: completed agents return their saved results. |
| `PLANNING` with P4 open | Read `planning/open-questions.md`: the last `P4 round <n>` phase-log row says which round was asked. Re-present that round's unanswered questions; if the round was fully answered, run discovery `GRILL` for the next frontier. Never restart from round 1. |
| `PLANNING` after P4 | Re-launch `shipyard-plan` with the same `cycle`. |
| `AWAITING_PLAN_APPROVAL` | Re-present `PLAN.HUMAN.md` in chat. |
| `IMPLEMENTING`, slice `TEST_PLANNING`…`AGENT_REVIEW` | Check out the slice branch; re-launch `shipyard-slice` for it (relaunch the stopped run if the session still has it; else `startAt: "VERIFY"` when `TEST_PLAN.md` says `APPROVED` and the slice has code commits, otherwise a fresh launch with `round: 0`). |
| slice `VERIFYING` with a `PENDING` shared tier | Re-ask the human for that tier; do not re-run verification. |
| slice `HUMAN_REVIEW` | Check the evidence commit still matches the slice branch (else re-launch), then re-show `REVIEW.HUMAN.md`. |
| a merge commit for the slice on the feature branch but slice not `MERGED` | Re-run the post-merge test, then P9.9 step 8 and P10. |
| `BLOCKED` | Report the recorded reason; ask what the human wants. Never clear `BLOCKED` without fixing its cause. |

Never re-run the size check on a resume.

## Workflow return contracts

Each workflow's return value has a contract: `discover-workflow-result`, `plan-workflow-result` and
`slice-workflow-result` (see `registry/roles.json` → `workflowContracts`). If a return value doesn't validate
(`python3 shipyard/scripts/shipyard_validate.py <contract> <file>`), treat it as `BLOCKED`.
To resume a slice at Verify without redoing the approved test plan (for example after an interruption), relaunch
`shipyard-slice` with `startAt: "VERIFY"`. `sharedApproved` alone never moves the start: a run without `startAt`
starts from the test plan.

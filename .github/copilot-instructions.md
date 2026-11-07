# Shipyard: repository instructions for Copilot

This repository runs the Shipyard method: a large change ships as a chain of small, independently mergeable
slices, each with a test plan before any code, agent review, and a human decision before every merge. The full
contract is the skill `.github/skills/shipyard-framework/SKILL.md`; the agents are under `.github/agents/`; the
tool-independent core (registry, contracts, scripts, hooks) is under `shipyard/`.

## Entry point

- `shipyard-coordinator` is the only agent a person starts. The twelve specialists are hidden
  (`user-invocable: false`) and work only on a brief that starts with `Caller: shipyard-coordinator` and a
  `Mode:` line. If you are a specialist and the brief lacks that header, do no work and say so.
- Three modes exist: Copilot CLI (dynamic workflows), the IDE (the coordinator drives specialists following
  `.github/prompts/shipyard.*.prompt.md`), and the cloud coding agent (one task per phase). `docs/modes.md`
  explains them. The gates and the `.ai/` state are the same in every mode.

## The `.ai/` folder

- All project state lives in `.ai/` at the repository root, plus `.ai/state.json`. Re-read the files; never rely
  on what an earlier turn remembered.
- `.ai/` never enters a work branch. It is ignored through `.git/info/exclude` and committed only to the notes
  branch `<feature>-shipyard` by `python3 shipyard/scripts/shipyard_state.py snapshot`. A pull request that
  touches `.ai/**` fails the `shipyard-notes-guard` check.
- Write `state.json` only through `shipyard_state.py`. Never by hand.
- Each file has one writer (see `.github/instructions/ai-folder.instructions.md`). `*.HUMAN.md` files are one
  screen (about 40 lines) and are the only files a person is expected to read.
- No secrets in `.ai/`. Record where a secret lives, never its value: `<REDACTED>`.

## Findings

Every review finding has these lines, in this order: `ID:`, `Severity:`, `Category:`, `Location:`, `Finding:`,
`Why it matters:`, `Evidence:`, `Required resolution:`, `Confidence:`, `Owner:`, `Status:`. Ids are
`<short>-NNN` (for example `code-007`). A findings file with nothing to report carries the exact line
`NO FINDINGS`. Evidence is mandatory: a path and line range, a command and its output, or a cited requirement.

Severity scale: `BLOCKING` (wrong, unsafe, or breaks a contract) · `MAJOR` (a real problem that will cost later)
· `MINOR` (small but real) · `NOTE` (optional). Security findings map `CRITICAL`/`HIGH` → `BLOCKING`,
`MEDIUM` → `MAJOR`, `LOW` → `MINOR`, `INFORMATIONAL` → `NOTE`. Every `BLOCKING`, `MAJOR` and `MINOR` finding is
fixed or rebutted (once, with a citation) before a slice reaches a person.

## Assumption labels

Label every material fact: `SPECIFIED` (a human-approved source says it), `DERIVED` (follows from specified
facts or observed evidence, cited), `ASSUMED` (reasonable, not established; say the risk if wrong), `UNRESOLVED`
(needs evidence or a human). A claim a command under 60 seconds can settle is settled by running it.

## Hard rules in one screen

1. Test plan first: no production code and no test code until `.ai/slices/<id>/TEST_PLAN.md` says
   `Status: APPROVED`, and only `shipyard-code-reviewer` writes that line.
2. The implementer writes only the slice's code touch set; the verifier only the test touch set. Never both.
3. Never push. Never commit, merge, rebase or reset on `main`, `master`, the default branch or any branch in
   `state.json` → `protectedBranches`. Slices merge into the feature branch with `git merge --no-ff` after a
   person says yes.
4. Fail closed: a missing input, an invalid return, a step that could not run → `BLOCKED` with the reason.
5. Agents recommend; a person decides at P0, P4, P8 and every merge. Silence is not approval.

Ask for the skill `shipyard-framework` when any of this needs detail.

---
applyTo: ".ai/**"
---

# Writing under `.ai/`

`.ai/` is Shipyard's working memory. It is plain text and JSON so a run can resume from disk alone. Every file
has one writer; everyone else reads.

| Path | Only writer | Notes |
|---|---|---|
| `state.json` | coordinator, through `python3 shipyard/scripts/shipyard_state.py` | Never edit by hand. Valid against `shipyard/contracts/state.schema.json`. |
| `PROJECT.md` | coordinator (`Status`, `## Delivery parameters`, `## Phase log`, `## Framework configuration`); discovery (the rest) | C-1..C-10 answers are recorded verbatim with the label `SPECIFIED` or `ASSUMED`. |
| `GLOSSARY.md`, `planning/discovery.md`, `planning/concepts.md`, `planning/assumptions.md`, `planning/open-questions.md`, `CONSUMERS.md` | discovery | The sealed elephant take in `concepts.md` is written once and never edited. |
| `ARCHITECTURE.md`, `INVARIANTS.md`, `decisions/**`, `formal/**`, `planning/architect.md` | architect | The coordinator may write short-form ADRs from the P4 grill. |
| `DELIVERY_PLAN.md`, `slices/*/SLICE.md`, `planning/planner.md` | planner | Slice ids are two digits; both touch sets are listed, never overlapping, never `.ai/**`. |
| `slices/<id>/TEST_PLAN.md` | verifier, always as `Status: DRAFT` | Only `shipyard-code-reviewer` changes that one line to `Status: APPROVED`, and changes nothing else in the file. |
| `slices/<id>/findings/<reviewer>.md`, `planning/<reviewer>.md` | that reviewer | First line is the agent banner; then `NO FINDINGS` or finding blocks. |
| `slices/<id>/findings/verifier.md` | verifier | The full verification report. |
| `slices/<id>/EVIDENCE.md`, `slices/<id>/FINDINGS.json`, `slices/<id>/REVIEW.HUMAN.md`, `PLAN.HUMAN.md`, `returns/**` | coordinator | |

Rules:

- `*.HUMAN.md` files fit on one screen: about 40 lines, recommendation first, at most three things to check,
  risks, one line of evidence. Everything else is for agents and starts with the banner line
  `> 🤖 AGENT FILE. The human is not expected to read this.`
- No secrets. Record where a secret lives, never its value (`<REDACTED>`). A hook and push protection on the
  remote both look for secrets here.
- Label every material fact `SPECIFIED`, `DERIVED`, `ASSUMED` or `UNRESOLVED`, and cite a path and line range or a
  command and its output for `SPECIFIED` and `DERIVED`.
- Budget: any single file about 25 KB, `planning/` about 150 KB in total, a slice spec about 12 KB, a findings
  file about 15 KB. Reference, do not restate. Supersede by deletion.
- Never stage or commit `.ai/` on a work branch. `shipyard_state.py snapshot` commits it to the notes branch.
- Templates for every file: `.github/skills/shipyard-framework/references/artifact-templates.md`.

# Changelog

## 1.1.0 — 2026-11-08

- Invariant tables and `Violated by:` sequences are explicit inputs: missing cells and reachable violations are
  findings.
- Model-checked procedure (C-10 model-checked, PLAN mode): run every `.ai/formal/*.qnt` with
  `scripts/formal_check.py`, require the planted fault to fail, render a counterexample as a plain-English scenario
  plus a step table, report PASS as bounded evidence only.

## 1.0.0 — 2026-10-15

Initial release.

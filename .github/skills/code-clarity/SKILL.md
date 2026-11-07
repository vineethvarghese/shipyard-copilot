---
name: code-clarity
description: >
  Clarity and design-depth review method for Shipyard. The code-reviewer loads it in SLICE and RECHECK mode to judge
  whether new or changed code is easy to read and safe to change; the architect loads it in CRITIQUE mode to judge
  module boundaries in a plan. Covers complexity symptoms (change amplification, cognitive load, unknown unknowns),
  deep versus shallow modules, information hiding and leakage, pass-through methods and variables, layering, pulling
  complexity down, defining errors away, interface generality, obvious code, naming and comments, plus structure
  checks (single responsibility, dependency direction, hidden coupling, opaque names, god objects). Not for
  performance, security, test quality, or whether a new layer should exist at all (simplicity-review).
---

# Code clarity

Version 1.0.0 · used by code-review (`shipyard-code-reviewer`), architect (`shipyard-architect`, CRITIQUE)

Complexity is anything about the code that makes it hard to understand or hard to change. Your job is to find the
complexity that **this change adds**, show its concrete cost, and name the smallest change that removes it. Taste is
not a finding. A finding names a cost a reader or a future change will pay.

The ideas below are paraphrased from John Ousterhout, *A Philosophy of Software Design* (chapters on the nature of
complexity, deep modules, information hiding, layering, errors, naming and comments), plus structure checks from
established code-review practice. Cite the book by topic when it sharpens a finding; repository evidence always
outranks a citation.

## How to review

1. Read the requirement first (`SLICE.md` objective and ACs, or the plan artifact). Clarity is judged against what the
   code must do.
2. Read the tests, then the diff. Judge **changed and added lines**. Pre-existing complexity that the diff only
   touches is `NOTE` (or `MINOR` if the diff makes it worse).
3. For each candidate, gather evidence of cost before writing anything (see each check). No cost shown, no finding.
4. Prefer one well-evidenced finding over five impressions. Cap: the reviewer-wide cap of 15 findings applies.

## The three symptoms (use them to state cost)

Every clarity finding should name at least one symptom. They are how you turn "I don't like this" into evidence.

| Symptom | What it means | How to evidence it |
|---|---|---|
| Change amplification | One simple change needs edits in many places. | Name the plausible change (e.g. "add a currency") and list every file and line that would have to change. |
| Cognitive load | A developer must hold many facts in mind to make a change safely. | List the facts a reader must know that the code does not tell them (units, ordering rules, which flag combos are legal). |
| Unknown unknowns | It is not obvious which code must change, or what a change will break. | Show the two distant locations that are coupled, and that nothing in either points at the other. |

## Design checks

Each check: **look for**, **evidence**, **severity guidance**. Category is `clarity/<check-id>` (e.g.
`clarity/information-leakage`).

### shallow-module
- **Look for:** a new class, function or module whose interface is nearly as complex as what it does. Many small
  methods that each do almost nothing. A wrapper that renames one call.
- **Evidence:** compare interface size (parameters, methods, concepts a caller must learn) with the functionality
  behind it. Quote the body.
- **Severity:** `MINOR`; `MAJOR` when callers must now learn several shallow pieces to do one job.
- Good modules are *deep*: a small, simple interface over a lot of useful work.

### information-leakage
- **Look for:** one design decision (a file format, a protocol detail, a key layout, an ordering rule) encoded in two
  or more places. Also *temporal decomposition*: code split by the order things happen (read, then parse, then write)
  so the same knowledge appears in each step.
- **Evidence:** quote both locations and name the decision they share. Name the change that would have to touch both.
- **Severity:** `MAJOR` when the shared knowledge crosses module boundaries; `MINOR` within one file.

### pass-through
- **Look for:** a method that only forwards to another method with the same or nearly the same signature; a variable
  threaded through several layers that do not use it, only to reach one deep function.
- **Evidence:** show the call chain and that intermediate layers add nothing.
- **Severity:** `MINOR`; `MAJOR` if a pass-through variable crosses three or more layers. If the right fix is "delete
  this new layer", it is simplicity-review's finding, not yours.

### layer-abstraction
- **Look for:** adjacent layers that offer the same abstraction (a "service" whose methods mirror the repository
  one-to-one; a decorator that changes nothing). Each layer should change the level of abstraction.
- **Evidence:** list the matching method pairs.
- **Severity:** `MINOR`, `MAJOR` when it forces every future change to be made twice.

### complexity-pushed-up
- **Look for:** the module makes every caller handle something it could handle itself: required configuration with no
  sensible default, raw error codes every caller must interpret, a setting exposed because the author did not decide.
  Complexity should be pulled down into the module, where it is paid once.
- **Evidence:** show two or more callers repeating the same handling, or a new knob with no requirement behind it.
- **Severity:** `MINOR`; `MAJOR` when three or more call sites repeat logic.

### errors-not-defined-away
- **Look for:** exceptions or error returns for situations that could be normal behaviour (deleting something absent,
  an empty range, a substring past the end). Error handling scattered across many callers when it could be handled
  once at a lower level, or aggregated at one higher level.
- **Evidence:** show the special-case paths and the callers that must handle them.
- **Severity:** `MINOR`; `MAJOR` if callers already handle it inconsistently. If an error is *silently swallowed*
  and that hides a defect, the defect is the finding and may be `BLOCKING` (state the failing scenario).

### interface-too-special
- **Look for:** an interface shaped around one caller's exact situation (method names that describe a UI action, a
  boolean that switches between two unrelated behaviours). A somewhat general-purpose interface is usually simpler and
  deeper. Do not push the other way into speculative generality.
- **Evidence:** show the caller-specific shape and a simpler general form that serves today's callers.
- **Severity:** `MINOR`.

### non-obvious-code
- **Look for:** behaviour a careful reader would mispredict: boolean flag arguments (`send(msg, true, false)`), generic
  containers whose fields have hidden meaning (`Pair`, tuples, `map[string]any`), event handlers whose trigger is far
  away, a method whose name promises less than it does (a getter that writes).
- **Evidence:** quote the call site and state what a reader would wrongly assume.
- **Severity:** `MINOR`; `MAJOR` when the misprediction leads to a plausible bug — name it.

### imprecise-name
- **Look for:** vague names (`data`, `info`, `tmp`, `manager`, `handler`, `util`, `process`), one name used for two
  things, two names for one thing, names that conflict with the project's key terminology.
- **Evidence:** quote the name and what it actually holds or does; propose a precise name.
- **Severity:** `MINOR`; `NOTE` for local variables in short scopes.

### comment-gap
- **Look for:** missing comments for what the code cannot say — units, invariants, why a non-obvious choice was made,
  what a parameter means at the boundary; or comments that only repeat the code.
- **Evidence:** name the fact a reader cannot recover from the code.
- **Severity:** `MINOR` for a public interface; `NOTE` otherwise.

### tactical-shortcut
- **Look for:** "one more special case" patches: a new `if` for one customer, a copied block with one line changed, a
  TODO that defers the design. Tactical code works today and raises the cost of every later change; strategic code
  spends a little more now to keep the design clean.
- **Evidence:** show the special case and the general rule it bypasses.
- **Severity:** `MINOR`; `MAJOR` when the slice adds the second or third copy of the same shortcut.

## Structure checks

### single-responsibility
- **Look for:** a function or class doing two jobs that change for different reasons (parse *and* persist; compute
  *and* format).
- **Evidence:** name the two reasons to change. **Severity:** `MINOR`, `MAJOR` for a new public module.

### dependency-direction
- **Look for:** business or domain logic importing infrastructure detail (HTTP types, SQL, a vendor SDK, the file
  system) when the repository's architecture says it should not.
- **Evidence:** the import line and the rule in `.ai/ARCHITECTURE.md` or the repository convention it breaks.
- **Severity:** `MAJOR` when it breaks a documented rule; `MINOR` otherwise. It becomes the architect's question if
  it changes component ownership.

### hidden-coupling
- **Look for:** two places that must change together with nothing linking them: matching string keys, parallel enums,
  positional argument order shared across modules, global state.
- **Evidence:** both locations and the change that would break one silently. **Severity:** `MAJOR`.

### god-object
- **Look for:** a class or function that the change grows into the place where everything happens (many unrelated
  fields, many collaborators, a long function with several phases).
- **Evidence:** counts (methods, fields, collaborators, lines added this slice) and the responsibilities mixed.
- **Severity:** `MAJOR` when the slice creates it or adds a new unrelated responsibility to it; `NOTE` if pre-existing.

## Severity calibration

- **Clarity in new code is at most `MAJOR`.** It becomes `BLOCKING` only when the unclear code hides a real defect
  (the defect is then the finding: name the failing input or sequence), or breaks a documented architecture rule
  that an ADR marks as non-negotiable.
- `MAJOR`: cost is concrete and recurring — shared knowledge across modules, repeated handling at many call sites,
  hidden coupling, a new god object.
- `MINOR`: real but local — one shallow wrapper, one vague name in a public signature, one missing comment.
- `NOTE`: pre-existing complexity, style preference with a reason, local names.
- If more than half your findings are `MAJOR` on a routine slice, re-check your calibration.

## Finding examples

GOOD (cost shown, location exact, minimum fix):

```text
ID: code-004
Severity: MAJOR
Category: clarity/information-leakage
Location: src/export/csv_writer.py:22-41
Finding: The CSV column order for exported invoices is defined twice: as a list in csv_writer.py:22-30 and again as
  positional indexes in src/import/csv_reader.py:15-19.
Why it matters: Change amplification and an unknown unknown. Adding or reordering a column requires editing both
  files, and nothing in either file points at the other; a one-sided change silently swaps fields on re-import.
Evidence: csv_writer.py:22-30 `COLUMNS = ["id", "date", "amount", ...]`; csv_reader.py:15-19 `row[0]`, `row[1]`,
  `row[2]` with no reference to COLUMNS.
Required resolution: Define the column list once (e.g. in src/export/columns.py) and make the reader map by header
  name from that list.
Confidence: HIGH
Owner: implementer
Status: OPEN
```

BAD (taste, no cost, no location, inflated):

```text
ID: code-009
Severity: BLOCKING
Category: clarity
Location: whole slice
Finding: The code is hard to read and should be cleaned up.
Why it matters: Readability is important.
Evidence: General impression.
Required resolution: Refactor for clarity.
Confidence: MEDIUM
Owner: implementer
Status: OPEN
```

What is wrong with it: no symptom named, no line, no concrete fix, and `BLOCKING` for a clarity concern with no
hidden defect.

## Out of jurisdiction

- Whether a new layer, interface or capability should exist at all → simplicity-review.
- Runtime cost, hot paths, allocation → `performance`.
- Domain vocabulary, aggregates, invariants → `domain-design`.
- Test coverage and test necessity → `test-quality`.
- Failure, concurrency, timeouts → reliability-review. Public API shape and compatibility → contract-review.
- Formatting and lint rules the repository's formatter enforces: never a finding.

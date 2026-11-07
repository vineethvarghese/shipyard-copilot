---
name: lang-packs
description: >
  Language packs for Shipyard. shipyard-code-reviewer, shipyard-security-reviewer, shipyard-implementer and
  shipyard-verifier load it to apply language-specific idioms, error-handling conventions, concurrency pitfalls,
  performance traps, security sinks (with CWE ids) and test conventions on top of their own method. Packs cover
  Python, TypeScript/JavaScript, Go, Rust, Java/Kotlin, C#, C/C++, Swift, Ruby, PHP, SQL, shell, and
  infrastructure as code (Terraform, Kubernetes YAML, Dockerfile). Load only the packs for languages present in
  the diff or the slice's touch set. Not a review method on its own and never a source of findings without
  evidence from the code.
---

# Language packs

Version 1.0.0 · used by code-review, security-review, implementer, verifier

A pack is a short, language-specific checklist. It adds to the role's own method; it does not replace it. A pack
item is a **prompt to look**, not a finding. A finding still needs a location, evidence from the diff or a command
you ran, and a concrete cost (see the shipyard-framework skill, `references/finding-schema.md`).

## Which packs to load

Load a pack only when its language is in the diff (`git diff <featureBranch>...<sliceBranch> --name-only`) or in
the slice's expected touch sets. Most slices need one or two packs. Never load all of them.

| Files | Pack |
|---|---|
| `.py`, `.pyi`, files with a `python` shebang | `references/python.md` |
| `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`, `.cjs` | `references/typescript-javascript.md` |
| `.go` | `references/go.md` |
| `.rs` | `references/rust.md` |
| `.java`, `.kt`, `.kts` | `references/java-kotlin.md` |
| `.cs` | `references/csharp.md` |
| `.c`, `.h`, `.cc`, `.cpp`, `.cxx`, `.hh`, `.hpp`, `.hxx`, `.ipp` | `references/c-cpp.md` |
| `.swift` | `references/swift.md` |
| `.rb`, `.rake`, `.gemspec`, `Gemfile`, `Rakefile` | `references/ruby.md` |
| `.php` | `references/php.md` |
| `.sql`, migration files, and SQL built as strings inside another language | `references/sql.md` |
| `.sh`, `.bash`, files with a `sh`/`bash` shebang, `run:` blocks in CI files | `references/shell.md` |
| `.tf`, `.tfvars`, `.hcl`; YAML with `apiVersion:` and `kind:`; `Dockerfile`, `*.dockerfile`, `Containerfile` | `references/iac.md` |

A `.h` file belongs to the C/C++ pack. If a file type is not listed, work without a pack and say so in one line;
do not borrow a pack for a different language.

## The overriding rule: repository convention beats pack advice

The source-of-truth order in the shipyard-framework skill puts **existing repository convention** above agent
judgment, and a pack is agent judgment. Before you apply a pack item, check what the repository already does
(formatter and linter config, nearby code, `.ai/planning/discovery.md`). If the repository consistently does it
another way, follow the repository and do not raise a finding. The exceptions are security sinks and behaviour
bugs: a repository habit never makes an injectable query or a data race acceptable.

## How each role uses a pack

**Code-reviewer** (`shipyard-code-reviewer`). Read *Error-handling*, *Concurrency*, *Performance traps*,
*Testing conventions* and *Things NOT to flag* for each language in the diff, then check changed and added lines.
Severity guidance:
- A pitfall that makes the code wrong (lost error, data race, leaked resource, wrong null semantics) and is
  reachable from the slice's behaviour → `MAJOR`; `BLOCKING` if it breaks an acceptance criterion or an
  invariant.
- A performance trap → `MAJOR` only with evidence: a benchmark, a profile, a query plan, or a hot path named in
  the ACs plus input sizes that make the cost real. Without that → `MINOR` or `NOTE`, stated as a risk.
- A missed idiom with a real readability or safety cost → `MINOR`. A missed idiom that is pure taste → nothing.
- Anything under *Things NOT to flag* or owned by the formatter → never a finding.

**Security-reviewer** (`shipyard-security-reviewer`). Read *Security sinks and footguns*. For each sink present in
the diff, trace whether attacker-controlled data can reach it. Report only with a concrete path from source to
sink; cite the CWE id the pack gives. Severity comes from impact and reachability (CRITICAL/HIGH/MEDIUM/LOW/
INFORMATIONAL, mapped to BLOCKING/MAJOR/MINOR/NOTE as the framework says), never from the pack line itself. A sink
with no untrusted input reaching it is at most `INFORMATIONAL`.

**Implementer** (`shipyard-implementer`). Before writing code, read *Idioms to follow*, *Error-handling
conventions* and *Concurrency model and pitfalls* for the languages in the code touch set. Write code that already
passes the reviewer's checks. Where the repository's style differs from the pack, match the repository. Run the
formatter and linter the repository configures before you commit.

**Verifier** (`shipyard-verifier`). Read *Testing conventions*. Use it to recognise the test framework, the test
layout and the likely canonical command. The **repository's** canonical command (from `PROJECT.md`,
`discovery.md`, CI config, or the package manifest) always wins over the pack's examples; confirm it by running it
(framework hard rule 5). Use *Performance traps* to choose benchmarks for performance ACs, and *Concurrency* to
decide when a race detector or stress test belongs in the plan.

## Pack layout

Every pack has the same eight sections, in this order: Idioms to follow · Error-handling conventions · Concurrency
model and pitfalls · Performance traps · Security sinks and footguns · Testing conventions · Readability
conventions · Things NOT to flag. Lines are short and concrete. CWE ids are given only where the mapping is well
known.

## Adding or changing a pack

1. Copy `references/TEMPLATE.md` to `references/<language>.md` and fill every section. Keep it to about 60–120
   lines of short bullets.
2. Write in your own words. Name only open, widely used tools and frameworks; no vendor services.
3. Add the file extensions to the table above.
4. Bump this skill's version (new pack = minor; changed advice = patch) and add a `CHANGELOG.md` entry.
5. Add or update an eval under `evals/abilities/lang-packs/` that shows the new advice changes a review.

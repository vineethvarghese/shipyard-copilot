# <Language> pack

Applies to: `<extensions>` · Loaded by: code-review, security-review, implementer, verifier

Copy this file to `references/<language>.md`, replace every `<...>`, and delete these instructions. Keep the eight
sections below, in this order, with these exact headings. Aim for 60–120 lines of short bullets. Write in your own
words. Name only open, widely used tools and frameworks; never vendor services.

## Idioms to follow

- <The way experienced authors write this language: resource cleanup, null/absence handling, data types,
  module layout, naming.>
- <One line each. Say what to do, and briefly why when it is not obvious.>

## Error-handling conventions

- <How errors are signalled (exceptions, result types, return codes) and how they should be propagated.>
- <Patterns that lose errors or context: swallowing, broad catches, dropped return values.>

## Concurrency model and pitfalls

- <The runtime model in one or two lines (threads, event loop, goroutines, actors, global lock).>
- <Concrete pitfalls: races, deadlocks, blocking the loop, leaked tasks, unsafe shared state.>

## Performance traps

- <Trap> — <why it costs> — <how to evidence it: benchmark tool, profiler, query plan, input size>.
- Reviewers raise a trap as MAJOR only with evidence; say what evidence settles it.

## Security sinks and footguns

- <API or construct> — <what goes wrong> (CWE-<id> when well known).
- Cover injection (SQL, command, code), deserialization, path traversal, markup output, crypto and randomness,
  TLS validation, resource exhaustion, and language-specific traps.

## Testing conventions

- Frameworks: <common frameworks>.
- Canonical commands: <e.g. `<tool> test`>. The repository's own canonical command always wins.
- <Layout, naming, fixtures, data-driven tests, race/fuzz/property tools.>

## Readability conventions

- Formatter: <tool>. Linter: <tool>. Type checker if any: <tool>.
- <Naming and layout conventions the community expects.>

## Things NOT to flag

- Anything the configured formatter owns (spacing, wrapping, import order, quote style).
- <Idioms that look odd to outsiders but are standard in this language.>
- <Common false positives for this language's reviewers.>

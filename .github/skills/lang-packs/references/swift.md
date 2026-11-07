# Swift pack

Applies to: `.swift` · Loaded by: code-review, security-review, implementer, verifier

## Idioms to follow

- `let` by default; `var` only when the value changes.
- Unwrap optionals with `guard let` / `if let`; exit early with `guard`.
- Avoid force unwrap `!` and `try!` outside tests and truly impossible cases.
- Prefer value types (`struct`, `enum`) for data; use `class` when identity or shared mutable state is required.
- Use enums with associated values for states; `switch` exhaustively without a catch-all `default` when possible.
- Protocols with extensions for shared behaviour; `some Protocol` over `any Protocol` when the type is fixed.
- `Codable` for serialisation; `defer` for cleanup on every exit path.
- Narrowest access control that works (`private`, `fileprivate`, `internal`).
- Capture `[weak self]` (or `unowned` with care) in escaping closures stored by `self`.

## Error-handling conventions

- Throw errors (`throws`) for recoverable failure; handle with `do`/`catch`.
- `try?` turns every error into `nil`; flag it when the failure matters and is now silent.
- `try!` and `fatalError` crash; use only where failure is a programming error.
- Use `precondition` for caller contract checks; `assert` disappears in optimised builds.
- Error enums conform to `Error` and carry enough context to act on.
- `Result` is for storing or passing outcomes; do not wrap synchronous throwing code in it without a reason.

## Concurrency model and pitfalls

- Structured concurrency: `async`/`await`, task groups, and `actor`s; UI state lives on `@MainActor`.
- Strict concurrency checking flags non-`Sendable` values crossing isolation; do not silence it with
  `@unchecked Sendable` without a written argument.
- Actor reentrancy: state can change across any `await` inside an actor method; re-check after awaiting.
- Unstructured `Task { }` is not cancelled automatically; keep the handle or tie it to a lifecycle.
- `Task.detached` drops the caller's actor and priority; use it only on purpose.
- Blocking with semaphores or `sleep` inside async code can deadlock the cooperative pool.
- Long-running work must check `Task.isCancelled` or call `try Task.checkCancellation()`.
- Older dispatch-queue code: unsynchronised shared state across queues is a data race.
- Retain cycles between objects and stored closures leak memory.

## Performance traps

- Copy-on-write surprises: mutating a copy of a large array or dictionary copies the whole buffer.
  Evidence: a benchmark or allocation profile.
- `String.count` and character indexing are O(n); avoid repeated index arithmetic in loops.
- `any Protocol` existentials in hot paths add indirection and allocation; generics can specialise.
- `reduce` that builds arrays — use `reduce(into:)` or a loop.
- Heavy work on the main actor stalls the UI. Evidence: frame timing or a profile of a release build.
- Measure optimised builds only; debug builds distort Swift performance heavily.
- Evidence tools: `measure {}` blocks in XCTest, a benchmark package, a release-build profiler.

## Security sinks and footguns

- Unarchiving untrusted data without secure coding (CWE-502).
- `Process` with a shell and interpolated user input (CWE-78).
- SQL strings built by interpolation in database wrappers (CWE-89); bind parameters.
- Web views loading untrusted HTML or exposing native bridges to page script (CWE-79, CWE-749).
- URL session delegates that accept any server certificate (CWE-295).
- Secrets or tokens in user defaults, plists, or logs (CWE-312, CWE-532); use the platform's secure store.
- Force unwrap or `try!` on untrusted input is a crash, i.e. a denial of service (CWE-476 class).
- `Unsafe*Pointer` and manual memory binding (CWE-119).
- Seeded or custom random generators for secrets (CWE-338); use the system generator.
- File paths built from user input without containment checks (CWE-22).

## Testing conventions

- Frameworks: XCTest and Swift Testing (`@Test`, `#expect`, `#require`).
- Canonical commands: `swift test` for packages; app targets run through the repository's build scheme command.
- Async tests are `async` functions; avoid fixed sleeps, use expectations or confirmations.
- Parameterised tests with Swift Testing `arguments:`; one behaviour per test.
- Inject clocks and network clients through protocols so tests stay deterministic.

## Readability conventions

- Formatter: `swift-format`. Linter: SwiftLint when configured.
- `lowerCamelCase` values and functions, `UpperCamelCase` types and protocols; argument labels read as phrases.

## Things NOT to flag

- Omitting `self.` where the compiler allows it; implicit returns in single-expression bodies.
- Shorthand closure arguments (`$0`) in short closures; trailing closure syntax.
- `guard` with early return as the main control-flow style.
- `_ =` to discard a result on purpose; `@discardableResult` on fluent APIs.
- Implicitly unwrapped optionals for values set up by the framework before first use, when the repository does so.
- Formatting — the formatter owns it.

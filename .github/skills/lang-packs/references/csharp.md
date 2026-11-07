# C# pack

Applies to: `.cs` · Loaded by: code-review, security-review, implementer, verifier

## Idioms to follow

- Dispose with `using` declarations or blocks; `await using` for async-disposable resources.
- Async all the way: an `async` method returns `Task`/`ValueTask`, and callers `await` it.
- Accept a `CancellationToken` (usually last) on async APIs and pass it to every call that takes one.
- Enable nullable reference types and respect the warnings; avoid the `!` suppression without a reason.
- `record` types for values; `init`-only and `readonly` members for immutability.
- Pattern matching (`is`, `switch` expressions) over cascades of casts.
- LINQ where it reads clearly; a plain loop where it is a hot path or has side effects.
- Constructor injection; `nameof(...)` instead of string literals for member names.
- Guard arguments with `ArgumentNullException.ThrowIfNull` and similar helpers.

## Error-handling conventions

- Rethrow with `throw;`, not `throw ex;`, to keep the original stack trace.
- Catch specific exception types; catch `Exception` only at a boundary that logs and translates.
- Use exception filters (`catch (X e) when (...)`) instead of catch-and-rethrow.
- Use `TryParse`/`TryGetValue` patterns where failure is expected; do not use exceptions for control flow.
- Keep the inner exception when wrapping (`new XException(msg, inner)`).
- `OperationCanceledException` is expected on cancellation; do not log it as an error or swallow it.

## Concurrency model and pitfalls

- Thread pool plus `async`/`await`; some app types have a synchronization context that resumes on one thread.
- `async void` is only for event handlers; its exceptions cannot be caught and can end the process.
- Blocking on tasks (`.Result`, `.Wait()`, `GetAwaiter().GetResult()`) can deadlock under a synchronization
  context and starves the thread pool in servers.
- Libraries commonly use `ConfigureAwait(false)`; follow the repository's convention.
- You cannot `await` inside `lock`; use `SemaphoreSlim.WaitAsync` for async mutual exclusion.
- `Dictionary<,>` and `List<>` are not thread-safe; use concurrent collections or confinement.
- `ConcurrentDictionary.GetOrAdd` may run the value factory more than once; wrap expensive factories in `Lazy<T>`.
- Fire-and-forget tasks lose exceptions; observe them or use a hosted background worker.
- `Task.Run` around synchronous work in a server request only moves the block to another pool thread.

## Performance traps

- Multiple enumeration of an `IEnumerable` that re-runs a query. Evidence: query count or a counting test double.
- `.Count() > 0` on a sequence instead of `.Any()`; LINQ allocations in tight loops.
- String concatenation in loops — use `StringBuilder`. Evidence: allocation counts from a micro-benchmark.
- Boxing value types through `object` or non-generic interfaces in hot paths.
- A new HTTP client instance per request exhausts sockets; share one or use a client factory.
- ORM lazy loading inside loops (N+1). Evidence: SQL log or query count in a test.
- Large arrays allocated per call; consider pooling, `Span<T>` or `Memory<T>` with evidence.
- Evidence: a micro-benchmark harness run in Release configuration, a profiler, or runtime allocation counters.

## Security sinks and footguns

- SQL built by concatenation or interpolation into command text (CWE-89); use parameters.
- `BinaryFormatter`, and JSON serializers configured with type-name handling, on untrusted data (CWE-502).
- XML readers with DTD processing enabled or an unrestricted resolver (CWE-611).
- `Process.Start` with a shell and user input in the argument string (CWE-78); use an argument list.
- `Path.Combine(root, user)` — an absolute `user` replaces `root` (CWE-22). Resolve with `Path.GetFullPath`
  and check the prefix.
- `System.Random` for tokens or keys (CWE-338); use `RandomNumberGenerator`.
- Certificate validation callbacks that always return `true` (CWE-295).
- Raw HTML output helpers with user data (CWE-79).
- `Regex` on user input without a timeout or the non-backtracking option (CWE-1333).
- MD5/SHA-1 or unsalted hashes for passwords (CWE-916).
- Redirects to user-supplied URLs without a local-URL check (CWE-601).
- Exception details or stack traces returned to clients (CWE-209).

## Testing conventions

- Frameworks: xUnit, NUnit or MSTest through the repository's canonical test command.
- Data-driven tests: `[Theory]`/`[InlineData]`, `[TestCase]`, or `[DataRow]` depending on the framework.
- Async tests return `Task`; never `async void` test methods.
- Use the repository's mocking library and fake clock abstraction instead of real time.
- Integration tests that need a database or network are tagged so the fast suite can exclude them.

## Readability conventions

- Formatting and analyzer rules come from `.editorconfig` and the build's configured analyzers; follow them.
- `PascalCase` types, methods and properties; `camelCase` locals and parameters; `_camelCase` private fields is a
  common convention; interfaces start with `I`.
- `Async` suffix on async methods where the repository uses it.

## Things NOT to flag

- `var` when the type is obvious; target-typed `new()`; file-scoped namespaces.
- Expression-bodied members; `_` discards; `is null` / `is not null`.
- `#pragma warning disable` with a narrow scope and a reason.
- `ConfigureAwait(false)` present or absent, when it matches the repository's rule.
- Formatting and `using` order — `.editorconfig` and the formatter own them.

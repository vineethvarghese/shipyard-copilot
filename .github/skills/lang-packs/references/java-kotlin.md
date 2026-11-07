# Java and Kotlin pack

Applies to: `.java`, `.kt`, `.kts` · Loaded by: code-review, security-review, implementer, verifier

## Idioms to follow

- Java: close resources with try-with-resources; never in a hand-written `finally` that can mask the first error.
- Java: `Optional` for return values that may be absent; not for fields, parameters or collections.
- Java: records for plain data; immutable collections (`List.of`, `Map.copyOf`); `final` fields.
- Java: override `equals` and `hashCode` together; switch expressions and sealed types for closed variants.
- Kotlin: `val` over `var`; nullable types instead of sentinels; avoid `!!` — use `?.`, `?:`, `requireNotNull`.
- Kotlin: `data class` for values; `sealed` hierarchies with exhaustive `when`; `use {}` for closeable resources.
- Kotlin: scope functions (`let`, `apply`, `also`) only when they make code clearer; avoid nesting them.
- Inject dependencies through constructors; avoid static mutable singletons.

## Error-handling conventions

- Catch specific exceptions; `catch (Exception e)` / `catch (Throwable t)` only at a boundary that logs and maps.
- Never swallow an exception silently; keep the cause when wrapping (`new XException(msg, e)`).
- On `InterruptedException`, restore the flag (`Thread.currentThread().interrupt()`) or rethrow.
- Do not `return` or `throw` from `finally`; it discards the original exception.
- Kotlin has no checked exceptions; document thrown exceptions on public APIs.
- Kotlin `runCatching` and broad `catch (e: Exception)` also catch `CancellationException`, which breaks
  coroutine cancellation; rethrow it.
- Do not use exceptions for normal control flow.

## Concurrency model and pitfalls

- Platform threads, executors, and (Java 21+) virtual threads; Kotlin adds coroutines with structured concurrency.
- `HashMap`, `ArrayList`, `SimpleDateFormat` are not thread-safe; use concurrent collections or confinement.
- Check-then-act on a `ConcurrentHashMap` (`if (!containsKey) put`) is a race; use `computeIfAbsent`/`merge`.
- Double-checked locking needs a `volatile` field.
- Do not `synchronized` on a boxed value, a string literal, or a non-final field.
- Shut down every `ExecutorService` you create; unshut pools leak threads.
- `CompletableFuture` chains drop exceptions unless something calls `join`/`get` or handles them.
- `ThreadLocal` in pooled or virtual threads leaks state between tasks unless cleared.
- Kotlin: `GlobalScope` launches escape structured concurrency; `runBlocking` inside a coroutine can deadlock;
  blocking I/O belongs on an I/O dispatcher.

## Performance traps

- String concatenation in a loop — use `StringBuilder` / `buildString`. Evidence: JMH benchmark.
- Autoboxing in hot loops (`List<Integer>`, `Map<Long, ...>`). Evidence: allocation profile.
- `String.matches`/`replaceAll` compile the regex on every call; hoist a `Pattern`.
- ORM lazy loading inside loops (N+1). Evidence: SQL log query count in the test run.
- Building log messages eagerly; use parameterized logging (`log.debug("x={}", x)`).
- Unbounded in-memory caches and collections that only grow.
- Evidence tools: JMH for micro-benchmarks, async-profiler or the JDK Flight Recorder, GC logs.

## Security sinks and footguns

- `Statement.execute` / string-built JPQL or SQL (CWE-89); use `PreparedStatement` or bound parameters.
- `ObjectInputStream.readObject` on untrusted data, and JSON mappers with polymorphic default typing (CWE-502).
- XML parsers with DTDs or external entities enabled — the default for several JDK factories (CWE-611).
- `Runtime.exec` / `ProcessBuilder` invoking `sh -c` with user data (CWE-78).
- Expression-language evaluation of user input (template or rule engines) (CWE-917).
- `new File(base, userPath)` without normalise-and-check (CWE-22); archive extraction ("zip slip") (CWE-22).
- `java.util.Random` for tokens (CWE-338); use `SecureRandom`.
- Trust managers or hostname verifiers that accept everything (CWE-295).
- `Class.forName(userInput)` or reflection driven by input (CWE-470).
- Binding request parameters straight onto entities (mass assignment) (CWE-915).
- Logging user input without neutralising line breaks (CWE-117).

## Testing conventions

- Frameworks: JUnit 5 (Jupiter), TestNG, Kotest; mocking with Mockito or MockK; assertions with AssertJ.
- Canonical commands: `mvn test` / `./mvnw test`, `gradle test` / `./gradlew test`; integration tests often
  under `mvn verify` or a separate Gradle task.
- `@ParameterizedTest` for data-driven cases; `@Nested` to group behaviour.
- Coroutine code: use the coroutine test library's virtual time instead of `delay` in tests.
- Container-backed integration tests need a container runtime; mark them so the fast suite can skip them.

## Readability conventions

- Java formatter: whatever the build configures (Spotless, a checked-in formatter profile). Linters: Checkstyle,
  PMD, SpotBugs.
- Kotlin: `ktlint` and `detekt`.
- `camelCase` members, `PascalCase` types, `UPPER_SNAKE_CASE` constants; packages lower-case.

## Things NOT to flag

- `var` for local type inference (Java 10+) when the type is clear from the right-hand side.
- Kotlin `it` in short lambdas; trailing lambdas; expression-bodied functions.
- Lombok or annotation processors the repository already uses.
- Static imports in tests (`assertThat`, `when`).
- `@Suppress`/`@SuppressWarnings` with a specific key and a reason.
- Missing `final` on locals or parameters, unless the repository enforces it.
- Formatting and import order — the formatter owns them.

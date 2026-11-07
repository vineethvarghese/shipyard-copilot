# C and C++ pack

Applies to: `.c`, `.h`, `.cc`, `.cpp`, `.cxx`, `.hh`, `.hpp`, `.hxx`, `.ipp` · Loaded by: code-review, security-review, implementer, verifier

## Idioms to follow

- C++: RAII for every resource; `std::unique_ptr` by default, `std::shared_ptr` only for real shared ownership.
- C++: rule of zero (let members manage themselves), otherwise rule of five.
- C++: `const` correctness; references for non-null parameters; `std::span`/`std::string_view` for views.
- C++: standard containers over raw arrays; `enum class`; `nullptr`; `override`; `explicit` single-argument
  constructors.
- C++: watch view lifetimes — a `string_view` or `span` must not outlive what it points to.
- C: one clear owner for each allocation, documented at the API; pair every `malloc` with one `free`.
- C: `size_t` for sizes and indexes; `snprintf` over `sprintf`; check every return value.
- C: a single `goto cleanup` exit path is the accepted way to release resources.
- Headers: include guards or `#pragma once`; include what you use.

## Error-handling conventions

- C: return codes plus `errno`; check them, including `malloc`, `fclose` and `write` results.
- C++: exceptions or error codes as the codebase decides (some build with exceptions off); do not mix within a
  module.
- Destructors must not throw; move constructors should be `noexcept`.
- `[[nodiscard]]` on functions whose result must be checked; `std::expected` / `std::optional` where available.
- Never ignore a partial `read`/`write` count.

## Concurrency model and pitfalls

- Native threads; a data race is undefined behaviour, not just a wrong value.
- Protect shared data with `std::mutex` and `std::lock_guard`/`std::scoped_lock`; lock several mutexes together
  with `scoped_lock` to avoid ordering deadlocks.
- Condition variables wake spuriously; always wait with a predicate.
- A joinable `std::thread` destroyed without `join` calls `std::terminate`; prefer `std::jthread`.
- `volatile` is not a synchronisation tool; use `std::atomic` and think about memory order.
- Static initialisation order across translation units is unspecified.
- Signal handlers may only call async-signal-safe functions.
- Iterator and reference invalidation after container growth is a classic cross-thread and single-thread bug.

## Performance traps

- Passing large objects by value where `const&` or a move would do. Evidence: a micro-benchmark or profile.
- Missing `reserve` before filling a vector of known size.
- `std::endl` in loops forces a flush; use `'\n'`.
- Heap allocation inside hot loops; `shared_ptr` copies (atomic reference counts) in hot paths.
- False sharing between threads writing neighbouring fields.
- Benchmarks from unoptimised builds are not evidence; measure an optimised build (`-O2` or the release config).
- Evidence tools: `perf`, `valgrind --tool=callgrind`, a micro-benchmark library, generated assembly.

## Security sinks and footguns

- `strcpy`, `strcat`, `sprintf`, `gets`, unbounded `scanf("%s")` (CWE-120, CWE-676).
- Out-of-bounds write and read (CWE-787, CWE-125); off-by-one on buffer sizes and terminators.
- Use after free and double free (CWE-416, CWE-415), including dangling views and invalidated iterators.
- Integer overflow in size calculations before allocation (CWE-190, CWE-680).
- Signed/unsigned conversion of lengths (CWE-195).
- User-controlled format strings to `printf`-family calls (CWE-134).
- NULL pointer dereference (CWE-476); use of uninitialised memory (CWE-457).
- `system()`, `popen()` with built-up command strings (CWE-78).
- Check-then-use on files (`access` then `open`) (CWE-367).
- `memset` to clear secrets may be optimised away (CWE-14); use an explicit secure-zero function.
- Run sanitizers and fuzzers on parsers of untrusted input.

## Testing conventions

- Frameworks: Catch2, doctest, or the xUnit-style framework the repository uses; Check or cmocka for C.
- Canonical commands: `ctest --test-dir build` after the configure/build step, or `make test` / `make check`.
- Run tests under AddressSanitizer and UndefinedBehaviorSanitizer (`-fsanitize=address,undefined`), and
  ThreadSanitizer for concurrent code; `valgrind` memcheck where sanitizers are not available.
- Fuzz input parsers with libFuzzer or AFL++ when the repository has a fuzz target.
- Build tests with the same warning flags as production.

## Readability conventions

- Formatter: `clang-format` with the checked-in config. Linters: `clang-tidy`, `cppcheck`.
- Compile with warnings on (`-Wall -Wextra`, often `-Werror` in CI).
- Naming follows the repository's style guide; it varies widely across projects.

## Things NOT to flag

- `goto cleanup` in C; `do { ... } while (0)` in multi-statement macros.
- `auto` when the type is obvious or unspellable; `!ptr` for null checks.
- `static` functions at file scope; anonymous namespaces in C++.
- C-style code in a C codebase, and C++ standard level as configured by the build.
- Brace and spacing style — `clang-format` owns it.

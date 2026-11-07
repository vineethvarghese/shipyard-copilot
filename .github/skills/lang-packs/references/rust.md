# Rust pack

Applies to: `.rs` · Loaded by: code-review, security-review, implementer, verifier

## Idioms to follow

- Return `Result`/`Option` and propagate with `?`; reserve panics for broken invariants.
- Take borrowed views in parameters: `&str` over `&String`, `&[T]` over `&Vec<T>`, `impl AsRef<Path>` for paths.
- Model states with `enum` and `match` exhaustively; avoid a `_ =>` arm that hides new variants.
- Use newtypes for IDs and units so the compiler catches mix-ups.
- Implement `From` for error conversions so `?` works; derive common traits (`Debug`, `Clone`, `PartialEq`).
- Prefer iterators and adapters over index loops when it reads clearly.
- Use RAII: cleanup belongs in `Drop`, not in a manual `close()` callers may forget.
- Keep `unsafe` blocks small, wrapped in a safe API, each with a `// SAFETY:` comment stating the invariant.

## Error-handling conventions

- No `unwrap()`/`expect()` on fallible input in library or service code; `expect("reason")` only where failure
  is a bug, and the message says why it cannot fail.
- Libraries define typed errors (often with `thiserror`); applications may use `anyhow`-style errors with context.
- Add context when converting errors; do not map every error to a string.
- Mark results that must be used with `#[must_use]`; never discard a `Result` with `let _ =` without a comment.
- Slicing a `&str` at a non-character boundary panics; indexing out of bounds panics. Use `get`.

## Concurrency model and pitfalls

- `Send`/`Sync` make data races a compile error in safe code; deadlocks and logic races are still possible.
- Shared state is `Arc<Mutex<T>>` or `Arc<RwLock<T>>`; keep the guard's scope short.
- Holding a `std::sync::MutexGuard` across `.await` blocks the executor thread and makes the future `!Send`;
  use the async runtime's mutex or drop the guard first.
- Blocking work (file I/O, CPU, sync clients) inside async code stalls the executor; use the runtime's
  blocking-task API.
- A panic while holding a `std` mutex poisons it; decide how to handle `PoisonError`.
- In `select!`-style macros, branches that are not cancellation-safe can lose data when another branch wins.
- Spawned tasks keep running when their handle is dropped; keep handles or use a task set to stop them.
- Lock ordering across several mutexes must be consistent.

## Performance traps

- Needless `.clone()`, `.to_string()`, `.to_vec()` to satisfy the borrow checker in a hot path.
  Evidence: allocation counts in a benchmark.
- `collect()` into a `Vec` only to iterate again; chain the iterator instead.
- Missing `Vec::with_capacity` / `String::with_capacity` when the size is known.
- `format!` and `Box<dyn Trait>` in tight loops.
- Benchmarking debug builds — numbers from `cargo build` without `--release` are not evidence.
- Evidence tools: `cargo bench` (often with criterion), a flamegraph of a release build.

## Security sinks and footguns

- `unsafe` code: raw pointer use, unchecked indexing, lifetime extension (CWE-119, CWE-416).
- `std::mem::transmute` and unchecked casts between types (CWE-843).
- Integer overflow wraps silently in release builds (CWE-190); use `checked_*`/`saturating_*` on untrusted values.
- `Command::new("sh").arg("-c").arg(user)` (CWE-78); pass arguments individually.
- SQL built with `format!` (CWE-89); use the driver's bind parameters.
- Joining user paths without containment checks (CWE-22).
- Deserializing untrusted input with no size or depth limits (CWE-770).
- `panic!` reachable from untrusted input in a server is a denial of service.
- FFI boundaries: null pointers, ownership transfer, and string encoding.
- Check dependencies with `cargo audit` or `cargo deny` when configured.

## Testing conventions

- Unit tests in a `#[cfg(test)] mod tests` beside the code; integration tests in `tests/`; doc tests in `///`.
- Canonical commands: `cargo test` (add `--all-features` or `--workspace` if the repository does);
  `cargo nextest run` where configured.
- Property tests with `proptest` or `quickcheck`; run `unsafe` code under `cargo miri test` when available.
- `#[should_panic(expected = "...")]` only for real panics; prefer asserting on `Err` values.
- Async tests use the runtime's test attribute that the repository already uses.

## Readability conventions

- Formatter: `rustfmt` (`cargo fmt --check`). Linter: `clippy` (`cargo clippy -- -D warnings` if the CI does).
- `snake_case` functions and modules, `PascalCase` types and traits, `SCREAMING_SNAKE_CASE` constants.

## Things NOT to flag

- Shadowing to transform a value (`let line = line.trim();`).
- No explicit `return` on the final expression; turbofish `::<T>`; `'_` anonymous lifetimes.
- `unwrap()`/`expect()` in tests, examples and build scripts.
- `#[allow(clippy::...)]` with a stated reason.
- Several `impl` blocks for one type, and `matches!` for simple pattern tests.
- Formatting — `rustfmt` owns it.

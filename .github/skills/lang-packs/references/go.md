# Go pack

Applies to: `.go` · Loaded by: code-review, security-review, implementer, verifier

## Idioms to follow

- Handle errors where they occur and return early; keep the happy path unindented.
- Accept interfaces, return concrete types. Keep interfaces small and define them where they are consumed.
- Make the zero value useful; avoid constructors that only set defaults.
- `context.Context` is the first parameter of anything that does I/O or may block; never store it in a struct.
- `defer` cleanup right after acquiring the resource (`defer rows.Close()`, `defer mu.Unlock()`).
- Short, lower-case package names; no `util`/`common` dumping grounds; no stutter (`cache.Cache` is fine,
  `cache.CacheClient` is not).
- No `Get` prefix on getters; `MixedCaps`, not underscores; exported names have doc comments.
- Use `errgroup` for a group of goroutines that can fail together.

## Error-handling conventions

- Check every returned error. `_ =` on an error needs a comment saying why it is safe.
- Wrap with context: `fmt.Errorf("load config %q: %w", path, err)`. Use `%w` only when callers may inspect it.
- Compare with `errors.Is` / `errors.As`, never by string or `==` on wrapped errors.
- Either log an error or return it, not both — double logging hides the real source.
- `panic` is for programmer errors and impossible states; libraries do not panic on bad input.
- `defer f.Close()` on a file you wrote drops the close error, which can carry the write failure; check it.
- Sentinel errors are package-level `var ErrX = errors.New(...)`; custom types when callers need fields.

## Concurrency model and pitfalls

- Goroutines are cheap but not free; every goroutine needs a clear way to stop (context, closed channel).
- Goroutine leak: a send or receive on a channel nobody will ever service. Check every early return path.
- Concurrent map writes crash the process; guard maps with a mutex or use `sync.Map` for its narrow use cases.
- Do not copy a value that contains a `sync.Mutex` or `sync.WaitGroup` (`go vet` copylocks check).
- Call `wg.Add` before starting the goroutine, not inside it.
- Only the sender closes a channel; closing twice or sending on a closed channel panics.
- Loop variables are per-iteration from Go 1.22; in modules with an older `go` directive, capturing them in a
  closure shares one variable.
- A `select` with `default` in a loop is a busy spin.
- Holding a mutex across I/O or a channel operation invites deadlock and latency spikes.

## Performance traps

- String building with `+` in a loop — use `strings.Builder`. Evidence: `go test -bench . -benchmem`.
- `append` in a loop when the final size is known — preallocate with `make([]T, 0, n)`.
- Unneeded `[]byte` ↔ `string` conversions copy data. Evidence: `-benchmem` allocation counts.
- Values escaping to the heap in a hot path. Evidence: `go build -gcflags=-m`.
- `defer` inside a long loop holds every resource until the function returns.
- Reflection-heavy encoding in hot paths. Evidence: CPU profile via `pprof`.
- Compare benchmark runs with `benchstat`; one run is not evidence.

## Security sinks and footguns

- `exec.Command("sh", "-c", userString)` (CWE-78). `exec.Command(name, args...)` does not use a shell; keep it that way.
- `db.Query(fmt.Sprintf(...))` (CWE-89); use placeholders.
- `text/template` to produce HTML (CWE-79); use `html/template`. `template.HTML(userData)` defeats escaping.
- `filepath.Join(base, userPath)` does not stop `..` (CWE-22); use `os.Root` (1.24+) or `filepath.IsLocal`.
- Archive extraction without checking entry names (CWE-22, "zip slip").
- `math/rand` for secrets (CWE-338); use `crypto/rand`.
- `tls.Config{InsecureSkipVerify: true}` (CWE-295).
- `http.Server` without read/write/idle timeouts, or the default `http.ListenAndServe` in production (CWE-400).
- `io.ReadAll` on request bodies without `http.MaxBytesReader` (CWE-770).
- Narrowing integer conversions of untrusted values (`int64` → `int32`) (CWE-681).
- Server-side HTTP requests to user-supplied URLs (CWE-918).
- `unsafe` and `cgo` code needs the same review depth as C.
- Check dependencies with `govulncheck ./...`; static checks with `gosec` when configured.

## Testing conventions

- Framework: the standard `testing` package; assertion helpers only if the repository already uses them.
- Canonical commands: `go test ./...`; add `-race` for concurrent code (`go test -race ./...`); `go vet ./...`.
- Table-driven tests with `t.Run(name, ...)`; `t.Helper()` in helpers; `t.Cleanup` over manual teardown.
- `t.Parallel()` only when the test shares no mutable global state.
- `net/http/httptest` for handlers and clients; golden files under `testdata/`.
- Fuzz parsers with `go test -fuzz=FuzzX`; benchmarks are `BenchmarkX(b *testing.B)`.

## Readability conventions

- Formatter: `gofmt` (or `goimports`). Linters: `go vet`, `staticcheck`, `golangci-lint` when configured.
- Comments on exported names start with the name.

## Things NOT to flag

- Repeated `if err != nil { return ... }` blocks — that is the language's error style.
- Short names in small scopes (`i`, `r`, `w`, `ctx`, `err`) and one- or two-letter receiver names.
- Blank imports for side effects (`_ "image/png"`, database drivers).
- Naked returns in very short functions with named results.
- No exceptions, no generics where an interface is simpler, no getters/setters.
- Formatting and import grouping — `gofmt` owns them.

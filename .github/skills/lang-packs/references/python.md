# Python pack

Applies to: `.py`, `.pyi`, files with a `python` shebang · Loaded by: code-review, security-review, implementer, verifier

## Idioms to follow

- Manage resources with `with` (files, locks, connections, temp dirs); never rely on garbage collection to close.
- Use `pathlib.Path` for paths; `is None` / `is not None` for absence checks.
- Prefer `dataclasses` (or the repository's model library) over bare dicts for structured data.
- Type-annotate public functions; keep annotations honest (`Optional[X]` / `X | None` when `None` is possible).
- Use comprehensions for simple transforms; switch to a loop when there is more than one condition or side effect.
- Use `enumerate`, `zip` (`strict=True` on 3.10+ when lengths must match), `dict.get`, `collections` helpers.
- Never use a mutable default argument (`def f(x=[])`); default to `None` and create inside.
- Put module-level side effects behind `if __name__ == "__main__":`.
- Use the `logging` module with lazy arguments (`log.info("x=%s", x)`), not `print`, in library and service code.

## Error-handling conventions

- Catch the narrowest exception that you can actually handle; never a bare `except:` (it also catches
  `KeyboardInterrupt` and `SystemExit`).
- `except Exception: pass` hides bugs; if you must ignore, log with `log.exception` or comment why.
- Chain causes with `raise NewError(...) from err`; use `from None` only when hiding the cause is deliberate.
- Keep `try` blocks small; put success-path code in `else`, cleanup in `finally` or a context manager.
- Define domain exceptions in one module; do not signal failure with sentinel return values mixed with data.
- `assert` is removed under `python -O`; never use it for input validation or security checks.

## Concurrency model and pitfalls

- The standard build has a global interpreter lock: threads help with I/O, not CPU. Use processes for CPU work.
  (The optional free-threaded build removes the lock; do not assume it unless the repository targets it.)
- `asyncio`: a blocking call (`time.sleep`, sync HTTP/DB client, heavy CPU) inside `async def` stalls every task.
  Use async libraries or `asyncio.to_thread`.
- A coroutine called without `await` never runs; the runtime only warns.
- Keep a reference to tasks from `asyncio.create_task`; unreferenced tasks can be garbage-collected mid-flight.
- Prefer `asyncio.TaskGroup` (3.11+) over bare `gather`, so one failure cancels siblings and errors surface.
- Shared mutable state across threads needs a `Lock`; "atomic because of the lock" reasoning is fragile.
- Swallowing `asyncio.CancelledError` breaks cancellation; re-raise it after cleanup.
- `multiprocessing` with the `spawn` start method re-imports the main module; guard entry points.

## Performance traps

- Membership tests on a `list` inside a loop are O(n) each — use a `set`/`dict`. Evidence: input sizes in the AC.
- Building strings with `+=` in a loop — use `"".join(...)`. Evidence: `python -m timeit` on realistic sizes.
- ORM lazy loading in a loop (N+1 queries). Evidence: query count in the test log or a query counter fixture.
- Row-wise iteration over dataframes (`iterrows`, `apply` with Python lambdas) where a vectorised op exists.
- Reading a whole file or response into memory when streaming would do. Evidence: input size bounds.
- Repeated `copy.deepcopy`, regex compile, or JSON parse inside hot loops.
- Evidence tools: `python -m cProfile`, `py-spy`, `pytest-benchmark`, `tracemalloc` for memory.

## Security sinks and footguns

- `eval`, `exec`, `compile` on untrusted input (CWE-95).
- `pickle`, `marshal`, `shelve`, `dill` loads of untrusted data (CWE-502).
- `yaml.load` without `SafeLoader` / use `yaml.safe_load` (CWE-502).
- `subprocess` with `shell=True` and interpolated input, `os.system`, `os.popen` (CWE-78). Pass an argument list.
- SQL built with f-strings, `%` or `.format` (CWE-89). Use driver parameters.
- `tarfile.extractall` / `zipfile` with untrusted archives — path traversal (CWE-22); use `filter="data"` (3.12+).
- `os.path.join(base, user)` — an absolute `user` replaces `base` (CWE-22). Resolve and check containment.
- XML from untrusted sources with stdlib parsers — entity expansion (CWE-776); use `defusedxml`.
- `random` for tokens or passwords (CWE-338); use `secrets`.
- `hashlib.md5`/`sha1` or unsalted hashes for passwords (CWE-916); use a password KDF.
- `requests`/`httpx` with `verify=False` (CWE-295).
- Template engines with autoescape off, or `Markup()` around user data (CWE-79).
- `tempfile.mktemp` (CWE-377); use `NamedTemporaryFile` or `mkstemp`.
- Web framework debug mode reachable in production (CWE-489).

## Testing conventions

- Frameworks: `pytest` (most common), `unittest` (stdlib), `hypothesis` for property tests.
- Canonical commands: `pytest`, `python -m pytest`, `python -m unittest discover`, or `tox` / `nox` sessions.
- Use fixtures, `tmp_path`, `monkeypatch`, and `pytest.mark.parametrize` for data-driven cases.
- Assert exceptions with `pytest.raises(..., match=...)`; check the message only when it is part of the contract.
- Async tests need the plugin the repository uses (`pytest-asyncio`, `anyio`); check its mode setting.
- Freeze time and seed randomness instead of sleeping or retrying.

## Readability conventions

- Formatter: `ruff format` or `black`. Imports: `ruff` or `isort`. Linter: `ruff` or `flake8`/`pylint`.
- Type checker: `mypy` or `pyright` when configured; run it if the repository does.
- PEP 8 naming: `snake_case` functions and variables, `PascalCase` classes, `UPPER_CASE` constants.

## Things NOT to flag

- Formatting, line length, quote style and import order — the formatter owns them.
- `if not items:` to test for empty; `_` for unused values; leading `_` for internal names.
- EAFP (`try`/`except KeyError`) instead of look-before-you-leap; both are idiomatic.
- `try`/`except`/`else`, the walrus operator, and `for`/`else` when used plainly.
- Imports under `if TYPE_CHECKING:`; `# noqa` / `# type: ignore[code]` with a specific code.
- `__dunder__` methods and `@property` used as intended.

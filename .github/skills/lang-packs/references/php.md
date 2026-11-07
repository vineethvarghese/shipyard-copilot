# PHP pack

Applies to: `.php` · Loaded by: code-review, security-review, implementer, verifier

## Idioms to follow

- `declare(strict_types=1);` at the top of files where the repository uses it.
- Type declarations on parameters, returns and properties; nullable types (`?T`) only when null is valid.
- Strict comparison `===` / `!==`; loose `==` juggles types in surprising ways.
- `??` for defaults; `?->` for optional chains.
- Constructor property promotion, `readonly` properties, enums (8.1+) and `match` over long `switch`.
- PSR-4 autoloading through Composer; one class per file; namespaces match directories.
- Dependency injection through constructors; no `global` and no static service locators in new code.
- Escape output at the point of rendering, using the template engine's auto-escaping.

## Error-handling conventions

- Throw exceptions for failures; catch `\Throwable` only at the top-level handler.
- Never use the `@` error-suppression operator to hide failures.
- Many built-ins return `false` on failure: check with `=== false` (`strpos` can return `0`).
- `json_decode`/`json_encode` with `JSON_THROW_ON_ERROR`; otherwise check `json_last_error()`.
- Convert warnings to exceptions with an error handler if the repository does; do not rely on warnings.
- Keep the previous exception when wrapping (`new X($msg, 0, $previous)`).

## Concurrency model and pitfalls

- Classic deployment is share-nothing: each request starts fresh. Long-running worker runtimes keep static and
  global state between requests — check which one the repository uses.
- In worker runtimes, static caches, singletons and open connections leak data between users.
- File-based sessions lock per session; long requests block other requests from the same user.
- Read-modify-write on rows needs transactions with row locks or an atomic `UPDATE`.
- Scheduled jobs can overlap; guard with a lock.

## Performance traps

- Queries inside loops (N+1) through the ORM. Evidence: query log or query count in a test.
- `in_array` / `array_search` on large arrays inside loops; flip to keys and use `isset`.
- Loading whole files or result sets into memory; use generators or cursors.
- Production without opcache, or without an optimised Composer autoloader (`composer dump-autoload -o`).
- Regex in hot loops without anchoring. Evidence: a profiler run (for example Xdebug or SPX profiling).

## Security sinks and footguns

- SQL built by concatenation (CWE-89); use PDO or driver prepared statements with bound values.
- `echo`/`print` of user data without `htmlspecialchars` or template escaping (CWE-79).
- `include`/`require` with user-influenced paths (CWE-98, CWE-22).
- `unserialize` on user data (CWE-502); `phar://` paths passed to file functions can also trigger it.
- `exec`, `system`, `shell_exec`, `passthru`, `proc_open`, backticks with user input (CWE-78);
  use `escapeshellarg` per argument, or avoid the shell.
- `eval`, `assert` with strings, `create_function` in old code (CWE-95).
- `extract($_GET)` / `extract($_POST)` and `$$var` from input (CWE-621).
- Loose comparison in authentication (`"0e1" == "0e2"` is true) (CWE-697); use `hash_equals` for secrets.
- `md5`/`sha1` for passwords (CWE-916); use `password_hash` / `password_verify`.
- `rand`/`mt_rand`/`uniqid` for tokens (CWE-338); use `random_bytes` / `random_int`.
- Uploads saved under user-chosen names or inside the web root (CWE-434).
- `file_get_contents($userUrl)` or curl to user URLs from the server (CWE-918).
- XML parsing with entity substitution enabled (`LIBXML_NOENT`) (CWE-611).
- `header("Location: " . $input)` without an allowlist (CWE-601).

## Testing conventions

- Frameworks: PHPUnit, Pest.
- Canonical commands: `vendor/bin/phpunit`, `vendor/bin/pest`, or `composer test` when defined.
- Data providers for data-driven cases; one behaviour per test method.
- Static analysis as a separate gate when configured: `vendor/bin/phpstan analyse`, `vendor/bin/psalm`.
- Framework test helpers (HTTP test clients, database refresh traits) as the repository already uses them.

## Readability conventions

- Style: PSR-12 / PER coding style through PHP-CS-Fixer or PHP_CodeSniffer.
- `PascalCase` classes, `camelCase` methods; property and variable case follows the framework convention.

## Things NOT to flag

- Omitting the closing `?>` tag in pure-PHP files (it is recommended).
- Arrays used as ordered maps; short array syntax; trailing commas in multi-line calls.
- Framework "magic" (facades, attribute routing, active-record models) that the repository uses consistently.
- `$this->` verbosity and docblocks that add type detail beyond native types (generics, array shapes).
- Formatting — the fixer owns it.

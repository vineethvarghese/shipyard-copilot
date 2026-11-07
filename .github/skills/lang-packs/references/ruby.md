# Ruby pack

Applies to: `.rb`, `.rake`, `.gemspec`, `Gemfile`, `Rakefile` · Loaded by: code-review, security-review, implementer, verifier

## Idioms to follow

- Iterate with blocks and `Enumerable` (`each`, `map`, `select`, `each_with_object`); `&:method` for simple calls.
- Guard clauses and early `return` over nested conditionals; `unless` only for simple negative conditions.
- Keyword arguments for anything beyond one or two positional parameters.
- `# frozen_string_literal: true` where the repository uses it; do not mutate shared string literals.
- `Struct` or `Data` (3.2+) for small value objects instead of bare hashes passed around.
- Predicate methods end in `?`; methods that mutate or raise where a sibling does not end in `!`.
- Resource blocks (`File.open(path) { |f| ... }`) close automatically; prefer them to manual close.
- Rails code: follow the framework's conventions (fat models are not a goal; keep controllers thin).

## Error-handling conventions

- `rescue => e` catches `StandardError`; never `rescue Exception` (it catches signals and exit).
- Do not swallow errors in a bare `rescue` or the `rescue nil` modifier; log or re-raise.
- Custom errors inherit from `StandardError`, grouped under one base class per library.
- `retry` needs a counter and backoff; an unbounded `retry` is an infinite loop.
- `ensure` for cleanup; do not `return` from `ensure` (it swallows the exception).
- `raise NewError, "msg"` inside `rescue` keeps the original as `cause` automatically.

## Concurrency model and pitfalls

- The interpreter has a global VM lock: threads help with I/O, not CPU. Ractors are separate and still limited.
- Multi-threaded app servers run requests in parallel threads: class-level mutable state, class variables
  (`@@x`) and memoised globals are shared.
- `@x ||= compute` is not atomic; two threads can both compute and race.
- `Timeout.timeout` can interrupt code at any point and leave state corrupt; prefer library-level timeouts.
- Database connection pools must be at least the thread count, or requests block.
- Background job code must be idempotent; jobs are retried.

## Performance traps

- N+1 queries from associations in loops — use `includes`/`preload`. Evidence: query log or a query counter in
  the test.
- `Model.all.each` loads everything; use `find_each` for large tables.
- `map(&:id)` on a relation loads records; `pluck(:id)` does not.
- `count` issues a query each call; `size`/`length` behave differently on loaded relations.
- String `+=` in loops allocates; use `<<` on an unfrozen buffer or `join`.
- Evidence tools: `benchmark-ips`, `stackprof`, allocation tracing, request-level profilers.

## Security sinks and footguns

- `eval`, `instance_eval`, `class_eval` with strings from input (CWE-95).
- `send`, `public_send`, `constantize`, `const_get` with user-chosen names (CWE-470).
- `Marshal.load` on untrusted data; `YAML.unsafe_load` or old `YAML.load` behaviour (CWE-502).
- Backticks, `system`, `exec`, `%x()`, `IO.popen` with interpolated strings (CWE-78); pass argument arrays.
- `Kernel#open` with user input can start a process (`|cmd`) (CWE-78); use `File.open` explicitly.
- SQL fragments with interpolation: `where("name = '#{x}'")`, `order(params[:sort])` (CWE-89).
- `html_safe`, `raw`, `<%==` on user data (CWE-79).
- Mass assignment without strong parameters (CWE-915).
- `redirect_to params[:url]` without an allowlist (CWE-601).
- `File.join`/`send_file` with user paths (CWE-22).
- Validation regexes using `^`/`$` (line anchors) instead of `\A`/`\z` (CWE-625).
- Static analysis: Brakeman for Rails apps; `bundle audit` for dependencies when configured.

## Testing conventions

- Frameworks: RSpec, Minitest; factories (e.g. FactoryBot) or fixtures.
- Canonical commands: `bundle exec rspec`, `bundle exec rake test`, `bin/rails test`.
- RSpec: `let` for lazy setup, `describe`/`context` for structure; avoid `allow_any_instance_of`.
- Freeze or travel time with the framework helper instead of sleeping.
- Database cleaning strategy must match whether tests run in transactions or across threads.

## Readability conventions

- Linter and formatter: RuboCop (or Standard) with the checked-in config.
- `snake_case` methods and variables, `CamelCase` classes and modules, `SCREAMING_SNAKE_CASE` constants.

## Things NOT to flag

- Implicit return of the last expression; omitted parentheses in DSL calls (`validates :name, presence: true`).
- Trailing `if`/`unless` modifiers on short statements; `unless` without `else`.
- `%w[]` / `%i[]` literals; safe navigation `&.`; `!!` to coerce booleans.
- Metaprogramming that the framework requires (concerns, `included do`), when it follows the repository pattern.
- Layout and string quote style — RuboCop owns them.

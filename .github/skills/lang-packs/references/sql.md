# SQL pack

Applies to: `.sql`, migration files, and SQL built as strings inside other languages · Loaded by: code-review, security-review, implementer, verifier

Dialects differ. Check which engine and version the repository targets before applying a line below.

## Idioms to follow

- List columns explicitly in application queries, inserts and views; `SELECT *` breaks when columns change.
- Explicit `JOIN ... ON` syntax; meaningful table aliases.
- Bind parameters for every value; never splice values into the SQL text.
- Put integrity in the schema: `NOT NULL`, primary keys, foreign keys, `UNIQUE`, `CHECK`.
- Use `EXISTS` for existence checks; CTEs to name steps in a long query.
- Wrap multi-statement changes in an explicit transaction.
- Migrations are versioned, forward-only in shared environments, and small; destructive steps are separate.
- Expand-then-contract for schema changes that running code depends on (add, backfill, switch, then drop).

## Error-handling conventions

- `= NULL` is never true; use `IS NULL` / `IS NOT NULL`.
- `NOT IN (subquery)` returns no rows if the subquery yields any `NULL`; use `NOT EXISTS`.
- `SUM`, `MAX` and friends return `NULL` on empty input; wrap with `COALESCE` where zero is meant.
- Integer division truncates in many engines; cast deliberately.
- Check affected-row counts for updates that must hit exactly one row.
- Treat constraint violations as expected outcomes where the application relies on them (e.g. duplicate key).
- Roll back on any error inside a transaction; do not continue on a failed transaction.

## Concurrency model and pitfalls

- Know the isolation level in use; many engines default to read committed.
- Lost update: read a value, change it in code, write it back. Use an atomic `UPDATE ... SET x = x + 1`,
  `SELECT ... FOR UPDATE`, or an optimistic version column.
- "Insert if not exists" with a separate check races; use the engine's upsert (`ON CONFLICT`, `MERGE`) plus a
  unique constraint.
- Deadlocks come from locking rows or tables in different orders; keep a consistent order and retry on deadlock.
- Long transactions hold locks and block cleanup; keep them short and never wait on network calls inside one.
- Some DDL takes heavy locks on large tables (adding constraints, rewriting columns, building indexes); use the
  engine's online or concurrent options where they exist, and batch backfills.

## Performance traps

- Missing index for `WHERE`, `JOIN` or `ORDER BY` columns on large tables. Evidence: `EXPLAIN` plan.
- Functions or casts on an indexed column (`WHERE LOWER(email) = ?`) stop index use unless an expression index
  exists. Evidence: plan shows a full scan.
- Leading wildcard `LIKE '%term'` cannot use a normal index.
- Deep `OFFSET` pagination scans and discards rows; use keyset pagination.
- Queries issued per row from application code (N+1). Evidence: query count from the test log.
- Unbounded queries without `LIMIT` on tables that grow; very large `IN` lists.
- Implicit type conversion between column and parameter types.
- Evidence: `EXPLAIN` (and `EXPLAIN ANALYZE` only on a disposable database — it runs the query), row counts at
  realistic volume.

## Security sinks and footguns

- Dynamic SQL by concatenation — in application code or inside stored routines that execute a built string
  (CWE-89).
- Identifiers (table, column, sort direction) cannot be bound; validate against an allowlist (CWE-89).
- Missing tenant or owner filter, so a user-supplied ID reads another user's rows (CWE-639).
- Application accounts with DDL or superuser rights (CWE-250, CWE-269).
- Sensitive data stored in plain columns (CWE-312); credentials or real data in migration or seed files (CWE-798).
- Routines that run with their definer's rights without a fixed, trusted schema search path (CWE-269).
- Database error text returned to clients (CWE-209).

## Testing conventions

- Run migrations up (and down, if supported) against a disposable database in the test suite.
- Test queries through the application's own test command against a real engine of the same kind; an in-memory
  substitute engine can hide dialect differences.
- Database unit-test frameworks (for example pgTAP) only if the repository uses them.
- Seed minimal, explicit fixtures; never depend on row order without `ORDER BY`.
- For performance ACs, test with a realistic row count and assert on plan shape or timing budget.

## Readability conventions

- Formatter/linter: `sqlfluff` (or the repository's choice) with the configured dialect.
- One clause per line in long queries; consistent keyword case as the formatter sets it.
- `snake_case` names; singular or plural table names as the schema already does.

## Things NOT to flag

- Keyword case and indentation — the formatter owns them.
- `SELECT *` inside `EXISTS (...)`, in ad-hoc scripts, or in tests.
- `COUNT(*)` versus `COUNT(1)` — equivalent in mainstream engines.
- CTE versus subquery when the plans are the same.
- `WHERE 1=1` in query builders that append bound conditions.
- Dialect-specific syntax the repository already uses throughout.

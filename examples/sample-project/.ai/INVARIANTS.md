> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: PLAN.HUMAN.md.
### INV-001: Links created without a TTL behave exactly as before
Statement:        For every link created with ttl_seconds=None, resolve returns the url at any clock value.
Rationale:        Existing callers must see no change.
How to verify:    tests/test_shortener.py unchanged and passing; AC-4 of slice 02.
Introduced by:    ADR-000

### INV-002: All times come from the injected clock
Statement:        No module under src/shortener reads the system time.
Rationale:        Deterministic tests; expiry must be testable at the boundary instant.
How to verify:    `git grep -n "time\.\|datetime" src/shortener` returns only the clock parameter.
Introduced by:    ADR-000

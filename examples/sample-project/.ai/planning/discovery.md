> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: PLAN.HUMAN.md.
# Discovery: link-expiry

## Build and test
- Canonical test command: `python -m pytest -q` (ran at P1, 0.4 s, 6 passed). `DERIVED`
- Standard library only; Python 3.9+ (`pyproject.toml`). `DERIVED`

## Structure
- `src/shortener/service.py:12` `Shortener.create(url)`; `:27` `Shortener.resolve(code)`. `DERIVED`
- `src/shortener/store.py` `InMemoryStore`; no database, nothing persists between runs. `DERIVED`
- Time comes from an injected `clock` callable (`service.py:9`). `DERIVED`

## Consumers
None found: no other package imports `shortener` (`git grep -n "import shortener"` outside `src/` and `tests/`). `DERIVED`

## Validation tiers
| Tier | Invoked | Environment | Prerequisites | Cost | Reaches | Evidence |
|---|---|---|---|---|---|---|
| unit | `python -m pytest -q` | LOCAL | pytest | < 1 s | all library behaviour | `pyproject.toml`, `tests/` |

## Key terms the code uses
`Link`, `code`, `url`, `clock` (`models.py`, `service.py`). See `GLOSSARY.md`.

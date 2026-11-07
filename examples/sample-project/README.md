# Sample project: a toy link shortener

> **Illustrative example, hand-written to show the artifacts. Not a recorded run.**
> No agent produced these files. They show what Shipyard's `.ai/` folder looks like part-way through a small
> two-slice feature, so you can see each artifact's format before you run Shipyard on your own code.
> In a real project `.ai/` never sits on your work branches: Shipyard ignores it there through
> `.git/info/exclude` and commits it to a separate notes branch (`<feature>-shipyard`). It is checked in here only
> so you can read it.

## The toy

`shortener` is a tiny Python library: `Shortener.create(url)` returns a `Link` with a short code, and
`Shortener.resolve(code)` returns the URL. Links live in an in-memory store. Time comes from an injected clock,
so tests are deterministic.

```text
pyproject.toml
src/shortener/
  __init__.py      public exports
  models.py        Link dataclass
  store.py         InMemoryStore
  service.py       Shortener: create, resolve
tests/
  test_shortener.py       original behaviour
  test_expiry_create.py   added by slice 01
```

Run the tests (Python 3.9+):

```bash
python -m pytest -q              # with pytest installed
PYTHONPATH=src python -m unittest discover -s tests   # standard library only
```

## The feature: "add expiry to short links"

The request was: *"Add expiry to short links. Campaign links should stop working after a while."*
Shipyard planned it as two slices on the feature branch `feature/link-expiry`:

| Slice | Title | State in this snapshot |
|---|---|---|
| 01 | Store an optional expiry on links | MERGED into `feature/link-expiry` |
| 02 | Expired links stop resolving | TEST_PLANNING — its test plan is a DRAFT awaiting the code-reviewer |

The code in `src/` is the feature branch **after slice 01 merged**: `create()` takes `ttl_seconds`, but
`resolve()` does not enforce expiry yet. That is slice 02's job, and no slice 02 code exists because its test
plan is not approved — Shipyard writes no code before that.

## The `.ai/` folder

| File | What it shows |
|---|---|
| [`.ai/state.json`](.ai/state.json) | Machine state: status `IMPLEMENTING`, active slice `02`, its branch |
| [`.ai/PROJECT.md`](.ai/PROJECT.md) | Problem, goals, delivery parameters C-1..C-10, phase log |
| [`.ai/PLAN.HUMAN.md`](.ai/PLAN.HUMAN.md) | The one-screen plan-approval brief (stop 3) |
| [`.ai/DELIVERY_PLAN.md`](.ai/DELIVERY_PLAN.md) | Slices, states, branches, reconciliation log |
| [`.ai/planning/concepts.md`](.ai/planning/concepts.md) | Sealed elephant take, three goldfish lenses, top 3, disagreements, gap list |
| [`.ai/slices/01/SLICE.md`](.ai/slices/01/SLICE.md) | Slice spec with code and test touch sets and branch |
| [`.ai/slices/01/TEST_PLAN.md`](.ai/slices/01/TEST_PLAN.md) | `Status: APPROVED` test plan: AC → tests |
| [`.ai/slices/01/EVIDENCE.md`](.ai/slices/01/EVIDENCE.md) | Verification and review record |
| [`.ai/slices/01/REVIEW.HUMAN.md`](.ai/slices/01/REVIEW.HUMAN.md) | The one-screen merge brief (stop 4) |
| [`.ai/slices/02/SLICE.md`](.ai/slices/02/SLICE.md) | Next slice spec |
| [`.ai/slices/02/TEST_PLAN.md`](.ai/slices/02/TEST_PLAN.md) | `Status: DRAFT` — the gate that blocks code |

Also present, kept short: `ARCHITECTURE.md`, `INVARIANTS.md`, `GLOSSARY.md` and `planning/discovery.md`. Not
shown: the per-reviewer `findings/` files (`EVIDENCE.md` keeps the summary). `state.json` carries the recorded
gates (P0, P4, P8 and the slice 01 merge), which is what `check.py --phase` reads.

You can check the state file against its contract from this repository's root:

```bash
python3 shipyard/scripts/shipyard_validate.py state examples/sample-project/.ai/state.json
```

In CLI and IDE modes the coordinator would have snapshotted this folder to the notes branch
`feature/link-expiry-shipyard`; in cloud mode `shipyard-notes-sync.yml` commits it there from the task's artifact.

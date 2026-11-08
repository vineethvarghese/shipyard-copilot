# Contributing to shipyard-copilot

Thanks for helping. shipyard-copilot is small on purpose: plain Markdown agents, skills, prompts and
instructions under `.github/`, three JavaScript dynamic workflows, Python hooks and scripts that use only the
standard library, and JSON contracts. Keep it that way.

## Ground rules

- **Generic only.** No company, product-team, cloud-vendor or person names in the repository (credits live in
  `NOTICE` and the README's Credits section; GitHub and Copilot product names are fine). Use neutral examples such
  as `npm test`, `go test ./...`, `pytest` or `cargo test`. `shipyard/scripts/check.py` scans for a list of banned
  words.
- **Paraphrase books, never quote them.** Cite by author, title and topic.
- **Nothing pushes.** No script, hook, workflow or agent in this repository may push to a remote, except
  `shipyard-notes-sync.yml`, which pushes only to a notes branch and refuses anything else.
- **Plain, short sentences** in docs. Direct, imperative voice in agent, prompt and skill files.
- **Mark what you have not verified.** Any claim about Copilot behaviour that you did not confirm against a
  running client is written with "(unverified)".

## Dev setup

You need git, Python 3.9+ and Node 22. Nothing to install: there are no third-party dependencies.

```bash
git clone <your fork> shipyard-copilot && cd shipyard-copilot
copilot --agent=shipyard-coordinator     # try the working copy in Copilot CLI
```

## Tests to run before a pull request

```bash
python3 -m unittest discover -s shipyard/tests/hooks        # every hook allow/deny rule, with Copilot payloads
python3 -m unittest discover -s shipyard/tests/scripts      # validator, state helper, check.py, gen_agents
node --test shipyard/tests/extensions/                     # the dynamic workflows with a fake ctx
python3 shipyard/scripts/check.py                           # JSON, contracts, registry, banned words
python3 shipyard/scripts/gen_agents.py --check              # generated agent files are up to date
python3 shipyard/scripts/gen_plugin.py --check              # plugin.json and hooks.json match the repository hook file
python3 shipyard/scripts/check_links.py                     # every relative Markdown link resolves
```

## Agents are generated

`.github/agents/shipyard-<short>.agent.md` is written by `python3 shipyard/scripts/gen_agents.py` from
`shipyard/source-agents/<short>.md` (the Shipyard shells) and `shipyard/registry/roles.json`. Edit the source
shell or the generator, then regenerate; never edit a generated specialist by hand. The coordinator's body is
the one exception: it is hand-maintained, the generator refreshes only its frontmatter, and `--check` verifies it
still carries the markers the modes need (`check.py --phase`, `set-active-role`, the four `gate … approve` lines).

Tool names in the generated files follow the Copilot custom-agents reference: `read`, `search`, `edit`,
`execute`, `web`, `todo`, `agent`. Model ids come from `MODEL_MAP` in the generator (empty by default) or
`--model CLASS=id`.

## The diagram rule

A diagram changes with the behaviour it shows. If your change alters a phase, a gate, a role, a contract, a hook
or the branch model, update the matching diagram in `docs/diagrams/*.mmd` and its rendered `.svg`
(`npx -y @mermaid-js/mermaid-cli@11.4.2 -i x.mmd -o x.svg`) and the page that explains it, in the same pull
request. The README's hero diagram must stay identical to `docs/diagrams/01-hero.mmd`; `check.py` enforces that
one.

## Contracts and versioning

Contracts live in `shipyard/contracts/*.schema.json` (JSON Schema draft 2020-12). Each has `$id`, `title` and
`x-contract-version` (`MAJOR.MINOR.PATCH`).

- **Patch**: descriptions and wording only.
- **Minor**: a new optional property, or a new enum value every consumer already tolerates.
- **Major**: anything a consumer could break on. Bump the major, update `shipyard/registry/roles.json`
  (`"reviewer-result@2"`), the workflows that use it, `workflowContractMajor` if a workflow's return changes, the
  tests and the docs.

`check.py` fails if the registry asks for a major version a contract file does not have.

## Adding things

- **A role** (for example a new reviewer): a shell in `shipyard/source-agents/`, a capability skill, a registry
  entry with modes, compute classes, contract and routing triggers, a `HOOKS` row in `gen_agents.py`, hook
  coverage and tests, then `python3 shipyard/scripts/gen_agents.py`. The coordinator's `agents:` list is derived
  from the registry.
- **An ability**: `.github/skills/<ability>/SKILL.md` (with a `Version x.y.z` line), `CHANGELOG.md`, optional
  `references/`, and the ability added to the roles that load it.
- **A language pack**: `.github/skills/lang-packs/references/<language>.md`, linked from the pack's `SKILL.md`,
  plus an entry in that skill's `CHANGELOG.md`.
- **A prompt file**: `.github/prompts/shipyard.<phase>.prompt.md`, starting with `check.py --phase`, naming the
  specialist calls in order with the brief header, the caps, and the gate it ends at.

Every skill change bumps its version and adds a `CHANGELOG.md` entry.

## Commit conventions

Use Conventional Commits: `type(scope): summary`, with types such as `feat`, `fix`, `docs`, `test`, `refactor`,
`chore`, and a scope such as `agents`, `skills/<name>`, `hooks`, `extensions`, `prompts`, `contracts`, `registry`,
`scripts`, `docs`. Mark breaking changes with `!` and a `BREAKING CHANGE:` footer; every major contract bump is one.

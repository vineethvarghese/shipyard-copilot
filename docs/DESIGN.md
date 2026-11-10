# shipyard-copilot: design document

Working name: **shipyard-copilot**. A template repository that users copy into their own `.github/` (plus a small
tool-independent `shipyard/` folder) to run the Shipyard method under GitHub Copilot: Copilot CLI, Copilot
coding agent (cloud), and Copilot agent mode in VS Code / JetBrains.

Research date: 2026-11-08. Everything below marked **(unverified)** came from a single secondary source or from a
docs page that was silent on the point; it must be confirmed against `copilot --help` and the SDK before Phase 2.

## 0. Executive summary

- Copilot in late 2026 has first-class equivalents for Shipyard's **agent shells** (`.github/agents/*.agent.md`),
  **skills** (`.github/skills/*/SKILL.md`, loaded by every client), **hooks** (`.github/hooks/*.json`,
  `preToolUse` can deny, `subagentStop` can block; CLI and cloud agent), **subagents** (CLI `task` tool, VS Code
  `runSubagent`, SDK `customAgents`) and, surprisingly, **saved workflows**: *dynamic workflows* are
  `extension.mjs` modules in `.github/extensions/<name>/` built with `defineWorkflow({ meta, run })`, where
  `ctx.agent(prompt, { schema })` runs a subagent and validates its return against a (structural subset of) JSON
  Schema, `ctx.step` journals deterministic work for resume, `ctx.parallel` fans out, and `ctx.pause` checkpoints.
  This is a near one-to-one match for Shipyard's `workflows/*.js`, but it is **public preview, CLI-only, behind
  `--experimental`**, and the authoring API is documented mainly by third parties.
- The three things that do not port cleanly are: (1) **hook scoping by agent**: Copilot hook payloads carry
  `toolName`/`toolArgs`/`cwd`, and there is no documented `agent_type` field, so "do nothing unless a Shipyard agent
  is running" must be inferred from `.ai/state.json` and from CLI-only agent-scoped hooks; (2) **a single
  entry point**: any user can select any `.agent.md`, so `Caller: shipyard:coordinator` is a convention, not a
  rule, mitigated by `user-invocable: false`; (3) **per-call effort**: `model` per agent is fine, but reasoning
  effort per mode exists only in the SDK (`reasoningEffort`) and as a global CLI setting (`effortLevel`).
- GitHub Actions and rulesets substitute well for the *remote* half of the guardrails (protect `main`, require a
  `shipyard-slice-check` status, CODEOWNERS on `.ai/`), and they are the only enforcement available in the cloud
  coding agent and IDE modes. They cannot replace the *local* hooks' per-tool-call checks.
- Recommended shape: **CLI-first** (coordinator custom agent + three dynamic workflows + hooks), with an
  **IDE mode** (handoffs + prompt-file checklists, hooks where the client has them) and a **cloud mode** (one
  coding-agent task per phase, gates as issue/PR events, Actions checks). Fidelity is full/partial/manual
  respectively, and the README must say so.

## 1. What Copilot offers (November 2026)

### 1.1 Customization surfaces

| Surface | Path | Clients | Notes |
|---|---|---|---|
| Repo instructions | `.github/copilot-instructions.md` | all | Always on. |
| Path-scoped instructions | `.github/instructions/*.instructions.md`, frontmatter `applyTo: "glob,glob"`, optional `excludeAgent: code-review \| cloud-agent` | cloud agent, code review (GitHub.com); VS Code/JetBrains | Code review reads them from the PR head branch. |
| Agent instructions | `AGENTS.md` anywhere (nearest wins), or root `CLAUDE.md`/`GEMINI.md` | cloud agent, CLI, IDEs | Nested files supported. |
| Prompt files | `.github/prompts/*.prompt.md` | VS Code (and JetBrains) only; not confirmed for CLI or cloud | Slash-command style reusable prompts; keys `mode/agent`, `model`, `tools`, `description` (VS Code docs). |
| Custom agents | `.github/agents/*.agent.md`; user `~/.copilot/agents`; org `.github`/`.github-private` repo `/agents`; enterprise | CLI (GA), cloud agent, VS Code; JetBrains/Eclipse/Xcode public preview | Frontmatter: `name`, `description` (required), `tools`, `model`, `disable-model-invocation`, `user-invocable`, `mcp-servers` (cloud/org), `metadata`, `target: vscode\|github-copilot`. VS Code adds `handoffs`, `agents`, `argument-hint`. CLI adds agent-scoped `hooks`. Body ≤ 30 000 chars. Precedence: user > repo > org > enterprise. |
| Skills | `.github/skills/<name>/SKILL.md` (also `.claude/skills`, `.agents/skills`); personal `~/.copilot/skills`, `~/.agents/skills` | CLI, cloud agent, code review, VS Code, Visual Studio, JetBrains, Copilot app | Loaded "when relevant" (no preload list). `gh skill` installs them. Shipyard's 13 skills port verbatim. |
| Hooks | `.github/hooks/*.json` (`version: 1`), `~/.copilot/hooks/*.json`, inline in `.github/copilot/settings.json`, plugin `hooks.json`, policy dir | CLI (full), cloud agent (subset, `.github/hooks` only), VS Code (agent-scoped hooks in `.agent.md`), JetBrains (preview) | Events: `sessionStart/End`, `userPromptSubmitted`, `preToolUse`, `postToolUse`, `postToolUseFailure`, `permissionRequest` (CLI), `agentStop`, `subagentStart`, `subagentStop`, `errorOccurred`, `preCompact`. `preToolUse` → `{permissionDecision: allow\|deny\|ask, permissionDecisionReason, modifiedArgs}` (`ask` = `deny` in cloud). Exit 2 = deny; other non-zero = deny for `preToolUse` (fail closed), skipped elsewhere; **timeout = fail open**. `subagentStop` → `{decision: block\|allow, reason}`. `matcher` regex anchored `^(?:…)$`. `toolArgs` is a JSON *string*. |
| MCP | CLI: `~/.copilot/mcp-config.json`, `copilot mcp`; cloud: repo Settings → Copilot → MCP servers JSON (`mcpServers`, `type local\|stdio\|http\|sse`, `tools` allowlist, `COPILOT_MCP_*` secrets); `.vscode/mcp.json` for VS Code | per client | Cloud agent does **not** read `.vscode/mcp.json`. GitHub MCP and Playwright built in. |
| Cloud environment | `.github/workflows/copilot-setup-steps.yml`, job must be named `copilot-setup-steps`; honours `steps`, `permissions`, `runs-on`, `services`, `snapshot`, `timeout-minutes` ≤ 59 | cloud agent | Any shell steps run before the agent starts: the place to restore `.ai/` from the notes branch and install Python. |
| Copilot CLI | `copilot` | — | `--agent=NAME`, `/agent`; `-p PROMPT` non-interactive; `--output-format json` (JSONL events, not schema); `--allow-tool='shell(git:*),write(.ai/**)'`, `--deny-tool`, `--available-tools`, `--excluded-tools`, `--allow-all`; `--model=`, precedence agent `model` > `--model` > `COPILOT_MODEL` > settings; `effortLevel` in settings (global); `--resume [ID]`, `--continue`; `--no-ask-user`; `--add-dir`; `--trust-folder`; `/fleet` + `--fleet` parallel subagents; `/tasks`; `&` prefix delegates to the cloud agent; `/autopilot`; `copilot workflow run NAME --args @f.json --result-file r.json --silent --output-format json`; exit codes 0/1/2/130. |
| Copilot SDK | TS, Python, Go, .NET, Java; public preview since 2026-04 | — | `createSession({ model, customAgents:[{name, prompt, tools, mcpServers, skills, model, reasoningEffort, infer}], onPermissionRequest })`. Sub-agents run in isolated context, stream `subagent.*` events. No documented structured-output option. |
| Dynamic workflows | `.github/extensions/<name>/extension.mjs` (also `~/.copilot/extensions/`, plugins); `defineWorkflow({meta:{name, description, phases, argsSchema, limits}, run(ctx)})`; `ctx.args`, `ctx.phase`, `ctx.step(key, fn)` (journaled, replayed on resume), `ctx.agent(prompt, {label, schema})` (null on failure, one retry on schema mismatch, memoised), `ctx.parallel`, `ctx.pipeline`, `ctx.pause(name)`, `ctx.signal`, `ctx.log`; nested `ctx.workflow` rejected | CLI with `--experimental`; Copilot app (monitor local runs only) | **Public preview.** Needs `GITHUB_COPILOT_PROMPT_MODE_EXTENSIONS=true` for project extensions in headless runs. `workflow run` cannot `--resume`, `--agent`, `--fleet`. Whether `ctx.agent` accepts a custom-agent name or a `model` is **(unverified)**. |

### 1.2 Capability check against Shipyard's needs

| Need | Status | Where |
|---|---|---|
| Saved, deterministic workflows that orchestrate subagents with schema-validated returns | **Partially supported**: dynamic workflows (`defineWorkflow`, `ctx.agent` with `schema`, `ctx.step`, `ctx.parallel`), CLI-only, preview; schema is a structural subset (`pattern`, `minLength`, ranges, `additionalProperties` ignored) | https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-dynamic-workflows · https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference |
| Subagent spawning from an agent, with an allowlist | **Supported**: CLI `task` tool / automatic delegation; VS Code `runSubagent` + `agents:` allowlist (`[]` blocks); SDK `customAgents`. Nested depth 5 in VS Code with a setting | https://code.visualstudio.com/docs/copilot/agents/subagents · https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/custom-agents |
| Per-call model | **Supported**: `model` in `.agent.md`; VS Code caps subagent cost tier at the parent's | custom-agents-configuration |
| Per-call effort | **Partially**: SDK `reasoningEffort` per custom agent; CLI only a global `effortLevel`; nothing in `.agent.md` | cli-programmatic-reference · SDK custom-agents |
| Hooks that block a tool call | **Supported** (CLI, cloud agent): `preToolUse` deny; agent-scoped hooks CLI-only; VS Code agent-scoped hooks per changelog; JetBrains preview | https://docs.github.com/en/copilot/reference/hooks-reference |
| Hook knows which custom agent is running | **Not documented** (payload: `sessionId`, `timestamp`, `cwd`, `toolName`, `toolArgs`); `subagentStart`/`subagentStop` have a `matcher` whose target field is **(unverified)** | hooks-reference |
| Block a subagent from stopping without its deliverable | **Supported**: `subagentStop` → `{decision: "block", reason}` (CLI, cloud) | hooks-reference |
| JSON-schema-enforced structured output of a session | **Not supported** outside dynamic workflows (`--output-format json` is an event stream); third-party comparison lists Copilot CLI as "none" | cli-programmatic-reference |
| Headless runs in CI | **Supported**: `copilot -p … --allow-tool…`, `copilot workflow run … --result-file`; GitHub recommends Agentic Workflows (gh-aw) for Actions automation | https://docs.github.com/en/copilot/how-tos/copilot-cli/automate-copilot-cli/run-cli-programmatically |
| Plugin packaging | **Supported for the CLI** (verified 1.0.107): `plugin.json` with `agents`, `skills`, `extensions` and `hooks` path keys; `${PLUGIN_ROOT}` expands in hook commands; plugin agents are namespaced `<plugin>:<agent>`; plugin workflows register without folder trust; the cloud agent and the IDEs read only `.github/`, hence the project installer | use-dynamic-workflows · hooks-reference |

### 1.3 How GitHub Actions and repo settings fill gaps

| Shipyard rule | GitHub substitute | Strength |
|---|---|---|
| Never push to / merge on `main` or base branch | Ruleset on `main` and `release/*`: require PR, 1 review, required status checks, block force push; **do not** grant Copilot the ruleset bypass | Stronger than the hook (enforced server-side) but only at push time |
| `.ai/` never enters a work branch | Action `shipyard-notes-guard.yml`: fail if a PR to `main` or the feature branch touches `.ai/**`; CODEOWNERS `.ai/ @shipyard-owners` so a human must approve any such change | Enforced at PR time |
| Slice scope (touch sets), test plan approved, findings files present, `EVIDENCE.md` exists | Action `shipyard-slice-check.yml` running `shipyard/scripts/check.py` on PRs into the feature branch; make it a required status check on `feature/*` via a ruleset | Enforced at PR time, not at write time |
| Plan approved before slices | `check.py` requires `.ai/DELIVERY_PLAN.md` state `APPROVED` with a human approval line; in cloud mode also a `shipyard:plan-approved` label | Enforced at PR time |
| Human merge approval | Normal PR review on the slice PR into the feature branch; `pull_request_review` approved event by a human (not `copilot`) | Enforced |
| Secrets in `.ai/` | Secret scanning + push protection on the repo (covers the notes branch) in addition to the hook | Enforced server-side |
| Resumable state | `copilot-setup-steps.yml` restores `.ai/` from the notes branch before a cloud task; local modes read disk | Manual |
| Validation tiers / test command | `copilot-setup-steps.yml` installs toolchain; `shipyard-slice-check.yml` runs the recorded test command | Enforced |
| Orchestration of phases in CI | GitHub Agentic Workflows (`gh aw compile` → `.lock.yml`, read-only sandbox, writes only through `safe-outputs`) can run a reviewer sweep on a slice PR | Available, but a separate engine; optional |

### 1.4 Prior art: Copilot ports of spec/plan/implement/review frameworks

| Project | Structure | Handoffs and gates | Take-away for shipyard-copilot |
|---|---|---|---|
| **github/spec-kit** | Installed with `specify init --integration copilot`; commands `/speckit-constitution`, `-specify`, `-plan`, `-tasks`, `-implement`, `-converge` (now "GitHub Copilot's default skills syntax", i.e. `.github/skills/`); artifacts under `.specify/` (`memory/constitution.md`, `scripts/`, `templates/`) and per-feature spec folders; extensions add bug/assessment flows and "hook" behaviour around commands | Order is kept by **prerequisite-check scripts** each command runs first, plus "review before continuing" discipline; `implement`/`converge` loop until the converge step reports `Converged` | The prerequisite-script pattern is the right fallback for IDE/cloud modes where no workflow engine exists: every prompt/skill begins by running `check.py --phase X`. |
| **github/awesome-copilot** | A catalogue of `.agent.md` files (38 pages); architecture agents (e.g. ".NET Self Learning Architect") that "decide between parallel subagents and orchestrated team execution"; ADR generator; accessibility reviewers | No cross-agent handoff chains in the catalogue; agents are standalone | Confirms that community agents are single-role; orchestration is left to the user, which is the gap Shipyard fills. |
| **BMAD-METHOD** | Older versions emitted `.github/chatmodes/*.chatmode.md` per role (dev, qa, ux, master); current installer targets `.github/copilot/` and `.github/agents/*.agent.md` (community tests count `*.agent.md`); `bmad-copilot-adapter` on npm runs BMAD workflows as prompt files | Gates are prose in the agent bodies; no hooks or Actions | Same conclusion; also a warning that Copilot file conventions moved (chatmodes → agents) and a port must track them. |
| **githubnext / github gh-aw** | Markdown workflow + YAML frontmatter compiled to Actions; engines Copilot/Claude/Codex/Gemini | Read-only agent jobs; writes only via sanitized `safe-outputs` applied by separate jobs | A clean model for the *CI-side* reviewer sweep; not a replacement for the interactive loop. |

## A. Capability mapping

Fidelity: **full** = same guarantee; **degraded** = works but weaker or client-dependent; **manual** = convention
plus a later check, not enforcement at the moment of action.

| Shipyard mechanism | Copilot equivalent | Fidelity | How the gap is handled |
|---|---|---|---|
| **Coordinator** as the main session, sole entry point, owns the chat and gates | `.github/agents/shipyard-coordinator.agent.md`, launched with `copilot --agent=shipyard-coordinator` (CLI), selected in the IDE picker, or named in a cloud task | degraded | Specialists set `user-invocable: false` so they are hidden from pickers; in VS Code the coordinator's `agents:` key lists exactly the 12 specialists and every specialist omits the `agent` tool and sets `agents: []`. `Caller:` line stays as convention; `brief-check` hook (CLI only) checks it on `task` calls. |
| **Saved workflows** `discover.js`, `plan.js`, `slice.js` (order, caps, routing, dedupe, schema-checked returns) | Dynamic workflows `.github/extensions/shipyard-{discover,plan,slice}/extension.mjs` using `defineWorkflow`, `ctx.agent(prompt,{schema})`, `ctx.step`, `ctx.parallel`, `argsSchema`, `limits` | degraded (CLI-only, preview) | Same three-workflow split as ADR-0001 (a workflow cannot ask the human; each ends at a gate). IDE and cloud modes fall back to **phase prompt files / skills** whose first step is `python3 shipyard/scripts/check.py --phase …` (spec-kit pattern) and whose last step validates the return with `shipyard_validate.py`. Caps and routing become instructions, verified after the fact by `check.py`. |
| **Role registry** `registry/roles.json` (role → agent, compute per mode, routing triggers, contract) | Same file under `shipyard/registry/roles.json`, read by the extensions; `.agent.md` `model` set from it by a generator script | degraded | Effort per mode is not expressible in `.agent.md`; the generator emits `model` only. Workflows pass the registry via `--args`. **(unverified)** whether `ctx.agent` can name a custom agent and model; if not, the workflow inlines the agent body as the prompt and the registry picks the model via a separate `copilot --model` process. |
| **Agent shells** `agents/*.md` (identity, tools, model, effort, maxTurns, skills preload) | `.github/agents/*.agent.md` with `name`, `description`, `tools`, `model`, `user-invocable`, (VS Code) `agents`, (CLI) `hooks`; body = Shipyard shell with Claude tool names mapped (`Read/Grep/Glob` → `read`, `search`; `Bash` → `shell`; `Write/Edit` → `write`/`edit`; `Agent` → `task`/`agent`) | full for identity and tools; degraded for effort/turn caps/preload | `skills:` preload is replaced by an explicit body line "Load skill `code-clarity` …" (skills load by relevance). `maxTurns` → `Budget:` line in the brief plus workflow `limits`. |
| **Capability skills** `skills/<name>/SKILL.md` | `.github/skills/<name>/SKILL.md`, byte-for-byte except tool names; loaded by CLI, cloud agent, code review, VS Code, JetBrains | full | Code review on GitHub.com also loads them, which gives a free "reviewer" surface on every PR. |
| **Contracts** `contracts/*.schema.json`, runtime-enforced in workflows, `shipyard_validate.py` for direct calls | Same JSON files; `ctx.agent(…, {schema})` enforces a structural subset inside workflows; everywhere else the caller validates the fenced JSON block with `shipyard_validate.py` | degraded | Strip unsupported keywords when loading (`pattern`, `minLength`, numeric ranges, `additionalProperties` are ignored anyway) and re-validate the full schema in `ctx.step` with a tiny validator after `ctx.agent` returns. `null` return = retry once, then `BLOCKED`. |
| **Hook: protect-branches** | `.github/hooks/shipyard.json` `preToolUse` matcher `shell` → `protect-branches.py` (payload adapter: `toolArgs` string → command); plus `main` ruleset (no bypass for Copilot) and `--deny-tool='shell(git push:*)'` in launch scripts | degraded locally, full remotely | Hook cannot see `agent_type`; it applies whenever `.ai/state.json` exists in `cwd`. Remote protection is the real guarantee. |
| **Hook: write-scope** (per-role allowed paths) | CLI: agent-scoped `hooks` in each `.agent.md` (`preToolUse` on `write`/`edit`/`shell`) carrying the role name as an env var to `write-scope.py`; cloud: repo hook infers the role from `state.json.activeRole` set by the coordinator before each delegation; IDE: `tools` restriction only | degraded | `activeRole` in `state.json` is a convention the coordinator must keep; `check.py` diff-vs-touch-set in Actions is the backstop. Also `--allow-tool='write(.ai/**)'` style launch filters for the coordinator. |
| **Hook: test-plan-gate** | Same hook file, same inference; plus `shipyard-slice-check` refuses a slice PR whose `TEST_PLAN.md` was `APPROVED` after the first code commit (git log check) | degraded | Order violation is caught at PR time if the hook missed it. |
| **Hook: readonly-bash** (reviewers, planners) | `tools: [read, search]` in those `.agent.md` files (tool removed entirely); keep `shell` only for reviewers that must run tests, guarded by the hook | full (stronger than Shipyard where the tool is absent) | — |
| **Hook: goldfish-blinders** | `preToolUse` matcher `read\|grep\|glob\|search\|view` (names differ per client, list all) denying `.ai/**` except `SLICE.md`, agent-scoped to `shipyard-goldfish` (CLI); IDE: none | degraded | In IDE/cloud modes the goldfish brief says "do not open `.ai/`" and the workflow/prompt passes only the verbatim request. State as unenforced there. |
| **Hook: secrets-guard** | `preToolUse` on `write`/`edit` into `.ai/**` + GitHub push protection on the notes branch | full remotely, degraded locally | — |
| **Hook: findings-gate** (reviewer must write a parseable findings file; 3 retries) | `subagentStop` hook with `matcher` on reviewer subagents → `{decision: "block", reason}` when the findings file is missing/stale/malformed; `subagentStart` records the start time | degraded | Retry cap is kept in a temp file keyed by `sessionId`+reviewer; whether the matcher sees the custom agent name is **(unverified)**; in workflows the `schema` on `ctx.agent` is the primary gate. |
| **Hook: brief-check** (`Caller:`, `Mode:`, `Round:` on coordinator → specialist calls) | `preToolUse` matcher `task\|agent\|runSubagent` → `brief-check.py` (CLI; VS Code agent-scoped hooks if available) | degraded | Workflows build briefs in code, as today; direct calls in IDE/cloud are convention. |
| **`.ai/` folder**, excluded via `.git/info/exclude` | Same folder and scripts; `.git/info/exclude` works for CLI and IDE; cloud agent clones fresh, so `copilot-setup-steps.yml` restores `.ai/` from the notes branch and adds the exclude line | degraded in cloud | Cloud agent pushes only its task branch; the notes branch update happens from the Actions side (`shipyard-notes-sync.yml` on `workflow_dispatch`/PR event) — see §C. |
| **Notes branch** `<feature>-shipyard` snapshots | Same via `shipyard_state.py snapshot` (CLI, IDE); cloud: Action commits `.ai/` artifacts uploaded by the task | manual in cloud | Honest statement: cloud mode may keep `.ai/` on the feature branch instead (see §D). |
| **Human gates** P0/P4/P8/merge | CLI: coordinator asks in chat (keep `--no-ask-user` off); workflows end with `NEEDS_HUMAN`/`AWAITING_PLAN_APPROVAL`; VS Code: `handoffs` with `send: false` so a human clicks; cloud: issue form, issue/PR comments, labels, PR review | full (CLI/IDE), manual (cloud) | `shipyard_state.py gate P8 approve --by <login>` records approvals; `check.py` refuses to proceed without them. |
| **Local `--no-ff` merge** into the feature branch after approval | CLI/IDE: identical; cloud: a PR from the slice branch into the feature branch, merged by the human (merge commit strategy enforced by ruleset) | full / manual | Evidence summary goes into the PR body template instead of the merge commit message in cloud mode. |
| **Compute classes** COORDINATOR/DEEP/STANDARD (model + effort) | `model` per `.agent.md` from the registry (e.g. DEEP → `claude-opus-4…`/`gpt-5.x`, STANDARD → cheaper); effort: SDK `reasoningEffort` in workflow-spawned agents **(unverified)**, otherwise `effortLevel` global | degraded | Document two settings profiles; VS Code's cost-tier ceiling gives "delegate never above coordinator" for free. |
| **Parallelism** (implementer ∥ verifier, concurrent reviewers) | `ctx.parallel` in workflows; `/fleet`; VS Code parallel subagents | degraded outside workflows | Prompt files run reviewers sequentially; acceptable. |
| **Evals** (`claude plugin eval`) | None | manual | Actions job runs `copilot -p` / `copilot workflow run` on `examples/sample-project` with `--result-file` and asserts on the JSON. |
| **Plugin install / marketplace** | `copilot plugin install <owner>/shipyard-copilot` for the CLI; `install.sh` + `shipyard/scripts/install.py` (`init`, `update`, `status`, `remove`, checksummed manifest) for the project | supported | Marketplace listing pending. |

## B. Proposed repository layout (template repo `shipyard-copilot`)

```text
shipyard-copilot/
├─ README.md                                  what ports, what is degraded, three modes, quickstart
├─ LICENSE · NOTICE                           MIT; credits carried over from Shipyard
├─ AGENTS.md                                  root agent instructions: Shipyard contract summary, .ai/ map, "never push", one slice at a time
├─ .github/
│  ├─ copilot-instructions.md                 repo-wide: .ai/ conventions, finding format, severity scale, assumption labels
│  ├─ instructions/
│  │  ├─ ai-folder.instructions.md            applyTo ".ai/**": who writes what, HUMAN.md one screen, no secrets
│  │  ├─ slice-branch.instructions.md         applyTo "**": touch-set rule, TEST_PLAN first, commit on the slice branch only
│  │  └─ tests.instructions.md                applyTo test globs: verifier-only, derive from ACs
│  ├─ agents/
│  │  ├─ shipyard-coordinator.agent.md        hub: tools read/edit/shell/task; VS Code agents:[12 specialists]; handoffs P0/P4/P8/merge; CLI hooks: brief-check
│  │  ├─ shipyard-discovery.agent.md          user-invocable:false; tools read/search/shell/write; model STANDARD
│  │  ├─ shipyard-goldfish.agent.md           user-invocable:false; tools read/search/fetch only; agents:[]; CLI hooks: goldfish-blinders
│  │  ├─ shipyard-architect.agent.md          user-invocable:false; model DEEP
│  │  ├─ shipyard-planner.agent.md            user-invocable:false; model DEEP
│  │  ├─ shipyard-implementer.agent.md        user-invocable:false; tools read/search/shell/write/edit; CLI hooks: write-scope, test-plan-gate
│  │  ├─ shipyard-verifier.agent.md           user-invocable:false; same tools; CLI hooks: write-scope, test-plan-gate
│  │  ├─ shipyard-code-reviewer.agent.md      user-invocable:false; tools read/search/shell/edit(TEST_PLAN status flip only via hook)
│  │  ├─ shipyard-security-reviewer.agent.md  user-invocable:false; tools read/search/shell
│  │  ├─ shipyard-contract-reviewer.agent.md  user-invocable:false
│  │  ├─ shipyard-integration-reviewer.agent.md
│  │  ├─ shipyard-reliability-reviewer.agent.md
│  │  └─ shipyard-simplicity-reviewer.agent.md
│  ├─ skills/                                 the 13 Shipyard skills, verbatim bodies, tool names mapped
│  │  ├─ shipyard-framework/SKILL.md          + references/finding-schema.md, references/modes.md
│  │  ├─ brainstorm-elephant-goldfish/SKILL.md
│  │  ├─ code-clarity/ · performance/ · domain-design/ · test-quality/ · test-design/
│  │  ├─ contract-review/ · integration-review/ · reliability-review/ · security-audit/ · simplicity-review/
│  │  └─ lang-packs/SKILL.md + references/<language>.md
│  ├─ prompts/                                IDE-mode phase checklists (VS Code/JetBrains); each starts with check.py --phase
│  │  ├─ shipyard.intake.prompt.md            P0: C-1..C-9 form, branch, breadth → shipyard_state.py init
│  │  ├─ shipyard.discover.prompt.md          P1-P3 driven by the coordinator with subagents; ends at P4 questions
│  │  ├─ shipyard.plan.prompt.md              P5-P7; ends with PLAN.HUMAN.md shown
│  │  ├─ shipyard.slice.prompt.md             P9 for one slice; ends with REVIEW.HUMAN.md
│  │  ├─ shipyard.merge.prompt.md             P9.9: checks, --no-ff merge, EVIDENCE, snapshot
│  │  ├─ shipyard.reconcile.prompt.md         P10
│  │  └─ shipyard.resume.prompt.md            read .ai/state.json and continue
│  ├─ extensions/                             CLI-mode dynamic workflows (public preview)
│  │  ├─ shipyard-discover/extension.mjs      P1-P3: defineWorkflow; ctx.parallel goldfish; ctx.agent with contracts
│  │  ├─ shipyard-plan/extension.mjs          P5-P7: critique routing, ≤2 refine cycles, readiness goldfish per slice
│  │  ├─ shipyard-slice/extension.mjs         P9: test plan gate, implementer ∥ verifier, verify, routed review, ≤3 fix rounds
│  │  └─ shipyard-lib/                        shared: registry/contract loaders, brief(), schema subset stripper, result validator
│  ├─ hooks/
│  │  └─ shipyard.json                        version 1; preToolUse (shell → protect-branches, readonly, write-scope, test-plan-gate; write|edit → write-scope, test-plan-gate, secrets-guard; task → brief-check); subagentStart/Stop → findings-gate
│  ├─ copilot/settings.json                   CLI repo settings: effortLevel profiles note, hooks enabled
│  ├─ workflows/
│  │  ├─ copilot-setup-steps.yml              cloud env: python3, test toolchain, restore .ai/ from <feature>-shipyard, add .git/info/exclude
│  │  ├─ shipyard-slice-check.yml             PR → feature/*: check.py (touch sets, TEST_PLAN approved before code, findings present, EVIDENCE.md, contracts valid, test command passes)
│  │  ├─ shipyard-notes-guard.yml             PR → main or feature/*: fail if .ai/** in diff
│  │  ├─ shipyard-plan-gate.yml               PR → feature/*: require DELIVERY_PLAN state APPROVED (+ label shipyard:plan-approved in cloud mode)
│  │  └─ shipyard-notes-sync.yml              cloud mode: commit uploaded .ai/ artifact to the notes branch
│  ├─ rulesets/
│  │  ├─ main-protection.json                 importable ruleset: PR required, 1 review, checks, no force push, no Copilot bypass
│  │  └─ feature-branches.json                feature/*: required check shipyard-slice-check, merge commits only
│  ├─ ISSUE_TEMPLATE/shipyard-intake.yml      cloud-mode P0 form: request, C-1..C-9, breadth, feature branch, base branch
│  ├─ PULL_REQUEST_TEMPLATE/shipyard-slice.md evidence summary, reviewers run, open findings, human change requests
│  └─ CODEOWNERS                              .ai/ @<owners>; .github/agents .github/hooks .github/extensions @<owners>
├─ shipyard/                                  tool-independent core (mirrors Shipyard's registry/contracts/scripts)
│  ├─ registry/roles.json                     unchanged schema; computeClasses map to Copilot model ids
│  ├─ contracts/*.schema.json                 unchanged
│  ├─ scripts/
│  │  ├─ shipyard_state.py                    unchanged + `gate <P> approve --by <login>` + `set-active-role`
│  │  ├─ shipyard_validate.py                 unchanged
│  │  ├─ check.py                             extended: --phase gate checks, PR-mode checks used by Actions
│  │  ├─ gen_agents.py                        writes .github/agents/*.agent.md model lines from the registry
│  │  └─ hooks/                               the 8 Python hooks + copilot_hooklib.py (payload adapter: toolName/toolArgs string, role from env or state.json)
│  └─ tests/                                  unittest for hooks (Copilot payloads) and check.py; node --test for extensions
├─ examples/sample-project/                   tiny repo with an illustrative .ai/ and a recorded headless run
└─ docs/
   ├─ getting-started.md · modes.md (CLI / IDE / cloud) · capability-map.md (table A) · unenforced.md (section D)
   ├─ gates.md (section C) · hooks.md · workflows.md · decisions/ADR-0001-three-modes.md …
```

## C. The human-gate model under Copilot

Shipyard's gates work because one coordinator session owns the chat and the workflows hand control back to it. Under
Copilot there are three different owners of "the chat", so there are three gate models. All three write the same
`.ai/state.json`, and `check.py` refuses to advance a phase whose gate is not recorded, so the modes can be mixed
(for example discover in the CLI, slices in the cloud).

### C.1 CLI mode (primary, highest fidelity)

- Launch: `copilot --experimental --agent=shipyard-coordinator --model <COORDINATOR model>` in the project folder,
  after `python3 shipyard/scripts/check.py --env` and with the hooks trusted (`--trust-folder` or interactive trust).
- The coordinator agent is the chat owner. It asks the P0 batched question itself, writes `state.json`, creates the
  branches, and then runs `shipyard-discover` as a dynamic workflow (in-session: "run the shipyard-discover workflow
  with args …", approved once). The workflow returns `NEEDS_HUMAN` with concepts, gaps and questions; the coordinator
  presents P4 and waits. Same for `shipyard-plan` (returns `AWAITING_PLAN_APPROVAL`, coordinator shows
  `PLAN.HUMAN.md`) and `shipyard-slice` (returns `READY_FOR_HUMAN`, coordinator shows `REVIEW.HUMAN.md`).
- A workflow never pauses for the human; it ends. That keeps ADR-0001. `ctx.pause` is used only for the SHARED-tier
  stop inside a slice, because the resumed run replays journaled steps and continues at VERIFY.
- Approval is explicit: the coordinator runs `shipyard_state.py gate P8 approve --by <login>` only after a literal
  yes; the `brief-check` and `write-scope` hooks keep the coordinator inside `.ai/**`.
- Headless CI use (`copilot workflow run shipyard-slice --args @slice.json --result-file out.json`) is for conformance
  tests, not for production runs, because headless runs cannot resume and need pre-granted permissions.

### C.2 IDE mode (VS Code; JetBrains with custom agents in preview)

- No dynamic workflows, so the coordinator agent orchestrates specialists directly as subagents (`agents:` lists the
  12; specialists have `agents: []` and no `agent` tool). Phase prompt files are the checklists the coordinator follows
  and the human can read.
- Gates are **handoffs with `send: false`**: after P3 the coordinator's response ends with a handoff button
  "Answer P4 questions" that pre-fills a reply template the human edits and sends; after P7, "Approve plan" pre-fills
  `APPROVE PLAN <feature>`; after P9, "Approve merge" / "Request changes". Nothing is sent until a human clicks, and
  the coordinator records the gate only on receipt of the literal phrase.
- Order and caps are convention here. `check.py --phase` at the top of every prompt file and `shipyard-slice-check`
  on the slice PR are the enforcement. Document this as degraded.

### C.3 Cloud mode (Copilot coding agent)

There is no interactive session, so the issue and the PR are the gates, and **one task = one phase** (the agent can
open one PR per task and runs at most 59 minutes on Actions).

| Gate | Mechanism |
|---|---|
| P0 Intake | Issue form `shipyard-intake.yml` (request, C-1..C-9 with defaults, breadth, feature and base branch). Assigning the issue to Copilot with the coordinator agent named in the body starts task 1 (`discover`). |
| P4 Questions | Task 1 ends by posting the concepts/gaps/questions as a comment on the issue (through the GitHub MCP server, read-only token widened for issues) and uploading `.ai/` as an artifact that `shipyard-notes-sync.yml` commits to the notes branch. The human answers in a comment and re-assigns; task 2 (`plan`) reads the answers. |
| P8 Plan approval | Task 2 posts `PLAN.HUMAN.md` as a comment. A maintainer adds the label `shipyard:plan-approved` (CODEOWNERS-restricted team). `shipyard-plan-gate.yml` and `check.py` require that label plus the `DELIVERY_PLAN.md` approval line before any slice PR can pass. |
| Merge | Each slice task opens a PR from `copilot/<slice-branch>` into the feature branch with the slice PR template. Required checks: `shipyard-slice-check`, `shipyard-notes-guard`, the test command. A human review approval is required by the feature-branch ruleset; the human merges with a merge commit (ruleset forbids squash so the evidence summary in the PR body is preserved in the merge commit). Change requests are PR review comments; the agent iterates in the same task. |
| Final PR | Human raises the PR from the feature branch to `main` exactly as in Shipyard. |

Honest limits of cloud mode: no local hooks except the `.github/hooks` subset; no `.git/info/exclude` persistence;
`.ai/` reaches the notes branch via Actions rather than the coordinator; reviewer isolation (goldfish blinders) is not
enforced; and Copilot must **not** be granted the ruleset bypass or it can push to protected branches.

## D. What is dropped or stated as unenforced, and the top 5 risks

**Dropped**

1. Shipyard-style `effort` per mode and `maxTurns` per agent: no `.agent.md` keys. Replaced by `model` per agent,
   workflow `limits`, and a `Budget:` line.
2. `claude plugin eval` suites: replaced by CI conformance runs on `examples/sample-project`.
3. Plugin marketplace listing: the CLI plugin installs from the repository directly and the project install has an
   installer with `remove`; only the marketplace entry is outstanding.
4. The single-entry-point guarantee (`Caller: shipyard:coordinator` refusal in every specialist): kept as text in each
   agent body, enforced only by the CLI `brief-check` hook on `task` calls and by `user-invocable: false`.
5. Hook retries (`findings-gate` sends a reviewer back up to 3 times): kept where `subagentStop` can `block`; the
   retry counter is best effort.

**Stated as unenforced (per mode)**

| Rule | CLI | IDE | Cloud |
|---|---|---|---|
| Hooks apply only to Shipyard agents (`agent_type`) | inferred from agent-scoped hooks and `state.json` | agent-scoped hooks where supported, else none | inferred from `state.json.activeRole` |
| Per-role write scope at write time | enforced (agent-scoped hooks) | tools restriction only | hook with inferred role; PR check is the backstop |
| Test plan before code at write time | enforced | unenforced; PR check | hook with inferred role; PR check |
| Goldfish sees nothing in `.ai/` | enforced (CLI hook) | unenforced | unenforced |
| Schema-checked agent returns | enforced inside workflows (subset) | post-hoc `shipyard_validate.py` | post-hoc |
| Loop caps and routing | code (workflows) | convention + `check.py` | convention + `check.py` |
| Never push / never touch `main` | hook + ruleset | ruleset | ruleset (no bypass) |

**Top 5 risks**

1. **Dynamic workflows are a moving target.** Public preview, `--experimental`, authoring API documented mainly by
   third parties, no headless resume, `ctx.agent` custom-agent/model options unverified at design time (since
   verified on CLI 1.0.108; see docs/workflows.md). Mitigation: isolate all
   SDK calls in `shipyard-lib`, pin the CLI version in CI (`COPILOT_AUTO_UPDATE=false`), keep the IDE-mode prompt
   files as the always-working fallback.
2. **Hook parity across clients.** CLI full, cloud subset (`ask` → `deny`, timeouts fail open), VS Code agent-scoped
   only, JetBrains preview. The same repo behaves differently per client; users will assume protection they do not
   have. Mitigation: `check.py --env` prints the effective guardrail matrix at startup; `docs/unenforced.md`.
3. **Role inference is spoofable.** Without `agent_type` in hook payloads, write-scope and test-plan-gate trust
   `state.json.activeRole`, which the coordinator writes. A confused coordinator weakens every per-role hook.
   Mitigation: agent-scoped hooks in CLI pass the role from the agent file, not from state; Actions diff checks.
4. **Cloud-mode state fragility.** One PR per task, 59-minute cap, fresh clone per task, `.ai/` round-trip through
   artifacts and a sync workflow. A lost artifact means a lost phase. Mitigation: every task also writes a compact
   summary comment on the issue; `shipyard-notes-sync` is idempotent; cloud mode is documented as "manual fidelity".
5. **Cost and prompt-injection surface.** Six DEEP reviewers plus goldfish fan-out per slice is many premium
   requests on Copilot's metered models; and the cloud agent and code review read instructions and skills from the
   PR head branch, so a malicious slice branch could alter the reviewers' instructions. Mitigation: `limits` in every
   workflow, CODEOWNERS on `.github/agents|skills|hooks|extensions` and `.ai/`, `shipyard-notes-guard` on PRs.

## E. Phased build plan

**Phase 1: core port, CLI-first, no workflow engine (2–3 weeks)**
- Copy `registry/`, `contracts/`, `scripts/` into `shipyard/`; add `gen_agents.py`; write `copilot_hooklib.py`
  (payload adapter: `toolName`, `toolArgs` JSON string, `cwd`, role from `SHIPYARD_ROLE` env or `state.json`).
- Port the 13 agents to `.github/agents/*.agent.md` and the 13 skills to `.github/skills/` with tool names mapped;
  specialists `user-invocable: false`; reviewers without `write`.
- `.github/hooks/shipyard.json` wiring all eight hooks; agent-scoped hooks in the agent files for CLI.
- `AGENTS.md`, `copilot-instructions.md`, path-scoped instructions.
- Coordinator orchestrates specialists directly through the `task` tool following the phase prompt files
  (so Phase 1 already runs end to end in CLI and VS Code, with order enforced by `check.py --phase`).
- Actions: `shipyard-slice-check`, `shipyard-notes-guard`, `shipyard-plan-gate`; rulesets JSON; CODEOWNERS; PR
  template. Unit tests for hooks with Copilot payloads. Exit criterion: the sample project completes one slice in
  CLI mode with every gate recorded and every Action green.

**Phase 2: dynamic workflows and conformance (2–3 weeks, gated on verifying the extension API)**
- Spike: confirm `ctx.agent` options (custom agent name, model, tools), `matcher` targets for `subagentStart/Stop`,
  and schema-subset behaviour. Record findings in `docs/decisions/ADR-0002-dynamic-workflows.md`.
- Implement `shipyard-discover`, `shipyard-plan`, `shipyard-slice` as `extension.mjs` with `argsSchema`, `phases`,
  `limits`, `ctx.parallel` for goldfish and implementer∥verifier, `ctx.step` for every deterministic check, and full
  contract validation after each `ctx.agent`. Coordinator switches to launching workflows when `--experimental` is on.
- CI conformance: `copilot workflow run … --result-file` on the sample project, asserting on the result JSON; node
  tests for the extensions with a fake `ctx`.

**Phase 3: IDE handoffs and cloud mode (2 weeks)**
- VS Code: `handoffs` on the coordinator for P4/P8/merge with `send: false`; `agents:` allowlists; prompt files
  polished; JetBrains tested as far as its preview allows.
- Cloud: `shipyard-intake.yml` issue form, `copilot-setup-steps.yml` (toolchain, restore `.ai/` from the notes
  branch), `shipyard-notes-sync.yml`, label-based P8 gate, PR-template evidence, MCP repo settings snippet
  (GitHub MCP with issue-comment tools only).
- Docs: `modes.md`, `capability-map.md`, `unenforced.md`, getting-started per mode; `check.py --env` guardrail
  matrix; optional gh-aw reviewer sweep workflow as an example.

## F. Sources

GitHub Docs
- Custom agents configuration reference: https://docs.github.com/en/copilot/reference/custom-agents-configuration
- About agent skills: https://docs.github.com/en/copilot/concepts/agents/about-agent-skills
- Hooks reference: https://docs.github.com/en/copilot/reference/hooks-reference
- Hooks for Copilot (concepts): https://docs.github.com/en/copilot/concepts/agents/hooks
- About hooks (coding agent): https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-hooks
- Using hooks with Copilot CLI: https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks
- Repository custom instructions (applyTo, excludeAgent, AGENTS.md): https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions
- Invoking custom agents in Copilot CLI: https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/invoke-custom-agents
- CLI command reference: https://docs.github.com/en/copilot/reference/cli-command-reference
- CLI programmatic reference (`-p`, `--allow-tool`, `--model`, `workflow run`, exit codes): https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference
- Running Copilot CLI programmatically: https://docs.github.com/en/copilot/how-tos/copilot-cli/automate-copilot-cli/run-cli-programmatically
- Using dynamic workflows: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-dynamic-workflows
- About CLI extensions: https://docs.github.com/en/enterprise-cloud@latest/copilot/concepts/agents/copilot-cli/about-cli-extensions
- `/fleet` parallel tasks: https://docs.github.com/en/copilot/concepts/agents/copilot-cli/fleet
- Delegating and parallelizing work with agents: https://docs.github.com/en/copilot/concepts/agent-capabilities/choosing-and-delegating-agent-work/delegating-and-parallelizing-work-with-agents
- Copilot SDK custom agents and sub-agent orchestration: https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/custom-agents
- Customize the coding agent environment (`copilot-setup-steps.yml`): https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/customize-the-agent-environment
- Extend coding agent with MCP: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/extend-coding-agent-with-mcp
- About the coding agent (cloud): https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent
- Copilot CLI in GitHub Actions: https://docs.github.com/en/copilot/concepts/agent-capabilities/agent-powered-workflows-and-operations/copilot-cli-in-github-actions

GitHub Changelog / Blog
- Copilot CLI generally available (hooks, skills, `&` delegation): https://github.blog/changelog/2026-02-25-github-copilot-cli-is-now-generally-available/
- Copilot SDK public preview: https://github.blog/changelog/2026-04-02-copilot-sdk-in-public-preview/
- Custom agents in JetBrains/Eclipse/Xcode (preview): https://github.blog/changelog/2025-11-18-custom-agents-available-in-github-copilot-for-jetbrains-eclipse-and-xcode-now-in-public-preview/
- JetBrains agentic improvements (custom agents, subagents GA; hooks preview): https://github.blog/changelog/2026-03-11-major-agentic-capabilities-improvements-in-github-copilot-for-jetbrains-ides/
- VS Code March 2026 releases (nested subagents, agent-scoped hooks): https://github.blog/changelog/2026-04-08-github-copilot-in-visual-studio-code-march-releases/
- VS Code July 2026 releases (subagent tracking): https://github.blog/changelog/2026-07-30-github-copilot-in-visual-studio-code-july-2026-releases/
- Copilot code review: skills and MCP GA: https://github.blog/changelog/2026-07-29-copilot-code-review-agent-skills-and-mcp-now-generally-available/
- CLI custom agents and delegation to the coding agent: https://github.blog/changelog/2025-10-28-github-copilot-cli-use-custom-agents-and-delegate-to-copilot-coding-agent/
- What's new with Copilot coding agent: https://github.blog/ai-and-ml/github-copilot/whats-new-with-github-copilot-coding-agent/
- `/fleet` in Copilot CLI: https://github.blog/2026/04/01/run-multiple-agents-at-once-with-fleet-in-copilot-cli/

VS Code docs
- Custom agents (handoffs, user-invocable, disable-model-invocation): https://code.visualstudio.com/docs/copilot/customization/custom-agents
- Subagents (`runSubagent`, `agents:` key, nesting, model order): https://code.visualstudio.com/docs/copilot/agents/subagents

Repositories and third-party (used for leads; marked unverified where relied on)
- github/spec-kit: https://github.com/github/spec-kit
- github/awesome-copilot agents: https://awesome-copilot.github.com/agents/
- BMAD-METHOD Copilot guide (chatmodes era) and `bmad-copilot-adapter`: https://registry.npmjs.org/bmad-copilot-adapter
- github/gh-aw (Agentic Workflows, safe-outputs): https://github.com/github/gh-aw
- github/copilot-sdk issue #301 (subagents): https://github.com/github/copilot-sdk/issues/301
- Dynamic workflow authoring (`defineWorkflow`, `ctx.agent` schema, CI invocation) — third party: https://startdebugging.net/2026/10/how-to-define-a-github-copilot-cli-dynamic-workflow-and-run-it-from-ci/
- Copilot CLI extensions overview — third party: https://dev.to/htekdev/github-copilot-cli-extensions-the-most-powerful-feature-nobodys-talking-about-4f8f
- Structured output comparison (Copilot "none") — third party: https://github.com/pathscale/RustAgentAbstraction/pull/10

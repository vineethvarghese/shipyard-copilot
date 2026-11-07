// Shared helpers for the three Shipyard dynamic workflows (shipyard-discover, shipyard-plan, shipyard-slice).
//
// Everything that touches the Copilot extension runtime is isolated here, so a change in the preview API is a
// change in one file. The workflows themselves only use the toolkit returned by `makeToolkit(ctx, name)`.
//
// Runtime facts this file relies on, and how sure we are (see docs/decisions/ADR-0002-dynamic-workflows.md):
//   - `ctx.agent(prompt, { label, schema })` runs a subagent, validates a structural subset of the schema, retries
//     once on a mismatch and resolves to null on failure. Documented by a third party; label and schema only.
//   - Identical calls are memoised by label, so every label here is unique within a run (a call counter).
//   - `ctx.step(key, fn)` journals fn's result under key and replays it on resume. Keys are unique within a run.
//   - Whether `ctx.agent` accepts `agent` (a custom agent name), `model` or `reasoningEffort` is unverified.
//     `agentOptions()` is the one switch: `args.agentSelection` "agent" (default) passes them; "prompt" passes
//     only label and schema and names the agent in a preamble line of the prompt instead.
//   - The SDK entry point `@github/copilot-sdk/extension` (defineWorkflow, joinSession) is unverified; `attach()`
//     imports it dynamically and does nothing when it is absent, so the workflows load under plain Node for tests.
//
// This file reads the registry and the contracts from disk when the args omit them (Node `fs`, read-only, under
// the repository root). It never writes, never uses the network, the clock or randomness.

import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
export const SHIPYARD_DIR = join(REPO_ROOT, 'shipyard');
export const STRIP_KEYS = ['$schema', '$id', 'title', 'description', 'x-contract-version'];
export const SEVERITIES = ['BLOCKING', 'MAJOR', 'MINOR', 'NOTE'];
export const FORMAL_TIERS = ['none', 'invariants', 'properties', 'model-checked'];
export const AGENT_SELECTIONS = ['agent', 'prompt'];
export const SDK_MODULE = '@github/copilot-sdk/extension';

// ---------------------------------------------------------------------------------------------
// Workflow definition and registration
// ---------------------------------------------------------------------------------------------

/** Shape-check a workflow definition and return it unchanged (a plain `{ meta, run }` object). */
export function defineWorkflow(def) {
  if (!def || typeof def !== 'object') throw new Error('defineWorkflow: expected { meta, run }');
  const m = def.meta;
  if (!m || typeof m.name !== 'string' || !m.name) throw new Error('defineWorkflow: meta.name is required');
  if (typeof m.description !== 'string' || !m.description) throw new Error(`defineWorkflow(${m.name}): meta.description is required`);
  if (!Array.isArray(m.phases) || !m.phases.length) throw new Error(`defineWorkflow(${m.name}): meta.phases must be a non-empty list`);
  for (const p of m.phases) if (!p || typeof p.title !== 'string') throw new Error(`defineWorkflow(${m.name}): every phase needs a title`);
  if (m.argsSchema && typeof m.argsSchema !== 'object') throw new Error(`defineWorkflow(${m.name}): meta.argsSchema must be an object`);
  if (m.limits && typeof m.limits !== 'object') throw new Error(`defineWorkflow(${m.name}): meta.limits must be an object`);
  if (typeof def.run !== 'function') throw new Error(`defineWorkflow(${m.name}): run(ctx) must be a function`);
  return def;
}

/**
 * Register the workflow with the Copilot CLI extension SDK when it is present.
 * Returns true when the SDK registered it, false when the SDK is absent (tests, plain Node).
 */
export async function attach(def) {
  let sdk = null;
  try {
    sdk = await import(SDK_MODULE);
  } catch (e) {
    return false;
  }
  if (!sdk || typeof sdk.defineWorkflow !== 'function') return false;
  const wf = sdk.defineWorkflow(def);
  if (typeof sdk.joinSession === 'function') await sdk.joinSession({ workflows: [wf] });
  return true;
}

// ---------------------------------------------------------------------------------------------
// Inputs: registry and contracts, from args or from the repository
// ---------------------------------------------------------------------------------------------

export function loadRegistryFile(root = SHIPYARD_DIR) {
  return JSON.parse(readFileSync(join(root, 'registry', 'roles.json'), 'utf8'));
}

export function loadContractFiles(root = SHIPYARD_DIR) {
  const dir = join(root, 'contracts');
  const out = {};
  for (const f of readdirSync(dir).sort()) {
    if (f.endsWith('.schema.json')) out[f.replace(/\.schema\.json$/, '')] = JSON.parse(readFileSync(join(dir, f), 'utf8'));
  }
  return out;
}

/** The registry and contracts: from args when given, else from <repo>/shipyard/ (or args.shipyardDir). */
export function loadInputs(args, name) {
  const A = args || {};
  const root = typeof A.shipyardDir === 'string' && A.shipyardDir ? resolve(REPO_ROOT, A.shipyardDir) : SHIPYARD_DIR;
  let registry = A.registry;
  let contracts = A.contracts;
  if (registry == null) {
    try {
      registry = loadRegistryFile(root);
    } catch (e) {
      throw new Error(`${name}: args.registry (parsed registry/roles.json) is required: could not read it from ${root} (${e.message})`);
    }
  }
  if (contracts == null) {
    try {
      contracts = loadContractFiles(root);
    } catch (e) {
      throw new Error(`${name}: args.contracts (contracts keyed by file stem) is required: could not read them from ${root} (${e.message})`);
    }
  }
  if (!registry || !registry.roles || !registry.computeClasses) throw new Error(`${name}: args.registry (parsed registry/roles.json) is required`);
  if (!contracts || typeof contracts !== 'object') throw new Error(`${name}: args.contracts (contracts keyed by file stem) is required`);
  return { registry, contracts };
}

// ---------------------------------------------------------------------------------------------
// JSON-schema validation (the full subset the contracts use; the runtime enforces less)
// ---------------------------------------------------------------------------------------------

/**
 * Validate `value` against `schema`. Supports type (incl. arrays of types), enum, const, required, properties,
 * additionalProperties, items, minLength, maxLength, minimum, maximum, minItems, maxItems, anyOf/oneOf/allOf.
 * Returns a list of error strings (empty when valid).
 */
export function validate(schema, value, path = '$') {
  const errs = [];
  if (schema === true || schema == null) return errs;
  if (schema === false) return [`${path}: not allowed`];
  const typeOf = (v) => (v === null ? 'null' : Array.isArray(v) ? 'array' : Number.isInteger(v) ? 'integer' : typeof v);
  const types = schema.type ? (Array.isArray(schema.type) ? schema.type : [schema.type]) : null;
  if (types) {
    const t = typeOf(value);
    const ok = types.some((x) => x === t || (x === 'number' && (t === 'integer' || t === 'number')));
    if (!ok) return [`${path}: expected ${types.join('|')}, got ${t}`];
  }
  if (schema.enum && !schema.enum.some((e) => e === value)) errs.push(`${path}: ${JSON.stringify(value)} not in enum`);
  if ('const' in schema && schema.const !== value) errs.push(`${path}: ${JSON.stringify(value)} is not the constant ${JSON.stringify(schema.const)}`);
  if (typeof value === 'string') {
    if (schema.minLength != null && value.length < schema.minLength) errs.push(`${path}: shorter than ${schema.minLength}`);
    if (schema.maxLength != null && value.length > schema.maxLength) errs.push(`${path}: longer than ${schema.maxLength}`);
  }
  if (typeof value === 'number') {
    if (schema.minimum != null && value < schema.minimum) errs.push(`${path}: below ${schema.minimum}`);
    if (schema.maximum != null && value > schema.maximum) errs.push(`${path}: above ${schema.maximum}`);
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const r of schema.required || []) if (!(r in value)) errs.push(`${path}: missing ${r}`);
    const props = schema.properties || {};
    for (const k of Object.keys(value)) {
      if (props[k]) errs.push(...validate(props[k], value[k], `${path}.${k}`));
      else if (schema.additionalProperties === false) errs.push(`${path}: unexpected property ${k}`);
      else if (schema.additionalProperties && typeof schema.additionalProperties === 'object') errs.push(...validate(schema.additionalProperties, value[k], `${path}.${k}`));
    }
  }
  if (Array.isArray(value)) {
    if (schema.minItems != null && value.length < schema.minItems) errs.push(`${path}: fewer than ${schema.minItems} items`);
    if (schema.maxItems != null && value.length > schema.maxItems) errs.push(`${path}: more than ${schema.maxItems} items`);
    if (schema.items) value.forEach((v, i) => errs.push(...validate(schema.items, v, `${path}[${i}]`)));
  }
  if (Array.isArray(schema.allOf)) for (const s of schema.allOf) errs.push(...validate(s, value, path));
  if (Array.isArray(schema.anyOf) && !schema.anyOf.some((s) => validate(s, value, path).length === 0)) errs.push(`${path}: matches none of anyOf`);
  if (Array.isArray(schema.oneOf) && schema.oneOf.filter((s) => validate(s, value, path).length === 0).length !== 1) errs.push(`${path}: must match exactly one of oneOf`);
  return errs;
}

/** The contract for `<stem>@<major>` with its metadata keys stripped; throws on a major-version mismatch. */
export function schemaFor(contracts, contractRef, name = 'workflow') {
  const m = /^([A-Za-z0-9_-]+)@(\d+)$/.exec(String(contractRef || ''));
  if (!m) throw new Error(`${name}: bad contract reference '${contractRef}' (expected '<stem>@<major>')`);
  const stem = m[1];
  const wanted = Number(m[2]);
  const s = contracts[stem];
  if (!s || typeof s !== 'object') throw new Error(`${name}: contract '${stem}' missing from args.contracts`);
  const version = String(s['x-contract-version'] || '');
  const major = Number(version.split('.')[0]);
  if (!version || major !== wanted) {
    throw new Error(`${name}: contract '${stem}' major version mismatch: registry wants ${wanted}, schema is '${version || 'unversioned'}'`);
  }
  const out = {};
  for (const k of Object.keys(s)) if (STRIP_KEYS.indexOf(k) === -1) out[k] = s[k];
  return out;
}

/** Throw when the workflow's own result contract is not at the major the registry expects. */
export function checkWorkflowContract(registry, contracts, name) {
  const stem = `${name}-workflow-result`;
  const resultContract = contracts[stem];
  const wantMajor = registry.workflowContractMajor && registry.workflowContractMajor[name];
  if (resultContract && wantMajor != null) {
    const have = Number(String(resultContract['x-contract-version'] || '').split('.')[0]);
    if (have !== Number(wantMajor)) throw new Error(`${name}: contract '${stem}' major ${have} does not match registry workflowContractMajor.${name} ${wantMajor}`);
  }
}

// ---------------------------------------------------------------------------------------------
// Briefs and agent selection
// ---------------------------------------------------------------------------------------------

/** The brief header every Shipyard specialist expects, then the free text. Same lines as Shipyard. */
export function brief(b) {
  const lines = ['Caller: shipyard:coordinator', `Mode: ${b.mode}`];
  if (b.slice != null) lines.push(`Slice: ${b.slice}`);
  if (b.round != null) lines.push(`Round: ${b.round}`);
  if (b.featureBranch) lines.push(`Feature-branch: ${b.featureBranch}`);
  if (b.sliceBranch) lines.push(`Slice-branch: ${b.sliceBranch}`);
  if (b.diff) lines.push(`Diff: ${b.diff === true ? `git diff ${b.featureBranch}...${b.sliceBranch}` : b.diff}`);
  if (b.read && b.read.length) lines.push(`Read: ${b.read.join(', ')}`);
  if (b.write) lines.push(`Write: ${Array.isArray(b.write) ? b.write.join(', ') : b.write}`);
  if (b.budgetTurns) lines.push(`Budget: ${b.budgetTurns} turns`);
  return lines.join('\n') + (b.text ? `\n\n${b.text}` : '') + '\n';
}

/** `shipyard:code-reviewer` or `shipyard-code-reviewer` → `code-reviewer`. */
export function shortAgentName(agent) {
  return String(agent || '').replace(/^shipyard[:-]/, '');
}

/** The Copilot custom-agent name for a registry agent: `shipyard-<short>`. */
export function copilotAgentName(agent) {
  return `shipyard-${shortAgentName(agent)}`;
}

export function agentSelectionOf(args) {
  const sel = args && args.agentSelection != null ? args.agentSelection : 'agent';
  if (AGENT_SELECTIONS.indexOf(sel) === -1) throw new Error(`args.agentSelection must be one of ${AGENT_SELECTIONS.join(', ')}, got '${sel}'`);
  return sel;
}

/** The preamble that names the agent when the runtime cannot be told which custom agent to run. */
export function agentPreamble(agentName) {
  return `Act as \`${agentName}\`: read .github/agents/${agentName}.agent.md first and follow it as your identity, tools and rules.\n\n`;
}

/**
 * The extra `ctx.agent` options that select the agent and its compute class.
 * selection "agent": { agent: "shipyard-<short>", model, reasoningEffort } (unverified runtime options).
 * selection "prompt": {} — the agent is named in the prompt by `agentPreamble` instead.
 */
export function agentOptions(registry, roleName, mode, selection = 'agent') {
  const r = registry.roles[roleName];
  if (!r) throw new Error(`role '${roleName}' is not in the registry`);
  const cls = (r.modes || {})[mode];
  if (!cls) throw new Error(`role '${roleName}' has no mode '${mode}' in the registry`);
  const c = registry.computeClasses[cls];
  if (!c) throw new Error(`compute class '${cls}' (role '${roleName}', mode '${mode}') is not defined`);
  if (selection === 'prompt') return {};
  const out = { agent: copilotAgentName(r.agent) };
  if (c.model) out.model = c.model;
  if (c.effort) out.reasoningEffort = c.effort;
  return out;
}

// ---------------------------------------------------------------------------------------------
// Findings
// ---------------------------------------------------------------------------------------------

export function sevRank(s) {
  const i = SEVERITIES.indexOf(s);
  return i === -1 ? SEVERITIES.length : i;
}

export function siteOf(f) {
  return `${String(f.location || '').trim().toLowerCase()}|${String(f.category || '').trim().toLowerCase()}`;
}

export function memberKey(f) {
  return `${(f.reporters || [])[0] || '?'}:${f.id}`;
}

export function keysOf(f) {
  return f.memberKeys || [memberKey(f)];
}

export function anyKey(map, f) {
  return keysOf(f).some((k) => map[k]);
}

export function markKeys(map, f, value) {
  for (const k of keysOf(f)) map[k] = value;
}

/** Plan dedupe: findings at the same location with the same category are one problem, whoever reported them. */
export function dedupePlanFindings(list) {
  const groups = {};
  const order = [];
  for (const f of list) {
    const k = siteOf(f);
    if (!groups[k]) {
      groups[k] = [];
      order.push(k);
    }
    groups[k].push(f);
  }
  const out = [];
  for (const k of order) {
    const g = groups[k].slice().sort((a, b) => sevRank(a.severity) - sevRank(b.severity));
    const top = Object.assign({}, g[0]);
    const reporters = [];
    for (const f of g) for (const r of f.reporters || []) if (reporters.indexOf(r) === -1) reporters.push(r);
    top.reporters = reporters;
    top.status = g.some((f) => f.status === 'OPEN') ? 'OPEN' : g[0].status;
    out.push(top);
  }
  out.sort((a, b) => sevRank(a.severity) - sevRank(b.severity) || String(a.id).localeCompare(String(b.id)));
  return out;
}

/**
 * Slice dedupe: two findings are the same problem when they sit at the same location with the same category AND
 * come from different reviewers. Findings from one reviewer are never merged with each other. Each raw finding
 * has a stable member key `<reporter>:<id>`; a merged finding carries all of them in `memberKeys`.
 */
export function dedupeSliceFindings(list) {
  const groups = [];
  const bySite = {};
  for (const f of list) {
    const site = siteOf(f);
    const candidates = bySite[site] || (bySite[site] = []);
    const mine = f.reporters || [];
    let g = candidates.find((grp) => !grp.some((m) => (m.reporters || []).some((r) => mine.indexOf(r) !== -1)));
    if (!g) {
      g = [];
      candidates.push(g);
      groups.push(g);
    }
    g.push(f);
  }
  const out = [];
  for (const g of groups) {
    const openFirst = (f) => (f.status === 'OPEN' ? 0 : 1);
    const sorted = g.slice().sort((a, b) => openFirst(a) - openFirst(b) || sevRank(a.severity) - sevRank(b.severity));
    const top = Object.assign({}, sorted[0]);
    const reporters = [];
    for (const f of g) for (const r of f.reporters || []) if (reporters.indexOf(r) === -1) reporters.push(r);
    top.reporters = reporters;
    top.status = g.some((f) => f.status === 'OPEN') ? 'OPEN' : sorted[0].status;
    top.memberKeys = g.map(memberKey);
    out.push(top);
  }
  out.sort((a, b) => sevRank(a.severity) - sevRank(b.severity) || String(a.id).localeCompare(String(b.id)));
  return out;
}

export const dedupe = dedupeSliceFindings;

export function publicFinding(f) {
  const out = Object.assign({}, f);
  delete out.memberKeys;
  return out;
}

export function normaliseFindings(list, roleName) {
  return (Array.isArray(list) ? list : []).map((f) => Object.assign({}, f, { reporters: [roleName] }));
}

export function fixScopeOf(registry) {
  return Array.isArray(registry.fixScope) ? registry.fixScope : ['BLOCKING', 'MAJOR', 'MINOR'];
}

// ---------------------------------------------------------------------------------------------
// Routing
// ---------------------------------------------------------------------------------------------

/** Plan routing: `always` routes; a flag that is true routes; a flag that is not false is uncertain and routes. */
export function routePlan(registry, flags) {
  const F = flags && typeof flags === 'object' ? flags : {};
  const routed = [];
  const notRouted = [];
  for (const rule of (registry.routing && registry.routing.plan) || []) {
    const hits = [];
    for (const w of rule.when || []) {
      if (w === 'always') hits.push('always');
      else if (F[w] === true) hits.push(`${w}=true`);
      else if (F[w] !== false) hits.push(`${w}=uncertain`);
    }
    if (hits.length) routed.push({ role: rule.role, because: hits.join('; ') });
    else notRouted.push({ role: rule.role, because: `no trigger: ${(rule.when || []).map((w) => `${w}=false`).join(', ')}` });
  }
  return { routed, notRouted };
}

function flagOf(facts, name) {
  const f = facts && facts[name];
  const v = f && typeof f === 'object' ? f.value : f;
  if (v === true) return { value: true, uncertain: false, evidence: (f && f.evidence) || '' };
  if (v === false) return { value: false, uncertain: false, evidence: (f && f.evidence) || '' };
  return { value: null, uncertain: true, evidence: 'flag missing or uncertain' };
}

/** Slice routing: `when` any flag true → route unless an `unless` flag is true; uncertain → route. */
export function routeSlice(registry, facts) {
  const routed = [];
  const skipped = [];
  for (const rule of (registry.routing && registry.routing.slice) || []) {
    const when = rule.when || [];
    const hits = [];
    for (const w of when) {
      const fl = w === 'always' ? { value: true, evidence: 'always' } : flagOf(facts, w);
      if (fl.value === true || fl.uncertain) hits.push(`${w}=${fl.uncertain ? 'uncertain' : 'true'}${fl.evidence ? ` (${fl.evidence})` : ''}`);
    }
    if (!hits.length) {
      skipped.push({ role: rule.role, because: `no trigger: ${when.map((w) => `${w}=false`).join(', ')}` });
      continue;
    }
    let blockedBy = null;
    for (const u of rule.unless || []) {
      const fl = flagOf(facts, u);
      if (fl.value === true) {
        blockedBy = `${u}=true${fl.evidence ? ` (${fl.evidence})` : ''}`;
        break;
      }
    }
    if (blockedBy) skipped.push({ role: rule.role, because: `not routed: ${blockedBy}` });
    else routed.push({ role: rule.role, because: hits.join('; ') });
  }
  return { routed, skipped };
}

// ---------------------------------------------------------------------------------------------
// Toolkit: the per-run helpers a workflow's run(ctx) uses
// ---------------------------------------------------------------------------------------------

export function json(x) {
  return JSON.stringify(x, null, 2);
}

/**
 * Build the helpers for one run. `name` is the workflow's short name (discover, plan, slice) used in messages.
 * Loads the registry and contracts, checks the workflow's own result contract, and returns:
 *   REG, CONTRACTS, LIMITS, RETRIES, FIX_SCOPE, A (args), role, shortName, compute, contractRefFor, schema,
 *   brief, call, enter, step, log, parallel, json, selection.
 */
export function makeToolkit(ctx, name) {
  if (!ctx || typeof ctx !== 'object') throw new Error(`${name}: run(ctx) needs the workflow context`);
  const A = ctx.args && typeof ctx.args === 'object' ? ctx.args : {};
  const { registry: REG, contracts: CONTRACTS } = loadInputs(A, name);
  checkWorkflowContract(REG, CONTRACTS, name);
  const selection = agentSelectionOf(A);
  const LIMITS = REG.limits || {};
  const RETRIES = Number.isInteger(LIMITS.reviewerRetries) ? LIMITS.reviewerRetries : 1;
  const FIX_SCOPE = fixScopeOf(REG);

  let currentPhase = null;
  let callSeq = 0;
  const stepKeys = {};

  function log(msg) {
    if (typeof ctx.log === 'function') ctx.log(String(msg));
  }

  function enter(title) {
    currentPhase = title;
    if (typeof ctx.phase === 'function') ctx.phase(title);
  }

  async function parallel(thunks) {
    if (typeof ctx.parallel === 'function') return ctx.parallel(thunks);
    return Promise.all(thunks.map((t) => Promise.resolve().then(t).catch(() => null)));
  }

  // Journaled deterministic work. Keys are unique within a run; a repeated key gets a counter suffix so a
  // computation that runs once per round never replays another round's value.
  async function step(key, fn) {
    const n = (stepKeys[key] = (stepKeys[key] || 0) + 1);
    const k = n === 1 ? key : `${key} #${n}`;
    if (typeof ctx.step === 'function') return ctx.step(k, fn);
    return fn();
  }

  function role(roleName) {
    const r = REG.roles[roleName];
    if (!r) throw new Error(`${name}: role '${roleName}' is not in the registry`);
    return r;
  }

  function shortName(roleName) {
    return shortAgentName(role(roleName).agent);
  }

  function compute(roleName, mode) {
    const cls = (role(roleName).modes || {})[mode];
    if (!cls) throw new Error(`${name}: role '${roleName}' has no mode '${mode}' in the registry`);
    const c = REG.computeClasses[cls];
    if (!c) throw new Error(`${name}: compute class '${cls}' (role '${roleName}', mode '${mode}') is not defined`);
    return { model: c.model, effort: c.effort };
  }

  function contractRefFor(roleName, mode) {
    const r = role(roleName);
    if (r.contracts && r.contracts[mode]) return r.contracts[mode];
    if (r.contract) return r.contract;
    throw new Error(`${name}: role '${roleName}' has no contract for mode '${mode}'`);
  }

  function schema(contractRef) {
    return schemaFor(CONTRACTS, contractRef, name);
  }

  /**
   * Run one specialist: brief → ctx.agent with the stripped contract as schema → full re-validation in a step.
   * One retry (registry.limits.reviewerRetries) on a null or invalid result; then null (the caller fails closed).
   */
  async function call(roleName, mode, briefObj, label, contractRef) {
    const r = role(roleName);
    compute(roleName, mode);
    const sch = schema(contractRef || contractRefFor(roleName, mode));
    const extra = agentOptions(REG, roleName, mode, selection);
    const text = brief(Object.assign({}, briefObj, { mode }));
    const prompt = selection === 'prompt' ? agentPreamble(copilotAgentName(r.agent)) + text : text;
    const seq = ++callSeq;
    for (let attempt = 0; attempt <= RETRIES; attempt++) {
      const tag = `${label} #${seq}${attempt ? ` (retry ${attempt})` : ''}`;
      let res = null;
      try {
        res = await ctx.agent(prompt, Object.assign({}, extra, { label: tag, schema: sch, phase: currentPhase }));
      } catch (e) {
        res = null;
      }
      if (res != null && typeof res === 'object') {
        const errs = await step(`validate ${tag}`, () => validate(sch, res));
        if (!errs.length) return res;
        log(`${tag}: result does not match its contract: ${errs.slice(0, 5).join('; ')}`);
      }
      log(`${label}: no valid result${attempt < RETRIES ? '; retrying' : '; giving up'}`);
    }
    return null;
  }

  return {
    A, REG, CONTRACTS, LIMITS, RETRIES, FIX_SCOPE, selection, role, shortName, compute, contractRefFor, schema, brief, call,
    enter, step, log, parallel, json, phaseNow: () => currentPhase,
  };
}

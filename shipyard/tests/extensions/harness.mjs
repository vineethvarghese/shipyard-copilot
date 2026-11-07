// Test harness for the Shipyard dynamic workflows (.github/extensions/shipyard-*/extension.mjs).
// Imports a workflow module and runs `workflow.run(ctx)` with a fake ctx: agents scripted per key
// `<agent short name>|<MODE>` (the agent from the `agent` option or the prompt preamble, the mode from the
// prompt's `Mode:` line), a step journal (unique keys, JSON-serialisable values), parallel batches, pauses.
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { validate } from '../../../.github/extensions/shipyard-lib/index.mjs';

export { validate };

export const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
export const SHIPYARD_DIR = join(REPO_ROOT, 'shipyard');
export const EXTENSIONS_DIR = join(REPO_ROOT, '.github', 'extensions');

export function loadRegistry() {
  return JSON.parse(readFileSync(join(SHIPYARD_DIR, 'registry', 'roles.json'), 'utf8'));
}

export function loadContracts() {
  const dir = join(SHIPYARD_DIR, 'contracts');
  const out = {};
  for (const f of readdirSync(dir)) {
    if (f.endsWith('.schema.json')) out[f.replace(/\.schema\.json$/, '')] = JSON.parse(readFileSync(join(dir, f), 'utf8'));
  }
  return out;
}

export function extensionPath(name) {
  return join(EXTENSIONS_DIR, `shipyard-${name}`, 'extension.mjs');
}

export function workflowSource(name) {
  return readFileSync(extensionPath(name), 'utf8');
}

export async function loadWorkflow(name) {
  const mod = await import(pathToFileURL(extensionPath(name)).href);
  if (!mod.workflow || typeof mod.workflow.run !== 'function') throw new Error(`${name}: extension.mjs must export workflow = { meta, run }`);
  return mod.workflow;
}

export async function loadMeta(name) {
  return (await loadWorkflow(name)).meta;
}

export function modeOf(prompt) {
  const m = /^Mode: (\S+)$/m.exec(prompt);
  return m ? m[1] : null;
}

export function agentOf(prompt, opts) {
  if (opts && opts.agent) return String(opts.agent).replace(/^shipyard[:-]/, '');
  const m = /^Act as `shipyard-([a-z-]+)`/.exec(prompt);
  return m ? m[1] : '?';
}

export function keyOf(prompt, opts) {
  return `${agentOf(prompt, opts)}|${modeOf(prompt)}`;
}

/**
 * Run a workflow with scripted agents.
 * @param {string} name workflow short name (discover, plan, slice)
 * @param {object} args workflow args (registry/contracts added if absent, unless options.noInputs)
 * @param {object} script map key → array of responses (object | null | function(prompt, opts, call) → object|null)
 * @param {object} defaults map key → default response (object | function) used when the queue is empty
 * @param {object} options { pauses: { [name-prefix]: value | function }, noInputs: boolean }
 */
export async function runWorkflow(name, args, script = {}, defaults = {}, options = {}) {
  const workflow = await loadWorkflow(name);
  const calls = [];
  const phases = [];
  const logs = [];
  const errors = [];
  const steps = [];
  const pauses = [];
  const labels = {};
  const stepKeys = {};
  const queues = {};
  for (const k of Object.keys(script)) queues[k] = script[k].slice();
  let batch = null;
  let batchSeq = 0;
  let phaseNow = null;

  async function agent(prompt, opts = {}) {
    if (typeof prompt !== 'string') throw new Error('agent(): prompt must be a string');
    const key = keyOf(prompt, opts);
    const call = { key, prompt, opts, batch, phase: phaseNow, index: calls.length };
    calls.push(call);
    if (!opts.label) errors.push(`${key}: every ctx.agent call needs a label`);
    else if (labels[opts.label]) errors.push(`${key}: label '${opts.label}' used twice (identical calls are memoised)`);
    labels[opts.label] = true;
    if (opts.schema) {
      const s = opts.schema;
      const bad = [];
      if (s.type !== 'object' || !s.properties) bad.push(`${key}: schema root must be {type:'object', properties}`);
      for (const r of s.required || []) if (!(r in (s.properties || {}))) bad.push(`${key}: required ${r} not in properties`);
      for (const banned of ['$schema', '$id', 'title', 'description', 'x-contract-version']) {
        if (banned in s) bad.push(`${key}: schema still carries ${banned}`);
      }
      if (bad.length) {
        errors.push(...bad);
        throw new Error(bad.join('; '));
      }
    } else {
      errors.push(`${key}: ctx.agent called without a schema`);
    }
    let res;
    if (queues[key] && queues[key].length) res = queues[key].shift();
    else if (key in defaults) res = defaults[key];
    else {
      errors.push(`no scripted response for ${key}`);
      throw new Error(`no scripted response for ${key}`);
    }
    if (typeof res === 'function') res = res(prompt, opts, call);
    await Promise.resolve();
    if (res == null) {
      call.result = null;
      return null;
    }
    res = structuredClone(res);
    if (opts.schema) {
      const errs = validate(opts.schema, res);
      if (errs.length) {
        errors.push(`fixture for ${key} does not match its contract: ${errs.slice(0, 5).join('; ')}`);
        throw new Error(errors[errors.length - 1]);
      }
    }
    call.result = res;
    return res;
  }

  async function step(key, fn) {
    if (typeof key !== 'string' || !key) errors.push('ctx.step: key must be a non-empty string');
    if (stepKeys[key]) errors.push(`ctx.step: key '${key}' used twice in one run`);
    stepKeys[key] = true;
    const value = await fn();
    try {
      JSON.parse(JSON.stringify(value === undefined ? null : value));
    } catch (e) {
      errors.push(`ctx.step '${key}': value is not JSON-serialisable`);
    }
    steps.push({ key, value, phase: phaseNow });
    return value;
  }

  async function parallel(thunks) {
    const id = ++batchSeq;
    const prev = batch;
    batch = id;
    let promises;
    try {
      promises = thunks.map((t) => {
        try {
          return Promise.resolve(t());
        } catch (e) {
          return Promise.reject(e);
        }
      });
    } finally {
      batch = prev;
    }
    return Promise.all(promises.map((p) => p.then((v) => v, (e) => {
      logs.push(`parallel slot error: ${e && e.message}`);
      return null;
    })));
  }

  async function pipeline(items, ...stages) {
    return Promise.all(items.map(async (item, i) => {
      let v = item;
      for (const s of stages) {
        try {
          v = await s(v, item, i);
        } catch (e) {
          return null;
        }
      }
      return v;
    }));
  }

  async function pause(pauseName) {
    pauses.push({ name: pauseName, phase: phaseNow, index: calls.length });
    const scripted = options.pauses || {};
    for (const prefix of Object.keys(scripted)) {
      if (String(pauseName).startsWith(prefix)) {
        const v = scripted[prefix];
        return typeof v === 'function' ? v(pauseName) : v;
      }
    }
    return undefined;
  }

  function phase(title) {
    phaseNow = title;
    phases.push(title);
  }
  function log(msg) {
    logs.push(String(msg));
  }

  const fullArgs = options.noInputs ? Object.assign({}, args) : Object.assign({ registry: loadRegistry(), contracts: loadContracts() }, args);
  const ctx = { args: fullArgs, agent, step, parallel, pipeline, pause, phase, log, signal: new AbortController().signal };
  const result = await workflow.run(ctx);
  return { meta: workflow.meta, result, calls, phases, logs, errors, steps, pauses, unused: Object.fromEntries(Object.entries(queues).filter(([, q]) => q.length)) };
}

// ---------------------------------------------------------------------------------------------
// Fixture builders (valid against the contracts)
// ---------------------------------------------------------------------------------------------
export function counts(findings = []) {
  const c = { BLOCKING: 0, MAJOR: 0, MINOR: 0, NOTE: 0 };
  for (const f of findings) c[f.severity] += 1;
  return c;
}

export function finding(o = {}) {
  return Object.assign({
    id: 'code-001', severity: 'MINOR', category: 'clarity', location: 'src/cache/store.js:10-20',
    finding: 'Name hides intent', whyItMatters: 'Readers misread the eviction rule', evidence: 'src/cache/store.js:12',
    requiredResolution: 'Rename', confidence: 'HIGH', owner: 'implementer', reporters: ['code-reviewer'], status: 'OPEN',
  }, o);
}

export function reviewer(o = {}) {
  const findings = o.findings || [];
  return Object.assign({
    reviewer: 'code-reviewer', mode: 'SLICE', verdict: findings.some((f) => f.status === 'OPEN' && f.severity !== 'NOTE') ? 'CHANGES_REQUIRED' : 'PASS',
    findingsFile: '.ai/slices/01/findings/code-reviewer.md', counts: counts(findings), mostSerious: findings[0] ? findings[0].id : 'none',
    findings, extras: {}, abilityVersions: {}, humanInputRequested: null,
  }, o, { findings, counts: counts(findings) });
}

export function testPlanResult(o = {}) {
  return Object.assign({
    slice: '01', testPlanFile: '.ai/slices/01/TEST_PLAN.md',
    acCoverage: [{ ac: 'AC1', tests: ['tests/cache/store.test.js'], level: 'unit' }],
    acNotVerifiable: [], failureCases: ['empty cache'], benchmarks: [], tiers: [], humanInputRequested: null,
  }, o);
}

export function author(role, mode, o = {}) {
  return Object.assign({
    role, mode, slice: '01', round: 0, acSatisfied: ['AC1'], acNotSatisfied: [], filesChanged: [], commit: null,
    fixed: [], rebuttals: [], architectureConcerns: [], outOfScopeNoticed: [], stubsRemaining: [], build: 'PASS',
    humanInputRequested: null,
  }, o);
}

export function facts(o = {}) {
  const base = { productionCode: true, mechanicalOnly: false, publicContract: false, concurrency: false, consumerVisible: false, security: false, config: false };
  const merged = Object.assign(base, o);
  const out = {};
  for (const k of Object.keys(merged)) out[k] = { value: merged[k], evidence: `${k} evidence` };
  return out;
}

export function verifyResult(o = {}) {
  const { routing, ...rest } = o;
  return Object.assign({
    slice: '01', commit: 'abc1234', testPlanStatus: 'APPROVED', scopeCheck: 'IN_SCOPE', drift: [], build: 'PASS', staticAnalysis: 'PASS',
    unitTests: { status: 'PASS', run: 12, failures: 0 }, integrationTests: 'NOT_APPLICABLE', tiers: [],
    commandUsed: 'npm test', testsAdded: ['tests/cache/store.test.js'], acVerified: [{ ac: 'AC1', test: 'tests/cache/store.test.js' }],
    acNotVerified: [], invariantsChecked: ['INV-1'], failureScenarios: [], confidence: 'HIGH', confidenceReason: 'all planned tests pass',
    routingFacts: facts(routing || {}), humanInputRequested: null,
  }, rest);
}

export function rebuttalResponse(findingId, response, reason = 'checked') {
  return { findingId, response, reason };
}

export function architect(o = {}) {
  const findings = o.findings || [];
  return Object.assign({
    mode: 'DRAFT', verdict: 'SOUND', findingsFile: null, counts: counts(findings), findings, abstractionsChallenged: 0,
    abstractionsRejected: 0, invariantsChanged: 0, decisionRecord: null, humanInputRequested: null,
  }, o, { findings, counts: counts(findings) });
}

export function discovery(mode, o = {}) {
  return Object.assign({ mode, artifactsWritten: [`.ai/planning/${mode.toLowerCase()}.md`], couldNotInspect: [], humanInputRequested: null }, o);
}

export function goldfish(o = {}) {
  return Object.assign({ mode: 'BRAINSTORM', lens: 'technical', concepts: [], readiness: 'NOT_APPLICABLE', questions: [] }, o);
}

export function planner(o = {}) {
  return Object.assign({
    mode: 'PLAN', slices: 2, orderingRationale: 'walking skeleton first', largestSlice: '02', consumerMigrationOrder: [],
    risks: [], verdict: 'PLANNED', exceptionRequests: [], humanInputRequested: null,
  }, o);
}

/** Defaults for a clean slice run: every reviewer passes, every author succeeds. */
export function sliceDefaults() {
  const d = {
    'verifier|TEST_PLAN': testPlanResult(),
    'code-reviewer|TEST_PLAN': reviewer({ mode: 'TEST_PLAN', verdict: 'APPROVE', extras: { testPlanStatus: 'APPROVED' } }),
    'implementer|IMPLEMENT': author('implementer', 'IMPLEMENT', { commit: 'c0de' }),
    'verifier|WRITE_TESTS': author('verifier', 'WRITE_TESTS'),
    'verifier|VERIFY': verifyResult(),
    'implementer|FIX': author('implementer', 'FIX'),
    'verifier|FIX_TESTS': author('verifier', 'FIX_TESTS'),
    'architect|ADJUDICATE': architect({ mode: 'ADJUDICATE', verdict: 'RESOLVED' }),
  };
  for (const r of ['code', 'security', 'contract', 'integration', 'reliability', 'simplicity']) {
    d[`${r}-reviewer|SLICE`] = reviewer({ reviewer: `${r}-reviewer`, mode: 'SLICE' });
    d[`${r}-reviewer|RECHECK`] = reviewer({ reviewer: `${r}-reviewer`, mode: 'RECHECK' });
    d[`${r}-reviewer|PLAN`] = reviewer({ reviewer: `${r}-reviewer`, mode: 'PLAN' });
    d[`${r}-reviewer|REBUTTAL`] = (prompt) => rebuttalResponse(/finding (\S+)\./.exec(prompt)[1], 'MAINTAIN_FINDING');
  }
  return d;
}

export const SLICE_ARGS = { slice: '01', featureBranch: 'feature/demo', sliceBranch: 'feature/demo-slice-01', round: 0, sharedApproved: [] };

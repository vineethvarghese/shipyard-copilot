import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { loadMeta, loadWorkflow, workflowSource, loadRegistry, loadContracts, EXTENSIONS_DIR, validate } from './harness.mjs';
import {
  brief, schemaFor, agentOptions, agentPreamble, copilotAgentName, shortAgentName, routePlan, routeSlice,
  dedupePlanFindings, dedupeSliceFindings, defineWorkflow, loadInputs, attach,
} from '../../../.github/extensions/shipyard-lib/index.mjs';

const WORKFLOWS = ['discover', 'plan', 'slice'];
const FORBIDDEN = [
  [/\bDate\s*\.\s*now\s*\(/, 'Date.now'], [/\bMath\s*\.\s*random\s*\(/, 'Math.random'], [/\bnew\s+Date\s*\(/, 'new Date()'],
  [/\bprocess\s*\.\s*env\b/, 'process.env'], [/\bfetch\s*\(/, 'fetch'], [/['"]node:(fs|child_process|http|https|net)['"]/, 'node builtin'],
  [/\brequire\s*\(/, 'require()'],
];

function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:\\])\/\/[^\n]*/g, '$1');
}

for (const name of WORKFLOWS) {
  test(`${name}: extension.mjs exports workflow = defineWorkflow({ meta, run }) with argsSchema, phases and limits`, async () => {
    const wf = await loadWorkflow(name);
    const meta = await loadMeta(name);
    assert.equal(meta.name, `shipyard-${name}`, 'meta.name equals the folder name (copilot workflow run <name>)');
    assert.equal(typeof meta.description, 'string');
    assert.ok(meta.description.length > 40);
    assert.ok(Array.isArray(meta.phases) && meta.phases.length > 0);
    for (const p of meta.phases) assert.ok(p.title && p.detail);
    assert.equal(meta.argsSchema.type, 'object');
    assert.ok(meta.argsSchema.properties && Array.isArray(meta.argsSchema.required));
    for (const r of meta.argsSchema.required) assert.ok(r in meta.argsSchema.properties, `required ${r} declared`);
    for (const k of ['registry', 'contracts', 'agentSelection', 'shipyardDir']) assert.ok(k in meta.argsSchema.properties, `argsSchema has ${k}`);
    assert.ok(Number.isInteger(meta.limits.maxConcurrentSubagents) && Number.isInteger(meta.limits.maxTotalSubagents));
    assert.equal(typeof wf.run, 'function');
    const src = workflowSource(name);
    assert.match(src, /^import \{[^}]*\bdefineWorkflow\b[^}]*\} from '\.\.\/shipyard-lib\/index\.mjs';/m);
    assert.match(src, /^export const workflow = defineWorkflow\(\{ meta, run \}\);/m);
    assert.match(src, /^export default workflow;/m);
    assert.match(src, /^await attach\(workflow\);/m);
  });

  test(`${name}: meta.phases titles equal the enter() titles used`, async () => {
    const src = workflowSource(name);
    const used = new Set([...src.matchAll(/\benter\('([^']+)'\)/g)].map((m) => m[1]));
    const declared = new Set((await loadMeta(name)).phases.map((p) => p.title));
    assert.deepEqual([...used].sort(), [...declared].sort());
  });

  test(`${name}: plain JavaScript with no forbidden APIs and no hard-coded agent names`, () => {
    const body = stripComments(workflowSource(name));
    for (const [re, label] of FORBIDDEN) assert.doesNotMatch(body, re, label);
    assert.doesNotMatch(body, /shipyard[:-](?!coordinator|lib|discover|plan|slice)[a-z-]+/, 'agent names come from the registry, not the script');
    const imports = [...body.matchAll(/^import [^;]* from '([^']+)';/gm)].map((m) => m[1]);
    assert.deepEqual(imports, ['../shipyard-lib/index.mjs'], 'the only import is the shared lib');
  });

  test(`${name}: every role used by the workflow exists in the registry`, () => {
    const reg = loadRegistry();
    const src = workflowSource(name);
    const roles = [...src.matchAll(/call\('([a-z-]+)'/g)].map((m) => m[1]);
    assert.ok(roles.length > 0);
    for (const r of roles) assert.ok(reg.roles[r], `${name}: role ${r}`);
  });
}

test('shipyard-lib: no clock, randomness or network; fs is read-only', () => {
  const body = stripComments(readFileSync(join(EXTENSIONS_DIR, 'shipyard-lib', 'index.mjs'), 'utf8'));
  for (const [re, label] of FORBIDDEN.filter(([, l]) => l !== 'node builtin')) assert.doesNotMatch(body, re, label);
  assert.doesNotMatch(body, /['"]node:(child_process|http|https|net)['"]/);
  assert.doesNotMatch(body, /\bwriteFileSync|\bwriteFile\b|\bmkdirSync|\bunlinkSync|\brmSync/);
});

test('attach() returns false when the Copilot SDK is absent (plain Node), and the workflow still loads', async () => {
  const wf = await loadWorkflow('discover');
  assert.equal(await attach(wf), false);
});

test('defineWorkflow checks the definition shape', () => {
  const run = async () => ({});
  assert.throws(() => defineWorkflow({ meta: { name: 'x' }, run }), /description/);
  assert.throws(() => defineWorkflow({ meta: { name: 'x', description: 'd', phases: [] }, run }), /phases/);
  assert.throws(() => defineWorkflow({ meta: { name: 'x', description: 'd', phases: [{ title: 'A' }] } }), /run\(ctx\)/);
  const def = defineWorkflow({ meta: { name: 'x', description: 'd', phases: [{ title: 'A' }] }, run });
  assert.equal(def.run, run);
});

test('brief(): the header lines are the Shipyard ones, in order', () => {
  const text = brief({ mode: 'SLICE', slice: '01', round: 2, featureBranch: 'f', sliceBranch: 's', diff: true, read: ['a', 'b'], write: ['w'], budgetTurns: 5, text: 'Body.' });
  assert.equal(text, 'Caller: shipyard:coordinator\nMode: SLICE\nSlice: 01\nRound: 2\nFeature-branch: f\nSlice-branch: s\nDiff: git diff f...s\nRead: a, b\nWrite: w\nBudget: 5 turns\n\nBody.\n');
  assert.equal(brief({ mode: 'SCAN' }), 'Caller: shipyard:coordinator\nMode: SCAN\n');
});

test('agent names: both registry prefixes map to shipyard-<short>', () => {
  assert.equal(shortAgentName('shipyard:code-reviewer'), 'code-reviewer');
  assert.equal(shortAgentName('shipyard-code-reviewer'), 'code-reviewer');
  assert.equal(copilotAgentName('shipyard:goldfish'), 'shipyard-goldfish');
  assert.equal(copilotAgentName('shipyard-goldfish'), 'shipyard-goldfish');
  assert.match(agentPreamble('shipyard-goldfish'), /^Act as `shipyard-goldfish`: read \.github\/agents\/shipyard-goldfish\.agent\.md/);
});

test('agentOptions(): "agent" selection passes agent, model and reasoningEffort; "prompt" passes nothing', () => {
  const reg = loadRegistry();
  assert.deepEqual(agentOptions(reg, 'verifier', 'VERIFY', 'agent'), { agent: 'shipyard-verifier', model: 'sonnet', reasoningEffort: 'medium' });
  assert.deepEqual(agentOptions(reg, 'architect', 'DRAFT'), { agent: 'shipyard-architect', model: 'opus', reasoningEffort: 'high' });
  assert.deepEqual(agentOptions(reg, 'architect', 'DRAFT', 'prompt'), {});
  assert.throws(() => agentOptions(reg, 'architect', 'NOPE'), /has no mode 'NOPE'/);
  assert.throws(() => agentOptions(reg, 'nobody', 'DRAFT'), /not in the registry/);
});

test('schemaFor(): strips metadata keys and checks the major version', () => {
  const contracts = loadContracts();
  const s = schemaFor(contracts, 'verify-result@2');
  for (const k of ['$schema', '$id', 'title', 'description', 'x-contract-version']) assert.ok(!(k in s));
  assert.equal(s.type, 'object');
  assert.throws(() => schemaFor(contracts, 'verify-result@1'), /major version mismatch/);
  assert.throws(() => schemaFor(contracts, 'verify-result'), /bad contract reference/);
  assert.throws(() => schemaFor(contracts, 'nothing@1'), /missing from args\.contracts/);
});

test('validate(): the full subset the runtime does not enforce', () => {
  const schema = {
    type: 'object', required: ['a'], additionalProperties: false,
    properties: {
      a: { type: 'string', minLength: 2, maxLength: 4 },
      n: { type: ['integer', 'null'], minimum: 1, maximum: 3 },
      e: { enum: ['x', 'y'] },
      c: { const: 7 },
      l: { type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 2 },
      any: { anyOf: [{ type: 'string' }, { type: 'integer' }] },
      one: { oneOf: [{ type: 'string' }, { type: 'integer' }] },
    },
  };
  assert.deepEqual(validate(schema, { a: 'ab', n: null, e: 'x', c: 7, l: ['s'], any: 1, one: 's' }), []);
  const errs = validate(schema, { a: 'a', n: 0, e: 'z', c: 8, l: [], any: true, one: null, extra: 1 });
  for (const frag of ['$.a: shorter', '$.n: below', '$.e: "z" not in enum', '$.c: 8 is not the constant', '$.l: fewer than', '$.any: matches none', '$.one: must match exactly one', 'unexpected property extra']) {
    assert.ok(errs.some((e) => e.includes(frag)), `${frag} in ${errs.join(' | ')}`);
  }
  assert.deepEqual(validate(schema, { a: 'ab', n: 2.5 }), ['$.n: expected integer|null, got number']);
  assert.deepEqual(validate(schema, { a: 'abcde' }), ['$.a: longer than 4']);
  assert.deepEqual(validate(schema, {}), ['$: missing a']);
  assert.deepEqual(validate({ type: 'object' }, []), ['$: expected object, got array']);
  assert.deepEqual(validate({ type: 'number' }, 3), []);
});

test('routePlan(): always, true and uncertain route; false does not', () => {
  const reg = loadRegistry();
  const r = routePlan(reg, { publicContract: false, consumerVisible: false, concurrency: false, security: true, config: false, modelChecked: false });
  assert.deepEqual(r.routed.map((x) => x.role), ['architect', 'simplicity-review', 'security-review']);
  assert.ok(r.notRouted.some((x) => x.role === 'contract-review' && /publicContract=false, config=false/.test(x.because)));
  const u = routePlan(reg, {});
  assert.equal(u.routed.length, 6);
  assert.ok(u.routed.some((x) => x.role === 'reliability-review' && /concurrency=uncertain/.test(x.because)));
});

test('routeSlice(): when/unless with evidence; uncertain routes', () => {
  const reg = loadRegistry();
  const facts = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, { value: v, evidence: `${k} ev` }]));
  const r = routeSlice(reg, facts({ productionCode: true, mechanicalOnly: true, publicContract: false, config: false, consumerVisible: false, concurrency: false, security: false }));
  assert.deepEqual(r.routed.map((x) => x.role), ['code-review']);
  assert.ok(r.skipped.some((x) => x.role === 'simplicity-review' && /not routed: mechanicalOnly=true \(mechanicalOnly ev\)/.test(x.because)));
  const u = routeSlice(reg, facts({ productionCode: true, mechanicalOnly: false }));
  assert.ok(u.routed.some((x) => x.role === 'security-review' && /security=uncertain \(flag missing or uncertain\)/.test(x.because)));
  // plain booleans are accepted too
  const b = routeSlice(reg, { productionCode: true, mechanicalOnly: false, security: true, publicContract: false, config: false, consumerVisible: false, concurrency: false });
  assert.deepEqual(b.routed.map((x) => x.role), ['code-review', 'simplicity-review', 'security-review']);
});

test('dedupe: plan merges per site; slice never merges one reviewer with itself and keeps member keys', () => {
  const f = (id, reporter, sev = 'MINOR', status = 'OPEN') => ({ id, severity: sev, category: 'design', location: 'src/a.js:1', reporters: [reporter], status });
  const plan = dedupePlanFindings([f('a', 'code-review'), f('b', 'simplicity-review', 'MAJOR', 'FIXED')]);
  assert.equal(plan.length, 1);
  assert.deepEqual([plan[0].id, plan[0].severity, plan[0].status, plan[0].reporters], ['b', 'MAJOR', 'OPEN', ['simplicity-review', 'code-review']]);
  const slice = dedupeSliceFindings([f('a', 'code-review'), f('b', 'code-review'), f('c', 'simplicity-review', 'MAJOR')]);
  assert.equal(slice.length, 2);
  const merged = slice.find((x) => x.reporters.length === 2);
  assert.deepEqual(merged.memberKeys, ['code-review:a', 'simplicity-review:c']);
  assert.equal(merged.severity, 'MAJOR');
  assert.ok(slice.some((x) => x.memberKeys.length === 1 && x.id === 'b'));
});

test('loadInputs(): args win; files are the fallback; absence fails loudly', () => {
  const reg = loadRegistry();
  const own = { roles: { x: {} }, computeClasses: {} };
  assert.equal(loadInputs({ registry: own, contracts: {} }, 't').registry, own);
  const fromFiles = loadInputs({}, 't');
  assert.deepEqual(Object.keys(fromFiles.registry.roles), Object.keys(reg.roles));
  assert.ok(fromFiles.contracts['slice-workflow-result']);
  assert.throws(() => loadInputs({ shipyardDir: 'does-not-exist' }, 't'), /args\.registry .* could not read/);
  assert.throws(() => loadInputs({ registry: {}, contracts: {} }, 't'), /args\.registry/);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runWorkflow, reviewer, architect, planner, goldfish, finding, sliceDefaults, loadContracts, validate } from './harness.mjs';

const NO_FLAGS = { publicContract: false, consumerVisible: false, concurrency: false, security: false, config: false, modelChecked: false };
const contracts = loadContracts();

function strip(schema) {
  const out = { ...schema };
  for (const k of ['$schema', '$id', 'title', 'description', 'x-contract-version']) delete out[k];
  return out;
}

function defaults() {
  return Object.assign(sliceDefaults(), {
    'architect|CRITIQUE': architect({ mode: 'CRITIQUE', verdict: 'SOUND' }),
    'architect|DRAFT': architect({ mode: 'DRAFT', verdict: 'SOUND' }),
    'planner|PLAN': planner({ slices: 2 }),
    'planner|REPLAN': planner({ mode: 'REPLAN', slices: 2 }),
    'goldfish|READINESS': goldfish({ mode: 'READINESS', lens: 'readiness', readiness: 'READY' }),
  });
}

async function runPlan(args, script = {}, extra = {}) {
  const run = await runWorkflow('plan', { planFlags: NO_FLAGS, cycle: 0, answers: { G1: '60s' }, ...args }, script, { ...defaults(), ...extra });
  assert.deepEqual(run.errors, [], run.errors.join('\n'));
  const errs = validate(strip(contracts['plan-workflow-result']), run.result);
  assert.deepEqual(errs, [], `result does not match plan-workflow-result: ${errs.join('; ')}`);
  return run;
}

const critique = (run) => run.calls.filter((c) => c.phase === 'Critique').map((c) => c.key).sort();

test('happy path → AWAITING_PLAN_APPROVAL with slices 01..NN', async () => {
  const run = await runPlan({});
  assert.equal(run.result.status, 'AWAITING_PLAN_APPROVAL');
  assert.deepEqual(run.result.slices, ['01', '02']);
  assert.deepEqual(run.result.readiness.map((r) => r.readiness), ['READY', 'READY']);
  assert.deepEqual(critique(run), ['architect|CRITIQUE', 'simplicity-reviewer|PLAN']);
  const plan = run.calls.find((c) => c.key === 'planner|PLAN');
  assert.match(plan.prompt, /two-digit sequential slice ids 01\.\.NN/);
  assert.match(plan.prompt, /## Seams under test/);
  assert.match(plan.prompt, /## Prior art/);
  assert.match(plan.prompt, /Formal rigour \(C-10\): none/);
  assert.match(plan.prompt, /^Read: .*\.ai\/GLOSSARY\.md/m);
  assert.equal(plan.opts.agent, 'shipyard-planner');
  const ready = run.calls.filter((c) => c.key === 'goldfish|READINESS');
  assert.deepEqual(ready.map((c) => /^Read: (.*)$/m.exec(c.prompt)[1]), ['.ai/slices/01/SLICE.md', '.ai/slices/02/SLICE.md']);
  const integ = run.calls.find((c) => c.key === 'integration-reviewer|PLAN' && c.phase === 'Delivery plan');
  assert.match(integ.prompt, /Sequencing and mergeability only/);
  const arch = run.calls.find((c) => c.key === 'architect|CRITIQUE' && c.phase === 'Delivery plan');
  assert.match(arch.prompt, /Intermediate states only/);
  assert.equal(integ.batch, arch.batch);
  assert.equal(ready[0].batch, integ.batch);
  const simp = run.calls.find((c) => c.key === 'simplicity-reviewer|PLAN');
  assert.match(simp.prompt, /At most 15 findings/);
  assert.match(simp.prompt, /^Write: \.ai\/planning\/simplicity-reviewer\.md$/m);
  assert.match(simp.prompt, /60s/);
  // deterministic routing and slice ids are journaled steps
  const route = run.steps.find((s) => s.key === 'route plan reviewers');
  assert.deepEqual(route.value.routed.map((r) => r.role), ['architect', 'simplicity-review']);
  assert.deepEqual(run.steps.find((s) => s.key === 'slice ids').value, ['01', '02']);
  assert.deepEqual(run.phases, ['Critique', 'Delivery plan']);
});

test('plan routes security when planFlags.security', async () => {
  const run = await runPlan({ planFlags: { ...NO_FLAGS, security: true } });
  assert.deepEqual(critique(run), ['architect|CRITIQUE', 'security-reviewer|PLAN', 'simplicity-reviewer|PLAN']);
  assert.ok(run.result.reviewersRouted.some((r) => r.role === 'security-review' && /security=true/.test(r.because)));
  assert.ok(run.result.reviewersNotRouted.some((r) => r.role === 'contract-review'));
});

test('modelChecked routes the reliability reviewer and tells it to run the models', async () => {
  const run = await runPlan({ planFlags: { ...NO_FLAGS, modelChecked: true }, formalRigour: 'model-checked' });
  assert.deepEqual(critique(run), ['architect|CRITIQUE', 'reliability-reviewer|PLAN', 'simplicity-reviewer|PLAN']);
  assert.ok(run.result.reviewersRouted.some((r) => r.role === 'reliability-review' && /modelChecked=true/.test(r.because)));
  const rel = run.calls.find((c) => c.key === 'reliability-reviewer|PLAN');
  assert.match(rel.prompt, /formal_check\.py/);
  assert.match(rel.prompt, /planted fault must fail/);
  const simp = run.calls.find((c) => c.key === 'simplicity-reviewer|PLAN');
  assert.match(simp.prompt, /Formal rigour \(C-10\): model-checked/);
  assert.doesNotMatch(simp.prompt, /formal_check\.py/);
  await assert.rejects(runWorkflow('plan', { planFlags: NO_FLAGS, formalRigour: 'proofs' }, {}, {}), /formalRigour must be one of/);
});

test('absent or uncertain plan flags → route', async () => {
  const run = await runPlan({ planFlags: { concurrency: 'unsure' } });
  assert.deepEqual(critique(run), [
    'architect|CRITIQUE', 'contract-reviewer|PLAN', 'integration-reviewer|PLAN', 'reliability-reviewer|PLAN', 'security-reviewer|PLAN', 'simplicity-reviewer|PLAN',
  ]);
});

test('human input requested in critique → NEEDS_HUMAN, no delivery planning', async () => {
  const hir = { question: 'Keep the old API?', evidence: 'CONSUMERS.md', recommendation: 'yes', blocked: 'migration order' };
  const run = await runPlan({}, { 'simplicity-reviewer|PLAN': [reviewer({ mode: 'PLAN', humanInputRequested: hir })] });
  assert.equal(run.result.status, 'NEEDS_HUMAN');
  assert.equal(run.result.humanInputRequests[0].question, 'Keep the old API?');
  assert.equal(run.calls.filter((c) => c.key.startsWith('planner')).length, 0);
});

test('open findings → architect DRAFT then only the reporting reviewer rechecks', async () => {
  const f = finding({ id: 'simp-001', severity: 'MAJOR', location: '.ai/ARCHITECTURE.md', category: 'abstraction' });
  const run = await runPlan({}, {
    'simplicity-reviewer|PLAN': [reviewer({ mode: 'PLAN', findings: [f] })],
    'simplicity-reviewer|RECHECK': [reviewer({ mode: 'RECHECK', findings: [{ ...f, status: 'FIXED' }] })],
  });
  assert.equal(run.result.status, 'AWAITING_PLAN_APPROVAL');
  const refine = run.calls.filter((c) => c.phase === 'Refine').map((c) => c.key);
  assert.deepEqual(refine, ['architect|DRAFT', 'simplicity-reviewer|RECHECK']);
  assert.match(run.calls.find((c) => c.key === 'architect|DRAFT').prompt, /simp-001/);
  assert.match(run.calls.find((c) => c.key === 'simplicity-reviewer|RECHECK').prompt, /simp-001/);
});

test('findings still open after the refine cap → NEEDS_HUMAN with them', async () => {
  const f = finding({ id: 'simp-001', severity: 'MINOR', location: '.ai/ARCHITECTURE.md', category: 'abstraction' });
  const run = await runPlan({}, {}, {
    'simplicity-reviewer|PLAN': reviewer({ mode: 'PLAN', findings: [f] }),
    'simplicity-reviewer|RECHECK': reviewer({ mode: 'RECHECK', findings: [f] }),
  });
  assert.equal(run.result.status, 'NEEDS_HUMAN');
  assert.equal(run.result.openFindings.length, 1);
  assert.equal(run.calls.filter((c) => c.key === 'architect|DRAFT').length, 2);
  assert.equal(run.result.cyclesUsed, 2);
  // two refine cycles → two distinct journal entries, never a replayed key
  assert.deepEqual(run.steps.filter((s) => /^findings after refine/.test(s.key)).map((s) => s.key), ['findings after refine 1', 'findings after refine 2']);
});

test('refine cap counts across launches: cycle 1 leaves one refine cycle, cycle 2 none', async () => {
  const f = finding({ id: 'simp-001', severity: 'MINOR', location: '.ai/ARCHITECTURE.md', category: 'abstraction' });
  const extra = {
    'simplicity-reviewer|PLAN': reviewer({ mode: 'PLAN', findings: [f] }),
    'simplicity-reviewer|RECHECK': reviewer({ mode: 'RECHECK', findings: [f] }),
  };
  const one = await runPlan({ cycle: 1 }, {}, extra);
  assert.equal(one.calls.filter((c) => c.key === 'architect|DRAFT').length, 1);
  assert.equal(one.result.cyclesUsed, 2);
  const none = await runPlan({ cycle: 2 }, {}, extra);
  assert.equal(none.result.status, 'NEEDS_HUMAN');
  assert.equal(none.calls.filter((c) => c.key === 'architect|DRAFT').length, 0);
});

test('NOT_READY slice → one REPLAN, then that slice is rechecked once', async () => {
  const notReady = goldfish({ mode: 'READINESS', lens: 'readiness', readiness: 'NOT_READY', questions: ['Which table holds prices?'] });
  const run = await runPlan({}, { 'goldfish|READINESS': [goldfish({ mode: 'READINESS', lens: 'readiness', readiness: 'READY' }), notReady] });
  assert.equal(run.result.status, 'AWAITING_PLAN_APPROVAL');
  const replan = run.calls.find((c) => c.key === 'planner|REPLAN');
  assert.match(replan.prompt, /Which table holds prices\?/);
  const ready = run.calls.filter((c) => c.key === 'goldfish|READINESS');
  assert.equal(ready.length, 3);
  assert.match(ready[2].prompt, /\.ai\/slices\/02\/SLICE\.md/);
  assert.deepEqual(run.steps.find((s) => s.key === 'replan recheck set').value, ['02']);
});

test('still NOT_READY after the replan → NEEDS_HUMAN', async () => {
  const notReady = goldfish({ mode: 'READINESS', lens: 'readiness', readiness: 'NOT_READY', questions: ['Which table?'] });
  const run = await runPlan({}, {}, { 'goldfish|READINESS': notReady });
  assert.equal(run.result.status, 'NEEDS_HUMAN');
  assert.equal(run.calls.filter((c) => c.key === 'planner|REPLAN').length, 1);
  assert.ok(run.result.humanInputRequests.some((h) => h.question === 'Which table?'));
});

test('a replan that adds a slice rechecks the new slice', async () => {
  const notReady = goldfish({ mode: 'READINESS', lens: 'readiness', readiness: 'NOT_READY', questions: ['Split?'] });
  const run = await runPlan({}, {
    'goldfish|READINESS': [goldfish({ mode: 'READINESS', lens: 'readiness', readiness: 'READY' }), notReady],
    'planner|REPLAN': [planner({ mode: 'REPLAN', slices: 3 })],
  });
  assert.equal(run.result.status, 'AWAITING_PLAN_APPROVAL');
  assert.deepEqual(run.result.slices, ['01', '02', '03']);
  assert.deepEqual(run.steps.find((s) => s.key === 'replan recheck set').value, ['02', '03']);
  assert.deepEqual(run.result.readiness.map((r) => r.readiness), ['READY', 'READY', 'READY']);
});

test('planner null after retry → BLOCKED', async () => {
  const run = await runPlan({}, { 'planner|PLAN': [null, null] });
  assert.equal(run.result.status, 'BLOCKED');
  assert.match(run.result.reason, /planner PLAN/);
});

test('a sequencing finding → one REPLAN, then only that reviewer rechecks', async () => {
  const f = finding({ id: 'integ-001', severity: 'MAJOR', location: '.ai/DELIVERY_PLAN.md', category: 'sequencing', reporters: ['integration-reviewer'] });
  const run = await runPlan({}, {
    'integration-reviewer|PLAN': [reviewer({ reviewer: 'integration-reviewer', mode: 'PLAN', findings: [f] }), reviewer({ reviewer: 'integration-reviewer', mode: 'PLAN', findings: [{ ...f, status: 'FIXED' }] })],
  });
  assert.equal(run.result.status, 'AWAITING_PLAN_APPROVAL');
  const integ = run.calls.filter((c) => c.key === 'integration-reviewer|PLAN');
  assert.equal(integ.length, 2);
  assert.match(integ[1].prompt, /Recheck your open findings after the replan/);
  assert.match(integ[1].prompt, /integ-001/);
  assert.equal(run.calls.filter((c) => c.key === 'architect|CRITIQUE').length, 2); // critique + delivery, no recheck
  assert.equal(run.calls.filter((c) => c.key === 'goldfish|READINESS').length, 2); // nothing NOT_READY → no readiness recheck
});

test('an open plan finding left out of a recheck stays OPEN', async () => {
  const f = finding({ id: 'simp-001', severity: 'MINOR', location: '.ai/ARCHITECTURE.md', category: 'abstraction' });
  const run = await runPlan({}, {}, {
    'simplicity-reviewer|PLAN': reviewer({ mode: 'PLAN', findings: [f] }),
    'simplicity-reviewer|RECHECK': reviewer({ mode: 'RECHECK', findings: [] }),
  });
  assert.equal(run.result.status, 'NEEDS_HUMAN');
  assert.equal(run.result.openFindings[0].id, 'simp-001');
});

test('plan dedupe merges the same site from two reviewers and keeps the highest severity', async () => {
  const a = finding({ id: 'simp-001', severity: 'MINOR', location: '.ai/ARCHITECTURE.md', category: 'design', reporters: ['simplicity-reviewer'] });
  const b = finding({ id: 'arch-001', severity: 'MAJOR', location: '.ai/ARCHITECTURE.md ', category: 'Design', reporters: ['architect'] });
  const run = await runPlan({}, {
    'simplicity-reviewer|PLAN': [reviewer({ mode: 'PLAN', findings: [a] })],
    'architect|CRITIQUE': [architect({ mode: 'CRITIQUE', verdict: 'NEEDS_CHANGES', findings: [b] })],
    'simplicity-reviewer|RECHECK': [reviewer({ mode: 'RECHECK', findings: [{ ...a, status: 'FIXED' }] })],
  });
  // the architect's recheck (CRITIQUE mode, default fixture: no findings) leaves arch-001 out → it stays OPEN
  assert.equal(run.result.status, 'NEEDS_HUMAN');
  assert.equal(run.result.findings.length, 1);
  const merged = run.result.findings[0];
  assert.equal(merged.severity, 'MAJOR');
  assert.equal(merged.status, 'OPEN');
  assert.deepEqual(merged.reporters.slice().sort(), ['architect', 'simplicity-review']);
  assert.equal(run.result.openFindings[0].id, 'arch-001');
  const rechecks = run.calls.filter((c) => c.phase === 'Refine' && c.key === 'architect|CRITIQUE');
  assert.equal(rechecks.length, 2);
  assert.match(rechecks[0].prompt, /Recheck your open findings/);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  runWorkflow, sliceDefaults, SLICE_ARGS, reviewer, finding, author, verifyResult, rebuttalResponse, architect,
  testPlanResult, loadContracts, validate,
} from './harness.mjs';

const contracts = loadContracts();

function strip(schema) {
  const out = { ...schema };
  for (const k of ['$schema', '$id', 'title', 'description', 'x-contract-version']) delete out[k];
  return out;
}

async function runSlice(script = {}, defaults = {}, args = {}, options = {}) {
  const run = await runWorkflow('slice', { ...SLICE_ARGS, ...args }, script, { ...sliceDefaults(), ...defaults }, options);
  assert.deepEqual(run.errors, [], `harness errors: ${run.errors.join('\n')}`);
  const errs = validate(strip(contracts['slice-workflow-result']), run.result);
  assert.deepEqual(errs, [], `result does not match slice-workflow-result: ${errs.join('; ')}`);
  return run;
}

const keys = (run) => run.calls.map((c) => c.key);
const count = (run, key) => run.calls.filter((c) => c.key === key).length;

test('happy path → READY_FOR_HUMAN with evidence', async () => {
  const run = await runSlice();
  const r = run.result;
  assert.equal(r.status, 'READY_FOR_HUMAN');
  assert.equal(r.rounds, 0);
  assert.equal(r.commit, 'abc1234');
  assert.equal(r.verify.commit, 'abc1234');
  assert.ok(r.testPlan);
  assert.deepEqual(r.reviewersRouted.map((x) => x.role).sort(), ['code-review', 'simplicity-review']);
  assert.ok(r.reviewersNotRouted.some((x) => x.role === 'security-review' && /security=false/.test(x.because)));
  assert.deepEqual(r.openFindings, []);
  // every brief carries the shared header; every call names its custom agent and compute class
  for (const c of run.calls) {
    assert.match(c.prompt, /^Caller: shipyard:coordinator\nMode: [A-Z_]+\nSlice: 01\nRound: \d+\nFeature-branch: feature\/demo\nSlice-branch: feature\/demo-slice-01\n/);
    assert.match(c.prompt, /^Budget: \d+ turns$/m);
    assert.ok(c.opts.model && c.opts.reasoningEffort && c.opts.agent.startsWith('shipyard-'));
    assert.ok(c.opts.label && c.opts.schema);
  }
  const review = run.calls.find((c) => c.key === 'code-reviewer|SLICE');
  assert.match(review.prompt, /^Diff: git diff feature\/demo\.\.\.feature\/demo-slice-01$/m);
  assert.match(review.prompt, /^Read: \.ai\/slices\/01\/SLICE\.md, \.ai\/slices\/01\/TEST_PLAN\.md, \.ai\/INVARIANTS\.md, \.ai\/ARCHITECTURE\.md$/m);
  assert.match(review.prompt, /^Write: \.ai\/slices\/01\/findings\/code-reviewer\.md$/m);
  assert.equal(review.opts.model, 'claude-opus-5.5');
  assert.equal(review.opts.reasoningEffort, 'high');
  assert.equal(review.opts.agent, 'shipyard-code-reviewer');
  const verify = run.calls.find((c) => c.key === 'verifier|VERIFY');
  assert.equal(verify.opts.model, 'claude-sonnet-5.5');
  const tpReview = run.calls.find((c) => c.key === 'code-reviewer|TEST_PLAN');
  assert.match(tpReview.prompt, /^Write: \.ai\/slices\/01\/findings\/code-reviewer\.test-plan\.md$/m);
  assert.match(tpReview.prompt, /Status: DRAFT/);
  assert.match(tpReview.prompt, /Status: APPROVED/);
  assert.deepEqual(run.phases, ['Test plan', 'Build', 'Verify', 'Review']);
  assert.deepEqual(run.pauses, []);
  // deterministic routing is a journaled step
  const route = run.steps.find((s) => s.key === 'route reviewers round 0');
  assert.deepEqual(route.value.routed.map((x) => x.role), ['code-review', 'simplicity-review']);
});

test('test plan REVISE beyond the cap → ESCALATE, nothing built', async () => {
  const revise = reviewer({ mode: 'TEST_PLAN', verdict: 'REVISE', findings: [finding({ id: 'code-001', owner: 'verifier', category: 'test-plan', location: '.ai/slices/01/TEST_PLAN.md' })] });
  const run = await runSlice({}, { 'code-reviewer|TEST_PLAN': revise });
  assert.equal(run.result.status, 'ESCALATE');
  assert.match(run.result.reason, /test plan not approved after 2 revision/);
  assert.equal(count(run, 'verifier|TEST_PLAN'), 3);
  assert.equal(count(run, 'code-reviewer|TEST_PLAN'), 3);
  assert.equal(count(run, 'implementer|IMPLEMENT'), 0);
  assert.equal(count(run, 'verifier|WRITE_TESTS'), 0);
  assert.equal(run.result.openFindings.length, 1);
  const second = run.calls.filter((c) => c.key === 'verifier|TEST_PLAN')[1];
  assert.match(second.prompt, /Revision 1 of at most 2/);
});

test('test plan approved on a revision → continues', async () => {
  const revise = reviewer({ mode: 'TEST_PLAN', verdict: 'REVISE', findings: [finding({ owner: 'verifier', category: 'test-plan' })] });
  const run = await runSlice({ 'code-reviewer|TEST_PLAN': [revise] });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  assert.equal(count(run, 'verifier|TEST_PLAN'), 2);
});

test('implementer and verifier run only after TEST_PLAN APPROVE, in the same parallel batch', async () => {
  const run = await runSlice();
  const approve = run.calls.findIndex((c) => c.key === 'code-reviewer|TEST_PLAN' && c.result && c.result.verdict === 'APPROVE');
  const impl = run.calls.find((c) => c.key === 'implementer|IMPLEMENT');
  const tests = run.calls.find((c) => c.key === 'verifier|WRITE_TESTS');
  assert.ok(approve >= 0);
  assert.ok(impl.index > approve && tests.index > approve);
  assert.ok(impl.batch != null);
  assert.equal(impl.batch, tests.batch);
  assert.equal(impl.phase, 'Build');
  const firstVerify = run.calls.findIndex((c) => c.key === 'verifier|VERIFY');
  assert.ok(firstVerify > impl.index && firstVerify > tests.index);
});

test('concurrency flag → reliability routed', async () => {
  const run = await runSlice({}, { 'verifier|VERIFY': verifyResult({ routing: { concurrency: true } }) });
  const routed = run.result.reviewersRouted.find((x) => x.role === 'reliability-review');
  assert.ok(routed);
  assert.match(routed.because, /concurrency=true/);
  assert.equal(count(run, 'reliability-reviewer|SLICE'), 1);
});

test('mechanicalOnly → simplicity not routed, with a reason', async () => {
  const run = await runSlice({}, { 'verifier|VERIFY': verifyResult({ routing: { mechanicalOnly: true } }) });
  assert.ok(!run.result.reviewersRouted.some((x) => x.role === 'simplicity-review'));
  const nr = run.result.reviewersNotRouted.find((x) => x.role === 'simplicity-review');
  assert.ok(nr);
  assert.match(nr.because, /mechanicalOnly=true/);
  assert.equal(count(run, 'simplicity-reviewer|SLICE'), 0);
  assert.equal(count(run, 'code-reviewer|SLICE'), 1);
});

test('reviewer null twice → BLOCKED_REVIEWER (fail closed)', async () => {
  const run = await runSlice({ 'code-reviewer|SLICE': [null, null] });
  assert.equal(run.result.status, 'BLOCKED_REVIEWER');
  assert.match(run.result.reason, /code-review SLICE/);
  assert.equal(count(run, 'code-reviewer|SLICE'), 2);
});

test('reviewer null once → retried under a new label and continues', async () => {
  const run = await runSlice({ 'code-reviewer|SLICE': [null] });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  const tries = run.calls.filter((c) => c.key === 'code-reviewer|SLICE');
  assert.equal(tries.length, 2);
  assert.notEqual(tries[0].opts.label, tries[1].opts.label);
  assert.match(tries[1].opts.label, /\(retry 1\)$/);
});

test('persistent MINOR for 3 rounds → ESCALATE with openFindings', async () => {
  const f = finding({ id: 'code-001', severity: 'MINOR' });
  const run = await runSlice({}, {
    'code-reviewer|SLICE': reviewer({ findings: [f] }),
    'code-reviewer|RECHECK': reviewer({ mode: 'RECHECK', findings: [f] }),
  });
  assert.equal(run.result.status, 'ESCALATE');
  assert.equal(run.result.rounds, 3);
  assert.equal(run.result.openFindings.length, 1);
  assert.equal(run.result.openFindings[0].id, 'code-001');
  assert.equal(count(run, 'implementer|FIX'), 3);
  assert.equal(count(run, 'code-reviewer|RECHECK'), 3);
  assert.equal(count(run, 'verifier|VERIFY'), 4);
  const fixes = run.calls.filter((c) => c.key === 'implementer|FIX').map((c) => /^Round: (\d+)$/m.exec(c.prompt)[1]);
  assert.deepEqual(fixes, ['1', '2', '3']);
  const recheck = run.calls.find((c) => c.key === 'code-reviewer|RECHECK');
  assert.match(recheck.prompt, /code-001/);
  // simplicity had no findings: not re-run in later rounds
  assert.equal(count(run, 'simplicity-reviewer|SLICE'), 1);
  assert.equal(count(run, 'simplicity-reviewer|RECHECK'), 0);
  // one journal entry per round for the deterministic decisions
  assert.deepEqual(run.steps.filter((s) => /^open findings round/.test(s.key)).map((s) => s.key), ['open findings round 0', 'open findings round 1', 'open findings round 2', 'open findings round 3']);
});

test('fixed finding → READY_FOR_HUMAN after one round', async () => {
  const f = finding({ id: 'code-001', severity: 'MAJOR' });
  const run = await runSlice({}, {
    'code-reviewer|SLICE': reviewer({ findings: [f] }),
    'code-reviewer|RECHECK': reviewer({ mode: 'RECHECK', findings: [{ ...f, status: 'FIXED' }] }),
    'implementer|FIX': author('implementer', 'FIX', { fixed: ['code-001'] }),
  });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  assert.equal(run.result.rounds, 1);
  assert.equal(run.result.findings[0].status, 'FIXED');
  assert.equal(count(run, 'verifier|FIX_TESTS'), 0);
});

test('findings grouped by owner: implementer FIX and verifier FIX_TESTS in parallel', async () => {
  const fc = finding({ id: 'code-001', owner: 'implementer', location: 'src/a.js:1' });
  const ft = finding({ id: 'code-002', owner: 'verifier', location: 'tests/a.test.js:1', category: 'test-quality' });
  const run = await runSlice({}, {
    'code-reviewer|SLICE': reviewer({ findings: [fc, ft] }),
    'code-reviewer|RECHECK': reviewer({ mode: 'RECHECK', findings: [{ ...fc, status: 'FIXED' }, { ...ft, status: 'FIXED' }] }),
  });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  const fix = run.calls.find((c) => c.key === 'implementer|FIX');
  const fixTests = run.calls.find((c) => c.key === 'verifier|FIX_TESTS');
  assert.equal(fix.batch, fixTests.batch);
  assert.match(fix.prompt, /code-001/);
  assert.doesNotMatch(fix.prompt, /code-002/);
  assert.match(fixTests.prompt, /code-002/);
  const groups = run.steps.find((s) => s.key === 'fix groups round 1');
  assert.deepEqual([groups.value.implementer.length, groups.value.verifier.length], [1, 1]);
});

test('accepted rebuttal → REBUTTED, not open', async () => {
  const f = finding({ id: 'code-001', severity: 'MAJOR' });
  const run = await runSlice({}, {
    'code-reviewer|SLICE': reviewer({ findings: [f] }),
    'implementer|FIX': author('implementer', 'FIX', { rebuttals: [{ findingId: 'code-001', citation: 'SLICE.md AC2', argument: 'required by AC2' }] }),
    'code-reviewer|REBUTTAL': rebuttalResponse('code-001', 'ACCEPT_REBUTTAL'),
  });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  assert.equal(run.result.findings.length, 1);
  assert.equal(run.result.findings[0].status, 'REBUTTED');
  assert.deepEqual(run.result.openFindings, []);
  const ask = run.calls.find((c) => c.key === 'code-reviewer|REBUTTAL');
  assert.match(ask.prompt, /^Mode: REBUTTAL$/m);
  assert.deepEqual(Object.keys(ask.opts.schema.properties).sort(), ['findingId', 'reason', 'response']);
  assert.match(ask.prompt, /AC2/);
  // the fix round's code is still looked at once by the code reviewer, on the incremental diff
  assert.equal(count(run, 'code-reviewer|RECHECK'), 1);
  assert.match(run.calls.find((c) => c.key === 'code-reviewer|RECHECK').prompt, /Changes since your last review: git diff abc1234\.\.feature\/demo-slice-01/);
});

test('maintained rebuttal → stays OPEN and is rechecked', async () => {
  const f = finding({ id: 'code-001', severity: 'MAJOR' });
  const run = await runSlice({}, {
    'code-reviewer|SLICE': reviewer({ findings: [f] }),
    'implementer|FIX': author('implementer', 'FIX', { rebuttals: [{ findingId: 'code-001', citation: 'x', argument: 'y' }] }),
    'code-reviewer|REBUTTAL': rebuttalResponse('code-001', 'MAINTAIN_FINDING'),
    'code-reviewer|RECHECK': reviewer({ mode: 'RECHECK', findings: [{ ...f, status: 'FIXED' }] }),
  });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  assert.equal(count(run, 'code-reviewer|REBUTTAL'), 1); // one rebuttal per finding
  assert.equal(count(run, 'code-reviewer|RECHECK'), 1);
});

test('maintained BLOCKING architecture finding → architect ADJUDICATE; ESCALATE verdict → ESCALATE', async () => {
  const f = finding({ id: 'code-001', severity: 'BLOCKING', category: 'architecture' });
  const run = await runSlice({}, {
    'code-reviewer|SLICE': reviewer({ findings: [f] }),
    'implementer|FIX': author('implementer', 'FIX', { rebuttals: [{ findingId: 'code-001', citation: 'ADR-002', argument: 'decided' }] }),
    'code-reviewer|REBUTTAL': rebuttalResponse('code-001', 'MAINTAIN_FINDING'),
    'architect|ADJUDICATE': architect({ mode: 'ADJUDICATE', verdict: 'ESCALATE' }),
  });
  assert.equal(run.result.status, 'ESCALATE');
  assert.equal(count(run, 'architect|ADJUDICATE'), 1);
});

test('architect-owned finding → ADJUDICATE first, then routed to the implementer', async () => {
  const f = finding({ id: 'code-001', severity: 'MAJOR', owner: 'architect', category: 'design' });
  const run = await runSlice({}, {
    'code-reviewer|SLICE': reviewer({ findings: [f] }),
    'architect|ADJUDICATE': architect({ mode: 'ADJUDICATE', verdict: 'RESOLVED', findings: [{ ...f, owner: 'implementer', reporters: ['architect'] }] }),
    'code-reviewer|RECHECK': reviewer({ mode: 'RECHECK', findings: [{ ...f, status: 'FIXED' }] }),
  });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  const adj = run.calls.findIndex((c) => c.key === 'architect|ADJUDICATE');
  const fix = run.calls.findIndex((c) => c.key === 'implementer|FIX');
  assert.ok(adj >= 0 && fix > adj);
});

test('human-owned finding → ESCALATE without a fix round', async () => {
  const f = finding({ id: 'code-001', severity: 'MAJOR', owner: 'human' });
  const run = await runSlice({}, { 'code-reviewer|SLICE': reviewer({ findings: [f] }) });
  assert.equal(run.result.status, 'ESCALATE');
  assert.equal(count(run, 'implementer|FIX'), 0);
});

test('SHARED tier → NEEDS_SHARED_APPROVAL; relaunch with sharedApproved continues', async () => {
  const tier = { name: 'staging-smoke', environment: 'SHARED', status: 'AWAITING_APPROVAL', why: 'needs the shared staging env' };
  const first = await runSlice({}, { 'verifier|VERIFY': verifyResult({ tiers: [tier] }) });
  assert.equal(first.result.status, 'NEEDS_SHARED_APPROVAL');
  assert.match(first.result.reason, /staging-smoke/);
  assert.equal(count(first, 'code-reviewer|SLICE'), 0);
  assert.deepEqual(first.pauses, [], 'no pause unless pauseForShared is set');

  const second = await runSlice({}, { 'verifier|VERIFY': verifyResult({ tiers: [{ ...tier, status: 'PASS' }] }) }, { sharedApproved: ['staging-smoke'], startAt: 'VERIFY' });
  assert.equal(second.result.status, 'READY_FOR_HUMAN');
  assert.equal(count(second, 'verifier|TEST_PLAN'), 0); // resumes at Verify
  assert.equal(count(second, 'implementer|IMPLEMENT'), 0);
  const v = second.calls.find((c) => c.key === 'verifier|VERIFY');
  assert.match(v.prompt, /Approved SHARED tiers: staging-smoke/);
});

test('pauseForShared: ctx.pause is the SHARED-tier stop; a resume with decisions continues at Verify', async () => {
  const tier = { name: 'staging-smoke', environment: 'SHARED', status: 'AWAITING_APPROVAL', why: 'needs the shared staging env' };
  let n = 0;
  const verify = () => verifyResult({ tiers: [{ ...tier, status: n++ === 0 ? 'AWAITING_APPROVAL' : 'PASS' }] });
  const run = await runSlice({}, { 'verifier|VERIFY': verify }, { pauseForShared: true }, { pauses: { 'shared-approval': { sharedApproved: { 'staging-smoke': true } } } });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  assert.equal(run.pauses.length, 1);
  assert.match(run.pauses[0].name, /^shared-approval: staging-smoke$/);
  assert.equal(count(run, 'verifier|VERIFY'), 2);
  assert.equal(count(run, 'verifier|TEST_PLAN'), 1); // the test plan and build are not redone
  assert.match(run.calls.filter((c) => c.key === 'verifier|VERIFY')[1].prompt, /Approved SHARED tiers: staging-smoke/);
  assert.equal(run.result.rounds, 0);
});

test('pauseForShared: a resume without decisions falls back to NEEDS_SHARED_APPROVAL', async () => {
  const tier = { name: 'staging-smoke', environment: 'SHARED', status: 'AWAITING_APPROVAL', why: 'needs the shared staging env' };
  const run = await runSlice({}, { 'verifier|VERIFY': verifyResult({ tiers: [tier] }) }, { pauseForShared: true });
  assert.equal(run.result.status, 'NEEDS_SHARED_APPROVAL');
  assert.equal(run.pauses.length, 1);
  assert.equal(count(run, 'verifier|VERIFY'), 1);
});

test('sharedApproved map: denied tier is not re-asked and continues; approved tier listed', async () => {
  const denied = { name: 'staging-smoke', environment: 'SHARED', status: 'AWAITING_APPROVAL', why: 'needs the shared staging env' };
  const run = await runSlice({}, { 'verifier|VERIFY': verifyResult({ tiers: [denied] }) }, { sharedApproved: { 'staging-smoke': false, 'perf-env': true }, startAt: 'VERIFY' });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  const v = run.calls.find((c) => c.key === 'verifier|VERIFY');
  assert.match(v.prompt, /Approved SHARED tiers: perf-env/);
  assert.match(v.prompt, /Denied SHARED tiers .*staging-smoke/);
});

test('build FAIL → implementer FIX with the failure, counts as a round', async () => {
  const run = await runSlice({ 'verifier|VERIFY': [verifyResult({ build: 'FAIL' })] });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  assert.equal(run.result.rounds, 1);
  const fix = run.calls.find((c) => c.key === 'implementer|FIX');
  assert.match(fix.prompt, /build FAIL/);
  assert.equal(count(run, 'verifier|VERIFY'), 2);
  assert.equal(count(run, 'verifier|FIX_TESTS'), 0); // a build failure is never the tests' fault
  assert.deepEqual(run.steps.find((s) => s.key === 'verify failure round 0').value, { buildFailed: true, text: 'build FAIL' });
});

test('dedupe merges reporters and keeps the highest severity', async () => {
  const a = finding({ id: 'code-001', severity: 'MINOR', category: 'design', location: 'src/cache/store.js:10-20' });
  const b = finding({ id: 'simp-001', severity: 'MAJOR', category: 'Design', location: 'src/cache/store.js:10-20 ', reporters: ['simplicity-reviewer'] });
  const run = await runSlice({}, {
    'code-reviewer|SLICE': reviewer({ findings: [a] }),
    'simplicity-reviewer|SLICE': reviewer({ reviewer: 'simplicity-reviewer', findings: [b] }),
    'code-reviewer|RECHECK': reviewer({ mode: 'RECHECK', findings: [{ ...a, status: 'FIXED' }] }),
    'simplicity-reviewer|RECHECK': reviewer({ reviewer: 'simplicity-reviewer', mode: 'RECHECK', findings: [{ ...b, status: 'FIXED' }] }),
  });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  assert.equal(run.result.findings.length, 1);
  const m = run.result.findings[0];
  assert.equal(m.severity, 'MAJOR');
  assert.deepEqual(m.reporters.slice().sort(), ['code-review', 'simplicity-review']);
  const fix = run.calls.find((c) => c.key === 'implementer|FIX');
  assert.equal((fix.prompt.match(/"id":/g) || []).length, 1); // one merged finding sent to the author
});

test('NOTE-only → READY_FOR_HUMAN', async () => {
  const n = finding({ id: 'code-001', severity: 'NOTE' });
  const run = await runSlice({}, { 'code-reviewer|SLICE': reviewer({ findings: [n] }) });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  assert.equal(run.result.findings.length, 1);
  assert.deepEqual(run.result.openFindings, []);
  assert.equal(count(run, 'implementer|FIX'), 0);
});

test('humanInputRequests and abilityVersions are collected', async () => {
  const hir = { question: 'Which cache size?', evidence: 'SLICE.md AC3', recommendation: '128', blocked: 'AC3' };
  const run = await runSlice({}, {
    'verifier|TEST_PLAN': testPlanResult({ humanInputRequested: hir }),
    'code-reviewer|SLICE': reviewer({ abilityVersions: { 'code-clarity': '1.0.0' } }),
    'simplicity-reviewer|SLICE': reviewer({ reviewer: 'simplicity-reviewer', abilityVersions: { 'simplicity-review': '1.0.0' } }),
  });
  assert.equal(run.result.humanInputRequests.length, 1);
  assert.equal(run.result.humanInputRequests[0].question, 'Which cache size?');
  assert.deepEqual(run.result.abilityVersions, { 'code-clarity': '1.0.0', 'simplicity-review': '1.0.0' });
});

test('contract major mismatch throws', async () => {
  const bad = loadContracts();
  bad['reviewer-result'] = { ...bad['reviewer-result'], 'x-contract-version': '2.0.0' };
  await assert.rejects(
    runWorkflow('slice', { ...SLICE_ARGS, contracts: bad }, {}, sliceDefaults()),
    /reviewer-result.*major version mismatch.*wants 1.*2\.0\.0/,
  );
  const badResult = loadContracts();
  badResult['slice-workflow-result'] = { ...badResult['slice-workflow-result'], 'x-contract-version': '3.0.0' };
  await assert.rejects(
    runWorkflow('slice', { ...SLICE_ARGS, contracts: badResult }, {}, sliceDefaults()),
    /slice-workflow-result.*major 3 does not match registry workflowContractMajor\.slice 1/,
  );
});

test('missing args fail loudly', async () => {
  await assert.rejects(runWorkflow('slice', { ...SLICE_ARGS, sliceBranch: undefined }, {}, sliceDefaults()), /sliceBranch/);
  await assert.rejects(runWorkflow('slice', { ...SLICE_ARGS, slice: undefined }, {}, sliceDefaults()), /args\.slice is required/);
});

test('schemas passed to agent() are stripped contracts', async () => {
  const run = await runSlice();
  const c = run.calls.find((x) => x.key === 'verifier|VERIFY');
  assert.deepEqual(c.opts.schema, strip(contracts['verify-result']));
  assert.ok(keys(run).includes('verifier|TEST_PLAN'));
});

// ---------------------------------------------------------------------------------------------
// Regression tests carried over from Shipyard's independent review
// ---------------------------------------------------------------------------------------------

test('two findings from one reviewer at the same location are both fixed, never merged', async () => {
  const a = finding({ id: 'code-001', category: 'tests/test-to-add', location: 'tests/x.py:1-40', owner: 'verifier', finding: 'AC-1 untested' });
  const b = finding({ id: 'code-002', category: 'tests/test-to-add', location: 'tests/x.py:1-40', owner: 'verifier', finding: 'AC-2 untested' });
  const run = await runSlice({
    'code-reviewer|RECHECK': [reviewer({ mode: 'RECHECK', findings: [{ ...a, status: 'FIXED' }, b] })],
  }, {
    'code-reviewer|SLICE': reviewer({ findings: [a, b] }),
    'code-reviewer|RECHECK': reviewer({ mode: 'RECHECK', findings: [{ ...a, status: 'FIXED' }, { ...b, status: 'FIXED' }] }),
  });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  assert.equal(run.result.findings.length, 2);
  const fixes = run.calls.filter((c) => c.key === 'verifier|FIX_TESTS');
  assert.match(fixes[0].prompt, /code-001/);
  assert.match(fixes[0].prompt, /code-002/);
  assert.doesNotMatch(fixes[1].prompt, /code-001/); // fixed one is not sent again
  assert.match(fixes[1].prompt, /code-002/);
  assert.equal(run.result.rounds, 2);
  for (const f of run.result.findings) assert.ok(!('memberKeys' in f));
});

test('sharedApproved alone does not skip the test plan', async () => {
  const run = await runSlice({}, {}, { sharedApproved: { staging: false } });
  assert.equal(count(run, 'verifier|TEST_PLAN'), 1);
  assert.equal(count(run, 'implementer|IMPLEMENT'), 1);
});

test('VERIFY must read the test plan as APPROVED, or the run stops (fail closed)', async () => {
  const run = await runSlice({}, { 'verifier|VERIFY': verifyResult({ testPlanStatus: 'DRAFT' }) }, { startAt: 'VERIFY' });
  assert.equal(run.result.status, 'BLOCKED');
  assert.match(run.result.reason, /test plan first/);
  assert.equal(count(run, 'code-reviewer|SLICE'), 0);
});

test('APPROVE without a confirmed status flip → BLOCKED before anything is built', async () => {
  const run = await runSlice({}, { 'code-reviewer|TEST_PLAN': reviewer({ mode: 'TEST_PLAN', verdict: 'APPROVE', extras: {} }) });
  assert.equal(run.result.status, 'BLOCKED');
  assert.match(run.result.reason, /not APPROVED/);
  assert.equal(count(run, 'implementer|IMPLEMENT'), 0);
  assert.equal(count(run, 'verifier|WRITE_TESTS'), 0);
  assert.deepEqual(run.steps.find((s) => s.key === 'test plan gate revision 0').value, { verdict: 'APPROVE', seen: null });
});

test('bad startAt fails loudly', async () => {
  await assert.rejects(runWorkflow('slice', { ...SLICE_ARGS, startAt: 'FIX' }, {}, sliceDefaults()), /startAt/);
});

test('human change requests: start at Fix, outside the cap, then full review', async () => {
  const run = await runSlice({}, {
    'implementer|FIX': (prompt) => author('implementer', 'FIX', { fixed: /human-1/.test(prompt) ? ['human-1'] : [] }),
  }, { round: 3, humanRound: 2, humanChanges: [{ id: 'human-1', owner: 'implementer', finding: 'Rename the flag to cacheEnabled' }] });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  assert.equal(count(run, 'verifier|TEST_PLAN'), 0);
  assert.equal(count(run, 'implementer|IMPLEMENT'), 0);
  const fix = run.calls.find((c) => c.key === 'implementer|FIX');
  assert.match(fix.prompt, /change requests from the merge gate/);
  assert.match(fix.prompt, /cacheEnabled/);
  assert.match(fix.prompt, /slice 01 human-2 round 0: code/);
  assert.ok(fix.index < run.calls.findIndex((c) => c.key === 'verifier|VERIFY'));
  // review re-runs in full (SLICE mode), and the human change is reported back
  assert.equal(count(run, 'code-reviewer|SLICE'), 1);
  assert.equal(run.result.humanChanges.length, 1);
  assert.equal(run.result.rounds, 0); // the cap starts fresh: earlier rounds (3) do not count
  assert.equal(run.phases[0], 'Fix');
});

test('human change request not done → ESCALATE', async () => {
  const run = await runSlice({}, {}, { humanChanges: [{ owner: 'verifier', finding: 'Add a test for an empty key' }] });
  assert.equal(run.result.status, 'ESCALATE');
  assert.match(run.result.reason, /human-1/);
  assert.equal(count(run, 'verifier|VERIFY'), 0);
});

test('bad humanChanges owner fails loudly', async () => {
  await assert.rejects(runWorkflow('slice', { ...SLICE_ARGS, humanChanges: [{ owner: 'architect', finding: 'x' }] }, {}, sliceDefaults()), /owner must be implementer or verifier/);
});

test('architecture concern from the implementer → architect rules → verifier fixes the test in the same round', async () => {
  const run = await runSlice({}, {
    'implementer|IMPLEMENT': author('implementer', 'IMPLEMENT', { testDisputes: [{ test: 'tests/cache/store.test.js::evicts', reason: 'expects LRU; AC2 says FIFO', citation: 'SLICE.md AC2' }] }),
    'architect|ADJUDICATE': (prompt) => {
      const id = /"id": "(implementer-dispute-[^"]+)"/.exec(prompt)[1];
      return architect({ mode: 'ADJUDICATE', verdict: 'RESOLVED', findings: [finding({ id, owner: 'verifier', requiredResolution: 'Assert FIFO order per AC2', reporters: ['architect'] })] });
    },
    'verifier|FIX_TESTS': (prompt) => author('verifier', 'FIX_TESTS', { fixed: [/"id": "(implementer-dispute-[^"]+)"/.exec(prompt)[1]] }),
  });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  const adj = run.calls.findIndex((c) => c.key === 'architect|ADJUDICATE');
  const fixTests = run.calls.findIndex((c) => c.key === 'verifier|FIX_TESTS');
  const verify = run.calls.findIndex((c) => c.key === 'verifier|VERIFY');
  assert.ok(adj > 0 && fixTests > adj && verify > fixTests);
  assert.match(run.calls[fixTests].prompt, /Assert FIFO order per AC2/);
  assert.equal(run.result.authorNotes.testDisputes.length, 1);
  assert.equal(run.result.authorNotes.rulings[0].owner, 'verifier');
});

test('architect escalates an architecture concern → ESCALATE', async () => {
  const run = await runSlice({}, {
    'implementer|IMPLEMENT': author('implementer', 'IMPLEMENT', { architectureConcerns: ['The approved port cannot express streaming'] }),
    'architect|ADJUDICATE': architect({ mode: 'ADJUDICATE', verdict: 'ESCALATE' }),
  });
  assert.equal(run.result.status, 'ESCALATE');
  assert.match(run.result.reason, /architect escalated author concerns/);
  assert.equal(count(run, 'verifier|VERIFY'), 0);
});

test('clean review but stubs remaining → a fix pass for the author, then READY_FOR_HUMAN', async () => {
  const run = await runSlice({}, { 'implementer|IMPLEMENT': author('implementer', 'IMPLEMENT', { stubsRemaining: ['src/cache/evict.js: TODO'] }) });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  assert.equal(run.result.rounds, 1);
  const fix = run.calls.find((c) => c.key === 'implementer|FIX');
  assert.match(fix.prompt, /reported this work as unfinished/);
  assert.match(fix.prompt, /evict\.js: TODO/);
});

test('stubs that never go away → ESCALATE at the cap, not READY_FOR_HUMAN', async () => {
  const stub = { stubsRemaining: ['src/cache/evict.js: TODO'] };
  const run = await runSlice({}, {
    'implementer|IMPLEMENT': author('implementer', 'IMPLEMENT', stub),
    'implementer|FIX': author('implementer', 'FIX', stub),
  });
  assert.equal(run.result.status, 'ESCALATE');
  assert.match(run.result.reason, /stubs remaining/);
  assert.equal(run.result.rounds, 3);
});

test('rebuttal and architecture concern in the same fix round: the rebuttal is still answered, labels stay unique', async () => {
  const f = finding({ id: 'code-001', severity: 'MAJOR' });
  const run = await runSlice({}, {
    'code-reviewer|SLICE': reviewer({ findings: [f] }),
    'implementer|FIX': (prompt) => (/architect's rulings/.test(prompt)
      ? author('implementer', 'FIX', { fixed: [/"id": "(implementer-concern-[^"]+)"/.exec(prompt)[1]] })
      : author('implementer', 'FIX', { rebuttals: [{ findingId: 'code-001', citation: 'SLICE.md AC2', argument: 'required' }], architectureConcerns: ['Port lacks streaming'] })),
    'architect|ADJUDICATE': (prompt) => architect({ mode: 'ADJUDICATE', verdict: 'RESOLVED', findings: [finding({ id: /"id": "(implementer-concern-[^"]+)"/.exec(prompt)[1], owner: 'implementer', requiredResolution: 'Buffer in the adapter', reporters: ['architect'] })] }),
    'code-reviewer|REBUTTAL': rebuttalResponse('code-001', 'ACCEPT_REBUTTAL'),
  });
  assert.equal(count(run, 'code-reviewer|REBUTTAL'), 1);
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  assert.equal(run.result.findings.find((x) => x.id === 'code-001').status, 'REBUTTED');
  // two implementer FIX calls in the same round carry different labels (the runtime memoises identical calls)
  const fixes = run.calls.filter((c) => c.key === 'implementer|FIX');
  assert.equal(fixes.length, 2);
  assert.notEqual(fixes[0].opts.label, fixes[1].opts.label);
});

test('a finding merged from two reviewers is rechecked by each under its own id: one round', async () => {
  const a = finding({ id: 'code-001', severity: 'MAJOR', category: 'design', location: 'src/a.js:1' });
  const b = finding({ id: 'simp-001', severity: 'MAJOR', category: 'design', location: 'src/a.js:1', reporters: ['simplicity-reviewer'] });
  const fixedAll = (who) => (prompt) => {
    const ids = [...prompt.matchAll(/"id": "([^"]+)"/g)].map((m) => m[1]);
    const src = who === 'code' ? a : b;
    return reviewer({ reviewer: `${who === 'code' ? 'code' : 'simplicity'}-reviewer`, mode: 'RECHECK', findings: ids.map((id) => ({ ...src, id, status: 'FIXED' })) });
  };
  const run = await runSlice({}, {
    'code-reviewer|SLICE': reviewer({ findings: [a] }),
    'simplicity-reviewer|SLICE': reviewer({ reviewer: 'simplicity-reviewer', findings: [b] }),
    'code-reviewer|RECHECK': fixedAll('code'),
    'simplicity-reviewer|RECHECK': fixedAll('simp'),
  });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  assert.equal(run.result.rounds, 1);
  const simpRecheck = run.calls.find((c) => c.key === 'simplicity-reviewer|RECHECK');
  assert.match(simpRecheck.prompt, /simp-001/);
});

test('a rebutted finding does not swallow a later finding from another reviewer at the same place', async () => {
  const a = finding({ id: 'code-001', severity: 'MAJOR', category: 'design', location: 'src/a.js:1' });
  const later = finding({ id: 'sec-001', severity: 'MAJOR', category: 'design', location: 'src/a.js:1', reporters: ['security-reviewer'] });
  const run = await runSlice({}, {
    'code-reviewer|SLICE': reviewer({ findings: [a] }),
    'implementer|FIX': author('implementer', 'FIX', { rebuttals: [{ findingId: 'code-001', citation: 'ADR-1', argument: 'decided' }] }),
    'code-reviewer|REBUTTAL': rebuttalResponse('code-001', 'ACCEPT_REBUTTAL'),
    // round 1: the verifier now reports security=true, so the security reviewer runs and files at the same spot
    'verifier|VERIFY': (() => { let n = 0; return () => verifyResult({ routing: { security: n++ > 0 } }); })(),
    'security-reviewer|SLICE': reviewer({ reviewer: 'security-reviewer', findings: [later] }),
    'security-reviewer|RECHECK': reviewer({ reviewer: 'security-reviewer', mode: 'RECHECK', findings: [{ ...later, status: 'FIXED' }] }),
  });
  assert.equal(count(run, 'security-reviewer|SLICE'), 1);
  assert.ok(count(run, 'implementer|FIX') >= 2, 'the later finding got its own fix round');
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
});

test('test-only slice still gets a code review', async () => {
  const run = await runSlice({}, { 'verifier|VERIFY': verifyResult({ routing: { productionCode: false } }) });
  assert.equal(count(run, 'code-reviewer|SLICE'), 1);
  assert.ok(run.result.reviewersRouted.some((x) => x.role === 'code-review' && /always/.test(x.because)));
});

test('a finding with category security pulls in the security reviewer', async () => {
  const f = finding({ id: 'code-001', severity: 'MAJOR', category: 'security' });
  const run = await runSlice({}, {
    'code-reviewer|SLICE': reviewer({ findings: [f] }),
    'code-reviewer|RECHECK': reviewer({ mode: 'RECHECK', findings: [{ ...f, status: 'FIXED' }] }),
  });
  assert.equal(count(run, 'security-reviewer|SLICE'), 1);
  assert.ok(run.result.reviewersRouted.some((x) => x.role === 'security-review' && /code-001/.test(x.because)));
  assert.ok(!run.result.reviewersNotRouted.some((x) => x.role === 'security-review'));
});

test('code review re-runs on fix-round code even with no open findings of its own', async () => {
  const s = finding({ id: 'simp-001', severity: 'MAJOR', category: 'abstraction', reporters: ['simplicity-reviewer'] });
  const run = await runSlice({}, {
    'simplicity-reviewer|SLICE': reviewer({ reviewer: 'simplicity-reviewer', findings: [s] }),
    'simplicity-reviewer|RECHECK': reviewer({ reviewer: 'simplicity-reviewer', mode: 'RECHECK', findings: [{ ...s, status: 'FIXED' }] }),
  });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  const cr = run.calls.filter((c) => c.key === 'code-reviewer|RECHECK');
  assert.equal(cr.length, 1);
  assert.match(cr[0].prompt, /Your open findings:\nnone/);
});

test('an open finding left out of a recheck stays OPEN (fail closed)', async () => {
  const f = finding({ id: 'code-001', severity: 'MAJOR' });
  const run = await runSlice({}, {
    'code-reviewer|SLICE': reviewer({ findings: [f] }),
    'code-reviewer|RECHECK': reviewer({ mode: 'RECHECK', findings: [] }),
  });
  assert.equal(run.result.status, 'ESCALATE');
  assert.equal(run.result.openFindings[0].id, 'code-001');
});

test('scope DRIFT from VERIFY is passed to every reviewer', async () => {
  const run = await runSlice({}, { 'verifier|VERIFY': verifyResult({ scopeCheck: 'DRIFT', drift: ['src/other.js'] }) });
  assert.equal(run.result.status, 'READY_FOR_HUMAN');
  for (const c of run.calls.filter((x) => /\|SLICE$/.test(x.key))) assert.match(c.prompt, /VERIFY reported scope DRIFT: src\/other\.js/);
});

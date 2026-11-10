import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runWorkflow, discovery, goldfish, architect } from './harness.mjs';

const REQUEST = 'Add a read-through cache in front of the pricing service so list pages stop timing out.';
const CONSTRAINTS = 'C-1 slice budget: ~400 lines. C-3 reuse posture: reuse first. C-9 cost budget: medium.';

function defaults() {
  return {
    'discovery|SCAN': discovery('SCAN', { artifactsWritten: ['.ai/planning/discovery.md'] }),
    'discovery|ELEPHANT': discovery('ELEPHANT', { artifactsWritten: ['.ai/planning/concepts.md'] }),
    'discovery|SYNTHESIZE': discovery('SYNTHESIZE', {
      artifactsWritten: ['.ai/planning/concepts.md'],
      topConcepts: [{ title: 'Read-through cache', summary: 'cache in the client', lensesThatProposedIt: ['technical'] }],
      disagreements: ['contrarian: fix the slow query instead'],
      gaps: [{ id: 'G1', question: 'TTL?', whyItMatters: 'staleness', evidence: 'pricing.js:40', options: ['60s', '5m'], recommendation: '60s', blocking: true }],
    }),
    'discovery|DRAFT': discovery('DRAFT', { artifactsWritten: ['.ai/PROJECT.md', '.ai/CONSUMERS.md'] }),
    'architect|DRAFT': architect({ mode: 'DRAFT', verdict: 'SOUND' }),
    'discovery|QUESTIONS': discovery('QUESTIONS', {
      artifactsWritten: ['.ai/planning/open-questions.md'],
      gaps: [
        { id: 'G1', question: 'TTL?', whyItMatters: 'staleness', evidence: 'pricing.js:40', options: ['60s', '5m'], recommendation: '60s', blocking: true, kind: 'decision', dependsOn: [], status: 'OPEN' },
        { id: 'G2', question: 'Evict on write?', whyItMatters: 'consistency', evidence: 'pricing.js:52', options: ['yes', 'no'], recommendation: 'yes', blocking: false, kind: 'decision', dependsOn: ['G1'], status: 'OPEN' },
        { id: 'G3', question: 'Which store?', whyItMatters: 'none', evidence: 'package.json', options: [], recommendation: 'in-memory, the only store present', blocking: false, kind: 'fact', dependsOn: [], status: 'SETTLED' },
      ],
      highestLeverageQuestion: 'TTL?',
    }),
    'goldfish|BRAINSTORM': (prompt) => {
      const lens = /^Lens: (\S+)$/m.exec(prompt)[1];
      return goldfish({ lens, concepts: [{ title: `${lens} idea`, summary: 's', why: 'w', risks: 'r', relativeSize: 'S' }] });
    },
  };
}

async function runDiscover(args, script = {}, options = {}) {
  const run = await runWorkflow('discover', { request: REQUEST, constraints: CONSTRAINTS, ...args }, script, defaults(), options);
  assert.deepEqual(run.errors, [], run.errors.join('\n'));
  return run;
}

function keys(run) {
  return run.calls.map((c) => c.key);
}

test('breadth 1 → 3 goldfish whose briefs contain only the request and the lens', async () => {
  const run = await runDiscover({ breadth: 1 });
  assert.equal(run.result.status, 'NEEDS_HUMAN');
  const fish = run.calls.filter((c) => c.key === 'goldfish|BRAINSTORM');
  assert.equal(fish.length, 3);
  assert.deepEqual(fish.map((c) => /^Lens: (\S+)$/m.exec(c.prompt)[1]), ['technical', 'value', 'contrarian']);
  assert.equal(new Set(fish.map((c) => c.batch)).size, 1);
  for (const c of fish) {
    assert.ok(c.prompt.includes(REQUEST));
    assert.doesNotMatch(c.prompt, /C-1|C-3|reuse posture/);
    assert.doesNotMatch(c.prompt, /discovery\.md|concepts\.md|elephant/i);
    assert.doesNotMatch(c.prompt, /^Read:/m);
    // only header lines + lens + request
    const body = c.prompt.split('\n\n').slice(1).join('\n\n').trim();
    assert.equal(body, `Lens: ${/^Lens: (\S+)$/m.exec(c.prompt)[1]}\n\nRequest (verbatim):\n${REQUEST}`);
    assert.match(c.prompt, /^Caller: shipyard-coordinator\nMode: BRAINSTORM\n/);
    assert.equal(c.opts.agent, 'shipyard-goldfish');
  }
  const scan = run.calls.find((c) => c.key === 'discovery|SCAN');
  assert.doesNotMatch(scan.prompt, /write your sealed elephant take/i);
  const elephant = run.calls.find((c) => c.key === 'discovery|ELEPHANT');
  assert.match(elephant.prompt, /sealed elephant take/i);
  assert.match(elephant.prompt, /\.ai\/planning\/concepts\.md/);
  assert.ok(elephant.index > scan.index && elephant.index < Math.min(...fish.map((f) => f.index)), 'the take is sealed before any goldfish runs');
  const synth = run.calls.find((c) => c.key === 'discovery|SYNTHESIZE');
  assert.match(synth.prompt, /"lens": "contrarian"/);
  assert.ok(synth.index > Math.max(...fish.map((f) => f.index)));
  assert.equal(run.result.topConcepts.length, 1);
  assert.equal(run.result.gaps[0].id, 'G1');
  assert.ok(run.result.questions.length >= 1);
  assert.ok(run.result.artifacts.includes('.ai/planning/concepts.md'));
  assert.deepEqual(keys(run).filter((k) => !k.startsWith('goldfish')), ['discovery|SCAN', 'discovery|ELEPHANT', 'discovery|SYNTHESIZE', 'discovery|DRAFT', 'architect|DRAFT', 'discovery|QUESTIONS']);
  const draft = run.calls.find((c) => c.key === 'discovery|DRAFT');
  assert.match(draft.prompt, /GLOSSARY\.md/);
  assert.match(draft.prompt, /User stories/);
  const q = run.calls.find((c) => c.key === 'discovery|QUESTIONS');
  assert.match(q.prompt, /question tree/);
  assert.match(q.prompt, /dependsOn/);
  assert.deepEqual(run.phases, ['Scan', 'Brainstorm', 'Draft']);
});

test('the first grill round is the open questions with no unanswered dependency; facts are never asked', async () => {
  const run = await runDiscover({ breadth: 1 });
  assert.deepEqual(run.result.questions.map((q) => q.id), ['G1', 'G2', 'G3']);
  assert.deepEqual(run.result.frontier, ['G1']);
  const g2 = run.result.questions.find((q) => q.id === 'G2');
  assert.deepEqual(g2.dependsOn, ['G1']);
  assert.equal(run.result.questions.find((q) => q.id === 'G3').status, 'SETTLED');
  assert.equal(run.result.formalRigour, 'none');
  assert.match(run.result.reason, /round 1/);
  // the grill round is a journaled step, so a resume replays it
  const grill = run.steps.find((s) => s.key === 'grill round 1');
  assert.ok(grill, 'grill round 1 step');
  assert.deepEqual(grill.value.frontier, ['G1']);
});

test('discovery QUESTIONS may order the frontier, but ineligible ids are dropped and eligible extras are merged in', async () => {
  const hir = { question: 'Keep the old API?', evidence: 'CONSUMERS.md', recommendation: 'yes', blocked: 'order' };
  const run = await runDiscover({ breadth: 0 }, {
    'architect|DRAFT': [architect({ mode: 'DRAFT', verdict: 'SOUND', humanInputRequested: hir })],
    'discovery|QUESTIONS': [discovery('QUESTIONS', {
      artifactsWritten: ['.ai/planning/open-questions.md'],
      gaps: [
        { id: 'G1', question: 'A?', whyItMatters: 'w', evidence: 'e', options: [], recommendation: 'r', blocking: true },
        { id: 'G2', question: 'B?', whyItMatters: 'w', evidence: 'e', options: [], recommendation: 'r', blocking: false, kind: 'decision', dependsOn: ['G1'], status: 'OPEN' },
      ],
      frontier: ['G2', 'G1'], highestLeverageQuestion: 'Why at all?',
    })],
  });
  // G2 depends on the still-open G1 so it is not eligible even though discovery listed it; the highest-leverage
  // question (HL) and the architect's human input request (HIR) are eligible and must not be skipped
  assert.deepEqual(run.result.frontier, ['G1', 'HL', 'HIR-architect']);
  const g1 = run.result.questions.find((q) => q.id === 'G1');
  assert.deepEqual([g1.kind, g1.dependsOn, g1.status], ['decision', [], 'OPEN']);
  const hl = run.result.questions.find((q) => q.id === 'HL');
  assert.deepEqual([hl.kind, hl.dependsOn, hl.status], ['decision', [], 'OPEN']);
});

test('a DEFERRED dependency (default taken) unblocks the questions that hang off it', async () => {
  const run = await runDiscover({ breadth: 0 }, {
    'discovery|QUESTIONS': [discovery('QUESTIONS', {
      artifactsWritten: ['.ai/planning/open-questions.md'],
      gaps: [
        { id: 'G1', question: 'A?', whyItMatters: 'w', evidence: 'e', options: ['x'], recommendation: 'x', blocking: false, kind: 'decision', dependsOn: [], status: 'DEFERRED' },
        { id: 'G2', question: 'B?', whyItMatters: 'w', evidence: 'e', options: [], recommendation: 'r', blocking: true, kind: 'decision', dependsOn: ['G1'], status: 'OPEN' },
      ],
      highestLeverageQuestion: 'B?',
    })],
  });
  assert.deepEqual(run.result.frontier, ['G2']);
});

test('formal rigour flows into the scan and the architect draft; an invalid value fails loudly', async () => {
  const run = await runDiscover({ breadth: 0, formalRigour: 'model-checked' });
  assert.match(run.calls.find((c) => c.key === 'discovery|SCAN').prompt, /quint/);
  const arch = run.calls.find((c) => c.key === 'architect|DRAFT');
  assert.match(arch.prompt, /Formal rigour \(C-10\): model-checked/);
  assert.match(arch.prompt, /\.ai\/formal\/INV-nnn\.qnt/);
  assert.match(arch.prompt, /planted fault/);
  assert.match(arch.prompt, /^Write: .*\.ai\/formal\/\*\.qnt/m);
  assert.equal(run.result.formalRigour, 'model-checked');
  const none = await runDiscover({ breadth: 0 });
  assert.doesNotMatch(none.calls.find((c) => c.key === 'discovery|SCAN').prompt, /quint/);
  assert.doesNotMatch(none.calls.find((c) => c.key === 'architect|DRAFT').prompt, /planted fault/);
  await assert.rejects(runWorkflow('discover', { request: 'x', breadth: 0, formalRigour: 'proofs' }, {}, {}), /formalRigour must be one of/);
});

test('breadth 0 skips goldfish and synthesis', async () => {
  const run = await runDiscover({ breadth: 0 });
  assert.equal(run.result.status, 'NEEDS_HUMAN');
  assert.equal(run.calls.filter((c) => c.key.startsWith('goldfish')).length, 0);
  assert.deepEqual(keys(run), ['discovery|SCAN', 'discovery|DRAFT', 'architect|DRAFT', 'discovery|QUESTIONS']);
  assert.ok(!run.phases.includes('Brainstorm'));
  assert.equal(run.calls.filter((c) => c.key === 'discovery|ELEPHANT').length, 0);
});

test('breadth 2 → five lenses then one outsider told only the cluster titles', async () => {
  const run = await runDiscover({ breadth: 2 });
  const fish = run.calls.filter((c) => c.key === 'goldfish|BRAINSTORM');
  assert.equal(fish.length, 6);
  const outsider = fish[5];
  assert.match(outsider.prompt, /^Lens: outsider$/m);
  assert.match(outsider.prompt, /- technical idea/);
  assert.match(outsider.prompt, /OUTSIDE/);
  assert.ok(outsider.prompt.includes(REQUEST));
  assert.doesNotMatch(outsider.prompt, /C-1/);
  assert.ok(outsider.index > Math.max(...fish.slice(0, 5).map((f) => f.index)));
  assert.deepEqual(run.steps.find((s) => s.key === 'cluster titles').value, ['technical idea', 'value idea', 'experience idea', 'contrarian idea', 'market idea']);
});

test('a required step null after retry → BLOCKED with reason', async () => {
  const run = await runDiscover({ breadth: 0 }, { 'architect|DRAFT': [null, null] });
  assert.equal(run.result.status, 'BLOCKED');
  assert.match(run.result.reason, /architect DRAFT/);
  assert.equal(run.calls.filter((c) => c.key === 'discovery|QUESTIONS').length, 0);
});

test('a goldfish null after retry → BLOCKED', async () => {
  const run = await runDiscover({ breadth: 1 }, { 'goldfish|BRAINSTORM': [null] });
  // first goldfish slot gets null, its retry gets the default → continues
  assert.equal(run.result.status, 'NEEDS_HUMAN');
  const run2 = await runDiscover({ breadth: 1 }, { 'goldfish|BRAINSTORM': [null, null, null, null, null, null] });
  assert.equal(run2.result.status, 'BLOCKED');
  assert.match(run2.result.reason, /goldfish/);
});

test('discovery runs STANDARD for SCAN and DEEP for ELEPHANT and SYNTHESIZE, through the custom-agent option', async () => {
  const run = await runDiscover({ breadth: 1 });
  const scan = run.calls.find((c) => c.key === 'discovery|SCAN');
  const elephant = run.calls.find((c) => c.key === 'discovery|ELEPHANT');
  const synth = run.calls.find((c) => c.key === 'discovery|SYNTHESIZE');
  assert.deepEqual([scan.opts.model, scan.opts.reasoningEffort], ['claude-sonnet-5.5', 'medium']);
  assert.deepEqual([elephant.opts.model, elephant.opts.reasoningEffort], ['claude-opus-5.5', 'high']);
  assert.deepEqual([synth.opts.model, synth.opts.reasoningEffort], ['claude-opus-5.5', 'high']);
  assert.equal(scan.opts.agent, 'shipyard-discovery');
  assert.doesNotMatch(scan.prompt, /^Act as/);
});

test('agentSelection "prompt" names the agent in a preamble and sends only label and schema', async () => {
  const run = await runDiscover({ breadth: 0, agentSelection: 'prompt' });
  assert.equal(run.result.status, 'NEEDS_HUMAN');
  const scan = run.calls.find((c) => c.key === 'discovery|SCAN');
  assert.match(scan.prompt, /^Act as `shipyard-discovery`: read .*\.github[\\/]agents[\\/]shipyard-discovery\.agent\.md first/);
  assert.match(scan.prompt, /\n\nCaller: shipyard-coordinator\nMode: SCAN\n/);
  assert.deepEqual(Object.keys(scan.opts).sort(), ['label', 'phase', 'schema']);
  await assert.rejects(runWorkflow('discover', { request: 'x', breadth: 0, agentSelection: 'magic' }, {}, {}), /agentSelection must be one of/);
});

test('registry and contracts are read from shipyard/ when the args omit them', async () => {
  const run = await runWorkflow('discover', { request: REQUEST, breadth: 0 }, {}, defaults(), { noInputs: true });
  assert.deepEqual(run.errors, []);
  assert.equal(run.result.status, 'NEEDS_HUMAN');
  assert.equal(run.calls.find((c) => c.key === 'discovery|SCAN').opts.agent, 'shipyard-discovery');
  await assert.rejects(runWorkflow('discover', { request: REQUEST, breadth: 0, shipyardDir: 'nowhere' }, {}, {}, { noInputs: true }), /args\.registry .* could not read/);
});

test('an agent result that passes the runtime subset but fails the full contract is retried, then BLOCKED', async () => {
  // couldNotInspect must be an array of strings: the runtime ignores nothing here, but the lib re-validates anyway.
  const bad = discovery('DRAFT', { couldNotInspect: 'not-a-list' });
  const run = await runWorkflow('discover', { request: REQUEST, breadth: 0 }, { 'discovery|DRAFT': [bad, bad] }, defaults());
  const fixtureErrors = run.errors.filter((e) => /fixture for discovery\|DRAFT/.test(e));
  assert.equal(fixtureErrors.length, 2, 'the harness rejects both attempts');
  assert.equal(run.result.status, 'BLOCKED');
  assert.match(run.result.reason, /discovery DRAFT/);
});

test('the elephant null after retry → BLOCKED before any goldfish runs', async () => {
  const run = await runDiscover({ breadth: 1 }, { 'discovery|ELEPHANT': [null, null] });
  assert.equal(run.result.status, 'BLOCKED');
  assert.match(run.result.reason, /ELEPHANT/);
  assert.equal(run.calls.filter((c) => c.key === 'goldfish|BRAINSTORM').length, 0);
});

test('breadth defaults to 1 when absent; an invalid breadth fails loudly', async () => {
  const run = await runDiscover({ breadth: undefined });
  assert.equal(run.calls.filter((c) => c.key === 'goldfish|BRAINSTORM').length, 3);
  for (const bad of ['1', 3, -1]) {
    await assert.rejects(runWorkflow('discover', { request: 'x', breadth: bad }, {}, {}), /breadth must be 0, 1 or 2/);
  }
});

test('every ctx.agent label is unique and every step key is unique', async () => {
  const run = await runDiscover({ breadth: 2 }, { 'goldfish|BRAINSTORM': [null] });
  assert.deepEqual(run.errors, []);
  const labels = run.calls.map((c) => c.opts.label);
  assert.equal(new Set(labels).size, labels.length);
  assert.ok(labels.some((l) => /\(retry 1\)$/.test(l)));
});

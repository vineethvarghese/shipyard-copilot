// Shipyard P9 (one slice) as a Copilot CLI dynamic workflow. Ported from Shipyard's workflows/slice.js: same args,
// same phases, same statuses, same caps, same routing, same dedupe, same briefs. The runtime helpers live in
// ../shipyard-lib/index.mjs. `ctx.pause` is used only for the SHARED-tier stop, and only when args.pauseForShared
// is true (a headless run cannot resume, so the default is to return NEEDS_SHARED_APPROVAL as Shipyard does).
import {
  defineWorkflow, attach, makeToolkit, routeSlice, dedupeSliceFindings, normaliseFindings, publicFinding,
  memberKey, keysOf, anyKey, markKeys,
} from '../shipyard-lib/index.mjs';

export const meta = {
  name: 'shipyard-slice',
  description: 'Run one approved Shipyard slice (P9): test plan first, code and tests in parallel, verify, routed review, capped fix rounds. Launched by the coordinator for one APPROVED slice after it has created and checked out the slice branch. Returns a slice-workflow-result: READY_FOR_HUMAN, NEEDS_SHARED_APPROVAL, ESCALATE, BLOCKED_REVIEWER or BLOCKED.',
  phases: [
    { title: 'Test plan', detail: 'verifier TEST_PLAN writes TEST_PLAN.md as DRAFT; code-review TEST_PLAN approves or asks for a revision (capped).' },
    { title: 'Build', detail: 'implementer IMPLEMENT (code touch set) and verifier WRITE_TESTS (test touch set) in parallel, both from SLICE.md and TEST_PLAN.md.' },
    { title: 'Verify', detail: 'verifier VERIFY commits tests, runs the canonical suite, scope check and LOCAL tiers, and reports routing facts.' },
    { title: 'Review', detail: 'Route reviewers from the registry and routing facts, run them in parallel on the raw diff, dedupe findings.' },
    { title: 'Fix', detail: 'implementer FIX and verifier FIX_TESTS on open findings (or the human\'s merge-gate change requests); rebuttals answered by the reporting reviewer in REBUTTAL mode; architect rules on architecture concerns and test disputes.' },
  ],
  argsSchema: {
    type: 'object',
    properties: {
      slice: { type: 'string', description: 'Two-digit slice id.' },
      featureBranch: { type: 'string' },
      sliceBranch: { type: 'string' },
      round: { type: 'integer', minimum: 0, description: 'Fix rounds already used; 0 on a fresh run.' },
      startAt: { type: 'string', enum: ['TEST_PLAN', 'VERIFY'], description: 'VERIFY resumes at Verify after a SHARED-tier decision.' },
      sharedApproved: { description: 'List of approved SHARED tier names, or a map tier -> true/false. Data only.' },
      humanChanges: { type: 'array', description: 'Merge-gate change requests [{id, owner implementer|verifier, finding, requiredResolution, location?}]; starts at Fix, outside the round cap.' },
      humanRound: { type: 'integer', minimum: 1, description: '1, 2, ... for successive change requests.' },
      pauseForShared: { type: 'boolean', description: 'Use ctx.pause for a SHARED-tier stop instead of returning NEEDS_SHARED_APPROVAL (interactive runs only).' },
      registry: { type: 'object', description: 'Parsed shipyard/registry/roles.json; read from disk when absent.' },
      contracts: { type: 'object', description: 'Contracts keyed by file stem; read from shipyard/contracts/ when absent.' },
      agentSelection: { type: 'string', enum: ['agent', 'prompt'], description: 'How the custom agent is selected per call (see shipyard-lib).' },
      shipyardDir: { type: 'string', description: 'Folder holding registry/ and contracts/ (default <repo>/shipyard).' },
    },
    required: ['slice', 'featureBranch', 'sliceBranch'],
  },
  limits: { maxConcurrentSubagents: 8, maxTotalSubagents: 120 },
};

const BUDGET = { TEST_PLAN: 40, IMPLEMENT: 80, WRITE_TESTS: 60, VERIFY: 40, FIX: 60, FIX_TESTS: 40, SLICE: 40, RECHECK: 25, REBUTTAL: 15, ADJUDICATE: 30 };

const AUTHOR_RULES =
  'Fix each finding below or rebut it ONCE with a citation (code, contract, ADR, SLICE.md or TEST_PLAN.md line) in `rebuttals`. ' +
  'List fixed finding ids in `fixed`. Stay inside your touch set. SLICE.md and TEST_PLAN.md are the source of truth, not the other author.';
const RULING_RULES =
  'These are the architect\'s rulings on concerns or test disputes raised this round. Carry out each one and list its id in `fixed`. ' +
  'They cannot be rebutted; if one is impossible inside your touch set, say why in architectureConcerns.';
const UNFINISHED_RULES =
  'You reported this work as unfinished (a stub, or an acceptance criterion not satisfied). Finish each item and list its id in `fixed`; ' +
  'if it cannot be finished inside your touch set, keep it in stubsRemaining or acNotSatisfied with the reason.';
const HUMAN_RULES =
  'These are the human\'s change requests from the merge gate. Make each change and list its id in `fixed`. They cannot be rebutted; ' +
  'if one cannot be done inside your touch set or would break SLICE.md, TEST_PLAN.md or INVARIANTS.md, say why in architectureConcerns.';
const rulesFor = (groups) => (groups.humanOnly ? HUMAN_RULES : groups.rulingsOnly ? RULING_RULES : groups.unfinishedOnly ? UNFINISHED_RULES : AUTHOR_RULES);

function verifyFailure(v) {
  const parts = [];
  if (v.build === 'FAIL') parts.push('build FAIL');
  if (v.unitTests && v.unitTests.status === 'FAIL') parts.push(`unit tests FAIL (${v.unitTests.failures} failing of ${v.unitTests.run})`);
  if (v.integrationTests === 'FAIL') parts.push('integration tests FAIL');
  for (const t of v.tiers || []) if (t.status === 'FAIL') parts.push(`tier ${t.name} (${t.environment}) FAIL: ${t.why}`);
  return parts.length ? { buildFailed: v.build === 'FAIL', text: parts.join('; ') } : null;
}

export async function run(ctx) {
  const T = makeToolkit(ctx, 'slice');
  const { A, REG, LIMITS, FIX_SCOPE, call, enter, step, log, parallel, json, shortName } = T;

  // ---------------------------------------------------------------------------------------------
  // Inputs
  // ---------------------------------------------------------------------------------------------
  const SLICE = A.slice == null ? '' : String(A.slice);
  const FB = A.featureBranch;
  const SB = A.sliceBranch;
  if (!SLICE) throw new Error('slice: args.slice is required');
  if (!FB || !SB) throw new Error('slice: args.featureBranch and args.sliceBranch are required');

  // sharedApproved accepts a list of approved tier names, or a map tier -> true (run it) / false (human said no).
  // It is data only: where the run starts is decided by startAt and humanChanges.
  const SHARED_DECISIONS = (() => {
    const raw = A.sharedApproved;
    if (Array.isArray(raw)) return raw.map((n) => [String(n), true]);
    if (raw && typeof raw === 'object') return Object.keys(raw).map((k) => [k, raw[k] === true]);
    return [];
  })();
  const SHARED_APPROVED = SHARED_DECISIONS.filter((d) => d[1]).map((d) => d[0]);
  const SHARED_DENIED = SHARED_DECISIONS.filter((d) => !d[1]).map((d) => d[0]);
  if (A.startAt != null && A.startAt !== 'VERIFY' && A.startAt !== 'TEST_PLAN') throw new Error(`slice: args.startAt must be "TEST_PLAN" or "VERIFY", got '${A.startAt}'`);
  const PAUSE_FOR_SHARED = A.pauseForShared === true && typeof ctx.pause === 'function';

  // humanChanges: the human's change requests from the merge gate. They become findings for the authors and
  // start the run at Fix; they do not count toward the fix-round cap, and review re-runs in full afterwards.
  const HUMAN_CHANGES = (Array.isArray(A.humanChanges) ? A.humanChanges : []).map((c, i) => {
    if (!c || typeof c !== 'object' || !c.finding) throw new Error(`slice: args.humanChanges[${i}] needs at least {owner, finding}`);
    if (c.owner !== 'implementer' && c.owner !== 'verifier') throw new Error(`slice: args.humanChanges[${i}].owner must be implementer or verifier (a change that alters acceptance criteria or the test plan goes back through SLICE.md and a fresh run)`);
    return {
      id: String(c.id || `human-${i + 1}`), severity: 'MAJOR', category: 'human-change', location: String(c.location || 'whole slice'),
      finding: String(c.finding), whyItMatters: 'Requested by the human at the merge gate.', evidence: 'Merge-gate decision recorded in DELIVERY_PLAN.md',
      requiredResolution: String(c.requiredResolution || c.finding), confidence: 'HIGH', owner: c.owner, reporters: ['human'], status: 'OPEN',
    };
  });
  const HUMAN_ROUND = Number.isInteger(A.humanRound) && A.humanRound > 0 ? A.humanRound : 1;
  const START = HUMAN_CHANGES.length ? 'HUMAN_CHANGES' : (A.startAt || 'TEST_PLAN');
  // Fix rounds already used count toward the cap, except in a human-change run, which gets a fresh cap.
  let round = HUMAN_CHANGES.length ? 0 : (Number.isInteger(A.round) && A.round >= 0 ? A.round : 0);
  const label = () => (HUMAN_CHANGES.length ? `human-${HUMAN_ROUND} round ${round}` : `round ${round}`);

  const DIR = `.ai/slices/${SLICE}`;
  const SLICE_MD = `${DIR}/SLICE.md`;
  const TEST_PLAN = `${DIR}/TEST_PLAN.md`;
  const INVARIANTS = '.ai/INVARIANTS.md';
  const ARCHITECTURE = '.ai/ARCHITECTURE.md';
  const BASE = { slice: SLICE, featureBranch: FB, sliceBranch: SB };
  const findingsFile = (roleName) => `${DIR}/findings/${shortName(roleName)}.md`;

  const humanInputRequests = [];
  const authorNotes = { architectureConcerns: [], testDisputes: [], rulings: [], outOfScopeNoticed: [], stubsRemaining: [], acNotSatisfied: [], build: {} };
  const latestAuthor = {}; // role -> latest author-result
  let lastReviewedCommit = null; // slice HEAD at the last completed review step
  const abilityVersions = {};
  const routedMap = {}; // role -> because (first time routed)
  let notRouted = [];
  let testPlan = null;
  let verify = null;
  let testPlanFindings = [];
  const byReviewer = {}; // role -> latest findings from that reviewer
  const ranOnce = {}; // role -> true once it ran in SLICE mode
  const rebuttedKeys = {}; // member key -> true once a rebuttal was accepted
  const rebuttalTried = {}; // member key -> true once rebutted (one rebuttal per finding)
  const overrides = {}; // member key -> {owner, requiredResolution} from architect adjudication

  function isOpen(f) {
    return f.status === 'OPEN' && FIX_SCOPE.indexOf(f.severity) !== -1;
  }

  function noteHuman(who, res) {
    if (res && res.humanInputRequested) humanInputRequests.push(Object.assign({ from: who }, res.humanInputRequested));
  }

  function mergeAbilities(res) {
    if (res && res.abilityVersions && typeof res.abilityVersions === 'object') {
      for (const k of Object.keys(res.abilityVersions)) abilityVersions[k] = res.abilityVersions[k];
    }
  }

  // Rebuttal and adjudication state applies to each original finding before dedupe, so a later finding from
  // another reviewer that lands in the same group is never swept up by an earlier rebuttal.
  function memberView(f) {
    const k = memberKey(f);
    const g = Object.assign({}, f);
    if (overrides[k]) Object.assign(g, overrides[k]);
    if (rebuttedKeys[k] && g.status === 'OPEN') g.status = 'REBUTTED';
    return g;
  }

  function currentFindings() {
    const all = [];
    for (const r of Object.keys(byReviewer)) for (const f of byReviewer[r]) all.push(memberView(f));
    return dedupeSliceFindings(all);
  }

  function noteAuthor(who, res) {
    if (!res) return;
    latestAuthor[who] = res;
    for (const c of res.architectureConcerns || []) authorNotes.architectureConcerns.push({ from: who, concern: c });
    for (const d of res.testDisputes || []) authorNotes.testDisputes.push(Object.assign({ from: who }, d));
    for (const o of res.outOfScopeNoticed || []) if (authorNotes.outOfScopeNoticed.indexOf(o) === -1) authorNotes.outOfScopeNoticed.push(o);
    authorNotes.build[who] = res.build;
  }

  function workItem(id, owner, category, text, resolution) {
    return {
      id, severity: 'MAJOR', category, location: 'whole slice', finding: text, whyItMatters: 'The slice is not done while the author reports unfinished work.',
      evidence: `${owner} return block`, requiredResolution: resolution, confidence: 'HIGH', owner, reporters: [owner], status: 'OPEN',
    };
  }

  // What the latest result of each author still reports as unfinished: the implementer's stubs and unmet ACs,
  // the verifier's ACs whose planned tests it could not write. Returns { text, items } where items are
  // finding-shaped work items owned by the author that reported them.
  function unfinishedWork() {
    const parts = [];
    const items = [];
    authorNotes.stubsRemaining = [];
    authorNotes.acNotSatisfied = [];
    for (const who of Object.keys(latestAuthor)) {
      const r = latestAuthor[who];
      (r.stubsRemaining || []).forEach((st, i) => {
        authorNotes.stubsRemaining.push({ from: who, stub: st });
        items.push(workItem(`${who}-stub-${i + 1}`, who, 'stub', String(st), 'Replace the stub with the real behaviour SLICE.md asks for.'));
      });
      (r.acNotSatisfied || []).forEach((ac, i) => {
        authorNotes.acNotSatisfied.push(Object.assign({ from: who }, ac));
        items.push(workItem(`${who}-ac-${i + 1}`, who, 'ac-not-satisfied', `${ac.ac}: ${ac.why}`, who === 'verifier' ? `Write the planned tests for ${ac.ac}.` : `Make the code satisfy ${ac.ac}.`));
      });
    }
    if (authorNotes.stubsRemaining.length) parts.push(`stubs remaining: ${authorNotes.stubsRemaining.map((x) => `${x.stub} (${x.from})`).join(', ')}`);
    if (authorNotes.acNotSatisfied.length) parts.push(`acceptance criteria not satisfied: ${authorNotes.acNotSatisfied.map((x) => `${x.ac} (${x.from}: ${x.why})`).join(', ')}`);
    return { text: parts.join('; '), items };
  }

  function finish(status, reason, extraOpen) {
    const findings = currentFindings();
    const openFindings = findings.filter(isOpen).concat(extraOpen || []);
    log(`slice ${SLICE}: ${status} — ${reason}`);
    return {
      slice: SLICE,
      status,
      rounds: round,
      reason,
      commit: verify && verify.commit ? verify.commit : null,
      verify,
      testPlan,
      reviewersRouted: Object.keys(routedMap).map((r) => ({ role: r, because: routedMap[r] })),
      reviewersNotRouted: notRouted.filter((n) => !routedMap[n.role]),
      findings: findings.concat(testPlanFindings).map(publicFinding),
      openFindings: openFindings.map(publicFinding),
      humanInputRequests,
      abilityVersions,
      authorNotes,
      humanChanges: HUMAN_CHANGES,
    };
  }

  // ---------------------------------------------------------------------------------------------
  // Step 1–2: test plan and its gate
  // ---------------------------------------------------------------------------------------------
  async function testPlanStep() {
    enter('Test plan');
    const maxRevisions = Number.isInteger(LIMITS.testPlanRevisions) ? LIMITS.testPlanRevisions : 2;
    let feedback = null;
    for (let revision = 0; ; revision++) {
      const text = revision === 0
        ? `Write ${TEST_PLAN} for slice ${SLICE}: first line the agent banner, then the line \`Status: DRAFT\`, then the AC → planned tests table, levels, failure and edge cases, benchmarks for performance ACs, ACs not verifiable here, and validation tiers (LOCAL or SHARED). Never write \`Status: APPROVED\`.`
        : `Revision ${revision} of at most ${maxRevisions}. Revise ${TEST_PLAN} to address the code-review findings below. Keep \`Status: DRAFT\`.\n\nFindings:\n${json(feedback)}`;
      const tp = await call('verifier', 'TEST_PLAN', Object.assign({}, BASE, {
        round, read: [SLICE_MD, INVARIANTS, ARCHITECTURE], write: TEST_PLAN, budgetTurns: BUDGET.TEST_PLAN, text,
      }), revision === 0 ? 'verifier TEST_PLAN' : `verifier TEST_PLAN revision ${revision}`);
      if (!tp) return finish('BLOCKED', 'verifier TEST_PLAN returned no valid result after retry');
      testPlan = tp;
      noteHuman('verifier', tp);

      const rv = await call('code-review', 'TEST_PLAN', Object.assign({}, BASE, {
        round, read: [SLICE_MD, TEST_PLAN, INVARIANTS, ARCHITECTURE],
        write: `${DIR}/findings/${shortName('code-review')}.test-plan.md`, budgetTurns: BUDGET.SLICE,
        text: 'Review the test plan against SLICE.md. Verdict APPROVE or REVISE. On APPROVE, and only then, edit TEST_PLAN.md with exactly old_string `Status: DRAFT` → new_string `Status: APPROVED` and nothing else, then read the file back and report the Status line you see in `extras.testPlanStatus`. On REVISE leave the status line alone and list what must change as findings (owner: verifier).',
      }), revision === 0 ? 'code-review TEST_PLAN' : `code-review TEST_PLAN revision ${revision}`);
      if (!rv) return finish('BLOCKED_REVIEWER', 'code-review TEST_PLAN returned no valid result after retry');
      noteHuman('code-review', rv);
      mergeAbilities(rv);
      const gate = await step(`test plan gate revision ${revision}`, () => ({
        verdict: rv.verdict, seen: rv.extras && rv.extras.testPlanStatus != null ? rv.extras.testPlanStatus : null,
      }));
      if (gate.verdict === 'APPROVE') {
        if (gate.seen !== 'APPROVED') {
          return finish('BLOCKED', `code-review approved the test plan but reports its Status line as '${gate.seen || 'not reported'}', not APPROVED (the status edit was refused or not made); nothing was built`);
        }
        testPlanFindings = [];
        log(`slice ${SLICE}: test plan APPROVED after ${revision} revision(s)`);
        return null;
      }
      testPlanFindings = normaliseFindings(rv.findings, 'code-review');
      if (revision >= maxRevisions) {
        return finish('ESCALATE', `test plan not approved after ${revision} revision(s) (cap ${maxRevisions})`,
          testPlanFindings.filter((f) => f.status === 'OPEN'));
      }
      feedback = rv.findings;
      log(`slice ${SLICE}: test plan REVISE (${revision + 1}/${maxRevisions})`);
    }
  }

  // ---------------------------------------------------------------------------------------------
  // Step 3: build in parallel
  // ---------------------------------------------------------------------------------------------
  async function buildStep() {
    enter('Build');
    const read = [SLICE_MD, TEST_PLAN, INVARIANTS, ARCHITECTURE];
    const [impl, tests] = await parallel([
      () => call('implementer', 'IMPLEMENT', Object.assign({}, BASE, {
        round, read, budgetTurns: BUDGET.IMPLEMENT,
        text: `Implement slice ${SLICE} from SLICE.md and the APPROVED TEST_PLAN.md. Write only paths in the code touch set; never tests, never .ai/. Do not wait for or read the verifier's new tests. At the end commit your code paths only as \`slice ${SLICE} ${label()}: code\`. Raise design problems in architectureConcerns and tests you believe are wrong in testDisputes; never work around them.`,
      }), 'implementer IMPLEMENT'),
      () => call('verifier', 'WRITE_TESTS', Object.assign({}, BASE, {
        round, read, budgetTurns: BUDGET.WRITE_TESTS,
        text: `Write the tests planned in the APPROVED TEST_PLAN.md for slice ${SLICE}. Write only paths in the test touch set; never production code. Derive tests from SLICE.md and TEST_PLAN.md, not from the implementation. Do not run git: VERIFY commits the tests.`,
      }), 'verifier WRITE_TESTS'),
    ]);
    noteHuman('implementer', impl);
    noteHuman('verifier', tests);
    if (!impl || !tests) {
      const who = [!impl ? 'implementer IMPLEMENT' : null, !tests ? 'verifier WRITE_TESTS' : null].filter(Boolean).join(' and ');
      return finish('BLOCKED', `${who} returned no valid result after retry`);
    }
    noteAuthor('implementer', impl);
    noteAuthor('verifier', tests);
    const esc = await authorEscalations({ implementer: impl, verifier: tests });
    return esc.stop || null;
  }

  // ---------------------------------------------------------------------------------------------
  // Fix helpers
  // ---------------------------------------------------------------------------------------------
  async function adjudicate(findings, why) {
    const res = await call('architect', 'ADJUDICATE', Object.assign({}, BASE, {
      round, diff: true, read: [SLICE_MD, TEST_PLAN, INVARIANTS, ARCHITECTURE],
      write: findingsFile('architect'), budgetTurns: BUDGET.ADJUDICATE,
      text: `${why}\nFor each finding: set owner to implementer or verifier with a concrete required resolution, mark it REBUTTED if it is wrong (with evidence), or return verdict ESCALATE if a human must decide. Return each finding you adjudicated in \`findings\` with its original id.\n\nFindings:\n${json(findings)}`,
    }), 'architect ADJUDICATE');
    noteHuman('architect', res);
    return res;
  }

  function applyAdjudication(res, findings) {
    const byId = {};
    for (const f of res.findings || []) byId[f.id] = f;
    for (const f of findings) {
      const a = byId[f.id];
      if (!a) continue;
      if (a.status === 'REBUTTED' || a.status === 'FIXED') {
        markKeys(rebuttedKeys, f, true);
      } else {
        markKeys(overrides, f, { owner: a.owner, requiredResolution: a.requiredResolution });
      }
    }
  }

  async function runAuthors(groups, failure) {
    const thunks = [];
    const who = [];
    const read = [SLICE_MD, TEST_PLAN, INVARIANTS, ARCHITECTURE];
    if (groups.implementer.length || failure) {
      who.push('implementer');
      const parts = [];
      if (failure) parts.push(`Verification failed: ${failure.text}\nFix the cause if it lies in your code paths.${failure.buildFailed ? '' : ' If a failing test itself is wrong (it contradicts SLICE.md or the approved TEST_PLAN.md), list it in testDisputes with a citation instead of working around it; the architect rules on it.'}`);
      if (groups.implementer.length) parts.push(`${rulesFor(groups)}\n\nFindings:\n${json(groups.implementer.map(publicFinding))}`);
      parts.push(`Commit your code paths only as \`slice ${SLICE} ${label()}: code\`.`);
      thunks.push(() => call('implementer', 'FIX', Object.assign({}, BASE, { round, diff: true, read, budgetTurns: BUDGET.FIX, text: parts.join('\n\n') }), `implementer FIX round ${round}`));
    }
    if (groups.verifier.length || (failure && !failure.buildFailed)) {
      who.push('verifier');
      const parts = [];
      if (failure && !failure.buildFailed) parts.push(`Verification failed: ${failure.text}\nFix the cause only if it lies in your test paths (a test that contradicts TEST_PLAN.md). Never weaken a test to make it pass.`);
      if (groups.verifier.length) parts.push(`${rulesFor(groups)}\n\nFindings:\n${json(groups.verifier.map(publicFinding))}`);
      parts.push('Do not run git: VERIFY commits the tests.');
      thunks.push(() => call('verifier', 'FIX_TESTS', Object.assign({}, BASE, { round, diff: true, read, budgetTurns: BUDGET.FIX_TESTS, text: parts.join('\n\n') }), `verifier FIX_TESTS round ${round}`));
    }
    const results = thunks.length ? await parallel(thunks) : [];
    const out = {};
    who.forEach((w, i) => {
      out[w] = results[i];
      noteHuman(w, results[i]);
      noteAuthor(w, results[i]);
    });
    return out;
  }

  // Architecture concerns and test disputes raised by the authors go to the architect, who rules on each one.
  // A ruling that names an owner goes straight back to that author in the same round. The architect can
  // escalate; a second wave of concerns in the same round escalates too (no ping-pong).
  async function authorEscalations(results) {
    const items = [];
    for (const who of Object.keys(results)) {
      const r = results[who];
      if (!r) continue;
      (r.architectureConcerns || []).forEach((c, i) => items.push({
        id: `${who}-concern-${round}-${i + 1}`, severity: 'MAJOR', category: 'architecture-concern', location: 'whole slice',
        finding: String(c), whyItMatters: `The ${who} says the approved design cannot be followed as written.`, evidence: `${who} return block, round ${round}`,
        requiredResolution: 'Architect ruling', confidence: 'MEDIUM', owner: 'architect', reporters: [who], status: 'OPEN',
      }));
      (r.testDisputes || []).forEach((d, i) => items.push({
        id: `${who}-dispute-${round}-${i + 1}`, severity: 'MAJOR', category: 'test-dispute', location: String(d.test),
        finding: String(d.reason), whyItMatters: 'Implementer and verifier disagree about what the slice requires.', evidence: String(d.citation),
        requiredResolution: 'Architect ruling: is the test or the code wrong?', confidence: 'MEDIUM', owner: 'architect', reporters: [who], status: 'OPEN',
      }));
    }
    if (!items.length) return { stop: null, results };
    const adj = await adjudicate(items, 'The authors raised these architecture concerns and test disputes. Rule on each one: set owner to implementer or verifier with a concrete requiredResolution (who changes what, citing SLICE.md, TEST_PLAN.md, INVARIANTS.md or an ADR), mark it REBUTTED with evidence if no change is needed, or return verdict ESCALATE if a human must decide (for example the approved plan or test plan is wrong).');
    if (!adj) return { stop: finish('BLOCKED', 'architect ADJUDICATE returned no valid result after retry') };
    if (adj.verdict === 'ESCALATE') return { stop: finish('ESCALATE', `architect escalated author concerns: ${items.map((x) => x.id).join(', ')}`) };
    const byId = {};
    for (const f of adj.findings || []) byId[f.id] = f;
    const rulings = { implementer: [], verifier: [] };
    for (const it of items) {
      const a = byId[it.id];
      if (!a) return { stop: finish('ESCALATE', `architect returned no ruling for ${it.id}`) };
      authorNotes.rulings.push({ id: it.id, owner: a.owner, status: a.status, requiredResolution: a.requiredResolution });
      if (a.status === 'OPEN' && (a.owner === 'implementer' || a.owner === 'verifier')) rulings[a.owner].push(Object.assign({}, it, { owner: a.owner, requiredResolution: a.requiredResolution, reporters: ['architect'] }));
      else if (a.status === 'OPEN') return { stop: finish('ESCALATE', `architect left ${it.id} with owner ${a.owner}`) };
    }
    if (!rulings.implementer.length && !rulings.verifier.length) return { stop: null, results };
    log(`slice ${SLICE}: architect rulings → implementer ${rulings.implementer.length}, verifier ${rulings.verifier.length}`);
    const follow = await runAuthors(Object.assign({ rulingsOnly: true }, rulings), null);
    const missing = Object.keys(follow).filter((w) => !follow[w]);
    if (missing.length) return { stop: finish('BLOCKED', `${missing.join(' and ')} returned no valid result after retry on the architect's ruling`) };
    const again = Object.keys(follow).filter((w) => (follow[w].architectureConcerns || []).length || (follow[w].testDisputes || []).length);
    if (again.length) return { stop: finish('ESCALATE', `${again.join(' and ')} still dispute the architect's ruling`) };
    const undone = rulings.implementer.concat(rulings.verifier).filter((x) => !((follow[x.owner] && follow[x.owner].fixed) || []).includes(x.id));
    if (undone.length) return { stop: finish('ESCALATE', `architect ruling(s) not carried out: ${undone.map((x) => x.id).join(', ')}`, undone) };
    // Keep what the authors said in their first pass (fixes, rebuttals of review findings) alongside the follow-up.
    const merged = Object.assign({}, results);
    for (const w of Object.keys(follow)) {
      const a = results[w];
      const b = follow[w];
      merged[w] = !a ? b : Object.assign({}, b, {
        fixed: (a.fixed || []).concat(b.fixed || []),
        rebuttals: (a.rebuttals || []).concat(b.rebuttals || []),
      });
    }
    return { stop: null, results: merged };
  }

  // Returns a finished result to stop with, or null to continue.
  async function answerRebuttals(authorResults) {
    const findings = currentFindings();
    const byAnyId = {};
    for (const f of findings) {
      byAnyId[f.id] = f;
      for (const k of keysOf(f)) {
        const id = k.slice(k.indexOf(':') + 1);
        if (!byAnyId[id]) byAnyId[id] = f;
      }
    }

    const asks = [];
    for (const author of Object.keys(authorResults)) {
      const res = authorResults[author];
      for (const rb of (res && res.rebuttals) || []) {
        const f = byAnyId[rb.findingId];
        if (!f || !isOpen(f)) continue;
        if (anyKey(rebuttalTried, f)) {
          log(`rebuttal of ${f.id} ignored: one rebuttal per finding; it stays OPEN`);
          continue;
        }
        markKeys(rebuttalTried, f, true);
        asks.push({ finding: f, rebuttal: rb, author });
      }
    }
    if (!asks.length) return null;

    const jobs = [];
    for (const ask of asks) {
      for (const reporter of ask.finding.reporters) {
        jobs.push({ ask, reporter });
      }
    }
    const answers = await parallel(jobs.map((j) => () => call(j.reporter, 'REBUTTAL', Object.assign({}, BASE, {
      round, diff: true, read: [SLICE_MD, TEST_PLAN], budgetTurns: BUDGET.REBUTTAL,
      text: `The ${j.ask.author} rebuts your finding ${j.ask.finding.id}. Answer ACCEPT_REBUTTAL or MAINTAIN_FINDING with a reason, judged on evidence only. Do not review anything else.\n\nFinding:\n${json(publicFinding(j.ask.finding))}\n\nRebuttal:\n${json(j.ask.rebuttal)}`,
    }), `${j.reporter} REBUTTAL ${j.ask.finding.id}`)));

    const missing = jobs.filter((j, i) => !answers[i]).map((j) => `${j.reporter} on ${j.ask.finding.id}`);
    if (missing.length) return finish('BLOCKED_REVIEWER', `no valid rebuttal response after retry: ${missing.join(', ')}`);

    for (const ask of asks) {
      const mine = jobs.map((j, i) => (j.ask === ask ? answers[i] : null)).filter(Boolean);
      const accepted = mine.every((a) => a.response === 'ACCEPT_REBUTTAL');
      if (accepted) {
        markKeys(rebuttedKeys, ask.finding, true);
        log(`rebuttal of ${ask.finding.id} accepted → REBUTTED`);
        continue;
      }
      log(`rebuttal of ${ask.finding.id} maintained → stays OPEN`);
      if (ask.finding.severity === 'BLOCKING' && /architect/i.test(String(ask.finding.category))) {
        const adj = await adjudicate([publicFinding(ask.finding)], `A maintained BLOCKING architecture finding. Rebuttal: ${json(ask.rebuttal)}\nReviewer answers: ${json(mine)}`);
        if (!adj) return finish('BLOCKED', 'architect ADJUDICATE returned no valid result after retry');
        if (adj.verdict === 'ESCALATE') return finish('ESCALATE', `architect escalated maintained finding ${ask.finding.id}`);
        applyAdjudication(adj, [ask.finding]);
      }
    }
    return null;
  }

  // Returns a finished result to stop with, or null to continue to VERIFY.
  async function fixRound(open, failure) {
    enter('Fix');
    log(`slice ${SLICE}: fix round ${round}${failure ? ` (verification: ${failure.text})` : ''}, ${open.length} open finding(s)`);

    const human = open.filter((f) => f.owner === 'human' || f.owner === 'planner');
    if (human.length) return finish('ESCALATE', `finding(s) need a human or planner decision: ${human.map((f) => f.id).join(', ')}`);

    const arch = open.filter((f) => f.owner === 'architect');
    if (arch.length) {
      const adj = await adjudicate(arch.map(publicFinding), 'These findings are owned by the architect. Adjudicate them before the authors fix anything.');
      if (!adj) return finish('BLOCKED', 'architect ADJUDICATE returned no valid result after retry');
      if (adj.verdict === 'ESCALATE') return finish('ESCALATE', `architect escalated: ${arch.map((f) => f.id).join(', ')}`);
      applyAdjudication(adj, arch);
      open = currentFindings().filter(isOpen);
      const still = open.filter((f) => f.owner === 'architect' || f.owner === 'human' || f.owner === 'planner');
      if (still.length) return finish('ESCALATE', `architect could not assign finding(s): ${still.map((f) => f.id).join(', ')}`);
    }

    const groups = await step(`fix groups round ${round}`, () => ({
      implementer: open.filter((f) => f.owner === 'implementer'),
      verifier: open.filter((f) => f.owner === 'verifier'),
    }));
    const results = await runAuthors(groups, failure);
    const missing = Object.keys(results).filter((w) => !results[w]);
    if (missing.length) return finish('BLOCKED', `${missing.join(' and ')} fix step returned no valid result after retry`);

    const esc = await authorEscalations(results);
    if (esc.stop) return esc.stop;
    return answerRebuttals(esc.results);
  }

  // The human's merge-gate change requests: one fix pass with those items only, outside the round cap.
  async function humanChangeStep() {
    enter('Fix');
    log(`slice ${SLICE}: applying ${HUMAN_CHANGES.length} human change request(s) (human round ${HUMAN_ROUND})`);
    const groups = {
      implementer: HUMAN_CHANGES.filter((f) => f.owner === 'implementer'),
      verifier: HUMAN_CHANGES.filter((f) => f.owner === 'verifier'),
      humanOnly: true,
    };
    const results = await runAuthors(groups, null);
    const missing = Object.keys(results).filter((w) => !results[w]);
    if (missing.length) return finish('BLOCKED', `${missing.join(' and ')} returned no valid result after retry on the human change requests`);
    const notDone = HUMAN_CHANGES.filter((c) => !((results[c.owner] && results[c.owner].fixed) || []).includes(c.id));
    if (notDone.length) return finish('ESCALATE', `human change request(s) not done: ${notDone.map((c) => c.id).join(', ')}`, notDone);
    const esc = await authorEscalations(results);
    return esc.stop || null;
  }

  // The SHARED-tier stop. With args.pauseForShared the run pauses at a durable checkpoint and, if the resume
  // hands back { sharedApproved }, continues at Verify in the same run. Otherwise the workflow ends with
  // NEEDS_SHARED_APPROVAL and the coordinator relaunches it with startAt VERIFY (Shipyard's behaviour).
  async function sharedPause(pending) {
    if (!PAUSE_FOR_SHARED) return false;
    let resumed = null;
    try {
      resumed = await ctx.pause(`shared-approval: ${pending.map((t) => t.name).join(', ')}`);
    } catch (e) {
      return false;
    }
    const raw = resumed && typeof resumed === 'object' ? resumed.sharedApproved : null;
    const decisions = Array.isArray(raw) ? raw.map((n) => [String(n), true]) : (raw && typeof raw === 'object' ? Object.keys(raw).map((k) => [k, raw[k] === true]) : []);
    if (!decisions.length) return false;
    for (const [tier, ok] of decisions) {
      const list = ok ? SHARED_APPROVED : SHARED_DENIED;
      if (list.indexOf(tier) === -1) list.push(tier);
    }
    log(`slice ${SLICE}: resumed after the SHARED-tier decision (approved: ${SHARED_APPROVED.join(', ') || 'none'}; denied: ${SHARED_DENIED.join(', ') || 'none'})`);
    return true;
  }

  // ---------------------------------------------------------------------------------------------
  // Review
  // ---------------------------------------------------------------------------------------------
  async function runReviewers(jobs, v) {
    if (!jobs.length) return null;
    const cap = LIMITS.findingsCapPerReviewer || 15;
    const drift = v.scopeCheck === 'DRIFT' ? `\nVERIFY reported scope DRIFT: ${(v.drift || []).join(', ')}` : '';
    const since = lastReviewedCommit ? `\nChanges since your last review: git diff ${lastReviewedCommit}..${SB}. Review those changes in your jurisdiction too, including code and tests changed for other reviewers' findings.` : '';
    const results = await parallel(jobs.map((j) => () => call(j.role, j.mode, Object.assign({}, BASE, {
      round, diff: true, read: [SLICE_MD, TEST_PLAN, INVARIANTS, ARCHITECTURE], write: findingsFile(j.role),
      budgetTurns: j.mode === 'RECHECK' ? BUDGET.RECHECK : BUDGET.SLICE,
      text: j.mode === 'SLICE'
        ? `Review the raw diff in your jurisdiction only. At most ${cap} findings, most serious first; every finding needs evidence and Status: OPEN. Owner: implementer for code paths and code actions, verifier for test paths and tests to add, remove or reshape, architect for architecture disputes, human only when a human decision is required.${drift}`
        : `Recheck your open findings against the new diff. Return your full current list: mark resolved findings FIXED, keep unresolved ones OPEN, add only new findings the changes introduced (at most ${cap}). Do not re-raise a rebutted finding.${since}${drift}\n\nYour open findings:\n${j.mine.length ? json(j.mine.map(publicFinding)) : 'none'}`,
    }), `${j.role} ${j.mode} round ${round}`)));

    const failed = jobs.filter((j, i) => !results[i]).map((j) => `${j.role} ${j.mode}`);
    if (failed.length) return finish('BLOCKED_REVIEWER', `reviewer returned no valid result after retry: ${failed.join(', ')}`);
    jobs.forEach((j, i) => {
      const res = results[i];
      const fresh = normaliseFindings(res.findings, j.role);
      // A recheck that leaves out an earlier finding does not make it disappear: fixed and rebutted findings stay
      // on the record, and an open one the reviewer forgot to list stays OPEN (fail closed).
      const ids = fresh.map((f) => f.id);
      const kept = j.mode === 'SLICE' ? [] : (byReviewer[j.role] || []).filter((f) => ids.indexOf(f.id) === -1);
      byReviewer[j.role] = fresh.concat(kept);
      if (j.mode === 'SLICE') ranOnce[j.role] = true;
      noteHuman(j.role, res);
      mergeAbilities(res);
    });
    return null;
  }

  // ---------------------------------------------------------------------------------------------
  // Main
  // ---------------------------------------------------------------------------------------------
  if (START === 'TEST_PLAN') {
    const stop = (await testPlanStep()) || (await buildStep());
    if (stop) return stop;
  } else if (START === 'HUMAN_CHANGES') {
    const stop = await humanChangeStep();
    if (stop) return stop;
  } else {
    log(`slice ${SLICE}: resuming at Verify (approved SHARED tiers: ${SHARED_APPROVED.join(', ') || 'none'})`);
  }

  const maxRounds = Number.isInteger(LIMITS.fixRounds) ? LIMITS.fixRounds : 3;
  for (;;) {
    // Step 4: verify
    enter('Verify');
    const v = await call('verifier', 'VERIFY', Object.assign({}, BASE, {
      round, read: [SLICE_MD, TEST_PLAN, INVARIANTS], budgetTurns: BUDGET.VERIFY,
      text: `First read the Status line of ${TEST_PLAN} and report it as testPlanStatus. Then commit your test paths as \`slice ${SLICE} ${label()}: tests\` (skip if nothing changed). Then run the canonical suite, the scope check against both touch sets in SLICE.md, and the planned LOCAL validation tiers. ` +
        `Never run a SHARED tier unless it is approved here; report it as AWAITING_APPROVAL. Approved SHARED tiers: ${SHARED_APPROVED.length ? SHARED_APPROVED.join(', ') : 'none'}. Denied SHARED tiers (report them NOT_RUN, reason: declined by the human): ${SHARED_DENIED.length ? SHARED_DENIED.join(', ') : 'none'}. ` +
        'Return routingFacts with a boolean and evidence for every flag, and the slice HEAD as commit.',
    }), `verifier VERIFY round ${round}`);
    if (!v) return finish('BLOCKED', 'verifier VERIFY returned no valid result after retry');
    verify = v;
    noteHuman('verifier', v);
    if (v.testPlanStatus !== 'APPROVED') {
      return finish('BLOCKED', `VERIFY reads ${TEST_PLAN} as '${v.testPlanStatus}', not APPROVED: test plan first. Re-run the slice from its test plan.`);
    }

    const pending = await step(`pending shared tiers round ${round}`, () => (v.tiers || []).filter((t) => t.environment === 'SHARED' && t.status === 'AWAITING_APPROVAL' && SHARED_APPROVED.indexOf(t.name) === -1 && SHARED_DENIED.indexOf(t.name) === -1));
    if (pending.length) {
      if (await sharedPause(pending)) continue;
      return finish('NEEDS_SHARED_APPROVAL', `SHARED tier(s) need human approval before they run: ${pending.map((t) => t.name).join(', ')}`);
    }

    const failure = await step(`verify failure round ${round}`, () => verifyFailure(v));
    if (failure) {
      log(`slice ${SLICE}: verification failed: ${failure.text}`);
      if (round >= maxRounds) return finish('ESCALATE', `verification still failing after ${round} fix round(s): ${failure.text}`);
      round += 1;
      const stop = await fixRound(currentFindings().filter(isOpen), failure);
      if (stop) return stop;
      continue;
    }

    // Step 5: route and review
    enter('Review');
    const { routed, skipped } = await step(`route reviewers round ${round}`, () => routeSlice(REG, v.routingFacts));
    for (const r of routed) if (!routedMap[r.role]) routedMap[r.role] = r.because;
    notRouted = skipped;

    const jobs = [];
    // Each reviewer rechecks its own original findings (its own ids), not a merged copy that may carry
    // another reviewer's id.
    for (const r of Object.keys(byReviewer)) {
      const mine = byReviewer[r].map(memberView).filter(isOpen);
      if (mine.length) jobs.push({ role: r, mode: 'RECHECK', mine });
    }
    // Code written in a fix round is always looked at again by the code reviewer, even when it had no open
    // findings: a fix made for another reviewer is still new code and new tests.
    if (lastReviewedCommit && ranOnce['code-review'] && !jobs.some((j) => j.role === 'code-review')) {
      jobs.push({ role: 'code-review', mode: 'RECHECK', mine: [] });
    }
    for (const r of routed) {
      if (!ranOnce[r.role] && !jobs.some((j) => j.role === r.role)) jobs.push({ role: r.role, mode: 'SLICE', mine: [] });
    }
    log(`slice ${SLICE}: round ${round} review: ${jobs.map((j) => `${j.role} ${j.mode}`).join(', ') || 'nothing to run'}; not routed: ${skipped.map((s) => s.role).join(', ') || 'none'}`);

    const failedRun = await runReviewers(jobs, v);
    if (failedRun) return failedRun;

    // A finding filed with category security pulls in the security reviewer if routing did not.
    const secHit = currentFindings().find((f) => /security/i.test(String(f.category)) && f.reporters.indexOf('security-review') === -1);
    if (secHit && !ranOnce['security-review'] && REG.roles['security-review']) {
      routedMap['security-review'] = `finding ${secHit.id} from ${secHit.reporters.join(', ')} has category ${secHit.category}`;
      log(`slice ${SLICE}: security-review routed by finding ${secHit.id}`);
      const failedSec = await runReviewers([{ role: 'security-review', mode: 'SLICE', mine: [] }], v);
      if (failedSec) return failedSec;
    }
    lastReviewedCommit = v.commit;

    // Step 6–7: dedupe and decide
    const open = await step(`open findings round ${round}`, () => currentFindings().filter(isOpen));
    if (!open.length) {
      const unfinished = unfinishedWork();
      if (!unfinished.text) return finish('READY_FOR_HUMAN', `clean after ${round} fix round(s); no open finding in ${FIX_SCOPE.join('/')}`);
      if (round >= maxRounds) return finish('ESCALATE', `reviews are clean but the authors still report unfinished work after ${round} fix round(s): ${unfinished.text}`, unfinished.items);
      round += 1;
      log(`slice ${SLICE}: reviews clean but unfinished work reported; fix round ${round}: ${unfinished.text}`);
      enter('Fix');
      const res = await runAuthors({
        implementer: unfinished.items.filter((x) => x.owner === 'implementer'),
        verifier: unfinished.items.filter((x) => x.owner === 'verifier'),
        unfinishedOnly: true,
      }, null);
      const miss = Object.keys(res).filter((w) => !res[w]);
      if (miss.length) return finish('BLOCKED', `${miss.join(' and ')} returned no valid result after retry on unfinished work`);
      const esc = await authorEscalations(res);
      if (esc.stop) return esc.stop;
      continue;
    }
    if (round >= maxRounds) return finish('ESCALATE', `${open.length} finding(s) still open after ${round} fix round(s) (cap ${maxRounds})`);
    round += 1;
    const stop = await fixRound(open, null);
    if (stop) return stop;
  }
}

export const workflow = defineWorkflow({ meta, run });
export default workflow;
await attach(workflow);

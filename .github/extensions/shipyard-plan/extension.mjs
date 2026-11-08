// Shipyard P5-P7 as a Copilot CLI dynamic workflow. Ported from Shipyard's workflows/plan.js: same args, same
// phases, same statuses, same caps, same routing, same briefs. The runtime helpers live in ../shipyard-lib.
import {
  defineWorkflow, attach, makeToolkit, FORMAL_TIERS, routePlan, dedupePlanFindings, normaliseFindings,
} from '../shipyard-lib/index.mjs';

export const meta = {
  name: 'shipyard-plan',
  description: 'Shipyard P5-P7: routed plan critique, capped refinement, delivery planning with sequencing checks and one cold readiness goldfish per slice. Launched by the coordinator after the P4 grill is closed. Returns AWAITING_PLAN_APPROVAL, NEEDS_HUMAN (back to P4) or BLOCKED.',
  phases: [
    { title: 'Critique', detail: 'routed plan reviewers in parallel on the raw planning artifacts (architect and simplicity always).' },
    { title: 'Refine', detail: 'architect updates the artifacts for open findings; only reviewers with open findings recheck; capped cycles.' },
    { title: 'Delivery plan', detail: 'planner slices the work with seams under test and prior art per slice; integration and architect check sequencing; one readiness goldfish per SLICE.md; one replan.' },
  ],
  argsSchema: {
    type: 'object',
    properties: {
      planFlags: { type: 'object', description: 'publicContract, consumerVisible, concurrency, security, config, modelChecked: absent or non-boolean = uncertain = route.' },
      cycle: { type: 'integer', minimum: 0, description: 'Refine cycles already used by earlier launches; 0 on the first.' },
      answers: { description: 'The P4 answers (string or object).' },
      formalRigour: { type: 'string', enum: ['none', 'invariants', 'properties', 'model-checked'], description: 'C-10 formal rigour (default none).' },
      registry: { type: 'object', description: 'Parsed shipyard/registry/roles.json; read from disk when absent.' },
      contracts: { type: 'object', description: 'Contracts keyed by file stem; read from shipyard/contracts/ when absent.' },
      agentSelection: { type: 'string', enum: ['agent', 'prompt'], description: 'How the custom agent is selected per call (see shipyard-lib).' },
      shipyardDir: { type: 'string', description: 'Folder holding registry/ and contracts/ (default <repo>/shipyard).' },
    },
    required: [],
  },
  limits: { maxConcurrentSubagents: 8, maxTotalSubagents: 60 },
};

const BUDGET = { PLAN: 40, RECHECK: 25, DRAFT: 40, CRITIQUE: 30, PLANNER: 60, READINESS: 15 };
const PLANNING_READ = ['.ai/PROJECT.md', '.ai/GLOSSARY.md', '.ai/ARCHITECTURE.md', '.ai/INVARIANTS.md', '.ai/CONSUMERS.md', '.ai/planning/discovery.md', '.ai/planning/concepts.md', '.ai/planning/open-questions.md', '.ai/decisions/*.md'];
const DELIVERY_PLAN = '.ai/DELIVERY_PLAN.md';

export async function run(ctx) {
  const T = makeToolkit(ctx, 'plan');
  const { A, REG, LIMITS, FIX_SCOPE, call, enter, step, log, parallel, json, role, shortName } = T;

  // ---------------------------------------------------------------------------------------------
  // Inputs and state
  // ---------------------------------------------------------------------------------------------
  const FLAGS = A.planFlags && typeof A.planFlags === 'object' ? A.planFlags : {};
  // Refine cycles already used by earlier launches of this workflow (0 on the first launch). The cap
  // (registry.limits.planRefineCycles) counts across launches, so a relaunch after NEEDS_HUMAN gets only what is left.
  const CYCLE = Number.isInteger(A.cycle) && A.cycle >= 0 ? A.cycle : 0;
  let cyclesUsed = CYCLE; // returned so the coordinator relaunches with the right count
  const ANSWERS = A.answers == null ? null : (typeof A.answers === 'string' ? A.answers : json(A.answers));
  const FORMAL = A.formalRigour == null ? 'none' : A.formalRigour;
  if (FORMAL_TIERS.indexOf(FORMAL) === -1) throw new Error(`plan: args.formalRigour must be one of ${FORMAL_TIERS.join(', ')}, got '${A.formalRigour}'`);
  const CAP = LIMITS.findingsCapPerReviewer || 15;

  const byReviewer = {};
  const humanInputRequests = [];
  let routedList = [];
  let notRoutedList = [];
  let slices = [];
  let readiness = [];

  function noteHuman(who, res) {
    if (res && res.humanInputRequested) humanInputRequests.push(Object.assign({ from: who }, res.humanInputRequested));
  }

  function isOpen(f) {
    return f.status === 'OPEN' && FIX_SCOPE.indexOf(f.severity) !== -1;
  }

  function currentFindings() {
    const all = [];
    for (const r of Object.keys(byReviewer)) for (const f of byReviewer[r]) all.push(f);
    return dedupePlanFindings(all);
  }

  function done(status, reason, extra) {
    log(`plan: ${status} — ${reason}`);
    return Object.assign({
      status, slices, readiness, findings: currentFindings(), humanInputRequests, reason, cyclesUsed,
      reviewersRouted: routedList, reviewersNotRouted: notRoutedList,
    }, extra || {});
  }

  // Plan reviewers use Mode PLAN; a role without a PLAN mode (the architect) critiques with CRITIQUE.
  function planMode(roleName, wanted) {
    const modes = role(roleName).modes || {};
    if (modes[wanted]) return wanted;
    if (modes.CRITIQUE) return 'CRITIQUE';
    throw new Error(`plan: role '${roleName}' has neither mode ${wanted} nor CRITIQUE`);
  }

  function reviewBrief(roleName, mode, mine, extraText) {
    const answers = ANSWERS ? `\n\nHuman answers recorded at P4 (cycle ${CYCLE}):\n${ANSWERS}` : '';
    const formal = `\n\nFormal rigour (C-10): ${FORMAL}.` + (roleName === 'reliability-review' && FORMAL === 'model-checked'
      ? ' Run every model under .ai/formal/ with scripts/formal_check.py (the planted fault must fail; a model that cannot fail is a finding); render any counterexample trace as a plain-English scenario and step table in your findings file.'
      : '');
    const text = mode === 'RECHECK' || (mode === 'CRITIQUE' && mine)
      ? `Recheck your open findings against the updated planning artifacts. Return your full current list: mark resolved findings FIXED, keep unresolved ones OPEN, add only new findings the update introduced (at most ${CAP}).${extraText || ''}\n\nYour open findings:\n${json(mine || [])}`
      : `Critique the plan in your jurisdiction only. At most ${CAP} findings, most serious first; every finding needs evidence and Status: OPEN. Request human input only for a decision the artifacts cannot settle.${extraText || ''}${answers}${formal}`;
    return { round: null, read: PLANNING_READ, write: `.ai/planning/${shortName(roleName)}.md`, budgetTurns: mode === 'RECHECK' ? BUDGET.RECHECK : BUDGET.PLAN, text };
  }

  async function runReviewers(jobs, tag) {
    const results = await parallel(jobs.map((j) => () => call(j.role, j.mode, reviewBrief(j.role, j.mode, j.mine, j.extra), `${j.role} ${j.mode}`)));
    const failed = jobs.filter((j, i) => !results[i]).map((j) => `${j.role} ${j.mode}`);
    if (failed.length) return `no valid result after retry: ${failed.join(', ')}`;
    jobs.forEach((j, i) => {
      const fresh = normaliseFindings(results[i].findings, j.role);
      // A recheck that leaves out an earlier finding does not make it disappear: an open finding the reviewer
      // forgot to list stays OPEN (fail closed), and closed ones stay on the record. The architect rechecks in
      // CRITIQUE mode (it has no RECHECK mode), so a recheck is any job that carries `mine`.
      const ids = fresh.map((f) => f.id);
      const isRecheck = j.mode === 'RECHECK' || Array.isArray(j.mine);
      const kept = isRecheck ? (byReviewer[j.role] || []).filter((f) => ids.indexOf(f.id) === -1) : [];
      byReviewer[j.role] = fresh.concat(kept);
      noteHuman(j.role, results[i]);
    });
    await step(`findings after ${tag}`, () => currentFindings());
    return null;
  }

  function recheckJobs(roles, extra) {
    const open = currentFindings().filter(isOpen);
    const jobs = [];
    for (const r of roles) {
      const mine = open.filter((f) => f.reporters.indexOf(r) !== -1);
      if (mine.length) jobs.push({ role: r, mode: planMode(r, 'RECHECK'), mine, extra });
    }
    return jobs;
  }

  // ---------------------------------------------------------------------------------------------
  // P5 Critique
  // ---------------------------------------------------------------------------------------------
  enter('Critique');
  const routing = await step('route plan reviewers', () => routePlan(REG, FLAGS));
  routedList = routing.routed;
  notRoutedList = routing.notRouted;
  const reviewers = routedList.map((r) => r.role);
  log(`plan: cycle ${CYCLE}; routed ${reviewers.join(', ')}; not routed ${notRoutedList.map((n) => n.role).join(', ') || 'none'}`);
  const err = await runReviewers(reviewers.map((r) => ({ role: r, mode: planMode(r, 'PLAN') })), 'critique');
  if (err) return done('BLOCKED', `plan critique: ${err}`);

  // ---------------------------------------------------------------------------------------------
  // P6 Refine
  // ---------------------------------------------------------------------------------------------
  const maxCycles = Number.isInteger(LIMITS.planRefineCycles) ? LIMITS.planRefineCycles : 2;
  for (let cycle = CYCLE; ; cycle++) {
    if (humanInputRequests.length) return done('NEEDS_HUMAN', `${humanInputRequests.length} human input request(s) from plan review`);
    const open = currentFindings().filter(isOpen);
    if (!open.length) break;
    if (cycle >= maxCycles) return done('NEEDS_HUMAN', `${open.length} plan finding(s) still open after ${cycle} refine cycle(s)`, { openFindings: open });
    enter('Refine');
    cyclesUsed = cycle + 1;
    log(`plan: refine cycle ${cycle + 1}/${maxCycles}, ${open.length} open finding(s)`);
    const upd = await call('architect', 'DRAFT', {
      read: PLANNING_READ, write: ['.ai/ARCHITECTURE.md', '.ai/INVARIANTS.md', '.ai/planning/architect.md'], budgetTurns: BUDGET.DRAFT,
      text: `Update the planning artifacts to resolve the open plan findings below. Where a finding is wrong, say why with evidence in .ai/planning/architect.md instead of changing the plan. Request human input for any decision that changes scope.\n\nOpen findings:\n${json(open)}`,
    }, `architect DRAFT refine ${cycle + 1}`);
    if (!upd) return done('BLOCKED', 'architect DRAFT (refine) returned no valid result after retry');
    noteHuman('architect', upd);
    if (humanInputRequests.length) return done('NEEDS_HUMAN', 'architect requested human input while refining the plan');
    const e2 = await runReviewers(recheckJobs(Object.keys(byReviewer)), `refine ${cycle + 1}`);
    if (e2) return done('BLOCKED', `plan recheck: ${e2}`);
  }

  // ---------------------------------------------------------------------------------------------
  // P7 Delivery planning
  // ---------------------------------------------------------------------------------------------
  enter('Delivery plan');
  const plan = await call('planner', 'PLAN', {
    read: PLANNING_READ, write: [DELIVERY_PLAN, '.ai/slices/*/SLICE.md', '.ai/planning/planner.md'], budgetTurns: BUDGET.PLANNER,
    text: `Cut the work into thin vertical slices, each independently mergeable into the feature branch. Use two-digit sequential slice ids 01..NN and write each spec to .ai/slices/<NN>/SLICE.md with objective, acceptance criteria, "## Expected touch set — code", "## Expected touch set — tests", "## Branch", "## Seams under test" (the public interface each AC is observed through: existing seam preferred, highest possible, ideally one) and "## Prior art" (similar tests already in the repository). Under "## Architecture constraints" list each invariant the slice must preserve with its C-10 tier. Use the glossary's terms. Return the slice count in \`slices\`.\n\nFormal rigour (C-10): ${FORMAL}.`,
  }, 'planner PLAN');
  if (!plan) return done('BLOCKED', 'planner PLAN returned no valid result after retry');
  noteHuman('planner', plan);
  if (plan.humanInputRequested || plan.verdict === 'UNDERSPECIFIED') return done('NEEDS_HUMAN', `planner verdict ${plan.verdict}${plan.humanInputRequested ? ' with a human input request' : ''}`);
  if (!plan.slices || plan.slices < 1) return done('BLOCKED', 'planner returned zero slices');

  const ids = (n) => Array.from({ length: n }, (_, i) => String(i + 1).padStart(2, '0'));
  slices = await step('slice ids', () => ids(plan.slices));
  const deliveryRead = [DELIVERY_PLAN, '.ai/ARCHITECTURE.md', '.ai/INVARIANTS.md'].concat(slices.map((s) => `.ai/slices/${s}/SLICE.md`));

  const readinessCall = (s) => call('goldfish', 'READINESS', {
    read: [`.ai/slices/${s}/SLICE.md`], budgetTurns: BUDGET.READINESS,
    text: `Lens: readiness\n\nRead .ai/slices/${s}/SLICE.md cold. Could a first-time implementer ship this without asking anything? Check that "## Seams under test" names at least one seam that either exists in the repository or is specified precisely as planned (its interface, and the slice that introduces it, which must be this slice or a prerequisite). Answer READY or NOT_READY; for NOT_READY list the exact questions they would have to ask.`,
  }, `goldfish READINESS ${s}`);

  const sequencingJobs = [
    { role: 'integration-review', mode: 'PLAN', text: 'Sequencing and mergeability only: can each slice merge into the feature branch on its own, in this order, without breaking consumers?' },
    { role: 'architect', mode: 'CRITIQUE', text: 'Intermediate states only: does the feature branch satisfy every invariant after each slice merges, in this order?' },
  ];
  const seqThunks = sequencingJobs.map((j) => () => call(j.role, j.mode, {
    read: deliveryRead, write: `.ai/planning/${shortName(j.role)}.md`, budgetTurns: BUDGET.CRITIQUE,
    text: `${j.text} At most ${CAP} findings, each with evidence and Status: OPEN.`,
  }, `${j.role} ${j.mode} delivery`));
  const all = await parallel(seqThunks.concat(slices.map((s) => () => readinessCall(s))));
  const seq = all.slice(0, sequencingJobs.length);
  const ready = all.slice(sequencingJobs.length);
  const failed = sequencingJobs.filter((j, i) => !seq[i]).map((j) => j.role).concat(slices.filter((s, i) => !ready[i]).map((s) => `goldfish READINESS ${s}`));
  if (failed.length) return done('BLOCKED', `delivery checks returned no valid result after retry: ${failed.join(', ')}`);

  const deliveryFindings = {};
  sequencingJobs.forEach((j, i) => {
    deliveryFindings[j.role] = normaliseFindings(seq[i].findings, j.role);
    noteHuman(j.role, seq[i]);
  });
  readiness = slices.map((s, i) => ({ slice: s, readiness: ready[i].readiness, questions: ready[i].questions || [] }));
  if (humanInputRequests.length) return done('NEEDS_HUMAN', 'human input requested during delivery checks');

  const openSeq = () => dedupePlanFindings(Object.keys(deliveryFindings).reduce((acc, r) => acc.concat(deliveryFindings[r]), [])).filter(isOpen);
  const verdict = await step('delivery verdict', () => ({
    notReady: readiness.filter((r) => r.readiness === 'NOT_READY'),
    seqOpen: openSeq(),
  }));
  const notReady = verdict.notReady;
  let seqOpen = verdict.seqOpen;

  if (notReady.length || seqOpen.length) {
    log(`plan: replan once for ${notReady.length} NOT_READY slice(s) and ${seqOpen.length} sequencing finding(s)`);
    const re = await call('planner', 'REPLAN', {
      read: deliveryRead, write: [DELIVERY_PLAN, '.ai/slices/*/SLICE.md', '.ai/planning/planner.md'], budgetTurns: BUDGET.PLANNER,
      text: `Revise the delivery plan once. Answer every readiness question inside the SLICE.md it concerns, and resolve the sequencing findings. Keep two-digit sequential slice ids.\n\nReadiness questions:\n${json(notReady)}\n\nSequencing findings:\n${json(seqOpen)}`,
    }, 'planner REPLAN');
    if (!re) return done('BLOCKED', 'planner REPLAN returned no valid result after retry');
    noteHuman('planner', re);
    if (re.humanInputRequested || re.verdict === 'UNDERSPECIFIED') return done('NEEDS_HUMAN', 'planner needs human input to replan');
    const before = slices.length;
    if (re.slices && re.slices >= 1) slices = ids(re.slices);
    const recheck = await step('replan recheck set', () => notReady.map((r) => r.slice).filter((s) => slices.indexOf(s) !== -1).concat(slices.slice(before)));
    const reSeq = sequencingJobs.filter((j) => seqOpen.some((f) => f.reporters.indexOf(j.role) !== -1));
    const reDeliveryRead = [DELIVERY_PLAN, '.ai/ARCHITECTURE.md', '.ai/INVARIANTS.md'].concat(slices.map((s) => `.ai/slices/${s}/SLICE.md`));
    const thunks = reSeq.map((j) => () => call(j.role, j.mode, {
      read: reDeliveryRead, write: `.ai/planning/${shortName(j.role)}.md`, budgetTurns: BUDGET.RECHECK,
      text: `${j.text} Recheck your open findings after the replan; return your full current list (FIXED or OPEN).\n\nYour open findings:\n${json(seqOpen.filter((f) => f.reporters.indexOf(j.role) !== -1))}`,
    }, `${j.role} ${j.mode} delivery recheck`)).concat(recheck.map((s) => () => readinessCall(s)));
    const res2 = await parallel(thunks);
    const seq2 = res2.slice(0, reSeq.length);
    const ready2 = res2.slice(reSeq.length);
    const failed2 = reSeq.filter((j, i) => !seq2[i]).map((j) => j.role).concat(recheck.filter((s, i) => !ready2[i]).map((s) => `goldfish READINESS ${s}`));
    if (failed2.length) return done('BLOCKED', `delivery rechecks returned no valid result after retry: ${failed2.join(', ')}`);
    reSeq.forEach((j, i) => {
      deliveryFindings[j.role] = normaliseFindings(seq2[i].findings, j.role);
      noteHuman(j.role, seq2[i]);
    });
    const latest = {};
    for (const r of readiness) latest[r.slice] = r;
    recheck.forEach((s, i) => {
      latest[s] = { slice: s, readiness: ready2[i].readiness, questions: ready2[i].questions || [] };
    });
    readiness = slices.map((s) => latest[s] || { slice: s, readiness: 'NOT_APPLICABLE', questions: [] });
    seqOpen = openSeq();
  }

  for (const r of Object.keys(deliveryFindings)) byReviewer[`${r}:delivery`] = deliveryFindings[r];
  const stillNotReady = readiness.filter((r) => r.readiness === 'NOT_READY');
  if (humanInputRequests.length || stillNotReady.length || seqOpen.length) {
    for (const r of stillNotReady) for (const q of r.questions) humanInputRequests.push({ from: `goldfish READINESS ${r.slice}`, question: q, evidence: `.ai/slices/${r.slice}/SLICE.md`, recommendation: '', blocked: `slice ${r.slice}` });
    return done('NEEDS_HUMAN', `after one replan: ${stillNotReady.length} slice(s) NOT_READY, ${seqOpen.length} sequencing finding(s) open`, { openFindings: seqOpen });
  }
  return done('AWAITING_PLAN_APPROVAL', `${slices.length} slice(s) planned, all READY, no open sequencing findings`);
}

export const workflow = defineWorkflow({ meta, run });
export default workflow;
await attach(workflow);

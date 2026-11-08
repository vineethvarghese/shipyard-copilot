// Shipyard P1-P3 as a Copilot CLI dynamic workflow. Ported from Shipyard's workflows/discover.js: same args,
// same phases, same statuses, same briefs. The runtime helpers live in ../shipyard-lib/index.mjs.
import { defineWorkflow, attach, makeToolkit, FORMAL_TIERS } from '../shipyard-lib/index.mjs';

export const meta = {
  name: 'shipyard-discover',
  description: 'Shipyard P1-P3: scan the repository, run the elephant/goldfish brainstorm, draft the planning artifacts and the P4 questions. Launched by the coordinator after the P0 gate. Returns NEEDS_HUMAN with concepts, the gap tree (kind, dependsOn) and the first grill round for the P4 gate, or BLOCKED with a reason.',
  phases: [
    { title: 'Scan', detail: 'discovery SCAN records repository facts; with a brainstorm, discovery ELEPHANT (deep compute) then seals the elephant take in concepts.md.' },
    { title: 'Brainstorm', detail: 'one goldfish per lens in parallel (verbatim request + lens only), an outsider sweep at breadth 2, then discovery SYNTHESIZE.' },
    { title: 'Draft', detail: 'discovery DRAFT (PROJECT.md body, user stories, GLOSSARY.md seed), architect DRAFT (invariants at the C-10 tier), then discovery QUESTIONS: the gap tree and the first grill round for P4.' },
  ],
  argsSchema: {
    type: 'object',
    properties: {
      request: { type: 'string', description: 'The verbatim request.' },
      breadth: { type: 'integer', enum: [0, 1, 2], description: 'Brainstorm breadth: 0 none, 1 three lenses (default), 2 five lenses plus an outsider sweep.' },
      constraints: { description: 'C-1..C-10 text (string) or an object.' },
      formalRigour: { type: 'string', enum: ['none', 'invariants', 'properties', 'model-checked'], description: 'C-10 formal rigour (default none).' },
      registry: { type: 'object', description: 'Parsed shipyard/registry/roles.json; read from disk when absent.' },
      contracts: { type: 'object', description: 'Contracts keyed by file stem; read from shipyard/contracts/ when absent.' },
      agentSelection: { type: 'string', enum: ['agent', 'prompt'], description: 'How the custom agent is selected per call (see shipyard-lib).' },
      shipyardDir: { type: 'string', description: 'Folder holding registry/ and contracts/ (default <repo>/shipyard).' },
    },
    required: ['request'],
  },
  limits: { maxConcurrentSubagents: 6, maxTotalSubagents: 24 },
};

const BUDGET = { SCAN: 40, ELEPHANT: 15, BRAINSTORM: 20, SYNTHESIZE: 30, DRAFT: 40, QUESTIONS: 20 };
const DISCOVERY_MD = '.ai/planning/discovery.md';
const CONCEPTS_MD = '.ai/planning/concepts.md';

export async function run(ctx) {
  const T = makeToolkit(ctx, 'discover');
  const { A, call, enter, step, log, parallel, json, role } = T;

  // ---------------------------------------------------------------------------------------------
  // Inputs
  // ---------------------------------------------------------------------------------------------
  const REQUEST = typeof A.request === 'string' ? A.request : '';
  if (!REQUEST.trim()) throw new Error('discover: args.request (the verbatim request) is required');
  // Brainstorm breadth: 0 (none), 1 (default: three lenses) or 2 (five lenses plus an outsider sweep).
  if (A.breadth != null && A.breadth !== 0 && A.breadth !== 1 && A.breadth !== 2) throw new Error(`discover: args.breadth must be 0, 1 or 2, got '${A.breadth}'`);
  const BREADTH = A.breadth == null ? 1 : A.breadth;
  const CONSTRAINTS = typeof A.constraints === 'string' ? A.constraints : json(A.constraints || {});
  // C-10 formal rigour: none (default), invariants, properties or model-checked.
  const FORMAL = A.formalRigour == null ? 'none' : A.formalRigour;
  if (FORMAL_TIERS.indexOf(FORMAL) === -1) throw new Error(`discover: args.formalRigour must be one of ${FORMAL_TIERS.join(', ')}, got '${A.formalRigour}'`);

  const artifacts = [];
  const humanInputRequests = [];

  function collect(who, res) {
    if (!res) return;
    for (const p of res.artifactsWritten || []) if (artifacts.indexOf(p) === -1) artifacts.push(p);
    if (res.humanInputRequested) humanInputRequests.push(Object.assign({ from: who }, res.humanInputRequested));
  }

  function blocked(reason, extra) {
    log(`discover: BLOCKED — ${reason}`);
    return Object.assign({ status: 'BLOCKED', topConcepts: [], gaps: [], questions: humanInputRequests.slice(), artifacts, reason }, extra || {});
  }

  function goldfishBrief(lens, extraText) {
    // ONLY the verbatim request and the lens: no constraints, no discovery notes, no elephant take.
    return {
      budgetTurns: BUDGET.BRAINSTORM,
      text: `Lens: ${lens}\n\nRequest (verbatim):\n${REQUEST}${extraText ? `\n\n${extraText}` : ''}`,
    };
  }

  // ---------------------------------------------------------------------------------------------
  // P1 Scan
  // ---------------------------------------------------------------------------------------------
  enter('Scan');
  const scan = await call('discovery', 'SCAN', {
    read: ['.ai/PROJECT.md', '.ai/state.json'], write: DISCOVERY_MD, budgetTurns: BUDGET.SCAN,
    text: `Scan the repository and record facts with assumption labels in ${DISCOVERY_MD}: build and test commands (run them when cheap), conventions, consumers, validation tiers (LOCAL or SHARED), and the key terms the code already uses.` +
      (FORMAL !== 'none' ? ` Formal rigour (C-10) is ${FORMAL}: also record under "## Validation tiers" whether formal tooling is present (quint, java, tla2tools), version and absence included; never install anything.` : '') +
      (BREADTH > 0
        ? ' Do not write concepts.md: a separate deep call writes the sealed elephant take next.'
        : ' Brainstorm breadth is 0: no goldfish will run, so do not write concepts.md.') +
      `\n\nRequest (verbatim):\n${REQUEST}\n\nDelivery constraints (P0):\n${CONSTRAINTS}\n\nBrainstorm breadth: ${BREADTH}`,
  }, 'discovery SCAN');
  if (!scan) return blocked('discovery SCAN returned no valid result after retry');
  collect('discovery', scan);

  if (BREADTH > 0) {
    // The sealed take is the elephant's half of the main signal (elephant vs goldfish disagreement), so it runs at
    // DEEP compute, separately from the high-volume STANDARD scan, and before any goldfish exists.
    const elephant = await call('discovery', 'ELEPHANT', {
      read: [DISCOVERY_MD, '.ai/PROJECT.md'], write: CONCEPTS_MD, budgetTurns: BUDGET.ELEPHANT,
      text: `Write your sealed elephant take on the request into ${CONCEPTS_MD} under "## Elephant take (sealed)": your own best concept from full context, written before any goldfish runs. Never edit that section later.\n\nRequest (verbatim):\n${REQUEST}\n\nDelivery constraints (P0):\n${CONSTRAINTS}`,
    }, 'discovery ELEPHANT');
    if (!elephant) return blocked('discovery ELEPHANT returned no valid result after retry');
    collect('discovery', elephant);
  }

  // ---------------------------------------------------------------------------------------------
  // P2 Brainstorm & narrow
  // ---------------------------------------------------------------------------------------------
  let synth = null;
  if (BREADTH > 0) {
    enter('Brainstorm');
    const lenses = await step('lenses', () => ((role('goldfish').lenses || {})[String(BREADTH)]) || []);
    if (!lenses.length) return blocked(`registry has no goldfish lenses for breadth ${BREADTH}`);
    log(`discover: ${lenses.length} goldfish: ${lenses.join(', ')}`);
    const wave = await parallel(lenses.map((lens) => () => call('goldfish', 'BRAINSTORM', goldfishBrief(lens), `goldfish BRAINSTORM ${lens}`)));
    const missing = lenses.filter((l, i) => !wave[i]);
    if (missing.length) return blocked(`goldfish returned no valid result after retry for lens(es): ${missing.join(', ')}`);
    const outputs = lenses.map((lens, i) => Object.assign({}, wave[i], { lens }));

    if (BREADTH === 2) {
      const titles = await step('cluster titles', () => {
        const t = [];
        for (const o of outputs) for (const c of o.concepts || []) if (t.indexOf(c.title) === -1) t.push(c.title);
        return t;
      });
      const outsider = await call('goldfish', 'BRAINSTORM', goldfishBrief('outsider',
        `Concept clusters already proposed (titles only):\n${titles.map((t) => `- ${t}`).join('\n') || '- (none)'}\n\nPropose concepts that fall OUTSIDE all of these clusters, including "much smaller or nothing".`),
      'goldfish BRAINSTORM outsider');
      if (!outsider) return blocked('outsider goldfish returned no valid result after retry');
      outputs.push(Object.assign({}, outsider, { lens: 'outsider' }));
    }

    synth = await call('discovery', 'SYNTHESIZE', {
      read: [DISCOVERY_MD, CONCEPTS_MD, '.ai/PROJECT.md'], write: CONCEPTS_MD, budgetTurns: BUDGET.SYNTHESIZE,
      text: `Cluster and rank the goldfish concepts below against the delivery constraints and the repository facts. Flag every goldfish-vs-elephant disagreement; do not average them away. Keep the sealed elephant take unchanged. Write the concepts brief (clusters, top 3, disagreements, open questions) and then the gap list G1..Gn into ${CONCEPTS_MD}.\n\nDelivery constraints (P0):\n${CONSTRAINTS}\n\nGoldfish outputs (JSON):\n${json(outputs)}`,
    }, 'discovery SYNTHESIZE');
    if (!synth) return blocked('discovery SYNTHESIZE returned no valid result after retry');
    collect('discovery', synth);
  }

  // ---------------------------------------------------------------------------------------------
  // P3 Draft
  // ---------------------------------------------------------------------------------------------
  enter('Draft');
  const draft = await call('discovery', 'DRAFT', {
    read: [DISCOVERY_MD].concat(BREADTH > 0 ? [CONCEPTS_MD] : []).concat(['.ai/PROJECT.md']),
    write: ['.ai/PROJECT.md', '.ai/CONSUMERS.md', '.ai/GLOSSARY.md', '.ai/planning/assumptions.md', '.ai/planning/open-questions.md'],
    budgetTurns: BUDGET.DRAFT,
    text: `Draft the planning artifacts for the request from the repository facts${BREADTH > 0 ? ' and the concepts brief' : ''}: the PROJECT.md body including numbered "## User stories" from the requester's perspective, CONSUMERS.md, assumptions, open questions, and seed .ai/GLOSSARY.md with the project-specific terms the request and the code use (one or two sentences each, an "Avoid" list where the code uses two words for one thing). Do not pick a concept for the human; mark choices that depend on the P4 answers as UNRESOLVED.${BREADTH > 0 ? '' : ` No brainstorm ran: write the gap list G1..Gn into ${CONCEPTS_MD}.`}\n\nRequest (verbatim):\n${REQUEST}\n\nDelivery constraints (P0):\n${CONSTRAINTS}`,
  }, 'discovery DRAFT');
  if (!draft) return blocked('discovery DRAFT returned no valid result after retry');
  collect('discovery', draft);

  const arch = await call('architect', 'DRAFT', {
    read: ['.ai/PROJECT.md', DISCOVERY_MD, '.ai/CONSUMERS.md', '.ai/GLOSSARY.md'].concat(BREADTH > 0 ? [CONCEPTS_MD] : []),
    write: ['.ai/ARCHITECTURE.md', '.ai/INVARIANTS.md'].concat(FORMAL === 'model-checked' ? ['.ai/formal/*.qnt'] : []), budgetTurns: BUDGET.DRAFT,
    text: `Draft the current and target architecture and the invariants every slice must preserve, using the glossary's terms. Challenge each new abstraction. Mark design choices that wait on the P4 answers as UNRESOLVED.\n\nFormal rigour (C-10): ${FORMAL}.` +
      (FORMAL === 'none' ? '' : ' Write every invariant in the extended block (plain English, why it matters, satisfied by, violated by, check, status, tags) and add a state-by-event table plus a Mermaid stateDiagram-v2 for anything stateful.') +
      (FORMAL === 'properties' || FORMAL === 'model-checked' ? ' Mark each invariant a property test or runtime assertion can check with "Check: property".' : '') +
      (FORMAL === 'model-checked' ? ' For invariants tagged concurrency, lifecycle or partial-failure, write a small model to .ai/formal/INV-nnn.qnt with one to three invariants and a planted fault that must fail; never install tooling.' : ''),
  }, 'architect DRAFT');
  if (!arch) return blocked('architect DRAFT returned no valid result after retry');
  if (arch.humanInputRequested) humanInputRequests.push(Object.assign({ from: 'architect' }, arch.humanInputRequested));
  if (arch.decisionRecord && artifacts.indexOf(arch.decisionRecord) === -1) artifacts.push(arch.decisionRecord);
  for (const p of ['.ai/ARCHITECTURE.md', '.ai/INVARIANTS.md']) if (artifacts.indexOf(p) === -1) artifacts.push(p);

  const questions = await call('discovery', 'QUESTIONS', {
    read: ['.ai/PROJECT.md', '.ai/ARCHITECTURE.md', '.ai/INVARIANTS.md', DISCOVERY_MD].concat([CONCEPTS_MD]),
    write: '.ai/planning/open-questions.md', budgetTurns: BUDGET.QUESTIONS,
    text: 'Draft the P4 grill for the human as a question tree: the concept pick (when a brainstorm ran) and every gap that changes the plan, each with kind (concept, scope, term, decision, invariant or fact), dependsOn (the gap ids it waits on), why it matters, evidence, options and a recommendation worded so that "yes" accepts it. Fold the questions the goldfish raised in as leaves. Settle every fact question from the repository yourself and mark it SETTLED; never leave one for the human. Return the frontier: the open gaps with no unanswered dependency, highest leverage first. Name the highest-leverage question.',
  }, 'discovery QUESTIONS');
  if (!questions) return blocked('discovery QUESTIONS returned no valid result after retry');
  collect('discovery', questions);

  // The question list and the first grill round are deterministic: journaled so a resume replays them.
  const grill = await step('grill round 1', () => {
    const gaps = (questions.gaps && questions.gaps.length ? questions.gaps : (synth && synth.gaps) || []);
    const topConcepts = (synth && synth.topConcepts) || [];
    const qList = gaps.map((g) => ({
      id: g.id, question: g.question, options: g.options, recommendation: g.recommendation, blocking: g.blocking,
      kind: g.kind || 'decision', dependsOn: Array.isArray(g.dependsOn) ? g.dependsOn : [], status: g.status || 'OPEN',
    }));
    if (questions.highestLeverageQuestion && !qList.some((q) => q.question === questions.highestLeverageQuestion)) {
      qList.unshift({ id: 'HL', question: questions.highestLeverageQuestion, options: [], recommendation: '', blocking: true, kind: 'decision', dependsOn: [], status: 'OPEN' });
    }
    for (const h of humanInputRequests) qList.push({ id: `HIR-${h.from}`, question: h.question, options: [], recommendation: h.recommendation, blocking: true, kind: 'decision', dependsOn: [], status: 'OPEN' });
    // The first grill round: every open question whose dependencies are all resolved. A dependency counts as
    // resolved when it is ANSWERED, SETTLED from evidence, or DEFERRED (the human took its default; the default is
    // ASSUMED but it still unblocks what hangs off it). Discovery's own ordering wins where it is eligible; the
    // supplemental questions (highest-leverage, humanInputRequested) are merged in so none is skipped. The
    // coordinator caps the round at registry.limits.grillQuestionsPerRound and recomputes later rounds with GRILL.
    const resolved = (id) => qList.some((q) => q.id === id && (q.status === 'ANSWERED' || q.status === 'SETTLED' || q.status === 'DEFERRED'));
    const eligible = qList.filter((q) => q.status === 'OPEN' && q.dependsOn.every(resolved)).map((q) => q.id);
    const proposed = Array.isArray(questions.frontier) ? questions.frontier.filter((id) => eligible.indexOf(id) !== -1) : [];
    const frontier = proposed.concat(eligible.filter((id) => proposed.indexOf(id) === -1));
    return { gaps, topConcepts, qList, frontier };
  });

  log(`discover: ${grill.topConcepts.length} top concept(s), ${grill.gaps.length} gap(s), ${grill.qList.length} question(s), ${grill.frontier.length} in the first grill round`);
  return {
    status: 'NEEDS_HUMAN',
    topConcepts: grill.topConcepts,
    gaps: grill.gaps,
    questions: grill.qList,
    frontier: grill.frontier,
    formalRigour: FORMAL,
    artifacts,
    disagreements: (synth && synth.disagreements) || [],
    reason: `P4 grill ready (breadth ${BREADTH}, ${grill.frontier.length} question(s) in round 1); the human picks a concept and answers rounds until the frontier is empty`,
  };
}

export const workflow = defineWorkflow({ meta, run });
export default workflow;
await attach(workflow);

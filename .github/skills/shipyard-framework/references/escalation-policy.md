# Escalation policy

The goal is the highest ratio of valuable human decisions to human attention spent. Escalating too much is as much a
failure as escalating too little — a human who is asked to adjudicate variable naming will stop reading the
escalations that matter.

This policy is deliberately short. It fixes the few cases where there is no discretion and leaves everything else to
the coordinator's judgment, because a category list can never anticipate every decision and an agent following one
stops thinking about the human it is supposed to protect.

## One channel to the human

The coordinator is the **only** agent that talks to the human (hard rule 9). A specialist that needs human input does
not ask; it returns a `humanInputRequested` object in its return block (every contract has one; `null` when there is
nothing):

```json
{
  "question": "<one decision, stated so it can be answered>",
  "evidence": "<paths, line ranges, command output>",
  "recommendation": "<the answer you would choose, and why>",
  "blocked": "<what cannot proceed without an answer, or \"nothing\">"
}
```

Inside a dynamic workflow these collect into the result's `humanInputRequests` (slice) or the workflow's human
questions (discover, plan). The workflow cannot pause for input, so it returns and the coordinator decides.

The coordinator adjudicates every request: it escalates it, settles it from evidence, routes it to the architect
(`ADJUDICATE`), or declines it and records why. A request is input to that judgment, not an obligation to interrupt
the human.

## The coordinator MUST escalate

No discretion. These go to the human even when the coordinator is confident of the answer:

- the P0 delivery parameters (C-1..C-10 and brainstorm breadth), the P4 grill (the concept pick, every round's
  frontier of plan-changing gaps, and the shared-understanding checklist), P8 plan approval, and every slice merge;
- any change a consumer outside the system can observe: public contract, wire or persisted data format, externally
  visible behaviour, or a compatibility break;
- anything irreversible or materially expensive: a new dependency or platform choice, or a rollout with real
  operational risk;
- a conflict between requirements, or between a requirement and an explicit human decision;
- a test plan still not approved after 2 revisions (`ESCALATE` from the `shipyard-slice` workflow);
- a slice whose findings are still open after 3 fix rounds (`ESCALATE`), or a maintained `BLOCKING` the architect
  could not resolve from approved sources;
- running any validation tier marked `SHARED` (any environment other people or services use), each time, even if
  the approved plan lists it (`NEEDS_SHARED_APPROVAL`). Planned is not the same as approved to run now;
- proceeding without a routed review that failed to run (`BLOCKED_REVIEWER`);
- running a role below its minimum compute class, or spending past C-9 (`compute-policy.md`);
- any fail-closed stop the coordinator cannot clear from evidence (`BLOCKED`).

## The coordinator MUST NOT escalate

- anything the repository, a command under 60 seconds (or the narrowest slower command), an accepted ADR, or an
  earlier human decision can settle — go and settle it;
- anything whose premise has not been verified (`verification-policy.md`);
- a lone question while related questions are pending — batch them;
- a disagreement between agents that the architect can settle from approved sources.

## Everything else: the coordinator's judgment

Ask one question: **would the human be surprised, or unhappy, to learn this was decided without them?** If yes,
escalate. If no, decide — using the architect for design questions, which it resolves from approved sources — and
record the outcome in `.ai/decisions/` with the reasoning, so the human can audit what was decided on their behalf.
A decision made without the human that was not recorded is indistinguishable from one that was never considered.

The coordinator's discretion covers *whether the human's attention is needed*. It does not extend to technical
truth: the coordinator never declares a reviewer's finding wrong or a disagreement settled. Those go to the
architect or the human.

## Escalation format

Never hand the human raw agent arguments or an unresolved transcript. Present a decision:

```text
Decision needed:

Why this decision exists:

Evidence:

Option A:
  Pros:
  Cons:

Option B:
  Pros:
  Cons:

Additional options, if meaningful:

Agent recommendation:            <and why>

Consequence of deferring:        <what stalls, what gets riskier>
```

A recommendation is mandatory. "Here are three options, you pick" wastes the leverage the agents were supposed to
provide. If evidence genuinely does not favour one option, say that explicitly and say what evidence would settle
it.

When a fail-closed stop is being reported, also set `Status: BLOCKED` with a one-line `Blocked reason:` in
`PROJECT.md` and `state.json` (`shipyard_state.py set-status BLOCKED`) before asking, so a resumed session sees it.

## Batching and rounds

Group related questions into one turn and order them by leverage — the answer to the first often makes later ones
moot. Ask the whole **frontier** per round (every question whose prerequisites are settled, capped at
`registry.limits.grillQuestionsPerRound`), never one question per turn; one-at-a-time trickling is the interaction
pattern this framework exists to remove. A question that depends on an unanswered one belongs to a later round, not
to this one: asking it now forces the human to answer twice. A question the human can answer only by looking at the
same code an agent could have read is a failure of discovery.

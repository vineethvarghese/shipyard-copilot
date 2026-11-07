---
name: domain-design
description: >
  Proportional domain-modelling review method for Shipyard. The code-reviewer loads it in SLICE and RECHECK mode to
  check that new code speaks the project's language and keeps business rules where they belong; the architect
  loads it in DRAFT and CRITIQUE mode to judge domain boundaries in a plan. Covers ubiquitous language against
  .ai/GLOSSARY.md (the terms the human settled in the P4 grill), bounded contexts, entities versus value objects, aggregates that guard the rules in
  INVARIANTS.md, domain logic leaking into controllers or infrastructure, anti-corruption layers for external
  models, and the anemic-model smell. Tactical patterns only where domain complexity warrants them. Not for
  general readability (code-clarity) or whether a layer should exist at all (simplicity-review).
---

# Domain design

Version 1.0.1 · used by code-review (`shipyard-code-reviewer`), architect (`shipyard-architect`, DRAFT and CRITIQUE)

Code is easiest to change when its names and boundaries match how the people who own the problem talk about it, and
when each business rule lives in one place that cannot be bypassed. Your job is to find where this change breaks
that, and to say what it costs. You are **not** here to install a pattern catalogue.

The ideas below paraphrase Eric Evans, *Domain-Driven Design* (ubiquitous language, bounded contexts, the building
blocks of a model, aggregates, and the anti-corruption layer). Cite the book by topic when it helps; repository
evidence always outranks a citation.

## Proportionality rules (read first)

1. **Match the weight of the model to the weight of the domain.** Simple create-read-update-delete over a table with
   no rules is fine as plain data plus a thin handler. Never demand repositories, factories, domain events,
   aggregates or value objects for it.
2. **Tactical patterns only where complexity warrants.** A pattern earns a finding only when you can name the rule,
   invariant or recurring change it would protect.
3. **DDD purity alone is never `BLOCKING`.** A domain finding is `BLOCKING` only when it lets an invariant in
   `.ai/INVARIANTS.md` be violated (then the defect is the finding: name the sequence that violates it).
4. **Follow the repository.** If the codebase has an established, simpler style, a slice that follows it is not a
   finding. Changing the house style is an architect decision, not a slice review comment.

## How to review

1. Read `.ai/GLOSSARY.md` (the project's terms, each with an `Avoid:` list, settled with the human in the P4
   grill), `.ai/INVARIANTS.md`, and the domain parts of `.ai/ARCHITECTURE.md`. If there is no glossary, fall back
   to `.ai/PROJECT.md` → `Key terminology`; if neither exists, say so in a `NOTE` and judge names against the
   requirement text.
2. Read `SLICE.md` ACs, then the diff.
3. For each check below, collect evidence before you write anything.

## Checks

Category is `domain/<check-id>`.

### ubiquitous-language
- **Look for:** new types, fields, methods or API names that use a different word than the glossary (`Coupon`
  where the glossary says `Voucher`; a word on a term's `Avoid:` list), one word used for two concepts, or
  technical words standing in for a domain concept (`StatusFlag2`).
- **Evidence:** the name in the diff and the term (with line) in `GLOSSARY.md` or the requirement.
- **Severity:** `MINOR`; `MAJOR` when the mismatch is in a public contract or persisted schema (hard to rename later).

### bounded-context
- **Look for:** one model stretched across two areas that mean different things by the same word (an `Account` that
  is both a login identity and a ledger account), or a module reaching into another context's internals.
- **Evidence:** the two meanings, with the code locations that rely on each.
- **Severity:** `MAJOR` when the change merges two meanings into one type; otherwise `MINOR`. Changes to context
  boundaries are the architect's call: say so.

### entity-vs-value
- **Look for:** things with identity and a lifecycle treated as interchangeable values, or plain values (money,
  date ranges, addresses, quantities with units) given ids and mutable setters, or passed around as bare primitives
  that lose their unit or validation.
- **Evidence:** the type and how it is compared, copied or mutated; the bug it invites (adding cents to dollars,
  comparing by reference).
- **Severity:** `MINOR`; `MAJOR` when the primitive form has already caused inconsistent handling in two places.

### aggregate-invariant
- **Look for:** a rule from `.ai/INVARIANTS.md` (or an AC) that can be broken because state is changed from outside
  the object that should guard it: fields set directly by a controller, collections exposed for mutation, two
  writes that must succeed together done separately.
- **Evidence:** the invariant (quote its id), the code path that bypasses it, and the concrete sequence that ends in
  an invalid state.
- **Severity:** `BLOCKING` when the sequence is reachable in this change and the invariant is approved; `MAJOR` when
  it is reachable only by a future caller using an exposed mutator.

### logic-placement
- **Look for:** business rules (pricing, eligibility, state transitions) written in controllers, request handlers,
  SQL strings, message consumers or UI code, especially when the same rule appears in two of them.
- **Evidence:** the rule, where it lives, and the other place that needs or duplicates it.
- **Severity:** `MINOR`; `MAJOR` when the rule is duplicated or must be kept in sync across entry points.

### anti-corruption
- **Look for:** an external system's model (a third-party API payload, another team's schema, a legacy table) used
  directly in core domain code, so its names, nulls and quirks spread inward.
- **Evidence:** the external type and the core locations that now depend on it.
- **Severity:** `MINOR`; `MAJOR` when the external model reaches persisted domain state or several modules. The
  fix is a small translation at the boundary, not a framework.

### anemic-model
- **Look for:** only where behaviour clearly belongs with data: a type whose fields are always validated, computed or
  transitioned by the same external helper in several places.
- **Evidence:** the type and at least two call sites repeating the same logic.
- **Severity:** `MINOR`. Never raise it for data-transfer objects, simple records, or CRUD with no rules.

## Severity calibration

- `BLOCKING`: an approved invariant can be violated by a reachable sequence in this change. Nothing else.
- `MAJOR`: a recurring, concrete cost: wrong names in public or persisted contracts, a rule duplicated across entry
  points, two meanings merged in one type.
- `MINOR`: local mismatch: one misnamed internal type, one rule in a controller with no duplicate yet.
- `NOTE`: pattern suggestions with no current cost, pre-existing modelling issues.

## Finding examples

GOOD (invariant cited, reachable sequence, minimum fix):

```text
ID: code-003
Severity: BLOCKING
Category: domain/aggregate-invariant
Location: src/main/java/shop/web/OrderController.java:58-71
Finding: applyVoucher in the controller subtracts the voucher value from order.total directly, bypassing Order,
  so the INV-004 rule "an order total is never negative" is not enforced.
Why it matters: A 20.00 voucher on a 15.00 order stores a total of -5.00, which the refund job then pays out.
Evidence: OrderController.java:66 `order.setTotal(order.getTotal().subtract(voucher.getValue()))`; INVARIANTS.md
  INV-004; Order.java exposes a public setTotal with no check.
Required resolution: Move the rule into Order.applyVoucher(voucher), clamp at zero as INV-004 requires, and make
  setTotal non-public.
Confidence: HIGH
Owner: implementer
Status: OPEN
```

BAD (ceremony demanded for simple CRUD, no cost, inflated):

```text
ID: code-010
Severity: BLOCKING
Category: domain
Location: app/tags/routes.py
Finding: Tags are not modelled as an aggregate with a repository and factory, which violates DDD.
Why it matters: Domain-driven design requires rich models.
Evidence: No TagRepository class exists.
Required resolution: Add Tag aggregate root, TagRepository interface and TagFactory.
Confidence: MEDIUM
Owner: implementer
Status: OPEN
```

What is wrong with it: tags are plain CRUD with no rules; no invariant, duplicated rule or cost is named; DDD purity
is never `BLOCKING`; and the resolution adds three constructs with no requirement behind them.

## Out of jurisdiction

- Whether a new layer, repository or interface should exist at all → simplicity-review.
- General naming and readability outside domain terms → `code-clarity`.
- Public API shape and compatibility of renamed fields → contract-review.
- Changing a bounded context or component ownership → the architect (raise it; do not decide it in a slice review).

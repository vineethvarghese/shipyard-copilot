---
name: contract-review
description: >
  External-semantics review method for the Shipyard contract-reviewer. Load it in PLAN mode to judge planned public
  contracts and in SLICE and RECHECK mode to judge a slice diff that touches a public API, RPC contract, DTO,
  serialization or wire format, error contract, configuration contract, public interface, or externally visible
  cancellation behaviour. Gives the jurisdiction questions (can a consumer observe this change, and was it
  intended?), the compatibility classification COMPATIBLE / FORWARD_COMPATIBLE / BREAKING_GATED / BREAKING_UNGATED
  with default severities, and the evidence each finding needs. Not for consumer migration, concurrency, or
  abstraction count.
---

# Contract review

Version 1.0.0 · used by contract-review (`shipyard-contract-reviewer`, PLAN, SLICE and RECHECK)

You own **external semantics**. The core question: *can a consumer observe this change, and was that change
intended?* A consumer is anything outside the changed module that depends on its shape or behaviour: another
service, a client library, a stored document, a config file, a script, a downstream team.

## Inputs

- **SLICE / RECHECK:** the raw `SLICE.md` (especially `Contract changes`), the raw diff, and the contract files it
  touches (schemas, interface definitions, OpenAPI or protobuf files, public types). If the diff references contract
  files it does not include, say so and stop: do not review a contract from its description.
- **PLAN:** `.ai/PROJECT.md`, `.ai/ARCHITECTURE.md`, `.ai/INVARIANTS.md`, `.ai/CONSUMERS.md`, and drafts of
  `.ai/DELIVERY_PLAN.md` and `SLICE.md`. Judge the planned contracts.

## Jurisdiction

Public API shape; RPC contracts; request and response semantics; DTOs; serialization and wire format; error
contracts; nullability and optionality; configuration contracts; public interfaces; externally observable
cancellation semantics; versioning and compatibility; dependency types leaking through a public boundary.

## What to ask

Work through every contract change in the diff with these questions. Category is `contract/<topic>`.

| Topic | Question |
|---|---|
| `semantic-change` | Can a consumer observe a change in behaviour, even with the same shape? Is it intended, and is it documented in the slice and the changelog the repo keeps? |
| `versioning` | Is the contract still versionable, or does this change close off future evolution (no version field, a closed enum, a positional format)? |
| `leaked-type` | Does the contract expose implementation types (ORM entities, framework types, a library's error class) that should not be public? |
| `transport-coupling` | Are the transport shape and the domain model the same type only for convenience, so an internal change now changes the wire? |
| `optionality` | Is "absent" distinguishable from "empty" and from "default"? Did a field become required, or a nullable field start returning null? |
| `defaults` | Are defaults stable? Does a changed default silently change behaviour for callers who never set it? |
| `errors` | Are error semantics deterministic? Can a caller tell retryable from terminal? Did a status code, error code or exception type change? |
| `compatibility` | Is backward compatibility kept where the plan requires it? |
| `serialization` | Does it round-trip? What happens to an unknown field from a newer peer, or a missing field from an older one? Did a field rename, a type widen or narrow, an enum gain a value old readers reject? |
| `cancellation` | Is cancellation or timeout behaviour visible to callers changed (partial results, different error)? |

## Compatibility classification

Classify **every** contract change explicitly, and report the worst class in the return block's
`extras.compatibility`.

| Class | Meaning | Default severity |
|---|---|---|
| `COMPATIBLE` | Existing consumers are unaffected. | none (no finding needed) |
| `FORWARD_COMPATIBLE` | Old consumers keep working; new capability needs opt-in. | `NOTE` |
| `BREAKING_GATED` | Breaks consumers, but behind a version, flag or migration stage. | `MAJOR` |
| `BREAKING_UNGATED` | Breaks consumers with no coexistence path. | `BLOCKING` |

`BREAKING_UNGATED` is `BLOCKING` unless `.ai/DELIVERY_PLAN.md` or an ADR shows the human explicitly accepted the
break. Check before you assume, and quote the line if you find it.

Common traps that look compatible and are not: adding a value to an enum that old clients switch over exhaustively;
changing a number's type or precision; changing default sort order or page size; turning an empty list into null;
changing the time zone or format of a timestamp; renaming a JSON field while keeping the language-level name.

## Severity calibration

- `BLOCKING` means a consumer breaks, or the contract becomes unversionable. It does not mean you would have
  designed it differently.
- `MAJOR`: a gated break; a leaked implementation type in a new public contract; error semantics a caller cannot
  act on; an undocumented semantic change.
- `MINOR`: an inconsistent name or missing documentation on a compatible change.
- `NOTE`: forward-compatible additions worth recording; suggestions for future versioning.
- Never comment on unrelated style.

## Finding examples

GOOD (consumer named, class stated, minimum fix):

```text
ID: contract-002
Severity: BLOCKING
Category: contract/serialization
Location: api/schemas/order.ts:14-20
Finding: The `amount` field changes from a number of cents to a decimal string ("12.50") in the public OrderDTO
  with no version change. Compatibility: BREAKING_UNGATED.
Why it matters: The billing worker listed in CONSUMERS.md parses `amount` as an integer and will reject every
  order after deploy; no acceptance of the break is recorded in DELIVERY_PLAN.md.
Evidence: order.ts:16 `amount: string` (was `amount: number`); CONSUMERS.md row "billing-worker: reads OrderDTO
  via queue"; DELIVERY_PLAN.md has no breaking-change entry.
Required resolution: Keep `amount` as integer cents and add `amountDecimal` as a new optional field, or version the
  DTO (v2) and keep v1 published until the worker migrates.
Confidence: HIGH
Owner: implementer
Status: OPEN
```

BAD (preference, no consumer, inflated):

```text
ID: contract-005
Severity: BLOCKING
Category: contract
Location: api/schemas/order.ts
Finding: I would prefer snake_case field names.
Why it matters: Consistency.
Evidence: Personal style.
Required resolution: Rename all fields.
Confidence: LOW
Owner: implementer
Status: OPEN
```

What is wrong with it: it is a style preference, no consumer breaks, no class is given, and the "fix" would itself
be a breaking change.

## Out of jurisdiction

- How consumers migrate, rollout and rollback → integration-review.
- Concurrency, retries and timeouts as behaviour under failure → reliability-review (visible cancellation semantics
  stay yours).
- Whether the abstraction behind the contract should exist → simplicity-review.
- Authorization and data exposure as security risks → security-review.

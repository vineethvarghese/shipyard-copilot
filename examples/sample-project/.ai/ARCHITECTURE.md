> 🤖 AGENT FILE. The human is not expected to read this. Human-facing summary: PLAN.HUMAN.md.
## Current state
A library: `Shortener` (service) over `InMemoryStore` (store) with `Link` records; time from an injected clock.
## Target state
`Link` gains an optional `expires_at`; `create` accepts `ttl_seconds`; `resolve` raises `LinkExpired` at or past
`expires_at`. No new modules; one new exception type in `errors.py`.
## Major components + responsibilities
`service.Shortener` (rules), `store.InMemoryStore` (storage), `models.Link` (data), `errors` (public exceptions).
## Dependency direction
service -> store, models, errors. Nothing imports service.
## Data and control flow
create: validate ttl -> build Link(expires_at) -> store. resolve: load -> expiry check -> url.
## Contract boundaries
Public: `Shortener.create`, `Shortener.resolve`, `Link`, `UnknownCode`, `LinkExpired`.
## Concurrency model
None (single-threaded library).
## Failure model
`UnknownCode` for unknown codes; `LinkExpired` for expired ones; `ValueError` for bad ttl.
## Lifecycle
In-memory; nothing persists.
## Configuration
None.
## Observability
None.
## Security assumptions
None (no network, no secrets).
## Migration architecture
Additive; callers that pass no ttl see no change.
## Open architectural questions
None.

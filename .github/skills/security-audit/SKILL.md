---
name: security-audit
description: >
  Security review method for the Shipyard security-reviewer. Load it in SLICE and RECHECK mode to audit a slice diff
  for vulnerabilities with concrete attack paths, and in PLAN mode to threat-model a planned design. Covers web
  flaws (XSS, CSRF, SQL and command injection, XXE, SSRF, open redirect, clickjacking, insecure deserialization),
  credentials and secrets, API flaws (broken authentication, excessive data exposure, missing rate limits, IDOR,
  input validation), and infrastructure-as-code and cloud misconfiguration. Every finding gives an exact location,
  attack path, impact, CWE id and OWASP category, and a minimum secure fix with a corrected snippet. Read-only: no
  exploitation of live systems, no scanning. Not for general reliability or code quality.
---

# Security audit

Version 1.0.0 · used by security-review (`shipyard-security-reviewer`, PLAN, SLICE and RECHECK)

You think like an attacker and write like an engineer. A security finding is worth filing only when you can say
**who** controls the input, **what path** it takes to a dangerous operation, and **what they gain**. Be precise and
do not soften real risk; equally, do not inflate a theoretical weakness with no reachable path.

## Specialisations

| Area | What to look for |
|---|---|
| Web | Cross-site scripting (output not encoded for its context), CSRF (state-changing requests without a token or same-site protection), SQL, NoSQL, LDAP, OS-command and template injection, XML external entities, server-side request forgery, open redirects, clickjacking (no frame protection on sensitive pages), insecure deserialization of untrusted data, path traversal, unrestricted file upload. |
| Credentials and secrets | Hard-coded secrets, keys or tokens; secrets in logs, errors, URLs or client bundles; weak or unsalted password hashing; homemade crypto; keys stored next to the data they protect; tokens without expiry or audience checks; session fixation. |
| API | Broken authentication; missing authorization on an endpoint or field; object-level access by user-controlled id (IDOR); excessive data exposure (returning whole records and filtering in the client); mass assignment; missing rate limits or size limits on expensive or sensitive operations; missing input validation; verbose errors. |
| Infrastructure as code and cloud | Over-broad identity and access policies (wildcard actions or resources), public storage buckets or containers, services or admin ports exposed to the internet, insecure defaults (encryption off, logging off, debug on), privilege-escalation paths (a role that can grant itself more), secrets in templates or pipeline variables in plain text, containers running as root. |
| Supply chain | New dependencies with known vulnerabilities, unpinned versions pulled at build time, scripts piped from the network into a shell. |

## Method

1. **Map the attack surface the change adds or alters.** New endpoints, handlers, message consumers, file parsers,
   CLI flags, scheduled jobs, IaC resources. For each, note who can reach it (anonymous, any user, admin, internal
   service).
2. **Trace untrusted input to sinks.** Sources: request bodies, query strings, headers, cookies, file contents,
   message payloads, environment set by others, data read back from storage that users wrote. Sinks: query
   builders, shells, file paths, HTML output, redirects, outbound HTTP, deserializers, template engines, `eval`-like
   calls. For each source → sink path, check whether validation, parameterization or encoding happens **on that
   path**, not just somewhere.
3. **Authorization on every path.** For each operation, find where the caller's right to do it to *this* object is
   checked. Authentication alone is not authorization. Check every branch, including error paths, bulk endpoints,
   and "internal" routes reachable from outside.
4. **Secrets handling.** Where do secrets come from, where are they stored, where could they leak (logs, errors,
   traces, crash reports, client code)? Never copy a secret value into a finding; give its location only.
5. **Crypto.** Algorithm, mode, key size, randomness source, IV/nonce reuse, constant-time comparison for tokens,
   certificate validation left on.
6. **Resource abuse.** Unbounded sizes, counts or nesting on untrusted input; expensive operations with no rate
   limit; regular expressions that can backtrack catastrophically.
7. **Configuration and IaC.** Defaults, exposure, identity policies, encryption, logging.

Use `references/owasp-cwe-map.md` to pick the CWE id and OWASP category.

## PLAN mode: threat modelling

Read `.ai/PROJECT.md`, `.ai/ARCHITECTURE.md`, `.ai/INVARIANTS.md`, `.ai/CONSUMERS.md` and slice drafts. Draw the
trust boundaries (who talks to what, across which boundary), then ask these questions per boundary and per new
component:

| Threat | Prompt |
|---|---|
| Spoofing | How does each side know who it is talking to? Can a caller claim another identity or tenant? |
| Tampering | Can data be changed in transit, at rest, or by a caller who should only read it? |
| Repudiation | Is there an audit trail for sensitive actions that the actor cannot erase? |
| Information disclosure | What sensitive data crosses the boundary? Is it minimised, encrypted, and kept out of logs? |
| Denial of service | What can an unauthenticated or low-privilege caller make expensive? What bounds it? |
| Elevation of privilege | Which path, if misconfigured, lets a caller act with more rights than granted? |

A plan finding names the boundary, the threat, the missing control, and which slice must add it (often as an AC or
an invariant). Missing controls that a requirement demands are `BLOCKING` at plan stage.

## Finding requirements

Every finding has:

- **Exact location:** `path:line-range` in the diff (or the planning artifact and section in PLAN mode).
- **Attack path:** attacker position → input → path through the code → sink, in one or two sentences.
- **Impact:** what the attacker gains (data read, data changed, account takeover, code execution, service down).
- **Classification:** `Category: security/<class> · CWE-<id> · OWASP <code>`.
- **Rating:** the first words of `Why it matters:` are `Rating: CRITICAL | HIGH | MEDIUM | LOW | INFORMATIONAL.`
- **Minimum secure fix:** `Required resolution:` gives the smallest change that closes the path, with a corrected
  snippet in the repository's language. Prefer the platform's safe primitive (parameterized queries, the
  framework's encoder, a vetted library) over custom code.

## Severity mapping

| Security rating | Shipyard severity | Typical examples |
|---|---|---|
| CRITICAL | BLOCKING | Unauthenticated remote code execution, SQL injection on a public endpoint, hard-coded production credentials. |
| HIGH | BLOCKING | IDOR exposing other users' data, stored XSS, SSRF reaching internal services, auth bypass for logged-in users. |
| MEDIUM | MAJOR | Reflected XSS needing user interaction, missing rate limit on login, verbose errors with internals. |
| LOW | MINOR | Missing hardening header on a non-sensitive page, weak but not exploitable configuration. |
| INFORMATIONAL | NOTE | Defence-in-depth suggestions with no current path. |
| Missing or unclear rating | BLOCKING | If you cannot decide a rating, treat it as BLOCKING and say what evidence would lower it. |

Rate by reachability and impact in this system, not by the class's reputation. Injection behind an admin-only,
internal tool with a parameterized fallback is not the same as on a public endpoint.

## Limits

- **Read-only.** You may read code and run read-only local commands (dependency listings, a local static analyzer
  that changes nothing). You never modify code.
- **No exploitation of live systems.** Never send payloads to a running service, shared environment or third-party
  endpoint. Never run network scanners. A local unit-level proof against code in the workspace is allowed only if it
  touches no network and no shared state.
- **Never copy secrets** into findings, return blocks or `.ai/`. Write `<REDACTED>` and the location.
- No speculative findings without a path. If a path depends on code you were not given, say what you need.

## Finding examples

GOOD (path, impact, CWE and OWASP, corrected snippet):

```text
ID: security-001
Severity: BLOCKING
Category: security/sql-injection · CWE-89 · OWASP A03:2021 Injection
Location: internal/api/invoices.go:42-49
Finding: GET /invoices builds its SQL by concatenating the `status` query parameter into the WHERE clause.
Why it matters: Rating: CRITICAL. Any logged-in user can send `status=' OR '1'='1` and read every tenant's invoices,
  or use stacked queries where the driver allows them to modify data.
Evidence: invoices.go:44 `q := "SELECT * FROM invoices WHERE tenant_id = " + tid + " AND status = '" +
  r.URL.Query().Get("status") + "'"`; the value reaches db.Query at line 47 with no validation.
Required resolution: Use placeholders for both values:
  `rows, err := db.QueryContext(ctx, "SELECT id, amount, status FROM invoices WHERE tenant_id = $1 AND status = $2",
  tid, status)` and reject status values outside the known set.
Confidence: HIGH
Owner: implementer
Status: OPEN
```

BAD (class name only, no path, no fix, secret copied):

```text
ID: security-007
Severity: BLOCKING
Category: security
Location: config/settings.py
Finding: Possible security issue with the API key sk_live_abc123... in settings.
Why it matters: Security is critical.
Evidence: OWASP.
Required resolution: Fix the security issue.
Confidence: LOW
Owner: implementer
Status: OPEN
```

What is wrong with it: it copies a secret into the finding, gives no line, attack path, impact, CWE or rating, and
the resolution is not a fix.

## Out of jurisdiction

- Reliability under load and failure that has no attacker → reliability-review.
- Code clarity, performance and test quality → the code-reviewer's abilities.
- Public API compatibility → contract-review (you still own authorization on that API).
- Production incident response, penetration testing of live systems, and network scanning: never.
